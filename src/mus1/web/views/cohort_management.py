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
    cohort_member_ids,
    create_cohort,
    export_training_csv,
    list_cohorts,
    load_cohort,
    remove_member,
    save_cohort,
)

_TASK_TYPES = ["EZM", "NOR", "NOF", "OF", "RR"]


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
    if st.sidebar.button("Create", key="cm_create", disabled=not new_name.strip()):
        slug = re.sub(r"[^a-z0-9]+", "_", new_name.lower().strip()).strip("_")
        coh_path = cohorts_dir / f"{slug}.json"
        if coh_path.exists():
            st.sidebar.error(f"Cohort file already exists: {coh_path.name}")
        else:
            coh = create_cohort(
                new_name.strip(), task_types=new_tasks, description=new_desc.strip(),
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

    # Filter available experiments by task type of cohort
    coh_tasks = set(coh.get("task_types") or [])
    available = [
        e for e in all_experiments
        if e["experiment_id"] not in member_ids
        and (not coh_tasks or e["task_type"] in coh_tasks)
    ]

    # Optional filter: by source data root and by current cohort assignment
    src_options = sorted({Path(e.get("data_root", "")).name for e in available if e.get("data_root")})
    col_src, col_unassigned = st.columns([2, 1])
    with col_src:
        sel_sources = st.multiselect(
            "Filter by data source",
            options=src_options,
            default=src_options,
            key="cm_add_src_filter",
            help="Roots scanned per `mus1.toml [paths] data_roots` (default: experiment_data + validation_data).",
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
