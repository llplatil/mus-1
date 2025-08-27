"""
Core Package for MUS1
Exposes main functionalities: data models, managers, etc.
"""

from .metadata import (
    init_metadata,
    SubjectMetadata,
    ExperimentMetadata,
    BatchMetadata,
    ProjectState,
    ProjectMetadata,
    ObjectMetadata,
    BodyPartMetadata
)

from .state_manager import StateManager
from .data_manager import DataManager
from .project_manager import ProjectManager
from .plugin_manager import PluginManager

__all__ = [
    "init_metadata",
    "SubjectMetadata",
    "ExperimentMetadata",
    "BatchMetadata",
    "ProjectState",
    "ProjectMetadata",
    "ObjectMetadata",
    "BodyPartMetadata",

    "StateManager",
    "DataManager",
    "ProjectManager",
    "PluginManager"
] 