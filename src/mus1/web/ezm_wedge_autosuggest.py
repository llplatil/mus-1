"""U-Net auto-suggest helpers for EZM Wedge Marking (T10).

Reads the predicted wedge-points block written by the CLI
``mus1 ezm-arena-inference`` (or any future profile-aware equivalent
from T11) at ``arena_markings.predicted.ezm_wedge_points`` and exposes:

  - the 4 predicted points,
  - the active-model run_id (for provenance pinning),
  - an ``initial_drawing`` payload suitable for :func:`st_canvas`
    pre-populating the canvas with the predicted points.

Plus a helper to determine whether the operator edited any of the
suggested points before saving, so the saved ``provenance.method``
distinguishes ``unet_suggested+human_accepted`` from
``unet_suggested+human_edited`` per ROADMAP Iteration 6c.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Pixel distance below which a "moved" point is considered "unmoved"
# (small jitter from the canvas drag-tolerance / rounding).
EDIT_TOLERANCE_PX: float = 2.0

# Canvas point radius — matches the value used by the wedge marking pane
# so the displayed circles line up with click extraction.
CANVAS_POINT_RADIUS: int = 8


def read_predicted_block(json_path: Path) -> Optional[Dict[str, Any]]:
    """Return the ``arena_markings.predicted.ezm_wedge_points`` dict or None."""
    try:
        data = json.loads(json_path.read_text())
    except Exception:
        return None
    am = data.get("arena_markings") or {}
    pred = (am.get("predicted") or {}).get("ezm_wedge_points")
    if isinstance(pred, dict) and pred.get("points"):
        return pred
    return None


def build_canvas_initial_drawing(
    points_xy: List[List[float]],
    *,
    scale: float,
    canvas_radius: int = CANVAS_POINT_RADIUS,
) -> Dict[str, Any]:
    """Build a Fabric.js-style ``initial_drawing`` for ``st_canvas``.

    *points_xy* are in original-image coordinates; *scale* is the
    image-display ratio (``canvas_w / img_w``). Each point becomes a
    green-filled circle of radius *canvas_radius*.
    """
    objects = []
    for px, py in points_xy:
        # Convert to canvas (display) coordinates
        cx = float(px) * scale
        cy = float(py) * scale
        objects.append({
            "type": "circle",
            "version": "4.4.0",
            "originX": "left",
            "originY": "top",
            "left": cx - canvas_radius,
            "top": cy - canvas_radius,
            "width": canvas_radius * 2,
            "height": canvas_radius * 2,
            "radius": canvas_radius,
            "fill": "rgba(0, 255, 0, 0.45)",
            "stroke": "#00ff00",
            "strokeWidth": 1,
            "scaleX": 1,
            "scaleY": 1,
            "angle": 0,
            "opacity": 1,
            "selectable": True,
        })
    return {
        "version": "4.4.0",
        "objects": objects,
        "background": "",
    }


def diff_points(
    suggested: List[List[float]],
    saved: List[List[float]],
    *,
    tolerance_px: float = EDIT_TOLERANCE_PX,
) -> List[Dict[str, Any]]:
    """For each saved point, find the closest suggested point and record
    the displacement. Pairs that moved more than *tolerance_px* are
    flagged as edits.

    Returns a list of ``{original_xy, final_xy, displacement_px, edited}``
    dicts, one per saved point. Length matches *saved*.

    The pairing is greedy nearest-neighbor (4 points → cheap; no need
    for optimal assignment).
    """
    if not suggested or not saved:
        return []
    remaining = list(range(len(suggested)))
    out: List[Dict[str, Any]] = []
    for sp in saved:
        sx, sy = float(sp[0]), float(sp[1])
        best_i = -1
        best_d = float("inf")
        for i in remaining:
            ox, oy = float(suggested[i][0]), float(suggested[i][1])
            d = ((sx - ox) ** 2 + (sy - oy) ** 2) ** 0.5
            if d < best_d:
                best_d = d
                best_i = i
        if best_i >= 0:
            remaining.remove(best_i)
            ox, oy = float(suggested[best_i][0]), float(suggested[best_i][1])
            out.append({
                "original_xy": [ox, oy],
                "final_xy": [sx, sy],
                "displacement_px": round(best_d, 2),
                "edited": best_d > tolerance_px,
            })
        else:
            out.append({
                "original_xy": None,
                "final_xy": [sx, sy],
                "displacement_px": None,
                "edited": True,
            })
    return out


def classify_marking_provenance(
    saved_points: List[List[float]],
    *,
    suggested_points: Optional[List[List[float]]] = None,
    tolerance_px: float = EDIT_TOLERANCE_PX,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Return ``(method, edits)`` for use in arena_markings.ezm_wedge_points.provenance.

    method ∈ {``manual``, ``unet_suggested+human_accepted``, ``unet_suggested+human_edited``}.
    """
    if not suggested_points or len(suggested_points) < len(saved_points):
        return "manual", []
    edits = diff_points(suggested_points, saved_points, tolerance_px=tolerance_px)
    any_edited = any(e["edited"] for e in edits)
    method = "unet_suggested+human_edited" if any_edited else "unet_suggested+human_accepted"
    return method, edits
