"""EZM Zones QC — arena marking review (wedge-point circle fit).

Per-experiment review of the circle-fit arena overlay derived from 4 wedge
border points.  Arena geometry only — metrics computation and tracking QC
live in the separate EZM Tracking QC pane.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from ..ezm_qc_shared import (
    build_zone_payload_from_wedge_points,
    load_ezm_experiments,
    load_frame_rgb,
    resolve_path,
    LOCKED_LH_THRESHOLD,
)
from ..ezm_trajectory_overlay import draw_ezm_qc_overlay, load_dlc_tracks
from ..filters import invalidate_after_write, mode_settings, pkey, render_filters


PANE = "ezm_zones"
_STATUS_OPTIONS = ["(not reviewed)", "keep", "re_mark", "exclude"]


def render_ezm_zones_qc(*, workspace_root: Optional[str], project_path: Path) -> None:
    st.header("EZM Zones QC")
    st.caption("Review arena circle fit from wedge point markings.")

    if st.button("Refresh (clear cache)", key=pkey(PANE, "refresh")):
        invalidate_after_write()
        st.rerun()

    if not workspace_root:
        st.error("This view requires `--workspace-root`.")
        st.stop()
    experiment_data_root = project_path / "experiment_data"

    # ── Discover experiments ──────────────────────────────────────────
    all_rows = load_ezm_experiments(str(experiment_data_root))
    n_total = len(all_rows)
    n_with_wedge = sum(1 for r in all_rows if r["has_wedge_points"])

    if n_total == 0:
        st.info(f"No EZM experiment folders found under `{experiment_data_root / 'EZM'}`.")
        st.stop()

    # ── Universal Filters block (cohort scope read from session_state) ──
    state, filtered = render_filters(
        rows=all_rows,
        fields={"marking_status", "qc_statuses", "genotypes", "sexes", "text"},
        key_prefix=PANE,
        marking_field="has_wedge_points",
        qc_field="arena_qc_status",
        project_path=project_path,
    )

    # ── Pane-specific Display settings ───────────────────────────────
    with mode_settings("Display", key_prefix=PANE):
        show_trajectory = st.checkbox(
            "Show trajectory", value=True, key=pkey(PANE, "show_traj"),
        )

    st.caption(f"{n_with_wedge} of {n_total} EZM experiments have wedge points marked.")

    if not filtered:
        st.info("No experiments match current filters.")
        st.stop()

    # ── Navigation ────────────────────────────────────────────────────
    n = len(filtered)
    idx_state_key = pkey(PANE, "idx")
    if idx_state_key not in st.session_state:
        st.session_state[idx_state_key] = 0
    idx = max(0, min(int(st.session_state[idx_state_key]), n - 1))

    col_prev, col_idx, col_next, col_count = st.columns([1, 2, 1, 2])
    with col_prev:
        if st.button("Prev", key=pkey(PANE, "prev"), disabled=idx <= 0):
            st.session_state[idx_state_key] = idx - 1
            st.rerun()
    with col_next:
        if st.button("Next", key=pkey(PANE, "next"), disabled=idx >= n - 1):
            st.session_state[idx_state_key] = idx + 1
            st.rerun()
    with col_idx:
        new_idx = st.number_input(
            "Index", min_value=0, max_value=n - 1, value=idx, step=1,
            key=pkey(PANE, "idx_input"),
        )
        if int(new_idx) != idx:
            idx = int(new_idx)
            st.session_state[idx_state_key] = idx
    with col_count:
        st.markdown(f"**{idx + 1} / {n}** experiments")

    rec = filtered[idx]
    exp_id = rec["experiment_id"]
    exp_json_path = Path(rec["json_path"])
    exp_data = json.loads(exp_json_path.read_text())

    st.subheader(exp_id)

    # ── Resolve video ─────────────────────────────────────────────────
    video_path = resolve_path(rec.get("video_path", ""))
    dlc_csv_path = resolve_path(rec.get("dlc_csv_path", ""))

    if video_path is None or not video_path.exists():
        st.error(f"Video not found: {rec.get('video_path', '')}")
        st.stop()

    # ── Load frame ────────────────────────────────────────────────────
    mid_frame_idx = 2100  # ~35s at 60fps
    frame_rgb = load_frame_rgb(str(video_path), mid_frame_idx)
    if frame_rgb is None:
        frame_rgb = load_frame_rgb(str(video_path), 0)
    if frame_rgb is None:
        st.error("Could not load video frame.")
        st.stop()

    # ── Build zone payload from wedge points ─────────────────────────
    am = exp_data.get("arena_markings") or {}
    wp = (am.get("ezm_wedge_points") or {}).get("points") or []
    zone_payload, fit_warning = build_zone_payload_from_wedge_points(wp, frame_rgb.shape)

    if zone_payload is None and len(wp) != 4:
        st.info(
            f"No wedge points for this experiment "
            f"({len(wp)}/4 found). Mark in Annotator → EZM: mark wedge points."
        )
    if fit_warning:
        st.warning(fit_warning)

    # Predicted (UNet auto-suggest) block
    predicted_block = (am.get("predicted") or {}).get("ezm_wedge_points") or {}
    pred_points = predicted_block.get("points") or []
    pred_status = predicted_block.get("qc_status", "")
    pred_zone_payload, pred_fit_warning = (None, None)
    if len(pred_points) == 4:
        pred_zone_payload, pred_fit_warning = build_zone_payload_from_wedge_points(
            pred_points, frame_rgb.shape
        )

    # ── Load tracks for overlay ──────────────────────────────────────
    tracks = None
    if dlc_csv_path is not None and dlc_csv_path.exists():
        tracks = load_dlc_tracks(dlc_csv_path, likelihood_threshold=LOCKED_LH_THRESHOLD)

    # ── Per-experiment invert toggle ─────────────────────────────────
    _saved_settings = (
        (exp_data.get("computed_metrics") or {})
        .get("ezm_open_closed", {})
        .get("exploration_settings") or {}
    )
    _k_inv = pkey(PANE, f"inv__{exp_id}")
    if _k_inv not in st.session_state:
        st.session_state[_k_inv] = _saved_settings.get("invert_open_closed", False)
    invert_open_closed = st.checkbox("Invert open/closed", key=_k_inv)

    # ── Draw overlay ─────────────────────────────────────────────────
    show_traj = bool(show_trajectory and tracks)
    if zone_payload is not None:
        overlay = draw_ezm_qc_overlay(
            frame_rgb, zone_payload, tracks or {}, "head",
            show_trajectory=show_traj,
            show_legend=True,
            invert_open_closed=bool(invert_open_closed),
        )
    else:
        overlay = frame_rgb

    # ── Two-column layout ────────────────────────────────────────────
    col_img, col_right = st.columns([3, 2])

    with col_img:
        st.image(overlay, use_container_width=True)

    with col_right:
        # Session info
        st.markdown("**Session info**")
        info = {
            "Subject": rec["subject_id"],
            "Date": rec["date_recorded"],
            "Genotype": rec["genotype"],
            "Sex": rec.get("sex", ""),
        }
        st.dataframe(
            pd.DataFrame(list(info.items()), columns=["Field", "Value"]),
            hide_index=True, use_container_width=True,
        )

    # ── Arena QC Review ──────────────────────────────────────────────
    st.markdown("---")
    arena_qc = (
        (exp_data.get("arena_markings") or {})
        .get("ezm_wedge_points", {})
        .get("qc") or {}
    )
    existing_status = arena_qc.get("status", "")
    existing_notes = arena_qc.get("notes", "")
    reviewed_at = arena_qc.get("reviewed_at", "")

    st.markdown("**Arena QC Review**")
    if reviewed_at:
        st.caption(f"Last reviewed: {reviewed_at[:19]}")

    _k_status = pkey(PANE, f"status__{exp_id}")
    if _k_status not in st.session_state:
        if existing_status in _STATUS_OPTIONS:
            st.session_state[_k_status] = existing_status
        else:
            st.session_state[_k_status] = "(not reviewed)"

    qc_status = st.radio(
        "Status", options=_STATUS_OPTIONS, horizontal=True, key=_k_status,
    )

    _k_notes = pkey(PANE, f"notes__{exp_id}")
    if _k_notes not in st.session_state:
        st.session_state[_k_notes] = existing_notes

    qc_notes = st.text_area(
        "Notes",
        placeholder="e.g., circle fit looks good, need to re-mark...",
        key=_k_notes,
        height=80, label_visibility="collapsed",
    )

    # ── Save ─────────────────────────────────────────────────────────
    if st.button(
        "Save arena QC",
        key=pkey(PANE, f"save__{exp_id}"), type="primary",
    ):
        fresh = json.loads(exp_json_path.read_text())
        am_f = fresh.setdefault("arena_markings", {})
        wp_f = am_f.setdefault("ezm_wedge_points", {})

        status_val = qc_status if qc_status != "(not reviewed)" else ""
        wp_f["qc"] = {
            "status": status_val,
            "notes": qc_notes.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Also save invert preference to exploration_settings
        cm_f = fresh.setdefault("computed_metrics", {})
        oc_f = cm_f.setdefault("ezm_open_closed", {})
        oc_f["exploration_settings"] = {
            "invert_open_closed": bool(invert_open_closed),
            "position_mode": "raw",
            "bodypart": "head",
            "likelihood_threshold": LOCKED_LH_THRESHOLD,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        exp_json_path.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
        invalidate_after_write()
        st.toast("Saved arena QC.")
        st.rerun()

    # ── Predicted (UNet auto-suggest) review ─────────────────────────
    if predicted_block:
        st.markdown("---")
        st.markdown("**Predicted wedge points (UNet auto-suggest)**")
        col_meta, col_actions = st.columns([3, 2])
        with col_meta:
            model_ver = predicted_block.get("model_version", "")
            pred_at = predicted_block.get("predicted_at", "")
            n_used = predicted_block.get("n_frames_sampled", 0)
            quality = predicted_block.get("quality", {}) or {}
            st.caption(
                f"Predicted at {pred_at[:19] if pred_at else '?'} "
                f"from {n_used} frames; status={pred_status or 'predicted_unreviewed'}"
            )
            st.caption(f"Model: `{model_ver}`")
            of = quality.get("open_pixel_fraction")
            cf = quality.get("closed_pixel_fraction")
            if of is not None and cf is not None:
                st.caption(
                    f"Mask quality: open_frac={of:.3f}, closed_frac={cf:.3f}, "
                    f"open_components={quality.get('n_open_components', '?')}"
                )
            # Per-point displacement vs manual (if manual exists)
            if len(wp) == 4 and len(pred_points) == 4:
                disps = []
                for (mx, my), (px, py) in zip(wp, pred_points):
                    dx = float(px) - float(mx)
                    dy = float(py) - float(my)
                    disps.append((dx * dx + dy * dy) ** 0.5)
                st.caption(
                    f"Manual ↔ predicted displacement (px): "
                    f"min={min(disps):.1f}, mean={sum(disps)/4:.1f}, max={max(disps):.1f}"
                )

        # Render predicted overlay (separate so user can compare)
        if pred_zone_payload is not None:
            try:
                pred_overlay = draw_ezm_qc_overlay(
                    frame_rgb, pred_zone_payload, tracks or {}, "head",
                    show_trajectory=False, show_legend=False,
                    invert_open_closed=bool(invert_open_closed),
                )
                st.image(pred_overlay, caption="Predicted overlay (auto-suggest)",
                          use_container_width=True)
            except Exception as e:
                st.warning(f"Could not render predicted overlay: {e}")
        else:
            st.warning("Predicted points present but zone fit failed.")
            if pred_fit_warning:
                st.warning(pred_fit_warning)

        with col_actions:
            st.markdown("**Predicted-mark actions**")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Accept → manual",
                              key=pkey(PANE, f"pred_accept__{exp_id}"),
                              type="primary",
                              disabled=(pred_status == "accepted_promoted"
                                        or len(pred_points) != 4)):
                    fresh = json.loads(exp_json_path.read_text())
                    am_f = fresh.setdefault("arena_markings", {})
                    # Promote predicted → manual ezm_wedge_points
                    wp_existing = am_f.get("ezm_wedge_points", {}) or {}
                    am_f["ezm_wedge_points"] = {
                        "points": pred_points,
                        "frame_shape": predicted_block.get("frame_shape",
                                                           list(frame_rgb.shape)),
                        "flag_review": False,
                        "note": (wp_existing.get("note", "") or "").strip()
                                + " [promoted from UNet prediction]",
                        "marked_at": datetime.now(timezone.utc).isoformat(),
                        "promoted_from_prediction": True,
                        "qc": wp_existing.get("qc", {}),
                    }
                    pred_blk = am_f.setdefault("predicted", {}).setdefault(
                        "ezm_wedge_points", {})
                    pred_blk["qc_status"] = "accepted_promoted"
                    pred_blk["accepted_at"] = datetime.now(timezone.utc).isoformat()
                    exp_json_path.write_text(
                        json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
                    invalidate_after_write()
                    st.toast("Predicted marks promoted to manual.")
                    st.rerun()
            with c2:
                if st.button("Reject prediction",
                              key=pkey(PANE, f"pred_reject__{exp_id}"),
                              disabled=(pred_status == "rejected")):
                    fresh = json.loads(exp_json_path.read_text())
                    pred_blk = fresh.setdefault("arena_markings", {}).setdefault(
                        "predicted", {}).setdefault("ezm_wedge_points", {})
                    pred_blk["qc_status"] = "rejected"
                    pred_blk["rejected_at"] = datetime.now(timezone.utc).isoformat()
                    exp_json_path.write_text(
                        json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
                    invalidate_after_write()
                    st.toast("Predicted marks rejected.")
                    st.rerun()
            st.caption("To edit the predicted points before accepting, "
                        "open the EZM Wedge Marking pane.")
