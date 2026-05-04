"""Path utilities — mount-alias normalization at the package level.

The Chinook cluster mounts the WDMOSEQ2 share under two equivalent
prefixes depending on which node opens the file:

    /center1/WDMOSEQ2/...     ← canonical, used in recorded paths
    /import/c1/WDMOSEQ2/...   ← alternate symlink mount

A path stored as ``/center1/...`` may not ``Path.exists()`` from a node
that mounts only ``/import/c1/...`` (and vice versa). Five files in the
codebase reimplemented the swap before this module existed; they now
all delegate here.

Public surface is intentionally tiny:

* :func:`resolve_with_mount_aliases` — try the original path, then both
  mount aliases, return the first that exists (or ``None``).
* :func:`mount_alias_variants` — all string variants for ad-hoc
  matching; used only by importers that need to dedupe across mounts.

This module is **pure-Python and import-safe from anywhere** —
compute, web, FastAPI, importers, and tests all share it. Do not
re-add `/center1/` or `/import/c1/` literals elsewhere.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional


_CENTER = "/center1/"
_IMPORT_C1 = "/import/c1/"


def resolve_with_mount_aliases(p: str | Path | None) -> Optional[Path]:
    """Return the first existing form of *p* across known mount aliases.

    Tries the path as-given, then with the ``/center1/`` ↔
    ``/import/c1/`` swap applied. Returns ``None`` if no variant
    exists. Empty / None inputs return ``None``.
    """
    if p is None:
        return None
    s = str(p).strip()
    if not s:
        return None
    primary = Path(s)
    if primary.exists():
        return primary
    for alt in mount_alias_variants(s):
        cand = Path(alt)
        if cand.exists():
            return cand
    return None


def mount_alias_variants(p: str | Path) -> List[str]:
    """Return ``[primary, swapped]`` (deduped) without checking existence.

    Useful for importers that scan symlinked artifacts and need to
    dedupe across mounts without touching the filesystem.
    """
    s = str(p)
    out: List[str] = [s]
    if s.startswith(_CENTER):
        out.append(_IMPORT_C1 + s[len(_CENTER):])
    elif s.startswith(_IMPORT_C1):
        out.append(_CENTER + s[len(_IMPORT_C1):])
    # dedupe, preserve order
    seen: set[str] = set()
    uniq: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq
