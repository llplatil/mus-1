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

try:
    from ..cohorts import (
        cohort_member_ids,
        list_cohorts,
        load_cohort,
    )
    _HAS_COHORTS = True
except ImportError:
    _HAS_COHORTS = False


_STATUS_OPTIONS = ["(not reviewed)", "keep", "re_mark", "exclude"]


def render_ezm_zones_qc(*, workspace_root: Optional[str], project_path: Path) -> None:
    st.header("EZM Zones QC")
    st.caption("Review arena circle fit from wedge point markings.")

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
    all_rows = load_ezm_experiments(str(experiment_data_root))
    n_total = len(all_rows)
    n_with_wedge = sum(1 for r in all_rows if r["has_wedge_points"])

    if n_total == 0:
        st.info(f"No EZM experiment folders found under `{experiment_data_root / 'EZM'}`.")
        st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────
    st.sidebar.header("Filters")

    show_trajectory = st.sidebar.checkbox("Show trajectory", value=True, key="ezm_zqc_show_traj")

    marking_filter = st.sidebar.selectbox(
        "Marking status", options=["has markings", "needs markings", "all"],
        index=0, key="ezm_zqc_marking_filter",
    )
    qc_filter = st.sidebar.selectbox(
        "Arena QC status", options=["All", "Unreviewed", "Reviewed", "Flagged"],
        index=0, key="ezm_zqc_qc_filter",
    )
    genotypes = sorted({r["genotype"] for r in all_rows if r["genotype"]})
    genotype_filter = st.sidebar.selectbox(
        "Genotype", options=["All"] + genotypes, index=0, key="ezm_zqc_genotype",
    )

    # Cohort filter (read-only)
    cohort_filter_ids: Optional[set] = None
    if _HAS_COHORTS:
        cohort_summaries = list_cohorts(cohorts_dir, task_type="EZM")
        cohort_names = ["(none)"] + [c["name"] for c in cohort_summaries]
        cohort_filter = st.sidebar.selectbox(
            "Cohort", options=cohort_names, index=0, key="ezm_zqc_cohort_filter",
        )
        if cohort_filter != "(none)":
            match = [c for c in cohort_summaries if c["name"] == cohort_filter]
            if match:
                active_cohort = load_cohort(Path(match[0]["path"]))
                cohort_filter_ids = cohort_member_ids(active_cohort)

    name_filter = st.sidebar.text_input("Filter (substring)", value="", key="ezm_zqc_name_filter")

    st.caption(f"{n_with_wedge} of {n_total} EZM experiments have wedge points marked.")

    # ── Filter experiments ────────────────────────────────────────────
    filtered = []
    for r in all_rows:
        if marking_filter == "has markings" and not r["has_wedge_points"]:
            continue
        if marking_filter == "needs markings" and r["has_wedge_points"]:
            continue
        if qc_filter == "Unreviewed" and r["arena_qc_status"]:
            continue
        if qc_filter == "Reviewed" and not r["arena_qc_status"]:
            continue
        if qc_filter == "Flagged" and r["arena_qc_status"] not in ("re_mark", "exclude"):
            continue
        if genotype_filter != "All" and r["genotype"] != genotype_filter:
            continue
        if cohort_filter_ids is not None and r["experiment_id"] not in cohort_filter_ids:
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
    _k_inv = f"ezm_zqc_exp_inv_{exp_id}"
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

    _k_status = f"ezm_zqc_status_{exp_id}"
    if _k_status not in st.session_state:
        if existing_status in _STATUS_OPTIONS:
            st.session_state[_k_status] = existing_status
        else:
            st.session_state[_k_status] = "(not reviewed)"

    qc_status = st.radio(
        "Status", options=_STATUS_OPTIONS, horizontal=True, key=_k_status,
    )

    _k_notes = f"ezm_zqc_notes_{exp_id}"
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
        key=f"ezm_zqc_save_{exp_id}", type="primary",
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
        st.cache_data.clear()
        st.toast("Saved arena QC.")
        st.rerun()
