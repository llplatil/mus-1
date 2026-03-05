"""NOR/NOF Object QC -- review and confirm object assignments per experiment.

Source of truth: experiment JSON files on disk.
DB sync happens separately via workspace_db_sync; this view only writes JSON.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import streamlit as st

# ---------------------------------------------------------------------------
# Canonical object vocabulary
# ---------------------------------------------------------------------------

CANONICAL_OBJECTS = ["diamond", "pyramid", "silo"]

_NORMALIZE_MAP: Dict[str, str] = {}
for _canon in CANONICAL_OBJECTS:
    _NORMALIZE_MAP[_canon] = _canon
    _NORMALIZE_MAP[_canon + "s"] = _canon
_NORMALIZE_MAP.update({
    "dimond": "diamond",
    "dimonds": "diamond",
    "pyramind": "pyramid",
    "pryamid": "pyramid",
})


def normalize_object_name(raw: str) -> str:
    """Map a single raw object token to its canonical name."""
    token = raw.strip().lower().rstrip("s")
    if token in _NORMALIZE_MAP:
        return _NORMALIZE_MAP[token]
    token_with_s = raw.strip().lower()
    if token_with_s in _NORMALIZE_MAP:
        return _NORMALIZE_MAP[token_with_s]
    for canon in CANONICAL_OBJECTS:
        if canon in token_with_s:
            return canon
    return raw.strip().lower()


def parse_toys_raw(toys_raw: str) -> Tuple[str, str]:
    """
    Parse a toys_raw string like 'pyramid + silo' into two canonical names.
    Returns (obj_a, obj_b). For single-object strings returns (obj, obj).
    """
    if not toys_raw:
        return ("", "")
    cleaned = toys_raw.strip()
    parts = re.split(r"\s*[+&,]\s*", cleaned)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return (normalize_object_name(parts[0]), normalize_object_name(parts[1]))
    if len(parts) == 1:
        return (normalize_object_name(parts[0]), normalize_object_name(parts[0]))
    return ("", "")


# ---------------------------------------------------------------------------
# Experiment row dataclass
# ---------------------------------------------------------------------------

@dataclass
class _ExperimentRow:
    experiment_id: str
    experiment_type: str
    subject_id: str
    date_recorded: str
    video_path: str
    video_filename: str
    json_path: Path
    toys_raw: str
    bucket: str
    object_left: Optional[str]
    object_right: Optional[str]
    novel_side: Optional[str]
    qc_status: Optional[str]
    qc_reviewed_at: Optional[str]
    qc_notes: str
    frame_count: Optional[int]
    duration_seconds: Optional[float]
    paired_experiment_id: Optional[str]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_nor_nof_experiments(experiment_data_root: Path) -> List[_ExperimentRow]:
    rows: List[_ExperimentRow] = []
    for task in ("NOR", "NOF"):
        task_dir = experiment_data_root / task
        if not task_dir.is_dir():
            continue
        for exp_dir in sorted(task_dir.iterdir()):
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
            el = md.get("experiment_level", {})
            vid = data.get("video", {})
            oqc = data.get("object_qc") or {}
            pair_block = data.get("nor_nof_pair") or {}

            toys_raw = el.get("toys_raw") or el.get("toy_raw") or ""
            rows.append(_ExperimentRow(
                experiment_id=data.get("experiment_id", exp_dir.name),
                experiment_type=data.get("experiment_type", task),
                subject_id=str(md.get("subject_id", "")),
                date_recorded=str(md.get("date_recorded", "")),
                video_path=vid.get("path", ""),
                video_filename=vid.get("filename", ""),
                json_path=jf,
                toys_raw=toys_raw,
                bucket=el.get("bucket", ""),
                object_left=el.get("object_left"),
                object_right=el.get("object_right"),
                novel_side=el.get("novel_side"),
                qc_status=oqc.get("status") if oqc else None,
                qc_reviewed_at=oqc.get("reviewed_at") if oqc else None,
                qc_notes=oqc.get("notes", "") if oqc else "",
                frame_count=vid.get("frame_count"),
                duration_seconds=vid.get("duration_seconds"),
                paired_experiment_id=pair_block.get("paired_experiment_id"),
            ))
    return rows


# ---------------------------------------------------------------------------
# Paired experiment lookup
# ---------------------------------------------------------------------------

def _load_pair_info(experiment_data_root: Path, paired_eid: Optional[str]) -> Optional[dict]:
    """Load key fields from the paired experiment's JSON."""
    if not paired_eid:
        return None
    parts = paired_eid.split("_", 1)
    if len(parts) < 2:
        return None
    task = parts[0]  # NOR or NOF
    pair_json = experiment_data_root / task / paired_eid / f"{paired_eid}.json"
    if not pair_json.exists():
        return None
    try:
        data = json.loads(pair_json.read_text())
    except Exception:
        return None
    el = data.get("metadata", {}).get("experiment_level", {})
    oqc = data.get("object_qc") or {}
    return {
        "experiment_id": paired_eid,
        "experiment_type": data.get("experiment_type", task),
        "toys_raw": el.get("toys_raw") or el.get("toy_raw") or "",
        "object_left": el.get("object_left"),
        "object_right": el.get("object_right"),
        "novel_side": el.get("novel_side"),
        "qc_status": oqc.get("status"),
    }


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


# ---------------------------------------------------------------------------
# Save helpers -- JSON only, DB syncs separately
# ---------------------------------------------------------------------------

def _save_qc_to_json(
    json_path: Path,
    *,
    object_left: str,
    object_right: str,
    novel_side: Optional[str],
    experiment_type: str,
    notes: str,
) -> None:
    data = json.loads(json_path.read_text())

    el = data.setdefault("metadata", {}).setdefault("experiment_level", {})
    el["object_left"] = object_left
    el["object_right"] = object_right
    if experiment_type == "NOR":
        el["novel_side"] = novel_side
    elif "novel_side" in el:
        del el["novel_side"]

    changed_type = data.get("experiment_type") != experiment_type
    original_type = data.get("experiment_type") if changed_type else None

    data["object_qc"] = {
        "status": "edited" if changed_type else "confirmed",
        "reviewed_at": datetime.now(tz=timezone.utc).isoformat(),
        "original_experiment_type": original_type,
        "notes": notes,
    }

    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def _change_experiment_type(
    *,
    experiment_data_root: Path,
    row: _ExperimentRow,
    new_type: str,
    object_left: str,
    object_right: str,
    novel_side: Optional[str],
    notes: str,
) -> Optional[str]:
    """
    Move an experiment from one task type to another (NOR<->NOF).
    Returns None on success, or an error string.
    """
    old_type = row.experiment_type
    if old_type == new_type:
        return None

    old_id = row.experiment_id
    new_id = old_id.replace(f"{old_type}_", f"{new_type}_", 1)

    old_folder = experiment_data_root / old_type / old_id
    new_folder = experiment_data_root / new_type / new_id

    if new_folder.exists():
        return f"Target folder already exists: {new_folder}"
    if not old_folder.exists():
        return f"Source folder not found: {old_folder}"

    new_task_dir = experiment_data_root / new_type
    new_task_dir.mkdir(parents=True, exist_ok=True)

    shutil.move(str(old_folder), str(new_folder))

    old_json = new_folder / f"{old_id}.json"
    new_json = new_folder / f"{new_id}.json"
    if old_json.exists():
        old_json.rename(new_json)

    data = json.loads(new_json.read_text())
    data["experiment_id"] = new_id
    data["experiment_type"] = new_type
    data["metadata"]["experiment_type"] = new_type

    old_video_path = data.get("video", {}).get("path", "")
    if old_video_path:
        data["video"]["path"] = old_video_path.replace(
            f"/{old_type}/{old_id}/", f"/{new_type}/{new_id}/"
        )

    el = data.setdefault("metadata", {}).setdefault("experiment_level", {})
    el["object_left"] = object_left
    el["object_right"] = object_right
    if new_type == "NOR":
        el["novel_side"] = novel_side
        if "toy_raw" in el:
            el["toys_raw"] = el.pop("toy_raw")
    else:
        if "novel_side" in el:
            del el["novel_side"]
        if "toys_raw" in el:
            el["toy_raw"] = el.pop("toys_raw")

    data["object_qc"] = {
        "status": "edited",
        "reviewed_at": datetime.now(tz=timezone.utc).isoformat(),
        "original_experiment_type": old_type,
        "notes": notes,
    }

    # Update nor_nof_pair references: the moved experiment now pairs
    # with the same subject+date under the *other* new task type.
    old_pair = data.get("nor_nof_pair", {})
    old_paired_eid = old_pair.get("paired_experiment_id")
    # After type flip, the new experiment pairs with the opposite task
    opposite_task = "NOF" if new_type == "NOR" else "NOR"
    data["nor_nof_pair"] = {
        "paired_experiment_id": old_paired_eid,
        "paired_experiment_type": opposite_task,
    }

    # Update the former pair's reference to point to the new experiment id
    if old_paired_eid:
        old_pair_parts = old_paired_eid.split("_", 1)
        if len(old_pair_parts) >= 2:
            pair_task = old_pair_parts[0]
            pair_json = experiment_data_root / pair_task / old_paired_eid / f"{old_paired_eid}.json"
            if pair_json.exists():
                try:
                    pair_data = json.loads(pair_json.read_text())
                    pair_data["nor_nof_pair"] = {
                        "paired_experiment_id": new_id,
                        "paired_experiment_type": new_type,
                    }
                    pair_json.write_text(json.dumps(pair_data, indent=2, default=str) + "\n")
                except Exception:
                    pass

    new_json.write_text(json.dumps(data, indent=2, default=str) + "\n")
    return None


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_nor_nof_object_qc(
    *,
    project_path: Path,
    workspace_root: Optional[str],
    db_path: Path,
) -> None:
    st.header("NOR/NOF Object QC")
    st.caption("Review object assignments per experiment. Edits write directly to JSON; DB syncs separately.")

    experiment_data_root = project_path / "experiment_data"
    if not experiment_data_root.is_dir():
        st.error(f"experiment_data not found at: {experiment_data_root}")
        st.stop()

    all_rows = _load_nor_nof_experiments(experiment_data_root)
    if not all_rows:
        st.warning("No NOR/NOF experiments found.")
        st.stop()

    # --- Filters ---
    fcol1, fcol2, fcol3 = st.columns([1, 1, 2])
    with fcol1:
        task_filter = st.radio("Task", ["Both", "NOR", "NOF"], horizontal=True, key="oqc_task")
    with fcol2:
        only_unreviewed = st.checkbox("Only un-QC'd", value=True, key="oqc_unreviewed")
    with fcol3:
        sort_by = st.selectbox("Sort by", ["subject_id", "date_recorded", "experiment_id"], key="oqc_sort")

    filtered = all_rows
    if task_filter != "Both":
        filtered = [r for r in filtered if r.experiment_type == task_filter]
    if only_unreviewed:
        filtered = [r for r in filtered if r.qc_status is None]

    filtered.sort(key=lambda r: getattr(r, sort_by))

    total_all = len(all_rows)
    total_qcd = sum(1 for r in all_rows if r.qc_status is not None)
    st.caption(f"Total: {total_all} | QC'd: {total_qcd} | Remaining: {total_all - total_qcd} | Showing: {len(filtered)}")

    if not filtered:
        st.success("All experiments in this filter have been QC'd.")
        st.stop()

    # --- Navigation ---
    # Use a separate session key for the "desired" index so we never write
    # to the widget key after the widget has been instantiated.
    if "oqc_nav_idx" not in st.session_state:
        st.session_state["oqc_nav_idx"] = 0

    nav1, nav2, nav3 = st.columns([1, 1, 4])
    with nav1:
        if st.button("Prev", key="oqc_prev"):
            st.session_state["oqc_nav_idx"] = max(0, st.session_state.get("oqc_nav_idx", 0) - 1)
            st.rerun()
    with nav2:
        if st.button("Next", key="oqc_next"):
            st.session_state["oqc_nav_idx"] = min(len(filtered) - 1, st.session_state.get("oqc_nav_idx", 0) + 1)
            st.rerun()

    cur_nav = st.session_state.get("oqc_nav_idx", 0)
    cur_nav = max(0, min(len(filtered) - 1, cur_nav))

    with nav3:
        idx = st.number_input(
            f"Index (0-{len(filtered)-1})",
            min_value=0,
            max_value=len(filtered) - 1,
            value=cur_nav,
            step=1,
            key="oqc_idx_input",
        )
    st.session_state["oqc_nav_idx"] = idx

    row = filtered[idx]

    # --- Header ---
    st.subheader(row.experiment_id)
    st.caption(
        f"Subject: {row.subject_id} | Date: {row.date_recorded} | "
        f"Type: {row.experiment_type} | Bucket: {row.bucket}"
    )

    # --- Frame display + current state side by side ---
    col_frame, col_info = st.columns([2, 1])

    with col_frame:
        frame = _read_mid_frame(row.video_path, row.frame_count)
        if frame is not None:
            st.image(frame, caption=f"Mid-frame: {row.video_filename}", width="stretch")
        else:
            st.warning(f"Could not read frame from: {row.video_path}")

    with col_info:
        st.markdown("**Current state in JSON**")
        st.text(f"toys_raw:     {row.toys_raw}")
        st.text(f"object_left:  {row.object_left or '(not set)'}")
        st.text(f"object_right: {row.object_right or '(not set)'}")
        st.text(f"novel_side:   {row.novel_side or '(not set)'}")
        st.text(f"bucket:       {row.bucket}")
        if row.qc_status:
            st.text(f"QC status:    {row.qc_status}")
            st.text(f"QC at:        {row.qc_reviewed_at}")

        if row.toys_raw:
            guessed_a, guessed_b = parse_toys_raw(row.toys_raw)
            st.caption(f"Auto-parsed: {guessed_a}, {guessed_b}")

        # Paired experiment info
        pair_info = _load_pair_info(experiment_data_root, row.paired_experiment_id)
        if pair_info:
            pair_type = pair_info["experiment_type"]
            st.markdown(f"---\n**Paired {pair_type}: {pair_info['experiment_id']}**")
            st.text(f"  toys_raw:     {pair_info['toys_raw']}")
            st.text(f"  object_left:  {pair_info['object_left'] or '(not set)'}")
            st.text(f"  object_right: {pair_info['object_right'] or '(not set)'}")
            if pair_type == "NOR":
                st.text(f"  novel_side:   {pair_info['novel_side'] or '(not set)'}")
            qc_tag = pair_info["qc_status"] or "not reviewed"
            st.text(f"  qc:           {qc_tag}")
        elif row.paired_experiment_id:
            st.markdown(f"---\n**Pair: {row.paired_experiment_id}** (JSON not found)")
        else:
            st.markdown("---\n*No paired experiment found*")

    # --- Edit form ---
    st.markdown("---")

    obj_options = CANONICAL_OBJECTS + ["(other)"]

    def _default_idx(val: Optional[str], options: List[str]) -> int:
        if val and val in options:
            return options.index(val)
        return 0

    guessed_left, guessed_right = "", ""
    if row.toys_raw:
        guessed_left, guessed_right = parse_toys_raw(row.toys_raw)

    default_left = row.object_left or guessed_left or ""
    default_right = row.object_right or guessed_right or ""

    ecol1, ecol2 = st.columns(2)
    with ecol1:
        left_sel = st.selectbox(
            "Object LEFT",
            options=obj_options,
            index=_default_idx(default_left, obj_options),
            key=f"oqc_left__{row.experiment_id}",
        )
        if left_sel == "(other)":
            left_sel = st.text_input("Left object name", value=default_left, key=f"oqc_left_other__{row.experiment_id}")

    with ecol2:
        right_sel = st.selectbox(
            "Object RIGHT",
            options=obj_options,
            index=_default_idx(default_right, obj_options),
            key=f"oqc_right__{row.experiment_id}",
        )
        if right_sel == "(other)":
            right_sel = st.text_input("Right object name", value=default_right, key=f"oqc_right_other__{row.experiment_id}")

    ecol3, ecol4 = st.columns(2)
    with ecol3:
        exp_type_sel = st.radio(
            "Experiment type",
            ["NOR", "NOF"],
            index=0 if row.experiment_type == "NOR" else 1,
            horizontal=True,
            key=f"oqc_type__{row.experiment_id}",
        )
    with ecol4:
        novel_side_sel: Optional[str] = None
        if exp_type_sel == "NOR":
            default_novel = row.novel_side or "left"
            novel_side_sel = st.radio(
                "Novel side",
                ["left", "right"],
                index=0 if default_novel == "left" else 1,
                horizontal=True,
                key=f"oqc_novel__{row.experiment_id}",
            )
        else:
            st.caption("NOF: both objects are familiar (no novel side)")

    notes_val = st.text_input("Notes (optional)", value=row.qc_notes, key=f"oqc_notes__{row.experiment_id}")

    # --- Save ---
    type_changed = exp_type_sel != row.experiment_type

    if type_changed:
        st.warning(
            f"Experiment type will change from **{row.experiment_type}** to **{exp_type_sel}**. "
            f"This will move the folder and rename files."
        )
        confirm_type_change = st.checkbox(
            "I confirm the type change", key=f"oqc_confirm_type__{row.experiment_id}"
        )
    else:
        confirm_type_change = True

    if st.button("Confirm QC", type="primary", key=f"oqc_save__{row.experiment_id}", disabled=not confirm_type_change):
        if type_changed:
            err = _change_experiment_type(
                experiment_data_root=experiment_data_root,
                row=row,
                new_type=exp_type_sel,
                object_left=left_sel,
                object_right=right_sel,
                novel_side=novel_side_sel,
                notes=notes_val,
            )
            if err:
                st.error(f"Type change failed: {err}")
            else:
                st.success(f"Type changed and QC saved: {row.experiment_id} -> {exp_type_sel}")
                _read_mid_frame.clear()
                st.session_state["oqc_nav_idx"] = min(idx + 1, len(filtered) - 1)
                st.rerun()
        else:
            _save_qc_to_json(
                row.json_path,
                object_left=left_sel,
                object_right=right_sel,
                novel_side=novel_side_sel,
                experiment_type=exp_type_sel,
                notes=notes_val,
            )
            st.success(f"QC saved for {row.experiment_id}")
            st.session_state["oqc_nav_idx"] = min(idx + 1, len(filtered) - 1)
            st.rerun()

    # --- Progress table ---
    st.markdown("---")
    with st.expander("Progress overview", expanded=False):
        table_rows = []
        for r in all_rows:
            table_rows.append({
                "experiment_id": r.experiment_id,
                "type": r.experiment_type,
                "subject": r.subject_id,
                "date": r.date_recorded,
                "toys_raw": r.toys_raw,
                "obj_left": r.object_left or "",
                "obj_right": r.object_right or "",
                "pair": r.paired_experiment_id or "",
                "qc": r.qc_status or "",
            })
        st.dataframe(table_rows, width="stretch", hide_index=True)
