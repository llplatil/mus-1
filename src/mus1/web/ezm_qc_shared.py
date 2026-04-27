"""Shared utilities for EZM QC views (Zones QC and Tracking QC).

Extracted to avoid duplication between arena-marking QC and tracking QC panes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import streamlit as st

# --- Zone geometry tools (from workspace arena_annotation) ---
_ARENA_ANNOTATION_DIR = str(
    Path(__file__).resolve().parents[3] / "workspace" / "arena_annotation"
)
if _ARENA_ANNOTATION_DIR not in sys.path:
    sys.path.insert(0, _ARENA_ANNOTATION_DIR)

from ezm_geometry import (  # noqa: E402
    zones_from_wedge_points,
    zones_to_json,
)

# Re-export for consumers
__all__ = [
    "LOCKED_POSITION_MODE",
    "LOCKED_BODYPART",
    "LOCKED_LH_THRESHOLD",
    "load_ezm_experiments",
    "resolve_path",
    "load_frame_rgb",
    "video_fps",
    "compute_auto_flags",
    "auto_flags_from_raw_metrics",
    "build_zone_payload_from_wedge_points",
    "zones_from_wedge_points",
    "zones_to_json",
]

# Locked tracking settings (determined from test-cohort QC review)
LOCKED_POSITION_MODE = "raw"
LOCKED_BODYPART = "head"
LOCKED_LH_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Experiment JSON discovery
# ---------------------------------------------------------------------------

from .discovery import CACHE_TTL_SECONDS  # noqa: E402  (after stdlib block above)


@st.cache_data(show_spinner="Loading EZM experiments...", ttl=CACHE_TTL_SECONDS)
def load_ezm_experiments(experiment_data_root: str) -> List[Dict[str, Any]]:
    """Scan ``EZM/`` under every configured data root and return one row per experiment.

    *experiment_data_root* is retained for back-compat; it is treated as a
    project-path anchor (its parent is the project_path used to discover
    additional roots like ``validation_data/``). Configure additional roots
    via ``[paths] data_roots`` in ``mus1.toml`` at the project_path.
    """
    from .discovery import task_dirs_across_roots

    rows: List[Dict[str, Any]] = []
    project_path = Path(experiment_data_root).parent
    exp_dirs = task_dirs_across_roots(project_path, "EZM")
    # Fallback: if discovery returned nothing (e.g. mus1.toml says no roots
    # but the caller passed a real experiment_data_root), still scan it.
    if not exp_dirs:
        ezm_dir = Path(experiment_data_root) / "EZM"
        if ezm_dir.is_dir():
            exp_dirs = sorted(p for p in ezm_dir.iterdir() if p.is_dir())

    for exp_dir in exp_dirs:
        if not exp_dir.is_dir():
            continue
        jsons = [f for f in exp_dir.iterdir() if f.suffix == ".json"]
        if not jsons:
            continue
        jf = jsons[0]
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue

        md = data.get("metadata", {})
        vid = data.get("video", {})
        dd = data.get("derived_data", {})
        az = dd.get("arena_zones") or {}
        cm = (data.get("computed_metrics") or {}).get("ezm_open_closed") or {}
        qc = cm.get("qc_review") or {}
        ext = data.get("extraction") or {}

        zone_json_path = az.get("zone_json_path", "")
        dlc_path = ext.get("tracking_file_path", "")
        am = data.get("arena_markings") or {}
        wp_data = am.get("ezm_wedge_points") or {}
        wp = wp_data.get("points") or []
        arena_qc = wp_data.get("qc") or {}

        # Extract consensus metrics for filtering/sorting
        variants = cm.get("variants") or {}
        cons = (variants.get("consensus_06") or {}).get("metrics") or {}
        _art_rate = cons.get("artifact_rate")
        _corr_frac = cons.get("corrected_fraction")

        rows.append({
            "experiment_id": data.get("experiment_id", exp_dir.name),
            "subject_id": str(md.get("subject_id", "")),
            "date_recorded": str(md.get("date_recorded", "")),
            "genotype": str(md.get("genotype", "")),
            "sex": str(md.get("sex", "")),
            "video_path": vid.get("path", ""),
            "json_path": str(jf),
            "zone_json_path": zone_json_path,
            "zone_method": az.get("method", ""),
            "has_zones": bool(zone_json_path),
            "has_wedge_points": len(wp) == 4,
            "has_dlc_csv": bool(dlc_path),
            "dlc_csv_path": dlc_path,
            "has_computed_metrics": bool(cm and any(k != "qc_review" for k in cm)),
            "qc_status": qc.get("status"),
            "qc_reviewed_at": qc.get("reviewed_at"),
            "arena_qc_status": arena_qc.get("status", ""),
            "artifact_rate": float(_art_rate) if _art_rate is not None else None,
            "corrected_fraction": float(_corr_frac) if _corr_frac is not None else None,
        })
    return rows


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_path(p_str: str) -> Optional[Path]:
    """Resolve a path, handling /center1 vs /import/c1 mount aliasing."""
    if not p_str:
        return None
    p = Path(p_str)
    if p.exists():
        return p
    alt = str(p).replace("/center1/", "/import/c1/")
    if Path(alt).exists():
        return Path(alt)
    alt2 = str(p).replace("/import/c1/", "/center1/")
    if Path(alt2).exists():
        return Path(alt2)
    return None


# ---------------------------------------------------------------------------
# Video helpers
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=60)
def load_frame_rgb(video_abs: str, frame_idx: int) -> Optional[Any]:
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        return None
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.uint8, copy=False)


@st.cache_data(show_spinner=False, ttl=120)
def video_fps(video_abs: str) -> float:
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return 60.0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 60.0)
    cap.release()
    return fps if fps > 1.0 else 60.0


@st.cache_data(show_spinner=False, ttl=120)
def video_frame_count(video_abs: str) -> int:
    """Return total frame count from video file."""
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return 0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return n


# ---------------------------------------------------------------------------
# Auto-flags
# ---------------------------------------------------------------------------

def compute_auto_flags(variants: Dict[str, dict]) -> List[str]:
    flags: List[str] = []
    open_fracs: List[float] = []
    for vname, v in variants.items():
        occ = v.get("occupancy") or v
        of = occ.get("open_fraction")
        if of is not None and np.isfinite(of):
            open_fracs.append(float(of))
            if float(of) > 0.8 or float(of) < 0.05:
                flags.append("POSSIBLE_INVERSION")
            if float(of) == 0.0:
                flags.append("ZERO_OPEN")
            cf = occ.get("closed_fraction")
            if cf is not None and float(cf) == 0.0:
                flags.append("ZERO_CLOSED")
        tqc = v.get("tracking_qc") or v
        pct = tqc.get("pct_frames_above_thr")
        if pct is not None and float(pct) < 0.5:
            flags.append("LOW_TRACKING")
        otf = occ.get("off_track_fraction", occ.get("off_track_fraction_all_frames"))
        if otf is not None and float(otf) > 0.1:
            flags.append("HIGH_OFF_TRACK")
    if len(open_fracs) >= 2 and (max(open_fracs) - min(open_fracs)) > 0.15:
        flags.append("VARIANT_DISAGREEMENT")
    return sorted(set(flags))


def auto_flags_from_raw_metrics(m: dict) -> List[str]:
    """Compute auto-flags from a raw metrics dict (session-state compute result)."""
    flags: List[str] = []
    of = m.get("open_fraction")
    if of is not None:
        if float(of) > 0.8 or float(of) < 0.05:
            flags.append("POSSIBLE_INVERSION")
        if float(of) == 0.0:
            flags.append("ZERO_OPEN")
    pct = m.get("pct_frames_above_thr")
    if pct is not None and float(pct) < 0.5:
        flags.append("LOW_TRACKING")
    otf = m.get("off_track_fraction_all_frames")
    if otf is not None and float(otf) > 0.1:
        flags.append("HIGH_OFF_TRACK")
    return sorted(set(flags))


# ---------------------------------------------------------------------------
# Zone payload from wedge points
# ---------------------------------------------------------------------------

def build_zone_payload_from_wedge_points(
    wedge_points: List,
    frame_shape: Tuple[int, ...],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Build a zone_payload dict from wedge points + frame shape.

    Returns (zone_payload_or_None, warning_str).
    """
    if len(wedge_points) != 4:
        return None, ""
    try:
        zones_obj, warning = zones_from_wedge_points(
            [(p[0], p[1]) for p in wedge_points],
        )
        payload = zones_to_json(
            zones_obj,
            image_wh=(frame_shape[1], frame_shape[0]),
            params={"method": "wedge_circle_fit"},
        )
        return payload, warning
    except Exception as e:
        return None, f"Circle fit failed: {e}"
