"""
Clean Plugin Manager for MUS1.

This module provides plugin management that integrates with the clean architecture,
using repositories for data access instead of the old DataManager pattern.
"""

import logging
from typing import Optional, Dict, Any, List, Set, Tuple
from importlib import metadata as importlib_metadata
from datetime import datetime
import json

from ..plugins.base_plugin import BasePlugin
from .metadata import PluginMetadata as DomainPluginMetadata, Experiment, Subject, VideoFile, ProjectConfig
from .repository import RepositoryFactory
from .schema import (
    Database, PluginMetadataModel, PluginResultModel,
    plugin_metadata_to_model, model_to_plugin_metadata,
    plugin_result_to_model, model_to_plugin_result
)

logger = logging.getLogger("mus1.core.plugin_manager_clean")


class PluginService:
    """Service layer providing clean data access for plugins."""

    def __init__(self, db: Database):
        self.db = db
        self.repos = RepositoryFactory(db)

    def get_experiment_data(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get experiment with related data (subject, videos)."""
        experiment = self.repos.experiments.find_by_id(experiment_id)
        if not experiment:
            return None

        subject = self.repos.subjects.find_by_id(experiment.subject_id)
        # Note: Video relationships would need to be implemented in repository
        # For now, return basic experiment data
        return {
            'experiment': experiment,
            'subject': subject,
            'videos': []  # TODO: Implement experiment-video relationships
        }

    def save_analysis_result(self, experiment_id: str, plugin_name: str,
                           capability: str, result_data: Dict[str, Any],
                           status: str = 'success', error_message: str = '',
                           output_files: Optional[List[str]] = None) -> None:
        """Save plugin analysis result to database."""
        from .metadata import PluginResult
        from .schema import plugin_result_to_model

        result = PluginResult(
            experiment_id=experiment_id,
            plugin_name=plugin_name,
            capability=capability,
            result_data=result_data,
            status=status,
            error_message=error_message,
            output_files=output_files or [],
            created_at=datetime.now(),
            completed_at=datetime.now() if status != 'running' else None
        )

        db_result = plugin_result_to_model(result)
        with self.db.get_session() as session:
            session.merge(db_result)
            session.commit()

    def get_analysis_result(self, experiment_id: str, plugin_name: str,
                          capability: str) -> Optional[Dict[str, Any]]:
        """Get analysis result from database."""
        from .schema import PluginResultModel, model_to_plugin_result

        with self.db.get_session() as session:
            db_result = session.query(PluginResultModel).filter(
                PluginResultModel.experiment_id == experiment_id,
                PluginResultModel.plugin_name == plugin_name,
                PluginResultModel.capability == capability
            ).first()

            if db_result:
                return model_to_plugin_result(db_result)
        return None

    def get_experiment_by_id(self, experiment_id: str) -> Optional['Experiment']:
        """Get experiment by ID."""
        return self.repos.experiments.find_by_id(experiment_id)

    def get_subject_by_id(self, subject_id: str) -> Optional['Subject']:
        """Get subject by ID."""
        return self.repos.subjects.find_by_id(subject_id)

    def get_experiments_for_subject(self, subject_id: str) -> List['Experiment']:
        """Get all experiments for a subject."""
        return self.repos.experiments.find_by_subject(subject_id)

    def get_video_by_hash(self, hash_value: str) -> Optional['VideoFile']:
        """Get video by hash."""
        return self.repos.videos.find_by_hash(hash_value)


class PluginManagerClean:
    """Clean plugin manager integrated with repositories."""

    def __init__(self, db: Database):
        self.db = db
        self.plugin_service = PluginService(db)
        self._plugins: List[BasePlugin] = []

        # Caches for faster lookups
        self._plugins_by_format: Dict[str, List[BasePlugin]] = {}
        self._plugins_by_capability: Dict[str, List[BasePlugin]] = {}
        self._supported_types: Optional[List[str]] = None

    def _clear_caches(self):
        """Clear caches when plugins are registered/unregistered."""
        self._plugins_by_format = {}
        self._plugins_by_capability = {}
        self._supported_types = None

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
            # Fallback to instance identity
            if plugin in self._plugins:
                logger.debug("Anonymous plugin instance already registered")
                return

        self._plugins.append(plugin)
        self._clear_caches()

        # Store plugin metadata in database
        self._store_plugin_metadata(plugin)

        logger.info(f"Registered plugin: {plugin.plugin_self_metadata().name}")

    def _store_plugin_metadata(self, plugin: BasePlugin) -> None:
        """Store plugin metadata in database."""
        metadata = plugin.plugin_self_metadata()
        db_metadata = plugin_metadata_to_model(metadata)

        with self.db.get_session() as session:
            session.merge(db_metadata)
            session.commit()

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
                metadata = plugin.plugin_self_metadata()
                supported = getattr(metadata, 'supported_experiment_types', []) or []
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

    # --- Utility Methods ---

    def get_all_plugin_metadata(self) -> List[DomainPluginMetadata]:
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
        """Get project actions for a specific plugin."""
        plugin = self.get_plugin_by_name(plugin_name)
        if not plugin:
            return []
        try:
            return list(plugin.supported_project_actions() or [])
        except Exception:
            return []

    # -------------------------------
    # Analysis execution with clean architecture
    # -------------------------------
    def run_plugin_analysis(self, experiment_id: str, plugin_name: str,
                          capability: str, project_config: 'ProjectConfig') -> Dict[str, Any]:
        """
        Execute plugin analysis using clean architecture data access.

        Args:
            experiment_id: ID of experiment to analyze
            plugin_name: Name of plugin to use
            capability: Analysis capability to execute
            project_config: Project configuration

        Returns:
            Analysis result dictionary
        """
        plugin = self.get_plugin_by_name(plugin_name)
        if not plugin:
            return {
                'status': 'failed',
                'error': f'Plugin {plugin_name} not found',
                'capability_executed': capability
            }

        # Get experiment from repository
        experiment = self.plugin_service.repos.experiments.find_by_id(experiment_id)
        if not experiment:
            return {
                'status': 'failed',
                'error': f'Experiment {experiment_id} not found',
                'capability_executed': capability
            }

        try:
            # Execute plugin analysis with plugin service
            result = plugin.analyze_experiment(
                experiment,
                self.plugin_service,
                capability,
                project_config
            )

            # Store result in database
            self.plugin_service.save_analysis_result(
                experiment_id=experiment_id,
                plugin_name=plugin_name,
                capability=capability,
                result_data=result.get('result_data', {}),
                status=result.get('status', 'success'),
                error_message=result.get('error', ''),
                output_files=result.get('output_file_paths', [])
            )

            return result

        except Exception as e:
            logger.error(f"Plugin analysis failed: {e}", exc_info=True)
            error_result = {
                'status': 'failed',
                'error': str(e),
                'capability_executed': capability
            }

            # Store error result
            self.plugin_service.save_analysis_result(
                experiment_id=experiment_id,
                plugin_name=plugin_name,
                capability=capability,
                result_data={},
                status='failed',
                error_message=str(e)
            )

            return error_result

    def get_plugin_analysis_history(self, experiment_id: str) -> List[Dict[str, Any]]:
        """Get analysis history for an experiment."""
        # This would need to be implemented in PluginService
        # For now, return empty list
        return []
