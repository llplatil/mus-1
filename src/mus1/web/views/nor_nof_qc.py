"""NOR/NOF paired QC review, novel-side editing, and training-set curation."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import streamlit as st


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

@dataclass
class _VideoAnnotation:
    task: str
    session_id: str
    subject_id: str
    recording_date: str
    video_path: str
    crop_xyxy: List[int]
    json_path: Path
    payload: Dict[str, Any]


@dataclass
class _Pair:
    key: str  # subject_id__recording_date
    subject_id: str
    recording_date: str
    nof: Optional[_VideoAnnotation] = None
    nor: Optional[_VideoAnnotation] = None


def _load_annotations(
    qc_csv: Path,
    json_dir: Path,
) -> List[_Pair]:
    """Read the QC CSV and pair each NOF/NOR by subject + recording_date."""
    if not qc_csv.exists():
        return []

    rows: List[Dict[str, str]] = []
    with qc_csv.open(newline="") as f:
        rows = list(csv.DictReader(f))

    # Build (subject_id, recording_date) -> {task -> row}
    by_key: Dict[str, Dict[str, Dict[str, str]]] = {}
    for r in rows:
        sid = str(r.get("subject_id") or "").strip()
        rdate = str(r.get("recording_date") or "").strip()
        task = str(r.get("task") or "").strip().upper()
        if not sid or not rdate or task not in ("NOR", "NOF"):
            continue
        key = f"{sid}__{rdate}"
        by_key.setdefault(key, {})[task] = r

    # Scan JSON dir once
    json_by_stem: Dict[str, Path] = {}
    if json_dir.is_dir():
        for jp in json_dir.glob("*_nor_nof_objects_v2.json"):
            json_by_stem[jp.stem] = jp

    def _find_json(session_id: str, video_path: str) -> Optional[Path]:
        from ..paths import safe_stem_annotator, _safe_token
        stem = safe_stem_annotator(video_path)
        if session_id:
            prefixed = f"{_safe_token(session_id)}__{stem}_nor_nof_objects_v2"
            if prefixed in json_by_stem:
                return json_by_stem[prefixed]
        plain = f"{stem}_nor_nof_objects_v2"
        if plain in json_by_stem:
            return json_by_stem[plain]
        for k, v in json_by_stem.items():
            if k.endswith(f"__{stem}_nor_nof_objects_v2"):
                return v
        return None

    pairs: List[_Pair] = []
    for key in sorted(by_key):
        parts = key.split("__", 1)
        sid, rdate = parts if len(parts) == 2 else (key, "")
        p = _Pair(key=key, subject_id=sid, recording_date=rdate)
        for task in ("NOF", "NOR"):
            r = by_key[key].get(task)
            if r is None:
                continue
            vp = str(r.get("video_path") or "").strip()
            session_id = str(r.get("session_id") or "").strip()
            crop_raw = str(r.get("crop_xyxy") or "").strip()
            crop: List[int] = []
            if crop_raw:
                try:
                    crop = [int(float(x)) for x in crop_raw.split(",")]
                except Exception:
                    crop = []
            jp = _find_json(session_id, vp)
            if jp is None:
                continue
            try:
                payload = json.loads(jp.read_text())
            except Exception:
                continue
            ann = _VideoAnnotation(
                task=task,
                session_id=session_id,
                subject_id=sid,
                recording_date=rdate,
                video_path=vp,
                crop_xyxy=crop if len(crop) == 4 else [],
                json_path=jp,
                payload=payload,
            )
            if task == "NOF":
                p.nof = ann
            else:
                p.nor = ann
        pairs.append(p)
    return pairs


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=300)
def _read_frame(video_path: str, frame_idx: int) -> Optional[np.ndarray]:
    vp = Path(video_path)
    if not vp.exists():
        return None
    cap = cv2.VideoCapture(str(vp))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ret, bgr = cap.read()
    cap.release()
    if not ret:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _apply_crop(frame: np.ndarray, crop_xyxy: List[int]) -> np.ndarray:
    if len(crop_xyxy) != 4:
        return frame
    h, w = frame.shape[:2]
    x1, x2, y1, y2 = crop_xyxy
    x1, x2 = max(0, min(w - 1, x1)), max(0, min(w, x2))
    y1, y2 = max(0, min(h - 1, y1)), max(0, min(h, y2))
    if x2 > x1 and y2 > y1:
        return frame[y1:y2, x1:x2].copy()
    return frame


def _draw_qc_overlay(
    frame: np.ndarray,
    payload: Dict[str, Any],
    *,
    show_center_dots: bool = True,
    highlight_novel: bool = True,
) -> np.ndarray:
    """Draw arena ellipse, object circles, center dots, and role labels."""
    img = frame.copy()
    h, w = img.shape[:2]

    # Arena ellipse
    arena = payload.get("arena_outer_ellipse", {})
    center = arena.get("center", [])
    axes = arena.get("axes", [])
    angle = arena.get("angle_deg", 0.0)
    if len(center) == 2 and len(axes) == 2:
        cx, cy = int(round(center[0])), int(round(center[1]))
        ax, ay = max(1, int(round(axes[0] / 2.0))), max(1, int(round(axes[1] / 2.0)))
        cv2.ellipse(img, (cx, cy), (ax, ay), float(angle), 0, 360, (0, 180, 255), 2, cv2.LINE_AA)

    # Objects
    objects = payload.get("objects", [])
    meta = payload.get("meta", {})
    for obj in objects:
        oc = obj.get("center", [])
        r = obj.get("radius_px", 0.0)
        role = str(obj.get("role") or "").lower()
        label = str(obj.get("label") or "")
        name = str(obj.get("name") or "")
        if len(oc) != 2:
            continue
        ox, oy = float(oc[0]), float(oc[1])
        ri = max(1, int(round(float(r))))
        oxi, oyi = int(round(ox)), int(round(oy))

        if role == "novel" and highlight_novel:
            circle_color = (255, 80, 80)  # red-ish for novel
        elif role == "familiar":
            circle_color = (0, 255, 0)  # green for familiar
        else:
            circle_color = (255, 255, 0)

        cv2.circle(img, (oxi, oyi), ri, circle_color, 2, cv2.LINE_AA)

        if show_center_dots:
            cv2.circle(img, (oxi, oyi), 5, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, (oxi, oyi), 5, circle_color, 2, cv2.LINE_AA)

        tag = f"{label} ({role})"
        text_y = max(15, oyi - ri - 8)
        cv2.putText(img, tag, (oxi - 40, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, circle_color, 1, cv2.LINE_AA)

    # Hemisphere divider (line between objects through arena center)
    if len(objects) >= 2 and len(center) == 2:
        c0 = objects[0].get("center", [])
        c1 = objects[1].get("center", [])
        if len(c0) == 2 and len(c1) == 2:
            vx = c1[0] - c0[0]
            vy = c1[1] - c0[1]
            dx, dy = -vy, vx
            norm = math.hypot(dx, dy)
            if norm > 0:
                dx /= norm
                dy /= norm
                span = max(h, w) * 2
                lx0 = int(round(center[0] - dx * span))
                ly0 = int(round(center[1] - dy * span))
                lx1 = int(round(center[0] + dx * span))
                ly1 = int(round(center[1] + dy * span))
                cv2.line(img, (lx0, ly0), (lx1, ly1), (255, 255, 255), 1, cv2.LINE_AA)

    return img


def _swap_novel_side(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Swap which object is novel vs familiar in the payload and return updated copy."""
    out = json.loads(json.dumps(payload))
    objects = out.get("objects", [])
    if len(objects) >= 2:
        for obj in objects:
            role = str(obj.get("role") or "").lower()
            if role == "novel":
                obj["role"] = "familiar"
            elif role == "familiar":
                obj["role"] = "novel"
    meta = out.get("meta", {})
    if isinstance(meta, dict):
        for key in ("object_a_role", "object_b_role", "left_object_role", "right_object_role"):
            val = str(meta.get(key) or "").lower()
            if val == "novel":
                meta[key] = "familiar"
            elif val == "familiar":
                meta[key] = "novel"
    out["meta"] = meta
    return out


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_nor_nof_qc(
    *,
    project_path: Path,
    workspace_root: Optional[str],
) -> None:
    st.header("NOR/NOF Paired QC Review")
    st.caption("Review marked arenas side-by-side, fix novel-object assignment, curate training set.")

    repo_root = Path(__file__).resolve().parents[4]
    json_dir = repo_root / "workspace" / "arena_zones" / "nor_nof_per_video_v2"

    qc_csv_default = project_path / "ml_review" / "nor_nof_roi" / "nor_nof_roi_todo.csv"
    qc_csv = Path(
        st.text_input(
            "QC CSV (source list)",
            value=str(qc_csv_default),
            key="nqc_qc_csv",
        )
    ).expanduser()
    if not qc_csv.exists():
        st.error(f"QC CSV not found: {qc_csv}")
        st.stop()

    json_dir_input = Path(
        st.text_input("JSON directory (saved annotations)", str(json_dir), key="nqc_json_dir")
    ).expanduser()

    pairs = _load_annotations(qc_csv, json_dir_input)
    complete_pairs = [p for p in pairs if p.nof is not None and p.nor is not None]
    incomplete = [p for p in pairs if p.nof is None or p.nor is None]

    st.caption(f"Total pairs: {len(pairs)} | Complete (both NOF+NOR): {len(complete_pairs)} | Incomplete: {len(incomplete)}")
    if incomplete:
        with st.expander(f"Incomplete pairs ({len(incomplete)})", expanded=False):
            for p in incomplete:
                missing = []
                if p.nof is None:
                    missing.append("NOF")
                if p.nor is None:
                    missing.append("NOR")
                st.write(f"`{p.key}` -- missing: {', '.join(missing)}")

    if not complete_pairs:
        st.warning("No complete NOF+NOR pairs found.")
        st.stop()

    # --- Approval state -------------------------------------------------------
    approval_key = "nqc_approved"
    if approval_key not in st.session_state:
        # Try to restore from sidecar
        sidecar = qc_csv.parent / ".nor_nof_qc_approval.json"
        if sidecar.exists():
            try:
                st.session_state[approval_key] = json.loads(sidecar.read_text())
            except Exception:
                st.session_state[approval_key] = {}
        else:
            st.session_state[approval_key] = {}

    def _persist_approval() -> None:
        sidecar = qc_csv.parent / ".nor_nof_qc_approval.json"
        try:
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(json.dumps(st.session_state.get(approval_key, {}), indent=2))
        except Exception:
            pass

    # --- Pair navigation ------------------------------------------------------
    if "nqc_pair_idx" not in st.session_state:
        st.session_state["nqc_pair_idx"] = 0
    st.session_state["nqc_pair_idx"] = max(0, min(len(complete_pairs) - 1, int(st.session_state["nqc_pair_idx"])))

    nav1, nav2, nav3 = st.columns([1, 1, 4])
    with nav1:
        if st.button("Prev pair", key="nqc_prev"):
            st.session_state["nqc_pair_idx"] = max(0, int(st.session_state["nqc_pair_idx"]) - 1)
            st.rerun()
    with nav2:
        if st.button("Next pair", key="nqc_next"):
            st.session_state["nqc_pair_idx"] = min(len(complete_pairs) - 1, int(st.session_state["nqc_pair_idx"]) + 1)
            st.rerun()
    with nav3:
        st.number_input(
            "Pair index",
            min_value=0,
            max_value=len(complete_pairs) - 1,
            step=1,
            key="nqc_pair_idx",
        )

    idx = int(st.session_state["nqc_pair_idx"])
    pair = complete_pairs[idx]
    assert pair.nof is not None and pair.nor is not None

    st.subheader(f"Pair: subject {pair.subject_id} / {pair.recording_date}")

    # --- Approval checkbox for this pair --------------------------------------
    approved = bool(st.session_state.get(approval_key, {}).get(pair.key, False))
    new_approved = st.checkbox(
        "Approved for training",
        value=approved,
        key=f"nqc_approve__{pair.key}",
    )
    if new_approved != approved:
        st.session_state.setdefault(approval_key, {})[pair.key] = new_approved
        _persist_approval()

    # --- Side-by-side rendering -----------------------------------------------
    col_nof, col_nor = st.columns(2)
    for col, ann, label in [(col_nof, pair.nof, "NOF (familiarization)"), (col_nor, pair.nor, "NOR (recognition)")]:
        with col:
            st.markdown(f"**{label}**")
            st.caption(f"`{Path(ann.video_path).name}`")
            frame_idx = int(ann.payload.get("annotations", {}).get("frame_idx", 0))
            frame = _read_frame(ann.video_path, frame_idx)
            if frame is None:
                st.error(f"Could not read frame from: {ann.video_path}")
                continue
            frame = _apply_crop(frame, ann.crop_xyxy)
            overlay = _draw_qc_overlay(frame, ann.payload, show_center_dots=True, highlight_novel=True)
            st.image(overlay, use_container_width=True)

            # Show metadata summary
            meta = ann.payload.get("meta", {})
            objects = ann.payload.get("objects", [])
            obj_summary = []
            for obj in objects:
                obj_summary.append(
                    f"{obj.get('name','?')}: {obj.get('label','?')} ({obj.get('role','?')})"
                    f" @ ({obj['center'][0]:.0f}, {obj['center'][1]:.0f})"
                )
            st.caption(" | ".join(obj_summary))

    # --- Novel side controls (NOR only) ---------------------------------------
    st.markdown("---")
    st.subheader("NOR novel-object assignment")

    nor = pair.nor
    objects = nor.payload.get("objects", [])
    if len(objects) >= 2:
        novel_idx = None
        for i, obj in enumerate(objects):
            if str(obj.get("role") or "").lower() == "novel":
                novel_idx = i
                break
        novel_name = objects[novel_idx]["name"] if novel_idx is not None else "unknown"
        novel_label = objects[novel_idx]["label"] if novel_idx is not None else "?"
        st.write(
            f"Currently novel: **{novel_name}** (label: {novel_label})"
            f" -- object_a={objects[0].get('label')} ({objects[0].get('role')})"
            f", object_b={objects[1].get('label')} ({objects[1].get('role')})"
        )

        swap_cols = st.columns([1, 3])
        with swap_cols[0]:
            do_swap = st.button("Swap novel side", key=f"nqc_swap__{pair.key}", type="primary")
        with swap_cols[1]:
            st.caption("Swaps which object is novel vs familiar in the NOR JSON and saves to disk.")

        if do_swap:
            updated = _swap_novel_side(nor.payload)
            try:
                nor.json_path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n")
                nor.payload.update(updated)
                st.success(f"Swapped novel side and saved: {nor.json_path.name}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save swapped JSON: {e}")
    else:
        st.warning("NOR JSON does not contain 2 objects.")

    # --- Summary table --------------------------------------------------------
    st.markdown("---")
    st.subheader("All pairs: approval status")

    approval_state = st.session_state.get(approval_key, {})
    table_rows = []
    for p in complete_pairs:
        assert p.nof is not None and p.nor is not None
        nor_objects = p.nor.payload.get("objects", [])
        novel_obj = next((o for o in nor_objects if str(o.get("role", "")).lower() == "novel"), None)
        table_rows.append({
            "pair": p.key,
            "subject": p.subject_id,
            "date": p.recording_date,
            "approved": bool(approval_state.get(p.key, False)),
            "novel_obj": f"{novel_obj['name']}: {novel_obj['label']}" if novel_obj else "?",
            "nof_json": p.nof.json_path.name,
            "nor_json": p.nor.json_path.name,
        })
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    n_approved = sum(1 for r in table_rows if r["approved"])
    n_rejected = len(table_rows) - n_approved
    st.caption(f"Approved: {n_approved} | Needs edits: {n_rejected}")

    # --- Bulk approve/reject buttons ------------------------------------------
    bulk_cols = st.columns(3)
    with bulk_cols[0]:
        if st.button("Approve ALL", key="nqc_approve_all"):
            for p in complete_pairs:
                st.session_state.setdefault(approval_key, {})[p.key] = True
            _persist_approval()
            st.rerun()
    with bulk_cols[1]:
        if st.button("Reject ALL", key="nqc_reject_all"):
            for p in complete_pairs:
                st.session_state.setdefault(approval_key, {})[p.key] = False
            _persist_approval()
            st.rerun()

    # --- Export ----------------------------------------------------------------
    st.markdown("---")
    st.subheader("Export")

    export_dir = qc_csv.parent
    approved_csv = export_dir / "nor_nof_training_approved.csv"
    edits_csv = export_dir / "nor_nof_needs_edits.csv"

    if st.button("Export approved + needs-edits CSVs", type="primary", key="nqc_export"):
        approved_rows: List[Dict[str, str]] = []
        edits_rows: List[Dict[str, str]] = []
        for p in complete_pairs:
            assert p.nof is not None and p.nor is not None
            is_approved = bool(approval_state.get(p.key, False))
            for ann in (p.nof, p.nor):
                row = {
                    "video_path": ann.video_path,
                    "task": ann.task,
                    "session_id": ann.session_id,
                    "subject_id": ann.subject_id,
                    "recording_date": ann.recording_date,
                    "crop_xyxy": ",".join(str(x) for x in ann.crop_xyxy),
                    "json_path": str(ann.json_path),
                    "pair_key": p.key,
                }
                if is_approved:
                    approved_rows.append(row)
                else:
                    edits_rows.append(row)

        fieldnames = ["video_path", "task", "session_id", "subject_id", "recording_date", "crop_xyxy", "json_path", "pair_key"]
        for path, data, desc in [
            (approved_csv, approved_rows, "approved"),
            (edits_csv, edits_rows, "needs-edits"),
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(data)
            st.success(f"Wrote {desc}: {path} ({len(data)} rows)")

        st.code(f"Approved:    {approved_csv}\nNeeds edits: {edits_csv}", language=None)
