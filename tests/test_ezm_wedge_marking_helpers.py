"""Tests for the EZM wedge marking save path (T16).

These exercise ``_save_wedge_marking`` directly. The Streamlit canvas
helper ``_render_canvas_and_save`` can't be unit-tested without a
Streamlit runtime, but its save behavior delegates to this function,
so covering the save contract here gives both render paths (annotator-
integrated and standalone) parity in their JSON output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from mus1.web.views.ezm_wedge_marking import _save_wedge_marking


def _read(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text())


def _seed_experiment_json(tmp_path: Path) -> Path:
    p = tmp_path / "EZM_test.json"
    p.write_text(json.dumps({
        "experiment_id": "EZM_test",
        "metadata": {"experiment_type": "EZM"},
        "arena_markings": {},
    }))
    return p


# ---------------------------------------------------------------------------
# Save contract — both render paths route through here
# ---------------------------------------------------------------------------

def test_save_manual_writes_provenance_manual(tmp_path: Path):
    jp = _seed_experiment_json(tmp_path)
    pts = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
    )
    data = _read(jp)
    block = data["arena_markings"]["ezm_wedge_points"]
    assert block["points"] == pts
    assert block["provenance"]["method"] == "manual"
    # No model_run_id / edits for manual saves
    assert "model_run_id" not in block["provenance"]
    assert "edits" not in block["provenance"]


def test_save_with_matching_suggestion_writes_accepted(tmp_path: Path):
    jp = _seed_experiment_json(tmp_path)
    pts = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
        suggested_points=pts, model_run_id="r-20260101",
    )
    block = _read(jp)["arena_markings"]["ezm_wedge_points"]
    assert block["provenance"]["method"] == "unet_suggested+human_accepted"
    assert block["provenance"]["model_run_id"] == "r-20260101"
    assert len(block["provenance"]["edits"]) == 4
    assert all(not e["edited"] for e in block["provenance"]["edits"])


def test_save_with_moved_points_writes_edited(tmp_path: Path):
    jp = _seed_experiment_json(tmp_path)
    suggested = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    saved = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [30.0, 30.0]]  # last moved
    _save_wedge_marking(
        jp, points=saved, frame_shape=[100, 100], flag_review=False, note="",
        suggested_points=suggested, model_run_id="r-20260101",
    )
    block = _read(jp)["arena_markings"]["ezm_wedge_points"]
    assert block["provenance"]["method"] == "unet_suggested+human_edited"
    assert any(e["edited"] for e in block["provenance"]["edits"])
    # The edited point's displacement should be sqrt(10^2 + 10^2) ≈ 14.14
    edited = [e for e in block["provenance"]["edits"] if e["edited"]]
    assert len(edited) == 1
    assert edited[0]["displacement_px"] == pytest.approx(14.14, abs=0.01)


def test_save_is_idempotent_modulo_timestamp(tmp_path: Path):
    jp = _seed_experiment_json(tmp_path)
    pts = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
    )
    first = _read(jp)["arena_markings"]["ezm_wedge_points"]
    _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
    )
    second = _read(jp)["arena_markings"]["ezm_wedge_points"]
    # Same content (modulo marked_at)
    for k in ("points", "frame_shape", "flag_review", "note", "provenance"):
        assert first[k] == second[k]


def test_save_returns_overwrite_flag(tmp_path: Path):
    jp = _seed_experiment_json(tmp_path)
    pts = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    first_was_overwrite = _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
    )
    second_was_overwrite = _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
    )
    assert first_was_overwrite is False
    assert second_was_overwrite is True


def test_save_preserves_other_arena_markings(tmp_path: Path):
    """T16 invariant: _save_wedge_marking touches only ezm_wedge_points;
    other arena_markings sub-blocks survive unchanged."""
    jp = tmp_path / "EZM_test.json"
    jp.write_text(json.dumps({
        "experiment_id": "EZM_test",
        "arena_markings": {
            "arena_profile": {"profile_id": "ezm_460mm"},
            "ezm_boundary_points": {"points": [[1, 2], [3, 4]]},
        },
    }))
    pts = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    _save_wedge_marking(
        jp, points=pts, frame_shape=[100, 100], flag_review=False, note="",
    )
    am = _read(jp)["arena_markings"]
    assert am["arena_profile"]["profile_id"] == "ezm_460mm"
    assert am["ezm_boundary_points"]["points"] == [[1, 2], [3, 4]]
    assert am["ezm_wedge_points"]["points"] == pts


def test_save_path_invariant_across_render_paths(tmp_path: Path):
    """Both annotator and standalone paths call ``_save_wedge_marking``
    with the same kwargs. This test pins that contract: any future
    change must keep these positional/keyword args + their meanings."""
    import inspect
    sig = inspect.signature(_save_wedge_marking)
    params = list(sig.parameters)
    # First arg is the path, rest are keyword-only
    assert params[0] == "json_path"
    # The keyword-only params that both render paths must support
    keyword_only = {
        name for name, p in sig.parameters.items()
        if p.kind == inspect.Parameter.KEYWORD_ONLY
    }
    assert keyword_only >= {
        "points", "frame_shape", "flag_review", "note",
        "suggested_points", "model_run_id",
    }
