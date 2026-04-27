"""Annotation service — arena marking read/write and provenance frame export.

Consolidates the annotation logic from ezm_wedge_marking.py and
nor_nof_object_marking.py into a task-agnostic service. The task
definition's annotation_schema drives what fields are valid.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from mus1.server.services.experiment_service import ExperimentService
from mus1.tasks.registry import TaskRegistry

logger = logging.getLogger(__name__)


class AnnotationService:
    """Arena annotation CRUD with task-schema validation."""

    def __init__(
        self,
        experiment_service: ExperimentService,
        task_registry: TaskRegistry,
    ):
        self._exp_svc = experiment_service
        self._tasks = task_registry

    def get_annotation(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Read the ``arena_markings`` block from an experiment JSON."""
        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            return None
        return data.get("arena_markings") or {}

    def save_annotation(
        self,
        experiment_id: str,
        annotation: Dict[str, Any],
        by: str = "app",
    ) -> Dict[str, Any]:
        """Save arena markings to the experiment JSON.

        Validates that the annotation contains fields defined in the
        task's annotation schema. Adds provenance metadata.
        """
        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            raise KeyError(f"Experiment not found: {experiment_id!r}")

        summary = self._exp_svc.get_experiment(experiment_id)
        task_def = self._tasks.get_or_none(summary.task_id) if summary else None

        # Validate required fields exist
        if task_def:
            for field in task_def.annotation_fields:
                if field.required and field.name not in annotation:
                    logger.warning(
                        "Annotation for %s missing required field %r",
                        experiment_id,
                        field.name,
                    )

        # Merge annotation into arena_markings (preserve existing fields)
        am = data.get("arena_markings") or {}
        am.update(annotation)

        # Add provenance
        am["_annotation_saved"] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "by": by,
        }

        data["arena_markings"] = am
        self._exp_svc.save_experiment_json(experiment_id, data)
        return am

    def export_annotated_frame(
        self,
        experiment_id: str,
        frame_index: Optional[int] = None,
        include_tracking: bool = False,
    ) -> Optional[bytes]:
        """Render an annotation overlay on a video frame for publication provenance.

        Returns PNG bytes with:
        - Video frame as background
        - Arena annotation overlay (wedge lines, object circles, boundary)
        - Optional tracking trajectory overlay
        - Metadata watermark (experiment_id, date, task type)

        Returns None if video or annotation is unavailable.
        """
        import cv2
        import numpy as np

        summary = self._exp_svc.get_experiment(experiment_id)
        if not summary:
            return None

        # Get the video frame
        frame_bytes = self._exp_svc.extract_frame(experiment_id, frame_index)
        if not frame_bytes:
            return None

        # Decode JPEG to numpy array
        frame = cv2.imdecode(
            np.frombuffer(frame_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if frame is None:
            return None

        # Get annotation
        data = self._exp_svc.get_experiment_json(experiment_id)
        am = (data.get("arena_markings") or {}) if data else {}

        h, w = frame.shape[:2]

        # Draw annotations based on task type
        task_def = self._tasks.get_or_none(summary.task_id)
        if task_def and summary.task_id == "EZM":
            self._draw_ezm_annotation(frame, am)
        elif task_def and summary.task_id in ("NOR", "NOF"):
            self._draw_nor_nof_annotation(frame, am)
        elif task_def and summary.task_id == "OF":
            self._draw_of_annotation(frame, am)

        # Metadata watermark
        text = f"{summary.experiment_id} | {summary.task_id} | {summary.date_recorded}"
        cv2.putText(
            frame, text, (10, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
            cv2.LINE_AA,
        )

        # Encode as PNG (lossless for provenance)
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            return None
        return bytes(buf)

    # ── Task-specific overlay drawing ───────────────────────────────────────

    @staticmethod
    def _draw_ezm_annotation(frame, am: dict) -> None:
        """Draw EZM wedge points and fitted circle."""
        import cv2

        wp = am.get("ezm_wedge_points", {})
        points = wp.get("points", [])
        if not points:
            return

        # Draw wedge points
        for pt in points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                cx, cy = int(pt[0]), int(pt[1])
                cv2.circle(frame, (cx, cy), 6, (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), 2, (0, 255, 0), -1)

        # Draw fitted circle if available
        fit = wp.get("circle_fit", {})
        if fit:
            center = fit.get("center")
            radius = fit.get("radius")
            if center and radius:
                cv2.circle(
                    frame,
                    (int(center[0]), int(center[1])),
                    int(radius),
                    (0, 200, 0),
                    1,
                )

    @staticmethod
    def _draw_nor_nof_annotation(frame, am: dict) -> None:
        """Draw NOR/NOF object centers and arena boundary."""
        import cv2

        # Object centers (multiple naming conventions)
        for key in ("object_a_xy", "object_left_xy", "object_b_xy", "object_right_xy"):
            pt = am.get(key)
            if pt and isinstance(pt, (list, tuple)) and len(pt) >= 2:
                cx, cy = int(pt[0]), int(pt[1])
                cv2.circle(frame, (cx, cy), 8, (0, 0, 255), 2)
                cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)

        # v2 objects
        v2 = am.get("nor_nof_objects_v2", {})
        for obj_key in ("object_a", "object_b"):
            obj = v2.get(obj_key, {})
            pt = obj.get("center_xy")
            if pt and isinstance(pt, (list, tuple)) and len(pt) >= 2:
                cx, cy = int(pt[0]), int(pt[1])
                cv2.circle(frame, (cx, cy), 8, (0, 0, 255), 2)
                cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)

        # Arena boundary ellipse
        boundary = am.get("arena_boundary") or am.get("nor_nof_arena") or {}
        ellipse = boundary.get("ellipse", {})
        center = ellipse.get("center_xy") or ellipse.get("center")
        axes = ellipse.get("axes_xy") or ellipse.get("axes")
        angle = ellipse.get("angle_deg", 0)
        if center and axes:
            cv2.ellipse(
                frame,
                (int(center[0]), int(center[1])),
                (int(axes[0] / 2), int(axes[1] / 2)),
                float(angle),
                0, 360,
                (255, 200, 0),
                1,
            )

    @staticmethod
    def _draw_of_annotation(frame, am: dict) -> None:
        """Draw OF arena boundary ellipse."""
        import cv2

        boundary = am.get("arena_boundary", {})
        ellipse = boundary.get("ellipse", {})
        center = ellipse.get("center_xy") or ellipse.get("center")
        axes = ellipse.get("axes_xy") or ellipse.get("axes")
        angle = ellipse.get("angle_deg", 0)
        if center and axes:
            cv2.ellipse(
                frame,
                (int(center[0]), int(center[1])),
                (int(axes[0] / 2), int(axes[1] / 2)),
                float(angle),
                0, 360,
                (255, 200, 0),
                2,
            )
