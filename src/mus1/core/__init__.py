"""
Clean Core Package for MUS1
Exposes simplified functionalities using the new architecture.
"""

# Import clean domain models and DTOs
from .metadata import (
    # Enums
    Sex, ProcessingStage, SubjectDesignation, InheritancePattern, WorkerProvider, ScanTargetKind,
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

# Keep existing config system (it's already clean)
from .config_manager import (
    ConfigManager,
    get_config_manager,
    init_config_manager,
    get_config,
    set_config,
    delete_config
)

# Clean plugin system (imported separately to avoid circular imports)
# from .plugin_manager_clean import PluginManagerClean, PluginService

__all__ = [
    # Enums
    "Sex", "ProcessingStage", "SubjectDesignation", "InheritancePattern", "WorkerProvider", "ScanTargetKind",
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
    # Config system
    "ConfigManager", "get_config_manager", "init_config_manager",
    "get_config", "set_config", "delete_config",
    # Clean plugin system (commented out to avoid circular imports)
    # "PluginManagerClean", "PluginService"
] 