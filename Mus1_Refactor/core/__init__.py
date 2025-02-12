"""
Core Package for MUS1
Exposes main functionalities: data models, managers, etc.
"""

from .metadata import (
    init_metadata,
    MouseMetadata,
    ExperimentMetadata,
    BatchMetadata,
    ProjectState,
    ProjectMetadata
)

from .state_manager import StateManager
from .data_manager import DataManager
from .project_manager import ProjectManager

__all__ = [
    "init_metadata",
    "MouseMetadata",
    "ExperimentMetadata",
    "BatchMetadata",
    "ProjectState",
    "ProjectMetadata",

    "StateManager",
    "DataManager",
    "ProjectManager"
] 