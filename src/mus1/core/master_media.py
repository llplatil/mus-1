from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Dict, Any, Optional


# NOTE (in development): Master Project concept
# -----------------------
# The previous approach maintained a per-machine JSON index of "master media" to
# optimize scans across machines. We are moving to a single, shared "Master Project"
# model: one shared project (network-accessible) acts as the authoritative catalog
# for static entities (subjects, recordings, experiments). Other projects can
# reference recordings without duplicating or moving them.
#
# Transitional policy:
# - The JSON index helpers remain temporarily but are deprecated.
# - New helper stubs below allow marking/checking a project as the Master Project
#   via an on-disk marker. Full integration into ProjectState is future work.


def _projects_root() -> Path:
    """Get projects root directory using ConfigManager."""
    try:
        from .config_manager import get_config_manager
        config_manager = get_config_manager()
        projects_root = config_manager.get("paths.projects_root")

        if projects_root:
            base_dir = Path(projects_root).expanduser().resolve()
        else:
            # Fallback to default
            base_dir = (Path.home() / "MUS1" / "projects").expanduser().resolve()

    except Exception:
        # Fallback if ConfigManager is not available
        base_dir = (Path.home() / "MUS1" / "projects").expanduser().resolve()

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def master_index_path() -> Path:
    return _projects_root() / "master_media_index.json"


# Removed deprecated methods - these have been replaced by the Master Project catalog system
# The old JSON index approach is no longer supported

def load_master_index() -> Dict[str, Any]:
    """Deprecated: Use Master Project catalog instead."""
    raise NotImplementedError("This method has been removed. Use the Master Project catalog system instead.")


def save_master_index(index: Dict[str, Any]) -> None:
    """Deprecated: Use Master Project catalog instead."""
    raise NotImplementedError("This method has been removed. Use the Master Project catalog system instead.")


def add_or_update_master_item(index: Dict[str, Any], *, sample_hash: str, info: Dict[str, Any]) -> None:
    """Deprecated: Use Master Project catalog instead."""
    raise NotImplementedError("This method has been removed. Use the Master Project catalog system instead.")


def _master_marker_path(project_root: Path) -> Path:
    """Return the marker file path used to flag a project as the Master Project.

    This is a temporary on-disk marker (".mus1-master-project") placed in the
    project root. Future work will persist this in ProjectState and enforce a
    single-master policy per lab/shared root.
    """
    return Path(project_root).expanduser().resolve() / ".mus1-master-project"


def mark_project_as_master(project_root: Path) -> None:
    """Create a marker indicating that this project is the Master Project (WIP).

    - Creates a small JSON marker with metadata. No global registry is updated.
    - Downstream code should prefer a project-level authoritative catalog for
      recordings/subjects/experiments rather than per-machine indices.
    """
    marker = _master_marker_path(project_root)
    try:
        marker.write_text(json.dumps({"version": 1, "created_by": "mus1", "note": "Master Project marker (in development)"}), encoding="utf-8")
    except Exception:
        # Best-effort only; caller may surface errors if needed
        pass


def is_project_master(project_root: Path) -> bool:
    """Return True if the project root appears to be marked as Master Project."""
    try:
        return _master_marker_path(project_root).exists()
    except Exception:
        return False


def read_master_marker(project_root: Path) -> Optional[Dict[str, Any]]:
    """Read the marker JSON if present (None if not set or on error)."""
    mp = _master_marker_path(project_root)
    try:
        if not mp.exists():
            return None
        return json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        return None

