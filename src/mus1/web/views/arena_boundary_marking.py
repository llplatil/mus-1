"""NOR/NOF/OF Arena Boundary Marking -- click 5+ points on the bucket rim.

Operators mark the perimeter of the circular arena (Tamco bucket, Home
Depot 5-gal bucket) so a U-Net can be trained from real ground-truth
ellipse parameters. Saved data lands at
``arena_markings.arena_boundary.ellipse = {center_xy, axes_xy, angle_deg}``
— the exact shape :func:`mus1.compute.scaling._scale_with_profile` reads
to convert pixel distances to millimetres.

Workflow:

  1. Filter to experiments whose resolved arena profile has
     ``geometry.shape == "circular"`` (today: ``tamco_black_bucket`` or
     ``home_depot_5gal_orange``). The per-experiment override at
     ``arena_markings.arena_profile.profile_id`` wins; otherwise we fall
     back to the task default ``arena_profile_id`` declared on the task
     definition (NOR/NOF/OF all resolve to ``tamco_black_bucket``).
  2. Click at least five points on the rim. ``cv2.fitEllipse`` runs as
     soon as the 5th point is placed; the fitted ellipse is the save
     payload.
  3. Optional auto-suggest: when the JSON has a predicted block at
     ``arena_markings.predicted.circular_arena_boundary.ellipse``, the
     canvas seeds with 5 evenly-spaced points sampled around the
     predicted ellipse. Provenance distinguishes accepted vs edited per
     ROADMAP Iteration 6c.
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

from ..filters import (
    SCOPE_KEY,
    _cohort_member_ids,
    invalidate_after_write,
    nav_go,
    nav_index,
    pkey,
    render_filters,
    render_scope_banner,
)
from ..discovery import (
    CACHE_TTL_SECONDS,
    find_experiment_json,
    iter_experiment_dirs,
)

PANE = "arena_boundary"

# Tasks whose default arena is circular today. Used purely for discovery
# scoping; per-experiment profile overrides are honored regardless.
_CIRCULAR_TASKS = ("NOR", "NOF", "OF")

# Minimum click-points required for a valid cv2.fitEllipse — also the
# number we sample for the auto-suggest seed.
_MIN_POINTS_FOR_FIT = 5


# ---------------------------------------------------------------------------
# Registry caches
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _arena_profile_registry(project_path_str: str):
    """Cached arena-profile registry (builtins + project YAML)."""
    from mus1.arena_profiles.registry import ArenaProfileRegistry
    return ArenaProfileRegistry.from_config(Path(project_path_str))


@st.cache_resource(show_spinner=False)
def _task_registry():
    """Cached task registry (builtins only)."""
    from mus1.tasks.registry import TaskRegistry
    return TaskRegistry()


def _resolve_profile_id_for(
    *, task: str, arena_markings: Dict[str, Any],
    task_registry: Any,
) -> Optional[str]:
    """Apply the resolution cascade documented on
    :func:`mus1.compute.scaling.compute_px_to_mm`:

      1. Per-experiment override (``arena_markings.arena_profile.profile_id``).
      2. Task default (``task_def.arena_profile_id``).

    Returns ``None`` when neither resolves.
    """
    override = arena_markings.get("arena_profile") or {}
    if isinstance(override, dict) and override.get("profile_id"):
        return str(override["profile_id"])
    task_def = task_registry.get_or_none(task)
    if task_def is None:
        return None
    return getattr(task_def, "arena_profile_id", None)


# ---------------------------------------------------------------------------
# Experiment row + discovery
# ---------------------------------------------------------------------------

@dataclass
class _BoundaryRow:
    experiment_id: str
    task_type: str
    subject_id: str
    date_recorded: str
    sex: str
    genotype: str
    video_path: str
    json_path: Path
    frame_count: Optional[int]
    profile_id: str
    has_arena_boundary: bool


@st.cache_data(
    show_spinner="Loading circular-arena experiments...",
    ttl=CACHE_TTL_SECONDS,
)
def _load_circular_arena_experiments(project_path_str: str) -> List[Dict[str, Any]]:
    """Scan NOR/NOF/OF experiments and keep those resolving to a circular profile.

    Returns row dicts (not :class:`_BoundaryRow`) so the result is hashable
    for ``st.cache_data``. Conversion to dataclass happens at the call site.
    """
    project_path = Path(project_path_str)
    profiles = _arena_profile_registry(str(project_path))
    tasks = _task_registry()

    rows: List[Dict[str, Any]] = []
    for _root, task, exp_dir in iter_experiment_dirs(project_path):
        if task not in _CIRCULAR_TASKS:
            continue
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue
        md = data.get("metadata", {}) or {}
        vid = data.get("video", {}) or {}
        am = data.get("arena_markings", {}) or {}

        profile_id = _resolve_profile_id_for(
            task=task, arena_markings=am, task_registry=tasks,
        )
        if not profile_id:
            continue
        profile = profiles.get_or_none(profile_id)
        if profile is None:
            continue
        # Only keep circular geometries — the pane saves an ellipse.
        if getattr(profile.geometry, "shape", "").lower() != "circular":
            continue

        boundary = am.get("arena_boundary") or {}
        ellipse = boundary.get("ellipse") or {}
        has_boundary = bool(
            ellipse.get("center_xy") and ellipse.get("axes_xy")
        )

        rows.append({
            "experiment_id": data.get("experiment_id", exp_dir.name),
            "task_type": task,
            "subject_id": str(md.get("subject_id", "")),
            "date_recorded": str(md.get("date_recorded", "")),
            "sex": str(md.get("sex", "")),
            "genotype": str(md.get("genotype", "")),
            "video_path": vid.get("path", ""),
            "json_path": str(jp),
            "frame_count": vid.get("frame_count"),
            "profile_id": profile_id,
            "has_arena_boundary": has_boundary,
        })
    rows.sort(key=lambda r: (r["task_type"], r["experiment_id"]))
    return rows


def _rows_from_dicts(dicts: List[Dict[str, Any]]) -> List[_BoundaryRow]:
    out: List[_BoundaryRow] = []
    for d in dicts:
        out.append(_BoundaryRow(
            experiment_id=d["experiment_id"],
            task_type=d["task_type"],
            subject_id=d["subject_id"],
            date_recorded=d["date_recorded"],
            sex=d["sex"],
            genotype=d["genotype"],
            video_path=d["video_path"],
            json_path=Path(d["json_path"]),
            frame_count=d.get("frame_count"),
            profile_id=d["profile_id"],
            has_arena_boundary=bool(d.get("has_arena_boundary")),
        ))
    return out


# ---------------------------------------------------------------------------
# Frame extraction
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
    """Return a cached PIL image so Streamlit's media-file store keeps the
    same hash across reruns (avoids the "Missing file" first-load error)."""
    frame = _read_mid_frame(video_path, frame_count)
    if frame is None:
        return None
    from PIL import Image
    return Image.fromarray(frame)


# ---------------------------------------------------------------------------
# Ellipse fitting + JSON save
# ---------------------------------------------------------------------------

def _fit_ellipse_from_points(points_xy: List[List[float]]):
    """Return ``((cx, cy), (major, minor), angle_deg)`` from >=5 click-points.

    ``axes`` follow OpenCV's full-diameter convention; ``angle_deg`` is
    measured from the major axis, clockwise in image coordinates.
    """
    if len(points_xy) < _MIN_POINTS_FOR_FIT:
        raise ValueError(
            f"Need >= {_MIN_POINTS_FOR_FIT} points to fit an ellipse; "
            f"got {len(points_xy)}."
        )
    pts = np.asarray(points_xy, dtype=np.float32).reshape(-1, 1, 2)
    (cx, cy), (maj, minu), ang = cv2.fitEllipse(pts)
    return (float(cx), float(cy)), (float(maj), float(minu)), float(ang)


def _read_json(json_path: Path) -> dict:
    return json.loads(json_path.read_text())


def _save_arena_boundary(
    json_path: Path,
    *,
    points: List[List[float]],
    frame_shape: List[int],
    flag_review: bool,
    note: str,
    suggested_points: Optional[List[List[float]]] = None,
    model_run_id: str = "",
) -> bool:
    """Save the fitted ellipse at ``arena_markings.arena_boundary``.

    Preserves other arena_markings subsections (predictions, arena_profile,
    object marks). Returns True when an existing boundary block was
    overwritten.
    """
    from ..arena_boundary_autosuggest import classify_marking_provenance

    data = _read_json(json_path)
    am = data.get("arena_markings") or {}
    was_overwrite = bool((am.get("arena_boundary") or {}).get("ellipse"))

    (cx, cy), (maj, minu), ang = _fit_ellipse_from_points(points)
    method, edits = classify_marking_provenance(
        points, suggested_points=suggested_points,
    )

    block: Dict[str, Any] = {
        "ellipse": {
            "center_xy": [round(cx, 2), round(cy, 2)],
            "axes_xy": [round(maj, 2), round(minu, 2)],
            "angle_deg": round(ang, 2),
        },
        "click_points": [[round(p[0], 2), round(p[1], 2)] for p in points],
        "n_clicks": len(points),
        "frame_shape": frame_shape,
        "flag_review": flag_review,
        "note": note,
        "marked_at": datetime.now(tz=timezone.utc).isoformat(),
        "provenance": {"method": method},
    }
    if method != "manual":
        block["provenance"]["model_run_id"] = model_run_id
        block["provenance"]["edits"] = edits

    am["arena_boundary"] = block
    data["arena_markings"] = am
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    return was_overwrite


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_arena_boundary_marking(
    *,
    project_path: Path,
    workspace_root: Optional[str],
    db_path: Path,
) -> None:
    st.header("NOR/NOF Arena Boundary Marking")
    st.caption(
        f"Click {_MIN_POINTS_FOR_FIT}+ points on the bucket rim. "
        "An ellipse is fitted as soon as the 5th point is placed. "
        "Accept saves and advances. Trash icon on canvas clears clicks."
    )
    render_scope_banner()

    if st.button("Refresh (clear cache)", key=pkey(PANE, "refresh")):
        invalidate_after_write()
        st.rerun()

    all_dicts = _load_circular_arena_experiments(str(project_path))
    if not all_dicts:
        st.warning(
            "No circular-arena experiments found. Check that NOR/NOF/OF "
            "experiments resolve to an arena profile with circular geometry."
        )
        st.stop()

    # Universal filters via filters.render_filters. The pane uses
    # `has_arena_boundary` (computed in the loader) as the row field for
    # the marking-status filter.
    state, filtered_dicts = render_filters(
        rows=all_dicts,
        fields={"marking_status", "qc_statuses", "genotypes", "sexes", "text"},
        key_prefix=PANE,
        marking_field="has_arena_boundary",
        project_path=project_path,
        expanded=True,
    )
    # Apply universal scope (defensive: filter_by_cohort in render_filters
    # already does it, but a misconfigured project_path could no-op).
    scope_cohort = st.session_state.get(SCOPE_KEY)
    if scope_cohort:
        member_ids = _cohort_member_ids(project_path, scope_cohort)
        filtered_dicts = [
            r for r in filtered_dicts if r["experiment_id"] in member_ids
        ]
    filtered = _rows_from_dicts(filtered_dicts)

    # Pane-specific task filter (NOR / NOF / OF / All) — kept inline
    # because it's the primary in-pane selector.
    tcol1, tcol2 = st.columns([1, 3])
    with tcol1:
        task_filter = st.radio(
            "Task",
            options=["All", *_CIRCULAR_TASKS],
            horizontal=True,
            key=pkey(PANE, "task"),
        )
    if task_filter != "All":
        filtered = [r for r in filtered if r.task_type == task_filter]
    with tcol2:
        sort_by = st.selectbox(
            "Sort by",
            options=["experiment_id", "subject_id", "date_recorded"],
            key=pkey(PANE, "sort"),
        )
    filtered.sort(key=lambda r: getattr(r, sort_by))

    total_marked = sum(1 for d in all_dicts if d["has_arena_boundary"])
    st.caption(
        f"Total: {len(all_dicts)} | Marked: {total_marked} | "
        f"Remaining: {len(all_dicts) - total_marked} | "
        f"Showing: {len(filtered)}"
    )

    if not filtered:
        st.success("No experiments match current filters.")
        st.stop()

    # --- Navigation (index selector only; Prev/Next live in the action row below) ---
    nav2, nav4 = st.columns([2, 3])
    with nav2:
        cur = nav_index(PANE, len(filtered))
    with nav4:
        st.markdown(f"**{cur + 1} / {len(filtered)}** experiments")
    st.progress((cur + 1) / max(1, len(filtered)))

    row = filtered[cur]

    # --- Header ---
    st.subheader(f"{row.experiment_id}  ({row.task_type})")
    hdr = st.columns(5)
    with hdr[0]:
        st.markdown(f"**Subject:** {row.subject_id}")
    with hdr[1]:
        st.markdown(f"**Date:** {row.date_recorded}")
    with hdr[2]:
        st.markdown(f"**Sex:** {row.sex}")
    with hdr[3]:
        st.markdown(f"**Genotype:** {row.genotype}")
    with hdr[4]:
        st.markdown(f"**Profile:** {row.profile_id}")

    # --- Read JSON state for existing block ---
    exp_data = _read_json(row.json_path)
    existing_am = exp_data.get("arena_markings") or {}
    existing_block = existing_am.get("arena_boundary") or {}

    # --- Load mid-frame ---
    pil_img = _get_pil_image(row.video_path, row.frame_count)
    if pil_img is None:
        st.warning(f"Could not read frame from: {row.video_path}")
        st.stop()
    img_w, img_h = pil_img.size
    canvas_w = min(img_w, 800)
    scale = canvas_w / img_w
    canvas_h = int(img_h * scale)

    # --- Suggestion source ---
    from ..arena_boundary_autosuggest import (
        N_SUGGEST_POINTS,
        build_canvas_initial_drawing,
        read_predicted_block,
        sample_ellipse_points,
    )
    predicted_block = read_predicted_block(row.json_path)
    suggested_points: List[List[float]] = []
    suggested_run_id: str = ""
    initial_drawing = None
    suggestion_options = ["Manual"]
    if predicted_block:
        suggestion_options.append("U-Net auto-suggest")
    src_key = pkey(PANE, f"suggest_src__{row.experiment_id}")
    suggestion_source = st.selectbox(
        "Suggestion source",
        options=suggestion_options,
        index=0,
        key=src_key,
        help=(
            "Pre-populate the canvas with U-Net predictions. "
            "Drag points to edit before saving; provenance records "
            "whether predictions were accepted as-is or edited."
        ),
    )
    if suggestion_source == "U-Net auto-suggest" and predicted_block:
        ellipse = predicted_block.get("ellipse") or {}
        suggested_points = sample_ellipse_points(
            center_xy=list(ellipse.get("center_xy") or [0.0, 0.0]),
            axes_xy=list(ellipse.get("axes_xy") or [0.0, 0.0]),
            angle_deg=float(ellipse.get("angle_deg", 0.0)),
            n=N_SUGGEST_POINTS,
        )
        suggested_run_id = (
            predicted_block.get("model_run_id", "")
            or predicted_block.get("model_version", "")
        )
        initial_drawing = build_canvas_initial_drawing(
            suggested_points, scale=scale,
        )
        st.caption(
            f"Pre-filled {N_SUGGEST_POINTS} points sampled around the "
            f"prediction from model `{suggested_run_id}`. Drag any point "
            "to edit. Save records `unet_suggested+human_accepted` if no "
            "edits, `unet_suggested+human_edited` otherwise."
        )

    # --- Canvas ---
    # Include suggestion source in the key so toggling between Manual
    # and U-Net resets the canvas (otherwise Streamlit caches widget state
    # and ignores the new initial_drawing).
    canvas_key = pkey(
        PANE, f"canvas__{row.experiment_id}__{suggestion_source}",
    )
    canvas_result = st_canvas(
        fill_color="rgba(0, 255, 0, 0.3)",
        stroke_width=0,
        stroke_color="#00ff00",
        background_image=pil_img,
        drawing_mode="point",
        point_display_radius=8,
        height=canvas_h,
        width=canvas_w,
        initial_drawing=initial_drawing,
        key=canvas_key,
    )

    # --- Extract clicks (mirror ezm_wedge_marking convention) ---
    _pt_r = 8  # must match point_display_radius above
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
        st.info(
            f"Click {_MIN_POINTS_FOR_FIT} or more points on the bucket rim."
        )
    elif n_points < _MIN_POINTS_FOR_FIT:
        st.info(
            f"{n_points}/{_MIN_POINTS_FOR_FIT} points placed. Click "
            f"{_MIN_POINTS_FOR_FIT - n_points} more."
        )
    else:
        st.success(
            f"{n_points} points placed. Ready to fit + save."
        )

    # --- Live ellipse preview (when fit is valid) ---
    fit_ok = n_points >= _MIN_POINTS_FOR_FIT
    if fit_ok:
        try:
            (cx, cy), (maj, minu), ang = _fit_ellipse_from_points(points)
            st.caption(
                f"Fitted ellipse: center=({cx:.1f}, {cy:.1f}), "
                f"axes=({maj:.1f}, {minu:.1f}) px, angle={ang:.1f} deg."
            )
        except Exception as e:  # pragma: no cover (cv2 should always fit)
            st.warning(f"Ellipse fit failed: {e}")
            fit_ok = False

    # --- Note ---
    note = st.text_input(
        "Note",
        value=str(existing_block.get("note", "")),
        key=pkey(PANE, f"note__{row.experiment_id}"),
        placeholder="Optional note for this marking",
    )

    def _save(flag: bool) -> None:
        ow = _save_arena_boundary(
            row.json_path,
            points=points,
            frame_shape=[img_h, img_w],
            flag_review=flag,
            note=note,
            suggested_points=(
                suggested_points if suggestion_source == "U-Net auto-suggest" else None
            ),
            model_run_id=suggested_run_id,
        )
        st.toast(("Overwrote" if ow else "Saved") + f" arena boundary for {row.experiment_id}")
        invalidate_after_write()

    # --- Action row: previous | accept | accept & next | next | flag ---
    n_items = len(filtered)
    b_prev, b_acc, b_acc_next, b_next, b_flag = st.columns(5)
    with b_prev:
        if st.button("◀ Previous", key=pkey(PANE, "prev"), width="stretch", disabled=cur <= 0):
            nav_go(PANE, -1)
    with b_acc:
        if st.button("Accept", key=pkey(PANE, f"accept__{row.experiment_id}"),
                     type="primary", width="stretch", disabled=not fit_ok):
            _save(flag=False)
            st.rerun()
    with b_acc_next:
        if st.button("Accept & next", key=pkey(PANE, f"accept_next__{row.experiment_id}"),
                     width="stretch", disabled=not fit_ok):
            _save(flag=False)
            nav_go(PANE, +1)
    with b_next:
        if st.button("Next ▶", key=pkey(PANE, "next"), width="stretch", disabled=cur >= n_items - 1):
            nav_go(PANE, +1)
    with b_flag:
        if st.button("⚑ Flag", key=pkey(PANE, f"flag_btn__{row.experiment_id}"),
                     width="stretch", disabled=not fit_ok):
            _save(flag=True)
            nav_go(PANE, +1)
    st.caption("Accept = save (clears flag) · Accept & next = save + advance · "
               "Flag = save flagged for review · trash icon on the canvas clears clicks.")

    # --- Show existing block ---
    if existing_block.get("ellipse"):
        st.markdown("---")
        e = existing_block["ellipse"]
        flag_tag = (
            " **[FLAGGED]**" if existing_block.get("flag_review") else ""
        )
        note_tag = (
            f" -- {existing_block['note']}"
            if existing_block.get("note") else ""
        )
        st.caption(
            f"Existing: center={e.get('center_xy')} "
            f"axes={e.get('axes_xy')} angle={e.get('angle_deg')} deg "
            f"(n_clicks={existing_block.get('n_clicks', '?')}, "
            f"{existing_block.get('marked_at', '?')})"
            f"{flag_tag}{note_tag}"
        )

    # --- Progress overview ---
    st.markdown("---")
    with st.expander("Progress overview", expanded=False):
        prog = []
        for d in all_dicts:
            prog.append({
                "experiment_id": d["experiment_id"],
                "task": d["task_type"],
                "subject": d["subject_id"],
                "profile": d["profile_id"],
                "marked": "yes" if d["has_arena_boundary"] else "",
            })
        st.dataframe(prog, width="stretch", hide_index=True)
