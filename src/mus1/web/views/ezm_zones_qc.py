"""EZM Zones QC — per-experiment review and cohort management.

Tracking settings locked to **raw / head / LH≥0.6**.  Per-experiment invert
toggle and QC decisions.  Compute on demand, save when happy.

Source of truth: experiment JSON files on disk (``data/experiment_data/EZM/``).
Cohort membership tracked via manifest files (``data/cohorts/``).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from ..cohorts import (
    add_member,
    cohort_member_ids,
    create_cohort,
    export_training_csv,
    list_cohorts,
    load_cohort,
    remove_member,
    save_cohort,
)
from ..ezm_trajectory_overlay import draw_ezm_qc_overlay, load_dlc_tracks

# --- Zone annotation tools (from workspace arena_annotation) ---
_ARENA_ANNOTATION_DIR = str(
    Path(__file__).resolve().parents[4] / "workspace" / "arena_annotation"
)
if _ARENA_ANNOTATION_DIR not in sys.path:
    sys.path.insert(0, _ARENA_ANNOTATION_DIR)

try:
    from ezm_geometry import (
        EllipseParams,
        boundary_angles_from_wedge_points,
        open_ranges_from_boundary_angles,
        EZMZones,
        zones_to_json,
        save_zones_json,
        zones_from_wedge_points,
    )
    from autofit_from_experiment_jsons import (
        _fit_outer_ellipse_from_points,
        _load_head_track,
    )
    from streamlit_drawable_canvas import st_canvas

    _CAN_ANNOTATE = True
except ImportError:
    _CAN_ANNOTATE = False


# ---------------------------------------------------------------------------
# Experiment JSON discovery
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading EZM experiments...", ttl=120)
def _load_ezm_experiments(experiment_data_root: str) -> List[Dict[str, Any]]:
    """Scan ``data/experiment_data/EZM/`` and return one row per experiment."""
    rows: List[Dict[str, Any]] = []
    ezm_dir = Path(experiment_data_root) / "EZM"
    if not ezm_dir.is_dir():
        return rows
    for exp_dir in sorted(ezm_dir.iterdir()):
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
        wp = (am.get("ezm_wedge_points") or {}).get("points") or []

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
        })
    return rows


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _resolve_path(p_str: str) -> Optional[Path]:
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


def _resolve_zone_json(zone_rel: str, project_root: Path) -> Optional[Path]:
    """Resolve a project-relative zone JSON path."""
    if not zone_rel:
        return None
    p = project_root / zone_rel
    if p.exists():
        return p
    return _resolve_path(str(p))


@st.cache_data(show_spinner=False, ttl=60)
def _load_frame_rgb(video_abs: str, frame_idx: int) -> Optional[Any]:
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
def _video_fps(video_abs: str) -> float:
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return 60.0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 60.0)
    cap.release()
    return fps if fps > 1.0 else 60.0


# ---------------------------------------------------------------------------
# Auto-flags
# ---------------------------------------------------------------------------

def _compute_auto_flags(variants: Dict[str, dict]) -> List[str]:
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


def _auto_flags_from_raw_metrics(m: dict) -> List[str]:
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
# Zone annotation helpers
# ---------------------------------------------------------------------------

_CANVAS_MAX_DIM = 600


@st.cache_data(show_spinner=False, ttl=300)
def _load_zone_template(workspace_root: str) -> Optional[Dict]:
    """Load the zone template JSON from workspace."""
    templates_dir = Path(workspace_root) / "arena_annotation" / "templates"
    if not templates_dir.is_dir():
        return None
    templates = sorted(templates_dir.glob("*.json"))
    if not templates:
        return None
    try:
        return json.loads(templates[0].read_text())
    except Exception:
        return None


@st.cache_data(show_spinner="Fitting ellipse...", ttl=300)
def _fit_ellipse_for_annotation(dlc_csv_path: str) -> Optional[Dict]:
    """Fit outer ellipse from DLC head track for annotation."""
    if not _CAN_ANNOTATE:
        return None
    track = _load_head_track(Path(dlc_csv_path), lh_threshold=0.6)
    if track is None or int(np.sum(track["ok"])) < 100:
        return None
    outer = _fit_outer_ellipse_from_points(track["x"], track["y"], track["ok"])
    return {
        "center": [float(outer.center_xy[0]), float(outer.center_xy[1])],
        "axes": [float(outer.axes_xy[0]), float(outer.axes_xy[1])],
        "angle_deg": float(outer.angle_deg),
    }


def _draw_annotation_guides(
    frame_rgb: np.ndarray, ellipse: Dict, r_inner: float,
) -> np.ndarray:
    """Draw ellipse guide outlines on frame for annotation."""
    img = frame_rgb.copy()
    cx = int(round(ellipse["center"][0]))
    cy = int(round(ellipse["center"][1]))
    ax_w = max(1, int(round(ellipse["axes"][0] / 2)))
    ax_h = max(1, int(round(ellipse["axes"][1] / 2)))
    ang = ellipse["angle_deg"]
    cv2.ellipse(img, (cx, cy), (ax_w, ax_h), ang, 0, 360, (0, 220, 0), 2, cv2.LINE_AA)
    ax_in = (max(1, int(round(ax_w * r_inner))), max(1, int(round(ax_h * r_inner))))
    cv2.ellipse(img, (cx, cy), ax_in, ang, 0, 360, (255, 0, 255), 1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), 4, (255, 255, 0), -1, cv2.LINE_AA)
    return img


def _extract_canvas_points(canvas_data: dict) -> List[Tuple[float, float]]:
    """Extract click positions from Fabric.js circle objects on canvas."""
    out: List[Tuple[float, float]] = []
    objects = canvas_data.get("objects", []) if isinstance(canvas_data, dict) else []
    for o in objects:
        if str(o.get("type")) != "circle":
            continue
        r = float(o.get("radius") or 0.0)
        left = float(o.get("left") or 0.0)
        top = float(o.get("top") or 0.0)
        origin_x = str(o.get("originX") or "").lower()
        origin_y = str(o.get("originY") or "").lower()
        cx = left if origin_x == "center" else (left + r)
        cy = top if origin_y == "center" else (top + r)
        out.append((cx, cy))
    return out


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

# Locked tracking settings (determined from test-cohort QC review)
_LOCKED_POSITION_MODE = "raw"
_LOCKED_BODYPART = "head"
_LOCKED_LH_THRESHOLD = 0.6

_STATUS_OPTIONS = ["(not reviewed)", "keep", "re_mark", "exclude", "needs_re_review"]


def render_ezm_zones_qc(*, workspace_root: Optional[str], project_path: Path) -> None:
    st.header("EZM Zones QC")
    st.caption("Explore settings per experiment, compute metrics, review, and save.")

    if st.button("Refresh (clear cache)", key="ezm_zqc_refresh"):
        st.cache_data.clear()
        st.rerun()

    if not workspace_root:
        st.error("This view requires `--workspace-root`.")
        st.stop()
    project_root = project_path.parent  # WDMOSEQ2 root
    experiment_data_root = project_path / "experiment_data"
    cohorts_dir = project_path / "cohorts"

    # ── Discover experiments ──────────────────────────────────────────
    all_rows = _load_ezm_experiments(str(experiment_data_root))
    n_total = len(all_rows)
    n_with_zones = sum(1 for r in all_rows if r["has_zones"])
    n_with_wedge = sum(1 for r in all_rows if r["has_wedge_points"])

    if n_total == 0:
        st.info(f"No EZM experiment folders found under `{experiment_data_root / 'EZM'}`.")
        st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────
    st.sidebar.header("Fit strategy")
    fit_strategy = st.sidebar.selectbox(
        "Zone source",
        ["Wedge-point circle fit", "Existing zone JSON"],
        key="ezm_zqc_fit_strategy",
    )

    st.sidebar.header("Filters")

    show_trajectory = st.sidebar.checkbox("Show trajectory", value=True, key="ezm_zqc_show_traj")

    _zone_filter_label = "Marking status" if fit_strategy == "Wedge-point circle fit" else "Zone status"
    zone_filter = st.sidebar.selectbox(
        _zone_filter_label, options=["has zones", "needs zones", "all"],
        index=0, key="ezm_zqc_zone_filter",
    )
    qc_filter = st.sidebar.selectbox(
        "QC status", options=["All", "Unreviewed", "Reviewed", "Flagged", "needs_re_review"],
        index=0, key="ezm_zqc_qc_filter",
    )
    genotypes = sorted({r["genotype"] for r in all_rows if r["genotype"]})
    genotype_filter = st.sidebar.selectbox(
        "Genotype", options=["All"] + genotypes, index=0, key="ezm_zqc_genotype",
    )

    # Cohort filter
    cohort_summaries = list_cohorts(cohorts_dir, task_type="EZM")
    cohort_names = ["(none)"] + [c["name"] for c in cohort_summaries]
    cohort_filter = st.sidebar.selectbox(
        "Cohort", options=cohort_names, index=0, key="ezm_zqc_cohort_filter",
    )
    active_cohort = None
    active_cohort_path = None
    active_cohort_ids: set = set()
    if cohort_filter != "(none)":
        match = [c for c in cohort_summaries if c["name"] == cohort_filter]
        if match:
            active_cohort_path = Path(match[0]["path"])
            active_cohort = load_cohort(active_cohort_path)
            active_cohort_ids = cohort_member_ids(active_cohort)

    name_filter = st.sidebar.text_input("Filter (substring)", value="", key="ezm_zqc_name_filter")

    # Strategy-aware summary
    if fit_strategy == "Wedge-point circle fit":
        st.caption(f"{n_with_wedge} of {n_total} EZM experiments have wedge points marked.")
    else:
        st.caption(f"{n_with_zones} of {n_total} EZM experiments have zone annotations.")

    # ── Filter experiments ────────────────────────────────────────────
    filtered = []
    _has_key = "has_wedge_points" if fit_strategy == "Wedge-point circle fit" else "has_zones"
    for r in all_rows:
        if zone_filter == "has zones" and not r[_has_key]:
            continue
        if zone_filter == "needs zones" and r[_has_key]:
            continue
        if qc_filter == "Unreviewed" and r["qc_reviewed_at"]:
            continue
        if qc_filter == "Reviewed" and not r["qc_reviewed_at"]:
            continue
        if qc_filter == "Flagged" and r["qc_status"] not in ("invert", "re_mark", "exclude", "needs_re_review"):
            continue
        if qc_filter == "needs_re_review" and r["qc_status"] != "needs_re_review":
            continue
        if genotype_filter != "All" and r["genotype"] != genotype_filter:
            continue
        if active_cohort_ids and r["experiment_id"] not in active_cohort_ids:
            continue
        if name_filter.strip() and name_filter.strip().lower() not in r["experiment_id"].lower():
            continue
        filtered.append(r)

    if not filtered:
        st.info("No experiments match current filters.")
        st.stop()

    # ── Navigation ────────────────────────────────────────────────────
    n = len(filtered)
    if "ezm_zqc_idx" not in st.session_state:
        st.session_state["ezm_zqc_idx"] = 0
    idx = max(0, min(int(st.session_state["ezm_zqc_idx"]), n - 1))

    col_prev, col_idx, col_next, col_count = st.columns([1, 2, 1, 2])
    with col_prev:
        if st.button("Prev", key="ezm_zqc_prev", disabled=idx <= 0):
            st.session_state["ezm_zqc_idx"] = idx - 1
            st.rerun()
    with col_next:
        if st.button("Next", key="ezm_zqc_next", disabled=idx >= n - 1):
            st.session_state["ezm_zqc_idx"] = idx + 1
            st.rerun()
    with col_idx:
        new_idx = st.number_input(
            "Index", min_value=0, max_value=n - 1, value=idx, step=1,
            key="ezm_zqc_idx_input",
        )
        if int(new_idx) != idx:
            idx = int(new_idx)
            st.session_state["ezm_zqc_idx"] = idx
    with col_count:
        st.markdown(f"**{idx + 1} / {n}** experiments")

    rec = filtered[idx]
    exp_id = rec["experiment_id"]
    exp_json_path = Path(rec["json_path"])
    exp_data = json.loads(exp_json_path.read_text())

    st.subheader(exp_id)

    # ── Per-experiment settings ─────────────────────────────────────────
    # Locked tracking: raw / head / LH≥0.6.  Only invert is per-experiment.
    _cm_all = (exp_data.get("computed_metrics") or {}).get("ezm_open_closed") or {}
    _saved = _cm_all.get("exploration_settings") or {}

    position_mode = _LOCKED_POSITION_MODE
    bodypart = _LOCKED_BODYPART
    lh_threshold = _LOCKED_LH_THRESHOLD

    _k_inv = f"ezm_zqc_exp_inv_{exp_id}"
    if _k_inv not in st.session_state:
        st.session_state[_k_inv] = _saved.get("invert_open_closed", False)

    sc1, sc2 = st.columns([1.5, 4])
    with sc1:
        invert_open_closed = st.checkbox("Invert open/closed", key=_k_inv)
    with sc2:
        st.caption(f"Settings: **{position_mode}** / **{bodypart}** / LH\u2265{lh_threshold}")

    # ── Resolve paths ─────────────────────────────────────────────────
    video_path = _resolve_path(rec.get("video_path", ""))
    zone_json_path = _resolve_zone_json(rec.get("zone_json_path", ""), project_root)
    dlc_csv_path = _resolve_path(rec.get("dlc_csv_path", ""))

    if video_path is None or not video_path.exists():
        st.error(f"Video not found: {rec.get('video_path', '')}")
        st.stop()

    # ── Load frame ────────────────────────────────────────────────────
    mid_frame_idx = 2100  # ~35s at 60fps
    frame_rgb = _load_frame_rgb(str(video_path), mid_frame_idx)
    if frame_rgb is None:
        frame_rgb = _load_frame_rgb(str(video_path), 0)
    if frame_rgb is None:
        st.error("Could not load video frame.")
        st.stop()

    # ── Load zone payload ─────────────────────────────────────────────
    zone_payload = None
    _wedge_fit_warning = ""
    if fit_strategy == "Wedge-point circle fit":
        _am = exp_data.get("arena_markings") or {}
        _wp = (_am.get("ezm_wedge_points") or {}).get("points") or []
        if len(_wp) == 4:
            try:
                _zones_obj, _wedge_fit_warning = zones_from_wedge_points(
                    [(p[0], p[1]) for p in _wp],
                )
                zone_payload = zones_to_json(
                    _zones_obj,
                    image_wh=(frame_rgb.shape[1], frame_rgb.shape[0]),
                    params={"method": "wedge_circle_fit"},
                )
            except Exception as _e:
                st.error(f"Circle fit failed: {_e}")
        else:
            st.info(
                f"No wedge points for this experiment "
                f"({len(_wp)}/4 found). Mark in Annotator → EZM: mark wedge points."
            )
    else:
        if zone_json_path is not None and zone_json_path.exists():
            try:
                zone_payload = json.loads(zone_json_path.read_text())
            except Exception:
                pass

    # ── Load tracks for overlay ──────────────────────────────────────
    tracks = None
    if dlc_csv_path is not None and dlc_csv_path.exists():
        tracks = load_dlc_tracks(dlc_csv_path, likelihood_threshold=lh_threshold)

    # ── Annotation mode (only for "Existing zone JSON" strategy) ────
    _k_annotate = f"ezm_zqc_annotate_{exp_id}"
    annotate_mode = False
    anno_pts: List[Tuple[float, float]] = []
    anno_ellipse_dict: Optional[Dict] = None
    anno_r_inner = 0.75
    anno_scale = 1.0
    anno_init_key = f"ezm_zqc_canvas_init_{exp_id}"
    anno_rev_key = f"ezm_zqc_canvas_rev_{exp_id}"
    vid_h, vid_w = frame_rgb.shape[:2]

    if _CAN_ANNOTATE and fit_strategy != "Wedge-point circle fit":
        if zone_payload is None:
            annotate_mode = True
        elif st.session_state.get(_k_annotate, False):
            annotate_mode = True

    # ── Draw overlay (normal mode) ───────────────────────────────────
    if zone_payload is not None and not annotate_mode:
        overlay = draw_ezm_qc_overlay(
            frame_rgb, zone_payload, tracks or {}, bodypart,
            show_trajectory=bool(show_trajectory and tracks),
            show_legend=True,
            invert_open_closed=bool(invert_open_closed),
        )
    else:
        overlay = frame_rgb

    if _wedge_fit_warning:
        st.warning(_wedge_fit_warning)

    # ── Two-column layout ─────────────────────────────────────────────
    col_img, col_right = st.columns([3, 2])

    with col_img:
        if annotate_mode and _CAN_ANNOTATE:
            # Load template for r_inner
            template = _load_zone_template(workspace_root)
            anno_r_inner = template["template_r_inner"] if template else 0.75

            # Fit ellipse from DLC track
            if dlc_csv_path is not None:
                anno_ellipse_dict = _fit_ellipse_for_annotation(str(dlc_csv_path))
            if anno_ellipse_dict is None and template and "prior_outer_ellipse" in template:
                anno_ellipse_dict = template["prior_outer_ellipse"]

            if anno_ellipse_dict is None:
                st.warning("Cannot fit ellipse — no DLC data or template.")
                st.image(overlay, use_container_width=True)
            else:
                # Scale for canvas display
                anno_scale = min(1.0, _CANVAS_MAX_DIM / max(vid_h, vid_w))
                disp_w = int(round(vid_w * anno_scale))
                disp_h = int(round(vid_h * anno_scale))
                disp_ellipse = {
                    "center": [anno_ellipse_dict["center"][0] * anno_scale,
                               anno_ellipse_dict["center"][1] * anno_scale],
                    "axes": [anno_ellipse_dict["axes"][0] * anno_scale,
                             anno_ellipse_dict["axes"][1] * anno_scale],
                    "angle_deg": anno_ellipse_dict["angle_deg"],
                }

                disp_frame = cv2.resize(frame_rgb, (disp_w, disp_h))
                guided = _draw_annotation_guides(disp_frame, disp_ellipse, anno_r_inner)
                bg_pil = Image.fromarray(guided)

                if anno_rev_key not in st.session_state:
                    st.session_state[anno_rev_key] = 0
                if anno_init_key not in st.session_state:
                    st.session_state[anno_init_key] = {}
                rev = st.session_state[anno_rev_key]

                c = st_canvas(
                    fill_color="rgba(255, 80, 80, 0.3)",
                    stroke_width=2,
                    stroke_color="rgba(255, 80, 80, 0.9)",
                    background_image=bg_pil,
                    update_streamlit=True,
                    height=disp_h,
                    width=disp_w,
                    drawing_mode="circle",
                    initial_drawing=st.session_state[anno_init_key] or None,
                    display_toolbar=True,
                    key=f"ezm_zqc_canvas_{exp_id}_{rev}",
                )

                if c and c.json_data:
                    cdata = c.json_data if isinstance(c.json_data, dict) else {}
                    anno_pts = _extract_canvas_points(cdata)
                    st.session_state[anno_init_key] = cdata

                uc1, uc2, uc3 = st.columns(3)
                with uc1:
                    if st.button("Undo", key=f"ezm_zqc_anno_undo_{exp_id}"):
                        cur = st.session_state.get(anno_init_key, {})
                        objs = cur.get("objects", []) if isinstance(cur, dict) else []
                        if objs:
                            st.session_state[anno_init_key] = {**cur, "objects": objs[:-1]}
                        st.session_state[anno_rev_key] = rev + 1
                        st.rerun()
                with uc2:
                    if st.button("Clear", key=f"ezm_zqc_anno_clear_{exp_id}"):
                        st.session_state[anno_init_key] = {}
                        st.session_state[anno_rev_key] = rev + 1
                        st.rerun()
                with uc3:
                    if zone_payload is not None:
                        if st.button("Cancel", key=f"ezm_zqc_anno_cancel_{exp_id}"):
                            st.session_state[_k_annotate] = False
                            st.session_state.pop(anno_init_key, None)
                            st.session_state.pop(anno_rev_key, None)
                            st.rerun()

                st.caption(f"{len(anno_pts)} / 4 boundary points")
        else:
            st.image(overlay, use_container_width=True)
            if _CAN_ANNOTATE:
                label = "Re-annotate zones" if zone_payload else "Annotate zones"
                if st.button(label, key=f"ezm_zqc_enter_annotate_{exp_id}"):
                    st.session_state[_k_annotate] = True
                    st.rerun()

    with col_right:
        # Session info
        st.markdown("**Session info**")
        info = {
            "Subject": rec["subject_id"],
            "Date": rec["date_recorded"],
            "Genotype": rec["genotype"],
            "Sex": rec.get("sex", ""),
            "Zone method": rec.get("zone_method", ""),
        }
        st.dataframe(
            pd.DataFrame(list(info.items()), columns=["Field", "Value"]),
            hide_index=True, use_container_width=True,
        )

        # ── Annotation preview + save ────────────────────────────────
        if annotate_mode and _CAN_ANNOTATE and anno_ellipse_dict is not None:
            st.markdown("---")
            if len(anno_pts) >= 4:
                img_pts = [(x / anno_scale, y / anno_scale) for x, y in anno_pts[:4]]
                _outer = EllipseParams(
                    center_xy=tuple(anno_ellipse_dict["center"]),
                    axes_xy=tuple(anno_ellipse_dict["axes"]),
                    angle_deg=anno_ellipse_dict["angle_deg"],
                )
                _w1 = [img_pts[0], img_pts[1]]
                _w2 = [img_pts[2], img_pts[3]]
                _boundary_angles, _open_sectors, _geom_warn = boundary_angles_from_wedge_points(
                    _w1, _w2, _outer.center_xy, _outer,
                )
                if _geom_warn:
                    st.warning(_geom_warn)
                _open_ranges = open_ranges_from_boundary_angles(
                    _boundary_angles, _open_sectors,
                )
                _preview_zone = {
                    "outer_ellipse": {
                        "center": list(_outer.center_xy),
                        "axes": list(_outer.axes_xy),
                        "angle_deg": _outer.angle_deg,
                    },
                    "r_inner": anno_r_inner,
                    "boundary_angles": _boundary_angles,
                    "open_angle_ranges": [list(r) for r in _open_ranges],
                }
                _preview = draw_ezm_qc_overlay(
                    frame_rgb, _preview_zone, tracks or {}, bodypart,
                    show_trajectory=bool(show_trajectory and tracks),
                    show_legend=True,
                )
                st.markdown("**Zone preview**")
                st.image(_preview, use_container_width=True)
                st.caption(
                    f"Boundaries: {[f'{a:.3f}' for a in _boundary_angles]}"
                    f" | Open: {_open_sectors}"
                )

                if st.button(
                    "Save zone annotation",
                    key=f"ezm_zqc_save_zone_{exp_id}",
                    type="primary",
                ):
                    _zone_dir = Path(workspace_root) / "arena_annotation" / "arena_zones"
                    _zone_dir.mkdir(parents=True, exist_ok=True)
                    _zone_path = _zone_dir / f"{exp_id}.json"

                    _zones = EZMZones(
                        outer_ellipse=_outer,
                        r_inner=anno_r_inner,
                        open_angle_ranges=tuple(_open_ranges),
                        boundary_angles=tuple(_boundary_angles),
                    )
                    _payload = zones_to_json(
                        _zones,
                        image_wh=(vid_w, vid_h),
                        params={"fit_method": "4click_boundary"},
                        notes="4-click boundary from MUS1 browser QC view",
                    )
                    _payload["annotations"] = {
                        "method": "4click_boundary",
                        "calibration": {
                            "source": "mus1_browser_qc_view",
                            "fitted_at": datetime.now(timezone.utc).isoformat(),
                        },
                        "wedge1_border_pts_img": _w1,
                        "wedge2_border_pts_img": _w2,
                    }
                    save_zones_json(_zone_path, _payload)

                    # Link to experiment JSON
                    try:
                        _rel = str(_zone_path.resolve().relative_to(project_root.resolve()))
                    except ValueError:
                        _rel = str(_zone_path)
                    _fresh = json.loads(exp_json_path.read_text())
                    _fresh.setdefault("derived_data", {})
                    _fresh["derived_data"]["arena_zones"] = {
                        "version": "ezm_open_closed_v2",
                        "method": "4click_boundary",
                        "zone_json_path": _rel,
                        "saved_at": datetime.now(timezone.utc).isoformat(),
                        "status": "confirmed",
                    }
                    exp_json_path.write_text(
                        json.dumps(_fresh, indent=2) + "\n", encoding="utf-8",
                    )

                    st.session_state[_k_annotate] = False
                    st.session_state.pop(anno_init_key, None)
                    st.session_state.pop(anno_rev_key, None)
                    st.cache_data.clear()
                    st.toast(f"Saved: {_zone_path.name}")
                    st.rerun()
            else:
                st.markdown(
                    "**4-click boundary annotation**\n\n"
                    "Click 4 points on outer track edge:\n"
                    "- Clicks 1+2: borders of **open arm 1**\n"
                    "- Clicks 3+4: borders of **open arm 2**\n\n"
                    "Green = fitted outer track"
                )

        # ── Compute button ────────────────────────────────────────────
        _metrics_key = f"ezm_zqc_exp_metrics_{exp_id}"
        can_compute = zone_payload is not None and dlc_csv_path is not None

        if st.button(
            "Compute metrics", key=f"ezm_zqc_compute_{exp_id}",
            type="primary", disabled=not can_compute,
            help="Compute metrics with current settings. Not saved until you press Save.",
        ):
            with st.spinner("Computing..."):
                from ..ezm_compute_bridge import (
                    compute_open_closed_metrics,
                    load_zone_definition,
                    try_read_dlc_csv,
                )
                df = try_read_dlc_csv(dlc_csv_path)
                if df is None:
                    st.error("Failed to read DLC CSV.")
                else:
                    if fit_strategy == "Wedge-point circle fit":
                        # Build ZoneDefinition from zone_payload dict
                        # (same parsing as load_zone_definition but from dict, not file)
                        _oe = zone_payload["outer_ellipse"]
                        from ezm_open_closed_zones import ZoneDefinition as _ZD, EllipseParams as _EP
                        zones = _ZD(
                            outer_ellipse=_EP(
                                center_xy=(float(_oe["center"][0]), float(_oe["center"][1])),
                                axes_xy=(float(_oe["axes"][0]), float(_oe["axes"][1])),
                                angle_deg=float(_oe["angle_deg"]),
                            ),
                            r_inner=float(zone_payload["r_inner"]),
                            open_angle_ranges=(
                                (float(zone_payload["open_angle_ranges"][0][0]), float(zone_payload["open_angle_ranges"][0][1])),
                                (float(zone_payload["open_angle_ranges"][1][0]), float(zone_payload["open_angle_ranges"][1][1])),
                            ),
                        )
                    else:
                        zones = load_zone_definition(zone_json_path)
                    fps = _video_fps(str(video_path))
                    m = compute_open_closed_metrics(
                        df, zones, fps=fps,
                        likelihood_threshold=lh_threshold,
                        max_interp_gap_frames=10,
                        open_count_mode="sector",
                        bodypart_preferred=bodypart,
                        invert_open_closed=bool(invert_open_closed),
                        position_mode=position_mode,
                        nose_mode="blend",
                    )
                    st.session_state[_metrics_key] = {
                        "raw": m,
                        "settings": {
                            "position_mode": position_mode,
                            "bodypart": bodypart,
                            "likelihood_threshold": lh_threshold,
                            "invert_open_closed": bool(invert_open_closed),
                        },
                    }
                    st.rerun()

        if not can_compute:
            missing = []
            if zone_payload is None:
                missing.append("zone data (mark wedge points or create zone annotation)")
            if dlc_csv_path is None:
                missing.append("DLC CSV")
            st.caption(f"Cannot compute: missing {', '.join(missing)}")

        # ── Display metrics ───────────────────────────────────────────
        session_metrics = st.session_state.get(_metrics_key)

        # Existing variants from JSON (for fallback display)
        variants_json = {
            k: v for k, v in _cm_all.items()
            if k not in ("qc_review", "exploration_settings")
            and isinstance(v, dict) and "occupancy" in v
        }

        if session_metrics:
            # Show fresh compute results (unsaved)
            m = session_metrics["raw"]
            s = session_metrics["settings"]
            st.markdown("**Computed metrics** *(unsaved)*")
            desc_parts = [f"pos={s['position_mode']}", f"bp={s['bodypart']}", f"lh\u2265{s['likelihood_threshold']}"]
            if s["invert_open_closed"]:
                desc_parts.append("inverted")
            st.caption(" | ".join(desc_parts))
            metrics_display = {
                "Open fraction": f"{m.get('open_fraction', 0):.3f}",
                "Closed fraction": f"{m.get('closed_fraction', 0):.3f}",
                "Open time (s)": f"{m.get('open_time_s', 0):.1f}",
                "Closed time (s)": f"{m.get('closed_time_s', 0):.1f}",
                "Entries (C\u2192O)": f"{m.get('closed_to_open_entries', 0):.0f}",
                "Nose open frac": f"{m.get('nose_open_fraction_sector', 0):.3f}",
                "Track quality": f"{m.get('pct_frames_above_thr', 0):.1%}",
                "Off-track frac": f"{m.get('off_track_fraction_all_frames', 0):.3f}",
            }
            st.dataframe(
                pd.DataFrame(list(metrics_display.items()), columns=["Metric", "Value"]),
                hide_index=True, use_container_width=True,
            )
            flags = _auto_flags_from_raw_metrics(m)
            if flags:
                for fl in flags:
                    st.warning(fl)
            else:
                st.success("No auto-flags.")

        elif variants_json:
            # Show previously saved variants from JSON
            st.markdown("**Saved metrics**")
            vnames = list(variants_json.keys())
            selected = st.selectbox(
                "Variant", options=vnames, index=0,
                key=f"ezm_zqc_vsel_{exp_id}",
            )
            v = variants_json[selected]
            v_params = v.get("parameters", {})
            if v_params.get("invert_open_closed"):
                st.caption("Computed with **inverted** open/closed.")
            occ = v.get("occupancy", {})
            tqc = v.get("tracking_qc", {})
            expl = v.get("exploration", {})
            metrics_display = {
                "Open fraction": f"{occ.get('open_fraction', 0):.3f}",
                "Closed fraction": f"{occ.get('closed_fraction', 0):.3f}",
                "Open time (s)": f"{occ.get('open_time_s', 0):.1f}",
                "Closed time (s)": f"{occ.get('closed_time_s', 0):.1f}",
                "Entries (C\u2192O)": f"{expl.get('closed_to_open_entries', 0):.0f}",
                "Nose open frac": f"{expl.get('nose_open_fraction_sector', 0):.3f}",
                "Track quality": f"{tqc.get('pct_frames_above_thr', 0):.1%}",
                "Off-track frac": f"{occ.get('off_track_fraction', 0):.3f}",
            }
            st.dataframe(
                pd.DataFrame(list(metrics_display.items()), columns=["Metric", "Value"]),
                hide_index=True, use_container_width=True,
            )
            flags = _compute_auto_flags(variants_json)
            if flags:
                for fl in flags:
                    st.warning(fl)
            else:
                st.success("No auto-flags.")
        else:
            st.info("No metrics yet. Press **Compute metrics** above.")

    # ── QC Review ─────────────────────────────────────────────────────
    st.markdown("---")
    qc_review = _cm_all.get("qc_review", {})
    existing_status = qc_review.get("status", "")
    existing_notes = qc_review.get("notes", "")
    reviewed_at = qc_review.get("reviewed_at", "")

    st.markdown("**QC Review**")
    if reviewed_at:
        st.caption(f"Last reviewed: {reviewed_at[:19]}")

    _k_status = f"ezm_zqc_status_{exp_id}"
    if _k_status not in st.session_state:
        if existing_status in _STATUS_OPTIONS:
            st.session_state[_k_status] = existing_status
        else:
            st.session_state[_k_status] = "(not reviewed)"

    qc_status = st.radio(
        "Status", options=_STATUS_OPTIONS, horizontal=True,
        key=_k_status,
    )

    _k_notes = f"ezm_zqc_notes_{exp_id}"
    if _k_notes not in st.session_state:
        st.session_state[_k_notes] = existing_notes

    qc_notes = st.text_area(
        "Notes",
        placeholder="e.g., zones look correct, tracking drift in late frames...",
        key=_k_notes,
        height=80, label_visibility="collapsed",
    )

    # ── SAVE ALL ──────────────────────────────────────────────────────
    if st.button(
        "Save all (settings + metrics + QC)",
        key=f"ezm_zqc_save_all_{exp_id}", type="primary",
    ):
        fresh = json.loads(exp_json_path.read_text())
        cm_f = fresh.setdefault("computed_metrics", {})
        oc_f = cm_f.setdefault("ezm_open_closed", {})

        # 1) Save exploration settings (locked + per-experiment invert)
        oc_f["exploration_settings"] = {
            "invert_open_closed": bool(invert_open_closed),
            "position_mode": position_mode,
            "bodypart": bodypart,
            "likelihood_threshold": lh_threshold,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        # 2) Save computed metrics if we have session results from Compute
        session_metrics = st.session_state.get(_metrics_key)
        if session_metrics:
            m = session_metrics["raw"]
            s = session_metrics["settings"]
            lh_str = str(s["likelihood_threshold"]).replace(".", "p")
            inv_suffix = "_inv" if s["invert_open_closed"] else ""
            variant_name = f"{s['position_mode']}_lh{lh_str}{inv_suffix}"
            fps = _video_fps(str(video_path))
            variant_block = {
                "variant": variant_name,
                "description": (
                    f"Computed in MUS1 browser ({s['position_mode']}, "
                    f"lh>={s['likelihood_threshold']}"
                    f"{', inverted' if s['invert_open_closed'] else ''})"
                ),
                "is_primary": False,
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "computed_by": "mus1_browser",
                "parameters": {
                    "position_mode": s["position_mode"],
                    "likelihood_threshold": s["likelihood_threshold"],
                    "max_interp_gap_frames": 10,
                    "fps": fps,
                    "open_count_mode": "sector",
                    "bodypart_used": m.get("bodypart_used", s["bodypart"]),
                    "nose_mode": "blend",
                    "invert_open_closed": s["invert_open_closed"],
                },
                "tracking_qc": {
                    "pct_frames_above_thr": m.get("pct_frames_above_thr"),
                    "pct_frames_xy_filled": m.get("pct_frames_xy_filled"),
                    "body_ok_fraction": m.get("body_ok_fraction"),
                    "head_ok_fraction": m.get("head_ok_fraction"),
                    "nose_ok_fraction": m.get("nose_ok_fraction"),
                    "n_frames": m.get("n_frames"),
                },
                "occupancy": {
                    "open_time_s": m.get("open_time_s"),
                    "closed_time_s": m.get("closed_time_s"),
                    "valid_time_s": m.get("valid_time_s"),
                    "open_fraction": m.get("open_fraction"),
                    "closed_fraction": m.get("closed_fraction"),
                    "off_track_time_s": m.get("off_track_time_s"),
                    "off_track_fraction": m.get("off_track_fraction_all_frames"),
                },
                "exploration": {
                    "closed_to_open_entries": m.get("closed_to_open_entries"),
                    "nose_open_fraction_sector": m.get("nose_open_fraction_sector"),
                    "outside_outer_time_s": m.get("outside_outer_time_s"),
                    "outside_outer_open_time_s": m.get("outside_outer_open_time_s"),
                },
            }
            oc_f[variant_name] = variant_block
            # Clear session metrics — now persisted
            st.session_state.pop(_metrics_key, None)

        # 3) Save QC review
        status_val = qc_status if qc_status != "(not reviewed)" else ""
        all_variants = {
            k: v for k, v in oc_f.items()
            if k not in ("qc_review", "exploration_settings")
            and isinstance(v, dict) and "occupancy" in v
        }
        flags = _compute_auto_flags(all_variants) if all_variants else []
        oc_f["qc_review"] = {
            "status": status_val,
            "notes": qc_notes.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "auto_flags": flags,
        }

        exp_json_path.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
        st.cache_data.clear()
        st.toast("Saved: settings + metrics + QC.")
        st.rerun()

    # ── Cohort management ─────────────────────────────────────────────
    with st.expander("Cohort Management", expanded=False):
        if active_cohort is not None and active_cohort_path is not None:
            in_cohort = exp_id in active_cohort_ids
            cola, colb = st.columns(2)
            with cola:
                if st.button(
                    f"Remove from '{active_cohort['name']}'",
                    disabled=not in_cohort, key="ezm_zqc_cohort_remove",
                ):
                    active_cohort = remove_member(active_cohort, exp_id)
                    save_cohort(active_cohort_path, active_cohort)
                    st.success(f"Removed {exp_id}.")
                    st.cache_data.clear()
                    st.rerun()
            with colb:
                if st.button(
                    f"Add to '{active_cohort['name']}'",
                    disabled=in_cohort, key="ezm_zqc_cohort_add",
                ):
                    active_cohort = add_member(active_cohort, exp_id)
                    save_cohort(active_cohort_path, active_cohort)
                    st.success(f"Added {exp_id}.")
                    st.cache_data.clear()
                    st.rerun()

            st.caption(
                f"Cohort '{active_cohort['name']}': "
                f"{len(active_cohort.get('members', []))} members"
            )

            # Bulk add all currently filtered experiments
            n_not_in = sum(
                1 for r in filtered if r["experiment_id"] not in active_cohort_ids
            )
            if st.button(
                f"Add all {n_not_in} filtered to cohort",
                disabled=n_not_in == 0,
                key="ezm_zqc_cohort_bulk_add",
                help="Add every experiment in the current filtered list to this cohort.",
            ):
                for r in filtered:
                    if r["experiment_id"] not in active_cohort_ids:
                        active_cohort = add_member(active_cohort, r["experiment_id"])
                save_cohort(active_cohort_path, active_cohort)
                st.success(f"Added {n_not_in} experiments to cohort.")
                st.cache_data.clear()
                st.rerun()
        else:
            st.caption("Select a cohort in the sidebar to manage membership.")

        # Create new cohort
        st.markdown("**Create new cohort**")
        new_name = st.text_input("Name", key="ezm_zqc_new_cohort_name")
        new_desc = st.text_input("Description", key="ezm_zqc_new_cohort_desc")
        if st.button("Create", key="ezm_zqc_create_cohort", disabled=not new_name.strip()):
            cohort = create_cohort(
                new_name.strip(), task_types=["EZM"], description=new_desc.strip(),
            )
            cpath = cohorts_dir / f"{new_name.strip().replace(' ', '_').lower()}.json"
            save_cohort(cpath, cohort)
            st.success(f"Created cohort: {cpath.name}")
            st.cache_data.clear()
            st.rerun()

        # Export
        if active_cohort is not None:
            st.markdown("**Export**")
            default_csv = (
                project_path / "ml_review" / "ezm_unet"
                / f"{active_cohort['name']}_training.csv"
            )
            export_path = Path(
                st.text_input("Export CSV path", value=str(default_csv), key="ezm_zqc_export_path")
            )
            if st.button("Export training CSV", key="ezm_zqc_export"):
                n_written = export_training_csv(
                    active_cohort, experiment_data_root, export_path,
                )
                st.success(f"Wrote {n_written} rows to {export_path}")
