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

@st.cache_data(show_spinner="Loading experiments...", ttl=120)
def _load_all_experiments(experiment_data_root: str) -> List[Dict[str, Any]]:
    """Scan all task-type folders and return basic experiment metadata."""
    rows: List[Dict[str, Any]] = []
    root = Path(experiment_data_root)
    if not root.is_dir():
        return rows
    for task_dir in sorted(root.iterdir()):
        if not task_dir.is_dir():
            continue
        task_type = task_dir.name
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
            rows.append({
                "experiment_id": data.get("experiment_id", exp_dir.name),
                "task_type": task_type,
                "subject_id": str(md.get("subject_id", "")),
                "date_recorded": str(md.get("date_recorded", "")),
                "genotype": str(md.get("genotype", "")),
                "sex": str(md.get("sex", "")),
            })
    return rows


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
            save_cohort(coh_path, coh)
            st.sidebar.success(f"Created: {new_name}")
            st.cache_data.clear()
            st.rerun()

    # ── Main content ──────────────────────────────────────────────────
    if not cohort_summaries:
        st.info("No cohorts found. Create one in the sidebar.")
        return

    # Select cohort
    cohort_labels = [
        f"{c['name']}  ({c['n_members']} members, {', '.join(c['task_types']) or 'any'})"
        for c in cohort_summaries
    ]
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
    col_info, col_edit = st.columns([2, 1])
    with col_info:
        st.caption(f"File: `{coh_path.name}`")
        st.caption(
            f"Members: {len(member_ids)} | "
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
            save_cohort(coh_path, coh)
            st.success("Description updated.")
            st.rerun()

    # ── Members table ─────────────────────────────────────────────────
    st.markdown("#### Members")
    members_list = coh.get("members") or []
    exp_lookup = {e["experiment_id"]: e for e in all_experiments}

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
            save_cohort(coh_path, coh)
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

    if not available:
        st.caption("All matching experiments are already in this cohort.")
    else:
        add_targets = st.multiselect(
            f"Select experiments to add ({len(available)} available)",
            options=[e["experiment_id"] for e in available],
            key="cm_add_select",
        )
        col_add_sel, col_add_all = st.columns(2)
        with col_add_sel:
            if add_targets and st.button(
                f"Add {len(add_targets)} selected", key="cm_add_selected",
            ):
                for eid in add_targets:
                    add_member(coh, eid)
                save_cohort(coh_path, coh)
                st.success(f"Added {len(add_targets)} experiment(s).")
                st.rerun()
        with col_add_all:
            if st.button(
                f"Add all {len(available)} matching", key="cm_add_all",
            ):
                for e in available:
                    add_member(coh, e["experiment_id"])
                save_cohort(coh_path, coh)
                st.success(f"Added {len(available)} experiment(s).")
                st.rerun()

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
