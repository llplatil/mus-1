"""NOR/NOF Object Association — assign L/R objects + novel side per experiment.

Where the experimenter confirms which physical object is on which side of
the arena and (for NOR) which side is novel, side-by-side with the
linked NOR↔NOF partner so laterality matches across the pair. The pane's
historical name was "Object QC" but it's really an *association* step
(the L/R names + novel-side metadata are the output, not a quality
gate). Downstream visual QC of the actual mark coordinates lives in the
NOR/NOF Interaction QC pane.

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

from ..filters import (
    SCOPE_KEY,
    _cohort_member_ids,
    invalidate_after_write,
    nav_go,
    nav_index,
    pkey,
    render_scope_banner,
)

PANE = "nor_nof_oqc"

# ---------------------------------------------------------------------------
# Canonical object vocabulary
# ---------------------------------------------------------------------------

# Canonical object vocabulary across cohorts:
#   - publication 3D-printed: diamond, pyramid, silo
#   - validation_2026 everyday objects: fish, atom, dino, tube
#   - pilot (P_NO) everyday objects: atom, tube, dino, cap, cap_2, weird_plastic
# When new objects are added (e.g., a future pilot), append them here and add
# any common typos to ``_NORMALIZE_MAP`` below. Names are stored lowercase.
# The per-cohort ``objects`` list (resolved via cohorts.resolve_object_vocabulary)
# narrows what a given experiment's selector shows; this is only the fallback.
# NOTE: ``cap_2`` must precede ``cap`` in substring fallback terms — but exact
# matches in ``_NORMALIZE_MAP`` (auto-added below) resolve first, so order here
# only affects the substring-scan fallback in ``normalize_object_name``.
CANONICAL_OBJECTS = [
    "diamond", "pyramid", "silo",
    "fish", "atom", "dino", "tube",
    "cap_2", "cap", "weird_plastic",
]

_NORMALIZE_MAP: Dict[str, str] = {}
for _canon in CANONICAL_OBJECTS:
    _NORMALIZE_MAP[_canon] = _canon
    _NORMALIZE_MAP[_canon + "s"] = _canon
_NORMALIZE_MAP.update({
    "dimond": "diamond",
    "dimonds": "diamond",
    "pyramind": "pyramid",
    "pryamid": "pyramid",
    "fishy": "fish",        # validation CSV used "Fishy" for fish
    "dinosaur": "dino",     # full word → short
    "dinos": "dino",
    "bottlecap": "cap",     # pilot 4th object variants
    "bottle_cap": "cap",
    "bottle cap": "cap",
    "cap2": "cap_2",        # second, distinct cap (pilot)
    "cap 2": "cap_2",
    "cap_two": "cap_2",
    "weird plastic": "weird_plastic",   # pilot odd object
    "weirdplastic": "weird_plastic",
    "weird": "weird_plastic",
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
    novel_object: Optional[str]
    qc_status: Optional[str]
    qc_reviewed_at: Optional[str]
    qc_notes: str
    frame_count: Optional[int]
    duration_seconds: Optional[float]
    paired_experiment_id: Optional[str]


def bucket_label(project_path: Path, row: "_ExperimentRow") -> str:
    """Display label for an experiment's arena/bucket.

    Prefers the per-experiment ``bucket`` field; otherwise resolves the owning
    cohort's ``canonical_arena`` profile (e.g. the pilot cohort ->
    ``home_depot_5gal_orange``). Returns ``"(not set)"`` when neither is known.
    """
    if row.bucket:
        return row.bucket
    from ..cohorts import resolve_arena_profile_id, arena_profile_label
    pid = resolve_arena_profile_id(project_path, row.experiment_id)
    return arena_profile_label(pid) or "(not set)"


def has_video(row: "_ExperimentRow") -> bool:
    """True if the experiment has a video to read a frame from.

    Cheap, decode-free (does not stat the file) — reflects whether a video was
    ever recorded/linked. Experiments with no video (e.g. pilot NOR whose test
    recording is missing) can never be frame-marked, so panes use this to keep
    them out of marking queues and to render a graceful "no video" state
    instead of a hard stop. A path that is set but unreadable is a *different*
    condition, caught at frame-decode time.
    """
    return bool(row.video_path)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_nor_nof_experiments(experiment_data_root: Path) -> List[_ExperimentRow]:
    """Scan NOR + NOF folders across all configured data roots."""
    from mus1.web.discovery import task_dirs_across_roots

    rows: List[_ExperimentRow] = []
    project_path = Path(experiment_data_root).parent
    for task in ("NOR", "NOF"):
        exp_dirs = task_dirs_across_roots(project_path, task)
        if not exp_dirs:
            task_dir = experiment_data_root / task
            if task_dir.is_dir():
                exp_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())
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
            el = md.get("experiment_level", {})
            vid = data.get("video", {})
            oqc = data.get("object_qc") or {}
            _pair_raw = data.get("nor_nof_pair")
            pair_block = _pair_raw if isinstance(_pair_raw, dict) else {}

            toys_raw = el.get("toys_raw") or el.get("toy_raw") or ""
            # Resolve video.path: pilot/supplementary JSONs store it relative
            # to the project root (e.g. "pilot_data/NOR/.../x.mp4"), whereas
            # publication JSONs store absolute paths. Anchor relatives to the
            # project_path so the frame reader gets a resolvable path
            # regardless of the Streamlit process CWD.
            _video_path = vid.get("path", "")
            if _video_path and not Path(_video_path).is_absolute():
                _video_path = str(project_path / _video_path)
            rows.append(_ExperimentRow(
                experiment_id=data.get("experiment_id", exp_dir.name),
                experiment_type=data.get("experiment_type", task),
                subject_id=str(md.get("subject_id", "")),
                date_recorded=str(md.get("date_recorded", "")),
                video_path=_video_path,
                video_filename=vid.get("filename", ""),
                json_path=jf,
                toys_raw=toys_raw,
                bucket=el.get("bucket", ""),
                object_left=el.get("object_left"),
                object_right=el.get("object_right"),
                novel_side=el.get("novel_side"),
                novel_object=el.get("novel_object"),
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
    """Load key fields from the paired experiment's JSON.

    Searches every configured data root via the multi-root discovery layer
    so validation cohorts (in ``validation_data/``) resolve correctly.
    *experiment_data_root* is retained as the project-path anchor for
    back-compat — its parent is treated as the project_path passed to
    discovery.
    """
    if not paired_eid:
        return None
    from mus1.web.discovery import find_experiment_dir, find_experiment_json

    project_path = Path(experiment_data_root).parent
    exp_dir = find_experiment_dir(project_path, paired_eid)
    pair_json: Optional[Path] = None
    if exp_dir is not None:
        pair_json = find_experiment_json(exp_dir)
    if pair_json is None:
        # Last-resort fallback to the legacy single-root path so callers
        # still using ``data/experiment_data/`` directly keep working.
        parts = paired_eid.split("_", 1)
        task = parts[0] if parts else ""
        legacy = experiment_data_root / task / paired_eid / f"{paired_eid}.json"
        if legacy.exists():
            pair_json = legacy
        else:
            return None
    try:
        data = json.loads(pair_json.read_text())
    except Exception:
        return None
    el = data.get("metadata", {}).get("experiment_level", {})
    oqc = data.get("object_qc") or {}
    task = (data.get("experiment_type")
            or paired_eid.split("_", 1)[0])
    return {
        "experiment_id": paired_eid,
        "experiment_type": task,
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
    novel_object: Optional[str] = None,
    familiar_object: Optional[str] = None,
    experiment_type: str,
    notes: str,
) -> None:
    data = json.loads(json_path.read_text())

    el = data.setdefault("metadata", {}).setdefault("experiment_level", {})
    el["object_left"] = object_left
    el["object_right"] = object_right
    if experiment_type == "NOR":
        el["novel_side"] = novel_side
        # Identities are derived from novel_side by the caller, never entered
        # separately -- a standalone control for them let the two copies of the
        # same fact drift apart. Recompute here as well so a caller that passes
        # neither still writes a consistent record rather than a stale one.
        if novel_side in ("left", "right") and object_left and object_right:
            el["novel_object"] = (
                novel_object or (object_left if novel_side == "left" else object_right)
            )
            el["familiar_object"] = (
                familiar_object or (object_right if novel_side == "left" else object_left)
            )
        else:
            for k in ("novel_object", "familiar_object"):
                if k in el:
                    del el[k]
    else:
        for k in ("novel_side", "novel_object", "familiar_object"):
            if k in el:
                del el[k]

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
    novel_object: Optional[str] = None,
    familiar_object: Optional[str] = None,
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

    # Locate the experiment in whichever data root it actually lives in
    # (experiment_data/, pilot_data/, validation_data/, ...) instead of
    # assuming experiment_data/. row.json_path is the on-disk JSON, so its
    # parent is the experiment folder; fall back to multi-root discovery.
    old_folder = row.json_path.parent
    if not old_folder.is_dir():
        from mus1.web.discovery import find_experiment_dir
        located = find_experiment_dir(Path(experiment_data_root).parent, old_id)
        if located:
            old_folder = located
    # Keep the experiment in the same data root; only the task subdir changes.
    new_task_dir = old_folder.parent.parent / new_type
    new_folder = new_task_dir / new_id

    if new_folder.exists():
        return f"Target folder already exists: {new_folder}"
    if not old_folder.exists():
        return f"Source folder not found: {old_folder}"

    new_task_dir.mkdir(parents=True, exist_ok=True)

    shutil.move(str(old_folder), str(new_folder))

    old_json = new_folder / row.json_path.name
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
        # Same derivation as _save_qc_to_json: identities follow from novel_side.
        if novel_side in ("left", "right") and object_left and object_right:
            el["novel_object"] = (
                novel_object or (object_left if novel_side == "left" else object_right)
            )
            el["familiar_object"] = (
                familiar_object or (object_right if novel_side == "left" else object_left)
            )
        else:
            for k in ("novel_object", "familiar_object"):
                if k in el:
                    del el[k]
        if "toy_raw" in el:
            el["toys_raw"] = el.pop("toy_raw")
    else:
        for k in ("novel_side", "novel_object", "familiar_object"):
            if k in el:
                del el[k]
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
    _old_pair_raw = data.get("nor_nof_pair")
    old_pair = _old_pair_raw if isinstance(_old_pair_raw, dict) else {}
    old_paired_eid = old_pair.get("paired_experiment_id")
    # After type flip, the new experiment pairs with the opposite task
    opposite_task = "NOF" if new_type == "NOR" else "NOR"
    data["nor_nof_pair"] = {
        "paired_experiment_id": old_paired_eid,
        "paired_experiment_type": opposite_task,
    }

    # Update the former pair's reference to point to the new experiment id.
    # Resolve through multi-root discovery so validation pairs in
    # ``validation_data/`` are also located.
    if old_paired_eid:
        from mus1.web.discovery import find_experiment_dir, find_experiment_json

        project_path = Path(experiment_data_root).parent
        partner_dir = find_experiment_dir(project_path, old_paired_eid)
        pair_json: Optional[Path] = (
            find_experiment_json(partner_dir) if partner_dir else None
        )
        if pair_json is None:
            # Legacy single-root fallback
            old_pair_parts = old_paired_eid.split("_", 1)
            if len(old_pair_parts) >= 2:
                legacy = (experiment_data_root / old_pair_parts[0]
                          / old_paired_eid / f"{old_paired_eid}.json")
                if legacy.exists():
                    pair_json = legacy
        if pair_json is not None:
            try:
                pair_data = json.loads(pair_json.read_text())
                pair_data["nor_nof_pair"] = {
                    "paired_experiment_id": new_id,
                    "paired_experiment_type": new_type,
                }
                pair_json.write_text(
                    json.dumps(pair_data, indent=2, default=str) + "\n"
                )
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
    st.header("NOR/NOF Object Association")
    st.caption(
        "Confirm L/R object names + novel side; view the linked NOR↔NOF "
        "partner side-by-side to verify laterality matches across the pair."
    )
    st.caption("Review object assignments per experiment. Edits write directly to JSON; DB syncs separately.")
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
    # (see web/filters.py). Task / un-QC'd / sort are pane-specific
    # primary controls and stay in the main area for ergonomics.
    fcol1, fcol2, fcol3 = st.columns([1, 1, 2])
    with fcol1:
        task_filter = st.radio(
            "Task", ["Both", "NOR", "NOF"], horizontal=True,
            key=pkey(PANE, "task"),
        )
    with fcol2:
        only_unreviewed = st.checkbox(
            "Only un-QC'd", value=True, key=pkey(PANE, "unreviewed"),
        )
    with fcol3:
        sort_by = st.selectbox(
            "Sort by",
            ["subject_id", "date_recorded", "experiment_id"],
            key=pkey(PANE, "sort"),
        )

    filtered = all_rows
    # Apply universal cohort scope
    scope_cohort = st.session_state.get(SCOPE_KEY)
    if scope_cohort:
        member_ids = _cohort_member_ids(project_path, scope_cohort)
        filtered = [r for r in filtered if r.experiment_id in member_ids]

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

    # --- Navigation (index selector + Prev/Next; single source of truth) ---
    nidx, nprev, nnext = st.columns([3, 1, 1])
    with nidx:
        idx = nav_index(PANE, len(filtered))
    with nprev:
        if st.button("◀ Prev", key="oqc_prev", width="stretch", disabled=idx <= 0):
            nav_go(PANE, -1)
    with nnext:
        if st.button("Next ▶", key="oqc_next", width="stretch",
                     disabled=idx >= len(filtered) - 1):
            nav_go(PANE, +1)

    row = filtered[idx]

    # --- Header ---
    st.subheader(row.experiment_id)
    st.caption(
        f"Subject: {row.subject_id} | Date: {row.date_recorded} | "
        f"Type: {row.experiment_type} | Bucket: {bucket_label(project_path, row)}"
    )

    # --- Frame display + current state side by side ---
    col_frame, col_info = st.columns([2, 1])

    with col_frame:
        frame = _read_mid_frame(row.video_path, row.frame_count) if has_video(row) else None
        if frame is not None:
            st.image(frame, caption=f"Mid-frame: {row.video_filename}", width="stretch")
        elif not has_video(row):
            # No video ever recorded (e.g. pilot NOR with a missing test video).
            # Object *names* don't require the frame — they can be assigned from
            # the linked partner + design — so guide rather than just warn.
            st.info(
                "**No video for this experiment.** You can still assign object "
                "names below from the linked NOR↔NOF partner + protocol, then "
                "click **Confirm QC** — the frame isn't needed for name assignment."
            )
        else:
            st.warning(
                f"Could not read a frame from: {row.video_path} "
                "(file missing or unreadable). Object names can still be assigned below."
            )

    with col_info:
        st.markdown("**Current state in JSON**")
        st.text(f"toys_raw:     {row.toys_raw}")
        st.text(f"object_left:  {row.object_left or '(not set)'}")
        st.text(f"object_right: {row.object_right or '(not set)'}")
        st.text(f"novel_side:   {row.novel_side or '(not set)'}")
        st.text(f"novel_object: {row.novel_object or '(not set)'}")
        st.text(f"bucket:       {bucket_label(project_path, row)}")
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

    # Object vocabulary: prefer the union of objects[] from every cohort
    # this experiment belongs to (data-driven). Fall back to the global
    # CANONICAL_OBJECTS for legacy experiments not in any object-aware cohort.
    from ..cohorts import resolve_object_vocabulary, resolve_no_protocol
    cohort_vocab = resolve_object_vocabulary(
        project_path, row.experiment_id, fallback=CANONICAL_OBJECTS,
    )
    # Novel-object familiarization protocol for this experiment's cohort.
    no_protocol = resolve_no_protocol(project_path, row.experiment_id)
    _is_distinct = no_protocol == "distinct_pair_familiarization"
    if _is_distinct:
        st.caption(
            "Protocol: **distinct-pair familiarization** — sample phase (NOF) uses "
            "two *different* objects; the test (NOR) swaps one for a novel object."
        )
    else:
        st.caption(
            "Protocol: **identical familiarization** — sample phase (NOF) uses two "
            "*identical* objects; the test (NOR) swaps one for a novel object."
        )
    # If the experiment already has names assigned, ensure they appear in the
    # selector even if the cohort vocab doesn't list them yet (so we don't
    # silently force "(other)" on already-marked experiments).
    for existing in (row.object_left, row.object_right):
        if existing and existing not in cohort_vocab:
            cohort_vocab = list(cohort_vocab) + [existing]
    obj_options = cohort_vocab + ["(other)"]

    def _default_idx(val: Optional[str], options: List[str]) -> Optional[int]:
        """Index of ``val`` in ``options``, or ``None`` to leave the widget unset.

        This used to return 0 when ``val`` was empty or unrecognised, which
        silently pre-selected the first entry of the cohort vocabulary --
        ``atom`` for the pilot. An operator who reviewed a frame and pressed
        Save then wrote an object they never chose. Returning ``None`` makes
        "not set" representable, and the save guard below refuses to write it.
        """
        if val and val in options:
            return options.index(val)
        return None

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
            placeholder="— not set —",
            key=f"oqc_left__{row.experiment_id}",
        )
        if left_sel == "(other)":
            left_sel = st.text_input("Left object name", value=default_left, key=f"oqc_left_other__{row.experiment_id}")

    with ecol2:
        right_sel = st.selectbox(
            "Object RIGHT",
            options=obj_options,
            index=_default_idx(default_right, obj_options),
            placeholder="— not set —",
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
            # No default. Falling back to "left" for unset experiments made
            # "left" the recorded answer wherever the operator did not actively
            # choose: the pilot reads 47 left / 3 right (binomial p ~ 4e-11
            # against a counterbalanced design), which is a UI artifact rather
            # than data. An unset novel side must stay visibly unset.
            _stored_side = row.novel_side if row.novel_side in ("left", "right") else None
            novel_side_sel = st.radio(
                "Novel side",
                ["left", "right"],
                index=["left", "right"].index(_stored_side) if _stored_side else None,
                horizontal=True,
                key=f"oqc_novel__{row.experiment_id}",
            )
        elif _is_distinct:
            st.caption("NOF sample: two *distinct* objects (no novel side).")
        else:
            st.caption("NOF sample: two *identical* objects (no novel side).")

    # Novel-object identity (NOR only) is DERIVED, never entered.
    #
    # It is fully determined by novel_side plus the two object slots: the novel
    # object is whatever sits on the novel side, under both protocols. Offering a
    # separate control for it meant the same fact was entered twice and the two
    # copies could disagree -- which is exactly what happened. Across the pilot
    # the standalone dropdown wrote the FAMILIAR object into novel_object on
    # roughly half the NOR records, and in validation novel_object/familiar_object
    # ended up swapped on 4 of 12. One fact, one input.
    novel_object_sel: Optional[str] = None
    familiar_object_sel: Optional[str] = None
    if exp_type_sel == "NOR" and novel_side_sel and left_sel and right_sel:
        novel_object_sel = left_sel if novel_side_sel == "left" else right_sel
        familiar_object_sel = right_sel if novel_side_sel == "left" else left_sel
        st.markdown(
            f"Novel object: **{novel_object_sel}** &nbsp;·&nbsp; "
            f"familiar: **{familiar_object_sel}** &nbsp;"
            f"<span style='opacity:0.6'>(derived from novel side)</span>",
            unsafe_allow_html=True,
        )
        # Independent cross-check: under either protocol the novel object is the
        # one absent from the paired sample session, so the NOF partner arbitrates
        # without reference to novel_side. This is the OA1 rule (WORKLOG.md), and
        # it is the check that caught every defect the standalone dropdown caused.
        _partner = next(
            (r for r in all_rows if r.experiment_id == row.paired_experiment_id),
            None,
        ) if row.paired_experiment_id else None
        _partner_objs = (
            {o for o in (_partner.object_left, _partner.object_right) if o}
            if _partner else set()
        )
        if _partner_objs:
            _diff = {left_sel, right_sel} - _partner_objs
            if len(_diff) == 1 and next(iter(_diff)) != novel_object_sel:
                st.warning(
                    f"**Novel side disagrees with the paired sample session.** "
                    f"The sample ({row.paired_experiment_id}) used "
                    f"{sorted(_partner_objs)}, so the object swapped in for the test "
                    f"is **{next(iter(_diff))}** — but novel side *{novel_side_sel}* "
                    f"holds **{novel_object_sel}**. Check the video before saving."
                )
            elif len(_diff) != 1:
                st.warning(
                    f"**Cannot derive the novel object from the pair.** Test objects "
                    f"{sorted({left_sel, right_sel})} vs sample {sorted(_partner_objs)} "
                    f"leave {sorted(_diff) or 'no'} object(s) unaccounted for. Either a "
                    f"label is wrong or the two sessions are not a valid pair."
                )

    # Protocol-aware sanity hint on the two sample objects (NOF only).
    if exp_type_sel == "NOF" and left_sel and right_sel and left_sel != "(other)":
        if not _is_distinct and left_sel != right_sel:
            st.warning(
                "Identical-familiarization protocol expects the **same** object on "
                "both sides during the sample phase, but LEFT and RIGHT differ."
            )
        if _is_distinct and left_sel == right_sel:
            st.warning(
                "Distinct-pair protocol expects **two different** objects during the "
                "sample phase, but LEFT and RIGHT are the same."
            )

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

    # Nothing may be written that the operator did not actively choose. The
    # widgets above now return None when unset, so refuse the save rather than
    # persisting a None (or a silently defaulted value) into experiment_level.
    _missing: List[str] = []
    if not left_sel:
        _missing.append("Object LEFT")
    if not right_sel:
        _missing.append("Object RIGHT")
    if exp_type_sel == "NOR" and not novel_side_sel:
        _missing.append("Novel side")
    # ``novel_object``/``familiar_object`` are not listed here: they are derived
    # above from novel_side, so requiring them would be requiring novel_side twice.
    if _missing:
        st.info("Set " + ", ".join(_missing) + " to enable saving.")

    if st.button(
        "Confirm QC",
        type="primary",
        key=f"oqc_save__{row.experiment_id}",
        disabled=not confirm_type_change or bool(_missing),
    ):
        if type_changed:
            err = _change_experiment_type(
                experiment_data_root=experiment_data_root,
                row=row,
                new_type=exp_type_sel,
                object_left=left_sel,
                object_right=right_sel,
                novel_side=novel_side_sel,
                novel_object=novel_object_sel,
                familiar_object=familiar_object_sel,
                notes=notes_val,
            )
            if err:
                st.error(f"Type change failed: {err}")
            else:
                st.success(f"Type changed and QC saved: {row.experiment_id} -> {exp_type_sel}")
                _read_mid_frame.clear()
                nav_go(PANE, +1)
        else:
            _save_qc_to_json(
                row.json_path,
                object_left=left_sel,
                object_right=right_sel,
                novel_side=novel_side_sel,
                novel_object=novel_object_sel,
                familiar_object=familiar_object_sel,
                experiment_type=exp_type_sel,
                notes=notes_val,
            )
            st.success(f"QC saved for {row.experiment_id}")
            nav_go(PANE, +1)

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
