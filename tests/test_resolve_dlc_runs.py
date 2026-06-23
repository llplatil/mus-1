"""Tests for the DLC run registry in ``mus1.compute.tracking``.

Covers:
  - derive_run_id prefers scorer, falls back to project__snapshot
  - list_dlc_runs unions dlc_runs[] + legacy, dedups by CSV
  - get_dlc_run / selected_dlc_run lookups
  - resolve_dlc_csv_path precedence: primary > cohort > legacy > last-run
  - resolve_dlc_csv_path back-compat: cohort=None + no primary == original
  - make_dlc_run_entry shape
  - back-compat against real on-disk experiment JSONs (no behavior change)
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from mus1.compute.tracking import (
    DlcRun,
    derive_run_id,
    get_dlc_run,
    list_dlc_runs,
    make_dlc_run_entry,
    resolve_dlc_csv_path,
    selected_dlc_run,
)

DATA_ROOTS = [
    "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/data/experiment_data",
    "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/data/validation_data",
]


# ---------------------------------------------------------------------------
# Fixtures: synthetic extraction dicts
# ---------------------------------------------------------------------------

def _legacy_ext() -> dict:
    """Publication-batch schema: flat tracking_file_path + dlc_model_path."""
    return {
        "tracking_file_path": "/data/v1/EZM_429_v1.csv",
        "dlc_model_path": "DLC_Resnet50_EZM_v1Dec10shuffle1_snapshot_best-90",
    }


def _two_run_ext(primary_idx: int | None = None) -> dict:
    """validation_2026 schema: two dlc_runs entries (v1 then v2)."""
    runs = [
        {
            "analysis_at": "2026-05-03T00:00:00Z",
            "dlc_project": "EZM_training_subset_30videos_20251210_191825-llplatil-x",
            "scorer": "DLC_Resnet50_EZM_v1Dec10shuffle1_snapshot_best-90",
            "shuffle": 1,
            "snapshot": "snapshot-best-90",
            "output": {"csv": "/data/v1.csv", "h5": "/data/v1.h5"},
        },
        {
            "analysis_at": "2026-05-21T00:00:00Z",
            "dlc_project": "EZM_v2_40videos_20260505",
            "scorer": "DLC_Resnet50_EZM_v2Dec10shuffle1_snapshot_best-160",
            "shuffle": 1,
            "snapshot": "snapshot-best-160",
            "output": {"csv": "/data/v2.csv", "h5": "/data/v2.h5"},
        },
    ]
    if primary_idx is not None:
        runs[primary_idx]["primary"] = True
    return {"dlc_runs": runs}


V1_ID = "DLC_Resnet50_EZM_v1Dec10shuffle1_snapshot_best-90"
V2_ID = "DLC_Resnet50_EZM_v2Dec10shuffle1_snapshot_best-160"


# ---------------------------------------------------------------------------
# derive_run_id
# ---------------------------------------------------------------------------

def test_derive_run_id_prefers_scorer():
    assert derive_run_id("DLC_Resnet50_X", "ProjA", "snapshot-best-90") == "DLC_Resnet50_X"


def test_derive_run_id_falls_back_to_project_snapshot():
    assert derive_run_id("", "/abs/path/EZM_v2_40videos_20260505", "snapshot-best-160") == (
        "EZM_v2_40videos_20260505__snapshot-best-160"
    )


def test_derive_run_id_empty_when_nothing():
    assert derive_run_id("", "", "") == ""


# ---------------------------------------------------------------------------
# list_dlc_runs
# ---------------------------------------------------------------------------

def test_list_dlc_runs_legacy_single():
    runs = list_dlc_runs(_legacy_ext())
    assert len(runs) == 1
    assert runs[0].source == "legacy"
    assert runs[0].run_id == V1_ID
    assert runs[0].csv_path == "/data/v1/EZM_429_v1.csv"
    assert runs[0].primary is False


def test_list_dlc_runs_two_runs():
    runs = list_dlc_runs(_two_run_ext())
    assert [r.run_id for r in runs] == [V1_ID, V2_ID]
    assert all(r.source == "dlc_runs" for r in runs)
    assert runs[1].snapshot == "snapshot-best-160"


def test_list_dlc_runs_dedup_legacy_against_dlc_runs():
    # Legacy CSV equal to a dlc_runs CSV must not produce a duplicate entry.
    ext = _two_run_ext()
    ext["tracking_file_path"] = "/data/v2.csv"
    ext["dlc_model_path"] = V2_ID
    runs = list_dlc_runs(ext)
    assert len(runs) == 2  # legacy folded out
    assert sum(1 for r in runs if r.csv_path == "/data/v2.csv") == 1


def test_list_dlc_runs_non_dict_returns_empty():
    assert list_dlc_runs(None) == []
    assert list_dlc_runs("nope") == []


# ---------------------------------------------------------------------------
# get_dlc_run / selected_dlc_run
# ---------------------------------------------------------------------------

def test_get_dlc_run_found_and_missing():
    ext = _two_run_ext()
    assert get_dlc_run(ext, V2_ID).csv_path == "/data/v2.csv"
    assert get_dlc_run(ext, "nonexistent") is None
    assert get_dlc_run(ext, "") is None


def test_selected_dlc_run_matches_resolver():
    ext = _two_run_ext()
    run = selected_dlc_run(ext)
    # No primary, no cohort -> last dlc_runs entry (v2)
    assert run is not None
    assert run.csv_path == "/data/v2.csv"


# ---------------------------------------------------------------------------
# resolve_dlc_csv_path precedence
# ---------------------------------------------------------------------------

def test_resolve_primary_override_wins():
    ext = _two_run_ext(primary_idx=0)  # mark v1 primary
    # Even with a cohort selecting v2, primary v1 wins.
    cohort = {"analysis_config": {"dlc_model": {"run_id": V2_ID}}}
    assert resolve_dlc_csv_path(ext, cohort=cohort) == "/data/v1.csv"


def test_resolve_cohort_selection():
    ext = _two_run_ext()
    cohort = {"analysis_config": {"dlc_model": {"run_id": V1_ID}}}
    assert resolve_dlc_csv_path(ext, cohort=cohort) == "/data/v1.csv"
    cohort2 = {"analysis_config": {"dlc_model": {"run_id": V2_ID}}}
    assert resolve_dlc_csv_path(ext, cohort=cohort2) == "/data/v2.csv"


def test_resolve_cohort_selection_unknown_run_falls_through():
    ext = _two_run_ext()
    cohort = {"analysis_config": {"dlc_model": {"run_id": "does-not-exist"}}}
    # Falls through to last dlc_runs entry.
    assert resolve_dlc_csv_path(ext, cohort=cohort) == "/data/v2.csv"


def test_resolve_legacy_precedence_over_dlc_runs():
    ext = _two_run_ext()
    ext["tracking_file_path"] = "/data/legacy.csv"
    ext["dlc_model_path"] = "DLC_legacy"
    # No primary, no cohort -> legacy wins (original behavior).
    assert resolve_dlc_csv_path(ext) == "/data/legacy.csv"


def test_resolve_no_cohort_no_primary_is_last_run():
    assert resolve_dlc_csv_path(_two_run_ext()) == "/data/v2.csv"


def test_resolve_non_dict():
    assert resolve_dlc_csv_path(None) == ""
    assert resolve_dlc_csv_path("x") == ""


# ---------------------------------------------------------------------------
# make_dlc_run_entry
# ---------------------------------------------------------------------------

def test_make_dlc_run_entry_shape():
    entry = make_dlc_run_entry(
        dlc_project="EZM_v2_40videos_20260505",
        snapshot="snapshot-best-160",
        csv="/out/v2.csv",
        scorer="DLC_Resnet50_EZM_v2",
        shuffle=1,
        h5="/out/v2.h5",
        note="registered by test",
        primary=True,
    )
    assert entry["output"] == {"csv": "/out/v2.csv", "h5": "/out/v2.h5"}
    assert entry["run_id"] == "DLC_Resnet50_EZM_v2"
    assert entry["primary"] is True
    assert entry["note"] == "registered by test"
    assert "analysis_at" in entry
    # Round-trips through list_dlc_runs.
    runs = list_dlc_runs({"dlc_runs": [entry]})
    assert runs[0].run_id == "DLC_Resnet50_EZM_v2"
    assert runs[0].primary is True


def test_make_dlc_run_entry_omits_primary_when_false():
    entry = make_dlc_run_entry(
        dlc_project="P", snapshot="s", csv="/c.csv", scorer="DLC_x"
    )
    assert "primary" not in entry
    assert "note" not in entry


# ---------------------------------------------------------------------------
# Back-compat against real on-disk JSONs
# ---------------------------------------------------------------------------

def _iter_real_extractions():
    for root in DATA_ROOTS:
        for jp in glob.glob(f"{root}/*/*/*.json"):
            try:
                data = json.loads(Path(jp).read_text())
            except Exception:
                continue
            ext = data.get("extraction")
            if isinstance(ext, dict):
                yield jp, ext


def _original_resolver(extraction) -> str:
    """Verbatim copy of the pre-change resolver, for differential testing."""
    if not isinstance(extraction, dict):
        return ""
    legacy = extraction.get("tracking_file_path") or ""
    if legacy:
        return legacy
    runs = extraction.get("dlc_runs") or []
    if runs:
        last = runs[-1] if isinstance(runs[-1], dict) else {}
        out = last.get("output") or {}
        return out.get("csv") or ""
    return ""


def test_back_compat_against_real_jsons():
    """With cohort=None, the new resolver must equal the original on every
    real experiment JSON. Skips if data roots are not present."""
    samples = list(_iter_real_extractions())
    if not samples:
        pytest.skip("canonical data roots not available in this environment")
    mismatches = []
    for jp, ext in samples:
        new = resolve_dlc_csv_path(ext)
        old = _original_resolver(ext)
        if new != old:
            mismatches.append((jp, old, new))
    assert not mismatches, f"{len(mismatches)} resolver mismatches, e.g. {mismatches[:3]}"
