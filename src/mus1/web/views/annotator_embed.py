from __future__ import annotations

import os
import sys
import importlib.util
from pathlib import Path
from typing import Optional

import streamlit as st


def render_annotator(*, workspace_root: Optional[str], project_path: Optional[Path], db_path: Optional[Path]) -> None:
    """
    Embed the Streamlit arena annotator inside the experiment browser so users
    don't need to swap between two separate apps.
    """
    repo_root = Path(__file__).resolve().parents[4]
    arena_dir = repo_root / "workspace" / "arena_annotation"
    app_path = arena_dir / "app.py"
    if not app_path.exists():
        st.error(f"Arena annotator not found at: `{app_path}`")
        st.stop()

    # Ensure its sibling modules are importable (ezm_geometry, nor_nof_geometry, etc.).
    if str(arena_dir) not in sys.path:
        sys.path.insert(0, str(arena_dir))

    if workspace_root:
        os.environ["MOSEQ2_WORKSPACE_ROOT"] = str(workspace_root)
    if project_path:
        os.environ["MOSEQ2_PROJECT_PATH"] = str(project_path)
    if db_path:
        os.environ["MOSEQ2_DB_PATH"] = str(db_path)

    st.caption("Annotator controls live in the sidebar (Mode, Video source, etc.).")

    try:
        spec = importlib.util.spec_from_file_location("mus1_workspace_arena_annotator", str(app_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to create module spec")
        arena_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(arena_app)  # type: ignore[attr-defined]
    except Exception as e:
        import traceback

        st.error(f"Failed to import arena annotator: {e}")
        st.code(traceback.format_exc(), language=None)
        st.stop()

    if not hasattr(arena_app, "render"):
        st.error("Arena annotator module does not expose `render()`.")
        st.stop()

    try:
        with st.spinner("Loading annotator… (first frame read can take a moment on network storage)"):
            arena_app.render()  # type: ignore[attr-defined]
    except Exception as e:
        import traceback

        st.error(f"Arena annotator failed while running: {e}")
        st.code(traceback.format_exc(), language=None)
        st.stop()

