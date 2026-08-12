"""NOR/NOF Object Marking -- click to mark object centers on mid-frame.

Workflow: click left object center, then right object center on the arena
image. Accept saves to JSON and advances. Use the canvas trash icon to
clear and re-mark. Flag for review adds a note to the JSON.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
import streamlit as st
from streamlit_drawable_canvas import st_canvas

from ..filters import (
    SCOPE_KEY,
    _cohort_member_ids,
    invalidate_after_write,
    nav_go,
    nav_index,
    pkey,
    render_scope_banner,
)

PANE = "nor_nof_om"

from .nor_nof_object_qc import (
    _ExperimentRow,
    _load_nor_nof_experiments,
    _load_pair_info,
    bucket_label,
    has_video,
)

# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _read_mid_frame_for_marking(video_path: str, frame_count: Optional[int]) -> Optional[np.ndarray]:
    """Return the mid-video frame as an RGB numpy array.

    Uses ``st.cache_resource`` so the *same* ndarray object stays in memory
    (avoids Streamlit's media-file-storage eviction that causes "Missing file"
    errors with ``st.cache_data``).
    """
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
def _get_pil_image_for_canvas(video_path: str, frame_count: Optional[int]):
    """Return a cached PIL Image for the canvas background.

    Creating a *new* PIL Image on every rerun gives it a new hash in
    Streamlit's media-file storage.  The browser still holds the old
    hash from the previous render, requests it, and gets a
    ``MediaFileStorageError``.  Caching the PIL object keeps the same
    hash alive across reruns, fixing the "Missing file" error on first load.
    """
    frame = _read_mid_frame_for_marking(video_path, frame_count)
    if frame is None:
        return None
    from PIL import Image
    return Image.fromarray(frame)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _read_json(json_path: Path) -> dict:
    return json.loads(json_path.read_text())


def _has_marking(row: _ExperimentRow) -> bool:
    try:
        am = _read_json(row.json_path).get("arena_markings") or {}
    except Exception:
        return False
    return bool(am.get("object_left_xy") and am.get("object_right_xy"))


def _save_marking(
    json_path: Path,
    *,
    left_xy: list,
    right_xy: list,
    frame_shape: list,
    flag_review: bool,
    note: str,
) -> None:
    data = _read_json(json_path)
    data["arena_markings"] = {
        "object_left_xy": left_xy,
        "object_right_xy": right_xy,
        "frame_shape": frame_shape,
        "flag_review": flag_review,
        "note": note,
        "marked_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n")


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_nor_nof_object_marking(
    *,
    project_path: Path,
    workspace_root: Optional[str],
    db_path: Path,
) -> None:
    st.header("NOR/NOF Object Marking")
    st.caption(
        "Click **left object center**, then **right object center** on the frame. "
        "Accept saves and advances. Trash icon on canvas clears clicks."
    )
    render_scope_banner()

    experiment_data_root = project_path / "experiment_data"
    if not experiment_data_root.is_dir():
        st.error(f"experiment_data not found at: {experiment_data_root}")
        st.stop()

    all_rows = _load_nor_nof_experiments(experiment_data_root)
    if not all_rows:
        st.warning("No NOR/NOF experiments found.")
        st.stop()

    # --- Filters ---
    # Cohort scope is read from the universal scope picker in the sidebar
    # (see web/filters.py). Task / unmarked / flagged / sort are
    # pane-specific primary controls and stay in the main area.
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 2])
    with fc1:
        task_filter = st.radio(
            "Task", ["Both", "NOR", "NOF"], horizontal=True,
            key=pkey(PANE, "task"),
        )
    with fc2:
        only_unmarked = st.checkbox(
            "Only unmarked", value=True, key=pkey(PANE, "unmarked"),
        )
    with fc3:
        only_flagged = st.checkbox(
            "Only flagged", value=False, key=pkey(PANE, "flagged"),
        )
    with fc4:
        sort_by = st.selectbox(
            "Sort by",
            ["subject_id", "date_recorded", "experiment_id"],
            key=pkey(PANE, "sort"),
        )

    filtered: List[_ExperimentRow] = list(all_rows)
    # Apply universal cohort scope
    scope_cohort = st.session_state.get(SCOPE_KEY)
    if scope_cohort:
        member_ids = _cohort_member_ids(project_path, scope_cohort)
        filtered = [r for r in filtered if r.experiment_id in member_ids]
    # Snapshot the population after cohort scope but before the pane-specific
    # task/marked/flagged filters. This lets the empty-result message below
    # distinguish "nothing is in scope" (empty/stale cohort) from "everything
    # in scope is already marked" -- the two used to be conflated into a
    # misleading "all marked" success.
    scoped = list(filtered)
    if task_filter != "Both":
        filtered = [r for r in filtered if r.experiment_type == task_filter]
    task_scoped = list(filtered)
    # Videoless experiments (e.g. pilot NOR whose test recording is missing) can
    # never be frame-marked. Keep them out of the "Only unmarked" queue so it can
    # actually reach zero; they stay visible/countable when the box is off.
    videoless = [r for r in task_scoped if not has_video(r)]
    if only_unmarked:
        filtered = [r for r in filtered if not _has_marking(r) and has_video(r)]
    if only_flagged:
        def _is_flagged(r: _ExperimentRow) -> bool:
            try:
                am = _read_json(r.json_path).get("arena_markings") or {}
            except Exception:
                return False
            return bool(am.get("flag_review"))
        filtered = [r for r in filtered if _is_flagged(r)]

    filtered.sort(key=lambda r: getattr(r, sort_by))

    total_marked = sum(1 for r in all_rows if _has_marking(r))
    # Note attaches to "Showing" (the current filtered view), not to the global
    # Total/Marked — videoless are hidden when the queue is on, else included.
    _vl_note = ""
    if videoless:
        _vl_note = (
            f" ({len(videoless)} videoless hidden — can't be marked)"
            if only_unmarked else
            f" (incl. {len(videoless)} videoless — can't be marked)"
        )
    st.caption(
        f"Total: {len(all_rows)} | Marked: {total_marked} | "
        f"Remaining: {len(all_rows) - total_marked} | Showing: {len(filtered)}{_vl_note}"
    )

    if not filtered:
        _where = f" in cohort **{scope_cohort}**" if scope_cohort else ""
        if scope_cohort and not scoped:
            st.warning(
                f"No experiments are in scope for cohort **{scope_cohort}** — it is "
                f"either empty or references experiment IDs that are not present on "
                f"disk. Clear the scope in the sidebar to browse all experiments, or "
                f"fix the cohort's membership."
            )
        elif not task_scoped:
            st.info(f"No **{task_filter}** experiments{_where}.")
        elif only_flagged:
            st.info(f"No experiments flagged for review{_where}.")
        elif only_unmarked:
            _markable = len(task_scoped) - len(videoless)
            if _markable == 0 and videoless:
                st.info(
                    f"No markable experiments{_where} matching this task filter — "
                    f"all {len(videoless)} have no video and can't be frame-marked "
                    f"(assign object names in the Object Association pane instead)."
                )
            else:
                _vl_tail = (
                    f" ({len(videoless)} more have no video and can't be marked)"
                    if videoless else ""
                )
                st.success(
                    f"All {_markable} markable experiment(s){_where} matching this "
                    f"task filter are already marked{_vl_tail}."
                )
        else:
            st.info("No experiments match the current filters.")
        st.stop()

    # --- Navigation (index selector only; Prev/Next live in the action row below) ---
    nc, _ = st.columns([2, 5])
    with nc:
        idx = nav_index(PANE, len(filtered))
    row = filtered[idx]

    # --- Read full JSON once for this experiment ---
    exp_data = _read_json(row.json_path)
    el = exp_data.get("metadata", {}).get("experiment_level", {})
    existing_am = exp_data.get("arena_markings") or {}

    # --- Header with object labels ---
    st.subheader(row.experiment_id)

    hdr_cols = st.columns([2, 2, 2, 2, 2])
    with hdr_cols[0]:
        st.markdown(f"**Subject:** {row.subject_id}")
    with hdr_cols[1]:
        st.markdown(f"**Date:** {row.date_recorded}")
    with hdr_cols[2]:
        st.markdown(f"**Type:** {row.experiment_type}")
    with hdr_cols[3]:
        st.markdown(f":red[**LEFT: {el.get('object_left', '?')}**]")
    with hdr_cols[4]:
        st.markdown(f":blue[**RIGHT: {el.get('object_right', '?')}**]")

    _bucket = bucket_label(project_path, row)
    if row.experiment_type == "NOR":
        ns = el.get("novel_side", "unknown")
        if ns and ns != "unknown":
            st.caption(f"Novel side: **{ns}** | Bucket: {_bucket}")
        else:
            st.caption(f"Novel side: unknown | Bucket: {_bucket}")

        pair_info = _load_pair_info(experiment_data_root, row.paired_experiment_id)
        if pair_info:
            st.caption(
                f"Paired {pair_info['experiment_type']}: {pair_info['experiment_id']} | "
                f"L: {pair_info['object_left'] or '?'} | R: {pair_info['object_right'] or '?'}"
            )
    else:
        st.caption(f"Bucket: {_bucket}")
        pair_info = _load_pair_info(experiment_data_root, row.paired_experiment_id)
        if pair_info:
            ns_tag = pair_info.get("novel_side") or "?"
            st.caption(
                f"Paired {pair_info['experiment_type']}: {pair_info['experiment_id']} | "
                f"L: {pair_info['object_left'] or '?'} | R: {pair_info['object_right'] or '?'} | "
                f"Novel side: {ns_tag}"
            )

    # --- Load frame ---
    # Only decode when a video exists; render a graceful state otherwise so the
    # pane stays usable (Prev/Next above still work) instead of a hard st.stop().
    pil_img = _get_pil_image_for_canvas(row.video_path, row.frame_count) if has_video(row) else None
    if pil_img is None:
        if not has_video(row):
            st.info(
                "**No video for this experiment** — it can't be object-marked, so "
                "it's excluded from the *Only unmarked* queue. Object *names* can "
                "still be assigned in the **NOR/NOF Object Association** pane from "
                "the linked partner. Use **Prev/Next** to continue."
            )
        else:
            st.warning(
                f"Could not read a frame from: {row.video_path} — the file may be "
                "missing or unreadable. Use **Prev/Next** to continue."
            )
        return  # keep the pane alive; skip the canvas/accept UI for this row

    img_w, img_h = pil_img.size

    canvas_w = min(img_w, 800)
    scale = canvas_w / img_w
    canvas_h = int(img_h * scale)

    # --- Canvas ---
    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.3)",
        stroke_width=0,
        stroke_color="#ff0000",
        background_image=pil_img,
        drawing_mode="point",
        point_display_radius=8,
        height=canvas_h,
        width=canvas_w,
        key=f"om_canvas__{row.experiment_id}",
    )

    # --- Extract clicks ---
    # fabric.js "point" mode: originX is "left" so the `left` property is
    # the circle's left edge, not its center.  Add point_display_radius to
    # get the true center-x.  originY is "center" so `top` is already the
    # center-y (confirmed by cross-referencing with zone-JSON markings).
    _pt_r = 8  # must match point_display_radius above
    points = []
    if canvas_result.json_data is not None:
        for obj in canvas_result.json_data.get("objects", []):
            if obj.get("type") == "circle":
                cx = obj.get("left", 0) + _pt_r
                cy = obj.get("top", 0)
                points.append((cx / scale, cy / scale))

    left_xy = None
    right_xy = None
    if len(points) >= 1:
        left_xy = [round(points[0][0], 1), round(points[0][1], 1)]
    if len(points) >= 2:
        right_xy = [round(points[1][0], 1), round(points[1][1], 1)]

    # --- Click status ---
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        if left_xy:
            st.success(f":red[LEFT] ({el.get('object_left','?')}): ({left_xy[0]}, {left_xy[1]})")
        else:
            st.info(f"Click **left** object ({el.get('object_left','?')})")
    with sc2:
        if right_xy:
            st.success(f":blue[RIGHT] ({el.get('object_right','?')}): ({right_xy[0]}, {right_xy[1]})")
        elif left_xy:
            st.info(f"Click **right** object ({el.get('object_right','?')})")
        else:
            st.write("")
    with sc3:
        if len(points) > 2:
            st.warning(f"{len(points)} clicks -- only first 2 used. Clear to redo.")

    # --- Note ---
    ready = left_xy is not None and right_xy is not None
    note = st.text_input(
        "Note",
        value=existing_am.get("note", ""),
        key=f"om_note__{row.experiment_id}",
        placeholder="Optional note for this marking",
    )

    def _save(flag: bool) -> None:
        # Flag can fire without a fresh 2-object click; preserve any existing
        # coords so flagging never erases a prior marking.
        lx = left_xy if left_xy is not None else existing_am.get("object_left_xy")
        rx = right_xy if right_xy is not None else existing_am.get("object_right_xy")
        fs = [img_h, img_w] if ready else existing_am.get("frame_shape", [img_h, img_w])
        _save_marking(row.json_path, left_xy=lx, right_xy=rx, frame_shape=fs,
                      flag_review=flag, note=note)

    # --- Action row: previous | accept | accept & next | next | flag ---
    n_items = len(filtered)
    b_prev, b_acc, b_acc_next, b_next, b_flag = st.columns(5)
    with b_prev:
        if st.button("◀ Previous", key="om_prev", width="stretch", disabled=idx <= 0):
            nav_go(PANE, -1)
    with b_acc:
        if st.button("Accept", key=f"om_accept__{row.experiment_id}", type="primary",
                     width="stretch", disabled=not ready):
            _save(flag=False)
            st.rerun()
    with b_acc_next:
        if st.button("Accept & next", key=f"om_accept_next__{row.experiment_id}",
                     width="stretch", disabled=not ready):
            _save(flag=False)
            nav_go(PANE, +1)
    with b_next:
        if st.button("Next ▶", key="om_next", width="stretch", disabled=idx >= n_items - 1):
            nav_go(PANE, +1)
    with b_flag:
        if st.button("⚑ Flag", key=f"om_flag_btn__{row.experiment_id}", width="stretch"):
            _save(flag=True)
            nav_go(PANE, +1)

    st.caption("Accept = save (clears flag) · Accept & next = save + advance · "
               "Flag = mark for review (keeps existing marks) · trash icon on the canvas clears clicks.")

    # --- Show existing marking ---
    if existing_am.get("object_left_xy"):
        st.markdown("---")
        flag_tag = " **[FLAGGED]**" if existing_am.get("flag_review") else ""
        note_tag = f" -- {existing_am['note']}" if existing_am.get("note") else ""
        st.caption(
            f"Existing: L={existing_am['object_left_xy']} "
            f"R={existing_am.get('object_right_xy')} "
            f"({existing_am.get('marked_at', '?')}){flag_tag}{note_tag}"
        )

    # --- Progress ---
    st.markdown("---")
    with st.expander("Progress", expanded=False):
        prog = []
        for r in all_rows:
            marked = _has_marking(r)
            try:
                am = _read_json(r.json_path).get("arena_markings") or {}
            except Exception:
                am = {}
            prog.append({
                "experiment_id": r.experiment_id,
                "type": r.experiment_type,
                "subject": r.subject_id,
                "marked": "yes" if marked else "",
                "flagged": "yes" if am.get("flag_review") else "",
                "note": am.get("note", ""),
            })
        st.dataframe(prog, width="stretch", hide_index=True)
