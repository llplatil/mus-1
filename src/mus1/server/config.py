"""Project configuration for mus1.

Replaces the hardcoded path resolution in ``web/paths.py`` with a
declarative ``mus1.yaml`` config file. If no config file exists, sensible
defaults are used.

Config file example (``mus1.yaml`` in project root)::

    project_name: "My Lab"
    experiment_data_root: "data/experiment_data"
    cohorts_dir: "data/cohorts"
    db_path: "mus1.db"
    tasks_config: "mus1_tasks.yaml"
    tracking_backend: "dlc"
    group_labels:
      - name: "WT"
        display: "Wild Type"
      - name: "HET"
        display: "Heterozygous"
      - name: "KO"
        display: "Knockout"
    subjects_roster: "resources/metadata/subjects_roster.csv"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "mus1.yaml"


@dataclass(frozen=True)
class GroupLabel:
    """A named group label (e.g. genotype)."""
    name: str
    display: str = ""

    def __post_init__(self):
        if not self.display:
            object.__setattr__(self, "display", self.name)


@dataclass
class ProjectConfig:
    """Resolved project configuration.

    All paths are resolved to absolute paths relative to ``project_root``.
    """
    project_root: Path
    project_name: str = "mus1"

    # Data paths (relative to project_root, resolved on access)
    _experiment_data_root: str = "data/experiment_data"
    _cohorts_dir: str = "data/cohorts"
    _db_path: str = "mus1.db"
    _tasks_config: str = "mus1_tasks.yaml"
    _subjects_roster: str = ""

    # Tracking
    tracking_backend: str = "dlc"  # "dlc" | "sleap" | "custom"

    # Groups
    group_labels: List[GroupLabel] = field(default_factory=list)

    # ── Resolved paths ──────────────────────────────────────────────────────

    @property
    def experiment_data_root(self) -> Path:
        return self.project_root / self._experiment_data_root

    @property
    def cohorts_dir(self) -> Path:
        return self.project_root / self._cohorts_dir

    @property
    def db_path(self) -> Path:
        return self.project_root / self._db_path

    @property
    def tasks_config_path(self) -> Optional[Path]:
        p = self.project_root / self._tasks_config
        return p if p.exists() else None

    @property
    def subjects_roster_path(self) -> Optional[Path]:
        if not self._subjects_roster:
            return None
        p = self.project_root / self._subjects_roster
        return p if p.exists() else None

    # ── Discovery ───────────────────────────────────────────────────────────

    def discover_task_dirs(self) -> List[str]:
        """List task directories found under experiment_data_root."""
        root = self.experiment_data_root
        if not root.is_dir():
            return []
        return sorted(
            d.name for d in root.iterdir()
            if d.is_dir() and not d.name.startswith((".", "_"))
        )

    # ── Factory ─────────────────────────────────────────────────────────────

    @classmethod
    def from_path(cls, path: Path) -> "ProjectConfig":
        """Load config from a directory or mus1.yaml file.

        Resolution order:
        1. If path is a file named mus1.yaml, load it.
        2. If path is a directory, look for mus1.yaml inside it.
        3. If no config found, use defaults with path as project_root.

        The project_root is the directory containing mus1.yaml (or the
        given directory if no config exists).
        """
        path = Path(path).resolve()

        if path.is_file() and path.name == CONFIG_FILENAME:
            config_path = path
            project_root = path.parent
        elif path.is_dir():
            config_path = path / CONFIG_FILENAME
            project_root = path
        else:
            # path might be the project root even if mus1.yaml doesn't exist
            project_root = path if path.is_dir() else path.parent
            config_path = project_root / CONFIG_FILENAME

        if config_path.exists():
            return cls._load_yaml(config_path, project_root)
        else:
            logger.info(
                "No %s found at %s, using defaults",
                CONFIG_FILENAME,
                project_root,
            )
            return cls(project_root=project_root)

    @classmethod
    def _load_yaml(cls, config_path: Path, project_root: Path) -> "ProjectConfig":
        """Parse a mus1.yaml file into a ProjectConfig."""
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}

        group_labels = []
        for gl in raw.get("group_labels", []):
            if isinstance(gl, str):
                group_labels.append(GroupLabel(name=gl))
            elif isinstance(gl, dict):
                group_labels.append(GroupLabel(
                    name=gl["name"],
                    display=gl.get("display", ""),
                ))

        return cls(
            project_root=project_root,
            project_name=raw.get("project_name", "mus1"),
            _experiment_data_root=raw.get("experiment_data_root", "data/experiment_data"),
            _cohorts_dir=raw.get("cohorts_dir", "data/cohorts"),
            _db_path=raw.get("db_path", "mus1.db"),
            _tasks_config=raw.get("tasks_config", "mus1_tasks.yaml"),
            _subjects_roster=raw.get("subjects_roster", ""),
            tracking_backend=raw.get("tracking_backend", "dlc"),
            group_labels=group_labels,
        )

    def to_dict(self) -> dict:
        """Serialize config to dict (for API responses / debugging)."""
        return {
            "project_root": str(self.project_root),
            "project_name": self.project_name,
            "experiment_data_root": str(self.experiment_data_root),
            "cohorts_dir": str(self.cohorts_dir),
            "db_path": str(self.db_path),
            "tasks_config_path": str(self.tasks_config_path) if self.tasks_config_path else None,
            "tracking_backend": self.tracking_backend,
            "group_labels": [{"name": g.name, "display": g.display} for g in self.group_labels],
            "discovered_task_dirs": self.discover_task_dirs(),
        }
