from typing import Optional, Dict, Any, List
from plugins.base_plugin import BasePlugin
from core.metadata import ExperimentMetadata, ProjectState, PluginMetadata


class PluginManager:
    def __init__(self):
        self._plugins: List[BasePlugin] = []

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a plugin instance, determine type and supported subtypes (eg BasicCSVPlot is an experiment type plugin, and supports NOR and OF)."""
        self._plugins.append(plugin)

    def get_all_plugins(self) -> List[BasePlugin]:
        return self._plugins

    def get_supported_experiment_types(self) -> List[str]:
        """Return a unique list of experiment types supported by all registered plugins."""
        types = set()
        for plugin in self.get_all_plugins():
            meta = plugin.plugin_self_metadata()
            supported_types = meta.supported_experiment_types or []
            types.update(supported_types)
        return sorted(list(types))

    def get_supported_processing_stages(self) -> List[str]:
        """Return unique processing stages from all registered plugins."""
        stages = set()
        for plugin in self.get_all_plugins():
            stages.update(plugin.get_supported_processing_stages())
        return sorted(list(stages))

    def get_supported_data_sources(self) -> List[str]:
        """Return unique data sources from all registered plugins."""
        sources = set()
        for plugin in self.get_all_plugins():
            sources.update(plugin.get_supported_data_sources())
        return sorted(list(sources))

    def get_supported_arena_sources(self) -> List[str]:
        """Return unique arena image sources supported by all plugins."""
        sources = set()
        for plugin in self.get_all_plugins():
            sources.update(plugin.get_supported_arena_sources())
        return sorted(list(sources))

    def get_plugins_for_experiment_type(self, exp_type: str) -> List[BasePlugin]:
        """Return a list of plugins that support the given experiment type."""
        return [plugin for plugin in self.get_all_plugins() 
                if exp_type in plugin.get_supported_experiment_types()]

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Validate an experiment using all plugins that support its type."""
        plugins = self.get_plugins_for_experiment_type(experiment.type)
        if not plugins:
            raise ValueError(f"No plugin registered supporting experiment type '{experiment.type}'")
        
        # Let each plugin validate its own parameters
        for plugin in plugins:
            plugin_name = plugin.plugin_self_metadata().name
            plugin_params = experiment.plugin_params.get(plugin_name, {})
            # Create a copy of the experiment with only this plugin's parameters
            experiment_for_validation = ExperimentMetadata(
                id=experiment.id,
                type=experiment.type,
                subject_id=experiment.subject_id,
                date_recorded=experiment.date_recorded,
                date_added=experiment.date_added,
                plugin_params={plugin_name: plugin_params}
            )
            plugin.validate_experiment(experiment_for_validation, project_state)

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Analyze an experiment using all plugins that support its type."""
        plugins = self.get_plugins_for_experiment_type(experiment.type)
        results = {}
        for plugin in plugins:
            plugin_name = plugin.plugin_self_metadata().name
            try:
                plugin_results = plugin.analyze_experiment(experiment)
                results[plugin_name] = plugin_results
            except Exception as e:
                results[plugin_name] = {"error": str(e)}
        return results

    def get_all_plugin_metadata(self) -> List[PluginMetadata]:
        """Return metadata for all registered plugins."""
        return [plugin.plugin_self_metadata() for plugin in self.get_all_plugins()]

    def get_sorted_plugins(self, sort_mode: str = None) -> List[BasePlugin]:
        """Return a sorted list of plugins based on the specified sort mode."""
        plugins = self.get_all_plugins()
        if sort_mode == "Date Added":
            return sorted(plugins, key=lambda p: p.plugin_self_metadata().date_created)
        else:  # Default to sorting by name
            return sorted(plugins, key=lambda p: p.plugin_self_metadata().name.lower())

    def get_plugins_by_criteria(self, exp_type: str, stage: str, source: str) -> List[BasePlugin]:
        """Return plugins supporting the given criteria combination: experiment type, processing stage, and data source."""
        return [plugin for plugin in self.get_all_plugins()
                if (exp_type in plugin.get_supported_experiment_types() and
                    stage in plugin.get_supported_processing_stages() and
                    source in plugin.get_supported_data_sources())]
