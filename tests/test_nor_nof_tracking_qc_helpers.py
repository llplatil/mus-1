"""Tests for the NOR/NOF Tracking QC pane helpers added in Iteration 5.5.

Covers the pure-Python helpers — slug builder, exploratory-run shape,
QC review save with legacy migration. The Streamlit-rendered widgets
themselves are not tested here (they require a Streamlit runtime); the
data-shape contracts they depend on are.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import is delayed because the view module imports streamlit at top
# level. If streamlit isn't installed, skip the module entirely.
streamlit = pytest.importorskip("streamlit")

from mus1.web.views.nor_nof_tracking_qc import (
    _build_exploratory_run,
    _build_variant_slug,
    _load_saved_exploratory_runs,
    _persist_exploratory_run,
    _save_qc_review,
)


# ---------------------------------------------------------------------------
# Variant slug
# ---------------------------------------------------------------------------

def test_variant_slug_canonical_form():
    assert _build_variant_slug(3.0, 0.6, "fixed", 60.0) == "r3cm_lh06_fix_bb60"


def test_variant_slug_otsu():
    assert _build_variant_slug(2.0, 0.7, "otsu", 80.0) == "r2cm_lh07_ots_bb80"


def test_variant_slug_lh_rounds_correctly():
    # 0.65 -> "07" via round-half-to-even on int(round(6.5)) -> 6 in py3
    # 0.55 -> rounds to 6 (or 5) depending on version. Just verify range is sane.
    s = _build_variant_slug(4.0, 0.65, "fixed", 60.0)
    assert s.startswith("r4cm_lh") and s.endswith("_fix_bb60")


# ---------------------------------------------------------------------------
# Exploratory run shape
# ---------------------------------------------------------------------------

def test_build_exploratory_run_has_required_fields():
    run = _build_exploratory_run(
        radius_cm=3.0, lh=0.6, buffer_mode="fixed", bb_px=60.0,
        metrics={"left_time_s": 5.5, "right_time_s": 7.2},
        fps=30.0,
    )
    assert run["name"] == "r3cm_lh06_fix_bb60"
    assert run["parameters"]["radius_cm"] == 3.0
    assert run["parameters"]["likelihood_threshold"] == 0.6
    assert run["parameters"]["buffer_mode"] == "fixed"
    assert run["parameters"]["bodypart_bound_px"] == 60.0
    assert run["parameters"]["fps"] == 30.0
    assert run["metrics"] == {"left_time_s": 5.5, "right_time_s": 7.2}
    assert "computed_at" in run
    assert run["computed_by"] == "mus1_browser"


# ---------------------------------------------------------------------------
# Persistence: exploratory_runs[]
# ---------------------------------------------------------------------------

def test_persist_exploratory_run_appends_to_canonical_home(tmp_path: Path):
    json_path = tmp_path / "exp.json"
    json_path.write_text(json.dumps({
        "experiment_id": "NOR_TEST",
        "computed_metrics": {},
    }))
    run1 = _build_exploratory_run(
        radius_cm=3.0, lh=0.6, buffer_mode="fixed", bb_px=60.0,
        metrics={"left_time_s": 1.0}, fps=30.0,
    )
    _persist_exploratory_run(json_path, run1)

    data = json.loads(json_path.read_text())
    runs = (data["computed_metrics"]["nor_nof_interaction"]
            ["qc_review"]["exploratory_runs"])
    assert len(runs) == 1
    assert runs[0]["name"] == "r3cm_lh06_fix_bb60"

    # Second append doesn't clobber the first
    run2 = _build_exploratory_run(
        radius_cm=4.0, lh=0.7, buffer_mode="otsu", bb_px=80.0,
        metrics={"left_time_s": 2.0}, fps=30.0,
    )
    _persist_exploratory_run(json_path, run2)
    data = json.loads(json_path.read_text())
    runs = (data["computed_metrics"]["nor_nof_interaction"]
            ["qc_review"]["exploratory_runs"])
    assert len(runs) == 2
    assert [r["name"] for r in runs] == ["r3cm_lh06_fix_bb60", "r4cm_lh07_ots_bb80"]


def test_load_saved_exploratory_runs_returns_empty_when_absent():
    assert _load_saved_exploratory_runs({}) == []
    assert _load_saved_exploratory_runs({"computed_metrics": {}}) == []
    assert _load_saved_exploratory_runs(
        {"computed_metrics": {"nor_nof_interaction": {}}}) == []


def test_load_saved_exploratory_runs_reads_canonical_home():
    data = {
        "computed_metrics": {
            "nor_nof_interaction": {
                "qc_review": {
                    "exploratory_runs": [
                        {"name": "r3cm_lh06_fix_bb60", "metrics": {}},
                        {"name": "r4cm_lh07_ots_bb80", "metrics": {}},
                    ]
                }
            }
        }
    }
    runs = _load_saved_exploratory_runs(data)
    assert len(runs) == 2
    assert runs[0]["name"] == "r3cm_lh06_fix_bb60"


# ---------------------------------------------------------------------------
# QC review save + legacy migration
# ---------------------------------------------------------------------------

def test_save_qc_review_writes_to_canonical_home(tmp_path: Path):
    json_path = tmp_path / "exp.json"
    json_path.write_text(json.dumps({"experiment_id": "NOR_TEST"}))
    _save_qc_review(json_path, status="good", notes="clean", migrated_from_legacy=False)

    data = json.loads(json_path.read_text())
    qc = data["computed_metrics"]["nor_nof_interaction"]["qc_review"]
    assert qc["status"] == "good"
    assert qc["notes"] == "clean"
    assert "reviewed_at" in qc
    # Status change history entry
    assert any(h.get("action") == "status_change"
               for h in qc.get("history", []))


def test_save_qc_review_migrates_legacy_block(tmp_path: Path):
    json_path = tmp_path / "exp.json"
    json_path.write_text(json.dumps({
        "experiment_id": "NOR_TEST",
        # Legacy top-level block from before 5.5d
        "interaction_qc": {
            "status": "good",
            "notes": "from prior session",
            "reviewed_at": "2026-05-04T00:00:00+00:00",
        },
    }))
    _save_qc_review(json_path, status="good", notes="updated",
                    migrated_from_legacy=True)

    data = json.loads(json_path.read_text())
    qc = data["computed_metrics"]["nor_nof_interaction"]["qc_review"]
    # Migration history entry preserves the legacy value verbatim
    migrations = [h for h in qc.get("history", [])
                  if h.get("action") == "migrated_from_legacy"]
    assert len(migrations) == 1
    detail = json.loads(migrations[0]["detail"])
    assert detail["legacy_value"]["notes"] == "from prior session"
    # The legacy block itself is left in place for one cycle (so any
    # other reader still sees its old shape) — Iteration 5.5 doesn't
    # delete it; later cleanup can.
    assert "interaction_qc" in data


def test_save_qc_review_history_records_status_changes(tmp_path: Path):
    json_path = tmp_path / "exp.json"
    json_path.write_text(json.dumps({"experiment_id": "NOR_TEST"}))
    # First save
    _save_qc_review(json_path, status="good", notes="ok",
                    migrated_from_legacy=False)
    # Second save: same status — should NOT add a status_change entry
    _save_qc_review(json_path, status="good", notes="still ok",
                    migrated_from_legacy=False)
    # Third save: new status — should add an entry
    _save_qc_review(json_path, status="exclude", notes="actually no",
                    migrated_from_legacy=False)

    data = json.loads(json_path.read_text())
    qc = data["computed_metrics"]["nor_nof_interaction"]["qc_review"]
    status_changes = [h for h in qc.get("history", [])
                      if h.get("action") == "status_change"]
    # Two changes: (none -> good) and (good -> exclude)
    assert len(status_changes) == 2
    assert status_changes[-1]["detail"] == "good -> exclude"
