"""EZM trajectory overlay renderer using cv2.

Matches the NOR/NOF Interaction QC visual style: temporal trajectory coloring
(cyan→green→yellow), zone sector shading, and a color legend.

Zone transitions are marked with exit dots along the trajectory path, and
segments within open arms receive a brightness boost for visual distinction.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from mus1.compute import colors

TAU = 2.0 * math.pi


# ---------------------------------------------------------------------------
# DLC track loading (lightweight, no full compute pipeline)
# ---------------------------------------------------------------------------

def load_dlc_tracks(
    csv_path: Path,
    likelihood_threshold: float = 0.6,
    max_interp_gap: int = 10,
) -> Optional[Dict[str, Dict[str, np.ndarray]]]:
    """Read DLC CSV and return filtered tracks for key bodyparts.

    Returns ``{bodypart: {"x": ..., "y": ..., "ok": ...}}`` or None.
    """
    import pandas as pd

    try:
        df = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
        return None
    try:
        df.columns = df.columns.droplevel(0)
    except Exception:
        return None

    bodyparts = sorted(set(df.columns.get_level_values(0)))
    out: Dict[str, Dict[str, np.ndarray]] = {}
    for bp in bodyparts:
        try:
            x = pd.to_numeric(df[(bp, "x")], errors="coerce")
            y = pd.to_numeric(df[(bp, "y")], errors="coerce")
            p = pd.to_numeric(df[(bp, "likelihood")], errors="coerce")
        except KeyError:
            continue
        above = p >= likelihood_threshold
        xf = x.where(above).interpolate(limit=max_interp_gap, limit_direction="both")
        yf = y.where(above).interpolate(limit=max_interp_gap, limit_direction="both")
        ok = (xf.notna() & yf.notna()).to_numpy(dtype=bool)
        out[bp] = {"x": xf.to_numpy(dtype=float), "y": yf.to_numpy(dtype=float), "ok": ok}
    return out if out else None


# ---------------------------------------------------------------------------
# Zone geometry helpers
# ---------------------------------------------------------------------------

def _parse_zone(zone_payload: dict) -> Optional[Dict[str, Any]]:
    """Extract zone geometry from a zone JSON payload."""
    oe = zone_payload.get("outer_ellipse")
    if not oe:
        return None
    cx, cy = float(oe["center"][0]), float(oe["center"][1])
    ax_w, ax_h = float(oe["axes"][0]), float(oe["axes"][1])
    ang_deg = float(oe.get("angle_deg", 0))
    r_inner = float(zone_payload.get("r_inner", 0.5))
    boundary_angles = zone_payload.get("boundary_angles", [])
    open_ranges = zone_payload.get("open_angle_ranges", [])
    return {
        "cx": cx, "cy": cy, "ax_w": ax_w, "ax_h": ax_h, "ang_deg": ang_deg,
        "r_inner": r_inner, "boundary_angles": boundary_angles,
        "open_ranges": open_ranges,
    }


def _in_open_range(theta: float, open_ranges: List[List[float]]) -> bool:
    """Check if angle theta is in any open range."""
    theta = theta % TAU
    for rng in open_ranges:
        a_start = float(rng[0]) % TAU
        a_end = float(rng[1]) % TAU
        if a_start <= a_end:
            if a_start <= theta <= a_end:
                return True
        else:
            if theta >= a_start or theta <= a_end:
                return True
    return False


def _compute_r_theta_ellipse(
    x: np.ndarray, y: np.ndarray,
    cx: float, cy: float, ax_w: float, ax_h: float, ang_deg: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Normalized r (0=center, 1=outer edge) and theta for an elliptical track.

    theta is computed in the **normalized** (rotation-corrected) coordinate space,
    matching ``ezm_open_closed_zones.compute_r_theta`` and ``ezm_geometry.compute_r_theta``.
    The zone JSON boundary_angles are in this same space.
    """
    ang_rad = math.radians(ang_deg)
    c_rot = math.cos(-ang_rad)
    s_rot = math.sin(-ang_rad)
    dx = x - cx
    dy = y - cy
    xn = (dx * c_rot - dy * s_rot) / (ax_w / 2.0) if ax_w > 0 else dx
    yn = (dx * s_rot + dy * c_rot) / (ax_h / 2.0) if ax_h > 0 else dy
    r = np.sqrt(xn * xn + yn * yn)
    theta = np.arctan2(yn, xn) % TAU  # normalized coords, not raw (dy, dx)
    return r, theta


# ---------------------------------------------------------------------------
# Overlay drawing
# ---------------------------------------------------------------------------

def _draw_zone_sectors(
    img: np.ndarray,
    z: Dict[str, Any],
    alpha: float = 0.18,
    invert_open_closed: bool = False,
) -> np.ndarray:
    """Draw semi-transparent open (green) and closed (blue) sector fills."""
    h, w = img.shape[:2]
    cx, cy = z["cx"], z["cy"]
    ax_w, ax_h = z["ax_w"], z["ax_h"]
    ang_deg = z["ang_deg"]
    r_inner = z["r_inner"]
    open_ranges = z["open_ranges"]

    # Build pixel grid, compute r and theta
    yy, xx = np.mgrid[0:h, 0:w]
    r, theta = _compute_r_theta_ellipse(
        xx.astype(float), yy.astype(float),
        cx, cy, ax_w, ax_h, ang_deg,
    )
    in_annulus = (r >= r_inner) & (r <= 1.0)

    # Open vs closed by theta
    open_mask_px = np.zeros((h, w), dtype=bool)
    for rng in open_ranges:
        a_start = float(rng[0]) % TAU
        a_end = float(rng[1]) % TAU
        if a_start <= a_end:
            open_mask_px |= (theta >= a_start) & (theta <= a_end)
        else:
            open_mask_px |= (theta >= a_start) | (theta <= a_end)

    if invert_open_closed:
        open_mask_px = ~open_mask_px

    open_px = in_annulus & open_mask_px
    closed_px = in_annulus & (~open_mask_px)

    tint = np.zeros_like(img)
    tint[open_px] = list(colors.OPEN)
    tint[closed_px] = list(colors.CLOSED)
    return cv2.addWeighted(img, 1.0 - alpha, tint, alpha, 0)


def _theta_to_image_xy(
    theta: float, z: Dict[str, Any], scale: float = 1.0,
) -> Tuple[float, float]:
    """Convert normalized theta to image (x, y) on the ellipse boundary.

    The boundary_angles in the zone JSON are in the normalized (rotation-corrected)
    coordinate space.  This helper maps them back to image coordinates.
    """
    a = (z["ax_w"] / 2.0) * scale
    b = (z["ax_h"] / 2.0) * scale
    ang = math.radians(z["ang_deg"])
    x0 = a * math.cos(theta)
    y0 = b * math.sin(theta)
    xr = x0 * math.cos(ang) - y0 * math.sin(ang)
    yr = x0 * math.sin(ang) + y0 * math.cos(ang)
    return z["cx"] + xr, z["cy"] + yr


def _draw_zone_outlines(
    img: np.ndarray,
    z: Dict[str, Any],
    invert_open_closed: bool = False,
) -> np.ndarray:
    """Draw ellipse outlines and boundary lines."""
    cx, cy = int(round(z["cx"])), int(round(z["cy"]))
    ax_w, ax_h = z["ax_w"], z["ax_h"]
    ang_deg = z["ang_deg"]
    r_inner = z["r_inner"]

    # Outer ellipse (white)
    cv2.ellipse(img, (cx, cy), (max(1, int(round(ax_w / 2))), max(1, int(round(ax_h / 2)))),
                ang_deg, 0, 360, (255, 255, 255), 1, cv2.LINE_AA)
    # Inner ellipse (magenta)
    inner_ax = (max(1, int(round(ax_w * r_inner / 2))), max(1, int(round(ax_h * r_inner / 2))))
    cv2.ellipse(img, (cx, cy), inner_ax, ang_deg, 0, 360, (255, 0, 255), 1, cv2.LINE_AA)

    # Boundary lines — angles are in normalized theta space, convert to image coords
    for ba in z.get("boundary_angles", []):
        ex, ey = _theta_to_image_xy(ba, z, scale=1.15)
        cv2.line(img, (cx, cy), (int(round(ex)), int(round(ey))),
                 (255, 255, 255), 1, cv2.LINE_AA)

    # Sector labels — placed at 35% of outer radius along the sector midpoint
    open_ranges = z.get("open_ranges", [])
    for rng in open_ranges:
        mid = ((float(rng[0]) + float(rng[1])) / 2.0) % TAU
        if float(rng[0]) > float(rng[1]):
            mid = ((float(rng[0]) + float(rng[1]) + TAU) / 2.0) % TAU
        lx, ly = _theta_to_image_xy(mid, z, scale=0.7)
        lx, ly = int(round(lx)), int(round(ly))
        if invert_open_closed:
            cv2.putText(img, "CLOSED", (lx - 25, ly + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 255), 1, cv2.LINE_AA)
        else:
            cv2.putText(img, "OPEN", (lx - 20, ly + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)

    boundary_angles = sorted(z.get("boundary_angles", []))
    if len(boundary_angles) == 4:
        for i in range(4):
            a_start = boundary_angles[i]
            a_end = boundary_angles[(i + 1) % 4]
            mid = ((a_start + a_end) / 2.0) % TAU
            if a_end < a_start:
                mid = ((a_start + a_end + TAU) / 2.0) % TAU
            if not _in_open_range(mid, open_ranges):
                lx, ly = _theta_to_image_xy(mid, z, scale=0.7)
                lx, ly = int(round(lx)), int(round(ly))
                if invert_open_closed:
                    cv2.putText(img, "OPEN", (lx - 20, ly + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
                else:
                    cv2.putText(img, "CLOSED", (lx - 25, ly + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 255), 1, cv2.LINE_AA)

    return img


def _draw_trajectory(
    img: np.ndarray,
    track: Dict[str, np.ndarray],
    z: Dict[str, Any],
    *,
    subsample: int = 3,
    open_brightness_boost: float = 1.4,
    invert_open_closed: bool = False,
) -> np.ndarray:
    """Draw temporal trajectory with exit dots at zone transitions.

    Base coloring: NOR/NOF temporal gradient (cyan→green→yellow).
    Open-arm segments get a brightness boost.
    Dots at zone transitions (closed→open or open→closed).
    """
    x_arr = track["x"]
    y_arr = track["y"]
    ok_arr = track["ok"]
    total = len(ok_arr)
    if total == 0:
        return img

    # Compute zone classification per frame
    r, theta = _compute_r_theta_ellipse(
        x_arr, y_arr,
        z["cx"], z["cy"], z["ax_w"], z["ax_h"], z["ang_deg"],
    )
    in_annulus = (r >= z["r_inner"]) & (r <= 1.0)

    open_by_theta = np.zeros(total, dtype=bool)
    for rng in z.get("open_ranges", []):
        a_start = float(rng[0]) % TAU
        a_end = float(rng[1]) % TAU
        if a_start <= a_end:
            open_by_theta |= (theta >= a_start) & (theta <= a_end)
        else:
            open_by_theta |= (theta >= a_start) | (theta <= a_end)

    if invert_open_closed:
        open_by_theta = ~open_by_theta

    in_open = in_annulus & open_by_theta & ok_arr

    # Build continuous segments (same pattern as NOR/NOF)
    segments: List[Tuple[int, int]] = []
    seg_start = None
    for i in range(total):
        if ok_arr[i] and np.isfinite(x_arr[i]) and np.isfinite(y_arr[i]):
            if seg_start is None:
                seg_start = i
        else:
            if seg_start is not None and i - seg_start >= 2:
                segments.append((seg_start, i))
            seg_start = None
    if seg_start is not None and total - seg_start >= 2:
        segments.append((seg_start, total))

    # Draw polyline segments with temporal coloring (matching NOR/NOF exactly)
    for s, e in segments:
        n_pts = e - s
        if n_pts < 2:
            continue
        chunk_size = max(1, n_pts // 20)
        for ci in range(0, n_pts - 1, chunk_size):
            cs = s + ci
            ce = min(s + ci + chunk_size + 1, e)
            if ce - cs < 2:
                continue
            t = (cs + ce) / 2.0 / max(1, total)

            # NOR/NOF temporal gradient: cyan(0,200,255) → green(128,228,128) → yellow(255,255,0)
            r_c = int(255 * t)
            g_c = int(200 + 55 * t)
            b_c = int(255 * (1 - t))

            # Brightness boost for open-arm segments
            mid_idx = (cs + ce) // 2
            if mid_idx < total and in_open[mid_idx]:
                r_c = min(255, int(r_c * open_brightness_boost))
                g_c = min(255, int(g_c * open_brightness_boost))
                b_c = min(255, int(b_c * open_brightness_boost))

            color = (r_c, g_c, b_c)
            pts = np.column_stack([x_arr[cs:ce], y_arr[cs:ce]]).astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts], isClosed=False, color=color, thickness=1, lineType=cv2.LINE_AA)

    # Exit dots at zone transitions (closed→open or open→closed)
    prev_open = None
    for i in range(0, total, subsample):
        if not ok_arr[i] or not np.isfinite(x_arr[i]):
            prev_open = None
            continue
        cur_in_annulus = in_annulus[i]
        cur_open = bool(in_open[i])
        if prev_open is not None and cur_in_annulus and prev_open != cur_open:
            px = int(round(x_arr[i]))
            py = int(round(y_arr[i]))
            # White-filled dot with colored border at transition
            cv2.circle(img, (px, py), 4, (255, 255, 255), -1, cv2.LINE_AA)
            border_color = (0, 255, 0) if cur_open else (120, 120, 255)
            cv2.circle(img, (px, py), 4, border_color, 1, cv2.LINE_AA)
        prev_open = cur_open if cur_in_annulus else prev_open

    return img


def _draw_legend(img: np.ndarray, *, show_zones: bool = True) -> np.ndarray:
    """Draw color legend in bottom-right corner."""
    h, w = img.shape[:2]
    lx = w - 190
    ly = h - 90

    # Background box
    cv2.rectangle(img, (lx - 5, ly - 5), (lx + 185, ly + 85), (0, 0, 0), -1)
    cv2.rectangle(img, (lx - 5, ly - 5), (lx + 185, ly + 85), (100, 100, 100), 1)

    row = 0
    # Trajectory temporal legend (matching NOR/NOF)
    cv2.rectangle(img, (lx, ly + row), (lx + 20, ly + row + 10), (0, 200, 255), -1)
    cv2.putText(img, "early", (lx + 25, ly + row + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)
    row += 16
    cv2.rectangle(img, (lx, ly + row), (lx + 20, ly + row + 10), (128, 228, 128), -1)
    cv2.putText(img, "mid", (lx + 25, ly + row + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)
    row += 16
    cv2.rectangle(img, (lx, ly + row), (lx + 20, ly + row + 10), (255, 255, 0), -1)
    cv2.putText(img, "late", (lx + 25, ly + row + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)

    if show_zones:
        row += 16
        cv2.rectangle(img, (lx, ly + row), (lx + 20, ly + row + 10), colors.OPEN, -1)
        cv2.putText(img, "open arm", (lx + 25, ly + row + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, colors.OPEN, 1, cv2.LINE_AA)
        row += 16
        cv2.rectangle(img, (lx, ly + row), (lx + 20, ly + row + 10), colors.CLOSED, -1)
        cv2.putText(img, "closed arm", (lx + 25, ly + row + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 255), 1, cv2.LINE_AA)

    return img


# ---------------------------------------------------------------------------
# Head-corrected track computation (for overlay — lightweight, no zone compute)
# ---------------------------------------------------------------------------

def compute_corrected_head_track(
    tracks: Dict[str, Dict[str, np.ndarray]],
    primary_bp: str = "head",
    fallback_bps: Optional[List[str]] = None,
    likelihood_threshold: float = 0.6,
    raw_df: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Build a corrected head track from loaded DLC tracks.

    When primary_bp likelihood is below threshold, falls back to the
    highest-LH nearby bodypart.  Returns a track dict with an extra
    ``corrected`` boolean mask, or None if primary_bp is unavailable.

    Requires ``raw_df`` (the DLC DataFrame) to access per-frame likelihoods.
    If raw_df is not provided, returns the primary track without correction.
    """
    if primary_bp not in tracks:
        return None
    if fallback_bps is None:
        fallback_bps = ["neck_base", "nose"]

    prim = tracks[primary_bp]
    n = len(prim["x"])
    x = prim["x"].copy()
    y = prim["y"].copy()
    ok = prim["ok"].copy()
    corrected = np.zeros(n, dtype=bool)

    if raw_df is None:
        # No likelihood data — return uncorrected
        return {"x": x, "y": y, "ok": ok, "corrected": corrected}

    import pandas as pd
    prim_lh = pd.to_numeric(raw_df[(primary_bp, "likelihood")], errors="coerce").to_numpy(dtype=float)
    prim_good = (prim_lh >= likelihood_threshold) & np.isfinite(x) & np.isfinite(y)

    # For frames where primary LH is low, try fallbacks
    fb_data = []
    for bp in fallback_bps:
        if bp not in tracks or bp == primary_bp:
            continue
        bx = tracks[bp]["x"]
        by = tracks[bp]["y"]
        try:
            blh = pd.to_numeric(raw_df[(bp, "likelihood")], errors="coerce").to_numpy(dtype=float)
        except KeyError:
            continue
        fb_data.append((bp, bx, by, blh))

    for i in range(n):
        if prim_good[i]:
            continue
        best_lh = 0.0
        best_x, best_y = np.nan, np.nan
        for _, bx, by, blh in fb_data:
            if np.isfinite(blh[i]) and blh[i] >= likelihood_threshold and blh[i] > best_lh:
                if np.isfinite(bx[i]) and np.isfinite(by[i]):
                    best_lh = blh[i]
                    best_x, best_y = bx[i], by[i]
        if np.isfinite(best_x):
            x[i] = best_x
            y[i] = best_y
            corrected[i] = True
            ok[i] = True
        else:
            x[i] = np.nan
            y[i] = np.nan
            ok[i] = False

    return {"x": x, "y": y, "ok": ok, "corrected": corrected}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_CORRECTED_COLOR = colors.CORRECTED  # magenta for corrected frames


def draw_ezm_qc_overlay(
    frame_rgb: np.ndarray,
    zone_payload: dict,
    tracks: Dict[str, Dict[str, np.ndarray]],
    bodypart: str = "body_center",
    *,
    show_trajectory: bool = True,
    show_legend: bool = True,
    subsample: int = 3,
    invert_open_closed: bool = False,
    highlight_frame: int = -1,
    consensus_mode: bool = False,
    corrected_track: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """Draw zone sectors + trajectory overlay on a video frame.

    Parameters
    ----------
    frame_rgb : Video frame (H, W, 3) uint8 RGB.
    zone_payload : Zone JSON dict with outer_ellipse, r_inner, boundary_angles, open_angle_ranges.
    tracks : Dict of bodypart tracks from :func:`load_dlc_tracks`.
    bodypart : Which bodypart track to render.
    show_trajectory : If False, only draw zone sectors.
    show_legend : Include color legend.
    subsample : Frame subsampling for transition dot detection.
    invert_open_closed : Flip open/closed classification (zone JSON ranges become closed).
    highlight_frame : Frame index to mark with a crosshair on the trajectory (-1 = none).
    consensus_mode : If True, use corrected_track for drawing with color-coded corrections.
    corrected_track : Output of compute_corrected_head_track() — has x, y, ok, corrected mask.
    """
    z = _parse_zone(zone_payload)
    if z is None:
        return frame_rgb.copy()

    img = frame_rgb.copy()
    img = _draw_zone_sectors(img, z, invert_open_closed=invert_open_closed)
    img = _draw_zone_outlines(img, z, invert_open_closed=invert_open_closed)

    if show_trajectory:
        if consensus_mode and corrected_track is not None:
            # Draw corrected head track: normal temporal coloring for direct
            # head frames, magenta for frames using fallback bodyparts
            img = _draw_trajectory(img, corrected_track, z, subsample=subsample,
                                   invert_open_closed=invert_open_closed)
            # Overdraw corrected segments in magenta
            corr_mask = corrected_track.get("corrected")
            if corr_mask is not None:
                cx_arr = corrected_track["x"]
                cy_arr = corrected_track["y"]
                ok_arr = corrected_track["ok"]
                total = len(ok_arr)
                # Find runs of corrected frames and draw them
                in_run = False
                run_start = 0
                for i in range(total):
                    if corr_mask[i] and ok_arr[i]:
                        if not in_run:
                            run_start = max(0, i - 1)  # include one frame before for continuity
                            in_run = True
                    else:
                        if in_run and i - run_start >= 2:
                            run_end = min(total, i + 1)
                            pts = np.column_stack([cx_arr[run_start:run_end],
                                                   cy_arr[run_start:run_end]]).astype(np.int32).reshape((-1, 1, 2))
                            cv2.polylines(img, [pts], isClosed=False,
                                          color=_CORRECTED_COLOR, thickness=2, lineType=cv2.LINE_AA)
                        in_run = False
                if in_run and total - run_start >= 2:
                    pts = np.column_stack([cx_arr[run_start:total],
                                           cy_arr[run_start:total]]).astype(np.int32).reshape((-1, 1, 2))
                    cv2.polylines(img, [pts], isClosed=False,
                                  color=_CORRECTED_COLOR, thickness=2, lineType=cv2.LINE_AA)
        elif bodypart in tracks:
            img = _draw_trajectory(img, tracks[bodypart], z, subsample=subsample,
                                   invert_open_closed=invert_open_closed)

    # Draw crosshair at current frame position
    hlight_track = corrected_track if (consensus_mode and corrected_track) else (
        tracks.get(bodypart)
    )
    if highlight_frame >= 0 and hlight_track is not None:
        if highlight_frame < len(hlight_track["x"]) and hlight_track["ok"][highlight_frame]:
            hx = int(round(hlight_track["x"][highlight_frame]))
            hy = int(round(hlight_track["y"][highlight_frame]))
            for color, thickness in [((0, 0, 0), 3), ((255, 255, 255), 1)]:
                cv2.drawMarker(img, (hx, hy), color, cv2.MARKER_CROSS,
                               markerSize=20, thickness=thickness, line_type=cv2.LINE_AA)
            # Red dot if direct head, magenta if corrected
            corr = hlight_track.get("corrected")
            dot_color = _CORRECTED_COLOR if (corr is not None and corr[highlight_frame]) else colors.HIGHLIGHT_DOT
            cv2.circle(img, (hx, hy), 4, dot_color, -1, cv2.LINE_AA)

    if show_legend:
        if consensus_mode:
            img = _draw_legend(img, show_zones=True)
            # Add corrected-frame legend entry
            h, w = img.shape[:2]
            lx = w - 190
            ly = h - 90 - 18  # above the standard legend
            cv2.rectangle(img, (lx, ly), (lx + 20, ly + 10), _CORRECTED_COLOR, -1)
            cv2.putText(img, "corrected", (lx + 25, ly + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 80, 255), 1, cv2.LINE_AA)
        else:
            img = _draw_legend(img, show_zones=True)

    return img
