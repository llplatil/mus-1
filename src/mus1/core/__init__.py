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
from .app_initializer import (
    MUS1AppInitializer,
    get_app_initializer,
    initialize_mus1_app
)
from .plugin_manager import PluginManager
from .theme_manager import ThemeManager
from .config_manager import (
    ConfigManager,
    get_config_manager,
    init_config_manager,
    get_config,
    set_config,
    delete_config
)
from .config_migration import ConfigMigrationManager

__all__ = [
    "init_metadata",
    "SubjectMetadata",
    "ExperimentMetadata",
    "BatchMetadata",
    "ProjectState",
    "ProjectMetadata",
    "ObjectMetadata",
    "BodyPartMetadata",
    "MUS1AppInitializer",
    "get_app_initializer",
    "initialize_mus1_app",
    "PluginManager",
    "ThemeManager",
    "ConfigManager",
    "get_config_manager",
    "init_config_manager",
    "get_config",
    "set_config",
    "delete_config",
    "ConfigMigrationManager",
] 