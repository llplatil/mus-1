"""Core functionality for MUS1"""

# First ensure logging is available
from ...utils.logging_config import get_class_logger, get_logger
logger = get_logger("core")

# Import metadata classes first
from .metadata import (
    MouseMetadata,
    ExperimentMetadata,
    BatchMetadata,
    ProjectState
    #TODO: add TrackingData once its integrated in core
)

# Then import managers in dependency order
from .data_manager import DataManager
from .state_manager import StateManager
from .project_manager import ProjectManager

logger.debug("Core module initialization")

__all__ = [
    # Metadata classes
    'MouseMetadata',
    'ExperimentMetadata',
    'BatchMetadata',
    'ProjectState',
    
    # Managers
    'DataManager',
    'StateManager',
    'ProjectManager'
]

