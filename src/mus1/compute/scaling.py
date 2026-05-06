"""Pixel-to-mm scaling — single canonical entry point.

Replaces the hardcoded ``BUCKET_DIAMETER_MM = 441.325`` /
``DEFAULT_FLOOR_DIAMETER_PX = 705.0`` patterns scattered across panes
and compute modules pre-2026-05-04. Drives off
:class:`mus1.arena_profiles.ArenaProfile` so adding a new arena (P_NO's
Home Depot bucket, a new lab's box) is a registry entry, not Python
edits.

Resolution cascade (per experiment):

  1. Per-experiment override at
     ``arena_markings.arena_profile.profile_id`` → look up that profile
     and scale by it.
  2. Task default ``task_def.arena_profile_id`` → look up that profile
     and scale by it.
  3. (Future, Iteration 10) cohort-canonical arena.
  4. Missing — return ``(NaN, "missing")``. UI surfaces this; do NOT
     silently substitute a guess.

The per-pixel diameter for each step is read from
``arena_markings.arena_boundary.ellipse.{axes_xy|axes}`` (mean of the
two semi-axes-times-2). If the boundary is missing the scale is
"missing" regardless of which profile applies — we have nothing to
scale against.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from mus1.arena_profiles.base import ArenaProfile
from mus1.arena_profiles.registry import ArenaProfileRegistry


# Output ``source`` strings — short, machine-readable, for caption display.
SOURCE_PER_EXPERIMENT_OVERRIDE = "per_experiment_override"
SOURCE_TASK_DEFAULT = "task_default"
SOURCE_MISSING_BOUNDARY = "missing_arena_boundary"
SOURCE_MISSING_PROFILE = "missing_arena_profile"
SOURCE_MISSING = "missing"  # generic fall-through


def compute_px_to_mm(
    experiment_data: Dict[str, Any],
    task_def: Any,
    *,
    profile_registry: Optional[ArenaProfileRegistry] = None,
) -> Tuple[Optional[float], str]:
    """Return ``(value_mm_per_px, source)``.

    Parameters
    ----------
    experiment_data : the per-experiment JSON (must contain
        ``arena_markings``).
    task_def : a :class:`mus1.tasks.base.TaskDefinition` instance for
        this experiment's task. Used as the fallback when no
        per-experiment override is present.
    profile_registry : optional pre-instantiated registry. If omitted,
        a new one is built (cheap; builtins only).

    Returns
    -------
    (value, source) :
        *value* is a float (mm per pixel) when scaling can be computed,
        ``None`` otherwise. *source* is one of the ``SOURCE_*``
        constants explaining which fallback fired.

    The pane caption convention is::

        f"Scaling: {value:.4f} mm/px ({source})"

    so reviewers see at a glance whether the conversion comes from the
    task default vs. an override vs. a missing-data fallback.
    """
    arena_markings = experiment_data.get("arena_markings") or {}
    registry = profile_registry or ArenaProfileRegistry()

    # 1. Per-experiment override
    override = arena_markings.get("arena_profile") or {}
    override_id = override.get("profile_id") if isinstance(override, dict) else None
    if override_id:
        profile = registry.get_or_none(override_id)
        if profile is None:
            return None, SOURCE_MISSING_PROFILE
        value = _scale_with_profile(profile, arena_markings)
        return value, SOURCE_PER_EXPERIMENT_OVERRIDE if value is not None \
            else SOURCE_MISSING_BOUNDARY

    # 2. Task default
    task_profile_id = getattr(task_def, "arena_profile_id", None)
    if task_profile_id:
        profile = registry.get_or_none(task_profile_id)
        if profile is None:
            return None, SOURCE_MISSING_PROFILE
        value = _scale_with_profile(profile, arena_markings)
        return value, SOURCE_TASK_DEFAULT if value is not None \
            else SOURCE_MISSING_BOUNDARY

    # 3. Cohort-canonical (Iteration 10) — not yet implemented
    # 4. Missing
    return None, SOURCE_MISSING


def resolve_arena_state(
    experiment_data: Dict[str, Any],
    task_def: Any,
    *,
    profile_registry: Optional[ArenaProfileRegistry] = None,
) -> Tuple[Optional[str], Optional[ArenaProfile]]:
    """Return ``(state_id, profile)`` for the current experiment.

    Reads ``arena_markings.arena_profile.state_id`` if present; otherwise
    delegates to :meth:`ArenaProfile.resolve_state_id` on the resolved
    profile (which falls back to ``default_state_id``).

    Surfaces both the chosen state and the profile so callers (panes,
    compute helpers) can pick state-conditional behavior without
    re-walking the resolution chain.
    """
    arena_markings = experiment_data.get("arena_markings") or {}
    registry = profile_registry or ArenaProfileRegistry()

    override = arena_markings.get("arena_profile") or {}
    override_profile_id = override.get("profile_id") if isinstance(override, dict) else None
    requested_state = override.get("state_id") if isinstance(override, dict) else None

    profile_id = override_profile_id or getattr(task_def, "arena_profile_id", None)
    profile = registry.get_or_none(profile_id) if profile_id else None
    if profile is None:
        return None, None

    return profile.resolve_state_id(requested_state) or None, profile


def _scale_with_profile(
    profile: ArenaProfile, arena_markings: Dict[str, Any],
) -> Optional[float]:
    """Apply the profile's geometry to the per-experiment arena_boundary."""
    boundary = arena_markings.get("arena_boundary") or {}
    ellipse = boundary.get("ellipse") or {}
    axes = ellipse.get("axes_xy") or ellipse.get("axes")
    if axes and len(axes) >= 2:
        try:
            mean_diameter_px = (float(axes[0]) + float(axes[1])) / 2.0
        except (TypeError, ValueError):
            return None
        return profile.geometry.mm_per_pixel(mean_diameter_px)
    # Some legacy JSONs stored just a numeric diameter
    diameter_px = boundary.get("diameter_px")
    if diameter_px:
        try:
            return profile.geometry.mm_per_pixel(float(diameter_px))
        except (TypeError, ValueError):
            return None
    return None
