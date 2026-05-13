from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Sequence, Tuple

import cv2  # type: ignore
import numpy as np  # type: ignore


TAU = 2.0 * math.pi

LabelSource = Literal["auto", "derived", "annotations"]


@dataclass(frozen=True)
class EllipseParams:
    """OpenCV-style ellipse parameters.

    axes_xy are diameters (OpenCV convention).
    """

    center_xy: Tuple[float, float]  # (cx, cy)
    axes_xy: Tuple[float, float]  # (major_diameter, minor_diameter)
    angle_deg: float  # rotation of major axis, degrees

    @property
    def a(self) -> float:
        return float(self.axes_xy[0]) / 2.0

    @property
    def b(self) -> float:
        return float(self.axes_xy[1]) / 2.0

    @property
    def angle_rad(self) -> float:
        return math.radians(float(self.angle_deg))


def _wrap_angle(theta: np.ndarray) -> np.ndarray:
    return np.mod(theta, TAU)


def _angle_in_range(theta: np.ndarray, start: float, end: float) -> np.ndarray:
    t = _wrap_angle(theta)
    s = float(start) % TAU
    e = float(end) % TAU
    if s <= e:
        return (t >= s) & (t <= e)
    return (t >= s) | (t <= e)


def _angle_in_any_range(theta: np.ndarray, ranges: Sequence[Tuple[float, float]]) -> np.ndarray:
    m = np.zeros_like(theta, dtype=bool)
    for s, e in ranges:
        m |= _angle_in_range(theta, float(s), float(e))
    return m


def _rotation_matrix(angle_rad: float) -> np.ndarray:
    c = math.cos(float(angle_rad))
    s = math.sin(float(angle_rad))
    return np.array([[c, -s], [s, c]], dtype=float)


def _compute_r_theta(
    x: np.ndarray,
    y: np.ndarray,
    outer: EllipseParams,
) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    cx, cy = outer.center_xy
    pts = np.stack([x - cx, y - cy], axis=0)  # 2 x N
    R = _rotation_matrix(-outer.angle_rad)
    rot = R @ pts
    a = outer.a if outer.a > 0 else np.nan
    b = outer.b if outer.b > 0 else np.nan
    xn = rot[0, :] / a
    yn = rot[1, :] / b
    r = np.sqrt(xn * xn + yn * yn)
    theta = _wrap_angle(np.arctan2(yn, xn))
    return r, theta


def _ellipse_from_zone_payload(payload: Dict[str, Any]) -> EllipseParams:
    outer = (payload or {}).get("outer_ellipse") or {}
    (cx, cy) = outer.get("center") or [None, None]
    (ax, by) = outer.get("axes") or [None, None]
    ang = outer.get("angle_deg")
    if cx is None or cy is None or ax is None or by is None or ang is None:
        raise ValueError("Zone JSON missing outer_ellipse fields: center, axes, angle_deg")
    return EllipseParams(
        center_xy=(float(cx), float(cy)),
        axes_xy=(float(ax), float(by)),
        angle_deg=float(ang),
    )


def _open_ranges_from_payload(payload: Dict[str, Any]) -> List[Tuple[float, float]]:
    oar = (payload or {}).get("open_angle_ranges") or []
    if not (isinstance(oar, list) and len(oar) == 2):
        raise ValueError("Zone JSON missing open_angle_ranges.")
    return [(float(oar[0][0]), float(oar[0][1])), (float(oar[1][0]), float(oar[1][1]))]


def _make_mask_derived(payload: Dict[str, Any], *, out_hw: Tuple[int, int]) -> np.ndarray:
    """
    Parametric label mask from stored outer_ellipse + r_inner + open_angle_ranges.

    Returns uint8 mask in {0,1,2} for {background, open, closed}.
    """
    outer = _ellipse_from_zone_payload(payload)
    r_inner = float((payload or {}).get("r_inner") or 0.0)
    open_ranges = _open_ranges_from_payload(payload)

    h, w = int(out_hw[0]), int(out_hw[1])
    yy, xx = np.mgrid[0:h, 0:w]
    r, theta = _compute_r_theta(xx.reshape(-1), yy.reshape(-1), outer)
    r = r.reshape(h, w)
    theta = theta.reshape(h, w)
    in_track = (r >= float(r_inner)) & (r <= 1.0)
    is_open = in_track & _angle_in_any_range(theta, open_ranges)
    is_closed = in_track & (~is_open)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[is_open] = 1
    mask[is_closed] = 2
    return mask


def make_ezm_safe_bg_mask(
    zone_json_path: Path,
    *,
    out_hw: Tuple[int, int],
    inner_scale: float = 0.85,
    outer_scale: float = 1.12,
) -> np.ndarray:
    """
    Weak-label mask to visualize "this is NOT open or closed".

    Returns uint8 mask with:
    - 0 = enforced background (safe center ellipse + safe outside band)
    - 3 = unknown/ignored region (track-ish ring; we do NOT claim open/closed there)
    """
    payload = json.loads(Path(zone_json_path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("Zone JSON is not a dict payload.")
    outer = _ellipse_from_zone_payload(payload)
    r_inner = float((payload or {}).get("r_inner") or 0.0)

    h, w = int(out_hw[0]), int(out_hw[1])
    yy, xx = np.mgrid[0:h, 0:w]
    r, _ = _compute_r_theta(xx.reshape(-1), yy.reshape(-1), outer)
    r = r.reshape(h, w)
    safe_center = r <= (float(r_inner) * float(inner_scale))
    safe_outside = r >= float(outer_scale)
    out = np.full((h, w), 3, dtype=np.uint8)
    out[safe_center | safe_outside] = 0
    return out


def blend_safe_bg_overlay(frame_rgb: np.ndarray, safe_mask: np.ndarray) -> np.ndarray:
    """
    Overlay SAFE_BG mask on RGB frame for QC.
    - enforced background (0): red tint
    - unknown/ignored (3): no tint
    """
    rgb = np.asarray(frame_rgb).copy()
    overlay = rgb.copy()
    overlay[safe_mask == 0] = (255, 0, 0)  # red in RGB
    return cv2.addWeighted(rgb, 0.70, overlay, 0.30, 0)


def _extract_circle_centers(canvas_json: dict) -> list[tuple[float, float]]:
    """
    Extract circle centers from Fabric.js JSON (streamlit-drawable-canvas).
    """
    objs = (canvas_json or {}).get("objects")
    if not isinstance(objs, list):
        return []
    out: list[tuple[float, float]] = []
    for obj in objs:
        if not isinstance(obj, dict) or obj.get("type") != "circle":
            continue
        left = float(obj.get("left", 0.0))
        top = float(obj.get("top", 0.0))
        r0 = float(obj.get("radius", 0.0))
        sx = float(obj.get("scaleX", 1.0) or 1.0)
        sy = float(obj.get("scaleY", 1.0) or 1.0)
        cx = left + r0 * sx
        cy = top + r0 * sy
        out.append((float(cx), float(cy)))
    return out


def _extract_line_midpoints(canvas_json: dict) -> list[tuple[float, float]]:
    """
    Extract (mx,my) midpoints for Fabric.js line objects.

    We intentionally do NOT use the line direction (dx,dy). Users often draw border lines
    with arbitrary orientation/length; the midpoint vector from the arena center is robust.
    """
    objs = (canvas_json or {}).get("objects")
    if not isinstance(objs, list):
        return []
    out: list[tuple[float, float]] = []
    for obj in objs:
        if not isinstance(obj, dict) or obj.get("type") != "line":
            continue
        x1 = float(obj.get("x1", 0.0)) + float(obj.get("left", 0.0))
        y1 = float(obj.get("y1", 0.0)) + float(obj.get("top", 0.0))
        x2 = float(obj.get("x2", 0.0)) + float(obj.get("left", 0.0))
        y2 = float(obj.get("y2", 0.0)) + float(obj.get("top", 0.0))
        out.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    return out


def _fit_ellipse_params(pts_xy: list[tuple[float, float]]) -> tuple[tuple[float, float], tuple[float, float], float]:
    if len(pts_xy) < 5:
        raise ValueError("Need >=5 points to fitEllipse")
    pts = np.asarray(pts_xy, dtype=np.float32).reshape(-1, 1, 2)
    (cx, cy), (maj, minu), ang = cv2.fitEllipse(pts)
    return (float(cx), float(cy)), (float(maj), float(minu)), float(ang)


def _mask_fill_ellipse(hw: tuple[int, int], outer: EllipseParams) -> np.ndarray:
    h, w = int(hw[0]), int(hw[1])
    m = np.zeros((h, w), dtype=np.uint8)
    cx, cy = outer.center_xy
    center = (int(round(float(cx))), int(round(float(cy))))
    axes = (int(round(float(outer.axes_xy[0]) / 2.0)), int(round(float(outer.axes_xy[1]) / 2.0)))
    if axes[0] <= 0 or axes[1] <= 0:
        return m
    cv2.ellipse(m, center, axes, float(outer.angle_deg), 0, 360, 255, -1)
    return m


def _circular_mean(a: float, b: float) -> float:
    a = float(a) % TAU
    b = float(b) % TAU
    s = float(np.sin(a) + np.sin(b))
    c = float(np.cos(a) + np.cos(b))
    return float(np.arctan2(s, c) % TAU)


def _make_mask_from_annotations(payload: Dict[str, Any], *, out_hw: Tuple[int, int]) -> np.ndarray:
    """
    Label mask from *raw annotation objects* stored in zone JSON.

    Required keys:
      payload["annotations"]["outer_canvas"]
      payload["annotations"]["inner_canvas"]
      payload["annotations"]["borders_canvas"]
    """
    ann = (payload or {}).get("annotations") or {}
    outer_pts = _extract_circle_centers(ann.get("outer_canvas") or {})
    inner_pts = _extract_circle_centers(ann.get("inner_canvas") or {})
    border_mids = _extract_line_midpoints(ann.get("borders_canvas") or {})
    if len(outer_pts) < 5 or len(inner_pts) < 5:
        raise ValueError("Zone JSON missing sufficient outer/inner circle points for annotation-based labels.")
    if len(border_mids) != 4:
        raise ValueError(f"Expected 4 border lines for annotation-based labels, got {len(border_mids)}.")

    (cx, cy), outer_axes, outer_ang = _fit_ellipse_params(outer_pts)
    (_, _), inner_axes, inner_ang = _fit_ellipse_params(inner_pts)
    outer = EllipseParams(center_xy=(cx, cy), axes_xy=outer_axes, angle_deg=outer_ang)
    inner = EllipseParams(center_xy=(cx, cy), axes_xy=inner_axes, angle_deg=inner_ang)

    outer_fill = _mask_fill_ellipse((int(out_hw[0]), int(out_hw[1])), outer).astype(bool)
    inner_fill = _mask_fill_ellipse((int(out_hw[0]), int(out_hw[1])), inner).astype(bool)
    track = outer_fill & (~inner_fill)

    # Boundary rays: angle in image space from the border line midpoints (relative to center).
    phis = sorted([float(np.arctan2(my - cy, mx - cx) % TAU) for (mx, my) in border_mids])

    # Which phi sectors are open is inferred from stored open_angle_ranges.
    open_ranges = _open_ranges_from_payload(payload)
    open_sector = [False, False, False, False]
    for i in range(4):
        a = phis[i]
        b = phis[(i + 1) % 4]
        mid_phi = _circular_mean(a, b)
        px = cx + math.cos(mid_phi) * (outer.a * 0.9)
        py = cy + math.sin(mid_phi) * (outer.b * 0.9)
        _, th = _compute_r_theta(np.array([px]), np.array([py]), outer)
        open_sector[i] = bool(_angle_in_any_range(th, open_ranges)[0])

    h, w = int(out_hw[0]), int(out_hw[1])
    yy, xx = np.mgrid[0:h, 0:w]
    phi = (np.arctan2(yy - cy, xx - cx) % TAU).astype(np.float64)
    sector_idx = np.zeros((h, w), dtype=np.int8)
    for i in range(4):
        start = phis[i]
        end = phis[(i + 1) % 4]
        if i < 3:
            m = (phi >= start) & (phi < end)
        else:
            m = (phi >= start) | (phi < end)
        sector_idx[m] = i

    mask = np.zeros((h, w), dtype=np.uint8)
    open_ids = [i for i, ok in enumerate(open_sector) if ok]
    open_pix = track & np.isin(sector_idx, open_ids)
    closed_pix = track & (~open_pix)
    mask[open_pix] = 1
    mask[closed_pix] = 2
    return mask


def make_ezm_open_closed_mask(
    zone_json_path: Path,
    *,
    out_hw: Tuple[int, int],
    label_source: LabelSource = "auto",
) -> np.ndarray:
    """
    Generate EZM open/closed GT mask (uint8 {0,1,2}) from a per-video zone JSON.
    """
    payload = json.loads(Path(zone_json_path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("Zone JSON is not a dict payload.")
    use = str(label_source).strip().lower()
    has_ann = isinstance(payload.get("annotations"), dict) and isinstance((payload.get("annotations") or {}).get("outer_canvas"), dict)

    if use == "annotations" or (use == "auto" and has_ann):
        return _make_mask_from_annotations(payload, out_hw=out_hw)
    return _make_mask_derived(payload, out_hw=out_hw)


def blend_mask_overlay(frame_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Overlay mask on RGB frame for quick QC.

    Uses the canonical EZM palette from :mod:`mus1.compute.colors` so GT,
    prediction, and zone-sector renders share the same green/blue identity.
    """
    from mus1.compute import colors

    rgb = np.asarray(frame_rgb).copy()
    overlay = rgb.copy()
    overlay[mask == 1] = colors.OPEN
    overlay[mask == 2] = colors.CLOSED
    return cv2.addWeighted(rgb, 1.0 - colors.PREDICTED_OVERLAY_ALPHA,
                           overlay, colors.PREDICTED_OVERLAY_ALPHA, 0)

