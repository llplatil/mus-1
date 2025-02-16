from __future__ import annotations

import logging
from typing import Optional, List
from .metadata import ProjectState, MouseMetadata, ExperimentMetadata, PluginMetadata

logger = logging.getLogger("mus1.core.state_manager")

class StateManager:
    """
    Manages the in-memory ProjectState, providing methods for CRUD operations.
    """

    def __init__(self, project_state: Optional[ProjectState] = None):
        self._project_state = project_state or ProjectState()

    @property
    def project_state(self) -> ProjectState:
        return self._project_state

    def set_project_state(self, new_state: ProjectState) -> None:
        """Update the current project state with a new ProjectState."""
        self._project_state = new_state
        logger.info("Project state updated.")

    def sync_supported_experiment_types(self, plugin_manager) -> None:
        """
        Fetch the current list of experiment types from plugin_manager and
        store it in project_state.supported_experiment_types.
        """
        types_list = plugin_manager.get_supported_experiment_types()
        self._project_state.supported_experiment_types = types_list
        logger.info(f"Synced supported experiment types: {types_list}")

    # ----------------------------------------------------------------------
    # NEW: Methods for retrieving experiments and experiment types
    # ----------------------------------------------------------------------
    def get_supported_experiment_types(self) -> List[str]:
        """
        Return a copy of the current supported_experiment_types from the ProjectState.
        """
        return list(self._project_state.supported_experiment_types)

    def get_experiments_list(self) -> List[ExperimentMetadata]:
        """
        Return a list of all experiments in the project.
        You could add optional parameters for sorting, filters, etc.
        """
        return list(self._project_state.experiments.values())

    def get_experiment_ids(self) -> List[str]:
        """
        Return just the IDs (keys) of the experiments in the project.
        """
        return list(self._project_state.experiments.keys())

    def get_subject_ids(self) -> List[str]:
        """Return a list of subject IDs from the project state."""
        return list(self._project_state.subjects.keys())

    def get_experiment_by_id(self, experiment_id: str) -> Optional[ExperimentMetadata]:
        """
        Return a specific experiment by ID, or None if not found.
        """
        return self._project_state.experiments.get(experiment_id)

    def get_experiments_list_sorted(self) -> List[ExperimentMetadata]:
        """
        Return a list of all experiments in the project, sorted according
        to ProjectState.settings["global_sort_mode"]. Possible modes:
          - 'name' (alphabetical by experiment ID)
          - 'date'
        """
        all_exps = list(self._project_state.experiments.values())
        sort_mode = self._project_state.settings.get("global_sort_mode", "name")

        if sort_mode == "date":
            all_exps.sort(key=lambda e: e.date)
        else:
            # Default: alphabetical by experiment ID
            all_exps.sort(key=lambda e: e.id.lower())

        return all_exps

    # --------------------------------------------
    # NEW: sync and store plugin metadata
    # --------------------------------------------
    def sync_plugin_metadatas(self, plugin_manager) -> None:
        """
        Pull all plugin metadata from the plugin_manager, optionally sort them,
        then store them in project_state.registered_plugin_metadatas.
        """
        all_metadata = plugin_manager.get_all_plugin_metadata()

        # Suppose we also have a "plugin_sort_mode" in settings for consistency.
        plugin_sort_mode = self._project_state.settings.get("plugin_sort_mode", "name")

        if plugin_sort_mode == "date":
            all_metadata.sort(key=lambda pm: pm.date_created)
        else:
            # Default: sort by name (case-insensitive)
            all_metadata.sort(key=lambda pm: pm.name.lower())

        self._project_state.registered_plugin_metadatas = all_metadata
        logger.info(f"Synced plugin metadata (sorted by '{plugin_sort_mode}'): {[m.name for m in all_metadata]}")

    def get_plugin_metadatas(self) -> List[PluginMetadata]:
        """
        Return the plugin metadata objects currently stored (already sorted).
        """
        return list(self._project_state.registered_plugin_metadatas)

