from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

from core.metadata import ExperimentMetadata, ProjectState, PluginMetadata

class BasePlugin(ABC):
    @abstractmethod
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform plugin-specific validations for the experiment."""
        pass

    @abstractmethod
    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Run experiment-specific analysis and return the results."""
        pass

    @abstractmethod
    def plugin_self_metadata(self) -> PluginMetadata:
        """
        Return the PluginMetadata object that describes this plugin
        (name, creation_date, version, etc.).
        """
        pass


class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}

    def register_plugin(self, experiment_type: str, plugin: BasePlugin) -> None:
        self._plugins[experiment_type] = plugin

    def get_plugin(self, experiment_type: str) -> Optional[BasePlugin]:
        return self._plugins.get(experiment_type)

   
    def get_supported_experiment_types(self) -> List[str]:
        """
        Return a list of all experiment types for which a plugin is registered.
        """
        return list(self._plugins.keys())

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """
        Retrieve the plugin for experiment.type; raise an error if not found,
        otherwise delegate validation to that plugin.
        """
        # experiment.type might be an Enum or string, so .value if needed:
        exp_type_str = experiment.type.value if hasattr(experiment.type, 'value') else str(experiment.type)
        plugin = self.get_plugin(exp_type_str)
        if not plugin:
            raise ValueError(f"No registered plugin found for experiment type '{exp_type_str}'")

        plugin.validate_experiment(experiment, project_state)

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        plugin = self.get_plugin(experiment.type.value)
        if plugin:
            return plugin.analyze_experiment(experiment)
        return {}

    # ---------------------------------------------------------
    # NEW: method that returns an unsorted list of PluginMetadata
    # ---------------------------------------------------------
    def get_all_plugin_metadata(self) -> List[PluginMetadata]:
        """
        Gather plugin metadata from all registered plugins.
        """
        metadata_list = []
        for etype, plugin in self._plugins.items():
            metadata_list.append(plugin.plugin_self_metadata())
        return metadata_list 