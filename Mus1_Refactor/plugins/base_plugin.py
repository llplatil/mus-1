from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from core.metadata import ExperimentMetadata, ProjectState

class BasePlugin(ABC):
    @abstractmethod
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform plugin-specific validations for the experiment."""
        pass

    @abstractmethod
    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Run experiment-specific analysis and return the results."""
        pass


class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}

    def register_plugin(self, experiment_type: str, plugin: BasePlugin) -> None:
        self._plugins[experiment_type] = plugin

    def get_plugin(self, experiment_type: str) -> Optional[BasePlugin]:
        return self._plugins.get(experiment_type)

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        plugin = self.get_plugin(experiment.type.value)
        if plugin:
            plugin.validate_experiment(experiment, project_state)

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        plugin = self.get_plugin(experiment.type.value)
        if plugin:
            return plugin.analyze_experiment(experiment)
        return {} 