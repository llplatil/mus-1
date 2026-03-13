from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import streamlit as st

from .db import connect
from .paths import resolve_db_path
from .views.annotator_embed import render_annotator
from .views.cohort_management import render_cohort_management
from .views.ezm_ml import render_ezm_ml
from .views.ezm_tracking_qc import render_ezm_tracking_qc
from .views.ezm_zones_qc import render_ezm_zones_qc
from .views.experiments import render_experiments
from .views.nor_nof_interaction_qc import render_nor_nof_interaction_qc
from .views.nor_nof_object_marking import render_nor_nof_object_marking
from .views.nor_nof_object_qc import render_nor_nof_object_qc
from .views.nor_nof_qc import render_nor_nof_qc
from .views.nor_nof_roi import render_nor_nof_roi
from .views.subjects import render_subject_explorer
from .views.training_monitor import render_training_monitor


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

    st.sidebar.header("View")
    # Apply any requested mode switch BEFORE creating the radio widget.
    next_view = st.session_state.pop("mus1_view_mode_next", None)
    if next_view:
        st.session_state["mus1_view_mode"] = str(next_view)
    view = st.sidebar.radio(
        "Mode",
        options=["Subjects", "Experiments", "EZM Zones QC", "EZM Tracking QC", "EZM ML", "NOR/NOF ROI", "NOR/NOF QC", "NOR/NOF Object QC", "NOR/NOF Object Marking", "NOR/NOF Interaction QC", "Cohort Management", "Annotator", "Training Monitor"],
        index=0,
        key="mus1_view_mode",
    )

    if view == "Subjects":
        render_subject_explorer(con, db_path=db_path, workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "EZM Zones QC":
        render_ezm_zones_qc(workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "EZM Tracking QC":
        render_ezm_tracking_qc(workspace_root=workspace_root, project_path=project_path)
        st.stop()
    if view == "EZM ML":
        render_ezm_ml(con, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF ROI":
        render_nor_nof_roi(con, project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF QC":
        render_nor_nof_qc(project_path=project_path, workspace_root=workspace_root)
        st.stop()
    if view == "NOR/NOF Object QC":
        render_nor_nof_object_qc(project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF Object Marking":
        render_nor_nof_object_marking(project_path=project_path, workspace_root=workspace_root, db_path=db_path)
        st.stop()
    if view == "NOR/NOF Interaction QC":
        render_nor_nof_interaction_qc(project_path=project_path, workspace_root=workspace_root)
        st.stop()
    if view == "Cohort Management":
        render_cohort_management(project_path=project_path)
        st.stop()
    if view == "Annotator":
        render_annotator(workspace_root=workspace_root, project_path=project_path, db_path=db_path)
        st.stop()
    if view == "Training Monitor":
        render_training_monitor(project_path=project_path, workspace_root=workspace_root)
        st.stop()

    render_experiments(con, db_path=db_path, workspace_root=workspace_root, project_path=project_path)


if __name__ == "__main__":
    main()

