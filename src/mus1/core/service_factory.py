from pathlib import Path
from typing import Optional

from .project_manager_clean import ProjectManagerClean
from .plugin_manager_clean import PluginManagerClean


class ProjectServiceFactory:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._project_manager: Optional[ProjectManagerClean] = None
        self._plugin_manager: Optional[PluginManagerClean] = None

    @property
    def project_manager(self) -> ProjectManagerClean:
        if self._project_manager is None:
            self._project_manager = ProjectManagerClean(self.project_path)
        return self._project_manager

    @property
    def plugin_manager(self) -> PluginManagerClean:
        if self._plugin_manager is None:
            self._plugin_manager = PluginManagerClean(self.project_manager.db)
        return self._plugin_manager

    def reset(self):
        self._project_manager = None
        self._plugin_manager = None
