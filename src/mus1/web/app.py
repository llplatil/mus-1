from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import streamlit as st

from .db import connect
from .filters import render_scope_picker
from .paths import resolve_db_path
from .views.arena_boundary_marking import render_arena_boundary_marking
from .views.arena_inference_qc import render_arena_inference_qc
from .views.arena_training import render_arena_training
from .views.cohort_management import render_cohort_management
from .views.ezm_ml import render_ezm_ml
from .views.ezm_tracking_qc import render_ezm_tracking_qc
from .views.ezm_wedge_marking import render_ezm_wedge_marking
from .views.ezm_zones_qc import render_ezm_zones_qc
from .views.experiments import render_experiments
from .views.nor_nof_interaction_qc import render_nor_nof_interaction_qc
from .views.nor_nof_object_marking import render_nor_nof_object_marking
from .views.nor_nof_object_qc import render_nor_nof_object_qc
from .views.subjects import render_subject_explorer
from .views.training_monitor import render_training_monitor
from .views.ml_genotype import render_ml_genotype


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--project-path", default=None)
    p.add_argument("--workspace-root", default=None)
    # Streamlit adds its own flags; ignore unknown.
    args, _ = p.parse_known_args()
    return args


def main() -> None:
    st.set_page_config(page_title="MUS1 Experiment Browser", layout="wide")
    st.title("MUS1 Experiment Browser")

    st.sidebar.header("Database")
    args = parse_args()
    default_project = args.project_path or str(Path.cwd())
    project_path_str = st.sidebar.text_input(
        "Project path (dir containing mus1.db, or mus1.db file)",
        value=str(default_project),
    )
    project_path_in = Path(project_path_str).expanduser()
    project_path, db_path = resolve_db_path(project_path_in)
    workspace_root: Optional[str] = args.workspace_root

    if not db_path.exists():
        st.sidebar.error(f"mus1.db not found at: {db_path}")
        st.stop()

    con = connect(db_path)

    # Universal scope picker (cohort) — sits above the View radio so every
    # pane sees the same selection. See web/filters.py and ROADMAP.md
    # ("UI standardization") for the three-tier model.
    render_scope_picker(project_path)

    st.sidebar.header("View")
    # Apply any requested mode switch BEFORE creating the radio widget.
    next_view = st.session_state.pop("mus1_view_mode_next", None)
    if next_view:
        st.session_state["mus1_view_mode"] = str(next_view)
    # Pane order, by task-aligned lifecycle: Browse → Cohort scoping →
    # EZM Mark → EZM QC (arena → tracking) → NOR/NOF Mark → NOR/NOF QC
    # (arena → tracking) → Train. Cohort Management sits up top because
    # users define / pick a cohort *before* doing Mark or QC work.
    # See docs/web/ARCHITECTURE_CURRENT.md §1.2 for pane responsibilities.
    view = st.sidebar.radio(
        "Mode",
        options=[
            # Browse
            "Subjects",
            "Experiments",
            # Cohort scoping (defined before Mark/QC work)
            "Cohort Management",
            # EZM lifecycle (Mark → arena QC → tracking QC)
            "EZM Wedge Marking",
            "EZM Zones QC",
            "EZM Tracking QC",
            # NOR/NOF lifecycle (Mark → arena/object QC → tracking QC)
            "NOR/NOF Object Marking",
            "NOR/NOF Arena Boundary",
            "NOR/NOF Object Association",
            "NOR/NOF Tracking QC",
            # Arena U-Net (cross-profile inference review + training mgmt)
            "Arena Inference QC",
            "Arena Training",
            # Train / Monitor (renamed to "Job Monitor" planned — see ROADMAP)
            "EZM ML",
            "ML Genotype",
            "Training Monitor",
        ],
        index=0,
        key="mus1_view_mode",
    )

    if view == "Subjects":
        render_subject_explorer(con, db_path=db_path, workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "EZM Wedge Marking":
        render_ezm_wedge_marking(project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF Object Marking":
        render_nor_nof_object_marking(project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF Arena Boundary":
        render_arena_boundary_marking(project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "EZM Zones QC":
        render_ezm_zones_qc(workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "EZM Tracking QC":
        render_ezm_tracking_qc(workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "NOR/NOF Object Association":
        render_nor_nof_object_qc(project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF Tracking QC":
        render_nor_nof_interaction_qc(project_path=project_path, workspace_root=workspace_root)
        st.stop()
    if view == "Cohort Management":
        render_cohort_management(project_path=project_path)
        st.stop()
    if view == "Arena Inference QC":
        render_arena_inference_qc(workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "Arena Training":
        render_arena_training(
            workspace_root=workspace_root, project_path=project_path,
            db_path=db_path,
        )
        st.stop()
    if view == "EZM ML":
        render_ezm_ml(con, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "ML Genotype":
        render_ml_genotype(project_path=project_path, workspace_root=workspace_root)
        st.stop()
    if view == "Training Monitor":
        render_training_monitor(project_path=project_path, workspace_root=workspace_root)
        st.stop()

    render_experiments(con, db_path=db_path, workspace_root=workspace_root, project_path=project_path)


if __name__ == "__main__":
    main()

