from typing import Optional, Dict, Any, List
from plugins.base_plugin import BasePlugin
from core.metadata import ExperimentMetadata, ProjectState, PluginMetadata


class PluginManager:
    def __init__(self):
        self._plugins: List[BasePlugin] = []

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a plugin instance."""
        self._plugins.append(plugin)

    def get_all_plugins(self) -> List[BasePlugin]:
        return self._plugins

    def get_supported_experiment_types(self) -> List[str]:
        types = set()
        for plugin in self.get_all_plugins():
            meta = plugin.plugin_self_metadata()
            if meta.plugin_type:
                types.add(meta.plugin_type)
        return list(types)

    def get_plugins_by_experiment_type(self, exp_type: str) -> List[BasePlugin]:
        return [plugin for plugin in self.get_all_plugins() if plugin.plugin_self_metadata().plugin_type == exp_type]

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        plugins = self.get_plugins_by_experiment_type(experiment.type.value)
        if not plugins:
            raise ValueError(f"No plugin registered supporting experiment type '{experiment.type}'")
        plugin = plugins[0]
        plugin.validate_experiment(experiment, project_state)

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        plugins = self.get_plugins_by_experiment_type(experiment.type.value)
        if plugins:
            return plugins[0].analyze_experiment(experiment)
        return {}

    def get_all_plugin_metadata(self) -> List[PluginMetadata]:
        return [plugin.plugin_self_metadata() for plugin in self.get_all_plugins()]
