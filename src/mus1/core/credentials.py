from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional


def _creds_path() -> Path:
    home = Path.home()
    return (home / ".mus1" / "credentials.json").expanduser().resolve()


def load_credentials() -> Dict[str, Dict[str, Any]]:
    p = _creds_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_credentials(creds: Dict[str, Dict[str, Any]]) -> None:
    p = _creds_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    with open(p, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2, sort_keys=True)


def get_credential(alias: str) -> Optional[Dict[str, Any]]:
    return load_credentials().get(alias)


def set_credential(alias: str, *, user: Optional[str] = None, identity_file: Optional[str] = None) -> None:
    creds = load_credentials()
    entry = creds.get(alias) or {}
    if user is not None:
        entry["user"] = user
    if identity_file is not None:
        entry["identity_file"] = str(Path(identity_file).expanduser())
    creds[alias] = entry
    save_credentials(creds)


def remove_credential(alias: str) -> bool:
    creds = load_credentials()
    if alias in creds:
        del creds[alias]
        save_credentials(creds)
        return True
    return False


