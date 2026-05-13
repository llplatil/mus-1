"""Elevated Zero Maze (EZM) task definition.

Arena: annular track with two open arms and two closed arms.
Annotation: 4 wedge points on the outer rim where open/closed borders meet.
Key metrics: open-arm time, entries, latency, distance, immobility.
8 calculation variants (bodypart x LH threshold x position mode).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from mus1.tasks.base import AnnotationField, TaskDefinition, VariantSpec


class EZMTask(TaskDefinition):

    @property
    def task_id(self) -> str:
        return "EZM"

    @property
    def display_name(self) -> str:
        return "Elevated Zero Maze"

    @property
    def description(self) -> str:
        return (
            "Annular track with alternating open and closed arms. "
            "Measures anxiety-like behavior via open-arm exploration."
        )

    @property
    def arena_type(self) -> str:
        return "annular"

    @property
    def arena_profile_id(self) -> Optional[str]:
        return "ezm_460mm"

    @property
    def annotation_fields(self) -> List[AnnotationField]:
        return [
            AnnotationField(
                name="ezm_wedge_points",
                label="Wedge Border Points",
                field_type="point_set",
                required=True,
                min_count=4,
                max_count=4,
                description=(
                    "Click 4 points on the outer rim of the EZM track "
                    "where open/closed arm borders meet. Order does not matter."
                ),
            ),
        ]

    @property
    def qc_flag_vocabulary(self) -> List[str]:
        return [
            "LOW_TRACKING",
            "HIGH_CORRECTION_RATE",
            "VARIANT_DISAGREEMENT",
            "OFF_TRACK_EXCESS",
            "POOR_CIRCLE_FIT",
        ]

    def compute_auto_flags(self, experiment_data: dict) -> List[str]:
        flags: List[str] = []
        dlc = experiment_data.get("dlc", {})
        tracking_summary = dlc.get("tracking_summary", {})
        frac_below = tracking_summary.get("frac_frames_below_threshold")
        if frac_below is not None and float(frac_below) > 0.30:
            flags.append("LOW_TRACKING")
        return sorted(set(flags))

    @property
    def computed_metrics_key(self) -> str:
        return "ezm_open_closed"

    # ── 8 calculation variants ──────────────────────────────────────────────

    # Common (locked) parameters shared by all variants
    COMMON_PARAMS: Dict[str, Any] = {
        "open_count_mode": "sector",
        "max_interp_gap_frames": 10,
        "invert_open_closed": False,
        "context_fill_closed": True,
        "max_context_gap_frames": 30,
        "context_max_speed_px_s": 500.0,
        "dwell_time_s": 0.5,
        "hysteresis_deg": 2.0,
        "immobility_cm_s": 2.0,
        "outer_diameter_mm": 460.0,
    }

    @property
    def variants(self) -> List[VariantSpec]:
        return [
            VariantSpec(
                name="raw_head_06",
                description="Head bodypart, raw position, LH >= 0.6",
                parameters={
                    "bodypart_preferred": "head",
                    "position_mode": "raw",
                    "likelihood_threshold": 0.6,
                },
            ),
            VariantSpec(
                name="raw_nose_06",
                description="Nose bodypart, raw position, LH >= 0.6",
                parameters={
                    "bodypart_preferred": "nose",
                    "position_mode": "raw",
                    "likelihood_threshold": 0.6,
                },
            ),
            VariantSpec(
                name="bounded_head_06",
                description="Head with ghost rejection (bound vs neck_base at 60px), LH >= 0.6",
                parameters={
                    "bodypart_preferred": "head",
                    "position_mode": "bounded",
                    "likelihood_threshold": 0.6,
                    "bodypart_bound_px": 60.0,
                    "bound_reference_bp": "neck_base",
                },
            ),
            VariantSpec(
                name="bounded_nose_06",
                description="Nose with ghost rejection (bound vs head at 60px), LH >= 0.6",
                parameters={
                    "bodypart_preferred": "nose",
                    "position_mode": "bounded",
                    "likelihood_threshold": 0.6,
                    "bodypart_bound_px": 60.0,
                    "bound_reference_bp": "head",
                },
            ),
            VariantSpec(
                name="raw_body_06",
                description="Body center bodypart, raw position, LH >= 0.6",
                parameters={
                    "bodypart_preferred": "body_center",
                    "position_mode": "raw",
                    "likelihood_threshold": 0.6,
                },
            ),
            VariantSpec(
                name="raw_head_05",
                description="Head bodypart, raw position, LH >= 0.5",
                parameters={
                    "bodypart_preferred": "head",
                    "position_mode": "raw",
                    "likelihood_threshold": 0.5,
                },
            ),
            VariantSpec(
                name="raw_head_07",
                description="Head bodypart, raw position, LH >= 0.7",
                parameters={
                    "bodypart_preferred": "head",
                    "position_mode": "raw",
                    "likelihood_threshold": 0.7,
                },
            ),
            VariantSpec(
                name="consensus_06",
                description="Head-corrected track with fallback voters (neck_base, nose), LH >= 0.6",
                parameters={
                    "bodypart_preferred": "head",
                    "position_mode": "consensus",
                    "likelihood_threshold": 0.6,
                    "consensus_voter_bps": ["neck_base", "nose"],
                },
            ),
        ]

    @property
    def default_variant(self) -> Optional[str]:
        return "raw_head_06"
