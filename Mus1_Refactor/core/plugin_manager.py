from typing import Optional, Dict, Any, List
from plugins.base_plugin import BasePlugin
from core.metadata import ExperimentMetadata, ProjectState, PluginMetadata


class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}

    def register_plugin(self, experiment_type: str, plugin: BasePlugin) -> None:
        """Register a plugin for the given experiment type."""
        self._plugins[experiment_type] = plugin

    def get_plugin(self, experiment_type: str) -> Optional[BasePlugin]:
        """Retrieve the plugin corresponding to the given experiment type."""
        return self._plugins.get(experiment_type)

    def get_supported_experiment_types(self) -> List[str]:
        """Get a list of supported experiment types for which plugins are registered."""
        return list(self._plugins.keys())

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Validate the given experiment using the appropriate plugin."""
        exp_type_str = experiment.type.value if hasattr(experiment.type, 'value') else str(experiment.type)
        plugin = self.get_plugin(exp_type_str)
        if not plugin:
            raise ValueError(f"No registered plugin found for experiment type '{exp_type_str}'")
        plugin.validate_experiment(experiment, project_state)

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Analyze the experiment using the corresponding plugin."""
        exp_type_str = experiment.type.value if hasattr(experiment.type, 'value') else str(experiment.type)
        plugin = self.get_plugin(exp_type_str)
        if plugin:
            return plugin.analyze_experiment(experiment)
        return {}

    def get_all_plugin_metadata(self) -> List[PluginMetadata]:
        """Retrieve metadata from all registered plugins."""
        return [plugin.plugin_self_metadata() for plugin in self._plugins.values()]
