"""Experiment discovery, loading, and persistence.

Consolidates the 6+ different experiment-loading patterns scattered across
web views into a single service. All experiment data flows through here.

Discovery pattern: walk ``experiment_data/{TASK}/{EXP_ID}/*.json`` directories,
parse JSONs, return structured summaries or full data.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from mus1.tasks.registry import TaskRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExperimentSummary:
    """Lightweight experiment record for list views and filtering."""
    experiment_id: str
    task_id: str
    subject_id: str
    date_recorded: str
    genotype: str
    sex: str
    json_path: str
    # Optional enrichments (populated when available)
    video_path: str = ""
    frame_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    qc_status: str = "not_reviewed"
    auto_flags: List[str] = field(default_factory=list)
    has_annotation: bool = False
    has_tracking: bool = False
    has_computed_metrics: bool = False
    paired_experiment_id: str = ""


class ExperimentService:
    """Discovers experiments from experiment JSONs on disk.

    This is the single point of truth for experiment enumeration. Replaces:
    - cohort_management._load_all_experiments()
    - ezm_wedge_marking._load_ezm_experiments()
    - ezm_qc_shared.load_ezm_experiments()
    - nor_nof_object_qc._load_nor_nof_experiments()
    - experiment_loader.load_experiments()
    """

    def __init__(
        self,
        experiment_data_root: Path,
        task_registry: TaskRegistry,
    ):
        self._root = Path(experiment_data_root)
        self._tasks = task_registry
        # In-memory cache: experiment_id -> parsed summary
        self._cache: Dict[str, ExperimentSummary] = {}
        self._cache_loaded = False

    # ── Discovery ───────────────────────────────────────────────────────────

    def _ensure_cache(self) -> None:
        """Lazy-load the experiment cache on first access."""
        if self._cache_loaded:
            return
        self._scan_all()
        self._cache_loaded = True

    def _scan_all(self) -> None:
        """Walk all task directories and build the cache."""
        if not self._root.is_dir():
            logger.warning("experiment_data_root does not exist: %s", self._root)
            return

        count = 0
        for task_dir in sorted(self._root.iterdir()):
            if not task_dir.is_dir() or task_dir.name.startswith((".", "_")):
                continue
            task_id = task_dir.name
            for exp_dir in sorted(task_dir.iterdir()):
                if not exp_dir.is_dir() or exp_dir.name.startswith((".", "_")):
                    continue
                json_files = list(exp_dir.glob("*.json"))
                if not json_files:
                    continue
                json_path = json_files[0]
                try:
                    summary = self._parse_summary(json_path, task_id)
                    self._cache[summary.experiment_id] = summary
                    count += 1
                except Exception as exc:
                    logger.debug("Skipping %s: %s", json_path, exc)

        logger.info("Scanned %d experiments under %s", count, self._root)

    def _parse_summary(self, json_path: Path, task_id: str) -> ExperimentSummary:
        """Parse an experiment JSON into an ExperimentSummary."""
        data = json.loads(json_path.read_text())
        md = data.get("metadata") or {}
        video = data.get("video") or {}
        qf = data.get("qc_flags") or {}
        am = data.get("arena_markings") or {}
        ext = data.get("extraction") or {}
        cm = data.get("computed_metrics") or {}
        pair = data.get("nor_nof_pair") or {}

        experiment_id = data.get("experiment_id", json_path.parent.name)

        # Detect annotation presence based on task type
        has_annotation = False
        if task_id == "EZM":
            wp = am.get("ezm_wedge_points", {})
            has_annotation = bool(wp.get("points"))
        elif task_id in ("NOR", "NOF"):
            has_annotation = bool(
                am.get("object_a_xy") or am.get("object_left_xy")
                or am.get("nor_nof_objects_v2")
            )
        elif task_id == "OF":
            has_annotation = bool(am.get("arena_boundary"))

        # Resolve tracking presence across both legacy + new DLC schemas.
        # See compute.tracking.resolve_dlc_csv_path for schema duality.
        from mus1.compute.tracking import resolve_dlc_csv_path
        has_tracking = bool(resolve_dlc_csv_path(ext))

        # Check for computed metrics under the task's key
        task_def = self._tasks.get_or_none(task_id)
        metrics_key = task_def.computed_metrics_key if task_def else task_id.lower()
        has_computed_metrics = bool(cm.get(metrics_key))

        return ExperimentSummary(
            experiment_id=experiment_id,
            task_id=task_id,
            subject_id=str(md.get("subject_id", "")),
            date_recorded=str(md.get("date_recorded", "")),
            genotype=str(md.get("genotype", "")),
            sex=str(md.get("sex", "")),
            json_path=str(json_path),
            video_path=str(video.get("path", "")),
            frame_count=video.get("frame_count"),
            duration_seconds=video.get("duration_seconds"),
            qc_status=str(qf.get("status", "not_reviewed")),
            auto_flags=list(qf.get("auto_flags", [])),
            has_annotation=has_annotation,
            has_tracking=has_tracking,
            has_computed_metrics=has_computed_metrics,
            paired_experiment_id=str(pair.get("paired_experiment_id", "")) if isinstance(pair, dict) else "",
        )

    def invalidate_cache(self) -> None:
        """Clear the cache so next access re-scans from disk."""
        self._cache.clear()
        self._cache_loaded = False

    def refresh_experiment(self, experiment_id: str) -> Optional[ExperimentSummary]:
        """Re-read a single experiment from disk and update the cache."""
        existing = self._cache.get(experiment_id)
        if existing:
            jp = Path(existing.json_path)
            if jp.exists():
                try:
                    summary = self._parse_summary(jp, existing.task_id)
                    self._cache[experiment_id] = summary
                    return summary
                except Exception as exc:
                    logger.warning("Failed to refresh %s: %s", experiment_id, exc)
        return existing

    # ── Queries ─────────────────────────────────────────────────────────────

    def list_experiments(
        self,
        task_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        genotype: Optional[str] = None,
        sex: Optional[str] = None,
        cohort_ids: Optional[Set[str]] = None,
        qc_status: Optional[str] = None,
        exclude_statuses: Optional[Set[str]] = None,
        has_annotation: Optional[bool] = None,
        has_tracking: Optional[bool] = None,
    ) -> List[ExperimentSummary]:
        """List experiments with optional filtering.

        All filters are AND-combined. None means no filter on that field.
        """
        self._ensure_cache()
        results = []
        for exp in self._cache.values():
            if task_id and exp.task_id != task_id:
                continue
            if subject_id and exp.subject_id != subject_id:
                continue
            if genotype and exp.genotype != genotype:
                continue
            if sex and exp.sex != sex:
                continue
            if cohort_ids is not None and exp.experiment_id not in cohort_ids:
                continue
            if qc_status and exp.qc_status != qc_status:
                continue
            if exclude_statuses and exp.qc_status in exclude_statuses:
                continue
            if has_annotation is not None and exp.has_annotation != has_annotation:
                continue
            if has_tracking is not None and exp.has_tracking != has_tracking:
                continue
            results.append(exp)

        return sorted(results, key=lambda e: (e.task_id, e.subject_id, e.date_recorded))

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentSummary]:
        """Get a single experiment summary by ID."""
        self._ensure_cache()
        return self._cache.get(experiment_id)

    def get_experiment_json(self, experiment_id: str) -> Optional[dict]:
        """Load the full experiment JSON for an experiment."""
        self._ensure_cache()
        summary = self._cache.get(experiment_id)
        if not summary:
            return None
        jp = Path(summary.json_path)
        if not jp.exists():
            return None
        return json.loads(jp.read_text())

    def save_experiment_json(self, experiment_id: str, data: dict) -> None:
        """Write experiment JSON back to disk and refresh cache.

        The caller is responsible for maintaining data integrity
        (provenance blocks, QC flags, etc.).
        """
        self._ensure_cache()
        summary = self._cache.get(experiment_id)
        if not summary:
            raise KeyError(f"Unknown experiment_id: {experiment_id!r}")
        jp = Path(summary.json_path)
        jp.write_text(json.dumps(data, indent=2, default=str) + "\n")
        # Refresh this entry in cache
        self.refresh_experiment(experiment_id)

    # ── Video frame extraction ──────────────────────────────────────────────

    def extract_frame(
        self,
        experiment_id: str,
        frame_index: Optional[int] = None,
    ) -> Optional[bytes]:
        """Extract a single video frame as JPEG bytes.

        If frame_index is None, extracts the middle frame.
        Returns None if video is unavailable.
        """
        import cv2
        import numpy as np

        summary = self.get_experiment(experiment_id)
        if not summary or not summary.video_path:
            return None

        vp = Path(summary.video_path)
        if not vp.exists():
            return None

        cap = cv2.VideoCapture(str(vp))
        if not cap.isOpened():
            return None

        try:
            total = summary.frame_count or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total <= 0:
                return None

            idx = frame_index if frame_index is not None else total // 2
            idx = max(0, min(idx, total - 1))

            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                return None

            # Encode as JPEG
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                return None
            return bytes(buf)
        finally:
            cap.release()

    # ── Aggregate stats ─────────────────────────────────────────────────────

    def count_by_task(self) -> Dict[str, int]:
        """Return experiment counts per task_id."""
        self._ensure_cache()
        counts: Dict[str, int] = {}
        for exp in self._cache.values():
            counts[exp.task_id] = counts.get(exp.task_id, 0) + 1
        return dict(sorted(counts.items()))

    def list_subjects(self) -> List[Dict[str, Any]]:
        """Return unique subjects with their metadata and experiment counts."""
        self._ensure_cache()
        subjects: Dict[str, Dict[str, Any]] = {}
        for exp in self._cache.values():
            sid = exp.subject_id
            if sid not in subjects:
                subjects[sid] = {
                    "subject_id": sid,
                    "genotype": exp.genotype,
                    "sex": exp.sex,
                    "experiment_count": 0,
                    "task_ids": set(),
                }
            subjects[sid]["experiment_count"] += 1
            subjects[sid]["task_ids"].add(exp.task_id)

        result = []
        for s in sorted(subjects.values(), key=lambda x: x["subject_id"]):
            s["task_ids"] = sorted(s["task_ids"])
            result.append(s)
        return result
