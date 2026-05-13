"""Novel Object Familiarization (NOF) task definition.

Arena: circular bucket. Two identical objects placed inside.
Annotation: object center positions.
Key metrics: total exploration time, side preference, bout counts.
Paired with NOR (Novel Object Recognition).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from mus1.tasks.base import (
    AnnotationField,
    ObjectDefinition,
    TaskDefinition,
    VariantSpec,
)


class NOFTask(TaskDefinition):

    @property
    def task_id(self) -> str:
        return "NOF"

    @property
    def display_name(self) -> str:
        return "Novel Object Familiarization"

    @property
    def description(self) -> str:
        return (
            "Familiarization session: two identical objects. Establishes "
            "baseline exploration before the NOR test session."
        )

    @property
    def arena_type(self) -> str:
        return "circular"

    @property
    def arena_profile_id(self) -> Optional[str]:
        return "tamco_black_bucket"

    @property
    def annotation_fields(self) -> List[AnnotationField]:
        return [
            AnnotationField(
                name="object_centers",
                label="Object Centers",
                field_type="point_set",
                required=True,
                min_count=2,
                max_count=4,
                description="Click the center of each object in the arena.",
            ),
            AnnotationField(
                name="arena_boundary",
                label="Arena Boundary",
                field_type="ellipse",
                required=False,
                description="Arena boundary ellipse (auto-fitted when available).",
            ),
        ]

    @property
    def objects(self) -> List[ObjectDefinition]:
        return [
            ObjectDefinition(
                name="object_a",
                label="Left Object",
                role="familiar",
                description="Left object (identical to right)",
            ),
            ObjectDefinition(
                name="object_b",
                label="Right Object",
                role="familiar",
                description="Right object (identical to left)",
            ),
        ]

    @property
    def qc_flag_vocabulary(self) -> List[str]:
        return [
            "LOW_TRACKING",
            "HIGH_CORRECTION_RATE",
            "BODYPART_DISAGREEMENT",
            "POOR_ARENA_FIT",
            "ZERO_INTERACTION",
            "ARENA_FIT_OUTLIER",
            "OBJECT_CENTER_OUTLIER",
        ]

    def compute_auto_flags(self, experiment_data: dict) -> List[str]:
        flags: List[str] = []

        # arena fit quality
        am = experiment_data.get("arena_markings", {})
        boundary = am.get("nor_nof_arena") or am.get("arena_boundary") or {}
        fit_quality = boundary.get("fit_quality")
        if fit_quality is not None and float(fit_quality) < 0.8:
            flags.append("POOR_ARENA_FIT")

        # tracking quality
        dlc = experiment_data.get("dlc", {})
        tracking_summary = dlc.get("tracking_summary", {})
        frac_below = tracking_summary.get("frac_frames_below_threshold")
        if frac_below is not None and float(frac_below) > 0.30:
            flags.append("LOW_TRACKING")

        # zero interaction
        cm = experiment_data.get("computed_metrics", {})
        nor_nof = cm.get("nor_nof_interaction", {})
        total = nor_nof.get("total_interaction_time")
        if total is not None and float(total) == 0.0:
            flags.append("ZERO_INTERACTION")

        return sorted(set(flags))

    @property
    def paired_task_id(self) -> Optional[str]:
        return "NOR"

    @property
    def computed_metrics_key(self) -> str:
        return "nor_nof_interaction"

    @property
    def variants(self) -> List[VariantSpec]:
        return [
            VariantSpec(
                name="radius_2cm",
                description="Interaction zone radius = 2 cm",
                parameters={"interaction_radius_cm": 2.0},
            ),
            VariantSpec(
                name="radius_3cm",
                description="Interaction zone radius = 3 cm (default)",
                parameters={"interaction_radius_cm": 3.0},
            ),
            VariantSpec(
                name="radius_4cm",
                description="Interaction zone radius = 4 cm",
                parameters={"interaction_radius_cm": 4.0},
            ),
        ]

    @property
    def default_variant(self) -> Optional[str]:
        return "radius_3cm"
