"""EZM open/closed compute bridge for in-browser metric computation.

Core per-video functions extracted from
``statistics_workspace/scripts/dlc_ezm_open_closed/compute_ezm_open_closed_time.py``.
If the canonical script changes, re-sync the functions here.

No scipy dependency — group-level stats are not needed for single-video compute.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, TypedDict

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Make ezm_open_closed_zones importable from MUS1's workspace copy
# ---------------------------------------------------------------------------
_ZONES_DIR = Path(__file__).resolve().parents[3] / "workspace" / "dlc_ezm_open_closed"
if str(_ZONES_DIR) not in sys.path:
    sys.path.insert(0, str(_ZONES_DIR))

from ezm_open_closed_zones import (  # noqa: E402
    ZoneDefinition,
    TAU,
    angle_in_any_open_range,
    classify_points,
    compute_r_theta,
    load_zone_definition,
)

# Re-export for consumers
__all__ = [
    "try_read_dlc_csv",
    "compute_open_closed_metrics",
    "load_zone_definition",
    "classify_points",
    "compute_r_theta",
    "choose_position_bodypart",
    "Track",
    "_compose_body_head_nose_tracks",
    "ZONE_UNKNOWN",
    "ZONE_OPEN",
    "ZONE_CLOSED",
    "ZONE_OFF_TRACK",
    "ZONE_BUFFER",
]

# Zone label constants for unified per-frame zone assignment
ZONE_UNKNOWN: int = 0
ZONE_OPEN: int = 1
ZONE_CLOSED: int = 2
ZONE_OFF_TRACK: int = 3
ZONE_BUFFER: int = 4  # within angular hysteresis buffer at boundary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_float_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


class Track(TypedDict):
    x: np.ndarray
    y: np.ndarray
    ok: np.ndarray
    p_ok_mean: float
    above_frac: float


def try_read_dlc_csv(dlc_csv_path: Path) -> Optional[pd.DataFrame]:
    """Read DLC CSV with 3-row header -> MultiIndex (bodypart, coord)."""
    try:
        df = pd.read_csv(dlc_csv_path, header=[0, 1, 2], index_col=0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
        return None
    try:
        df.columns = df.columns.droplevel(0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 2:
        return None
    return df


def choose_position_bodypart(bodyparts: Sequence[str], preferred: str = "") -> str:
    preferred = str(preferred or "").strip()
    if preferred and preferred in bodyparts:
        return preferred
    for bp in ("body_center", "neck_base", "head", "nose"):
        if bp in bodyparts:
            return bp
    return bodyparts[0]


# ---------------------------------------------------------------------------
# Track extraction
# ---------------------------------------------------------------------------

def _bp_track(
    df: pd.DataFrame,
    bp: str,
    likelihood_threshold: float,
    max_interp_gap_frames: int,
) -> Track:
    x = _as_float_series(df[(bp, "x")])
    y = _as_float_series(df[(bp, "y")])
    p = _as_float_series(df[(bp, "likelihood")])

    above = p >= likelihood_threshold
    x_fill = x.where(above).interpolate(limit=max_interp_gap_frames, limit_direction="both")
    y_fill = y.where(above).interpolate(limit=max_interp_gap_frames, limit_direction="both")
    ok = (x_fill.notna() & y_fill.notna()).to_numpy(dtype=bool)

    mask = above & x_fill.notna() & y_fill.notna()
    if int(mask.sum()) == 0:
        p_ok_mean = float("nan")
    else:
        p_ok_mean = float(np.nanmean(p.where(mask).to_numpy(dtype=float)))
    above_frac = float(np.nanmean(above.to_numpy(dtype=float)))

    return {
        "x": x_fill.to_numpy(dtype=float),
        "y": y_fill.to_numpy(dtype=float),
        "ok": ok,
        "p_ok_mean": p_ok_mean,
        "above_frac": above_frac,
    }


def _apply_bodypart_bound(
    track: Track,
    ref_track: Track,
    bound_px: float,
    max_interp_gap_frames: int = 10,
) -> Track:
    """Reject frames where track is > bound_px from ref_track, then re-interpolate.

    This removes ghost-point detections (e.g. nose detected far from head).
    """
    x = track["x"].copy()
    y = track["y"].copy()
    ok = track["ok"].copy()
    ref_ok = ref_track["ok"]

    both = ok & ref_ok
    dist = np.full(len(x), np.nan)
    dist[both] = np.sqrt(
        (x[both] - ref_track["x"][both]) ** 2
        + (y[both] - ref_track["y"][both]) ** 2
    )

    reject = both & (dist > bound_px)
    x[reject] = np.nan
    y[reject] = np.nan
    ok[reject] = False
    n_rejected = int(np.sum(reject))

    # Re-interpolate after rejection
    xs = pd.Series(x).interpolate(limit=max_interp_gap_frames, limit_direction="both")
    ys = pd.Series(y).interpolate(limit=max_interp_gap_frames, limit_direction="both")
    ok2 = (xs.notna() & ys.notna()).to_numpy(dtype=bool)

    return {
        "x": xs.to_numpy(dtype=float),
        "y": ys.to_numpy(dtype=float),
        "ok": ok2,
        "p_ok_mean": track["p_ok_mean"],
        "above_frac": track["above_frac"],
    }


def _rolling_mean_nan(x: np.ndarray, window: int) -> np.ndarray:
    s = pd.Series(np.asarray(x, dtype=float))
    return s.rolling(window=int(window), center=True, min_periods=1).mean().to_numpy(dtype=float)


def _speed_px_s(x: np.ndarray, y: np.ndarray, fps: float) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    dx = np.diff(x)
    dy = np.diff(y)
    sp = np.sqrt(dx * dx + dy * dy) * float(fps)
    return np.concatenate([[np.nan], sp])


def _velocity_gate_ok(x: np.ndarray, y: np.ndarray, ok: np.ndarray, fps: float, max_speed_px_s: float) -> np.ndarray:
    ok = np.asarray(ok, dtype=bool)
    sp = _speed_px_s(x, y, fps=float(fps))
    return ok & np.isfinite(sp) & (sp <= float(max_speed_px_s))


# ---------------------------------------------------------------------------
# Derived tracks (body / head / nose)
# ---------------------------------------------------------------------------

def _compose_body_head_nose_tracks(
    df: pd.DataFrame,
    zones: ZoneDefinition,
    fps: float,
    likelihood_threshold: float,
    max_interp_gap_frames: int,
    max_speed_px_s: float = 12000.0,
    smooth_window: int = 7,
    nose_mode: str = "blend",
) -> tuple:
    """Build derived body, head, nose tracks.

    Returns (body_t, head_t, nose_t, qc_dict).
    """
    bodyparts = sorted(set(df.columns.get_level_values(0)))
    have = set(bodyparts)

    def has(bp: str) -> bool:
        return bp in have

    t_tail = _bp_track(df, "tail_base", likelihood_threshold, max_interp_gap_frames) if has("tail_base") else None
    t_bodyc = _bp_track(df, "body_center", likelihood_threshold, max_interp_gap_frames) if has("body_center") else None
    t_neck = _bp_track(df, "neck_base", likelihood_threshold, max_interp_gap_frames) if has("neck_base") else None
    t_head = _bp_track(df, "head", likelihood_threshold, max_interp_gap_frames) if has("head") else None
    t_nose = _bp_track(df, "nose", likelihood_threshold, max_interp_gap_frames) if has("nose") else None
    t_le = _bp_track(df, "left_ear", likelihood_threshold, max_interp_gap_frames) if has("left_ear") else None
    t_re = _bp_track(df, "right_ear", likelihood_threshold, max_interp_gap_frames) if has("right_ear") else None

    n = int(len(df))
    nan = np.full(n, np.nan, dtype=float)
    false = np.zeros(n, dtype=bool)

    # Body: prefer body_center, else midpoint(neck,tail), else neck, else tail.
    bx = nan.copy(); by = nan.copy(); bok = false.copy()
    if t_bodyc is not None:
        bx = np.where(t_bodyc["ok"], t_bodyc["x"], bx)
        by = np.where(t_bodyc["ok"], t_bodyc["y"], by)
        bok = bok | t_bodyc["ok"]
    if t_neck is not None and t_tail is not None:
        mid_ok = (~bok) & t_neck["ok"] & t_tail["ok"]
        bx = np.where(mid_ok, 0.5 * (t_neck["x"] + t_tail["x"]), bx)
        by = np.where(mid_ok, 0.5 * (t_neck["y"] + t_tail["y"]), by)
        bok = bok | mid_ok
    if t_neck is not None:
        take = (~bok) & t_neck["ok"]
        bx = np.where(take, t_neck["x"], bx); by = np.where(take, t_neck["y"], by); bok = bok | take
    if t_tail is not None:
        take = (~bok) & t_tail["ok"]
        bx = np.where(take, t_tail["x"], bx); by = np.where(take, t_tail["y"], by); bok = bok | take

    # Head: prefer neck_base, else head, else body_center
    hx = nan.copy(); hy = nan.copy(); hok = false.copy()
    if t_neck is not None:
        hx = np.where(t_neck["ok"], t_neck["x"], hx)
        hy = np.where(t_neck["ok"], t_neck["y"], hy)
        hok = hok | t_neck["ok"]
    if t_head is not None:
        take = (~hok) & t_head["ok"]
        hx = np.where(take, t_head["x"], hx); hy = np.where(take, t_head["y"], hy); hok = hok | take
    if t_bodyc is not None:
        take = (~hok) & t_bodyc["ok"]
        hx = np.where(take, t_bodyc["x"], hx); hy = np.where(take, t_bodyc["y"], hy); hok = hok | take

    # Velocity gate + smooth body/head
    bok2 = _velocity_gate_ok(bx, by, bok, fps=float(fps), max_speed_px_s=float(max_speed_px_s))
    hok2 = _velocity_gate_ok(hx, hy, hok, fps=float(fps), max_speed_px_s=float(max_speed_px_s))
    bx_s = _rolling_mean_nan(pd.Series(bx).where(bok2).to_numpy(dtype=float), window=smooth_window)
    by_s = _rolling_mean_nan(pd.Series(by).where(bok2).to_numpy(dtype=float), window=smooth_window)
    hx_s = _rolling_mean_nan(pd.Series(hx).where(hok2).to_numpy(dtype=float), window=smooth_window)
    hy_s = _rolling_mean_nan(pd.Series(hy).where(hok2).to_numpy(dtype=float), window=smooth_window)
    bok_s = np.isfinite(bx_s) & np.isfinite(by_s)
    hok_s = np.isfinite(hx_s) & np.isfinite(hy_s)

    # Nose prediction from heading
    nx_raw = t_nose["x"] if t_nose is not None else nan.copy()
    ny_raw = t_nose["y"] if t_nose is not None else nan.copy()
    nok_raw = t_nose["ok"] if t_nose is not None else false.copy()

    L = np.nan
    if t_nose is not None:
        both = nok_raw & hok_s
        if int(np.sum(both)) > 20:
            d = np.sqrt((nx_raw[both] - hx_s[both]) ** 2 + (ny_raw[both] - hy_s[both]) ** 2)
            L = float(np.nanmedian(d))
    if not np.isfinite(L) or L <= 0:
        L = 30.0

    vx = hx_s - bx_s; vy = hy_s - by_s
    vnorm = np.sqrt(vx * vx + vy * vy)
    ux = np.full_like(vx, np.nan, dtype=float)
    uy = np.full_like(vy, np.nan, dtype=float)
    np.divide(vx, vnorm, out=ux, where=vnorm > 1e-6)
    np.divide(vy, vnorm, out=uy, where=vnorm > 1e-6)
    nose_hat_x = hx_s + float(L) * ux
    nose_hat_y = hy_s + float(L) * uy
    nose_hat_ok = hok_s & bok_s & np.isfinite(nose_hat_x) & np.isfinite(nose_hat_y)

    ear_ok = false.copy()
    if t_le is not None and t_re is not None:
        ear_ok = t_le["ok"] & t_re["ok"]

    nm = str(nose_mode).lower()
    nx = nan.copy(); ny = nan.copy(); nok = false.copy()
    if nm == "raw":
        nx, ny, nok = nx_raw, ny_raw, nok_raw
    elif nm == "derived":
        nx, ny, nok = nose_hat_x, nose_hat_y, nose_hat_ok
    else:
        both = nok_raw & nose_hat_ok
        w = np.where(ear_ok, 0.75, 0.25).astype(float)
        nx = np.where(both, w * nx_raw + (1.0 - w) * nose_hat_x, np.where(nok_raw, nx_raw, nose_hat_x))
        ny = np.where(both, w * ny_raw + (1.0 - w) * nose_hat_y, np.where(nok_raw, ny_raw, nose_hat_y))
        nok = nok_raw | nose_hat_ok

    nok2 = _velocity_gate_ok(nx, ny, nok, fps=float(fps), max_speed_px_s=float(max_speed_px_s))
    nx_s = _rolling_mean_nan(pd.Series(nx).where(nok2).to_numpy(dtype=float), window=smooth_window)
    ny_s = _rolling_mean_nan(pd.Series(ny).where(nok2).to_numpy(dtype=float), window=smooth_window)
    nok_s = np.isfinite(nx_s) & np.isfinite(ny_s)

    qc = {
        "body_ok_fraction": float(np.mean(bok_s.astype(float))) if n > 0 else np.nan,
        "head_ok_fraction": float(np.mean(hok_s.astype(float))) if n > 0 else np.nan,
        "nose_ok_fraction": float(np.mean(nok_s.astype(float))) if n > 0 else np.nan,
        "nose_hat_len_px": float(L),
        "body_speed_p99_px_s": float(np.nanquantile(_speed_px_s(bx_s, by_s, float(fps)), 0.99)),
        "nose_speed_p99_px_s": float(np.nanquantile(_speed_px_s(nx_s, ny_s, float(fps)), 0.99)),
    }

    body_t: Track = {"x": bx_s, "y": by_s, "ok": bok_s, "p_ok_mean": float(t_bodyc["p_ok_mean"]) if t_bodyc is not None else np.nan, "above_frac": float(t_bodyc["above_frac"]) if t_bodyc is not None else np.nan}
    head_t: Track = {"x": hx_s, "y": hy_s, "ok": hok_s, "p_ok_mean": float(t_neck["p_ok_mean"]) if t_neck is not None else np.nan, "above_frac": float(t_neck["above_frac"]) if t_neck is not None else np.nan}
    nose_t: Track = {"x": nx_s, "y": ny_s, "ok": nok_s, "p_ok_mean": float(t_nose["p_ok_mean"]) if t_nose is not None else np.nan, "above_frac": float(t_nose["above_frac"]) if t_nose is not None else np.nan}
    return body_t, head_t, nose_t, qc


# ---------------------------------------------------------------------------
# 1a: Context-aware zone assignment for low-LH closed-arm frames
# ---------------------------------------------------------------------------

def _build_zone_labels(
    ok: np.ndarray,
    in_open_sector: np.ndarray,
    in_closed_sector: np.ndarray,
    off_track: np.ndarray,
) -> np.ndarray:
    """Build per-frame zone label array from boolean masks."""
    n = len(ok)
    labels = np.full(n, ZONE_UNKNOWN, dtype=np.int8)
    labels[in_open_sector] = ZONE_OPEN
    labels[in_closed_sector] = ZONE_CLOSED
    labels[off_track] = ZONE_OFF_TRACK
    # Frames with ok=False remain ZONE_UNKNOWN
    return labels


def _context_fill_closed(
    zone_labels: np.ndarray,
    ok: np.ndarray,
    speed_px_s: np.ndarray,
    max_gap_frames: int = 30,
    max_speed_px_s: float = 500.0,
) -> tuple:
    """Fill ZONE_UNKNOWN gaps with closed-arm assignment when context supports it.

    Only fills when:
    - Last confident zone before the gap was ZONE_CLOSED
    - Gap length <= max_gap_frames
    - Speed at gap boundaries is below max_speed_px_s (mouse isn't moving fast)

    Returns (filled_labels, n_context_filled_frames).
    """
    filled = zone_labels.copy()
    n = len(filled)
    n_filled = 0
    i = 0
    while i < n:
        if ok[i]:
            i += 1
            continue
        # Find gap: [i, j) are all ok=False
        j = i
        while j < n and not ok[j]:
            j += 1
        gap_len = j - i
        if gap_len <= max_gap_frames and i > 0:
            last_zone = int(filled[i - 1])
            if last_zone == ZONE_CLOSED:
                speed_ok = True
                if np.isfinite(speed_px_s[i - 1]):
                    speed_ok = speed_ok and (speed_px_s[i - 1] <= max_speed_px_s)
                if j < n and np.isfinite(speed_px_s[j]):
                    speed_ok = speed_ok and (speed_px_s[j] <= max_speed_px_s)
                if speed_ok:
                    filled[i:j] = ZONE_CLOSED
                    n_filled += gap_len
        i = j if j > i else i + 1
    return filled, n_filled


# ---------------------------------------------------------------------------
# 1b: Committed-transition exit counting with dwell time + hysteresis
# ---------------------------------------------------------------------------

def _angular_distance(theta: np.ndarray, boundary: float) -> np.ndarray:
    """Signed angular distance from boundary, wrapped to [-pi, pi]."""
    return np.abs(np.mod(theta - boundary + math.pi, TAU) - math.pi)


def _apply_boundary_hysteresis(
    zone_labels: np.ndarray,
    theta: np.ndarray,
    open_angle_ranges: Sequence,
    buffer_rad: float,
) -> np.ndarray:
    """Mark frames within buffer_rad of any open/closed boundary as ZONE_BUFFER."""
    if buffer_rad <= 0:
        return zone_labels
    labels = zone_labels.copy()
    for start, end in open_angle_ranges:
        for boundary in (float(start), float(end)):
            near = _angular_distance(theta, boundary) <= buffer_rad
            # Only mark frames that were open or closed (don't override unknown/off_track)
            definitive = (labels == ZONE_OPEN) | (labels == ZONE_CLOSED)
            labels[near & definitive] = ZONE_BUFFER
    return labels


def _count_committed_transitions(
    zone_labels: np.ndarray,
    from_zone: int,
    to_zone: int,
    dwell_frames: int,
    max_gap: int = 10,
) -> int:
    """Count committed transitions from from_zone to to_zone.

    A transition is counted when the animal spends >= dwell_frames in to_zone
    after being committed to from_zone. Non-definitive frames (unknown,
    off_track, buffer) pause the dwell counter; gaps > max_gap reset it.
    """
    n = len(zone_labels)
    committed = 0  # not yet committed
    candidate = 0
    cand_count = 0
    gap_count = 0
    count = 0

    for i in range(n):
        z = int(zone_labels[i])

        if z == from_zone or z == to_zone:
            gap_count = 0
            if z == candidate:
                cand_count += 1
            else:
                candidate = z
                cand_count = 1

            if committed == 0:
                if cand_count >= dwell_frames:
                    committed = candidate
            elif cand_count >= dwell_frames and candidate != committed:
                if committed == from_zone and candidate == to_zone:
                    count += 1
                committed = candidate
        else:
            gap_count += 1
            if gap_count > max_gap:
                cand_count = 0
                candidate = 0

    return count


def _count_committed_transitions_gated(
    zone_labels: np.ndarray,
    from_zone: int,
    to_zone: int,
    dwell_frames: int,
    theta: np.ndarray,
    open_angle_ranges: Sequence,
    boundary_corridor_deg: float = 5.0,
    max_gap: int = 10,
) -> tuple:
    """Count committed transitions with boundary-crossing gate.

    Like _count_committed_transitions, but each counted transition is also
    checked for physical plausibility: the trajectory must pass within
    ±boundary_corridor_deg of a sector boundary angle during the transition
    window (from last committed from_zone frame to first committed to_zone
    frame).

    Returns:
        (total_transitions, clean_transitions, artifact_transitions)
        where clean = crossed a boundary, artifact = did not.
    """
    corridor_rad = math.radians(float(boundary_corridor_deg))
    # Collect all boundary angles
    boundaries = []
    for start, end in open_angle_ranges:
        boundaries.append(float(start))
        boundaries.append(float(end))

    n = len(zone_labels)
    committed = 0
    candidate = 0
    cand_count = 0
    gap_count = 0
    total = 0
    clean = 0
    # Track the frame where commitment to from_zone was established
    committed_from_frame = -1

    for i in range(n):
        z = int(zone_labels[i])

        if z == from_zone or z == to_zone:
            gap_count = 0
            if z == candidate:
                cand_count += 1
            else:
                candidate = z
                cand_count = 1

            if committed == 0:
                if cand_count >= dwell_frames:
                    committed = candidate
                    if committed == from_zone:
                        committed_from_frame = i
            elif cand_count >= dwell_frames and candidate != committed:
                if committed == from_zone and candidate == to_zone:
                    total += 1
                    # Check boundary crossing in the window
                    # Window: from the last committed from_zone frame to current frame
                    win_start = max(0, committed_from_frame)
                    win_end = i + 1
                    crossed = False
                    for b in boundaries:
                        window_dist = _angular_distance(theta[win_start:win_end], b)
                        if len(window_dist) > 0 and float(np.nanmin(window_dist)) <= corridor_rad:
                            crossed = True
                            break
                    if crossed:
                        clean += 1
                committed = candidate
                if committed == from_zone:
                    committed_from_frame = i
        else:
            gap_count += 1
            if gap_count > max_gap:
                cand_count = 0
                candidate = 0

    return total, clean, total - clean


# ---------------------------------------------------------------------------
# 1c: Latency-to-first-open and immobility
# ---------------------------------------------------------------------------

def _latency_to_first_open(zone_labels: np.ndarray, fps: float) -> float:
    """Time in seconds from recording start to first ZONE_OPEN frame.

    Returns NaN if the animal never enters an open arm.
    """
    open_indices = np.where(zone_labels == ZONE_OPEN)[0]
    if len(open_indices) == 0:
        return float("nan")
    return float(open_indices[0]) / float(fps)


def _compute_immobility(
    speed_px_s: np.ndarray,
    ok: np.ndarray,
    px_to_mm: float,
    threshold_mm_s: float = 20.0,
) -> tuple:
    """Classify frames as immobile (speed < threshold).

    Args:
        speed_px_s: per-frame speed in pixels/second
        ok: boolean mask of valid frames
        px_to_mm: conversion factor (mm per pixel)
        threshold_mm_s: immobility threshold in mm/s (default 20 = 2 cm/s)

    Returns (immobile_mask, immobile_fraction, immobile_time_s_would_need_fps).
    """
    speed_mm_s = np.abs(speed_px_s) * px_to_mm
    immobile = ok & np.isfinite(speed_mm_s) & (speed_mm_s < threshold_mm_s)
    valid = ok & np.isfinite(speed_mm_s)
    n_valid = int(np.sum(valid))
    frac = float(np.sum(immobile)) / n_valid if n_valid > 0 else float("nan")
    return immobile, frac


# ---------------------------------------------------------------------------
# 1e: Head-corrected track (fallback to nearby high-LH bodyparts)
# ---------------------------------------------------------------------------

def _head_corrected_track(
    df: pd.DataFrame,
    likelihood_threshold: float,
    max_interp_gap_frames: int,
    primary_bp: str = "head",
    fallback_bps: Sequence[str] = ("neck_base", "nose"),
) -> tuple:
    """Build a corrected head track using fallback bodyparts when head LH drops.

    Head is the point of interest.  When head likelihood drops below threshold,
    the highest-LH nearby bodypart is used as a position proxy for that frame.
    Remaining gaps are interpolated.

    Returns:
        x, y: corrected position arrays (float64)
        ok: boolean mask of valid frames
        corrected: boolean mask of frames where a fallback bodypart was used
        corrected_fraction: fraction of ok frames that used fallback
        fallback_counts: dict {bodypart_name: n_frames_used}
    """
    bodyparts = sorted(set(df.columns.get_level_values(0)))
    have = set(bodyparts)

    if primary_bp not in have:
        primary_bp = "head" if "head" in have else bodyparts[0]

    n = int(len(df))

    # Primary bodypart raw data
    prim_x = _as_float_series(df[(primary_bp, "x")]).to_numpy(dtype=float)
    prim_y = _as_float_series(df[(primary_bp, "y")]).to_numpy(dtype=float)
    prim_lh = _as_float_series(df[(primary_bp, "likelihood")]).to_numpy(dtype=float)
    prim_good = (prim_lh >= likelihood_threshold) & np.isfinite(prim_x) & np.isfinite(prim_y)

    # Fallback bodypart raw data
    fb_data = []
    for bp in fallback_bps:
        if bp not in have or bp == primary_bp:
            continue
        bx = _as_float_series(df[(bp, "x")]).to_numpy(dtype=float)
        by = _as_float_series(df[(bp, "y")]).to_numpy(dtype=float)
        blh = _as_float_series(df[(bp, "likelihood")]).to_numpy(dtype=float)
        fb_data.append((bp, bx, by, blh))

    # Build corrected track
    x = prim_x.copy()
    y = prim_y.copy()
    corrected = np.zeros(n, dtype=bool)
    fallback_counts: Dict[str, int] = {}

    for i in range(n):
        if prim_good[i]:
            continue  # head is good, use directly

        # Head LH is low — find best available fallback
        best_bp_name = ""
        best_lh = 0.0
        best_x = np.nan
        best_y = np.nan

        for bp_name, bx, by, blh in fb_data:
            if np.isfinite(blh[i]) and blh[i] >= likelihood_threshold and blh[i] > best_lh:
                if np.isfinite(bx[i]) and np.isfinite(by[i]):
                    best_bp_name = bp_name
                    best_lh = blh[i]
                    best_x = bx[i]
                    best_y = by[i]

        if best_bp_name:
            x[i] = best_x
            y[i] = best_y
            corrected[i] = True
            fallback_counts[best_bp_name] = fallback_counts.get(best_bp_name, 0) + 1
        else:
            x[i] = np.nan
            y[i] = np.nan

    # Interpolate remaining gaps
    xs = pd.Series(x).interpolate(limit=max_interp_gap_frames, limit_direction="both")
    ys = pd.Series(y).interpolate(limit=max_interp_gap_frames, limit_direction="both")
    ok = (xs.notna() & ys.notna()).to_numpy(dtype=bool)

    n_ok = int(np.sum(ok))
    n_corrected = int(np.sum(corrected & ok))
    corrected_fraction = float(n_corrected) / float(n_ok) if n_ok > 0 else 0.0

    return (
        xs.to_numpy(dtype=float),
        ys.to_numpy(dtype=float),
        ok,
        corrected,
        corrected_fraction,
        fallback_counts,
    )


# ---------------------------------------------------------------------------
# Main per-video compute
# ---------------------------------------------------------------------------

def compute_open_closed_metrics(
    df: pd.DataFrame,
    zones: ZoneDefinition,
    fps: float,
    likelihood_threshold: float,
    max_interp_gap_frames: int,
    open_count_mode: str = "track",
    bodypart_preferred: str = "",
    invert_open_closed: bool = False,
    position_mode: str = "derived_body",
    nose_mode: str = "blend",
    # 1a: context-aware zone fill
    context_fill_closed: bool = False,
    max_context_gap_frames: int = 30,
    context_max_speed_px_s: float = 500.0,
    # 1b: committed-transition entry counting
    dwell_time_s: float = 0.5,
    hysteresis_deg: float = 2.0,
    # 1c: immobility
    immobility_cm_s: float = 2.0,
    outer_diameter_mm: float = 460.0,
    # bodypart-bounded ghost rejection
    bodypart_bound_px: float = 0.0,
    bound_reference_bp: str = "",
    # 1e: head-corrected track fallback bodyparts
    consensus_voter_bps: Sequence[str] = ("neck_base", "nose"),
) -> Dict[str, float]:
    """Compute EZM open/closed time metrics for a single video."""
    n_frames = int(len(df))
    bodyparts = sorted(set(df.columns.get_level_values(0)))
    pos_mode = str(position_mode).lower()
    nose_mode_s = str(nose_mode).lower()

    bp_raw = choose_position_bodypart(bodyparts, preferred=str(bodypart_preferred))
    raw = _bp_track(df, bp_raw, likelihood_threshold, max_interp_gap_frames)

    body_t, head_t, nose_t, qc = _compose_body_head_nose_tracks(
        df=df, zones=zones, fps=float(fps),
        likelihood_threshold=float(likelihood_threshold),
        max_interp_gap_frames=int(max_interp_gap_frames),
        max_speed_px_s=12000.0, smooth_window=7, nose_mode=nose_mode_s,
    )

    if pos_mode in ("derived", "derived_body"):
        pos = body_t; bp_used = "derived_body"
    elif pos_mode == "derived_nose":
        pos = nose_t; bp_used = "derived_nose"
    elif pos_mode == "bounded" and float(bodypart_bound_px) > 0 and str(bound_reference_bp):
        # Bodypart-bounded: raw track with ghost-point rejection
        ref_bp = str(bound_reference_bp)
        if ref_bp in set(df.columns.get_level_values(0)):
            ref_track = _bp_track(df, ref_bp, likelihood_threshold, max_interp_gap_frames)
            pos = _apply_bodypart_bound(raw, ref_track, float(bodypart_bound_px), max_interp_gap_frames)
            bp_used = f"bounded_{bp_raw}"
        else:
            pos = raw; bp_used = bp_raw
    elif pos_mode == "consensus":
        # 1e: Head-corrected track — fallback to high-LH nearby bodyparts
        _corr_x, _corr_y, _corr_ok, _corr_mask, _corr_frac, _corr_fb_counts = \
            _head_corrected_track(
                df, float(likelihood_threshold), int(max_interp_gap_frames),
                primary_bp=str(bodypart_preferred) or "head",
                fallback_bps=tuple(consensus_voter_bps),
            )
        pos = {
            "x": _corr_x, "y": _corr_y, "ok": _corr_ok,
            "p_ok_mean": raw["p_ok_mean"], "above_frac": raw["above_frac"],
        }
        bp_used = "consensus"
    else:
        pos = raw; bp_used = bp_raw

    xy_ok = pos["ok"]
    if int(np.sum(xy_ok)) == 0:
        return {
            "n_frames": float(n_frames), "bodypart_used": bp_used,
            "nose_mode": str(nose_mode_s), "position_mode": str(pos_mode),
            "pct_frames_above_thr": np.nan, "pct_frames_xy_filled": 0.0,
            "valid_time_s": np.nan, "open_time_s": np.nan,
            "closed_time_s": np.nan, "open_fraction": np.nan, "closed_fraction": np.nan,
        }

    x_arr = pos["x"]; y_arr = pos["y"]
    in_track, in_open, in_closed, r, theta = classify_points(x_arr, y_arr, zones)
    ok = np.asarray(xy_ok, dtype=bool)
    in_track = in_track & ok; in_open = in_open & ok; in_closed = in_closed & ok
    off_track = (~in_track) & ok
    outside_outer = (r > 1.0) & ok
    inside_inner = (r < float(zones.r_inner)) & ok

    open_by_theta = angle_in_any_open_range(theta, zones.open_angle_ranges)
    if invert_open_closed:
        open_by_theta = ~open_by_theta
    in_open_sector = (r >= float(zones.r_inner)) & open_by_theta & ok
    in_closed_sector = (r >= float(zones.r_inner)) & (~open_by_theta) & ok

    # Nose-based off-edge metrics
    nx_arr = nose_t["x"]; ny_arr = nose_t["y"]; nok = np.asarray(nose_t["ok"], dtype=bool)
    _in_track_n, _in_open_n, _in_closed_n, r_n, theta_n = classify_points(nx_arr, ny_arr, zones)
    open_by_theta_n = angle_in_any_open_range(theta_n, zones.open_angle_ranges)
    if invert_open_closed:
        open_by_theta_n = ~open_by_theta_n
    outside_outer_n = (r_n > 1.0) & nok
    outside_outer_open = outside_outer_n & open_by_theta_n
    outside_outer_closed = outside_outer_n & (~open_by_theta_n)
    inside_inner_n = (r_n < float(zones.r_inner)) & nok
    inside_inner_closed_n = inside_inner_n & (~open_by_theta_n)

    nose_in_open_sector = (r_n >= float(zones.r_inner)) & open_by_theta_n & nok
    nose_in_closed_sector = (r_n >= float(zones.r_inner)) & (~open_by_theta_n) & nok
    nose_open_time_s_sector = float(int(np.sum(nose_in_open_sector)) / float(fps))
    nose_closed_time_s_sector = float(int(np.sum(nose_in_closed_sector)) / float(fps))
    nose_valid_time_s_sector = float((int(np.sum(nose_in_open_sector)) + int(np.sum(nose_in_closed_sector))) / float(fps))
    denom_n = int(np.sum(nose_in_open_sector)) + int(np.sum(nose_in_closed_sector))
    nose_open_fraction_sector = float(int(np.sum(nose_in_open_sector)) / denom_n) if denom_n > 0 else np.nan

    def _count_transitions(prev_mask, next_mask, ok_mask, min_prev_frames=3, min_next_frames=3):
        prev_mask = np.asarray(prev_mask, dtype=bool) & np.asarray(ok_mask, dtype=bool)
        next_mask = np.asarray(next_mask, dtype=bool) & np.asarray(ok_mask, dtype=bool)
        nn = int(len(prev_mask))
        if nn == 0:
            return 0
        state = np.zeros(nn, dtype=np.int8)
        state[prev_mask] = 1; state[next_mask] = 2
        count = 0; i = 0
        while i < nn:
            if state[i] != 1:
                i += 1; continue
            j = i
            while j < nn and state[j] == 1:
                j += 1
            if j - i < int(min_prev_frames):
                i = j; continue
            k = j
            while k < nn and state[k] == 0:
                k += 1
                if (k - j) > 2:
                    break
            if k < nn and state[k] == 2:
                m = k
                while m < nn and state[m] == 2:
                    m += 1
                if m - k >= int(min_next_frames):
                    count += 1; i = m; continue
            i = j
        return int(count)

    # ── Build unified zone labels ─────────────────────────────────
    zone_labels = _build_zone_labels(ok, in_open_sector, in_closed_sector, off_track)

    # 1a: Context-aware closed-arm fill for low-LH gaps
    body_speed = _speed_px_s(x_arr, y_arr, float(fps))
    context_filled_frames = 0
    if context_fill_closed:
        zone_labels, context_filled_frames = _context_fill_closed(
            zone_labels, ok, body_speed,
            max_gap_frames=int(max_context_gap_frames),
            max_speed_px_s=float(context_max_speed_px_s),
        )

    # 1b: Apply angular hysteresis buffer at zone boundaries
    hysteresis_rad = math.radians(float(hysteresis_deg))
    zone_labels_hyst = _apply_boundary_hysteresis(
        zone_labels, theta, zones.open_angle_ranges, hysteresis_rad,
    )

    # Recount frames from zone labels (includes context-filled)
    open_frames_track = int(np.sum(in_open)); closed_frames_track = int(np.sum(in_closed))
    denom_track = open_frames_track + closed_frames_track
    open_frames_sector = int(np.sum(zone_labels == ZONE_OPEN))
    closed_frames_sector = int(np.sum(zone_labels == ZONE_CLOSED))
    denom_sector = open_frames_sector + closed_frames_sector
    off_track_frames = int(np.sum(zone_labels == ZONE_OFF_TRACK))

    open_time_s_track = open_frames_track / float(fps)
    closed_time_s_track = closed_frames_track / float(fps)
    valid_time_s_track = denom_track / float(fps)
    open_time_s_sector = open_frames_sector / float(fps)
    closed_time_s_sector = closed_frames_sector / float(fps)
    valid_time_s_sector = denom_sector / float(fps)
    off_track_time_s = off_track_frames / float(fps)

    open_fraction_track = (open_frames_track / denom_track) if denom_track > 0 else np.nan
    closed_fraction_track = (closed_frames_track / denom_track) if denom_track > 0 else np.nan
    open_fraction_sector = (open_frames_sector / denom_sector) if denom_sector > 0 else np.nan
    closed_fraction_sector = (closed_frames_sector / denom_sector) if denom_sector > 0 else np.nan

    if str(open_count_mode).lower() == "sector":
        open_time_s = float(open_time_s_sector); closed_time_s = float(closed_time_s_sector)
        valid_time_s = float(valid_time_s_sector)
        open_fraction = float(open_fraction_sector) if np.isfinite(open_fraction_sector) else np.nan
        closed_fraction = float(closed_fraction_sector) if np.isfinite(closed_fraction_sector) else np.nan
    else:
        open_time_s = float(open_time_s_track); closed_time_s = float(closed_time_s_track)
        valid_time_s = float(valid_time_s_track)
        open_fraction = float(open_fraction_track) if np.isfinite(open_fraction_track) else np.nan
        closed_fraction = float(closed_fraction_track) if np.isfinite(closed_fraction_track) else np.nan

    # 1b: Committed-transition entry counts (with hysteresis labels)
    dwell_frames = max(1, int(round(float(dwell_time_s) * float(fps))))
    committed_closed_to_open = _count_committed_transitions(
        zone_labels_hyst, ZONE_CLOSED, ZONE_OPEN, dwell_frames,
    )
    committed_open_to_closed = _count_committed_transitions(
        zone_labels_hyst, ZONE_OPEN, ZONE_CLOSED, dwell_frames,
    )

    # 1f: Boundary-crossing gated entry counts
    _co_total, _co_clean, _co_artifact = _count_committed_transitions_gated(
        zone_labels_hyst, ZONE_CLOSED, ZONE_OPEN, dwell_frames,
        theta, zones.open_angle_ranges, boundary_corridor_deg=5.0,
    )
    _oc_total, _oc_clean, _oc_artifact = _count_committed_transitions_gated(
        zone_labels_hyst, ZONE_OPEN, ZONE_CLOSED, dwell_frames,
        theta, zones.open_angle_ranges, boundary_corridor_deg=5.0,
    )
    total_entries = _co_total + _oc_total
    artifact_entries = _co_artifact + _oc_artifact
    artifact_rate = float(artifact_entries) / float(total_entries) if total_entries > 0 else 0.0

    # 1c: Latency to first open arm entry
    latency_first_open_s = _latency_to_first_open(zone_labels, float(fps))

    # 1c: Immobility (speed-based)
    mean_diam_px = (float(zones.outer_ellipse.axes_xy[0])
                    + float(zones.outer_ellipse.axes_xy[1])) / 2.0
    px_to_mm = float(outer_diameter_mm) / mean_diam_px if mean_diam_px > 0 else 1.0
    immobility_threshold_mm_s = float(immobility_cm_s) * 10.0  # cm/s -> mm/s
    immobile_mask, immobile_fraction = _compute_immobility(
        body_speed, ok, px_to_mm, immobility_threshold_mm_s,
    )
    immobile_frames = int(np.sum(immobile_mask))
    immobile_time_s = float(immobile_frames) / float(fps)

    # 1c: Total distance in mm
    dx = np.diff(x_arr)
    dy = np.diff(y_arr)
    step_px = np.sqrt(dx * dx + dy * dy)
    # Only count steps where both frames are ok
    ok_steps = ok[:-1] & ok[1:]
    total_distance_mm = float(np.nansum(step_px[ok_steps])) * px_to_mm
    valid_ok = int(np.sum(ok))
    mean_speed_mm_s = total_distance_mm / (float(valid_ok) / float(fps)) if valid_ok > 0 else float("nan")

    out = {
        "n_frames": float(n_frames), "bodypart_used": bp_used,
        "position_mode": str(pos_mode), "nose_mode": str(nose_mode_s),
        "pct_frames_above_thr": float(raw["above_frac"]) if np.isfinite(raw["above_frac"]) else np.nan,
        "pct_frames_xy_filled": float(np.mean(ok.astype(float))),
        "body_ok_fraction": float(qc.get("body_ok_fraction", np.nan)),
        "head_ok_fraction": float(qc.get("head_ok_fraction", np.nan)),
        "nose_ok_fraction": float(qc.get("nose_ok_fraction", np.nan)),
        "nose_hat_len_px": float(qc.get("nose_hat_len_px", np.nan)),
        "body_speed_p99_px_s": float(qc.get("body_speed_p99_px_s", np.nan)),
        "nose_speed_p99_px_s": float(qc.get("nose_speed_p99_px_s", np.nan)),
        "open_count_mode": str(open_count_mode),
        "invert_open_closed": bool(invert_open_closed),
        "valid_time_s": float(valid_time_s),
        "open_time_s": float(open_time_s), "closed_time_s": float(closed_time_s),
        "open_fraction": float(open_fraction), "closed_fraction": float(closed_fraction),
        "off_track_time_s": float(off_track_time_s),
        "off_track_fraction_all_frames": float(off_track_frames / float(n_frames)) if n_frames > 0 else np.nan,
        "outside_outer_time_s": float(int(np.sum(outside_outer)) / float(fps)),
        "outside_outer_open_time_s": float(int(np.sum(outside_outer_open)) / float(fps)),
        "outside_outer_closed_time_s": float(int(np.sum(outside_outer_closed)) / float(fps)),
        "inside_inner_time_s": float(int(np.sum(inside_inner)) / float(fps)),
        "nose_inside_inner_time_s": float(int(np.sum(inside_inner_n)) / float(fps)),
        "nose_open_time_s_sector": float(nose_open_time_s_sector),
        "nose_closed_time_s_sector": float(nose_closed_time_s_sector),
        "nose_valid_time_s_sector": float(nose_valid_time_s_sector),
        "nose_open_fraction_sector": float(nose_open_fraction_sector) if np.isfinite(nose_open_fraction_sector) else np.nan,
        # Legacy simple-debounce entries (preserved for comparison)
        "closed_to_open_entries": float(
            _count_transitions(in_closed_sector, in_open_sector, ok_mask=ok, min_prev_frames=3, min_next_frames=3)
        ),
        "closed_to_outside_open_entries": float(
            _count_transitions(in_closed_sector, outside_outer_open, ok_mask=ok, min_prev_frames=3, min_next_frames=3)
        ),
        # 1b: Committed-transition entries (dwell-time state machine + hysteresis)
        "committed_closed_to_open_entries": float(committed_closed_to_open),
        "committed_open_to_closed_entries": float(committed_open_to_closed),
        "entry_dwell_time_s": float(dwell_time_s),
        "entry_hysteresis_deg": float(hysteresis_deg),
        # 1f: Boundary-crossing gated entries
        "gated_closed_to_open_entries": float(_co_clean),
        "gated_open_to_closed_entries": float(_oc_clean),
        "artifact_closed_to_open_entries": float(_co_artifact),
        "artifact_open_to_closed_entries": float(_oc_artifact),
        "artifact_rate": float(artifact_rate),
        # 1a: Context-aware zone fill diagnostics
        "context_filled_closed_frames": float(context_filled_frames),
        "context_filled_closed_time_s": float(context_filled_frames) / float(fps),
        # 1c: Latency, immobility, locomotion
        "latency_first_open_s": float(latency_first_open_s) if np.isfinite(latency_first_open_s) else np.nan,
        "immobile_time_s": float(immobile_time_s),
        "immobile_fraction": float(immobile_fraction) if np.isfinite(immobile_fraction) else np.nan,
        "immobility_threshold_cm_s": float(immobility_cm_s),
        "total_distance_mm": float(total_distance_mm),
        "mean_speed_mm_s": float(mean_speed_mm_s) if np.isfinite(mean_speed_mm_s) else np.nan,
        "px_to_mm": float(px_to_mm),
        # Track-based (unchanged)
        "open_time_s_track": float(open_time_s_track), "closed_time_s_track": float(closed_time_s_track),
        "valid_time_s_track": float(valid_time_s_track),
        "open_fraction_track": float(open_fraction_track) if np.isfinite(open_fraction_track) else np.nan,
        "closed_fraction_track": float(closed_fraction_track) if np.isfinite(closed_fraction_track) else np.nan,
        "open_time_s_sector": float(open_time_s_sector), "closed_time_s_sector": float(closed_time_s_sector),
        "valid_time_s_sector": float(valid_time_s_sector),
        "open_fraction_sector": float(open_fraction_sector) if np.isfinite(open_fraction_sector) else np.nan,
        "closed_fraction_sector": float(closed_fraction_sector) if np.isfinite(closed_fraction_sector) else np.nan,
    }
    # 1e: Append head-corrected track metrics when in consensus mode
    if pos_mode == "consensus":
        out["corrected_fraction"] = float(_corr_frac)
        out["fallback_counts"] = dict(_corr_fb_counts)
    return out
