"""Tests for the NOR/NOF arena-boundary U-Net auto-suggest helpers (T13)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from mus1.web.arena_boundary_autosuggest import (
    CANVAS_POINT_RADIUS,
    EDIT_TOLERANCE_PX,
    N_SUGGEST_POINTS,
    build_canvas_initial_drawing,
    classify_marking_provenance,
    diff_points,
    read_predicted_block,
    sample_ellipse_points,
)


# ---------------------------------------------------------------------------
# read_predicted_block
# ---------------------------------------------------------------------------

def test_read_predicted_block_returns_none_when_missing(tmp_path: Path):
    jp = tmp_path / "NOR_test.json"
    jp.write_text(json.dumps({"arena_markings": {}}))
    assert read_predicted_block(jp) is None


def test_read_predicted_block_returns_block_when_present(tmp_path: Path):
    jp = tmp_path / "NOR_test.json"
    jp.write_text(json.dumps({
        "arena_markings": {
            "predicted": {
                "circular_arena_boundary": {
                    "ellipse": {
                        "center_xy": [320.0, 240.0],
                        "axes_xy": [400.0, 380.0],
                        "angle_deg": 0.0,
                    },
                    "model_run_id": "r1",
                }
            }
        }
    }))
    block = read_predicted_block(jp)
    assert block is not None
    assert block["model_run_id"] == "r1"
    assert block["ellipse"]["center_xy"] == [320.0, 240.0]


def test_read_predicted_block_handles_unreadable_json(tmp_path: Path):
    jp = tmp_path / "bad.json"
    jp.write_text("not json")
    assert read_predicted_block(jp) is None


def test_read_predicted_block_returns_none_when_no_ellipse(tmp_path: Path):
    """A predicted block without an ``ellipse`` (e.g. legacy diameter-only
    or QC-only payload) is not usable to seed the canvas."""
    jp = tmp_path / "NOR_test.json"
    jp.write_text(json.dumps({
        "arena_markings": {
            "predicted": {"circular_arena_boundary": {"qc_status": "unreviewed"}}
        }
    }))
    assert read_predicted_block(jp) is None


def test_read_predicted_block_returns_none_when_ellipse_missing_axes(tmp_path: Path):
    """Partial ellipse (center only, no axes) is not usable."""
    jp = tmp_path / "NOR_test.json"
    jp.write_text(json.dumps({
        "arena_markings": {
            "predicted": {
                "circular_arena_boundary": {
                    "ellipse": {"center_xy": [10.0, 10.0]}
                }
            }
        }
    }))
    assert read_predicted_block(jp) is None


# ---------------------------------------------------------------------------
# sample_ellipse_points
# ---------------------------------------------------------------------------

def test_sample_ellipse_points_emits_n_points_by_default():
    pts = sample_ellipse_points(
        center_xy=[0.0, 0.0], axes_xy=[200.0, 100.0], angle_deg=0.0,
    )
    assert len(pts) == N_SUGGEST_POINTS == 5


def test_sample_ellipse_points_axis_aligned_circle():
    """Unrotated circle of diameter 200 → 5 points around radius 100."""
    pts = sample_ellipse_points(
        center_xy=[0.0, 0.0], axes_xy=[200.0, 200.0], angle_deg=0.0, n=5,
    )
    # First point at t=0 → (a, 0) where a = 200/2 = 100
    assert pts[0][0] == pytest.approx(100.0, abs=0.01)
    assert pts[0][1] == pytest.approx(0.0, abs=0.01)
    # Each point lies on the circle (distance to center ≈ 100)
    for x, y in pts:
        d = (x * x + y * y) ** 0.5
        assert d == pytest.approx(100.0, abs=0.01)


def test_sample_ellipse_points_respects_rotation():
    """Rotating a circle by any angle should still yield points on it.
    Use an actual ellipse so the rotation visibly matters: rotating by 90°
    should swap major/minor on the x-axis."""
    pts_unrot = sample_ellipse_points(
        center_xy=[0.0, 0.0], axes_xy=[200.0, 100.0], angle_deg=0.0, n=5,
    )
    pts_rot = sample_ellipse_points(
        center_xy=[0.0, 0.0], axes_xy=[200.0, 100.0], angle_deg=90.0, n=5,
    )
    # At t=0 unrotated → (a, 0) = (100, 0); rotated by 90° → (0, a) = (0, 100)
    assert pts_unrot[0][0] == pytest.approx(100.0, abs=0.01)
    assert pts_unrot[0][1] == pytest.approx(0.0, abs=0.01)
    assert pts_rot[0][0] == pytest.approx(0.0, abs=0.01)
    assert pts_rot[0][1] == pytest.approx(100.0, abs=0.01)


def test_sample_ellipse_points_translation():
    """Center offset should add to every sampled point."""
    pts = sample_ellipse_points(
        center_xy=[500.0, 250.0], axes_xy=[100.0, 100.0], angle_deg=0.0, n=5,
    )
    # All points on a circle of radius 50 around (500, 250)
    for x, y in pts:
        d = ((x - 500.0) ** 2 + (y - 250.0) ** 2) ** 0.5
        assert d == pytest.approx(50.0, abs=0.01)


def test_sample_ellipse_points_evenly_spaced():
    """Adjacent sampled points should be separated by 2π/n in parameter t.

    Verified via the central angle for an unrotated circle (where the
    parameter t equals the polar angle exactly)."""
    pts = sample_ellipse_points(
        center_xy=[0.0, 0.0], axes_xy=[100.0, 100.0], angle_deg=0.0, n=5,
    )
    expected_step = 2.0 * math.pi / 5.0
    for i in range(len(pts)):
        x, y = pts[i]
        ang = math.atan2(y, x) % (2.0 * math.pi)
        expected = (i * expected_step) % (2.0 * math.pi)
        # Allow ±0.001 radian rounding tolerance.
        diff = abs((ang - expected + math.pi) % (2.0 * math.pi) - math.pi)
        assert diff < 1e-3


# ---------------------------------------------------------------------------
# build_canvas_initial_drawing
# ---------------------------------------------------------------------------

def test_build_canvas_initial_drawing_emits_n_circles():
    pts = [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0],
           [100.0, 200.0], [150.0, 150.0]]
    drawing = build_canvas_initial_drawing(pts, scale=0.5)
    assert len(drawing["objects"]) == 5
    assert all(o["type"] == "circle" for o in drawing["objects"])
    # First point at (100, 100) at scale 0.5 → canvas xy (50, 50)
    # → top-left at (50 - CANVAS_POINT_RADIUS, 50 - CANVAS_POINT_RADIUS)
    first = drawing["objects"][0]
    assert first["left"] == pytest.approx(50.0 - CANVAS_POINT_RADIUS)
    assert first["top"] == pytest.approx(50.0 - CANVAS_POINT_RADIUS)


def test_build_canvas_initial_drawing_uses_canvas_radius():
    pts = [[10.0, 10.0]]
    drawing = build_canvas_initial_drawing(pts, scale=1.0, canvas_radius=5)
    obj = drawing["objects"][0]
    assert obj["radius"] == 5
    assert obj["left"] == 5.0
    assert obj["top"] == 5.0


# ---------------------------------------------------------------------------
# diff_points
# ---------------------------------------------------------------------------

def test_diff_points_no_movement():
    sug = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0],
           [20.0, 20.0], [15.0, 15.0]]
    saved = list(sug)
    edits = diff_points(sug, saved)
    assert len(edits) == 5
    assert all(not e["edited"] for e in edits)
    assert all(e["displacement_px"] == 0.0 for e in edits)


def test_diff_points_one_point_moved():
    sug = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0],
           [20.0, 20.0], [15.0, 15.0]]
    saved = [[10.0, 10.0], [20.0, 10.0], [10.0, 20.0],
             [25.0, 25.0], [15.0, 15.0]]  # 4th point moved by sqrt(50)
    edits = diff_points(sug, saved)
    moved = [e for e in edits if e["edited"]]
    assert len(moved) == 1
    assert moved[0]["original_xy"] == [20.0, 20.0]
    assert moved[0]["final_xy"] == [25.0, 25.0]
    assert moved[0]["displacement_px"] == pytest.approx(7.07, abs=0.01)


def test_diff_points_tolerance_avoids_jitter_classification():
    """Small displacements (≤ tolerance) should NOT flag as edits."""
    sug = [[100.0, 100.0]]
    saved = [[100.5, 100.5]]  # ~0.7 px, below default tolerance of 2.0
    edits = diff_points(sug, saved)
    assert not edits[0]["edited"]


def test_diff_points_empty_returns_empty():
    assert diff_points([], [[1, 2]]) == []
    assert diff_points([[1, 2]], []) == []


# ---------------------------------------------------------------------------
# classify_marking_provenance
# ---------------------------------------------------------------------------

def test_classify_manual_when_no_suggestion():
    saved = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [5.0, 5.0]]
    method, edits = classify_marking_provenance(saved)
    assert method == "manual"
    assert edits == []


def test_classify_accepted_when_no_edits():
    pts = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [5.0, 5.0]]
    method, edits = classify_marking_provenance(pts, suggested_points=pts)
    assert method == "unet_suggested+human_accepted"
    assert len(edits) == 5
    assert all(not e["edited"] for e in edits)


def test_classify_edited_when_any_point_moved():
    sug = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [5.0, 5.0]]
    saved = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [50.0, 50.0]]
    method, edits = classify_marking_provenance(saved, suggested_points=sug)
    assert method == "unet_suggested+human_edited"
    assert any(e["edited"] for e in edits)


def test_classify_manual_when_suggestion_incomplete():
    """If the suggestion has fewer points than saved (partial predicted
    block), fall back to manual."""
    sug = [[1.0, 1.0], [2.0, 2.0]]
    saved = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [5.0, 5.0]]
    method, edits = classify_marking_provenance(saved, suggested_points=sug)
    assert method == "manual"
    assert edits == []


def test_classify_respects_custom_tolerance():
    sug = [[10.0, 10.0]]
    saved = [[12.5, 10.0]]  # 2.5 px movement
    # Default tolerance 2.0 → edited
    method_default, _ = classify_marking_provenance(saved, suggested_points=sug)
    assert method_default == "unet_suggested+human_edited"
    # Looser tolerance 5.0 → accepted
    method_loose, _ = classify_marking_provenance(
        saved, suggested_points=sug, tolerance_px=5.0,
    )
    assert method_loose == "unet_suggested+human_accepted"


def test_edit_tolerance_constant_pinned():
    """Pin EDIT_TOLERANCE_PX so a change is deliberate (it governs every
    save's provenance classification)."""
    assert EDIT_TOLERANCE_PX == 2.0


def test_n_suggest_points_meets_min_fitellipse_requirement():
    """cv2.fitEllipse needs at least 5 points; the seed must match."""
    assert N_SUGGEST_POINTS >= 5
