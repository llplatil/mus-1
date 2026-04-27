"""Dependency injection container and FastAPI dependency functions."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Request

from mus1.server.services.annotation_service import AnnotationService
from mus1.server.services.cohort_service import CohortService
from mus1.server.services.experiment_service import ExperimentService
from mus1.server.services.qc_service import QCService
from mus1.tasks.registry import TaskRegistry


class ServiceContainer:
    """Holds all singleton services for the app lifetime."""

    def __init__(
        self,
        data_root: Optional[Path] = None,
        cohorts_dir: Optional[Path] = None,
    ):
        self.data_root = Path(data_root) if data_root else Path(".")
        if cohorts_dir:
            self._cohorts_dir = Path(cohorts_dir)
        else:
            # Default: sibling directory data_root/../cohorts
            self._cohorts_dir = self.data_root.parent / "cohorts"

        self.task_registry = TaskRegistry()
        self.experiment_service = ExperimentService(self.data_root, self.task_registry)
        self.cohort_service = CohortService(self._cohorts_dir, self.experiment_service)
        self.qc_service = QCService(self.experiment_service, self.task_registry)
        self.annotation_service = AnnotationService(self.experiment_service, self.task_registry)


def get_container(request: Request) -> ServiceContainer:
    """FastAPI dependency: retrieve the service container from app state."""
    return request.app.state.container


def get_experiment_service(request: Request) -> ExperimentService:
    return get_container(request).experiment_service


def get_cohort_service(request: Request) -> CohortService:
    return get_container(request).cohort_service


def get_qc_service(request: Request) -> QCService:
    return get_container(request).qc_service


def get_annotation_service(request: Request) -> AnnotationService:
    return get_container(request).annotation_service


def get_task_registry(request: Request) -> TaskRegistry:
    return get_container(request).task_registry
