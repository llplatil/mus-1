"""Tests for the ``mus1 arena-inference`` CLI (T14).

Covers the generic driver in :mod:`mus1.core.arena_inference_cli` plus
the back-compat ``mus1 ezm-arena-infer`` wrapper. Uses
``typer.testing.CliRunner`` against the top-level ``app`` so we exercise
typer's argument parsing + exit-code propagation.

Heavy paths (real torch / cv2) are stubbed via monkeypatching
``mus1.compute.arena_unet.load_arena_unet`` and friends so the suite
stays fast and does not require GPU.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from mus1.core.simple_cli import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Help-surface tests (no project fixture required)
# ---------------------------------------------------------------------------

def test_arena_inference_help_lists_run_subcommand():
    """`arena-inference --help` mentions the ``run`` subcommand."""
    result = runner.invoke(app, ["arena-inference", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    # Description from the typer.Typer help= kwarg
    assert "Profile-aware arena U-Net" in result.stdout


def test_arena_inference_run_help_lists_flags():
    """`arena-inference run --help` shows the required flags."""
    result = runner.invoke(app, ["arena-inference", "run", "--help"])
    assert result.exit_code == 0
    # Argument
    assert "profile_id" in result.stdout.lower() or "PROFILE_ID" in result.stdout
    # Options
    for flag in ("--cohort", "--project-path", "--frames-per-video",
                  "--overwrite", "--dry-run", "--json-out", "--limit"):
        assert flag in result.stdout, f"missing flag: {flag}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_with_cohort(tmp_path: Path) -> Path:
    """Set up a minimal project containing a cohorts/ dir + one cohort JSON."""
    (tmp_path / "cohorts").mkdir()
    (tmp_path / "experiment_data" / "EZM").mkdir(parents=True)
    cohort_path = tmp_path / "cohorts" / "fake_cohort.json"
    cohort_path.write_text(json.dumps({
        "name": "fake_cohort",
        "members": [
            {"experiment_id": "EZM_001_2026-01-01"},
            {"experiment_id": "EZM_002_2026-01-02"},
        ],
    }))
    return tmp_path


def _write_arena_models_yaml(project_path: Path, ckpt: Path,
                              run_id: str = "test_run_001") -> None:
    """Drop an arena_models.yaml that activates ezm_460mm against *ckpt*."""
    (project_path / "arena_models.yaml").write_text(
        "arena_models:\n"
        "  ezm_460mm:\n"
        "    active:\n"
        f"      run_id: {run_id}\n"
        f"      checkpoint: {ckpt}\n"
        "      n_classes: 3\n"
        "      mask_to_marking: ezm_wedge_points\n"
        "      activated_at: '2026-05-13T00:00:00Z'\n"
        "      notes: 'test'\n"
    )


def _make_experiment(project_path: Path, eid: str, task: str = "EZM",
                      *, video_path: str = "", with_predicted: bool = False) -> Path:
    """Materialise a stub experiment folder + JSON. Returns the JSON path."""
    exp_dir = project_path / "experiment_data" / task / eid
    exp_dir.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {
        "experiment_id": eid,
        "video": {"path": video_path},
        "arena_markings": {},
    }
    if with_predicted:
        data["arena_markings"]["predicted"] = {
            "ezm_wedge_points": {
                "points": [[1.0, 1.0]] * 4,
                "qc_status": "predicted_unreviewed",
            }
        }
    jp = exp_dir / f"{eid}.json"
    jp.write_text(json.dumps(data, indent=2) + "\n")
    return jp


# ---------------------------------------------------------------------------
# Validation / error-path tests
# ---------------------------------------------------------------------------

def test_unknown_profile_exits_nonzero(project_with_cohort: Path):
    """Bad profile_id → exit 2 + helpful listing of available profiles."""
    result = runner.invoke(app, [
        "arena-inference", "run", "totally_made_up_profile",
        "--cohort", "fake_cohort",
        "--project-path", str(project_with_cohort),
        "--dry-run",
    ])
    assert result.exit_code == 2
    assert "Unknown arena profile" in result.stdout
    # Lists available profile ids
    assert "ezm_460mm" in result.stdout


def test_missing_arena_models_yaml_exits_2(project_with_cohort: Path):
    """No arena_models.yaml → exit 2 ('no active arena U-Net')."""
    result = runner.invoke(app, [
        "arena-inference", "run", "ezm_460mm",
        "--cohort", "fake_cohort",
        "--project-path", str(project_with_cohort),
        "--dry-run",
    ])
    assert result.exit_code == 2
    assert "No active arena U-Net" in result.stdout


def test_missing_cohort_file_exits_3(tmp_path: Path):
    """Cohort JSON absent → exit 3."""
    (tmp_path / "cohorts").mkdir()
    result = runner.invoke(app, [
        "arena-inference", "run", "ezm_460mm",
        "--cohort", "no_such_cohort",
        "--project-path", str(tmp_path),
        "--dry-run",
    ])
    assert result.exit_code == 3
    assert "Cohort file not found" in result.stdout


def test_empty_cohort_exits_3(tmp_path: Path):
    """Cohort file present but no members → exit 3."""
    (tmp_path / "cohorts").mkdir()
    (tmp_path / "cohorts" / "empty.json").write_text(json.dumps({"members": []}))
    result = runner.invoke(app, [
        "arena-inference", "run", "ezm_460mm",
        "--cohort", "empty",
        "--project-path", str(tmp_path),
        "--dry-run",
    ])
    assert result.exit_code == 3
    assert "No experiments" in result.stdout


# ---------------------------------------------------------------------------
# Dry-run / write-path tests (mock the loader to avoid torch)
# ---------------------------------------------------------------------------

def _make_fake_model(run_id: str = "test_run_001") -> MagicMock:
    """Return a stub model with the T8 attribute tags set."""
    m = MagicMock()
    m._mus1_run_id = run_id
    m._mus1_profile_id = "ezm_460mm"
    m._mus1_mask_to_marking = "ezm_wedge_points"
    return m


def test_dry_run_does_not_write_jsons(project_with_cohort: Path, monkeypatch):
    """End-to-end dry-run: model load + sampling stubs return data, but no
    JSON should be touched on disk."""
    proj = project_with_cohort
    ckpt = proj / "model_best.pt"
    ckpt.write_bytes(b"fake-checkpoint")
    _write_arena_models_yaml(proj, ckpt)

    video_path = str(proj / "fake.mp4")
    jp1 = _make_experiment(proj, "EZM_001_2026-01-01", video_path=video_path)
    jp2 = _make_experiment(proj, "EZM_002_2026-01-02", video_path=video_path)
    original_jp1 = jp1.read_text()
    original_jp2 = jp2.read_text()

    # Stub heavy CV / model paths
    import mus1.core.arena_inference_cli as cli_mod
    import mus1.compute.arena_unet as au_mod

    monkeypatch.setattr(au_mod, "load_arena_unet",
                         lambda profile_id, project_path: _make_fake_model())
    monkeypatch.setattr(au_mod, "sample_video_frame",
                         lambda vp, fi: __import__("numpy").zeros((480, 640), dtype="uint8"))
    monkeypatch.setattr(au_mod, "infer_arena_mask",
                         lambda model, frame: (
                             __import__("numpy").zeros((256, 256), dtype="uint8"),
                             type("M", (), {"src_h": 480, "src_w": 640,
                                              "pad_top": 0, "pad_left": 0,
                                              "pad_size": 640, "out_size": 256})(),
                         ))
    monkeypatch.setattr(au_mod, "run_post_processor",
                         lambda name, mask, meta, **kw: {
                             "points": [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
                             "ellipse_orig": {"center_xy": [0.0, 0.0],
                                                "axes_xy": [1.0, 1.0], "angle_deg": 0.0},
                             "quality": {"open_pixel_fraction": 0.1},
                         })
    monkeypatch.setattr(au_mod, "model_run_id", lambda m: m._mus1_run_id)
    monkeypatch.setattr(au_mod, "model_version_string",
                         lambda p: "fake_runs@fake_best@sha256:deadbeefdeadbeef")

    # Stub cv2.VideoCapture so we don't need a real video file.
    class _FakeCap:
        def __init__(self, *a, **kw): pass
        def get(self, _): return 600  # 600 frames
        def release(self): pass
    monkeypatch.setattr("cv2.VideoCapture", _FakeCap)
    # Create the fake video file so Path(vpath).exists() returns True.
    Path(video_path).write_bytes(b"\x00")

    result = runner.invoke(app, [
        "arena-inference", "run", "ezm_460mm",
        "--cohort", "fake_cohort",
        "--project-path", str(proj),
        "--frames-per-video", "3",
        "--dry-run",
    ])
    assert result.exit_code == 0, result.stdout
    assert "Predicted: 2/2" in result.stdout
    # JSONs MUST be byte-identical (dry-run)
    assert jp1.read_text() == original_jp1
    assert jp2.read_text() == original_jp2


def test_write_includes_run_id_and_version(project_with_cohort: Path, monkeypatch):
    """Real-write path: predicted block carries model_run_id + model_version."""
    proj = project_with_cohort
    ckpt = proj / "model_best.pt"
    ckpt.write_bytes(b"fake-checkpoint")
    _write_arena_models_yaml(proj, ckpt, run_id="anchor_run_42")

    video_path = str(proj / "fake.mp4")
    jp = _make_experiment(proj, "EZM_001_2026-01-01", video_path=video_path)

    import mus1.compute.arena_unet as au_mod
    monkeypatch.setattr(au_mod, "load_arena_unet",
                         lambda profile_id, project_path: _make_fake_model("anchor_run_42"))
    monkeypatch.setattr(au_mod, "sample_video_frame",
                         lambda vp, fi: __import__("numpy").zeros((480, 640), dtype="uint8"))
    monkeypatch.setattr(au_mod, "infer_arena_mask",
                         lambda model, frame: (
                             __import__("numpy").zeros((256, 256), dtype="uint8"),
                             type("M", (), {"src_h": 480, "src_w": 640,
                                              "pad_top": 0, "pad_left": 0,
                                              "pad_size": 640, "out_size": 256})(),
                         ))
    monkeypatch.setattr(au_mod, "run_post_processor",
                         lambda name, mask, meta, **kw: {
                             "points": [[10.0, 20.0]] * 4,
                             "ellipse_orig": {"center_xy": [320.0, 240.0],
                                                "axes_xy": [200.0, 200.0],
                                                "angle_deg": 0.0},
                             "quality": {"open_pixel_fraction": 0.3},
                         })
    monkeypatch.setattr(au_mod, "model_run_id", lambda m: m._mus1_run_id)
    monkeypatch.setattr(au_mod, "model_version_string",
                         lambda p: "fake_runs@fake_best@sha256:cafebabecafebabe")

    class _FakeCap:
        def __init__(self, *a, **kw): pass
        def get(self, _): return 600
        def release(self): pass
    monkeypatch.setattr("cv2.VideoCapture", _FakeCap)
    Path(video_path).write_bytes(b"\x00")

    result = runner.invoke(app, [
        "arena-inference", "run", "ezm_460mm",
        "--cohort", "fake_cohort",
        "--project-path", str(proj),
        "--frames-per-video", "3",
        "--limit", "1",
    ])
    assert result.exit_code == 0, result.stdout

    data = json.loads(jp.read_text())
    predicted = data["arena_markings"]["predicted"]["ezm_wedge_points"]
    assert predicted["model_run_id"] == "anchor_run_42"
    assert predicted["model_version"].startswith("fake_runs@fake_best@sha256:")
    assert predicted["qc_status"] == "predicted_unreviewed"
    assert predicted["n_frames_sampled"] == 3
    assert predicted["frame_shape"] == [480, 640]
    # ezm_wedge_points always carries 4 (x, y) points
    assert len(predicted["points"]) == 4


def test_predicted_existing_skipped_without_overwrite(project_with_cohort: Path, monkeypatch):
    """An experiment that already has a predicted block is skipped unless
    --overwrite is set."""
    proj = project_with_cohort
    ckpt = proj / "model_best.pt"
    ckpt.write_bytes(b"fake-checkpoint")
    _write_arena_models_yaml(proj, ckpt)

    video_path = str(proj / "fake.mp4")
    _make_experiment(proj, "EZM_001_2026-01-01", video_path=video_path,
                       with_predicted=True)
    _make_experiment(proj, "EZM_002_2026-01-02", video_path=video_path,
                       with_predicted=True)

    import mus1.compute.arena_unet as au_mod
    monkeypatch.setattr(au_mod, "load_arena_unet",
                         lambda profile_id, project_path: _make_fake_model())
    monkeypatch.setattr(au_mod, "model_run_id", lambda m: m._mus1_run_id)
    monkeypatch.setattr(au_mod, "model_version_string",
                         lambda p: "fake_runs@fake_best@sha256:1234567890abcdef")

    result = runner.invoke(app, [
        "arena-inference", "run", "ezm_460mm",
        "--cohort", "fake_cohort",
        "--project-path", str(proj),
        "--dry-run",
    ])
    assert result.exit_code == 0, result.stdout
    assert "skipped_existing: 2" in result.stdout


def test_legacy_ezm_arena_infer_still_works(project_with_cohort: Path, monkeypatch):
    """The deprecated ``ezm-arena-infer`` command keeps working and emits the
    deprecation tip."""
    proj = project_with_cohort
    ckpt = proj / "model_best.pt"
    ckpt.write_bytes(b"fake-checkpoint")
    _write_arena_models_yaml(proj, ckpt)

    # Make the wrapper's default project-root resolution land here.
    monkeypatch.setenv("MOSEQ2_PROJECT_PATH", str(proj.parent))
    # The wrapper looks for proj.parent/data; symlink data -> our tmp project
    parent = proj.parent
    data_link = parent / "data"
    if not data_link.exists():
        data_link.symlink_to(proj, target_is_directory=True)

    video_path = str(proj / "fake.mp4")
    # Both cohort members must exist on disk so we don't report failures.
    _make_experiment(proj, "EZM_001_2026-01-01", video_path=video_path,
                       with_predicted=True)
    _make_experiment(proj, "EZM_002_2026-01-02", video_path=video_path,
                       with_predicted=True)

    import mus1.compute.arena_unet as au_mod
    monkeypatch.setattr(au_mod, "load_arena_unet",
                         lambda profile_id, project_path: _make_fake_model())
    monkeypatch.setattr(au_mod, "model_run_id", lambda m: m._mus1_run_id)
    monkeypatch.setattr(au_mod, "model_version_string",
                         lambda p: "legacy@runs@sha256:abcd0123abcd0123")

    result = runner.invoke(app, [
        "ezm-arena-infer",
        "--cohort", "fake_cohort",
        "--dry-run",
    ])
    assert result.exit_code == 0, result.stdout
    assert "is the new canonical form" in result.stdout
