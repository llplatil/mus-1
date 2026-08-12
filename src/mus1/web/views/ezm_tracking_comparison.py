"""EZM Tracking Comparison — visually compare two DLC trackings.

When an experiment has more than one registered DLC tracking (e.g. a v1
production model and a v2 candidate), this pane overlays both on the video
frame, shows per-bodypart agreement / coverage, surfaces the worst
disagreement frames, and records a per-experiment verdict.

Trackings are registered via ``mus1 tracking register-run``. Model A
defaults to the cohort-selected / primary model; Model B to the next
registered run. Verdicts are stored under
``extraction.tracking_comparisons[]`` (see tracking_comparison_store).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from ...compute.tracking import get_dlc_run, list_dlc_runs, selected_dlc_run
from ...compute.tracking_comparison import compare_tracks, comparison_to_jsonable
from ..ezm_qc_shared import (
    build_zone_payload_from_wedge_points,
    load_ezm_experiments,
    load_frame_rgb,
    resolve_path,
    video_frame_count,
)
from ..ezm_trajectory_overlay import draw_ezm_comparison_overlay, load_dlc_tracks
from ..filters import (
    SCOPE_KEY,
    invalidate_after_write,
    mode_settings,
    nav_go,
    nav_index,
    pkey,
    render_filters,
    render_scope_banner,
)
from ..tracking_comparison_store import read_comparison, write_comparison

PANE = "ezm_tcompare"

_VERDICT_LABELS = {
    "not_reviewed": "(not reviewed)",
    "A_better": "A better",
    "B_better": "B better",
    "tie": "tie / equivalent",
    "both_bad": "both bad",
}


# ---------------------------------------------------------------------------
# Cached heavy reads
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=300)
def _tracks_cached(csv_path: str, mtime: float):
    return load_dlc_tracks(Path(csv_path))


@st.cache_data(show_spinner=False, ttl=300)
def _compare_cached(csv_a: str, csv_b: str, mtime_a: float, mtime_b: float,
                    run_a: str, run_b: str, pcutoff: float, top_n: int):
    comp = compare_tracks(Path(csv_a), Path(csv_b), run_a_id=run_a, run_b_id=run_b,
                          pcutoff=pcutoff, top_n=top_n)
    return comp


def _mtime(p: Optional[Path]) -> float:
    try:
        return p.stat().st_mtime if p else 0.0
    except OSError:
        return 0.0


def _load_scope_cohort(project_path: Path) -> Optional[Dict[str, Any]]:
    """Load the active scope cohort dict (for defaulting Model A)."""
    name = st.session_state.get(SCOPE_KEY)
    if not name:
        return None
    cp = project_path / "cohorts" / f"{name}.json"
    if not cp.is_file():
        return None
    try:
        return json.loads(cp.read_text())
    except Exception:
        return None


def _jump_to(key: str, frame: int) -> None:
    st.session_state[key] = int(frame)


def _worst_track_score(doc: Dict[str, Any]) -> Optional[float]:
    """Worst head-keypoint below-threshold fraction across registered DLC models.

    Reads the model-keyed ``computed_metrics.ezm_open_closed.head_qc`` block
    (written by compute_ezm_head_qc.py) so low-tracking sessions can be surfaced
    first. Returns the max frac_below_threshold over available models, or None.
    """
    hq = ((((doc or {}).get("computed_metrics") or {}).get("ezm_open_closed") or {})
          .get("head_qc") or {})
    vals = [float(m["frac_below_threshold"])
            for m in (hq.get("models") or {}).values()
            if isinstance(m.get("frac_below_threshold"), (int, float))]
    if not vals and isinstance(hq.get("frac_below_threshold"), (int, float)):
        vals.append(float(hq["frac_below_threshold"]))  # single-model (older) head_qc
    return max(vals) if vals else None


# ---------------------------------------------------------------------------
# Pane
# ---------------------------------------------------------------------------

def render_ezm_tracking_comparison(*, workspace_root: Optional[str], project_path: Path) -> None:
    st.header("EZM Tracking Comparison")
    st.caption("Compare two DLC trackings (e.g. v1 vs v2) for the same experiment.")
    render_scope_banner()

    if st.button("Refresh (clear cache)", key=pkey(PANE, "refresh")):
        invalidate_after_write()
        _tracks_cached.clear()
        _compare_cached.clear()
        st.rerun()

    if not workspace_root:
        st.error("This view requires `--workspace-root`.")
        st.stop()

    experiment_data_root = project_path / "experiment_data"
    all_rows = load_ezm_experiments(str(experiment_data_root))
    if not all_rows:
        st.info("No EZM experiments found.")
        st.stop()

    state, filtered = render_filters(
        rows=all_rows,
        fields={"qc_statuses", "genotypes", "sexes", "text"},
        key_prefix=PANE,
        qc_field="qc_status",
        project_path=project_path,
    )

    with mode_settings("Display", key_prefix=PANE):
        only_multi = st.checkbox("Only experiments with ≥2 trackings", value=True,
                                 key=pkey(PANE, "only_multi"))
        worst_first = st.checkbox("Worst tracking first (head_qc)", value=True,
                                  key=pkey(PANE, "worst_first"),
                                  help="Sort experiments by worst head-keypoint below-threshold "
                                       "fraction (across DLC models), lowest performers first.")
        show_zones = st.checkbox("Show EZM zones", value=True, key=pkey(PANE, "show_zones"))
        window = st.slider("Trajectory window (frames each side)", 30, 600, 180, 30,
                           key=pkey(PANE, "window"))
        pcutoff = st.slider("pcutoff", 0.0, 0.95, 0.6, 0.05, key=pkey(PANE, "pcutoff"))

    cohort_data = _load_scope_cohort(project_path)

    # Augment rows with their registered runs; optionally keep only multi-run.
    rows2: List[Dict[str, Any]] = []
    for r in filtered:
        try:
            doc = json.loads(Path(r["json_path"]).read_text())
            ext = doc.get("extraction")
        except Exception:
            doc, ext = {}, None
        runs = list_dlc_runs(ext)
        if only_multi and len(runs) < 2:
            continue
        rows2.append({**r, "_n_runs": len(runs), "_track_worst": _worst_track_score(doc)})

    if worst_first:
        # sessions with a head_qc score first, worst (highest below-thr fraction) at top
        rows2.sort(key=lambda x: (x.get("_track_worst") is not None,
                                  x.get("_track_worst") or 0.0), reverse=True)

    st.caption(f"{len(rows2)} experiments shown"
               + (" (with ≥2 trackings)" if only_multi else "")
               + (" · worst-tracking first" if worst_first else "") + ".")
    if not rows2:
        st.info("No experiments with ≥2 trackings. Register a second model with "
                "`mus1 tracking register-run`.")
        st.stop()

    # ── Navigation (index selector + Prev/Next; single source of truth) ──
    n = len(rows2)
    c_idx, c_prev, c_next, c_count = st.columns([2, 1, 1, 2])
    with c_idx:
        idx = nav_index(PANE, n)
    with c_prev:
        if st.button("◀ Prev", key=pkey(PANE, "prev"), width="stretch", disabled=idx <= 0):
            nav_go(PANE, -1)
    with c_next:
        if st.button("Next ▶", key=pkey(PANE, "next"), width="stretch", disabled=idx >= n - 1):
            nav_go(PANE, +1)
    with c_count:
        st.markdown(f"**{idx + 1} / {n}** experiments")

    rec = rows2[idx]
    exp_id = rec["experiment_id"]
    json_path = Path(rec["json_path"])
    exp_data = json.loads(json_path.read_text())
    ext = exp_data.get("extraction")
    runs = list_dlc_runs(ext)
    st.subheader(exp_id)
    _tw = rec.get("_track_worst")
    if _tw is not None:
        st.caption(f"worst head-tracking below-0.6 fraction: **{_tw:.3f}**"
                   + ("  ⚠️ low performer" if _tw >= 0.30 else ""))

    if len(runs) < 2:
        st.warning("Only one tracking registered for this experiment — nothing to "
                   "compare. Register another model with `mus1 tracking register-run`.")
        st.stop()

    # ── Model A / B selectors ───────────────────────────────────────────
    run_by_id = {r.run_id: r for r in runs}
    run_ids = list(run_by_id.keys())
    labels = {rid: f"{run_by_id[rid].model_label}  [{run_by_id[rid].source}]" for rid in run_ids}
    sel = selected_dlc_run(ext, cohort=cohort_data)
    default_a = sel.run_id if sel and sel.run_id in run_by_id else run_ids[0]
    default_b = next((r for r in run_ids if r != default_a), run_ids[0])

    cA, cB = st.columns(2)
    with cA:
        run_a = st.selectbox("Model A", run_ids, index=run_ids.index(default_a),
                             format_func=lambda r: labels[r], key=pkey(PANE, f"A_{exp_id}"))
    with cB:
        b_index = run_ids.index(default_b) if default_b in run_ids else 0
        run_b = st.selectbox("Model B", run_ids, index=b_index,
                             format_func=lambda r: labels[r], key=pkey(PANE, f"B_{exp_id}"))
    if run_a == run_b:
        st.warning("Pick two different models to compare.")
        st.stop()

    ra, rb = run_by_id[run_a], run_by_id[run_b]
    csv_a = resolve_path(ra.csv_path)
    csv_b = resolve_path(rb.csv_path)
    if csv_a is None or not csv_a.exists():
        st.error(f"Model A CSV not found: `{ra.csv_path}`")
        st.stop()
    if csv_b is None or not csv_b.exists():
        st.error(f"Model B CSV not found: `{rb.csv_path}`")
        st.stop()

    comp = _compare_cached(str(csv_a), str(csv_b), _mtime(csv_a), _mtime(csv_b),
                           run_a, run_b, pcutoff, 50)
    if comp is None:
        st.error("Could not read one of the tracking CSVs.")
        st.stop()
    for w in comp.warnings:
        st.caption(f"⚠ {w}")

    tracks_a = _tracks_cached(str(csv_a), _mtime(csv_a))
    tracks_b = _tracks_cached(str(csv_b), _mtime(csv_b))

    # ── Bodypart selector (default: worst by median distance) ───────────
    if not comp.bodyparts:
        st.error("No common bodyparts between the two trackings.")
        st.stop()
    worst_bp = max(
        comp.bodyparts,
        key=lambda b: (comp.per_bodypart[b].median_distance_px
                       if not np.isnan(comp.per_bodypart[b].median_distance_px) else -1),
    )
    bp = st.selectbox("Bodypart overlay", comp.bodyparts,
                      index=comp.bodyparts.index(worst_bp), key=pkey(PANE, f"bp_{exp_id}"))

    # ── Frame state (default: top disagreement frame) ───────────────────
    video_path = rec.get("video_path", "")
    total = video_frame_count(str(video_path)) if video_path else comp.n_frames
    total = max(1, total)
    default_frame = comp.top_disagreements[0].frame if comp.top_disagreements else total // 2
    k_frame = pkey(PANE, f"frame_{exp_id}")
    st.session_state.setdefault(k_frame, min(default_frame, total - 1))

    col_img, col_right = st.columns([3, 2])

    with col_img:
        frame_idx = st.slider("Frame", 0, total - 1, key=k_frame)
        frame_rgb = load_frame_rgb(str(video_path), frame_idx) if video_path else None
        if frame_rgb is None:
            st.warning("Could not load video frame; showing metrics only.")
        else:
            zone_payload = None
            if show_zones:
                am = exp_data.get("arena_markings") or {}
                wp = (am.get("ezm_wedge_points") or {}).get("points") or []
                if len(wp) == 4:
                    zone_payload, _warn = build_zone_payload_from_wedge_points(
                        wp, frame_rgb.shape)
            overlay = draw_ezm_comparison_overlay(
                frame_rgb, zone_payload,
                (tracks_a or {}).get(bp), (tracks_b or {}).get(bp),
                label_a=f"A: {ra.snapshot or run_a[:18]}",
                label_b=f"B: {rb.snapshot or run_b[:18]}",
                highlight_frame=frame_idx, window=int(window), show_zones=show_zones,
            )
            st.image(overlay, use_container_width=True)

        # Disagreement timeline (per-frame max across bodyparts).
        tl = comp.disagreement_timeline
        if tl.size:
            st.caption("Disagreement over time (px, max across bodyparts)")
            st.line_chart(pd.DataFrame({"disagreement_px": tl}))

    with col_right:
        st.markdown(f"**A:** {labels[run_a]}")
        st.markdown(f"**B:** {labels[run_b]}")
        ov = comp.overall
        md = ov.get("median_distance_px")
        st.metric("Median distance (px, both-ok)",
                  "n/a" if md is None or np.isnan(md) else f"{md:.2f}")

        # Per-bodypart table.
        table_rows = []
        for b in comp.bodyparts:
            p = comp.per_bodypart[b]
            table_rows.append({
                "bodypart": b,
                "cov A": f"{p.coverage_a:.2f}",
                "cov B": f"{p.coverage_b:.2f}",
                "Δcov (B−A)": f"{p.coverage_delta:+.2f}",
                "med px": ("—" if np.isnan(p.median_distance_px) else f"{p.median_distance_px:.1f}"),
                "agree%": ("—" if np.isnan(p.agreement_frac) else f"{p.agreement_frac*100:.0f}"),
            })
        st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)

        # Jump to worst-disagreement frames.
        if comp.top_disagreements:
            st.caption("Jump to worst-disagreement frames:")
            jcols = st.columns(5)
            for i, fd in enumerate(comp.top_disagreements[:5]):
                with jcols[i]:
                    st.button(f"{fd.frame}", key=pkey(PANE, f"jump_{exp_id}_{i}"),
                              help=f"{fd.bodypart}: {fd.distance_px:.0f}px",
                              on_click=_jump_to, args=(k_frame, fd.frame))

        # ── Verdict ─────────────────────────────────────────────────────
        st.divider()
        existing = read_comparison(ext, run_a, run_b)
        cur_verdict = (existing or {}).get("verdict", "not_reviewed")
        cur_notes = (existing or {}).get("notes", "")
        if existing:
            st.caption(f"Last reviewed {existing.get('reviewed_at','?')} "
                       f"by {existing.get('reviewed_by','?')}")
        verdict_keys = list(_VERDICT_LABELS.keys())
        verdict = st.radio(
            "Verdict (A vs B)", verdict_keys,
            index=verdict_keys.index(cur_verdict) if cur_verdict in verdict_keys else 0,
            format_func=lambda k: _VERDICT_LABELS[k], key=pkey(PANE, f"verdict_{exp_id}"),
        )
        notes = st.text_area("Notes", value=cur_notes, key=pkey(PANE, f"notes_{exp_id}"))
        if st.button("Save verdict", type="primary", key=pkey(PANE, f"save_{exp_id}")):
            js = comparison_to_jsonable(comp, top_n=0)
            snapshot = {"pcutoff": pcutoff, "n_frames": comp.n_frames, "overall": js["overall"]}
            write_comparison(
                json_path, run_a_id=run_a, run_b_id=run_b,
                verdict=verdict, notes=notes, metrics_snapshot=snapshot,
                reviewed_by="app",
            )
            invalidate_after_write()
            st.success(f"Saved verdict: {_VERDICT_LABELS[verdict]}")
            st.rerun()
