"""Cohort management service.

Thin wrapper around the existing ``web/cohorts.py`` module, using
ExperimentService for metadata resolution instead of raw disk I/O.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from mus1.server.services.experiment_service import ExperimentService

# Re-use the existing cohorts module (already framework-agnostic)
from mus1.web.cohorts import (
    add_member,
    cohort_member_ids,
    compute_cohort_summary,
    create_cohort,
    export_training_csv,
    list_cohorts,
    load_cohort,
    remove_member,
    save_cohort,
)

logger = logging.getLogger(__name__)


class CohortService:
    """Cohort CRUD with ExperimentService-backed metadata resolution."""

    def __init__(
        self,
        cohorts_dir: Path,
        experiment_service: ExperimentService,
    ):
        self._dir = Path(cohorts_dir)
        self._exp_svc = experiment_service

    def _build_experiment_lookup(self) -> Dict[str, Dict[str, str]]:
        """Build a lookup dict from ExperimentService cache."""
        lookup = {}
        for exp in self._exp_svc.list_experiments():
            lookup[exp.experiment_id] = {
                "experiment_id": exp.experiment_id,
                "task_type": exp.task_id,
                "subject_id": exp.subject_id,
                "genotype": exp.genotype,
                "sex": exp.sex,
                "date_recorded": exp.date_recorded,
            }
        return lookup

    # ── List / get ──────────────────────────────────────────────────────────

    def list_cohorts(self, task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return lightweight summaries for all cohort JSONs on disk."""
        return list_cohorts(self._dir, task_type=task_type)

    def get_cohort(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a cohort by name (stem of the JSON file)."""
        path = self._dir / f"{name}.json"
        if not path.exists():
            return None
        return load_cohort(path)

    def get_cohort_member_ids(self, name: str) -> Set[str]:
        """Return the set of experiment_ids in a named cohort."""
        cohort = self.get_cohort(name)
        if not cohort:
            return set()
        return cohort_member_ids(cohort)

    # ── Create / modify ─────────────────────────────────────────────────────

    def create_cohort(
        self,
        name: str,
        task_types: Optional[List[str]] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """Create a new cohort and save to disk."""
        cohort = create_cohort(name, task_types=task_types, description=description)
        path = self._dir / f"{name}.json"
        save_cohort(path, cohort, experiment_lookup=self._build_experiment_lookup())
        return cohort

    def add_member(self, name: str, experiment_id: str, notes: str = "") -> Dict[str, Any]:
        """Add an experiment to a cohort and save."""
        cohort = self.get_cohort(name)
        if not cohort:
            raise KeyError(f"Cohort not found: {name!r}")
        add_member(cohort, experiment_id, notes=notes)
        path = self._dir / f"{name}.json"
        save_cohort(path, cohort, experiment_lookup=self._build_experiment_lookup())
        return cohort

    def remove_member(self, name: str, experiment_id: str) -> Dict[str, Any]:
        """Remove an experiment from a cohort and save."""
        cohort = self.get_cohort(name)
        if not cohort:
            raise KeyError(f"Cohort not found: {name!r}")
        remove_member(cohort, experiment_id)
        path = self._dir / f"{name}.json"
        save_cohort(path, cohort, experiment_lookup=self._build_experiment_lookup())
        return cohort

    def refresh_summary(self, name: str) -> Dict[str, Any]:
        """Recompute the summary block for a cohort and save."""
        cohort = self.get_cohort(name)
        if not cohort:
            raise KeyError(f"Cohort not found: {name!r}")
        path = self._dir / f"{name}.json"
        save_cohort(path, cohort, experiment_lookup=self._build_experiment_lookup())
        return cohort
