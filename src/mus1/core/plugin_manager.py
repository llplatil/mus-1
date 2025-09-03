import logging
from typing import Optional, Dict, Any, List, Set
from importlib import metadata as importlib_metadata
from ..plugins.base_plugin import BasePlugin
from .metadata import ExperimentMetadata, ProjectState, PluginMetadata

logger = logging.getLogger("mus1.core.plugin_manager")

class PluginManager:
    def __init__(self):
        self._plugins: List[BasePlugin] = []
        # Caches for faster lookups
        self._plugins_by_format: Dict[str, List[BasePlugin]] = {}
        self._plugins_by_capability: Dict[str, List[BasePlugin]] = {}
        self._supported_types: Optional[List[str]] = None
        self._supported_stages: Optional[List[str]] = None

    def _clear_caches(self):
        """Clear caches when plugins are registered/unregistered."""
        self._plugins_by_format = {}
        self._plugins_by_capability = {}
        self._supported_types = None
        self._supported_stages = None

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a plugin instance, de-duplicated by plugin metadata name."""
        try:
            name = plugin.plugin_self_metadata().name
        except Exception:
            name = None
        if name:
            if any(p.plugin_self_metadata().name == name for p in self._plugins):
                logger.debug(f"Plugin already registered by name: {name}")
                return
        else:
            # Fallback to instance identity (shouldn't happen for well-formed plugins)
            if plugin in self._plugins:
                logger.debug("Anonymous plugin instance already registered")
                return
        self._plugins.append(plugin)
        self._clear_caches()
        logger.info(f"Registered plugin: {plugin.plugin_self_metadata().name}")

    # --- Discovery via entry points ---
    def discover_entry_points(self, group: str = "mus1.plugins") -> int:
        """Discover and register plugins advertised via Python entry points.

        Returns the number of plugins newly registered.
        """
        new_count = 0
        try:
            eps = importlib_metadata.entry_points()
            # PEP 660/685 compatible handling
            candidates = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
        except Exception:
            candidates = []

        for ep in list(candidates):
            try:
                obj = ep.load()
                if isinstance(obj, type) and issubclass(obj, BasePlugin):
                    instance = obj()
                    before = len(self._plugins)
                    self.register_plugin(instance)
                    if len(self._plugins) > before:
                        new_count += 1
                else:
                    logger.warning(f"Entry point '{ep.name}' did not resolve to a BasePlugin subclass")
            except Exception as e:
                logger.error(f"Failed to load plugin from entry point '{getattr(ep, 'name', '?')}': {e}")
        if new_count:
            self._clear_caches()
        logger.info(f"Entry-point discovery complete. New plugins: {new_count}")
        return new_count

    def get_all_plugins(self) -> List[BasePlugin]:
        """Return a list of all registered plugin instances."""
        return self._plugins

    # --- Discovery/Filtering Methods ---

    def get_plugins_for_format(self, data_format: str) -> List[BasePlugin]:
        """Return plugins that declare they can read/process the given data format."""
        if not self._plugins_by_format:
            # Build cache
            for plugin in self._plugins:
                for fmt in plugin.readable_data_formats():
                    if fmt not in self._plugins_by_format:
                        self._plugins_by_format[fmt] = []
                    self._plugins_by_format[fmt].append(plugin)
        return self._plugins_by_format.get(data_format, [])

    def get_plugins_with_capability(self, capability: str) -> List[BasePlugin]:
        """Return plugins that declare they provide the given analysis capability."""
        if not self._plugins_by_capability:
             # Build cache
             for plugin in self._plugins:
                 for cap in plugin.analysis_capabilities():
                     if cap not in self._plugins_by_capability:
                         self._plugins_by_capability[cap] = []
                     self._plugins_by_capability[cap].append(plugin)
        return self._plugins_by_capability.get(capability, [])

    def get_plugin_by_name(self, name: str) -> Optional[BasePlugin]:
        """Find a plugin instance by its unique name."""
        for plugin in self._plugins:
            if plugin.plugin_self_metadata().name == name:
                return plugin
        return None

    # --- Methods supporting UI Population (Using Caching) ---

    def get_supported_experiment_types(self) -> List[str]:
        """Return a unique, sorted list of experiment types supported by all registered plugins."""
        if self._supported_types is None:
            types: Set[str] = set()
            for plugin in self._plugins:
                # Use getattr for safety in case attribute doesn't exist in metadata
                supported = getattr(plugin.plugin_self_metadata(), 'supported_experiment_types', []) or []
                types.update(supported)
            self._supported_types = sorted(list(types))
        return self._supported_types

    def get_supported_experiment_subtypes(self) -> Dict[str, List[str]]:
        """Aggregate experiment subtypes from plugin metadata as {type: [subtypes...]}"""
        mapping: Dict[str, Set[str]] = {}
        for plugin in self._plugins:
            meta = plugin.plugin_self_metadata()
            sub_map = getattr(meta, 'supported_experiment_subtypes', None) or {}
            for exp_type, subtypes in sub_map.items():
                if exp_type not in mapping:
                    mapping[exp_type] = set()
                for st in (subtypes or []):
                    mapping[exp_type].add(st)
        # Convert to sorted lists
        return {k: sorted(list(v)) for k, v in mapping.items()}

    def get_supported_processing_stages(self) -> List[str]:
        """Return the canonical list of processing stages from metadata."""
        if self._supported_stages is None:
            from .metadata import DEFAULT_PROCESSING_STAGES
            self._supported_stages = list(DEFAULT_PROCESSING_STAGES)
        return self._supported_stages

    # --- Utility Methods ---

    def get_all_plugin_metadata(self) -> List[PluginMetadata]:
        """Return metadata for all registered plugins."""
        return [plugin.plugin_self_metadata() for plugin in self._plugins]

    def get_sorted_plugins(self, sort_mode: str = None) -> List[BasePlugin]:
        """Return a sorted list of plugins based on the specified sort mode."""
        plugins = self.get_all_plugins()
        if sort_mode == "Date Added":
            return sorted(plugins, key=lambda p: p.plugin_self_metadata().date_created)
        else:  # Default to sorting by name
            return sorted(plugins, key=lambda p: p.plugin_self_metadata().name.lower())

    # --- Convenience discovery helpers for UI (core-owned logic) ---

    def _unique_by_name(self, plugins: List[BasePlugin]) -> List[BasePlugin]:
        """Return plugins list de-duplicated by metadata name, preserving order."""
        seen: set[str] = set()
        deduped: list[BasePlugin] = []
        for p in plugins:
            name = p.plugin_self_metadata().name
            if name not in seen:
                seen.add(name)
                deduped.append(p)
        return deduped

    def get_plugins_by_plugin_type(self, plugin_type: str) -> List[BasePlugin]:
        """Return plugins whose PluginMetadata.plugin_type equals plugin_type."""
        result: list[BasePlugin] = []
        for plugin in self._plugins:
            meta = plugin.plugin_self_metadata()
            if getattr(meta, "plugin_type", None) == plugin_type:
                result.append(plugin)
        return sorted(result, key=lambda p: p.plugin_self_metadata().name.lower())

    def get_data_handler_plugins(self) -> List[BasePlugin]:
        """Return plugins capable of loading tracking data (capability-based)."""
        return sorted(
            self.get_plugins_with_capability("load_tracking_data"),
            key=lambda p: p.plugin_self_metadata().name.lower(),
        )

    def get_importer_plugins(self) -> List[BasePlugin]:
        """Return importer-like plugins for the UI's 'Data Handler/Importer' list."""
        explicit_importers = self.get_plugins_by_plugin_type("importer")
        handlers = self.get_data_handler_plugins()
        combined = self._unique_by_name(explicit_importers + handlers)
        return sorted(combined, key=lambda p: p.plugin_self_metadata().name.lower())

    def get_exporter_plugins(self) -> List[BasePlugin]:
        """Return exporter plugins for the UI's 'Exporter' list."""
        return self.get_plugins_by_plugin_type("exporter")

    def get_analysis_plugins_for_type(self, experiment_type: str) -> List[BasePlugin]:
        """Return analysis plugins that support the given experiment type."""
        result: list[BasePlugin] = []
        for plugin in self._plugins:
            meta = plugin.plugin_self_metadata()
            p_type = getattr(meta, "plugin_type", None)
            if p_type in {"importer", "exporter"}:
                continue
            caps = plugin.analysis_capabilities() or []
            has_non_loading_cap = any(cap != "load_tracking_data" for cap in caps)
            if not has_non_loading_cap:
                continue
            supported_types = getattr(meta, "supported_experiment_types", []) or []
            if experiment_type in supported_types:
                result.append(plugin)
        return sorted(result, key=lambda p: p.plugin_self_metadata().name.lower())

    # -------------------------------
    # Project-level action discovery
    # -------------------------------
    def get_plugins_with_project_actions(self) -> List[BasePlugin]:
        """
        Return plugins that advertise at least one project-level action via
        BasePlugin.supported_project_actions().
        """
        capable: list[BasePlugin] = []
        for p in self._plugins:
            try:
                actions = p.supported_project_actions()
                if actions:
                    capable.append(p)
            except Exception:
                continue
        return sorted(capable, key=lambda p: p.plugin_self_metadata().name.lower())

    def get_project_actions_for_plugin(self, plugin_name: str) -> List[str]:
        plugin = self.get_plugin_by_name(plugin_name)
        if not plugin:
            return []
        try:
            return list(plugin.supported_project_actions() or [])
        except Exception:
            return []