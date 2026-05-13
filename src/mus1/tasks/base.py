"""Base class for behavioral task definitions.

Every behavioral task in mus1 (EZM, NOR, OF, rotarod, or a custom task
defined by another lab) implements this interface. The task definition tells
mus1 how to annotate arenas, which QC flags exist, how to scale pixels to
real-world units, and how to compute task-specific metrics.

All metric computation methods in this module are deterministic: same inputs
always produce identical outputs. See ``src/mus1/compute/README.md`` for the
full deterministic-vs-stochastic boundary documentation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AnnotationField:
    """One field in an annotation schema.

    Describes a single piece of spatial information the user marks on a
    video frame (e.g. a wedge point, an object center, an arena boundary).
    """
    name: str
    label: str
    field_type: str  # "point", "point_set", "ellipse", "polygon"
    required: bool = True
    min_count: int = 1    # for point_set: minimum number of points
    max_count: int = 1    # for point_set: maximum number of points
    description: str = ""


@dataclass(frozen=True)
class ObjectDefinition:
    """Defines an object used in a task (e.g. NOR novel/familiar objects).

    Labs can define their own object names, roles, and count constraints.
    """
    name: str             # internal key, e.g. "object_a"
    label: str            # display label, e.g. "Novel Object"
    role: str = ""        # semantic role: "novel", "familiar", "distractor", or empty
    description: str = ""


@dataclass(frozen=True)
class VariantSpec:
    """Defines a calculation methodology variant.

    A variant is a specific parameter combination for computing metrics.
    Multiple variants can be run on the same experiment to compare
    methodologies (e.g. different bodyparts, likelihood thresholds,
    position modes).
    """
    name: str                        # e.g. "raw_head_06"
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


class TaskDefinition(ABC):
    """Abstract base for behavioral task definitions.

    Subclass this to define a new behavioral task. Built-in tasks (EZM, NOR,
    NOF, OF, RR) ship with mus1. Labs can also define tasks via YAML config
    without writing Python — see ``TaskRegistry.from_config()``.

    Design principle: the task definition declares *what* to compute, and the
    compute library (``mus1.compute``) provides *how*. The task definition is
    the configuration; the compute modules are the deterministic engines.
    """

    # ── Identity ────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def task_id(self) -> str:
        """Short unique identifier, e.g. 'EZM', 'NOR', 'MWM'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. 'Elevated Zero Maze'."""
        ...

    @property
    def description(self) -> str:
        """Optional longer description of the task."""
        return ""

    # ── Arena ───────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def arena_type(self) -> str:
        """Arena geometry class: 'annular', 'circular', 'rectangular', 'custom', or 'none'."""
        ...

    @property
    def arena_profile_id(self) -> Optional[str]:
        """Identifier of the default :class:`mus1.arena_profiles.ArenaProfile`.

        Tasks declare their default *physical artifact* (e.g. NOR uses
        the ``tamco_black_bucket`` profile). Per-experiment overrides
        live in ``arena_markings.arena_profile.profile_id``; cohort
        canonical (Iteration 10) is a future layer above. Returns
        ``None`` for tasks with no arena (rotarod).
        """
        return None

    @property
    def arena_physical_dimensions(self) -> Dict[str, float]:
        """Back-compat shim — derived from :attr:`arena_profile_id`.

        Pre-2026-05-04, tasks declared dimensions inline. Now they
        reference an :class:`ArenaProfile` and dimensions live there.
        Subclasses may still override this for tasks that don't use a
        profile, but new code should set ``arena_profile_id`` instead.
        """
        if self.arena_profile_id is None:
            return {}
        # Lazy import to avoid circular: tasks → arena_profiles → tasks.
        from mus1.arena_profiles.registry import ArenaProfileRegistry
        from mus1.arena_profiles.base import (
            AnnularGeometry, CircularGeometry,
        )
        prof = ArenaProfileRegistry().get_or_none(self.arena_profile_id)
        if prof is None:
            return {}
        g = prof.geometry
        if isinstance(g, CircularGeometry):
            return {"diameter_mm": g.diameter_mm}
        if isinstance(g, AnnularGeometry):
            return {
                "outer_diameter_mm": g.outer_diameter_mm,
                "inner_ratio": g.inner_ratio,
            }
        return {}

    def compute_px_to_mm(self, arena_annotation: Dict[str, Any]) -> float:
        """Compute pixel-to-mm conversion from arena annotation.

        Now delegates to :func:`mus1.compute.scaling.compute_px_to_mm`,
        which handles per-experiment override → task default → "missing"
        cascade. Returns ``nan`` if conversion cannot be computed; the
        canonical helper returns ``(value, source)`` and is preferred
        for new callers.
        """
        from mus1.compute.scaling import compute_px_to_mm
        value, _source = compute_px_to_mm(
            {"arena_markings": arena_annotation}, self,
        )
        return value if value is not None else float("nan")

    # ── Annotation ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def annotation_fields(self) -> List[AnnotationField]:
        """List of spatial fields the user marks during annotation.

        Each field becomes a tool in the annotation canvas UI.
        """
        ...

    @property
    def objects(self) -> List[ObjectDefinition]:
        """Objects used in this task (e.g. NOR novel/familiar).

        Default: no objects. Override for object-recognition tasks.
        """
        return []

    # ── QC ──────────────────────────────────────────────────────────────────

    @property
    def qc_flag_vocabulary(self) -> List[str]:
        """Valid auto-flag strings for this task.

        These are the flags that ``compute_auto_flags()`` can produce.
        The generic QC statuses (not_reviewed, good, poor_tracking, exclude,
        needs_review) are shared across all tasks and not listed here.
        """
        return []

    def compute_auto_flags(self, experiment_data: dict) -> List[str]:
        """Derive auto-flags from experiment JSON fields.

        Must be deterministic. Default: no flags.
        """
        return []

    # ── Groups / pairing ────────────────────────────────────────────────────

    @property
    def group_labels(self) -> List[str]:
        """Expected group labels for this task (e.g. ['WT', 'HET', 'KO']).

        Empty list means free-form (any label accepted).
        """
        return []

    @property
    def paired_task_id(self) -> Optional[str]:
        """If this task has a paired session (NOR<->NOF), return partner task_id."""
        return None

    # ── Calculation variants ────────────────────────────────────────────────

    @property
    def variants(self) -> List[VariantSpec]:
        """Calculation methodology variants available for this task.

        Used for side-by-side QC comparison of different analysis approaches
        (e.g. different bodyparts, likelihood thresholds, position modes).
        Empty list means no variant comparison is available.
        """
        return []

    @property
    def default_variant(self) -> Optional[str]:
        """Name of the default/primary variant for publication.

        Must match a name in ``variants``. None if no variants.
        """
        return None

    # ── Metrics ─────────────────────────────────────────────────────────────

    @property
    def computed_metrics_key(self) -> str:
        """Key under ``computed_metrics`` in the experiment JSON.

        E.g. 'ezm_open_closed', 'nor_nof_interaction'. Used by the compute
        service to store and retrieve results.
        """
        return self.task_id.lower()

    def compute_metrics(
        self,
        experiment_data: dict,
        tracking_data: Any = None,
        variant_name: Optional[str] = None,
    ) -> dict:
        """Compute task-specific metrics.

        Must be deterministic: same inputs always produce identical outputs.
        Default: empty dict (no metrics).

        Parameters
        ----------
        experiment_data : dict
            Full experiment JSON.
        tracking_data : optional
            Loaded tracking dataframe (DLC/SLEAP).
        variant_name : optional
            If provided, compute for this specific variant.
        """
        return {}

    # ── Serialization ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize task definition to dict (for API responses)."""
        return {
            "task_id": self.task_id,
            "display_name": self.display_name,
            "description": self.description,
            "arena_type": self.arena_type,
            "arena_physical_dimensions": self.arena_physical_dimensions,
            "annotation_fields": [
                {
                    "name": f.name,
                    "label": f.label,
                    "field_type": f.field_type,
                    "required": f.required,
                    "min_count": f.min_count,
                    "max_count": f.max_count,
                    "description": f.description,
                }
                for f in self.annotation_fields
            ],
            "objects": [
                {
                    "name": o.name,
                    "label": o.label,
                    "role": o.role,
                    "description": o.description,
                }
                for o in self.objects
            ],
            "qc_flag_vocabulary": self.qc_flag_vocabulary,
            "group_labels": self.group_labels,
            "paired_task_id": self.paired_task_id,
            "variants": [
                {
                    "name": v.name,
                    "description": v.description,
                    "parameters": v.parameters,
                }
                for v in self.variants
            ],
            "default_variant": self.default_variant,
            "computed_metrics_key": self.computed_metrics_key,
        }


class YAMLTaskDefinition(TaskDefinition):
    """Task definition loaded from YAML config.

    Allows labs to define custom tasks without writing Python. An AI agent
    can generate this YAML. The YAML provides the *what* (schemas, labels,
    physical dimensions); task-specific metric computation requires a Python
    plugin (or uses the generic defaults).
    """

    def __init__(self, config: dict):
        self._config = config

    @property
    def task_id(self) -> str:
        return self._config["id"]

    @property
    def display_name(self) -> str:
        return self._config.get("display_name", self.task_id)

    @property
    def description(self) -> str:
        return self._config.get("description", "")

    @property
    def arena_type(self) -> str:
        return self._config.get("arena_type", "custom")

    @property
    def arena_profile_id(self) -> Optional[str]:
        return self._config.get("arena_profile_id")

    @property
    def arena_physical_dimensions(self) -> Dict[str, float]:
        # Prefer the profile-driven path; fall back to inline YAML for
        # back-compat with task YAMLs written before the profile system.
        if self.arena_profile_id:
            return super().arena_physical_dimensions
        return self._config.get("arena_physical_dimensions", {})

    @property
    def annotation_fields(self) -> List[AnnotationField]:
        fields = []
        for f in self._config.get("annotation_fields", []):
            fields.append(AnnotationField(
                name=f["name"],
                label=f.get("label", f["name"]),
                field_type=f.get("field_type", "point"),
                required=f.get("required", True),
                min_count=f.get("min_count", 1),
                max_count=f.get("max_count", 1),
                description=f.get("description", ""),
            ))
        return fields

    @property
    def objects(self) -> List[ObjectDefinition]:
        objs = []
        for o in self._config.get("objects", []):
            objs.append(ObjectDefinition(
                name=o["name"],
                label=o.get("label", o["name"]),
                role=o.get("role", ""),
                description=o.get("description", ""),
            ))
        return objs

    @property
    def qc_flag_vocabulary(self) -> List[str]:
        return self._config.get("qc_flag_vocabulary", [])

    @property
    def group_labels(self) -> List[str]:
        return self._config.get("group_labels", [])

    @property
    def paired_task_id(self) -> Optional[str]:
        return self._config.get("paired_task_id")

    @property
    def variants(self) -> List[VariantSpec]:
        specs = []
        for v in self._config.get("variants", []):
            specs.append(VariantSpec(
                name=v["name"],
                description=v.get("description", ""),
                parameters=v.get("parameters", {}),
            ))
        return specs

    @property
    def default_variant(self) -> Optional[str]:
        return self._config.get("default_variant")
