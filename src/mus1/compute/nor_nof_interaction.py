"""NOR/NOF object interaction metrics — deterministic per-video computation.

Extracted from ``workspace/dlc_nor_nof_object_interactions/compute_nor_nof_object_interactions.py``.
This module contains only the pure compute functions (no argparse, no file I/O
except DLC CSV reading).

Usage::

    from mus1.compute.nor_nof_interaction import compute_interaction_metrics
    from mus1.compute.tracking import try_read_dlc_csv, bp_track

    df = try_read_dlc_csv(Path("tracking.csv"))
    x, y, ok = bp_track(df, "nose", 0.6, 10)
    metrics = compute_interaction_metrics(
        x=x, y=y, ok=ok,
        objects=[
            ObjectROI(name="object_a", cx=100, cy=200, radius_px=30, role="novel"),
            ObjectROI(name="object_b", cx=400, cy=200, radius_px=30, role="familiar"),
        ],
        arena_center_x=250.0,
        fps=60.0,
    )
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class ObjectROI:
    """A single object region of interest in the arena."""
    name: str
    cx: float
    cy: float
    radius_px: float
    role: str = ""        # "novel", "familiar", or ""
    label: str = ""       # human-readable label


def count_bouts(mask: np.ndarray, min_frames: int = 3) -> int:
    """Count contiguous True runs of length >= min_frames."""
    m = np.asarray(mask, dtype=bool)
    n = m.size
    if n == 0:
        return 0
    count = 0
    i = 0
    while i < n:
        if not m[i]:
            i += 1
            continue
        j = i
        while j < n and m[j]:
            j += 1
        if (j - i) >= min_frames:
            count += 1
        i = j
    return count


def otsu_threshold(values: np.ndarray, n_bins: int = 256) -> float:
    """Otsu threshold for a 1D array of nonneg values. Returns NaN if insufficient data."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v) & (v >= 0)]
    if v.size < 50:
        return float("nan")
    vmax = float(np.percentile(v, 99.5))
    if not np.isfinite(vmax) or vmax <= 0:
        return float("nan")
    v = np.clip(v, 0.0, vmax)
    hist, bin_edges = np.histogram(v, bins=n_bins, range=(0.0, vmax))
    hist = hist.astype(float)
    p = hist / (np.sum(hist) + 1e-12)
    omega = np.cumsum(p)
    mu = np.cumsum(p * (0.5 * (bin_edges[:-1] + bin_edges[1:])))
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom <= 1e-12] = np.nan
    sigma_b2 = (mu_t * omega - mu) ** 2 / denom
    k = int(np.nanargmax(sigma_b2))
    return float(0.5 * (bin_edges[k] + bin_edges[k + 1]))


def compute_interaction_metrics(
    x: np.ndarray,
    y: np.ndarray,
    ok: np.ndarray,
    objects: List[ObjectROI],
    arena_center_x: float,
    fps: float = 60.0,  # NOR/NOF capture standard; callers should pass the real probed fps
    buffer_mode: str = "fixed",
    buffer_px: float = 20.0,
    min_bout_frames: int = 3,
) -> Dict[str, Any]:
    """Compute per-video object interaction metrics.

    Parameters
    ----------
    x, y : array-like
        Bodypart positions (filtered + interpolated).
    ok : array-like (bool)
        Valid-frame mask.
    objects : list of ObjectROI
        Object positions and radii.
    arena_center_x : float
        X coordinate of arena center (for hemisphere division).
    fps : float
        Frames per second.
    buffer_mode : "fixed" or "otsu"
        How to compute interaction threshold beyond object radius.
    buffer_px : float
        Fixed buffer in pixels (used when buffer_mode="fixed").
    min_bout_frames : int
        Minimum consecutive frames for a bout.

    Returns
    -------
    dict with keys per object: ``{name}_time_s``, ``{name}_bouts``,
    ``{name}_fraction``, plus novelty metrics if roles are set.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.asarray(ok, dtype=bool)
    n_frames = len(x)
    ok_frames = int(np.sum(ok))

    metrics: Dict[str, Any] = {
        "n_frames": n_frames,
        "ok_frames": ok_frames,
        "ok_fraction": float(ok_frames / n_frames) if n_frames > 0 else float("nan"),
        "fps": fps,
        "buffer_mode": buffer_mode,
        "buffer_px_fixed": buffer_px,
        "min_bout_frames": min_bout_frames,
        "arena_center_x": arena_center_x,
    }

    # Hemisphere
    left = ok & np.isfinite(x) & (x < arena_center_x)
    right = ok & np.isfinite(x) & (x >= arena_center_x)
    metrics["left_time_s"] = float(np.sum(left)) / fps if fps > 0 else float("nan")
    metrics["right_time_s"] = float(np.sum(right)) / fps if fps > 0 else float("nan")

    # Per-object metrics
    novel_key = None
    familiar_key = None

    for obj in objects:
        dist = np.sqrt((x - obj.cx) ** 2 + (y - obj.cy) ** 2)

        # Buffer computation
        buf = buffer_px
        if buffer_mode == "otsu":
            excess = dist - obj.radius_px
            thr = otsu_threshold(excess[ok])
            if np.isfinite(thr) and thr >= 0:
                buf = thr

        in_zone = ok & np.isfinite(dist) & (dist <= (obj.radius_px + buf))
        zone_frames = int(np.sum(in_zone))
        time_s = float(zone_frames / fps) if fps > 0 else float("nan")
        bouts = count_bouts(in_zone, min_bout_frames)

        prefix = obj.name
        metrics[f"{prefix}_time_s"] = time_s
        metrics[f"{prefix}_bouts"] = bouts
        metrics[f"{prefix}_fraction"] = float(zone_frames / n_frames) if n_frames > 0 else float("nan")
        metrics[f"{prefix}_buffer_px"] = buf
        metrics[f"{prefix}_radius_px"] = obj.radius_px
        metrics[f"{prefix}_role"] = obj.role
        metrics[f"{prefix}_label"] = obj.label

        # Hemisphere breakdown
        metrics[f"{prefix}_left_time_s"] = float(np.sum(in_zone & left)) / fps if fps > 0 else float("nan")
        metrics[f"{prefix}_right_time_s"] = float(np.sum(in_zone & right)) / fps if fps > 0 else float("nan")

        # Track roles
        role = obj.role.strip().lower()
        if role == "novel":
            novel_key = prefix
        elif role == "familiar":
            familiar_key = prefix

    # Novelty metrics
    if novel_key and familiar_key:
        nt = metrics[f"{novel_key}_time_s"]
        ft = metrics[f"{familiar_key}_time_s"]
        denom = nt + ft
        metrics["novel_time_s"] = nt
        metrics["familiar_time_s"] = ft
        if np.isfinite(denom) and denom > 0:
            metrics["novelty_preference"] = nt / denom
            metrics["novelty_index"] = (nt - ft) / denom
        else:
            metrics["novelty_preference"] = float("nan")
            metrics["novelty_index"] = float("nan")

    return metrics
