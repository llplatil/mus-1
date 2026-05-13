"""Novel Object Recognition (NOR) task definition.

Arena: circular bucket. Two objects placed inside.
Annotation: object center positions (configurable count and labels).
Key metrics: discrimination index (d2), object interaction time, bout counts.
Paired with NOF (Novel Object Familiarization).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from mus1.tasks.base import (
    AnnotationField,
    ObjectDefinition,
    TaskDefinition,
    VariantSpec,
)


# Default interaction radius in cm for NOR/NOF
DEFAULT_INTERACTION_RADIUS_CM = 3.0
# Physical bucket diameter (17 3/8 inches) used for px-to-mm scaling
BUCKET_DIAMETER_MM = 441.325


class NORTask(TaskDefinition):

    @property
    def task_id(self) -> str:
        return "NOR"

    @property
    def display_name(self) -> str:
        return "Novel Object Recognition"

    @property
    def description(self) -> str:
        return (
            "Test session: one familiar and one novel object. Measures "
            "recognition memory via preferential exploration of the novel object."
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
                description=(
                    "Arena boundary ellipse. Auto-fitted from object positions "
                    "and brightness edge detection when available."
                ),
            ),
        ]

    @property
    def objects(self) -> List[ObjectDefinition]:
        return [
            ObjectDefinition(
                name="object_a",
                label="Left Object",
                role="",
                description="Object on the left side of the arena",
            ),
            ObjectDefinition(
                name="object_b",
                label="Right Object",
                role="",
                description="Object on the right side of the arena",
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
            "novel_side_unknown",
        ]

    def compute_auto_flags(self, experiment_data: dict) -> List[str]:
        flags: List[str] = []
        md = experiment_data.get("metadata", {})
        el = md.get("experiment_level", {})

        # novel_side_unknown — NOR only
        ns = el.get("novel_side")
        if not ns or str(ns).lower() in ("", "none", "null", "unknown"):
            flags.append("novel_side_unknown")

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
        return "NOF"

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
