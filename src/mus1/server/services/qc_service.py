"""QC flag management service.

Wraps the existing ``qc_flags_shared.py`` with task-registry awareness:
auto-flag computation is delegated to the task definition rather than
being hardcoded per task type.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mus1.server.services.experiment_service import ExperimentService
from mus1.tasks.registry import TaskRegistry
from mus1.web.qc_flags_shared import (
    VALID_STATUSES,
    read_qc_flags,
    save_qc_flags_to_json,
    set_auto_flags,
    set_notes,
    set_status,
)

logger = logging.getLogger(__name__)


class QCService:
    """QC flag read/write with task-aware auto-flag computation."""

    def __init__(
        self,
        experiment_service: ExperimentService,
        task_registry: TaskRegistry,
    ):
        self._exp_svc = experiment_service
        self._tasks = task_registry

    def get_qc_flags(self, experiment_id: str) -> Dict[str, Any]:
        """Return the qc_flags block for an experiment."""
        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            raise KeyError(f"Experiment not found: {experiment_id!r}")
        return read_qc_flags(data)

    def set_status(
        self,
        experiment_id: str,
        new_status: str,
        by: str = "app",
        detail: str = "",
    ) -> Dict[str, Any]:
        """Set QC review status and persist to JSON."""
        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            raise KeyError(f"Experiment not found: {experiment_id!r}")

        qf = read_qc_flags(data)
        set_status(qf, new_status, by=by, detail=detail)
        data["qc_flags"] = qf
        self._exp_svc.save_experiment_json(experiment_id, data)
        return qf

    def set_notes(
        self,
        experiment_id: str,
        notes: str,
        by: str = "app",
    ) -> Dict[str, Any]:
        """Update free-text QC notes."""
        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            raise KeyError(f"Experiment not found: {experiment_id!r}")

        qf = read_qc_flags(data)
        set_notes(qf, notes, by=by)
        data["qc_flags"] = qf
        self._exp_svc.save_experiment_json(experiment_id, data)
        return qf

    def compute_auto_flags(self, experiment_id: str) -> List[str]:
        """Compute auto-flags using the task definition.

        Delegates to ``TaskDefinition.compute_auto_flags()`` instead of
        hardcoded per-task logic.
        """
        summary = self._exp_svc.get_experiment(experiment_id)
        if not summary:
            raise KeyError(f"Experiment not found: {experiment_id!r}")

        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            return []

        task_def = self._tasks.get_or_none(summary.task_id)
        if task_def:
            return task_def.compute_auto_flags(data)
        return []

    def recompute_and_save_auto_flags(
        self,
        experiment_id: str,
        by: str = "auto",
    ) -> Dict[str, Any]:
        """Recompute auto-flags and persist to JSON."""
        data = self._exp_svc.get_experiment_json(experiment_id)
        if not data:
            raise KeyError(f"Experiment not found: {experiment_id!r}")

        summary = self._exp_svc.get_experiment(experiment_id)
        task_def = self._tasks.get_or_none(summary.task_id) if summary else None
        flags = task_def.compute_auto_flags(data) if task_def else []

        qf = read_qc_flags(data)
        set_auto_flags(qf, flags, by=by)
        data["qc_flags"] = qf
        self._exp_svc.save_experiment_json(experiment_id, data)
        return qf

    def batch_compute_auto_flags(
        self,
        experiment_ids: List[str],
        by: str = "auto",
    ) -> Dict[str, List[str]]:
        """Recompute auto-flags for multiple experiments.

        Returns a dict mapping experiment_id to computed flags.
        """
        results = {}
        for eid in experiment_ids:
            try:
                flags = self.compute_auto_flags(eid)
                results[eid] = flags
            except KeyError:
                logger.warning("Skipping unknown experiment: %s", eid)
        return results
