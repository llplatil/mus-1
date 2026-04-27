"""FastAPI application factory.

Creates the app with all services wired up via dependency injection.
Services are singletons scoped to the app lifetime.

Usage::

    # From CLI
    mus1 serve --data-root /path/to/data

    # Programmatic
    from mus1.server.app import create_app
    app = create_app(data_root=Path("/path/to/data/experiment_data"))
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mus1.server.deps import ServiceContainer
from mus1.server.routers import tasks, experiments, cohorts, qc, annotations, compute


def create_app(
    data_root: Optional[Path] = None,
    cohorts_dir: Optional[Path] = None,
    title: str = "mus1",
    version: str = "0.1.0",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    data_root : Path
        Path to ``experiment_data/`` directory containing task subdirs.
    cohorts_dir : Path, optional
        Path to ``cohorts/`` directory. Defaults to sibling of data_root's parent.
    """
    app = FastAPI(
        title=title,
        version=version,
        description="Rodent behavioral experiment management API",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Wire up services
    container = ServiceContainer(
        data_root=data_root,
        cohorts_dir=cohorts_dir,
    )
    app.state.container = container

    # Register routers
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(experiments.router, prefix="/api/experiments", tags=["experiments"])
    app.include_router(cohorts.router, prefix="/api/cohorts", tags=["cohorts"])
    app.include_router(qc.router, prefix="/api/qc", tags=["qc"])
    app.include_router(annotations.router, prefix="/api/annotations", tags=["annotations"])
    app.include_router(compute.router, prefix="/api/compute", tags=["compute"])

    @app.get("/api/health")
    def health():
        c = container
        return {
            "status": "ok",
            "data_root": str(c.data_root),
            "experiment_count": len(c.experiment_service.list_experiments()),
            "task_ids": c.task_registry.list_ids(),
        }

    return app
