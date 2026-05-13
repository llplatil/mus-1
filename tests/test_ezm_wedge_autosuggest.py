"""Tests for the U-Net auto-suggest helpers (T10)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mus1.web.ezm_wedge_autosuggest import (
    EDIT_TOLERANCE_PX,
    build_canvas_initial_drawing,
    classify_marking_provenance,
    diff_points,
    read_predicted_block,
)


# ---------------------------------------------------------------------------
# read_predicted_block
# ---------------------------------------------------------------------------

def test_read_predicted_block_returns_none_when_missing(tmp_path: Path):
    jp = tmp_path / "EZM_test.json"
    jp.write_text(json.dumps({"arena_markings": {}}))
    assert read_predicted_block(jp) is None


def test_read_predicted_block_returns_block_when_present(tmp_path: Path):
    jp = tmp_path / "EZM_test.json"
    jp.write_text(json.dumps({
        "arena_markings": {
            "predicted": {
                "ezm_wedge_points": {
                    "points": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]],
                    "model_run_id": "r1",
                }
            }
        }
    }))
    block = read_predicted_block(jp)
    assert block is not None
    assert block["model_run_id"] == "r1"
    assert len(block["points"]) == 4


def test_read_predicted_block_handles_unreadable_json(tmp_path: Path):
    jp = tmp_path / "bad.json"
    jp.write_text("not json")
    assert read_predicted_block(jp) is None


def test_read_predicted_block_returns_none_when_no_points(tmp_path: Path):
    jp = tmp_path / "EZM_test.json"
    jp.write_text(json.dumps({
        "arena_markings": {
            "predicted": {"ezm_wedge_points": {"qc_status": "predicted_unreviewed"}}
        }
    }))
    assert read_predicted_block(jp) is None


# ---------------------------------------------------------------------------
# build_canvas_initial_drawing
# ---------------------------------------------------------------------------

def test_build_canvas_initial_drawing_emits_4_circles():
    pts = [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]]
    drawing = build_canvas_initial_drawing(pts, scale=0.5)
    assert len(drawing["objects"]) == 4
    assert all(o["type"] == "circle" for o in drawing["objects"])
    # First point at (100, 100) at scale 0.5 → canvas xy (50, 50) → top-left at (42, 42)
    first = drawing["objects"][0]
    assert first["left"] == pytest.approx(50.0 - 8)
    assert first["top"] == pytest.approx(50.0 - 8)


def test_build_canvas_initial_drawing_uses_canvas_radius():
    pts = [[10.0, 10.0]]
    drawing = build_canvas_initial_drawing(pts, scale=1.0, canvas_radius=5)
    obj = drawing["objects"][0]
    assert obj["radius"] == 5
    # Top-left at (10 - 5, 10 - 5)
    assert obj["left"] == 5.0
    assert obj["top"] == 5.0


# ---------------------------------------------------------------------------
# diff_points
# ---------------------------------------------------------------------------

def test_diff_points_no_movement():
    sug = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    saved = list(sug)
    edits = diff_points(sug, saved)
    assert len(edits) == 4
    assert all(not e["edited"] for e in edits)
    assert all(e["displacement_px"] == 0.0 for e in edits)


def test_diff_points_one_point_moved():
    sug = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [20.0, 20.0]]
    saved = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0], [25.0, 25.0]]  # 4th point moved
    edits = diff_points(sug, saved)
    moved = [e for e in edits if e["edited"]]
    assert len(moved) == 1
    assert moved[0]["original_xy"] == [20.0, 20.0]
    assert moved[0]["final_xy"] == [25.0, 25.0]
    # Distance ≈ sqrt(5² + 5²) = 7.07
    assert moved[0]["displacement_px"] == pytest.approx(7.07, abs=0.01)


def test_diff_points_tolerance_avoids_jitter_classification():
    """Small displacements (≤ tolerance) should NOT flag as edits."""
    sug = [[100.0, 100.0]]
    saved = [[100.5, 100.5]]  # ~0.7 px away, below default tolerance of 2.0
    edits = diff_points(sug, saved)
    assert not edits[0]["edited"]


def test_diff_points_empty_returns_empty():
    assert diff_points([], [[1, 2]]) == []
    assert diff_points([[1, 2]], []) == []


# ---------------------------------------------------------------------------
# classify_marking_provenance
# ---------------------------------------------------------------------------

def test_classify_manual_when_no_suggestion():
    saved = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]]
    method, edits = classify_marking_provenance(saved)
    assert method == "manual"
    assert edits == []


def test_classify_accepted_when_no_edits():
    pts = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]]
    method, edits = classify_marking_provenance(pts, suggested_points=pts)
    assert method == "unet_suggested+human_accepted"
    assert len(edits) == 4
    assert all(not e["edited"] for e in edits)


def test_classify_edited_when_any_point_moved():
    sug = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]]
    saved = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [10.0, 10.0]]
    method, edits = classify_marking_provenance(saved, suggested_points=sug)
    assert method == "unet_suggested+human_edited"
    assert any(e["edited"] for e in edits)


def test_classify_manual_when_suggestion_incomplete():
    """If the suggestion has fewer points than saved (e.g. predicted block
    was partial), fall back to manual classification."""
    sug = [[1.0, 1.0], [2.0, 2.0]]  # only 2 suggested
    saved = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]]
    method, edits = classify_marking_provenance(saved, suggested_points=sug)
    assert method == "manual"
    assert edits == []


def test_classify_respects_custom_tolerance():
    sug = [[10.0, 10.0]]
    saved = [[12.5, 10.0]]  # 2.5 px movement
    # Default tolerance 2.0 → edited
    method_default, _ = classify_marking_provenance(saved, suggested_points=sug)
    assert method_default == "unet_suggested+human_edited"
    # Tighter tolerance 5.0 → accepted
    method_loose, _ = classify_marking_provenance(
        saved, suggested_points=sug, tolerance_px=5.0,
    )
    assert method_loose == "unet_suggested+human_accepted"


def test_edit_tolerance_constant_pinned():
    """Pin EDIT_TOLERANCE_PX so changes are deliberate (it affects every
    save's provenance classification)."""
    assert EDIT_TOLERANCE_PX == 2.0
