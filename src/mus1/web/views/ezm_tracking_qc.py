"""EZM Tracking QC — metrics computation, variant display, and tracking review.

Assumes arena marking is done (wedge points exist, optionally QC-approved in
EZM Zones QC).  This view focuses on DLC tracking quality and metric
correctness.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from ..ezm_qc_shared import (
    LOCKED_BODYPART,
    LOCKED_LH_THRESHOLD,
    LOCKED_POSITION_MODE,
    auto_flags_from_raw_metrics,
    build_zone_payload_from_wedge_points,
    compute_auto_flags,
    load_ezm_experiments,
    load_frame_rgb,
    resolve_path,
    video_fps,
    video_frame_count,
)
from ..ezm_trajectory_overlay import (
    compute_corrected_head_track,
    draw_ezm_qc_overlay,
    load_dlc_tracks,
)

from ..filters import (
    invalidate_after_write,
    mode_settings,
    pkey,
    render_filters,
    render_scope_banner,
)

PANE = "ezm_tracking"

# ZoneDefinition import for building from dict
_ZONES_DIR = str(Path(__file__).resolve().parents[4] / "workspace" / "dlc_ezm_open_closed")
if _ZONES_DIR not in sys.path:
    sys.path.insert(0, _ZONES_DIR)

from ezm_open_closed_zones import ZoneDefinition as _ZD, EllipseParams as _EP  # noqa: E402


_TRACKING_QC_STATUS_OPTIONS = [
    "(not reviewed)", "good", "poor_tracking", "exclude", "needs_re_review",
]


def _build_zone_definition_from_payload(zone_payload: dict) -> _ZD:
    """Build a ZoneDefinition from a zone_payload dict."""
    oe = zone_payload["outer_ellipse"]
    return _ZD(
        outer_ellipse=_EP(
            center_xy=(float(oe["center"][0]), float(oe["center"][1])),
            axes_xy=(float(oe["axes"][0]), float(oe["axes"][1])),
            angle_deg=float(oe["angle_deg"]),
        ),
        r_inner=float(zone_payload["r_inner"]),
        open_angle_ranges=(
            (float(zone_payload["open_angle_ranges"][0][0]),
             float(zone_payload["open_angle_ranges"][0][1])),
            (float(zone_payload["open_angle_ranges"][1][0]),
             float(zone_payload["open_angle_ranges"][1][1])),
        ),
    )


def render_ezm_tracking_qc(*, workspace_root: Optional[str], project_path: Path) -> None:
    st.header("EZM Tracking QC")
    st.caption("Compute metrics, review tracking quality, flag issues.")
    render_scope_banner()

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

    if n_total == 0:
        st.info(f"No EZM experiment folders found under `{experiment_data_root / 'EZM'}`.")
        st.stop()

    # Tracking QC always requires wedge points; pre-filter before showing
    # the universal filter widgets so the Filter expander only offers
    # values present in the eligible pool.
    has_wedge_rows = [r for r in all_rows if r.get("has_wedge_points")]

    # ── Universal Filters block (cohort scope read from session_state) ──
    state, filtered = render_filters(
        rows=has_wedge_rows,
        fields={"qc_statuses", "genotypes", "sexes", "text"},
        key_prefix=PANE,
        qc_field="qc_status",
        project_path=project_path,
    )

    # ── Pane-specific Display + arena/sort settings ─────────────────
    with mode_settings("Display", key_prefix=PANE):
        show_trajectory = st.checkbox(
            "Show trajectory", value=True, key=pkey(PANE, "show_traj"),
        )
        arena_req = st.selectbox(
            "Arena source",
            ["Auto from wedge points", "Require arena QC approved"],
            key=pkey(PANE, "arena_req"),
            help="`Require arena QC approved` hides experiments whose "
                 "wedge-point QC isn't 'keep'.",
        )
        sort_by_artifact = st.checkbox(
            "Sort by artifact rate (worst first)",
            value=False, key=pkey(PANE, "sort_artifact"),
        )
        high_correction_only = st.checkbox(
            "High correction only (>5%)",
            value=False, key=pkey(PANE, "high_corr"),
        )

    # Apply pane-specific filters that don't fit the generic widgets
    if arena_req == "Require arena QC approved":
        filtered = [r for r in filtered if r.get("arena_qc_status") == "keep"]
    if high_correction_only:
        filtered = [
            r for r in filtered
            if (r.get("corrected_fraction") or 0.0) > 0.05
        ]

    # Sort by artifact rate if requested (worst first)
    if sort_by_artifact:
        filtered.sort(key=lambda r: -(r.get("artifact_rate") or 0.0))

    n_filtered = len(filtered)
    n_with_wedge = sum(1 for r in all_rows if r["has_wedge_points"])
    st.caption(
        f"{n_filtered} experiments shown "
        f"({n_with_wedge} with wedge points, {n_total} total)."
    )

    if not filtered:
        st.info("No experiments match current filters.")
        st.stop()

    # ── Navigation ────────────────────────────────────────────────────
    n = n_filtered
    if "ezm_tqc_idx" not in st.session_state:
        st.session_state["ezm_tqc_idx"] = 0
    idx = max(0, min(int(st.session_state["ezm_tqc_idx"]), n - 1))

    col_prev, col_idx, col_next, col_count = st.columns([1, 2, 1, 2])
    with col_prev:
        if st.button("Prev", key="ezm_tqc_prev", disabled=idx <= 0):
            st.session_state["ezm_tqc_idx"] = idx - 1
            st.rerun()
    with col_next:
        if st.button("Next", key="ezm_tqc_next", disabled=idx >= n - 1):
            st.session_state["ezm_tqc_idx"] = idx + 1
            st.rerun()
    with col_idx:
        new_idx = st.number_input(
            "Index", min_value=0, max_value=n - 1, value=idx, step=1,
            key="ezm_tqc_idx_input",
        )
        if int(new_idx) != idx:
            idx = int(new_idx)
            st.session_state["ezm_tqc_idx"] = idx
    with col_count:
        st.markdown(f"**{idx + 1} / {n}** experiments")

    rec = filtered[idx]
    exp_id = rec["experiment_id"]
    exp_json_path = Path(rec["json_path"])
    exp_data = json.loads(exp_json_path.read_text())

    st.subheader(exp_id)

    # Consensus QC badge
    _rec_art = rec.get("artifact_rate")
    _rec_corr = rec.get("corrected_fraction")
    if _rec_art is not None or _rec_corr is not None:
        _badge_parts = []
        if _rec_corr is not None and _rec_corr > 0:
            _badge_parts.append(f"corrected={_rec_corr:.1%}")
        if _rec_art is not None and _rec_art > 0:
            _badge_parts.append(f"artifact_rate={_rec_art:.1%}")
        if _badge_parts:
            st.caption("Consensus: " + " | ".join(_badge_parts))

    # ── Per-experiment settings ─────────────────────────────────────
    _cm_all = (exp_data.get("computed_metrics") or {}).get("ezm_open_closed") or {}
    _saved = _cm_all.get("exploration_settings") or {}

    _k_inv = f"ezm_tqc_exp_inv_{exp_id}"
    if _k_inv not in st.session_state:
        st.session_state[_k_inv] = _saved.get("invert_open_closed", False)

    # ── Variant selector ────────────────────────────────────────────
    # Check for batch-computed variants in JSON
    _batch_variants = (_cm_all.get("variants") or {})
    _batch_variant_names = [
        k for k, v in _batch_variants.items()
        if isinstance(v, dict) and "metrics" in v
    ]
    _FALLBACK_LABEL = "(live compute) raw / head / LH≥0.6"
    _variant_options = [_FALLBACK_LABEL] + sorted(_batch_variant_names)
    # Default to consensus_06 if available
    _default_idx = (
        _variant_options.index("consensus_06")
        if "consensus_06" in _variant_options else 0
    )

    sc1, sc2 = st.columns([1.5, 4])
    with sc1:
        invert_open_closed = st.checkbox("Invert open/closed", key=_k_inv)
    with sc2:
        _k_var = f"ezm_tqc_variant_{exp_id}"
        if len(_batch_variant_names) > 0:
            selected_variant = st.selectbox(
                "Tracking variant",
                options=_variant_options,
                index=_default_idx,
                key=_k_var,
            )
        else:
            selected_variant = _variant_options[0]
            st.caption(
                f"Settings: **{LOCKED_POSITION_MODE}** / **{LOCKED_BODYPART}** "
                f"/ LH\u2265{LOCKED_LH_THRESHOLD}"
            )

    # Resolve active bodypart and LH from selected variant
    if selected_variant in _batch_variant_names:
        _vparams = _batch_variants[selected_variant].get("parameters", {})
        active_bodypart = _vparams.get("bodypart_preferred", LOCKED_BODYPART)
        active_lh = _vparams.get("likelihood_threshold", LOCKED_LH_THRESHOLD)
        active_pos_mode = _vparams.get("position_mode", LOCKED_POSITION_MODE)
    else:
        active_bodypart = LOCKED_BODYPART
        active_lh = LOCKED_LH_THRESHOLD
        active_pos_mode = LOCKED_POSITION_MODE

    # ── Resolve paths ─────────────────────────────────────────────────
    video_path = resolve_path(rec.get("video_path", ""))
    dlc_csv_path = resolve_path(rec.get("dlc_csv_path", ""))

    if video_path is None or not video_path.exists():
        st.error(f"Video not found: {rec.get('video_path', '')}")
        st.stop()

    # ── Frame navigation ─────────────────────────────────────────────
    total_frames = video_frame_count(str(video_path))
    if total_frames <= 0:
        total_frames = 18000  # fallback: 5 min at 60fps

    _k_frame = f"ezm_tqc_frame_{exp_id}"
    if _k_frame not in st.session_state:
        st.session_state[_k_frame] = min(2100, total_frames - 1)

    frame_nav_cols = st.columns([1, 1, 1, 4, 1, 1])
    with frame_nav_cols[0]:
        if st.button("\u23ea", key=f"ezm_tqc_fstart_{exp_id}",
                     help="Jump to start"):
            st.session_state[_k_frame] = 0
            st.rerun()
    with frame_nav_cols[1]:
        step_back = max(0, st.session_state[_k_frame] - 60)
        if st.button("\u25c0 1s", key=f"ezm_tqc_fback_{exp_id}",
                     help="Back 1 second (60 frames)"):
            st.session_state[_k_frame] = step_back
            st.rerun()
    with frame_nav_cols[2]:
        step_back1 = max(0, st.session_state[_k_frame] - 1)
        if st.button("\u25c0", key=f"ezm_tqc_fprev_{exp_id}",
                     help="Previous frame"):
            st.session_state[_k_frame] = step_back1
            st.rerun()
    with frame_nav_cols[3]:
        frame_idx = st.slider(
            "Frame", min_value=0, max_value=total_frames - 1,
            key=_k_frame, label_visibility="collapsed",
        )
    with frame_nav_cols[4]:
        step_fwd1 = min(total_frames - 1, st.session_state[_k_frame] + 1)
        if st.button("\u25b6", key=f"ezm_tqc_fnext_{exp_id}",
                     help="Next frame"):
            st.session_state[_k_frame] = step_fwd1
            st.rerun()
    with frame_nav_cols[5]:
        step_fwd = min(total_frames - 1, st.session_state[_k_frame] + 60)
        if st.button("1s \u25b6", key=f"ezm_tqc_ffwd_{exp_id}",
                     help="Forward 1 second (60 frames)"):
            st.session_state[_k_frame] = step_fwd
            st.rerun()

    cur_time_s = float(frame_idx) / 60.0
    st.caption(f"Frame {frame_idx} / {total_frames - 1}  |  {cur_time_s:.1f}s")

    frame_rgb = load_frame_rgb(str(video_path), frame_idx)
    if frame_rgb is None:
        frame_rgb = load_frame_rgb(str(video_path), 0)
    if frame_rgb is None:
        st.error("Could not load video frame.")
        st.stop()

    # ── Build zone payload from wedge points ─────────────────────────
    am = exp_data.get("arena_markings") or {}
    wp = (am.get("ezm_wedge_points") or {}).get("points") or []
    zone_payload, fit_warning = build_zone_payload_from_wedge_points(wp, frame_rgb.shape)

    if fit_warning:
        st.warning(fit_warning)
    if zone_payload is None:
        st.error("Cannot build zone geometry — check wedge points.")
        st.stop()

    # ── Load tracks ──────────────────────────────────────────────────
    tracks = None
    if dlc_csv_path is not None and dlc_csv_path.exists():
        tracks = load_dlc_tracks(dlc_csv_path, likelihood_threshold=active_lh)
    else:
        st.info(
            "No DLC CSV linked for this experiment — trajectory overlay "
            "and metric compute are disabled. Run DLC inference, then "
            "ensure the JSON's `extraction.tracking_file_path` or "
            "`extraction.dlc_runs[*].output.csv` points to the result."
        )

    # ── Compute corrected head track for consensus mode ─────────────
    _is_consensus = active_pos_mode == "consensus"
    _corrected_track = None
    if _is_consensus and tracks and dlc_csv_path is not None:
        from ...compute.tracking import try_read_dlc_csv
        _raw_df = try_read_dlc_csv(Path(dlc_csv_path))
        _corrected_track = compute_corrected_head_track(
            tracks, primary_bp="head",
            fallback_bps=["neck_base", "nose"],
            likelihood_threshold=active_lh,
            raw_df=_raw_df,
        )

    # ── Draw overlay ─────────────────────────────────────────────────
    overlay = draw_ezm_qc_overlay(
        frame_rgb, zone_payload, tracks or {}, active_bodypart,
        show_trajectory=bool(show_trajectory and tracks),
        show_legend=True,
        invert_open_closed=bool(invert_open_closed),
        highlight_frame=frame_idx,
        consensus_mode=_is_consensus,
        corrected_track=_corrected_track,
    )

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
            "Arena QC": rec.get("arena_qc_status", "") or "(not reviewed)",
        }
        st.dataframe(
            pd.DataFrame(list(info.items()), columns=["Field", "Value"]),
            hide_index=True, use_container_width=True,
        )

        # ── Compute button ──────────────────────────────────────────
        _metrics_key = f"ezm_tqc_exp_metrics_{exp_id}"
        can_compute = dlc_csv_path is not None

        if st.button(
            "Compute metrics", key=f"ezm_tqc_compute_{exp_id}",
            type="primary", disabled=not can_compute,
            help="Compute metrics with current settings. Not saved until you press Save.",
        ):
            with st.spinner("Computing..."):
                from ..ezm_compute_bridge import (
                    compute_open_closed_metrics,
                    try_read_dlc_csv,
                )
                df = try_read_dlc_csv(dlc_csv_path)
                if df is None:
                    st.error("Failed to read DLC CSV.")
                else:
                    zones = _build_zone_definition_from_payload(zone_payload)
                    fps = video_fps(str(video_path))
                    m = compute_open_closed_metrics(
                        df, zones, fps=fps,
                        likelihood_threshold=LOCKED_LH_THRESHOLD,
                        max_interp_gap_frames=10,
                        open_count_mode="sector",
                        bodypart_preferred=LOCKED_BODYPART,
                        invert_open_closed=bool(invert_open_closed),
                        position_mode=LOCKED_POSITION_MODE,
                        nose_mode="blend",
                    )
                    st.session_state[_metrics_key] = {
                        "raw": m,
                        "settings": {
                            "position_mode": LOCKED_POSITION_MODE,
                            "bodypart": LOCKED_BODYPART,
                            "likelihood_threshold": LOCKED_LH_THRESHOLD,
                            "invert_open_closed": bool(invert_open_closed),
                        },
                    }
                    st.rerun()

        if not can_compute:
            st.caption("Cannot compute: missing DLC CSV.")

        # ── Display metrics ─────────────────────────────────────────
        session_metrics = st.session_state.get(_metrics_key)

        # Existing variants from JSON (old format with "occupancy" key)
        variants_json = {
            k: v for k, v in _cm_all.items()
            if k not in ("qc_review", "exploration_settings", "variants",
                         "variants_computed_at", "variants_computed_by")
            and isinstance(v, dict) and "occupancy" in v
        }

        # Show batch-variant metrics if a variant is selected
        if selected_variant in _batch_variant_names:
            _vdata = _batch_variants[selected_variant]
            _vm = _vdata.get("metrics", {})
            st.markdown(f"**Variant: {selected_variant}**")
            st.caption(
                f"pos={active_pos_mode} / bp={active_bodypart} "
                f"/ LH≥{active_lh}"
            )
            _display_batch_variant_metrics(_vm)

        elif session_metrics:
            m = session_metrics["raw"]
            s = session_metrics["settings"]
            st.markdown("**Computed metrics** *(unsaved)*")
            desc_parts = [
                f"pos={s['position_mode']}", f"bp={s['bodypart']}",
                f"lh\u2265{s['likelihood_threshold']}",
            ]
            if s["invert_open_closed"]:
                desc_parts.append("inverted")
            st.caption(" | ".join(desc_parts))
            _display_metrics_table(m)
            flags = auto_flags_from_raw_metrics(m)
            _show_flags(flags)

        elif variants_json:
            st.markdown("**Saved metrics**")
            vnames = list(variants_json.keys())
            selected = st.selectbox(
                "Variant", options=vnames, index=0,
                key=f"ezm_tqc_vsel_{exp_id}",
            )
            v = variants_json[selected]
            v_params = v.get("parameters", {})
            if v_params.get("invert_open_closed"):
                st.caption("Computed with **inverted** open/closed.")
            _display_saved_variant(v)
            flags = compute_auto_flags(variants_json)
            _show_flags(flags)
        else:
            st.info("No metrics yet. Press **Compute metrics** above.")

    # ── Tracking QC Review ───────────────────────────────────────────
    st.markdown("---")
    qc_review = _cm_all.get("qc_review", {})
    existing_status = qc_review.get("status", "")
    existing_notes = qc_review.get("notes", "")
    reviewed_at = qc_review.get("reviewed_at", "")

    st.markdown("**Tracking QC Review**")
    if reviewed_at:
        st.caption(f"Last reviewed: {reviewed_at[:19]}")

    # Show auto-flags prominently
    all_variants = {
        k: v for k, v in _cm_all.items()
        if k not in ("qc_review", "exploration_settings")
        and isinstance(v, dict) and "occupancy" in v
    }
    if all_variants:
        all_flags = compute_auto_flags(all_variants)
        if all_flags:
            st.warning("Auto-flags: " + ", ".join(all_flags))

    _k_status = f"ezm_tqc_status_{exp_id}"
    if _k_status not in st.session_state:
        if existing_status in _TRACKING_QC_STATUS_OPTIONS:
            st.session_state[_k_status] = existing_status
        else:
            st.session_state[_k_status] = "(not reviewed)"

    qc_status = st.radio(
        "Status", options=_TRACKING_QC_STATUS_OPTIONS, horizontal=True,
        key=_k_status,
    )

    _k_notes = f"ezm_tqc_notes_{exp_id}"
    if _k_notes not in st.session_state:
        st.session_state[_k_notes] = existing_notes

    qc_notes = st.text_area(
        "Notes",
        placeholder="e.g., tracking drift in late frames, possible inversion...",
        key=_k_notes,
        height=80, label_visibility="collapsed",
    )

    # ── SAVE ALL ─────────────────────────────────────────────────────
    if st.button(
        "Save all (settings + metrics + QC)",
        key=f"ezm_tqc_save_all_{exp_id}", type="primary",
    ):
        fresh = json.loads(exp_json_path.read_text())
        cm_f = fresh.setdefault("computed_metrics", {})
        oc_f = cm_f.setdefault("ezm_open_closed", {})

        # 1) Save exploration settings
        oc_f["exploration_settings"] = {
            "invert_open_closed": bool(invert_open_closed),
            "position_mode": LOCKED_POSITION_MODE,
            "bodypart": LOCKED_BODYPART,
            "likelihood_threshold": LOCKED_LH_THRESHOLD,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        # 2) Save computed metrics if we have session results
        session_metrics = st.session_state.get(_metrics_key)
        if session_metrics:
            m = session_metrics["raw"]
            s = session_metrics["settings"]
            lh_str = str(s["likelihood_threshold"]).replace(".", "p")
            inv_suffix = "_inv" if s["invert_open_closed"] else ""
            variant_name = f"{s['position_mode']}_lh{lh_str}{inv_suffix}"
            fps = video_fps(str(video_path))
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
            st.session_state.pop(_metrics_key, None)

        # 3) Save QC review
        status_val = qc_status if qc_status != "(not reviewed)" else ""
        all_variants_fresh = {
            k: v for k, v in oc_f.items()
            if k not in ("qc_review", "exploration_settings")
            and isinstance(v, dict) and "occupancy" in v
        }
        flags = compute_auto_flags(all_variants_fresh) if all_variants_fresh else []
        oc_f["qc_review"] = {
            "status": status_val,
            "notes": qc_notes.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "auto_flags": flags,
        }

        exp_json_path.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
        invalidate_after_write()
        st.toast("Saved: settings + metrics + QC.")
        st.rerun()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _display_metrics_table(m: dict) -> None:
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


def _display_saved_variant(v: dict) -> None:
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


def _display_batch_variant_metrics(m: dict) -> None:
    """Display metrics from the batch-computed 7-variant output."""
    def _fmt(val, fmt=".3f"):
        if val is None:
            return "—"
        try:
            return f"{float(val):{fmt}}"
        except (TypeError, ValueError):
            return str(val)

    metrics_display = {
        "Open fraction": _fmt(m.get("open_fraction")),
        "Closed fraction": _fmt(m.get("closed_fraction")),
        "Open time (s)": _fmt(m.get("open_time_s"), ".1f"),
        "Closed time (s)": _fmt(m.get("closed_time_s"), ".1f"),
        "Entries (committed C→O)": _fmt(m.get("committed_closed_to_open_entries"), ".0f"),
        "Entries (gated C→O)": _fmt(m.get("gated_closed_to_open_entries"), ".0f"),
        "Artifact rate": _fmt(m.get("artifact_rate")),
        "Latency to open (s)": _fmt(m.get("latency_first_open_s"), ".1f"),
        "Immobile fraction": _fmt(m.get("immobile_fraction")),
        "Total distance (mm)": _fmt(m.get("total_distance_mm"), ".0f"),
        "Mean speed (mm/s)": _fmt(m.get("mean_speed_mm_s"), ".1f"),
        "Nose open frac": _fmt(m.get("nose_open_fraction_sector")),
        "Track quality": _fmt(m.get("pct_frames_above_thr"), ".1%"),
        "Off-track frac": _fmt(m.get("off_track_fraction_all_frames")),
        "Context-filled (s)": _fmt(m.get("context_filled_closed_time_s"), ".1f"),
    }
    # Consensus-specific metrics
    if m.get("corrected_fraction") is not None:
        metrics_display["Corrected frames"] = _fmt(m.get("corrected_fraction"), ".1%")
    st.dataframe(
        pd.DataFrame(list(metrics_display.items()), columns=["Metric", "Value"]),
        hide_index=True, use_container_width=True,
    )


def _show_flags(flags: List[str]) -> None:
    if flags:
        for fl in flags:
            st.warning(fl)
    else:
        st.success("No auto-flags.")
