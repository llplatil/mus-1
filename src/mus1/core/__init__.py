"""
Clean Core Package for MUS1
Exposes simplified functionalities using the new architecture.
"""

# Import clean domain models and DTOs
from .metadata import (
    # Enums
    Sex, ProcessingStage, InheritancePattern, WorkerProvider, ScanTargetKind,
    # Domain Models
    PluginMetadata, Subject, Experiment, VideoFile, Worker, ScanTarget,
    # DTOs
    SubjectDTO, ExperimentDTO, VideoFileDTO, WorkerDTO, ScanTargetDTO,
    # Simple Config
    ProjectConfig,
    # Utilities
    validate_subject_id, validate_experiment_id
)

# Import clean services and managers
from .project_manager_clean import ProjectManagerClean
from .repository import RepositoryFactory, SubjectRepository, ExperimentRepository
from .data_service import SubjectService, ExperimentService

# Keep existing config system (it's already clean)
from .config_manager import (
    ConfigManager,
    get_config_manager,
    init_config_manager,
    get_config,
    set_config,
    delete_config
)
from .config_migration import ConfigMigrationManager
from .theme_manager import ThemeManager

# Clean plugin system
from .plugin_manager_clean import PluginManagerClean, PluginService

__all__ = [
    # Enums
    "Sex", "ProcessingStage", "InheritancePattern", "WorkerProvider", "ScanTargetKind",
    # Domain Models
    "PluginMetadata", "Subject", "Experiment", "VideoFile", "Worker", "ScanTarget",
    # DTOs
    "SubjectDTO", "ExperimentDTO", "VideoFileDTO", "WorkerDTO", "ScanTargetDTO",
    # Config
    "ProjectConfig",
    # Utilities
    "validate_subject_id", "validate_experiment_id",
    # Services
    "ProjectManagerClean", "RepositoryFactory", "SubjectRepository", "ExperimentRepository",
    "SubjectService", "ExperimentService",
    # Config system
    "ConfigManager", "get_config_manager", "init_config_manager",
    "get_config", "set_config", "delete_config", "ConfigMigrationManager",
    # Theme system
    "ThemeManager",
    # Clean plugin system
    "PluginManagerClean", "PluginService"
] 