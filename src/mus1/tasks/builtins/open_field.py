"""Open Field (OF) task definition.

Arena: circular bucket (same as NOR/NOF).
Annotation: arena boundary ellipse.
Key metrics: total distance, center vs periphery time, velocity.
Also supports MoSeq2/KPMS syllable analysis (computed externally).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from mus1.tasks.base import AnnotationField, TaskDefinition
from mus1.tasks.builtins.nor import BUCKET_DIAMETER_MM


class OpenFieldTask(TaskDefinition):

    @property
    def task_id(self) -> str:
        return "OF"

    @property
    def display_name(self) -> str:
        return "Open Field"

    @property
    def description(self) -> str:
        return (
            "Circular open arena for measuring general locomotion, "
            "anxiety-related center avoidance, and behavioral syllables."
        )

    @property
    def arena_type(self) -> str:
        return "circular"

    @property
    def arena_physical_dimensions(self) -> Dict[str, float]:
        return {"diameter_mm": BUCKET_DIAMETER_MM}

    @property
    def annotation_fields(self) -> List[AnnotationField]:
        return [
            AnnotationField(
                name="arena_boundary",
                label="Arena Boundary",
                field_type="ellipse",
                required=True,
                description="Fit an ellipse to the arena boundary.",
            ),
        ]

    @property
    def qc_flag_vocabulary(self) -> List[str]:
        return [
            "LOW_TRACKING",
            "POOR_ARENA_FIT",
            "SHORT_RECORDING",
            "ZERO_AREA_FRAMES",
        ]

    def compute_auto_flags(self, experiment_data: dict) -> List[str]:
        flags: List[str] = []

        # arena fit quality
        am = experiment_data.get("arena_markings", {})
        boundary = am.get("arena_boundary", {})
        fit_quality = boundary.get("fit_quality")
        if fit_quality is not None and float(fit_quality) < 0.8:
            flags.append("POOR_ARENA_FIT")

        return sorted(set(flags))

    @property
    def computed_metrics_key(self) -> str:
        return "open_field"
