"""Arena profile registry — the *physical artifact* layer beneath tasks.

A **profile** is one physical arena artifact (a particular bucket, an EZM
ring, an OF box). It owns *invariant geometry* (dimensions). It may have
multiple *states* — orthogonal attributes that don't affect dimensions
but DO affect downstream interpretation (e.g. ``original`` vs.
``resanded_2024`` for a bucket whose surface was modified mid-cohort).

This is one level below ``mus1.tasks``: a task references a default
profile by id, and individual experiments may record a state (and, in
rare cases, override the profile entirely). Px-to-mm conversion reads
from the profile, not from the task constants directly — so adding a new
arena (P_NO's Home Depot bucket, a new lab's box) is a registry entry,
not Python edits to compute paths.

See ``docs/web/SCHEMA_VARIANTS.md`` for how profile + state are recorded
in per-experiment JSONs.
"""
from __future__ import annotations

from mus1.arena_profiles.base import (
    ArenaProfile,
    ArenaState,
    CircularGeometry,
    AnnularGeometry,
    Geometry,
)
from mus1.arena_profiles.registry import ArenaProfileRegistry

__all__ = [
    "ArenaProfile",
    "ArenaState",
    "Geometry",
    "CircularGeometry",
    "AnnularGeometry",
    "ArenaProfileRegistry",
]
