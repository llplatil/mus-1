"""Task registry: discovers and holds all registered TaskDefinitions.

The registry loads built-in tasks automatically and can load additional
user-defined tasks from a YAML config file (``mus1_tasks.yaml``). This
allows AI agents or lab administrators to define new behavioral tasks
without modifying Python code.

YAML task config example::

    tasks:
      - id: "MWM"
        display_name: "Morris Water Maze"
        arena_type: "circular"
        arena_physical_dimensions:
          diameter_mm: 1200.0
        annotation_fields:
          - name: "platform_center"
            label: "Platform Center"
            field_type: "point"
          - name: "arena_boundary"
            label: "Arena Boundary"
            field_type: "ellipse"
        objects:
          - name: "platform"
            label: "Hidden Platform"
            role: "target"
        qc_flag_vocabulary:
          - LOW_TRACKING
          - PLATFORM_NOT_VISIBLE
        group_labels: ["WT", "TG"]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from mus1.tasks.base import TaskDefinition, YAMLTaskDefinition

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Discovers and holds all registered TaskDefinitions."""

    def __init__(self, *, load_builtins: bool = True):
        self._tasks: Dict[str, TaskDefinition] = {}
        if load_builtins:
            self._load_builtins()

    def _load_builtins(self) -> None:
        from mus1.tasks.builtins import ALL_BUILTINS
        for task_cls in ALL_BUILTINS:
            task = task_cls()
            self.register(task)

    def register(self, task: TaskDefinition) -> None:
        """Register a task definition. Overwrites if task_id already exists."""
        tid = task.task_id
        if tid in self._tasks:
            logger.info("Overwriting task definition for %r", tid)
        self._tasks[tid] = task

    def get(self, task_id: str) -> TaskDefinition:
        """Get a task definition by ID. Raises KeyError if not found."""
        try:
            return self._tasks[task_id]
        except KeyError:
            available = sorted(self._tasks.keys())
            raise KeyError(
                f"Unknown task_id {task_id!r}. "
                f"Available: {available}"
            ) from None

    def get_or_none(self, task_id: str) -> Optional[TaskDefinition]:
        """Get a task definition by ID, or None if not found."""
        return self._tasks.get(task_id)

    def list_all(self) -> List[TaskDefinition]:
        """Return all registered task definitions, sorted by task_id."""
        return sorted(self._tasks.values(), key=lambda t: t.task_id)

    def list_ids(self) -> List[str]:
        """Return all registered task IDs, sorted."""
        return sorted(self._tasks.keys())

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._tasks

    def __len__(self) -> int:
        return len(self._tasks)

    # ── YAML loading ────────────────────────────────────────────────────────

    def load_from_yaml(self, yaml_path: Path) -> int:
        """Load user-defined tasks from a YAML config file.

        Returns the number of tasks loaded.
        """
        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            logger.debug("Tasks YAML not found at %s, skipping", yaml_path)
            return 0

        with open(yaml_path, "r") as f:
            config = yaml.safe_load(f)

        if not config or "tasks" not in config:
            logger.warning("Tasks YAML at %s has no 'tasks' key", yaml_path)
            return 0

        count = 0
        for task_config in config["tasks"]:
            if "id" not in task_config:
                logger.warning("Skipping task config without 'id': %s", task_config)
                continue
            task = YAMLTaskDefinition(task_config)
            self.register(task)
            count += 1
            logger.info("Loaded YAML task: %s (%s)", task.task_id, task.display_name)

        return count

    # ── Factory ─────────────────────────────────────────────────────────────

    @classmethod
    def from_config(
        cls,
        tasks_yaml_path: Optional[Path] = None,
        load_builtins: bool = True,
    ) -> "TaskRegistry":
        """Create a registry with builtins + optional YAML config."""
        registry = cls(load_builtins=load_builtins)
        if tasks_yaml_path:
            registry.load_from_yaml(tasks_yaml_path)
        return registry
