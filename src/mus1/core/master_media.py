from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any


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
    p = master_index_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    with open(p, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, sort_keys=True, default=str)


def add_or_update_master_item(index: Dict[str, Any], *, sample_hash: str, info: Dict[str, Any]) -> None:
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


