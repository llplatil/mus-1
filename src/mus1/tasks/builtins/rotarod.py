"""Rotarod (RR) task definition.

Arena: none (motorized rotating rod).
Annotation: none (trial-based, not video-annotated).
Key metrics: latency to fall per trial, mean latency across trials.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from mus1.tasks.base import AnnotationField, TaskDefinition


class RotarodTask(TaskDefinition):

    @property
    def task_id(self) -> str:
        return "RR"

    @property
    def display_name(self) -> str:
        return "Rotarod"

    @property
    def description(self) -> str:
        return (
            "Accelerating rotarod test measuring motor coordination "
            "and balance via latency to fall."
        )

    @property
    def arena_type(self) -> str:
        return "none"

    @property
    def annotation_fields(self) -> List[AnnotationField]:
        return []

    @property
    def qc_flag_vocabulary(self) -> List[str]:
        return [
            "MISSING_TRIALS",
            "OUTLIER_LATENCY",
        ]

    @property
    def computed_metrics_key(self) -> str:
        return "rotarod"
