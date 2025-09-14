"""
Unified MUS1 Application Initializer

This module provides a single, consistent initialization path for both GUI and CLI
applications, ensuring identical core setup regardless of user interface choice.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Tuple

from .metadata import init_metadata
from .state_manager import StateManager
from .plugin_manager import PluginManager
from .data_manager import DataManager
from .project_manager import ProjectManager
from .theme_manager import ThemeManager
from .logging_bus import LoggingEventBus
from .config_manager import init_config_manager, get_config_manager
from .config_migration import ConfigMigrationManager


class MUS1AppInitializer:
    """Unified initializer for MUS1 applications (GUI and CLI)."""

    def __init__(self):
        self.logger = logging.getLogger('mus1')
        self._managers = None
        self._logging_initialized = False
        self._metadata_initialized = False

    def initialize_logging(self, log_file: Optional[Path] = None) -> None:
        """Initialize logging with rotating file handler."""
        if self._logging_initialized:
            return

        # Set logger level
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        # Create formatter - consistent across GUI and CLI
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Remove existing handlers to prevent duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()

        # Configure RotatingFileHandler
        if log_file is None:
            log_file = Path(__file__).parent.parent / "mus1.log"

        max_bytes = 5 * 1024 * 1024  # 5 MB
        backup_count = 3

        try:
            file_handler = logging.handlers.RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            # Fallback to basic console logging
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
            )
            self.logger.error(f"Failed to set up rotating file log handler: {e}. Falling back to basic config.", exc_info=True)

        self._logging_initialized = True

    def initialize_metadata(self) -> bool:
        """Initialize the metadata system."""
        if self._metadata_initialized:
            return True

        success = init_metadata()
        if success:
            self._metadata_initialized = True
        else:
            self.logger.error("Metadata initialization failed")
        return success

    def initialize_core_managers(self) -> Tuple[StateManager, PluginManager, DataManager, ProjectManager, ThemeManager]:
        """Initialize all core managers with consistent setup."""
        if self._managers is not None:
            return self._managers

        # Create managers in dependency order
        state_manager = StateManager()
        plugin_manager = PluginManager()
        data_manager = DataManager(state_manager, plugin_manager)

        # Initialize lab manager for project manager
        from .lab_manager import LabManager
        lab_manager = LabManager()

        project_manager = ProjectManager(state_manager, plugin_manager, data_manager, lab_manager)
        theme_manager = ThemeManager(state_manager)

        # Discover external plugins via entry points
        try:
            plugin_manager.discover_entry_points()
            self.logger.info(f"Discovered {len(plugin_manager.get_plugins_with_project_actions())} plugin(s) with project actions")
        except Exception as e:
            self.logger.warning(f"Plugin discovery failed: {e}")

        self._managers = (state_manager, plugin_manager, data_manager, project_manager, theme_manager)
        return self._managers

    def initialize_config_system(self):
        """Initialize the unified configuration system."""
        try:
            # Initialize ConfigManager
            init_config_manager()
            config_manager = get_config_manager()

            # Run configuration migration if needed
            migration_manager = ConfigMigrationManager(config_manager)
            migration_result = migration_manager.migrate_all()

            if not migration_result.success:
                self.logger.warning(f"Configuration migration had issues: {migration_result.errors}")
            else:
                self.logger.info(f"Configuration migration completed: {migration_result.migrated_keys} keys migrated")

            # Set default configuration values if not already set
            self._set_default_config_values()

            self.logger.info("Configuration system initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize configuration system: {e}", exc_info=True)
            # Continue with basic defaults
            pass

    def _set_default_config_values(self):
        """Set default configuration values."""
        config_manager = get_config_manager()

        # Set default paths
        if not config_manager.get("paths.projects_root"):
            if sys.platform == "win32":
                default_projects = Path.home() / "MUS1" / "projects"
            else:
                default_projects = Path.home() / "MUS1" / "projects"
            config_manager.set("paths.projects_root", str(default_projects), scope="install")

        # Set default theme
        if not config_manager.get("ui.theme"):
            config_manager.set("ui.theme", "dark", scope="user")

        # Set default frame rate settings
        if not config_manager.get("processing.frame_rate"):
            config_manager.set("processing.frame_rate", 60, scope="install")

        if not config_manager.get("processing.frame_rate_enabled"):
            config_manager.set("processing.frame_rate_enabled", False, scope="user")

        # Set default sort mode
        if not config_manager.get("ui.sort_mode"):
            config_manager.set("ui.sort_mode", "Natural Order (Numbers as Numbers)", scope="user")

    def initialize_logging_bus(self) -> LoggingEventBus:
        """Initialize the logging event bus."""
        log_bus = LoggingEventBus.get_instance()
        log_bus.log("LoggingEventBus initialized", "info", "AppInitializer")
        return log_bus

    def initialize_complete_app(self, log_file: Optional[Path] = None) -> Tuple[
        StateManager, PluginManager, DataManager, ProjectManager, ThemeManager, LoggingEventBus
    ]:
        """
        Complete application initialization for both GUI and CLI.

        This ensures identical setup regardless of whether user launches GUI or CLI.
        """
        # Step 1: Initialize logging first
        self.initialize_logging(log_file)

        # Step 2: Initialize metadata system
        if not self.initialize_metadata():
            self.logger.error("Application initialization failed: metadata setup unsuccessful")
            sys.exit(1)

        # Step 3: Initialize unified configuration system
        self.initialize_config_system()

        # Step 4: Initialize logging event bus
        log_bus = self.initialize_logging_bus()

        # Step 5: Initialize all core managers
        state_manager, plugin_manager, data_manager, project_manager, theme_manager = self.initialize_core_managers()

        self.logger.info("MUS1 core initialization complete")

        return state_manager, plugin_manager, data_manager, project_manager, theme_manager, log_bus


# Global initializer instance
_initializer = None

def get_app_initializer() -> MUS1AppInitializer:
    """Get the global application initializer instance."""
    global _initializer
    if _initializer is None:
        _initializer = MUS1AppInitializer()
    return _initializer

def initialize_mus1_app(log_file: Optional[Path] = None) -> Tuple[
    StateManager, PluginManager, DataManager, ProjectManager, ThemeManager, LoggingEventBus
]:
    """
    Convenience function to initialize the complete MUS1 application.

    Returns all initialized managers and services needed by both GUI and CLI.
    """
    initializer = get_app_initializer()
    return initializer.initialize_complete_app(log_file)
