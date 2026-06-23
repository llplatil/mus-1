"""Cohort Management — standalone pane for all task types.

Sole location for cohort CRUD, membership, and export operations.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import streamlit as st

from ..cohorts import (
    add_member,
    cohort_canonical_arena,
    cohort_dlc_model,
    cohort_member_ids,
    create_cohort,
    export_training_csv,
    list_cohorts,
    load_cohort,
    remove_member,
    save_cohort,
    set_cohort_canonical_arena,
)

_TASK_TYPES = ["EZM", "NOR", "NOF", "OF", "RR"]


# ---------------------------------------------------------------------------
# Arena profile registry (cached per-pane render so YAML is read once)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _arena_profile_registry(project_path_str: str):
    """Build a config-aware ArenaProfileRegistry (builtins → user → project)."""
    from mus1.arena_profiles.registry import ArenaProfileRegistry
    return ArenaProfileRegistry.from_config(Path(project_path_str))


def _profile_label(profile_id: str, registry) -> str:
    if not profile_id:
        return "(none — per-experiment markings only)"
    profile = registry.get_or_none(profile_id)
    if profile is None:
        return f"{profile_id} (unknown)"
    return f"{profile_id} — {profile.description}"


def _state_options(profile_id: str, registry) -> List[str]:
    if not profile_id:
        return [""]
    profile = registry.get_or_none(profile_id)
    if profile is None or not profile.states:
        return [""]
    return [""] + list(profile.state_ids())


def _state_label(state_id: str, profile_id: str, registry) -> str:
    if not state_id:
        return "(default)"
    profile = registry.get_or_none(profile_id) if profile_id else None
    if profile is None:
        return state_id
    state = profile.get_state(state_id)
    if state is None:
        return f"{state_id} (unknown)"
    return f"{state_id} — {state.description}" if state.description else state_id


# ---------------------------------------------------------------------------
# Experiment scanning (lightweight, all task types)
# ---------------------------------------------------------------------------

from mus1.web.discovery import CACHE_TTL_SECONDS  # noqa: E402


@st.cache_data(show_spinner="Loading experiments...", ttl=CACHE_TTL_SECONDS)
def _load_all_experiments(experiment_data_root: str) -> List[Dict[str, Any]]:
    """Scan every configured data root and return basic experiment metadata.

    The argument is retained for back-compat; its parent is treated as the
    project_path and additional roots come from ``[paths] data_roots`` in
    ``mus1.toml`` (default: ``experiment_data``, ``validation_data``).
    """
    from mus1.web.discovery import discover_experiments

    project_path = Path(experiment_data_root).parent
    rows = discover_experiments(project_path)
    if not rows:
        # Fallback to the supplied root only (older projects without mus1.toml
        # whose only on-disk root is the legacy experiment_data/).
        from mus1.web.discovery import iter_experiment_dirs

        legacy_root = Path(experiment_data_root)
        if legacy_root.is_dir():
            rows = discover_experiments(project_path, data_roots=[legacy_root])
    # Project the full discovery dict down to the columns this pane uses.
    return [
        {
            "experiment_id": r["experiment_id"],
            "task_type": r["task_type"],
            "subject_id": r["subject_id"],
            "date_recorded": r["date_recorded"],
            "genotype": r["genotype"],
            "sex": r["sex"],
            "data_root": r["data_root"],  # surfaced so the UI can show source
            "cohort_assigned": r["cohort"],
        }
        for r in rows
    ]


def _build_experiment_lookup(
    all_experiments: List[Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    """Build experiment_id -> metadata dict for passing to save_cohort."""
    return {e["experiment_id"]: e for e in all_experiments}


def _render_dlc_model_section(
    coh: Dict[str, Any], member_ids: Set[str], project_path: Path,
) -> None:
    """Read-only: cohort-selected DLC model + per-pair comparison verdict tally."""
    from ..discovery import find_experiment_dir, find_experiment_json
    from ..tracking_comparison_store import list_comparisons

    st.markdown("#### DLC tracking model")
    dm = cohort_dlc_model(coh)
    if dm.get("run_id"):
        st.caption(
            f"Selected model: **{dm['run_id']}**"
            + (f"  (snapshot {dm['snapshot']})" if dm.get("snapshot") else "")
        )
        if dm.get("basis"):
            st.caption(f"Basis: {dm['basis']}")
        st.caption(
            f"Selected {dm.get('selected_at', '?')[:19]} by {dm.get('selected_by', '?')}. "
            "Set via `mus1 tracking set-cohort-model`."
        )
    else:
        st.caption("No cohort-level DLC model selected (downstream uses per-experiment "
                   "default). Select one with `mus1 tracking set-cohort-model`.")

    # Aggregate comparison verdicts across members, keyed by run pair.
    pair_counts: Dict[tuple, Dict[str, int]] = {}
    for eid in sorted(member_ids):
        exp_dir = find_experiment_dir(project_path, eid)
        if exp_dir is None:
            continue
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            ext = json.loads(jp.read_text()).get("extraction")
        except Exception:
            continue
        for comp in list_comparisons(ext):
            key = (comp.get("run_a_id", ""), comp.get("run_b_id", ""))
            tally = pair_counts.setdefault(key, {})
            v = comp.get("verdict", "not_reviewed")
            tally[v] = tally.get(v, 0) + 1

    if pair_counts:
        st.markdown("Tracking-comparison verdicts (across members):")
        rows = []
        for (a, b), tally in pair_counts.items():
            total = sum(tally.values())
            rows.append({
                "model A": a, "model B": b, "reviewed": total,
                "A better": tally.get("A_better", 0),
                "B better": tally.get("B_better", 0),
                "tie": tally.get("tie", 0),
                "both bad": tally.get("both_bad", 0),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_cohort_management(*, project_path: Path) -> None:
    st.header("Cohort Management")
    st.caption("Create, manage, and export experiment cohorts across all task types.")

    if st.button("Refresh (clear cache)", key="cm_refresh"):
        st.cache_data.clear()
        st.rerun()

    experiment_data_root = project_path / "experiment_data"
    cohorts_dir = project_path / "cohorts"
    cohorts_dir.mkdir(parents=True, exist_ok=True)

    all_experiments = _load_all_experiments(str(experiment_data_root))
    exp_lookup = _build_experiment_lookup(all_experiments)
    arena_registry = _arena_profile_registry(str(project_path))

    # ── Sidebar ───────────────────────────────────────────────────────
    st.sidebar.header("Cohort Management")

    # Task type filter
    task_type_filter = st.sidebar.selectbox(
        "Task type filter", options=["All"] + _TASK_TYPES,
        index=0, key="cm_task_type",
    )

    # List cohorts (optionally filtered by task type)
    task_filter_arg = task_type_filter if task_type_filter != "All" else None
    cohort_summaries = list_cohorts(cohorts_dir, task_type=task_filter_arg)

    # Create new cohort (sidebar)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Create new cohort**")
    new_name = st.sidebar.text_input("Name", key="cm_new_name")
    new_desc = st.sidebar.text_input("Description", key="cm_new_desc")
    new_tasks = st.sidebar.multiselect(
        "Task types", options=_TASK_TYPES, default=["EZM"], key="cm_new_tasks",
    )
    profile_options = [""] + arena_registry.list_ids()
    new_profile = st.sidebar.selectbox(
        "Arena profile (optional)",
        options=profile_options,
        format_func=lambda pid: _profile_label(pid, arena_registry),
        index=0,
        key="cm_new_profile",
        help="Cohort-level default for the physical arena. Per-experiment "
             "arena_markings still take precedence at compute time.",
    )
    state_options_new = _state_options(new_profile, arena_registry)
    new_state = ""
    if len(state_options_new) > 1:
        new_state = st.sidebar.selectbox(
            "Arena state",
            options=state_options_new,
            format_func=lambda sid: _state_label(sid, new_profile, arena_registry),
            index=0,
            key="cm_new_state",
        )
    if st.sidebar.button("Create", key="cm_create", disabled=not new_name.strip()):
        slug = re.sub(r"[^a-z0-9]+", "_", new_name.lower().strip()).strip("_")
        coh_path = cohorts_dir / f"{slug}.json"
        if coh_path.exists():
            st.sidebar.error(f"Cohort file already exists: {coh_path.name}")
        else:
            canonical_arena = (
                {"profile_id": new_profile, "state_id": new_state}
                if new_profile else None
            )
            coh = create_cohort(
                new_name.strip(),
                task_types=new_tasks,
                description=new_desc.strip(),
                canonical_arena=canonical_arena,
            )
            save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
            st.sidebar.success(f"Created: {new_name}")
            st.cache_data.clear()
            st.rerun()

    # ── Main content ──────────────────────────────────────────────────
    if not cohort_summaries:
        st.info("No cohorts found. Create one in the sidebar.")
        return

    # Select cohort — include subject count when available
    cohort_labels = []
    for c in cohort_summaries:
        n_subj = c.get("n_subjects")
        subj_str = f", {n_subj} subjects" if n_subj is not None else ""
        tasks_str = ", ".join(c["task_types"]) or "any"
        cohort_labels.append(
            f"{c['name']}  ({c['n_members']} experiments{subj_str}, {tasks_str})"
        )
    selected_idx = st.selectbox(
        "Select cohort", options=range(len(cohort_labels)),
        format_func=lambda i: cohort_labels[i],
        key="cm_select",
    )
    selected_summary = cohort_summaries[selected_idx]
    coh_path = Path(selected_summary["path"])
    coh = load_cohort(coh_path)
    member_ids = cohort_member_ids(coh)

    # ── Cohort details ────────────────────────────────────────────────
    st.subheader(coh.get("name", coh_path.stem))
    summary = coh.get("summary") or {}

    col_info, col_edit = st.columns([2, 1])
    with col_info:
        st.caption(f"File: `{coh_path.name}`")
        n_exp = summary.get("n_experiments", len(member_ids))
        n_subj = summary.get("n_subjects")
        subj_part = f" | Subjects: **{n_subj}**" if n_subj is not None else ""
        st.markdown(
            f"Experiments: **{n_exp}**{subj_part} | "
            f"Task types: {', '.join(coh.get('task_types', []))}"
        )
        st.caption(
            f"Created: {coh.get('created_at', '?')[:19]} | "
            f"Updated: {coh.get('updated_at', '?')[:19]}"
        )
    with col_edit:
        new_desc_val = st.text_area(
            "Description", value=coh.get("description", ""),
            key="cm_edit_desc", height=68,
        )
        if st.button("Save description", key="cm_save_desc"):
            coh["description"] = new_desc_val
            save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
            st.success("Description updated.")
            st.rerun()

    # ── Canonical arena (cohort-level default; per-experiment still wins) ──
    st.markdown("#### Canonical arena (cohort default)")
    st.caption(
        "Physical arena this cohort was run in. Per-experiment "
        "`arena_markings.arena_profile` overrides still win at compute time; "
        "this is the default for new experiments and a hint for stats grouping."
    )
    current_arena = cohort_canonical_arena(coh)
    profile_options_edit = [""] + arena_registry.list_ids()
    current_profile = current_arena.get("profile_id", "")
    profile_idx = (
        profile_options_edit.index(current_profile)
        if current_profile in profile_options_edit
        else 0
    )
    col_prof, col_state, col_save_arena = st.columns([3, 2, 1])
    with col_prof:
        edit_profile = st.selectbox(
            "Profile",
            options=profile_options_edit,
            format_func=lambda pid: _profile_label(pid, arena_registry),
            index=profile_idx,
            key=f"cm_edit_profile_{coh_path.name}",
        )
    state_opts_edit = _state_options(edit_profile, arena_registry)
    current_state = current_arena.get("state_id", "")
    state_idx = state_opts_edit.index(current_state) if current_state in state_opts_edit else 0
    with col_state:
        edit_state = st.selectbox(
            "State",
            options=state_opts_edit,
            format_func=lambda sid: _state_label(sid, edit_profile, arena_registry),
            index=state_idx,
            key=f"cm_edit_state_{coh_path.name}",
            disabled=(len(state_opts_edit) <= 1),
        )
    with col_save_arena:
        if st.button("Save arena", key=f"cm_save_arena_{coh_path.name}"):
            set_cohort_canonical_arena(coh, edit_profile or None, edit_state or None)
            save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
            st.success("Canonical arena updated.")
            st.cache_data.clear()
            st.rerun()

    # ── DLC model selection + comparison rollup (read-only) ───────────
    _render_dlc_model_section(coh, member_ids, project_path)

    # ── Summary: group breakdown ──────────────────────────────────────
    groups = summary.get("groups")
    subjects_by_group = summary.get("subjects_by_group")
    if groups:
        st.markdown("#### Group breakdown")
        group_rows = []
        for grp, n_exp_grp in sorted(groups.items()):
            n_subj_grp = len(subjects_by_group.get(grp, [])) if subjects_by_group else "?"
            group_rows.append({
                "group": grp,
                "experiments": n_exp_grp,
                "subjects": n_subj_grp,
            })
        st.dataframe(group_rows, use_container_width=True, hide_index=True)

    warnings = summary.get("warnings", [])
    if warnings:
        with st.expander(f"Summary warnings ({len(warnings)})", expanded=False):
            for w in warnings:
                st.warning(w)

    # ── NOR/NOF object vocabulary ─────────────────────────────────────
    # Each cohort can declare a list of object names ("fish", "atom",
    # "dino", "tube", "pyramid", …). The marking + QC panes union these
    # across every cohort an experiment belongs to and offer that union
    # as the dropdown. Per-experiment metadata.experiment_level.object_*
    # values still take precedence — this list is what's shown when the
    # selector goes to "(other)" or seeds defaults for a new mark.
    from mus1.web.cohorts import (
        cohort_objects as _cohort_objects,
        set_cohort_objects as _set_cohort_objects,
    )
    if {"NOR", "NOF"} & set(coh.get("task_types") or []) or not coh.get("task_types"):
        st.markdown("#### NOR/NOF object vocabulary")
        st.caption(
            "Comma- or space-separated object names this cohort uses. Stored "
            "lowercase. Per-experiment marks always win; this list seeds the "
            "selector for unmarked or freshly-added experiments."
        )
        current_objs = _cohort_objects(coh)
        col_objs, col_save = st.columns([4, 1])
        with col_objs:
            objs_input = st.text_input(
                "Objects",
                value=", ".join(current_objs),
                key="cm_edit_objects",
                placeholder="e.g. fish, atom, dino, tube",
                label_visibility="collapsed",
            )
        with col_save:
            if st.button("Save objects", key="cm_save_objects"):
                import re as _re
                new_objs = [
                    s.strip().lower()
                    for s in _re.split(r"[,\s]+", objs_input)
                    if s.strip()
                ]
                _set_cohort_objects(coh, new_objs)
                save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
                st.success(f"Saved: {_cohort_objects(coh)}")
                st.cache_data.clear()
                st.rerun()
        if current_objs:
            st.caption(f"Current: `{', '.join(current_objs)}`")
        else:
            st.caption("No objects declared. Marking selector will fall back to global CANONICAL_OBJECTS.")

    # ── Members table ─────────────────────────────────────────────────
    st.markdown("#### Members")
    members_list = coh.get("members") or []

    if not members_list:
        st.info("This cohort has no members yet.")
    else:
        member_rows = []
        for m in members_list:
            eid = m.get("experiment_id", "")
            exp = exp_lookup.get(eid)
            member_rows.append({
                "experiment_id": eid,
                "task": exp["task_type"] if exp else "?",
                "subject_id": exp["subject_id"] if exp else "?",
                "genotype": exp["genotype"] if exp else "",
                "sex": exp["sex"] if exp else "",
                "date": exp["date_recorded"] if exp else "",
                "added_at": m.get("added_at", "")[:19],
            })
        st.dataframe(member_rows, use_container_width=True, hide_index=True)

        # Remove members
        remove_targets = st.multiselect(
            "Select members to remove",
            options=[m["experiment_id"] for m in members_list],
            key="cm_remove_select",
        )
        if remove_targets and st.button(
            f"Remove {len(remove_targets)} member(s)", key="cm_remove_btn",
        ):
            for eid in remove_targets:
                remove_member(coh, eid)
            save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
            st.success(f"Removed {len(remove_targets)} member(s).")
            st.rerun()

    # ── Add experiments ───────────────────────────────────────────────
    st.markdown("#### Add experiments")

    # Pool starts as everything not already in this cohort, restricted by
    # the cohort's declared task_types (if any).
    coh_tasks = set(coh.get("task_types") or [])
    available = [
        e for e in all_experiments
        if e["experiment_id"] not in member_ids
        and (not coh_tasks or e["task_type"] in coh_tasks)
    ]

    # The universal scope picker (sidebar) further narrows the candidate
    # pool to members of another cohort, if one is selected. Useful for
    # transferring experiments between cohorts ("scope = pub, edit = val").
    from mus1.web.filters import SCOPE_KEY, _cohort_member_ids
    scope_cohort = st.session_state.get(SCOPE_KEY)
    if scope_cohort and scope_cohort != coh.get("name"):
        scope_member_ids = _cohort_member_ids(project_path, scope_cohort)
        available = [e for e in available if e["experiment_id"] in scope_member_ids]
        if scope_member_ids:
            st.caption(
                f"Scope active: only showing experiments from cohort "
                f"`{scope_cohort}` ({len(scope_member_ids)} members)."
            )

    # Local filters specific to cohort-add (data source + unassigned).
    src_options = sorted({Path(e.get("data_root", "")).name for e in available if e.get("data_root")})
    col_src, col_unassigned = st.columns([2, 1])
    with col_src:
        sel_sources = st.multiselect(
            "Filter by data source",
            options=src_options,
            default=src_options,
            key="cm_add_src_filter",
            help="Canonical roots: experiment_data + validation_data. See discovery module.",
        )
    with col_unassigned:
        only_unassigned = st.checkbox(
            "Unassigned only",
            value=False,
            key="cm_add_unassigned_only",
            help="Show only experiments whose JSON has no `metadata.experiment_level.cohort` set.",
        )
    available = [
        e for e in available
        if (not sel_sources or Path(e.get("data_root", "")).name in sel_sources)
        and (not only_unassigned or not e.get("cohort_assigned"))
    ]

    if not available:
        st.caption("No experiments match the current filters (or all are already in this cohort).")
    else:
        def _label(e: Dict[str, Any]) -> str:
            src = Path(e.get("data_root", "")).name or "?"
            asn = f"  · cohort: {e['cohort_assigned']}" if e.get("cohort_assigned") else ""
            return f"{e['experiment_id']}  ·  {e.get('genotype','?')}/{e.get('sex','?')}  ·  {src}{asn}"

        add_targets = st.multiselect(
            f"Select experiments to add ({len(available)} available)",
            options=[e["experiment_id"] for e in available],
            format_func=lambda eid: next((_label(e) for e in available if e["experiment_id"] == eid), eid),
            key="cm_add_select",
        )
        col_add_sel, col_add_all = st.columns(2)
        with col_add_sel:
            if add_targets and st.button(
                f"Add {len(add_targets)} selected", key="cm_add_selected",
            ):
                for eid in add_targets:
                    add_member(coh, eid)
                save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
                st.success(f"Added {len(add_targets)} experiment(s).")
                st.rerun()
        with col_add_all:
            if st.button(
                f"Add all {len(available)} matching", key="cm_add_all",
            ):
                for e in available:
                    add_member(coh, e["experiment_id"])
                save_cohort(coh_path, coh, experiment_lookup=exp_lookup)
                st.success(f"Added {len(available)} experiment(s).")
                st.rerun()

    # ── NOR↔NOF pair linking ──────────────────────────────────────────
    coh_tasks_set = set(coh.get("task_types") or [])
    if not coh_tasks_set or {"NOR", "NOF"} & coh_tasks_set:
        from mus1.web.cohorts import link_nor_nof_pairs

        st.markdown("#### NOR↔NOF pair linking")
        st.caption(
            "Pair NOR and NOF experiments by `(subject_id, date_recorded)`. "
            "Existing-but-conflicting links are flagged, never overwritten."
        )
        scope_label = "this cohort only" if member_ids else "this cohort"
        scope_only = st.checkbox(
            f"Restrict to {scope_label}",
            value=True,
            key="cm_pair_scope_only",
            help="Untick to link every unpaired NOR/NOF on disk (across all cohorts).",
        )
        col_dry, col_apply = st.columns(2)
        with col_dry:
            if st.button("Preview pairs (dry-run)", key="cm_pair_dry"):
                report = link_nor_nof_pairs(
                    project_path,
                    cohort_member_ids=(member_ids if scope_only else None),
                    dry_run=True,
                )
                st.session_state["cm_pair_report"] = report
        with col_apply:
            if st.button(
                "Apply pair links",
                key="cm_pair_apply",
                type="primary",
            ):
                report = link_nor_nof_pairs(
                    project_path,
                    cohort_member_ids=(member_ids if scope_only else None),
                    dry_run=False,
                )
                st.session_state["cm_pair_report"] = report
                st.cache_data.clear()
                st.success(
                    f"Linked {len(report['newly_linked'])} new pair(s); "
                    f"{len(report['already_linked'])} already linked."
                )

        # Surface the most-recent report inline
        rpt = st.session_state.get("cm_pair_report")
        if rpt:
            mode_tag = "[dry-run] " if rpt.get("dry_run") else ""
            st.markdown(
                f"**{mode_tag}Checked:** {rpt['checked']}  ·  "
                f"**Newly linked:** {len(rpt['newly_linked'])}  ·  "
                f"**Already linked:** {len(rpt['already_linked'])}  ·  "
                f"**Conflicts:** {len(rpt['conflicts'])}  ·  "
                f"**Unmatched:** {len(rpt['unmatched'])}"
            )
            if rpt["newly_linked"]:
                st.markdown("**New links:**")
                st.dataframe(
                    [{"NOR": n, "NOF": f} for (n, f) in rpt["newly_linked"]],
                    use_container_width=True, hide_index=True,
                )
            if rpt["conflicts"]:
                st.warning("Conflicts (not overwritten — fix manually):")
                st.dataframe(rpt["conflicts"], use_container_width=True, hide_index=True)
            if rpt["unmatched"]:
                with st.expander(f"Unmatched ({len(rpt['unmatched'])}) — no partner on disk"):
                    st.write(rpt["unmatched"])

    # ── Export ────────────────────────────────────────────────────────
    st.markdown("#### Export")
    default_csv = project_path / "exports" / f"{coh.get('name', 'cohort')}_training.csv"
    export_path = Path(
        st.text_input("Export CSV path", value=str(default_csv), key="cm_export_path")
    )
    if st.button("Export training CSV", key="cm_export"):
        n_written = export_training_csv(coh, experiment_data_root, export_path)
        st.success(f"Wrote {n_written} rows to {export_path}")

    # ── Delete cohort ────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Danger zone", expanded=False):
        st.warning(f"Delete cohort '{coh.get('name')}'? This cannot be undone.")
        if st.button(
            f"Delete '{coh.get('name')}'", key="cm_delete",
            type="primary",
        ):
            coh_path.unlink()
            st.success("Cohort deleted.")
            st.cache_data.clear()
            st.rerun()
