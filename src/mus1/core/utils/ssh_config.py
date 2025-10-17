from __future__ import annotations
from pathlib import Path
from typing import List


def list_ssh_aliases(config_path: Path | None = None) -> List[str]:
    """Return SSH host aliases from ~/.ssh/config (excluding wildcards and '*').

    A minimal parser: collects names after 'Host' directives, supports multiple
    aliases on one line, ignores patterns containing '*' or '?', and skips the
    catch-all 'Host *'.
    """
    path = config_path or (Path.home() / ".ssh" / "config")
    if not path.exists():
        return []

    aliases: List[str] = []
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Normalize: case-insensitive directive match
            if line.lower().startswith("host "):
                parts = line.split()[1:]  # tokens after 'Host'
                for token in parts:
                    # Skip wildcards and the catch-all
                    if token == "*" or "*" in token or "?" in token:
                        continue
                    # Ignore anchors like 'HostName' typo by requiring no '='
                    if "=" in token:
                        continue
                    aliases.append(token)
    except Exception:
        # Best-effort; return what we have
        pass

    # De-duplicate preserving order
    seen = set()
    ordered: List[str] = []
    for a in aliases:
        if a not in seen:
            ordered.append(a)
            seen.add(a)
    return ordered


