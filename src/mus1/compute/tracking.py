"""Shared DLC/SLEAP tracking utilities.

Functions for reading pose-estimation CSVs, filtering by likelihood,
interpolating gaps, and extracting bodypart tracks. Used by both
EZM and NOR/NOF compute pipelines.

These are the same patterns duplicated in ezm_compute_bridge._bp_track(),
nor_nof_object_interactions._bp_track(), and overlay.load_dlc_tracks().
Consolidated here as the single implementation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd


def try_read_dlc_csv(path: Path) -> Optional[pd.DataFrame]:
    """Read a DLC CSV with 3-row header into a (bodypart, coord) MultiIndex DataFrame.

    Returns None if the file is unreadable or has the wrong structure.
    """
    try:
        df = pd.read_csv(path, header=[0, 1, 2], index_col=0)
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


def bp_track(
    df: pd.DataFrame,
    bodypart: str,
    likelihood_threshold: float = 0.6,
    max_interp_gap: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract a single bodypart track with likelihood filtering + interpolation.

    Returns (x, y, ok) arrays of length len(df).
    """
    x = pd.to_numeric(df[(bodypart, "x")], errors="coerce")
    y = pd.to_numeric(df[(bodypart, "y")], errors="coerce")
    p = pd.to_numeric(df[(bodypart, "likelihood")], errors="coerce")
    above = p >= likelihood_threshold
    xf = x.where(above).interpolate(limit=max_interp_gap, limit_direction="both")
    yf = y.where(above).interpolate(limit=max_interp_gap, limit_direction="both")
    ok = (xf.notna() & yf.notna()).to_numpy(dtype=bool)
    return xf.to_numpy(dtype=float), yf.to_numpy(dtype=float), ok


def load_all_tracks(
    path: Path,
    likelihood_threshold: float = 0.6,
    max_interp_gap: int = 10,
) -> Optional[Dict[str, Dict[str, np.ndarray]]]:
    """Read DLC CSV and return filtered tracks for all bodyparts.

    Returns ``{bodypart: {"x": ..., "y": ..., "ok": ...}}`` or None.
    """
    df = try_read_dlc_csv(path)
    if df is None:
        return None
    bodyparts = sorted(set(df.columns.get_level_values(0)))
    out: Dict[str, Dict[str, np.ndarray]] = {}
    for bp in bodyparts:
        try:
            x, y, ok = bp_track(df, bp, likelihood_threshold, max_interp_gap)
        except KeyError:
            continue
        out[bp] = {"x": x, "y": y, "ok": ok}
    return out if out else None


def list_bodyparts(df: pd.DataFrame) -> list[str]:
    """Return sorted list of bodypart names in a DLC DataFrame."""
    return sorted(set(df.columns.get_level_values(0)))


def speed_px_per_frame(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Frame-to-frame speed in pixels. First frame is NaN."""
    dx = np.diff(np.asarray(x, dtype=float))
    dy = np.diff(np.asarray(y, dtype=float))
    return np.concatenate([[np.nan], np.sqrt(dx * dx + dy * dy)])
