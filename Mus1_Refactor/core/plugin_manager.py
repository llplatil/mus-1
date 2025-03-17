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

    def get_all_plugin_styles(self) -> str:
        """Combine all plugin custom styles into a single stylesheet."""
        combined_styles = ""
        for plugin in self._plugins:
            custom_style = plugin.plugin_custom_style()
            if custom_style:
                # Add plugin-specific namespace
                plugin_id = plugin.plugin_self_metadata().name
                custom_style = f"/* Plugin: {plugin_id} */\n{custom_style}\n"
                combined_styles += custom_style
        return combined_styles
        
    def get_all_plugin_styling_preferences(self) -> Dict[str, Dict[str, Any]]:
        """
        Collect and normalize styling preferences from all registered plugins.
        
        Returns:
            Dictionary mapping plugin IDs to their styling preferences.
        """
        styling_preferences = {}
        for plugin in self._plugins:
            plugin_id = plugin.plugin_self_metadata().name
            # Collect styling preferences
            preferences = plugin.get_styling_preferences()
            # Store them with the plugin ID as the key
            styling_preferences[plugin_id] = preferences
        return styling_preferences
    
    def get_plugin_styling_classes(self) -> Dict[str, List[str]]:
        """
        Convert plugin styling preferences to CSS classes.
        
        This maps the standardized styling preferences to actual CSS classes
        that can be applied to UI elements.
        
        Returns:
            Dictionary mapping plugin IDs to lists of CSS classes to apply.
        """
        plugin_classes = {}
        for plugin in self._plugins:
            plugin_id = plugin.plugin_self_metadata().name
            classes = []
            
            # Get the plugin's preferences
            prefs = plugin.get_styling_preferences()
            
            # Convert preferences to CSS classes
            # Primary color
            primary_color = prefs.get("colors", {}).get("primary", "default")
            if primary_color == "accent":
                classes.append("plugin-primary-accent")
            elif primary_color == "default":
                classes.append("plugin-primary-default")
            elif primary_color.startswith("#"):  # Custom hex color
                # Custom colors are handled differently - we'll add data attributes later
                classes.append("plugin-primary-custom")
            
            # Border style
            border_style = prefs.get("borders", {}).get("style", "default")
            if border_style == "rounded":
                classes.append("plugin-border-rounded")
            elif border_style == "sharp":
                classes.append("plugin-border-sharp")
            elif border_style == "none":
                classes.append("plugin-border-none")
            else:
                classes.append("plugin-border-default")
            
            # Spacing
            internal_spacing = prefs.get("spacing", {}).get("internal", "default")
            if internal_spacing == "compact":
                classes.append("plugin-spacing-compact")
            elif internal_spacing == "spacious":
                classes.append("plugin-spacing-spacious")
            else:
                classes.append("plugin-spacing-default")
            
            # Store the classes with the plugin ID as the key
            plugin_classes[plugin_id] = classes
            
        return plugin_classes

    def register_plugin_styles_with_theme_manager(self, theme_manager):
        """Register all plugin style manifests with the given ThemeManager instance.

        This method iterates through all registered plugins, and if a plugin provides a style manifest
        via get_style_manifest(), it registers those style overrides with the ThemeManager.
        The manifest is expected to be a dictionary with a single 'base' key, e.g.,
            { 'base': { '$VARIABLE': 'value', ... } }
        """
        import logging
        logger = logging.getLogger("mus1.core.plugin_manager")
        for plugin in self._plugins:
            try:
                manifest = plugin.get_style_manifest()
                if manifest is not None:
                    # Use the plugin's own metadata name as its identifier
                    plugin_id = plugin.plugin_self_metadata().name
                    theme_manager.register_plugin_styles(plugin_id, manifest)
                    logger.info(f"Registered style manifest for plugin: {plugin_id}")
            except Exception as e:
                logger.warning(f"Error registering styles for plugin {plugin.plugin_self_metadata().name}: {e}")
