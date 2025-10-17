"""
Service Factory Layer for MUS1.

This module provides standardized service instantiation patterns for MUS1.
Implements the ProjectServiceFactory pattern to centralize creation of
project-scoped services with proper dependency injection.
"""

from pathlib import Path
from typing import Optional

from .project_manager_clean import ProjectManagerClean
from .plugin_manager_clean import PluginManagerClean


class ProjectServiceFactory:
    """
    Central factory for project-scoped services.

    This factory standardizes the creation of project-related services,
    ensuring consistent dependency injection and lifecycle management.
    """

    def __init__(self, project_path: Path):
        """
        Initialize the project service factory.

        Args:
            project_path: Path to the project directory
        """
        self.project_path = project_path
        self._project_manager: Optional[ProjectManagerClean] = None
        self._plugin_manager: Optional[PluginManagerClean] = None
        self._gui_services: Optional[GUIServiceFactory] = None

    @property
    def project_manager(self) -> ProjectManagerClean:
        """Get or create the project manager instance."""
        if self._project_manager is None:
            self._project_manager = ProjectManagerClean(self.project_path)
        return self._project_manager

    @property
    def plugin_manager(self) -> PluginManagerClean:
        """Get or create the plugin manager instance."""
        if self._plugin_manager is None:
            self._plugin_manager = PluginManagerClean(self.project_manager.db)
        return self._plugin_manager

    @property
    def gui_services(self):
        """Get or create the GUI services factory."""
        if self._gui_services is None:
            from ..gui.gui_services import GUIServiceFactory
            self._gui_services = GUIServiceFactory(self.project_manager)
            self._gui_services.set_plugin_manager(self.plugin_manager)
        return self._gui_services

    def reset(self):
        """Reset all cached service instances. Useful for testing or project switching."""
        self._project_manager = None
        self._plugin_manager = None
        self._gui_services = None
