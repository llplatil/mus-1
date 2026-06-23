"""Tests for the ``mus1 tracking`` CLI.

Covers register-run (CSV discovery, idempotency, --primary, --dry-run),
list-runs, compare (rollup), set-cohort-model (guard + write), and
set-primary (set/clear/guard). Uses ``typer.testing.CliRunner`` against a
synthetic project tree with real (tiny) DLC CSVs on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from mus1.core.simple_cli import app

runner = CliRunner()

BPS = ["nose", "head", "tail_base"]
V1_SCORER = "DLC_Resnet50_EZM_v1Dec10shuffle1_snapshot_best-90"
V2_SCORER = "DLC_Resnet50_EZM_v2Dec10shuffle1_snapshot_best-160"


def _write_dlc_csv(path: Path, *, n: int, shift: float = 0.0, lh: float = 0.9) -> None:
    cols, data = [], {}
    scorer = "S"
    for bp in BPS:
        cols += [(scorer, bp, "x"), (scorer, bp, "y"), (scorer, bp, "likelihood")]
        data[(scorer, bp, "x")] = np.linspace(100, 200, n) + shift
        data[(scorer, bp, "y")] = np.linspace(100, 200, n)
        data[(scorer, bp, "likelihood")] = np.full(n, lh)
    df = pd.DataFrame(data, columns=pd.MultiIndex.from_tuples(cols))
    df.index.name = "scorer"
    df.to_csv(path)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Project tree: 2 EZM experiments (each with a v1 dlc_runs entry +
    recording video), a cohort, and a v2 inference dir with matching CSVs.

    Mirrors production layout: the project root (``data/``) and
    ``dlc_workspace/`` are siblings, so register-run's default CSV-dir
    resolution (``project.parent / dlc_workspace / projects``) works.
    """
    proj = tmp_path / "data"
    (proj / "cohorts").mkdir(parents=True)
    exp_root = proj / "experiment_data" / "EZM"
    # dlc_workspace is a SIBLING of the project dir (as in production).
    v1_dir = tmp_path / "dlc_workspace" / "projects" / "EZM_v1" / "inference-results-pytorch"
    v2_dir = tmp_path / "dlc_workspace" / "projects" / "EZM_v2_40videos_20260505" / "inference-results-pytorch" / "batchX"
    v1_dir.mkdir(parents=True)
    v2_dir.mkdir(parents=True)

    members = []
    for i, eid in enumerate(["EZM_001_2026-01-01", "EZM_002_2026-01-02"]):
        edir = exp_root / eid
        edir.mkdir(parents=True)
        (edir / "recording").mkdir()
        stem = f"vid_{i}"
        video = edir / "recording" / f"{stem}.mp4"
        video.write_bytes(b"\x00")  # placeholder; never decoded in these tests

        v1_csv = v1_dir / f"{stem}{V1_SCORER}.csv"
        v2_csv = v2_dir / f"{stem}{V2_SCORER}.csv"
        _write_dlc_csv(v1_csv, n=30, shift=0.0)
        # v2 shifted by 2px on experiment 0, identical on experiment 1.
        _write_dlc_csv(v2_csv, n=30, shift=(2.0 if i == 0 else 0.0))

        (edir / f"{eid}.json").write_text(json.dumps({
            "experiment_id": eid,
            "video": {"path": str(video), "filename": f"{stem}.mp4"},
            "extraction": {
                "dlc_runs": [{
                    "analysis_at": "2026-05-03T00:00:00Z",
                    "dlc_project": "EZM_v1",
                    "scorer": V1_SCORER,
                    "shuffle": 1,
                    "snapshot": "snapshot-best-90",
                    "output": {"csv": str(v1_csv), "h5": ""},
                }],
            },
        }, indent=2))
        members.append({"experiment_id": eid})

    (proj / "cohorts" / "valc.json").write_text(json.dumps({
        "name": "valc", "task_types": ["EZM"], "members": members,
    }))
    return proj


def _read_runs(proj: Path, eid: str) -> list:
    jp = proj / "experiment_data" / "EZM" / eid / f"{eid}.json"
    return json.loads(jp.read_text())["extraction"]["dlc_runs"]


# ---------------------------------------------------------------------------
# register-run
# ---------------------------------------------------------------------------

def test_register_run_dry_run_does_not_write(project):
    r = runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--dry-run", "--json",
    ])
    assert r.exit_code == 0, r.stdout
    payload = json.loads(r.stdout)
    assert all(row["status"] == "registered" for row in payload)
    # Nothing persisted.
    assert len(_read_runs(project, "EZM_001_2026-01-01")) == 1


def test_register_run_writes_and_is_idempotent(project):
    args = [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write", "--json",
    ]
    r1 = runner.invoke(app, args)
    assert r1.exit_code == 0, r1.stdout
    runs = _read_runs(project, "EZM_001_2026-01-01")
    assert len(runs) == 2
    assert runs[1]["run_id"] == V2_SCORER
    assert runs[1]["scorer"] == V2_SCORER  # inferred from filename

    # Re-run: idempotent, no duplicate.
    r2 = runner.invoke(app, args)
    payload = json.loads(r2.stdout)
    assert all(row["status"] == "already_registered" for row in payload)
    assert len(_read_runs(project, "EZM_001_2026-01-01")) == 2


def test_register_run_primary_clears_others(project):
    r = runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write", "--primary",
    ])
    assert r.exit_code == 0, r.stdout
    runs = _read_runs(project, "EZM_001_2026-01-01")
    primaries = [x for x in runs if x.get("primary")]
    assert len(primaries) == 1
    assert primaries[0]["run_id"] == V2_SCORER


def test_register_run_pending_when_no_csv(project):
    r = runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "no-such-snap",
        "--csv-dir", str(project / "nonexistent"),
        "--project-path", str(project), "--write", "--json",
    ])
    assert r.exit_code == 0
    payload = json.loads(r.stdout)
    assert all(row["status"] == "pending" for row in payload)


# ---------------------------------------------------------------------------
# list-runs
# ---------------------------------------------------------------------------

def test_list_runs(project):
    runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write",
    ])
    r = runner.invoke(app, [
        "tracking", "list-runs", "EZM_001_2026-01-01",
        "--project-path", str(project), "--json",
    ])
    assert r.exit_code == 0, r.stdout
    payload = json.loads(r.stdout)
    ids = {run["run_id"] for run in payload["runs"]}
    assert ids == {V1_SCORER, V2_SCORER}
    assert all(run["csv_exists"] for run in payload["runs"])


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

def test_compare_rollup(project):
    runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write",
    ])
    out = project / "rollup.json"
    r = runner.invoke(app, [
        "tracking", "compare", "--cohort", "valc",
        "--run-a", V1_SCORER, "--run-b", V2_SCORER,
        "--project-path", str(project), "--out", str(out), "--json",
    ])
    assert r.exit_code == 0, r.stdout
    rollup = json.loads(out.read_text())
    assert rollup["n_compared"] == 2
    assert rollup["status_counts"].get("ok") == 2
    # exp0 was shifted 2px, exp1 identical -> nonzero median distance somewhere.
    per = {p["experiment_id"]: p for p in rollup["per_experiment"]}
    assert per["EZM_001_2026-01-01"]["per_bodypart"]["nose"]["median_distance_px"] == pytest.approx(2.0)
    assert per["EZM_002_2026-01-02"]["per_bodypart"]["nose"]["median_distance_px"] == pytest.approx(0.0)


def test_compare_missing_run(project):
    r = runner.invoke(app, [
        "tracking", "compare", "--cohort", "valc",
        "--run-a", V1_SCORER, "--run-b", "DLC_unregistered",
        "--project-path", str(project), "--json",
    ])
    assert r.exit_code == 0
    rollup = json.loads(r.stdout)
    assert rollup["status_counts"].get("missing_run") == 2
    assert rollup["n_compared"] == 0


# ---------------------------------------------------------------------------
# set-cohort-model
# ---------------------------------------------------------------------------

def test_set_cohort_model_guard_when_unregistered(project):
    r = runner.invoke(app, [
        "tracking", "set-cohort-model", "--cohort", "valc",
        "--run-id", V2_SCORER, "--project-path", str(project),
    ])
    assert r.exit_code == 1
    assert "not registered" in r.stderr


def test_set_cohort_model_writes_after_register(project):
    runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write",
    ])
    r = runner.invoke(app, [
        "tracking", "set-cohort-model", "--cohort", "valc",
        "--run-id", V2_SCORER, "--basis", "v2 better on tail_base",
        "--project-path", str(project),
    ])
    assert r.exit_code == 0, r.stdout
    cohort = json.loads((project / "cohorts" / "valc.json").read_text())
    dm = cohort["analysis_config"]["dlc_model"]
    assert dm["run_id"] == V2_SCORER
    assert dm["snapshot"] == "snapshot-best-160"
    assert dm["basis"] == "v2 better on tail_base"
    assert dm["selected_by"] == "cli"


def test_set_cohort_model_then_resolver_picks_v2(project):
    """End-to-end: register v2, select it cohort-wide, resolver returns v2 CSV."""
    from mus1.compute.tracking import resolve_dlc_csv_path
    from mus1.web.cohorts import load_cohort

    runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write",
    ])
    runner.invoke(app, [
        "tracking", "set-cohort-model", "--cohort", "valc",
        "--run-id", V2_SCORER, "--project-path", str(project),
    ])
    cohort = load_cohort(project / "cohorts" / "valc.json")
    ext = json.loads(
        (project / "experiment_data" / "EZM" / "EZM_001_2026-01-01"
         / "EZM_001_2026-01-01.json").read_text())["extraction"]
    # With cohort context -> v2; without -> original (last run == v2 here too,
    # so assert the path contains the v2 project to be meaningful).
    chosen = resolve_dlc_csv_path(ext, cohort=cohort)
    assert "EZM_v2_40videos_20260505" in chosen


# ---------------------------------------------------------------------------
# set-primary
# ---------------------------------------------------------------------------

def test_set_primary_set_and_clear(project):
    runner.invoke(app, [
        "tracking", "register-run", "--cohort", "valc",
        "--dlc-project", "EZM_v2_40videos_20260505", "--snapshot", "snapshot-best-160",
        "--project-path", str(project), "--write",
    ])
    r = runner.invoke(app, [
        "tracking", "set-primary", "EZM_001_2026-01-01",
        "--run-id", V1_SCORER, "--project-path", str(project),
    ])
    assert r.exit_code == 0, r.stdout
    runs = _read_runs(project, "EZM_001_2026-01-01")
    # The pre-existing v1 entry stores `scorer` (run_id is derived on read).
    assert [x for x in runs if x.get("primary")][0]["scorer"] == V1_SCORER

    # Clear.
    r2 = runner.invoke(app, [
        "tracking", "set-primary", "EZM_001_2026-01-01",
        "--clear", "--project-path", str(project),
    ])
    assert r2.exit_code == 0
    runs = _read_runs(project, "EZM_001_2026-01-01")
    assert not any(x.get("primary") for x in runs)


def test_set_primary_guard_unknown_run(project):
    r = runner.invoke(app, [
        "tracking", "set-primary", "EZM_001_2026-01-01",
        "--run-id", "DLC_unknown", "--project-path", str(project),
    ])
    assert r.exit_code == 1
    assert "not registered" in r.stderr


def test_set_primary_requires_exactly_one_mode(project):
    r = runner.invoke(app, [
        "tracking", "set-primary", "EZM_001_2026-01-01",
        "--project-path", str(project),
    ])
    assert r.exit_code == 2  # neither --run-id nor --clear
