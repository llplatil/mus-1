"""ArenaProfileRegistry — builtins + optional YAML extension.

Mirrors the shape of :class:`mus1.tasks.registry.TaskRegistry`. Created
once at the FastAPI / web layer; passed through to compute helpers that
need profile lookup. Pure-Python; no side effects on import.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover  (PyYAML is a project dependency)
    yaml = None

from mus1.arena_profiles.base import (
    AnnularGeometry,
    ArenaProfile,
    ArenaState,
    CircularGeometry,
    Geometry,
)

logger = logging.getLogger(__name__)


def _build_geometry(payload: Dict) -> Geometry:
    shape = (payload.get("shape") or "").lower()
    if shape == "circular":
        return CircularGeometry(diameter_mm=float(payload["diameter_mm"]))
    if shape == "annular":
        return AnnularGeometry(
            outer_diameter_mm=float(payload["outer_diameter_mm"]),
            inner_ratio=float(payload.get("inner_ratio", 0.0)),
        )
    raise ValueError(f"unknown arena geometry shape: {shape!r}")


def _build_state(payload: Dict) -> ArenaState:
    return ArenaState(
        id=str(payload["id"]),
        description=str(payload.get("description", "")),
        notes=str(payload.get("notes", "")),
    )


def _build_profile(payload: Dict) -> ArenaProfile:
    states_raw = payload.get("states") or []
    return ArenaProfile(
        id=str(payload["id"]),
        description=str(payload.get("description", "")),
        geometry=_build_geometry(payload["geometry"]),
        states=tuple(_build_state(s) for s in states_raw),
        default_state_id=str(payload.get("default_state_id", "")),
    )


class ArenaProfileRegistry:
    """In-memory map of profile id → :class:`ArenaProfile`.

    Populated from :data:`mus1.arena_profiles.builtins.ALL_BUILTINS`
    plus optional YAML files. Lookup is by exact id; missing ids
    return ``None`` (callers decide what to do).
    """

    def __init__(self) -> None:
        from mus1.arena_profiles.builtins import ALL_BUILTINS
        self._profiles: Dict[str, ArenaProfile] = {}
        for p in ALL_BUILTINS:
            self.register(p)

    def register(self, profile: ArenaProfile) -> None:
        if profile.id in self._profiles:
            logger.warning("arena profile %r overwritten in registry", profile.id)
        self._profiles[profile.id] = profile

    def get(self, profile_id: str) -> ArenaProfile:
        if profile_id not in self._profiles:
            raise KeyError(f"unknown arena profile id: {profile_id!r}")
        return self._profiles[profile_id]

    def get_or_none(self, profile_id: Optional[str]) -> Optional[ArenaProfile]:
        if not profile_id:
            return None
        return self._profiles.get(profile_id)

    def list_ids(self) -> List[str]:
        return sorted(self._profiles.keys())

    def list_all(self) -> List[ArenaProfile]:
        return [self._profiles[k] for k in self.list_ids()]

    # ── YAML loading ─────────────────────────────────────────────────────
    def load_from_yaml(self, yaml_path: Path) -> int:
        """Load lab/external profiles from a YAML file. Returns the count
        registered. Missing file is a no-op (returns 0).
        """
        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            logger.debug("arena profiles YAML not found at %s, skipping", yaml_path)
            return 0
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to read arena profile YAML but is not installed."
            )
        with yaml_path.open("r") as f:
            data = yaml.safe_load(f)
        if not data:
            return 0
        profiles_raw = data.get("arena_profiles") or []
        if not isinstance(profiles_raw, list):
            raise ValueError(
                f"{yaml_path}: top-level `arena_profiles` must be a list"
            )
        n = 0
        for raw in profiles_raw:
            if not isinstance(raw, dict):
                continue
            self.register(_build_profile(raw))
            n += 1
        return n

    # ── Factory ──────────────────────────────────────────────────────────
    @classmethod
    def from_config(
        cls,
        project_path: Optional[Path] = None,
        *,
        user_yaml_path: Optional[Path] = None,
    ) -> "ArenaProfileRegistry":
        """Build a registry: builtins → user YAML → project YAML.

        Layer precedence (later wins on id collision):

          1. Built-in profiles (always loaded).
          2. User-level YAML at ``~/.config/mus1/arena_profiles.yaml``
             (or *user_yaml_path* if given).
          3. Project-level YAML at
             ``<project_path>/arena_profiles.yaml`` if *project_path*
             is given.

        Either YAML layer may be absent — missing files are silently
        skipped. Malformed YAML raises ``ValueError`` (same contract as
        :meth:`load_from_yaml`).
        """
        registry = cls()
        user_path = user_yaml_path or Path("~/.config/mus1/arena_profiles.yaml").expanduser()
        registry.load_from_yaml(user_path)
        if project_path is not None:
            registry.load_from_yaml(Path(project_path) / "arena_profiles.yaml")
        return registry
