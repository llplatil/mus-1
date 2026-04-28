"""EZM Wedge Marking -- click 4 boundary points on the outer rim.

Workflow: click 4 points where open/closed borders meet the outer edge
of the EZM track. Order does not matter. Accept saves to experiment JSON
and advances. Use the canvas trash icon to clear and re-mark.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import streamlit as st
from streamlit_drawable_canvas import st_canvas

from ..cohorts import cohort_member_ids, list_cohorts, load_cohort
from ..filters import SCOPE_KEY, _cohort_member_ids, invalidate_after_write, pkey

PANE = "ezm_wedge"

# ---------------------------------------------------------------------------
# Experiment row
# ---------------------------------------------------------------------------

@dataclass
class _EZMRow:
    experiment_id: str
    subject_id: str
    date_recorded: str
    sex: str
    genotype: str
    video_path: str
    json_path: Path
    frame_count: Optional[int]


# ---------------------------------------------------------------------------
# Frame extraction (same pattern as NOR/NOF object marking)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _read_mid_frame(video_path: str, frame_count: Optional[int]) -> Optional[np.ndarray]:
    vp = Path(video_path)
    if not vp.exists():
        return None
    cap = cv2.VideoCapture(str(vp))
    if not cap.isOpened():
        return None
    total = frame_count or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    mid = max(0, total // 2)
    cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
    ret, bgr = cap.read()
    cap.release()
    if not ret:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


@st.cache_resource(show_spinner=False)
def _get_pil_image(video_path: str, frame_count: Optional[int]):
    frame = _read_mid_frame(video_path, frame_count)
    if frame is None:
        return None
    from PIL import Image
    return Image.fromarray(frame)


# ---------------------------------------------------------------------------
# Experiment discovery
# ---------------------------------------------------------------------------

from mus1.web.discovery import CACHE_TTL_SECONDS  # noqa: E402


@st.cache_data(show_spinner="Loading EZM experiments...", ttl=CACHE_TTL_SECONDS)
def _load_ezm_experiments(experiment_data_root: str) -> List[Dict[str, Any]]:
    """Scan EZM experiment folders across all configured data roots."""
    from mus1.web.discovery import task_dirs_across_roots

    rows: List[Dict[str, Any]] = []
    project_path = Path(experiment_data_root).parent
    exp_dirs = task_dirs_across_roots(project_path, "EZM")
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
        meta = data.get("metadata") or {}
        video = data.get("video") or {}
        video_path = video.get("path", "")
        if not video_path:
            continue
        rows.append({
            "experiment_id": data.get("experiment_id", exp_dir.name),
            "subject_id": meta.get("subject_id", ""),
            "date_recorded": meta.get("date_recorded", ""),
            "sex": meta.get("sex", ""),
            "genotype": meta.get("genotype", ""),
            "video_path": video_path,
            "json_path": str(jf),
            "frame_count": video.get("frame_count"),
        })
    return rows


def _rows_from_dicts(dicts: List[Dict[str, Any]]) -> List[_EZMRow]:
    return [
        _EZMRow(
            experiment_id=d["experiment_id"],
            subject_id=d["subject_id"],
            date_recorded=d["date_recorded"],
            sex=d["sex"],
            genotype=d["genotype"],
            video_path=d["video_path"],
            json_path=Path(d["json_path"]),
            frame_count=d.get("frame_count"),
        )
        for d in dicts
    ]


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _read_json(json_path: Path) -> dict:
    return json.loads(json_path.read_text())


def _has_wedge_marking(row: _EZMRow) -> bool:
    try:
        am = _read_json(row.json_path).get("arena_markings") or {}
    except Exception:
        return False
    wp = am.get("ezm_wedge_points") or {}
    pts = wp.get("points") or []
    return len(pts) == 4


def _save_wedge_marking(
    json_path: Path,
    *,
    points: List[List[float]],
    frame_shape: List[int],
    flag_review: bool,
    note: str,
) -> bool:
    """Save wedge points into arena_markings.ezm_wedge_points.

    Preserves other arena_markings subsections (e.g. ezm_boundary_points).
    Returns True if this was an overwrite of existing wedge points.
    """
    data = _read_json(json_path)
    am = data.get("arena_markings") or {}
    was_overwrite = bool((am.get("ezm_wedge_points") or {}).get("points"))
    am["ezm_wedge_points"] = {
        "points": points,
        "frame_shape": frame_shape,
        "flag_review": flag_review,
        "note": note,
        "marked_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    data["arena_markings"] = am
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    return was_overwrite


# ---------------------------------------------------------------------------
# Resolve experiment JSON from experiment_id
# ---------------------------------------------------------------------------

def _resolve_experiment_json(experiment_id: str) -> Optional[Path]:
    """Find experiment JSON path from experiment_id (e.g. EZM_868_2023-07-07)."""
    parts = experiment_id.split("_", 1)
    task = parts[0] if parts else "EZM"
    # Walk up from this module to find the data root
    # Module is at: apps/mus1/src/mus1/web/views/ezm_wedge_marking.py
    # Project data is at: data/experiment_data/
    import os
    project_path = Path(os.environ.get("MOSEQ2_PROJECT_PATH", ""))
    exp_dir = project_path / "experiment_data" / task / experiment_id
    if not exp_dir.is_dir():
        return None
    jsons = [f for f in exp_dir.iterdir() if f.suffix == ".json"]
    return jsons[0] if jsons else None


# ---------------------------------------------------------------------------
# Annotator-integrated renderer (single experiment, shared navigation)
# ---------------------------------------------------------------------------

def render_ezm_wedge_for_annotator(
    *,
    video_path: Path,
    frame_idx: int,
    experiment_id: str,
    meta: dict,
    advance_callback: Any,
) -> None:
    """Render wedge marking UI for one experiment within the annotator flow.

    Called by the annotator's shared dispatch. Navigation (prev/next) is
    handled by the annotator sidebar; this function only handles the canvas,
    click extraction, and save.
    """
    from typing import Callable
    st.header("EZM Wedge Marking")
    st.caption(
        "Click **4 points** on the outer rim where open/closed borders meet. "
        "Order does not matter. Accept saves and advances. "
        "Trash icon on canvas clears clicks."
    )

    if not experiment_id:
        st.warning("No experiment_id in metadata for this video.")
        st.stop()

    json_path = _resolve_experiment_json(experiment_id)
    if json_path is None:
        st.warning(f"Could not find experiment JSON for: {experiment_id}")
        st.stop()

    exp_data = _read_json(json_path)
    existing_am = exp_data.get("arena_markings") or {}
    existing_wp = existing_am.get("ezm_wedge_points") or {}
    exp_meta = exp_data.get("metadata") or {}

    # Header
    st.subheader(experiment_id)
    hdr = st.columns(4)
    with hdr[0]:
        st.markdown(f"**Subject:** {exp_meta.get('subject_id', meta.get('subject_id', '?'))}")
    with hdr[1]:
        st.markdown(f"**Date:** {exp_meta.get('date_recorded', meta.get('recording_date', '?'))}")
    with hdr[2]:
        st.markdown(f"**Sex:** {exp_meta.get('sex', '?')}")
    with hdr[3]:
        st.markdown(f"**Genotype:** {exp_meta.get('genotype', '?')}")

    # Load mid-frame (ignore frame_idx from sidebar, always use mid-frame)
    frame_count = (exp_data.get("video") or {}).get("frame_count")
    pil_img = _get_pil_image(str(video_path), frame_count)
    if pil_img is None:
        st.warning(f"Could not read frame from: {video_path}")
        st.stop()

    img_w, img_h = pil_img.size
    canvas_w = min(img_w, 800)
    scale = canvas_w / img_w
    canvas_h = int(img_h * scale)

    # Canvas
    canvas_result = st_canvas(
        fill_color="rgba(0, 255, 0, 0.3)",
        stroke_width=0,
        stroke_color="#00ff00",
        background_image=pil_img,
        drawing_mode="point",
        point_display_radius=8,
        height=canvas_h,
        width=canvas_w,
        key=f"ewm_canvas__{experiment_id}",
    )

    # Extract clicks
    _pt_r = 8
    points: List[List[float]] = []
    if canvas_result.json_data is not None:
        for obj in canvas_result.json_data.get("objects", []):
            if obj.get("type") == "circle":
                cx = obj.get("left", 0) + _pt_r
                cy = obj.get("top", 0)
                points.append([round(cx / scale, 1), round(cy / scale, 1)])

    # Click status
    n_points = len(points)
    if n_points == 0:
        st.info("Click 4 points on the outer rim at open/closed borders.")
    elif n_points < 4:
        st.info(f"{n_points}/4 points placed. Click {4 - n_points} more.")
    elif n_points == 4:
        st.success("4 points placed. Ready to save.")
    else:
        st.warning(f"{n_points} clicks -- only first 4 used. Clear to redo.")

    # Flag for review + note
    ready = n_points >= 4

    fc_flag, fc_note = st.columns([1, 3])
    with fc_flag:
        flag_review = st.checkbox(
            "Flag for review",
            value=existing_wp.get("flag_review", False),
            key=f"ewm_flag__{experiment_id}",
        )
    with fc_note:
        note = st.text_input(
            "Note",
            value=existing_wp.get("note", ""),
            key=f"ewm_note__{experiment_id}",
            placeholder="Optional note for this marking",
        )

    # Accept + Save
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button(
            "Accept + Save + Next",
            key=f"ewm_accept__{experiment_id}",
            type="primary",
            disabled=not ready,
        ):
            was_overwrite = _save_wedge_marking(
                json_path,
                points=points[:4],
                frame_shape=[img_h, img_w],
                flag_review=flag_review,
                note=note,
            )
            if was_overwrite:
                st.toast(f"Overwrote existing wedge markings for {experiment_id}")
            else:
                st.toast(f"Saved wedge markings for {experiment_id}")
            advance_callback()
    with ac2:
        st.caption("Use the trash icon on the canvas toolbar to clear and re-mark.")

    # Show existing marking
    if existing_wp.get("points"):
        st.markdown("---")
        flag_tag = " **[FLAGGED]**" if existing_wp.get("flag_review") else ""
        note_tag = f" -- {existing_wp['note']}" if existing_wp.get("note") else ""
        pts_str = ", ".join(f"({p[0]}, {p[1]})" for p in existing_wp["points"])
        st.caption(
            f"Existing: {pts_str} "
            f"({existing_wp.get('marked_at', '?')}){flag_tag}{note_tag}"
        )


# ---------------------------------------------------------------------------
# Standalone render (kept for backwards compat, no longer primary entry point)
# ---------------------------------------------------------------------------

def render_ezm_wedge_marking(
    *,
    project_path: Path,
    workspace_root: Optional[str],
    db_path: Path,
) -> None:
    st.header("EZM Wedge Marking")
    st.caption(
        "Click **4 points** on the outer rim where open/closed borders meet. "
        "Order does not matter. Accept saves and advances. "
        "Trash icon on canvas clears clicks."
    )

    experiment_data_root = project_path / "experiment_data"
    if not experiment_data_root.is_dir():
        st.error(f"experiment_data not found at: {experiment_data_root}")
        st.stop()

    all_dicts = _load_ezm_experiments(str(experiment_data_root))
    all_rows = _rows_from_dicts(all_dicts)
    if not all_rows:
        st.warning("No EZM experiments found.")
        st.stop()

    # --- Filters ---
    # Cohort scope is read from the universal scope picker in the sidebar
    # (see web/filters.py:render_scope_picker, wired in web/app.py).
    # Marking-status and sort are pane-specific primary controls and live
    # in the main area for ergonomics during the marking workflow.
    fc1, fc2 = st.columns([1, 2])
    with fc1:
        marking_filter = st.radio(
            "Status", ["Unmarked", "Marked", "All"],
            horizontal=True, key=pkey(PANE, "status"),
        )
    with fc2:
        sort_by = st.selectbox(
            "Sort by",
            ["subject_id", "date_recorded", "experiment_id"],
            key=pkey(PANE, "sort"),
        )

    # Apply cohort scope (universal)
    filtered: List[_EZMRow] = list(all_rows)
    scope_cohort = st.session_state.get(SCOPE_KEY)
    if scope_cohort:
        member_ids = _cohort_member_ids(project_path, scope_cohort)
        filtered = [r for r in filtered if r.experiment_id in member_ids]

    # Apply marking status filter
    if marking_filter == "Unmarked":
        filtered = [r for r in filtered if not _has_wedge_marking(r)]
    elif marking_filter == "Marked":
        filtered = [r for r in filtered if _has_wedge_marking(r)]

    filtered.sort(key=lambda r: getattr(r, sort_by))

    total_marked = sum(1 for r in all_rows if _has_wedge_marking(r))
    st.caption(
        f"Total: {len(all_rows)} | Marked: {total_marked} | "
        f"Remaining: {len(all_rows) - total_marked} | Showing: {len(filtered)}"
    )

    if not filtered:
        st.success("All experiments in this filter have been marked.")
        st.stop()

    # --- Navigation ---
    if "ewm_nav_idx" not in st.session_state:
        st.session_state["ewm_nav_idx"] = 0

    n1, n2, n3 = st.columns([1, 1, 4])
    with n1:
        if st.button("Prev", key="ewm_prev"):
            st.session_state["ewm_nav_idx"] = max(
                0, st.session_state.get("ewm_nav_idx", 0) - 1
            )
            st.rerun()
    with n2:
        if st.button("Next", key="ewm_next"):
            st.session_state["ewm_nav_idx"] = min(
                len(filtered) - 1, st.session_state.get("ewm_nav_idx", 0) + 1
            )
            st.rerun()

    cur = st.session_state.get("ewm_nav_idx", 0)
    cur = max(0, min(len(filtered) - 1, cur))

    with n3:
        idx = st.number_input(
            f"Index (0-{len(filtered)-1})",
            min_value=0, max_value=len(filtered) - 1,
            value=cur, step=1, key="ewm_idx_input",
        )
    st.session_state["ewm_nav_idx"] = idx
    row = filtered[idx]

    # --- Header ---
    exp_data = _read_json(row.json_path)
    existing_am = exp_data.get("arena_markings") or {}
    existing_wp = existing_am.get("ezm_wedge_points") or {}

    st.subheader(row.experiment_id)
    hdr = st.columns(4)
    with hdr[0]:
        st.markdown(f"**Subject:** {row.subject_id}")
    with hdr[1]:
        st.markdown(f"**Date:** {row.date_recorded}")
    with hdr[2]:
        st.markdown(f"**Sex:** {row.sex}")
    with hdr[3]:
        st.markdown(f"**Genotype:** {row.genotype}")

    # --- Load frame ---
    pil_img = _get_pil_image(row.video_path, row.frame_count)
    if pil_img is None:
        st.warning(f"Could not read frame from: {row.video_path}")
        st.stop()

    img_w, img_h = pil_img.size
    canvas_w = min(img_w, 800)
    scale = canvas_w / img_w
    canvas_h = int(img_h * scale)

    # --- Canvas ---
    canvas_result = st_canvas(
        fill_color="rgba(0, 255, 0, 0.3)",
        stroke_width=0,
        stroke_color="#00ff00",
        background_image=pil_img,
        drawing_mode="point",
        point_display_radius=8,
        height=canvas_h,
        width=canvas_w,
        key=f"ewm_canvas__{row.experiment_id}",
    )

    # --- Extract clicks ---
    _pt_r = 8  # must match point_display_radius
    points: List[List[float]] = []
    if canvas_result.json_data is not None:
        for obj in canvas_result.json_data.get("objects", []):
            if obj.get("type") == "circle":
                cx = obj.get("left", 0) + _pt_r
                cy = obj.get("top", 0)
                points.append([round(cx / scale, 1), round(cy / scale, 1)])

    # --- Click status ---
    n_points = len(points)
    if n_points == 0:
        st.info("Click 4 points on the outer rim at open/closed borders.")
    elif n_points < 4:
        st.info(f"{n_points}/4 points placed. Click {4 - n_points} more.")
    elif n_points == 4:
        st.success("4 points placed. Ready to save.")
    else:
        st.warning(f"{n_points} clicks -- only first 4 used. Clear to redo.")

    # --- Flag for review + note ---
    ready = n_points >= 4

    fc_flag, fc_note = st.columns([1, 3])
    with fc_flag:
        flag_review = st.checkbox(
            "Flag for review",
            value=existing_wp.get("flag_review", False),
            key=f"ewm_flag__{row.experiment_id}",
        )
    with fc_note:
        note = st.text_input(
            "Note",
            value=existing_wp.get("note", ""),
            key=f"ewm_note__{row.experiment_id}",
            placeholder="Optional note for this marking",
        )

    # --- Accept ---
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button(
            "Accept",
            key=f"ewm_accept__{row.experiment_id}",
            type="primary",
            disabled=not ready,
        ):
            was_overwrite = _save_wedge_marking(
                row.json_path,
                points=points[:4],
                frame_shape=[img_h, img_w],
                flag_review=flag_review,
                note=note,
            )
            if was_overwrite:
                st.toast(f"Overwrote existing wedge markings for {row.experiment_id}")
            else:
                st.toast(f"Saved wedge markings for {row.experiment_id}")
            st.session_state["ewm_nav_idx"] = min(idx + 1, len(filtered) - 1)
            st.rerun()
    with ac2:
        st.caption("Use the trash icon on the canvas toolbar to clear and re-mark.")

    # --- Show existing marking ---
    if existing_wp.get("points"):
        st.markdown("---")
        flag_tag = " **[FLAGGED]**" if existing_wp.get("flag_review") else ""
        note_tag = f" -- {existing_wp['note']}" if existing_wp.get("note") else ""
        pts_str = ", ".join(f"({p[0]}, {p[1]})" for p in existing_wp["points"])
        st.caption(
            f"Existing: {pts_str} "
            f"({existing_wp.get('marked_at', '?')}){flag_tag}{note_tag}"
        )

    # --- Progress ---
    st.markdown("---")
    with st.expander("Progress", expanded=False):
        prog = []
        for r in all_rows:
            marked = _has_wedge_marking(r)
            try:
                am = _read_json(r.json_path).get("arena_markings") or {}
                wp = am.get("ezm_wedge_points") or {}
            except Exception:
                wp = {}
            prog.append({
                "experiment_id": r.experiment_id,
                "subject": r.subject_id,
                "sex": r.sex,
                "genotype": r.genotype,
                "marked": "yes" if marked else "",
                "flagged": "yes" if wp.get("flag_review") else "",
                "note": wp.get("note", ""),
            })
        st.dataframe(prog, use_container_width=True, hide_index=True)
