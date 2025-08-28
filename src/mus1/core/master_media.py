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


