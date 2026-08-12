"""Arena Inference QC — profile-parameterized review of U-Net predictions.

T9 (ROADMAP Iteration 6b). Replaces the "Validation Inference Preview"
section of the legacy EZM ML pane with a first-class QC contract:

  - One profile per render (selectbox at top sourced from the arena
    profile registry).
  - One experiment per render via the standard navigation cluster.
  - Predicted overlay drawn from ``arena_markings.predicted.<key>`` where
    ``<key>`` is the active model's ``mask_to_marking`` post-processor
    name (``ezm_wedge_points`` today; ``circular_arena_boundary`` once a
    NOR/NOF arena U-Net is trained).
  - QC writeback at ``arena_markings.predicted.<key>.qc`` with a pinned
    ``model_run_id`` so historical reviews stay anchored to the model
    they were performed against (activation discipline confirmed by
    user 2026-05-07).

Empty states are graceful:

  - No active model for the selected profile → instructions to activate
    one via ``mus1 arena-models activate``.
  - Model is active but no experiments have predictions yet → instructions
    to run ``mus1 ezm-arena-inference`` (or the generic equivalent once
    T11 ships).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from ..ezm_qc_shared import (
    build_zone_payload_from_wedge_points,
    load_frame_rgb,
    resolve_path,
)
from ..ezm_trajectory_overlay import draw_ezm_qc_overlay
from ..filters import (
    invalidate_after_write,
    mode_settings,
    nav_go,
    nav_index,
    pkey,
    render_scope_banner,
)
from ..discovery import CACHE_TTL_SECONDS, iter_experiment_dirs, find_experiment_json


PANE = "arena_inference_qc"
_STATUS_OPTIONS = [
    "(not reviewed)",
    "keep",
    "promote_to_manual",
    "re_train",
    "disagree_visual_only",
]


# ---------------------------------------------------------------------------
# Registry helpers (cached so YAML is read once per render)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _arena_profile_registry(project_path_str: str):
    from mus1.arena_profiles.registry import ArenaProfileRegistry
    return ArenaProfileRegistry.from_config(Path(project_path_str))


@st.cache_resource(show_spinner=False)
def _arena_model_registry(project_path_str: str):
    from mus1.compute.arena_models import ArenaModelRegistry
    return ArenaModelRegistry.load(Path(project_path_str))


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def _discover_predicted_for_profile(
    project_path_str: str,
    profile_id: str,
    prediction_key: str,
) -> List[Dict[str, Any]]:
    """Scan every data root and return rows for experiments whose JSON has
    a ``arena_markings.predicted.<prediction_key>`` block AND whose
    ``arena_markings.arena_profile.profile_id`` matches *profile_id*.

    Each row is a minimal summary for the navigation table:
    ``{experiment_id, json_path, video_path, has_gt, qc_status,
       qc_reviewed_at, model_run_id, predicted_at}``.
    """
    project_path = Path(project_path_str)
    rows: List[Dict[str, Any]] = []
    for root, task, exp_dir in iter_experiment_dirs(project_path):
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue
        am = data.get("arena_markings") or {}
        ap = am.get("arena_profile") or {}
        if ap.get("profile_id") != profile_id:
            continue
        pred_root = am.get("predicted") or {}
        pred = pred_root.get(prediction_key) or {}
        if not pred:
            continue
        qc = pred.get("qc") or {}
        # Ground truth presence depends on the prediction key
        if prediction_key == "ezm_wedge_points":
            gt_points = (am.get("ezm_wedge_points") or {}).get("points") or []
            has_gt = len(gt_points) == 4
        elif prediction_key == "circular_arena_boundary":
            gt = am.get("arena_boundary") or {}
            has_gt = bool(gt.get("ellipse") or gt.get("diameter_px"))
        else:
            has_gt = False
        rows.append({
            "experiment_id": exp_dir.name,
            "task_type": task,
            "json_path": str(jp),
            "video_path": (data.get("video") or {}).get("path", ""),
            "has_gt": has_gt,
            "qc_status": qc.get("status", ""),
            "qc_reviewed_at": qc.get("reviewed_at", ""),
            "qc_model_run_id": qc.get("model_run_id", ""),
            "predicted_at": pred.get("predicted_at", ""),
            "pinned_model_run_id": pred.get("model_run_id", "")
            or pred.get("model_version", ""),
            "n_frames_sampled": pred.get("n_frames_sampled", 0),
        })
    rows.sort(key=lambda r: r["experiment_id"])
    return rows


# ---------------------------------------------------------------------------
# Per-profile renderers (one per mask_to_marking key)
# ---------------------------------------------------------------------------

def _render_ezm_wedge_points(
    *, frame_rgb, exp_data: Dict[str, Any], invert_open_closed: bool,
) -> Optional[Dict[str, Any]]:
    """Draw GT + predicted overlays for EZM. Returns a diagnostics dict
    for the right-hand column to render."""
    am = exp_data.get("arena_markings") or {}
    gt_pts = (am.get("ezm_wedge_points") or {}).get("points") or []
    pred = (am.get("predicted") or {}).get("ezm_wedge_points") or {}
    pred_pts = pred.get("points") or []

    diag: Dict[str, Any] = {
        "predicted_at": pred.get("predicted_at", ""),
        "model_version": pred.get("model_version", ""),
        "model_run_id": pred.get("model_run_id", "")
        or pred.get("model_version", ""),
        "quality": pred.get("quality") or {},
        "n_frames_sampled": pred.get("n_frames_sampled", 0),
    }

    # GT overlay
    if len(gt_pts) == 4:
        zone_gt, _w = build_zone_payload_from_wedge_points(gt_pts, frame_rgb.shape)
        try:
            gt_img = draw_ezm_qc_overlay(
                frame_rgb, zone_gt, {}, "head",
                show_trajectory=False, show_legend=False,
                invert_open_closed=invert_open_closed,
            )
            st.image(gt_img, caption="Ground truth (manual wedge points)",
                     use_container_width=True)
        except Exception as e:
            st.warning(f"GT overlay render failed: {e}")
    else:
        st.info(f"No GT wedge points yet ({len(gt_pts)}/4).")

    # Predicted overlay
    if len(pred_pts) == 4:
        zone_pred, _w = build_zone_payload_from_wedge_points(pred_pts, frame_rgb.shape)
        try:
            pred_img = draw_ezm_qc_overlay(
                frame_rgb, zone_pred, {}, "head",
                show_trajectory=False, show_legend=False,
                invert_open_closed=invert_open_closed,
            )
            st.image(pred_img, caption="Predicted (U-Net auto-suggest)",
                     use_container_width=True)
        except Exception as e:
            st.warning(f"Predicted overlay render failed: {e}")

    # Per-point displacement (manual ↔ predicted)
    if len(gt_pts) == 4 and len(pred_pts) == 4:
        disps = []
        for (mx, my), (px, py) in zip(gt_pts, pred_pts):
            dx = float(px) - float(mx)
            dy = float(py) - float(my)
            disps.append((dx * dx + dy * dy) ** 0.5)
        diag["displacement_px"] = {
            "min": min(disps),
            "mean": sum(disps) / 4.0,
            "max": max(disps),
            "per_point": disps,
        }

    return diag


# Dispatch table: prediction_key -> renderer
_RENDERERS = {
    "ezm_wedge_points": _render_ezm_wedge_points,
}


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_arena_inference_qc(*, workspace_root: Optional[str],
                              project_path: Path) -> None:
    st.header("Arena Inference QC")
    st.caption(
        "Review U-Net arena predictions for any registered arena profile "
        "and pin reviews to the model run_id they were performed against."
    )
    render_scope_banner()

    if st.button("Refresh (clear cache)", key=pkey(PANE, "refresh")):
        invalidate_after_write()
        st.rerun()

    profiles = _arena_profile_registry(str(project_path))
    models = _arena_model_registry(str(project_path))

    # ── Profile selector ─────────────────────────────────────────────
    profile_ids = profiles.list_ids()
    if not profile_ids:
        st.warning("No arena profiles registered.")
        st.stop()
    active_ids = models.list_profiles()
    default_idx = 0
    for i, pid in enumerate(profile_ids):
        if pid in active_ids:
            default_idx = i
            break
    profile_id = st.selectbox(
        "Arena profile",
        options=profile_ids,
        format_func=lambda pid: (
            f"{pid}  •  {'✓ model active' if pid in active_ids else 'no active model'}"
        ),
        index=default_idx,
        key=pkey(PANE, "profile"),
    )
    profile = profiles.get_or_none(profile_id)
    entry = models.get(profile_id)

    if entry is None:
        st.info(
            f"No active U-Net for `{profile_id}`. Activate one via:\n\n"
            f"```\nmus1 arena-models activate {profile_id} <run_id> --checkpoint <path> "
            f"--mask-to-marking <key>\n```"
        )
        st.stop()

    prediction_key = entry.mask_to_marking or ""
    if not prediction_key:
        st.warning(
            f"Active model for `{profile_id}` has no `mask_to_marking` key set. "
            "Edit `arena_models.yaml` and re-run `mus1 arena-models activate ...` "
            "with `--mask-to-marking <key>`."
        )
        st.stop()
    renderer = _RENDERERS.get(prediction_key)
    if renderer is None:
        st.warning(
            f"No renderer wired for `mask_to_marking={prediction_key}` yet. "
            f"Available: {list(_RENDERERS.keys())}. Add one in "
            f"`web/views/arena_inference_qc.py:_RENDERERS`."
        )
        st.stop()

    st.caption(
        f"Active model: `{entry.run_id}` "
        f"({entry.n_classes} classes, post-proc=`{prediction_key}`). "
        f"Checkpoint: `{entry.checkpoint}` "
        f"{'✓' if entry.checkpoint.is_file() else '✗ (missing on disk)'}"
    )

    # ── Discover experiments with predictions for this profile ──────
    rows = _discover_predicted_for_profile(
        str(project_path), profile_id, prediction_key,
    )
    if not rows:
        st.info(
            f"No experiments have `arena_markings.predicted.{prediction_key}` "
            f"set for profile `{profile_id}`. Run inference first, e.g.:\n\n"
            f"```\nmus1 ezm-arena-inference --cohort <cohort_name>\n```"
        )
        st.stop()

    # ── Sidebar filters ──────────────────────────────────────────────
    st.sidebar.markdown("**Filters**")
    show_only_unreviewed = st.sidebar.checkbox(
        "Show only unreviewed", value=True, key=pkey(PANE, "only_unrev"),
    )
    require_gt = st.sidebar.checkbox(
        "Require GT present (skip predict-only)", value=False,
        key=pkey(PANE, "require_gt"),
    )
    filtered = rows
    if show_only_unreviewed:
        filtered = [r for r in filtered if r["qc_status"] in ("", "(not reviewed)")]
    if require_gt:
        filtered = [r for r in filtered if r["has_gt"]]

    st.caption(
        f"{len(rows)} experiments with predictions; "
        f"{sum(1 for r in rows if r['qc_status'] not in ('', '(not reviewed)'))} reviewed."
    )

    if not filtered:
        st.info("No experiments match current filters.")
        st.stop()

    # ── Display settings ─────────────────────────────────────────────
    with mode_settings("Display", key_prefix=PANE):
        invert_open_closed = st.checkbox(
            "Invert open/closed (EZM only)",
            value=False, key=pkey(PANE, "invert"),
        )
        mid_frame_idx = st.number_input(
            "Frame index", min_value=0, value=2100, step=300,
            key=pkey(PANE, "frame_idx"),
        )

    # ── Navigation (index selector + Prev/Next; single source of truth) ──
    n = len(filtered)
    col_idx, col_prev, col_next, col_count = st.columns([2, 1, 1, 2])
    with col_idx:
        idx = nav_index(PANE, n)
    with col_prev:
        if st.button("◀ Prev", key=pkey(PANE, "prev"), width="stretch", disabled=idx <= 0):
            nav_go(PANE, -1)
    with col_next:
        if st.button("Next ▶", key=pkey(PANE, "next"), width="stretch", disabled=idx >= n - 1):
            nav_go(PANE, +1)
    with col_count:
        st.markdown(f"**{idx + 1} / {n}** experiments")
    st.progress((idx + 1) / n)

    rec = filtered[idx]
    exp_id = rec["experiment_id"]
    exp_json_path = Path(rec["json_path"])
    exp_data = json.loads(exp_json_path.read_text())
    st.subheader(exp_id)

    # ── Load video frame ─────────────────────────────────────────────
    vpath = resolve_path(rec.get("video_path", ""))
    if vpath is None or not vpath.exists():
        st.error(f"Video not found: {rec.get('video_path', '')}")
        st.stop()
    frame_rgb = load_frame_rgb(str(vpath), int(mid_frame_idx))
    if frame_rgb is None:
        frame_rgb = load_frame_rgb(str(vpath), 0)
    if frame_rgb is None:
        st.error("Could not load video frame.")
        st.stop()

    # ── Render overlays + collect diagnostics ────────────────────────
    diag = renderer(
        frame_rgb=frame_rgb, exp_data=exp_data,
        invert_open_closed=bool(invert_open_closed),
    ) or {}

    # ── Right column: pinned-model warning + diagnostics ─────────────
    pinned = rec.get("pinned_model_run_id", "")
    current = entry.run_id
    if pinned and current and pinned != current and not pinned.startswith(current):
        st.warning(
            f"Predictions were generated by `{pinned}`; the current active "
            f"model is `{current}`. The QC review will pin the prediction's "
            "model run_id, not the current one. Re-run inference to refresh."
        )

    quality = diag.get("quality") or {}
    info_rows = [
        ("Predicted at", str(diag.get("predicted_at", ""))[:19]),
        ("Pinned model", pinned or "(none)"),
        ("Active model", current),
        ("n_frames_sampled", str(diag.get("n_frames_sampled", ""))),
    ]
    if "open_pixel_fraction" in quality:
        info_rows.append(("open_pixel_frac", f"{quality['open_pixel_fraction']:.3f}"))
    if "closed_pixel_fraction" in quality:
        info_rows.append(("closed_pixel_frac", f"{quality['closed_pixel_fraction']:.3f}"))
    if "n_open_components" in quality:
        info_rows.append(("n_open_components", str(quality["n_open_components"])))
    disp = diag.get("displacement_px")
    if disp:
        info_rows.append(("Manual↔pred (px)",
                          f"min={disp['min']:.1f} / mean={disp['mean']:.1f} / max={disp['max']:.1f}"))

    st.markdown("**Diagnostics**")
    st.dataframe(
        pd.DataFrame(info_rows, columns=["Field", "Value"]),
        hide_index=True, use_container_width=True,
    )

    # ── QC review block ──────────────────────────────────────────────
    st.markdown("---")
    pred_block = ((exp_data.get("arena_markings") or {})
                  .get("predicted") or {}).get(prediction_key) or {}
    qc_existing = pred_block.get("qc") or {}
    existing_status = qc_existing.get("status", "")
    existing_notes = qc_existing.get("notes", "")

    st.markdown("**Inference QC Review**")
    if qc_existing.get("reviewed_at"):
        st.caption(
            f"Last reviewed: {qc_existing['reviewed_at'][:19]} "
            f"(pinned to model_run_id=`{qc_existing.get('model_run_id', '')}`)"
        )

    k_status = pkey(PANE, f"status__{exp_id}")
    if k_status not in st.session_state:
        st.session_state[k_status] = (
            existing_status if existing_status in _STATUS_OPTIONS else "(not reviewed)"
        )
    qc_status = st.radio(
        "Status", options=_STATUS_OPTIONS, horizontal=True, key=k_status,
    )

    k_notes = pkey(PANE, f"notes__{exp_id}")
    if k_notes not in st.session_state:
        st.session_state[k_notes] = existing_notes
    qc_notes = st.text_area(
        "Notes",
        placeholder="e.g., open arms swapped; predictions tight; needs more training data",
        key=k_notes, height=80, label_visibility="collapsed",
    )

    col_save, col_promote = st.columns([1, 1])
    with col_save:
        if st.button("Save & next", key=pkey(PANE, f"save__{exp_id}"),
                     type="primary"):
            _save_qc(
                exp_json_path=exp_json_path,
                prediction_key=prediction_key,
                status=qc_status if qc_status != "(not reviewed)" else "",
                notes=qc_notes.strip(),
                model_run_id=diag.get("model_run_id", "") or current,
            )
            invalidate_after_write()
            if idx + 1 < n:
                st.toast("Saved. Advanced to next.")
                nav_go(PANE, +1)
            else:
                st.toast("Saved. Review complete.")
            st.rerun()
    with col_promote:
        if st.button(
            "Promote predicted → manual",
            key=pkey(PANE, f"promote__{exp_id}"),
            disabled=(prediction_key != "ezm_wedge_points"),
            help="Copy predicted points into the manual GT slot (EZM only).",
        ):
            _promote_to_manual(exp_json_path, prediction_key)
            _save_qc(
                exp_json_path=exp_json_path,
                prediction_key=prediction_key,
                status="promote_to_manual",
                notes=qc_notes.strip(),
                model_run_id=diag.get("model_run_id", "") or current,
            )
            invalidate_after_write()
            st.toast("Promoted to manual.")
            st.rerun()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _save_qc(
    *, exp_json_path: Path, prediction_key: str,
    status: str, notes: str, model_run_id: str,
) -> None:
    """Persist the inference QC block, pinning the model_run_id."""
    data = json.loads(exp_json_path.read_text())
    am = data.setdefault("arena_markings", {})
    pred = am.setdefault("predicted", {})
    block = pred.setdefault(prediction_key, {})
    block["qc"] = {
        "status": status,
        "notes": notes,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "model_run_id": model_run_id,
    }
    exp_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _promote_to_manual(exp_json_path: Path, prediction_key: str) -> None:
    """For EZM: copy predicted wedge points into the manual GT slot."""
    if prediction_key != "ezm_wedge_points":
        return
    data = json.loads(exp_json_path.read_text())
    am = data.setdefault("arena_markings", {})
    pred = (am.get("predicted") or {}).get(prediction_key) or {}
    pts = pred.get("points") or []
    if len(pts) != 4:
        return
    manual = am.setdefault("ezm_wedge_points", {})
    manual["points"] = pts
    prov = manual.setdefault("provenance", {})
    prov["method"] = "unet_suggested+promoted"
    prov["model_run_id"] = pred.get("model_run_id", "") or pred.get("model_version", "")
    prov["promoted_at"] = datetime.now(timezone.utc).isoformat()
    exp_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
