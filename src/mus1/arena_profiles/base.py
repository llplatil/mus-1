"""ArenaProfile + Geometry + ArenaState dataclasses.

Pure data; no I/O, no Streamlit, no FastAPI. Safe to import from
compute, web, FastAPI, importers, and tests.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Geometry — one variant per arena shape
# ---------------------------------------------------------------------------

class Geometry(ABC):
    """Abstract arena geometry. Subclasses encode shape + dimensions."""

    @property
    @abstractmethod
    def shape(self) -> str:
        """Shape tag: ``circular``, ``annular``, ``rectangular``, ``custom``."""
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Round-trippable representation for JSON / YAML."""
        ...

    @abstractmethod
    def mm_per_pixel(self, mean_pixel_diameter: float) -> Optional[float]:
        """Convert a pixel-space diameter (from arena boundary) to mm/px.

        Returns ``None`` if the conversion cannot be computed (e.g. zero
        pixel diameter). Callers should treat ``None`` as "missing data"
        and surface it to the operator rather than papering over with a
        guess.
        """
        ...


@dataclass(frozen=True)
class CircularGeometry(Geometry):
    """A circular arena (bucket, OF box that's actually round, …)."""
    diameter_mm: float

    @property
    def shape(self) -> str:
        return "circular"

    def to_dict(self) -> Dict[str, Any]:
        return {"shape": "circular", "diameter_mm": self.diameter_mm}

    def mm_per_pixel(self, mean_pixel_diameter: float) -> Optional[float]:
        if mean_pixel_diameter <= 0:
            return None
        return self.diameter_mm / mean_pixel_diameter


@dataclass(frozen=True)
class AnnularGeometry(Geometry):
    """An annular arena (EZM)."""
    outer_diameter_mm: float
    inner_ratio: float  # inner_diameter / outer_diameter, in [0, 1)

    @property
    def shape(self) -> str:
        return "annular"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape": "annular",
            "outer_diameter_mm": self.outer_diameter_mm,
            "inner_ratio": self.inner_ratio,
        }

    def mm_per_pixel(self, mean_pixel_diameter: float) -> Optional[float]:
        if mean_pixel_diameter <= 0:
            return None
        return self.outer_diameter_mm / mean_pixel_diameter


# ---------------------------------------------------------------------------
# Arena state (orthogonal to dimensions)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArenaState:
    """A named state of a single arena profile.

    States DO NOT change geometry. They flag interpretation-relevant
    facts about a physical artifact that vary over time without
    requiring a separate profile (e.g. ``original`` vs.
    ``resanded_2024`` for the Tamco black bucket).

    Downstream compute may consult state for things like brightness
    normalization or per-state dim-zone calibration; today none does,
    but the field is preserved so it can be added without re-touching
    every JSON.
    """
    id: str
    description: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "description": self.description, "notes": self.notes}


# ---------------------------------------------------------------------------
# ArenaProfile
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArenaProfile:
    """A physical arena artifact: invariant geometry + named states.

    Attributes
    ----------
    id : Stable string identifier (e.g. ``tamco_black_bucket``).
    description : Human-friendly description for documentation.
    geometry : :class:`Geometry` instance.
    states : Optional named states. Empty tuple means "no
        sub-categorization needed for this profile".
    default_state_id : Identifier of the state to assume when an
        experiment doesn't record one. Falls back to the first state if
        not specified, or empty string if there are no states.
    """
    id: str
    description: str
    geometry: Geometry
    states: tuple = ()  # tuple[ArenaState, ...]
    default_state_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "geometry": self.geometry.to_dict(),
            "states": [s.to_dict() for s in self.states],
            "default_state_id": self.default_state_id,
        }

    def state_ids(self) -> List[str]:
        return [s.id for s in self.states]

    def get_state(self, state_id: str) -> Optional[ArenaState]:
        for s in self.states:
            if s.id == state_id:
                return s
        return None

    def resolve_state_id(self, requested: Optional[str]) -> str:
        """Pick a state id when an experiment may or may not have set one.

        - If *requested* is set and matches a known state, return it.
        - If *requested* is set but unknown, return it anyway (we don't
          silently rewrite operator input — the QC pane can warn).
        - If *requested* is unset, return ``default_state_id`` if any.
        - Otherwise return empty string.
        """
        if requested:
            return requested
        return self.default_state_id

    @property
    def diameter_mm(self) -> float:
        """Convenience: outer diameter in mm regardless of geometry shape."""
        if isinstance(self.geometry, CircularGeometry):
            return self.geometry.diameter_mm
        if isinstance(self.geometry, AnnularGeometry):
            return self.geometry.outer_diameter_mm
        return float("nan")
