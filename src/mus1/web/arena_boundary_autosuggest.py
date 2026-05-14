"""U-Net auto-suggest helpers for the NOR/NOF Arena Boundary Marking pane (T13).

Reads the predicted circular-arena ellipse block written by the
``circular_arena_boundary`` post-processor at
``arena_markings.predicted.circular_arena_boundary.ellipse`` and exposes:

  - the predicted ellipse parameters (center, axes, angle),
  - the active-model run_id (for provenance pinning),
  - a five-point sampling of the ellipse perimeter so the canvas
    pre-fills with five draggable points the operator can edit before
    saving (the pane's marking contract is "5+ click-points → fit
    ellipse via cv2.fitEllipse", so we sample 5 evenly-spaced points
    around the predicted ellipse),
  - an ``initial_drawing`` payload suitable for :func:`st_canvas`,
  - a classifier that decides ``manual`` vs ``unet_suggested+human_accepted``
    vs ``unet_suggested+human_edited`` from the displacement between
    suggested and saved points.

Mirrors :mod:`mus1.web.ezm_wedge_autosuggest` (T10) shape-for-shape so the
two panes share the same operator-visible vocabulary and tolerance.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Pixel distance below which a "moved" point is considered "unmoved"
# (small jitter from canvas drag-tolerance / rounding). Matches the
# constant used by the EZM wedge auto-suggest so a single project-wide
# value governs both panes.
EDIT_TOLERANCE_PX: float = 2.0

# Canvas point radius — matches the value used by the boundary marking
# pane so the displayed circles line up with click extraction.
CANVAS_POINT_RADIUS: int = 8

# Number of sample points placed around the predicted ellipse to seed
# the canvas. cv2.fitEllipse needs at least 5 points, so 5 is the
# minimum-information seed that still round-trips to a valid fit.
N_SUGGEST_POINTS: int = 5


def read_predicted_block(json_path: Path) -> Optional[Dict[str, Any]]:
    """Return the ``arena_markings.predicted.circular_arena_boundary`` dict or None.

    The block is considered present only when it contains an ``ellipse``
    sub-dict with both ``center_xy`` and ``axes_xy`` (the minimum needed
    to seed the canvas). Other shapes (e.g. legacy ``diameter_px``-only
    predictions) are deliberately ignored — this pane saves an ellipse.
    """
    try:
        data = json.loads(json_path.read_text())
    except Exception:
        return None
    am = data.get("arena_markings") or {}
    pred = (am.get("predicted") or {}).get("circular_arena_boundary")
    if not isinstance(pred, dict):
        return None
    ellipse = pred.get("ellipse")
    if not isinstance(ellipse, dict):
        return None
    if not ellipse.get("center_xy") or not ellipse.get("axes_xy"):
        return None
    return pred


def sample_ellipse_points(
    *,
    center_xy: List[float],
    axes_xy: List[float],
    angle_deg: float,
    n: int = N_SUGGEST_POINTS,
) -> List[List[float]]:
    """Return *n* evenly-spaced points on the ellipse perimeter (image coords).

    *axes_xy* is given as full diameters in OpenCV's ``cv2.fitEllipse``
    convention; we divide by 2 to get semi-axes for the parametric form.
    Angles are taken counter-clockwise in radians from the major-axis;
    the ellipse is rotated by *angle_deg* (OpenCV convention, clockwise
    in image coords because the y-axis points down).

    Parametric form (rotated ellipse, OpenCV image-coords convention)::

        x(t) = cx + a*cos(t)*cosθ - b*sin(t)*sinθ
        y(t) = cy + a*cos(t)*sinθ + b*sin(t)*cosθ
    """
    cx = float(center_xy[0])
    cy = float(center_xy[1])
    a = float(axes_xy[0]) / 2.0
    b = float(axes_xy[1]) / 2.0
    theta = math.radians(float(angle_deg))
    cos_th = math.cos(theta)
    sin_th = math.sin(theta)
    out: List[List[float]] = []
    for k in range(int(n)):
        t = 2.0 * math.pi * k / float(n)
        ct = math.cos(t)
        st = math.sin(t)
        x = cx + a * ct * cos_th - b * st * sin_th
        y = cy + a * ct * sin_th + b * st * cos_th
        out.append([round(x, 2), round(y, 2)])
    return out


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
    """For each saved point, pair it greedily with the nearest suggested
    point and record the displacement. Pairs that moved more than
    *tolerance_px* are flagged as edits.

    Returns a list of ``{original_xy, final_xy, displacement_px, edited}``
    dicts, one per saved point. Length matches *saved*.
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
    """Return ``(method, edits)`` for use in arena_markings.arena_boundary.provenance.

    method ∈ ``{manual, unet_suggested+human_accepted, unet_suggested+human_edited}``.

    Returns ``manual`` when no suggestion is supplied or the suggestion
    has fewer points than the operator placed (e.g. the predicted block
    only seeded a partial set). This is the conservative call: we never
    claim a fit was AI-seeded when the seed was incomplete.
    """
    if not suggested_points or len(suggested_points) < len(saved_points):
        return "manual", []
    edits = diff_points(suggested_points, saved_points, tolerance_px=tolerance_px)
    any_edited = any(e["edited"] for e in edits)
    method = "unet_suggested+human_edited" if any_edited else "unet_suggested+human_accepted"
    return method, edits
