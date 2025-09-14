"""
Configuration Migration System for MUS1

This module handles migration from the old scattered configuration system
to the new unified ConfigManager-based system.

Author: Assistant
Date: 2025-09-14
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import platform

from .config_manager import ConfigManager, get_config_manager

logger = logging.getLogger("mus1.core.config_migration")


@dataclass
class MigrationResult:
    """Result of a configuration migration."""
    success: bool
    migrated_keys: int = 0
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class ConfigMigrationManager:
    """
    Manages migration from old configuration system to new unified system.
    """

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or get_config_manager()
        self.migration_applied = set()

    def migrate_all(self) -> MigrationResult:
        """
        Run all available migrations in order.
        """
        logger.info("Starting configuration migration...")

        result = MigrationResult(success=True)

        # Run migrations in order of dependency
        migrations = [
            self._migrate_user_config,
            self._migrate_lab_configs,
            self._migrate_project_configs,
            self._migrate_environment_variables,
            self._migrate_theme_settings,
        ]

        for migration in migrations:
            try:
                migration_result = migration()
                result.migrated_keys += migration_result.migrated_keys
                result.errors.extend(migration_result.errors)
                result.warnings.extend(migration_result.warnings)

                if not migration_result.success:
                    result.success = False
                    break

            except Exception as e:
                logger.error(f"Migration failed: {e}", exc_info=True)
                result.errors.append(f"Migration error: {e}")
                result.success = False
                break

        if result.success:
            logger.info(f"Migration completed successfully. Migrated {result.migrated_keys} configuration keys.")
        else:
            logger.error("Migration failed with errors.")

        return result

    def _migrate_user_config(self) -> MigrationResult:
        """Migrate user-level configuration files."""
        result = MigrationResult(success=True)

        # Find potential user config locations
        config_paths = self._find_user_config_files()

        for config_path in config_paths:
            try:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                elif config_path.suffix.lower() == '.json':
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    continue

                # Migrate specific known keys
                migrated = self._migrate_user_config_data(data)
                result.migrated_keys += migrated

            except Exception as e:
                result.errors.append(f"Failed to migrate {config_path}: {e}")

        return result

    def _find_user_config_files(self) -> List[Path]:
        """Find user configuration files in standard locations."""
        config_files = []

        # Check standard config directories
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
            config_dirs = [Path(appdata) / "mus1"]
        elif os.name == "posix":  # macOS/Linux
            if platform.system() == "Darwin":
                config_dirs = [
                    Path.home() / "Library/Application Support/mus1",
                    Path.home() / ".mus1"
                ]
            else:
                xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
                config_dirs = [Path(xdg_config) / "mus1", Path.home() / ".mus1"]
        else:
            config_dirs = [Path.home() / ".mus1"]

        for config_dir in config_dirs:
            if config_dir.exists():
                # Look for config files
                for pattern in ["config.yaml", "config.yml", "config.json", "settings.yaml", "settings.json"]:
                    config_file = config_dir / pattern
                    if config_file.exists():
                        config_files.append(config_file)

        return config_files

    def _migrate_user_config_data(self, data: Dict[str, Any]) -> int:
        """Migrate user configuration data to new system."""
        migrated_count = 0

        # Migrate known configuration keys
        key_mappings = {
            'projects_root': 'paths.projects_root',
            'shared_root': 'paths.shared_root',
            'labs_root': 'paths.labs_root',
            'theme_mode': 'ui.theme',
            'global_frame_rate': 'processing.frame_rate',
            'global_frame_rate_enabled': 'processing.frame_rate_enabled',
            'global_sort_mode': 'ui.sort_mode',
        }

        for old_key, new_key in key_mappings.items():
            if old_key in data:
                value = data[old_key]
                self.config_manager.set(new_key, value, scope="user")
                migrated_count += 1
                logger.debug(f"Migrated user config {old_key} -> {new_key}")

        # Migrate nested configurations
        if 'plugin_styling' in data:
            self.config_manager.set('plugins.styling', data['plugin_styling'], scope="user")
            migrated_count += 1

        if 'data_sources' in data:
            self.config_manager.set('data.sources', data['data_sources'], scope="user")
            migrated_count += 1

        return migrated_count

    def _migrate_lab_configs(self) -> MigrationResult:
        """Migrate lab configuration files."""
        result = MigrationResult(success=True)

        # Find lab config directories
        lab_dirs = self._find_lab_directories()

        for lab_dir in lab_dirs:
            try:
                # Look for lab config files
                for config_file in lab_dir.glob("*.yaml"):
                    if config_file.is_file():
                        with open(config_file, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f) or {}

                        migrated = self._migrate_lab_config_data(data, config_file.stem)
                        result.migrated_keys += migrated

                for config_file in lab_dir.glob("*.json"):
                    if config_file.is_file():
                        with open(config_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        migrated = self._migrate_lab_config_data(data, config_file.stem)
                        result.migrated_keys += migrated

            except Exception as e:
                result.errors.append(f"Failed to migrate lab config in {lab_dir}: {e}")

        return result

    def _find_lab_directories(self) -> List[Path]:
        """Find lab configuration directories."""
        lab_dirs = []

        # Check standard lab directories
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
            lab_dirs.append(Path(appdata) / "mus1" / "labs")
        elif os.name == "posix":  # macOS/Linux
            if platform.system() == "Darwin":
                lab_dirs.extend([
                    Path.home() / "Library/Application Support/mus1/labs",
                    Path.home() / ".mus1/labs"
                ])
            else:
                xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
                lab_dirs.extend([
                    Path(xdg_config) / "mus1/labs",
                    Path.home() / ".mus1/labs"
                ])

        return [d for d in lab_dirs if d.exists() and d.is_dir()]

    def _migrate_lab_config_data(self, data: Dict[str, Any], lab_id: str) -> int:
        """Migrate lab configuration data to new system."""
        migrated_count = 0

        # Set the lab context
        self.config_manager.set_scope_path("lab", Path(f"lab:{lab_id}"))

        # Migrate metadata
        if 'metadata' in data:
            metadata = data['metadata']
            for key, value in metadata.items():
                self.config_manager.set(f"lab.metadata.{key}", value, scope="lab")
                migrated_count += 1

        # Migrate workers
        if 'workers' in data:
            self.config_manager.set("lab.workers", data['workers'], scope="lab")
            migrated_count += 1

        # Migrate credentials
        if 'credentials' in data:
            self.config_manager.set("lab.credentials", data['credentials'], scope="lab")
            migrated_count += 1

        # Migrate genotypes
        if 'genotypes' in data:
            self.config_manager.set("lab.genotypes", data['genotypes'], scope="lab")
            migrated_count += 1

        # Migrate treatments
        if 'tracked_treatments' in data:
            self.config_manager.set("lab.tracked_treatments", data['tracked_treatments'], scope="lab")
            migrated_count += 1

        # Migrate experiment types
        if 'tracked_experiment_types' in data:
            self.config_manager.set("lab.tracked_experiment_types", data['tracked_experiment_types'], scope="lab")
            migrated_count += 1

        # Migrate shared storage
        if 'shared_storage' in data:
            self.config_manager.set("lab.shared_storage", data['shared_storage'], scope="lab")
            migrated_count += 1

        logger.debug(f"Migrated lab config for {lab_id}: {migrated_count} keys")
        return migrated_count

    def _migrate_project_configs(self) -> MigrationResult:
        """Migrate project configuration files."""
        result = MigrationResult(success=True)

        # Find project directories
        project_dirs = self._find_project_directories()

        for project_dir in project_dirs:
            try:
                config_file = project_dir / "project_state.json"
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    migrated = self._migrate_project_config_data(data, project_dir)
                    result.migrated_keys += migrated

            except Exception as e:
                result.errors.append(f"Failed to migrate project config in {project_dir}: {e}")

        return result

    def _find_project_directories(self) -> List[Path]:
        """Find project directories."""
        project_dirs = []

        # Check configured project roots
        roots = [
            os.environ.get("MUS1_PROJECTS_DIR"),
            self.config_manager.get("paths.projects_root"),
            self.config_manager.get("paths.shared_root"),
        ]

        # Add default locations
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
            roots.extend([
                str(Path(appdata) / "mus1" / "projects"),
                str(Path.home() / "MUS1" / "projects")
            ])
        else:  # macOS/Linux
            roots.extend([
                str(Path.home() / ".mus1" / "projects"),
                str(Path.home() / "MUS1" / "projects")
            ])

        for root_str in roots:
            if root_str:
                root = Path(root_str).expanduser()
                if root.exists() and root.is_dir():
                    # Find all subdirectories that contain project_state.json
                    for item in root.iterdir():
                        if item.is_dir() and (item / "project_state.json").exists():
                            project_dirs.append(item)

        return project_dirs

    def _migrate_project_config_data(self, data: Dict[str, Any], project_dir: Path) -> int:
        """Migrate project configuration data to new system."""
        migrated_count = 0

        # Set the project context
        self.config_manager.set_scope_path("project", project_dir)

        # Migrate project metadata
        if 'project_metadata' in data:
            metadata = data['project_metadata']
            for key, value in metadata.items():
                if key in ['project_name', 'date_created', 'lab_id']:
                    self.config_manager.set(f"project.metadata.{key}", value, scope="project")
                    migrated_count += 1

                elif key in ['master_body_parts', 'active_body_parts', 'master_tracked_objects', 'active_tracked_objects']:
                    self.config_manager.set(f"project.{key}", value, scope="project")
                    migrated_count += 1

                elif key in ['master_treatments', 'active_treatments', 'master_genotypes', 'active_genotypes']:
                    self.config_manager.set(f"project.{key}", value, scope="project")
                    migrated_count += 1

                elif key in ['tracked_genotypes', 'tracked_experiment_types', 'tracked_treatments']:
                    self.config_manager.set(f"project.{key}", value, scope="project")
                    migrated_count += 1

        # Migrate global settings
        if 'settings' in data:
            settings = data['settings']
            for key, value in settings.items():
                if key.startswith('global_'):
                    # Map global_ prefixed keys
                    new_key = key.replace('global_', '').replace('_', '.')
                    self.config_manager.set(f"project.{new_key}", value, scope="project")
                else:
                    self.config_manager.set(f"project.settings.{key}", value, scope="project")
                migrated_count += 1

        logger.debug(f"Migrated project config for {project_dir.name}: {migrated_count} keys")
        return migrated_count

    def _migrate_environment_variables(self) -> MigrationResult:
        """Migrate relevant environment variables."""
        result = MigrationResult(success=True)
        migrated_count = 0

        # Environment variables to migrate
        env_mappings = {
            'MUS1_PROJECTS_DIR': 'paths.projects_root',
            'MUS1_SHARED_DIR': 'paths.shared_root',
            'MUS1_LABS_DIR': 'paths.labs_root',
            'MUS1_SHARED_STORAGE_MOUNT': 'lab.shared_storage.mount_point',
            'MUS1_ACTIVE_LAB': 'lab.active_lab',
        }

        for env_var, config_key in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                # Determine scope based on key
                if config_key.startswith('lab.'):
                    scope = "lab"
                else:
                    scope = "user"

                self.config_manager.set(config_key, value, scope=scope)
                migrated_count += 1
                logger.debug(f"Migrated env var {env_var} -> {config_key}")

        result.migrated_keys = migrated_count
        return result

    def _migrate_theme_settings(self) -> MigrationResult:
        """Migrate theme-related settings from various locations."""
        result = MigrationResult(success=True)
        migrated_count = 0

        # Try to find theme settings in various locations
        theme_files = self._find_theme_files()

        for theme_file in theme_files:
            try:
                with open(theme_file, 'r', encoding='utf-8') as f:
                    if theme_file.suffix.lower() in ['.yaml', '.yml']:
                        data = yaml.safe_load(f) or {}
                    else:
                        data = json.load(f)

                # Extract theme settings
                if 'theme_mode' in data:
                    self.config_manager.set('ui.theme', data['theme_mode'], scope="user")
                    migrated_count += 1

                if 'theme_colors' in data:
                    self.config_manager.set('ui.theme_colors', data['theme_colors'], scope="user")
                    migrated_count += 1

            except Exception as e:
                result.errors.append(f"Failed to migrate theme from {theme_file}: {e}")

        result.migrated_keys = migrated_count
        return result

    def _find_theme_files(self) -> List[Path]:
        """Find theme configuration files."""
        theme_files = []

        # Check theme directories
        theme_dirs = [
            Path(__file__).parent.parent / "themes",
        ]

        # Add user theme directories
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
            theme_dirs.append(Path(appdata) / "mus1" / "themes")
        else:  # macOS/Linux
            theme_dirs.extend([
                Path.home() / ".mus1" / "themes",
                Path.home() / "Library/Application Support/mus1/themes"
            ])

        for theme_dir in theme_dirs:
            if theme_dir.exists():
                for pattern in ["theme.yaml", "theme.json", "themes.yaml", "themes.json"]:
                    theme_file = theme_dir / pattern
                    if theme_file.exists():
                        theme_files.append(theme_file)

        return theme_files

    def create_backup(self, backup_dir: Optional[Path] = None) -> Path:
        """Create a backup of current configuration state."""
        if backup_dir is None:
            backup_dir = Path.home() / ".mus1" / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = Path(datetime.now().strftime("%Y%m%d_%H%M%S"))
        backup_path = backup_dir / f"config_backup_{timestamp}.json"

        # Export all configuration
        all_config = {}
        for scope_name, scope in self.config_manager.get_all_scopes().items():
            all_config[scope_name] = scope.data

        with open(backup_path, 'w') as f:
            json.dump(all_config, f, indent=2, default=str)

        logger.info(f"Configuration backup created at {backup_path}")
        return backup_path

    def restore_backup(self, backup_path: Path) -> MigrationResult:
        """Restore configuration from a backup."""
        result = MigrationResult(success=True)

        try:
            with open(backup_path, 'r') as f:
                backup_data = json.load(f)

            for scope_name, scope_data in backup_data.items():
                if scope_name in self.config_manager._scopes:
                    # Clear existing data
                    self.config_manager._clear_scope_data(scope_name)
                    # Import backup data
                    self.config_manager._import_nested_data(scope_name, scope_data, "")
                    result.migrated_keys += len(scope_data)

        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to restore backup: {e}")

        return result
