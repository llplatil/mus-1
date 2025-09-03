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
    env_dir = os.environ.get("MUS1_PROJECTS_DIR")
    if env_dir:
        base_dir = Path(env_dir).expanduser().resolve()
    else:
        # Try per-user config (same as ProjectManager.get_projects_directory())
        try:
            import platform
            import yaml
            if platform.system() == "Darwin":
                config_dir = Path.home() / "Library/Application Support/mus1"
            elif os.name == "nt":
                appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
                config_dir = Path(appdata) / "mus1"
            else:
                xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
                config_dir = Path(xdg) / "mus1"
            yaml_path = config_dir / "config.yaml"
            projects_root = None
            if yaml_path.exists():
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        data = json.load(f) if yaml_path.suffix == ".json" else None
                except Exception:
                    data = None
                try:
                    if data is None:
                        with open(yaml_path, "r", encoding="utf-8") as f2:
                            import yaml as _yaml
                            data = _yaml.safe_load(f2) or {}
                except Exception:
                    data = {}
                pr = (data or {}).get("projects_root")
                if pr:
                    projects_root = Path(str(pr)).expanduser()
            base_dir = Path(projects_root).expanduser().resolve() if projects_root else (Path.home() / "MUS1" / "projects").expanduser().resolve()
        except Exception:
            base_dir = (Path.home() / "MUS1" / "projects").expanduser().resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def master_index_path() -> Path:
    return _projects_root() / "master_media_index.json"


def load_master_index() -> Dict[str, Any]:
    warnings.warn(
        "master_media.load_master_index is deprecated; use the Master Project catalog (in development)",
        DeprecationWarning,
        stacklevel=2,
    )
    p = master_index_path()
    if not p.exists():
        return {"version": 1, "items": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            if not isinstance(data, dict):
                return {"version": 1, "items": {}}
            data.setdefault("version", 1)
            data.setdefault("items", {})
            return data
    except Exception:
        return {"version": 1, "items": {}}


def save_master_index(index: Dict[str, Any]) -> None:
    warnings.warn(
        "master_media.save_master_index is deprecated; use the Master Project catalog (in development)",
        DeprecationWarning,
        stacklevel=2,
    )
    p = master_index_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    with open(p, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, sort_keys=True, default=str)


def add_or_update_master_item(index: Dict[str, Any], *, sample_hash: str, info: Dict[str, Any]) -> None:
    warnings.warn(
        "master_media.add_or_update_master_item is deprecated; use the Master Project catalog (in development)",
        DeprecationWarning,
        stacklevel=2,
    )
    items = index.setdefault("items", {})
    entry = items.get(sample_hash) or {}
    # Merge shallowly and update known locations list
    for k, v in info.items():
        if k == "known_locations":
            existing = set(entry.get("known_locations") or [])
            for loc in (v or []):
                existing.add(str(loc))
            entry["known_locations"] = sorted(list(existing))
        else:
            if v is not None:
                entry[k] = v
    items[sample_hash] = entry


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

