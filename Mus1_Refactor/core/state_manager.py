from __future__ import annotations

import logging
from typing import Optional, List, Union, Callable, Dict, Any
from .metadata import ProjectState, SubjectMetadata, ExperimentMetadata, PluginMetadata
from .sort_manager import sort_items
from .logging_bus import LoggingEventBus

logger = logging.getLogger("mus1.core.state_manager")

class StateManager:
    """
    Manages the in-memory ProjectState, providing methods for CRUD operations.
    """

    def __init__(self, project_state: Optional[ProjectState] = None):
        self._project_state = project_state or ProjectState()
        self._observers: List[Callable[[], None]] = []  # Added list to track observer callbacks
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("StateManager initialized", "info", "StateManager")

    @property
    def project_state(self) -> ProjectState:
        return self._project_state

    def set_project_state(self, new_state: ProjectState) -> None:
        """Update the current project state with a new ProjectState."""
        self._project_state = new_state
        logger.info("Project state updated.")
        self.log_bus.log("Project state updated", "info", "StateManager")
        self.notify_observers()  # Notify observers on state change

    def sync_supported_experiment_types(self, plugin_manager) -> None:
        """
        Fetch the current list of experiment types from plugin_manager and
        store it in project_state.supported_experiment_types.
        """
        types_list = plugin_manager.get_supported_experiment_types()
        self._project_state.supported_experiment_types = types_list
        logger.info(f"Synced supported experiment types: {types_list}")
        self.log_bus.log(f"Synced supported experiment types: {len(types_list)} types", "info", "StateManager")

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

    def get_sorted_list(self, item_type: str, custom_sort: Optional[str] = None):
        """
        A unified method to fetch and return sorted items for a given type:
          - 'subjects'    -> returns sorted SubjectMetadata objects
          - 'experiments' -> returns sorted ExperimentMetadata objects
          - 'plugins'     -> returns sorted PluginMetadata
          - 'body_parts'  -> returns sorted list of BodyPartMetadata
          - 'objects'     -> returns sorted list of ObjectMetadata
        We rely on project_state and the global sort mode to do so.
        """
        # Use the global_settings property to get the global sort mode
        sort_mode = self.global_settings.get("global_sort_mode")
        
        # We'll gather items based on item_type:
        if item_type == "subjects":
            all_items = list(self._project_state.subjects.values())
            key_func = (lambda s: s.date_added) if sort_mode == "Date Added" else (lambda s: s.id)

        elif item_type == "experiments":
            all_items = list(self._project_state.experiments.values())
            if custom_sort:
                if custom_sort == "subject":
                    key_func = lambda e: e.subject_id
                elif custom_sort == "plugin":
                    key_func = lambda e: e.type  # Now using string directly instead of enum
                elif custom_sort == "date":
                    key_func = lambda e: e.date_added
                else:
                    key_func = (lambda e: e.date_added) if sort_mode == "Date Added" else (lambda e: e.id)
            else:
                key_func = (lambda e: e.date_added) if sort_mode == "Date Added" else (lambda e: e.id)

        elif item_type == "plugins":
            all_items = self._project_state.registered_plugin_metadatas
            key_func = (lambda pm: pm.date_created) if sort_mode == "Date Added" else (lambda pm: pm.name.lower())

        elif item_type == "body_parts":
            # Retrieve master_body_parts from global_settings
            all_items = self.global_settings.get("master_body_parts", [])
            key_func = (lambda bp: bp.date_added) if sort_mode == "Date Added" else (lambda bp: bp.name.lower())

        elif item_type == "objects":
            # Retrieve tracked_objects from global_settings
            all_items = self.global_settings.get("tracked_objects", [])
            key_func = (lambda obj: obj.date_added) if sort_mode == "Date Added" else (lambda obj: obj.name.lower())

        else:
            logger.warning(f"Unrecognized item_type in get_sorted_list: {item_type}")
            return []

        return sort_items(all_items, sort_mode, key_func=key_func)

    def sync_plugin_metadatas(self, plugin_manager) -> None:
        """
        Pull all plugin metadata from the plugin_manager, optionally sort them,
        then store them in project_state.registered_plugin_metadatas.
        """
        all_metadata = plugin_manager.get_all_plugin_metadata()

        # Use the global sort setting
        sort_mode = self._project_state.settings.get("global_sort_mode", "Lexicographical Order (Numbers as Characters)")

        if sort_mode == "Date Added":
            all_metadata.sort(key=lambda pm: pm.date_created)
        else:
            # Default: sort by name (case-insensitive)
            all_metadata.sort(key=lambda pm: pm.name.lower())

        self._project_state.registered_plugin_metadatas = all_metadata
        
        # Also sync plugin styling preferences
        self.sync_plugin_styling(plugin_manager)
        
        logger.info(f"Synced plugin metadata (sorted by '{sort_mode}'): {[m.name for m in all_metadata]}")

    def sync_plugin_styling(self, plugin_manager) -> None:
        """
        Sync plugin styling preferences from the plugin_manager to the project state.
        
        This retrieves standardized styling preferences from all plugins and 
        stores them in the project state for UI components to use.
        """
        styling_preferences = plugin_manager.get_all_plugin_styling_preferences()
        styling_classes = plugin_manager.get_plugin_styling_classes()
        
        # Store in project state - ensure settings exists
        if not hasattr(self._project_state, 'settings'):
            self._project_state.settings = {}
        
        # Store both the raw preferences and the processed CSS classes
        self._project_state.settings['plugin_styling_preferences'] = styling_preferences
        self._project_state.settings['plugin_styling_classes'] = styling_classes
        
        logger.info(f"Synced styling preferences for {len(styling_preferences)} plugins")
        self.log_bus.log(f"Synced styling for {len(styling_preferences)} plugins", "info", "StateManager")
    
    def get_plugin_styling_classes(self, plugin_id: str) -> List[str]:
        """
        Get the CSS classes to apply for a specific plugin.
        
        Args:
            plugin_id: The ID (name) of the plugin
            
        Returns:
            List of CSS class names to apply to this plugin's UI elements
        """
        # Get styling classes from project state
        styling_classes = self._project_state.settings.get('plugin_styling_classes', {})
        
        # Return classes for this plugin, or empty list if not found
        return styling_classes.get(plugin_id, [])
    
    def get_plugin_styling_preferences(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve plugin styling preferences."""
        return self.project_state.settings.get('plugin_styling_preferences', {})

    def get_plugin_metadatas(self) -> List[PluginMetadata]:
        """
        Return the plugin metadata objects currently stored (unsorted).
        """
        return list(self._project_state.registered_plugin_metadatas)
    
    def get_plugins_for_experiment_type(self, exp_type: str) -> List[PluginMetadata]:
        """
        Return a list of plugin metadata for plugins that support the given experiment type.
        """
        return [pm for pm in self._project_state.registered_plugin_metadatas 
                if hasattr(pm, 'supported_experiment_types') and 
                pm.supported_experiment_types and 
                exp_type in pm.supported_experiment_types]

    def get_sorted_body_parts(self) -> dict:
        """
        Return a dictionary containing sorted lists for both master and active body parts,
        using the global sort mode.

        Returns:
            dict: { "master": List[BodyPartMetadata], "active": List[BodyPartMetadata] }
        """
        sort_mode = self.global_settings.get("global_sort_mode")
        key_func = (lambda bp: bp.date_added) if sort_mode == "Date Added" else (lambda bp: bp.name.lower())
        master_sorted = sort_items(self.global_settings.get("master_body_parts", []), sort_mode, key_func=key_func)
        active_sorted = sort_items(self.global_settings.get("active_body_parts", []), sort_mode, key_func=key_func)
        return {"master": master_sorted, "active": active_sorted}

    def get_sorted_objects(self, list_type="master") -> List:
        """Return a sorted list of ObjectMetadata using the global sort mode."""
        sort_mode = self.global_settings.get("global_sort_mode")
        if list_type == "active":
            all_objects = self.global_settings.get("active_tracked_objects", [])
        else:  # master list by default
            all_objects = self.global_settings.get("master_tracked_objects", [])
        
        key_func = (lambda obj: obj.date_added) if sort_mode == "Date Added" else (lambda obj: obj.name.lower())
        return sort_items(all_objects, sort_mode, key_func=key_func)

    @property
    def global_settings(self) -> dict:
        """Returns a dictionary of global settings from the current project state."""
        settings_dict = {}
        if self._project_state.project_metadata is not None:
            settings_dict["global_sort_mode"] = self._project_state.project_metadata.global_sort_mode
            settings_dict["global_frame_rate"] = self._project_state.project_metadata.global_frame_rate
            settings_dict["global_frame_rate_enabled"] = self._project_state.project_metadata.global_frame_rate_enabled
            settings_dict["master_body_parts"] = self._project_state.project_metadata.master_body_parts
            settings_dict["active_body_parts"] = self._project_state.project_metadata.active_body_parts
            settings_dict["master_tracked_objects"] = self._project_state.project_metadata.master_tracked_objects
            settings_dict["active_tracked_objects"] = self._project_state.project_metadata.active_tracked_objects
        else:
            settings_dict["global_sort_mode"] = self._project_state.settings.get("global_sort_mode", "Natural Order (Numbers as Numbers)")
            settings_dict["global_frame_rate"] = self._project_state.settings.get("global_frame_rate", 60)
            settings_dict["global_frame_rate_enabled"] = self._project_state.settings.get("global_frame_rate_enabled", False)
            settings_dict["master_body_parts"] = self._project_state.settings.get("body_parts", [])
            settings_dict["active_body_parts"] = self._project_state.settings.get("active_body_parts", [])
            settings_dict["master_tracked_objects"] = self._project_state.settings.get("master_tracked_objects", [])
            settings_dict["active_tracked_objects"] = self._project_state.settings.get("active_tracked_objects", [])
        return settings_dict

    def get_treatments(self) -> dict:
        """
        Returns the treatments dictionary containing 'available' and 'active' lists,
        sorted according to the global sort mode from sort_manager.
        """
        from .sort_manager import sort_items
        treatments = self._project_state.settings.get("treatments", {"available": [], "active": []})
        sort_mode = self.global_settings.get("global_sort_mode")
        treatments["available"] = sort_items(treatments["available"], sort_mode, key_func=lambda x: x)
        treatments["active"] = sort_items(treatments["active"], sort_mode, key_func=lambda x: x)
        return treatments

    def get_genotypes(self) -> dict:
        """
        Returns the genotypes dictionary containing 'available' and 'active' lists,
        sorted according to the global sort mode from sort_manager.
        """
        from .sort_manager import sort_items
        genotypes = self._project_state.settings.get("genotypes", {"available": [], "active": []})
        sort_mode = self.global_settings.get("global_sort_mode")
        genotypes["available"] = sort_items(genotypes["available"], sort_mode, key_func=lambda x: x)
        genotypes["active"] = sort_items(genotypes["active"], sort_mode, key_func=lambda x: x)
        return genotypes

    def get_global_sort_mode(self) -> str:
        """
        Returns the current global sort mode using the consolidated global_settings property.
        """
        return self.global_settings.get("global_sort_mode")

    def get_experiments_grouped_by_subject(self) -> dict:
        """
        Groups experiments by subject and sorts each group based on the global sort preference.
        Returns:
            A dictionary mapping subject IDs to a sorted list of ExperimentMetadata objects.
        """
        # Use the helper to get current global sort mode
        sort_mode = self.get_global_sort_mode()

        # Group experiments by subject_id
        from collections import defaultdict
        groups = defaultdict(list)
        for exp in self._project_state.experiments.values():
            groups[exp.subject_id].append(exp)

        # Determine key function based on sort mode
        if sort_mode == "Date Added":
            key_func = lambda e: e.date_added
        else:
            key_func = lambda e: e.id

        # Sort each group's experiments using sort_items
        from .sort_manager import sort_items
        grouped_sorted = {subject: sort_items(exps, sort_mode, key_func=key_func) for subject, exps in groups.items()}

        return grouped_sorted

    def get_experiments_for_batch(self, batch_id):
        """
        Returns a list of experiments in a specific batch.
        
        Args:
            batch_id (str): The ID of the batch to fetch experiments for
            
        Returns:
            list: List of ExperimentMetadata objects in the batch
        """
        if batch_id not in self._project_state.batches:
            return []
            
        batch = self._project_state.batches[batch_id]
        return [self._project_state.experiments[exp_id] for exp_id in batch.experiment_ids 
                if exp_id in self._project_state.experiments]
    
    def get_batches_for_experiment(self, experiment_id):
        """
        Returns a list of batches that contain a specific experiment.
        
        Args:
            experiment_id (str): The ID of the experiment
            
        Returns:
            list: List of BatchMetadata objects containing the experiment
        """
        if experiment_id not in self._project_state.experiments:
            return []
            
        exp = self._project_state.experiments[experiment_id]
        return [self._project_state.batches[batch_id] for batch_id in exp.batch_ids 
                if batch_id in self._project_state.batches]
    
    def get_batches_list(self):
        """
        Returns a list of all batches in the project.
        
        Returns:
            list: List of all BatchMetadata objects
        """
        return list(self._project_state.batches.values())
    
    def get_sorted_batches(self, sort_key=None):
        """
        Returns a sorted list of batches.
        
        Args:
            sort_key (str, optional): Key to sort by ('id', 'name', 'date_added')
            
        Returns:
            list: Sorted list of BatchMetadata objects
        """
        # Get the global sort mode if not provided
        if sort_key is None:
            sort_mode = self.get_global_sort_mode()
            if sort_mode == "Date Added":
                sort_key = "date_added"
            else:
                sort_key = "id"
        
        # Get all batches
        batches = list(self._project_state.batches.values())
        
        # Sort based on key
        if sort_key == "date_added":
            return sorted(batches, key=lambda b: b.date_added)
        elif sort_key == "name":
            return sorted(batches, key=lambda b: b.name)
        elif sort_key == "size":
            return sorted(batches, key=lambda b: len(b.experiment_ids))
        else:  # Default to ID
            return sorted(batches, key=lambda b: b.id)

    def register_observer(self, callback: Callable[[], None]) -> None:
        """Register an observer callback to be notified when the state changes."""
        self._observers.append(callback)

    def notify_observers(self) -> None:
        """Notify all registered observers about a state change."""
        for callback in self._observers:
            callback()
        # Log notification to the LoggingEventBus
        self.log_bus.log(f"Notified {len(self._observers)} observers of state change", "info", "StateManager")

    def get_compatible_processing_stages(self, plugin_manager, exp_type: str) -> list:
        """Return processing stages compatible with the given experiment type using the plugin manager."""
        stages = set()
        for plugin in plugin_manager.get_all_plugins():
            if exp_type in plugin.get_supported_experiment_types():
                stages.update(plugin.get_supported_processing_stages())
        return sorted(list(stages))

    def get_compatible_data_sources(self, plugin_manager, exp_type: str, stage: str) -> list:
        """Return data sources compatible with the given experiment type and processing stage."""
        sources = set()
        for plugin in plugin_manager.get_all_plugins():
            if exp_type in plugin.get_supported_experiment_types() and stage in plugin.get_supported_processing_stages():
                sources.update(plugin.get_supported_data_sources())
        return sorted(list(sources))

    def compile_required_fields(self, plugins: list) -> list:
        """Compile and return a sorted list of unique required fields from the given plugins."""
        fields = set()
        for plugin in plugins:
            fields.update(plugin.required_fields())
        return sorted(list(fields))

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Subscribe an observer callback to be notified of state changes."""
        self.register_observer(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        """Unsubscribe an observer callback from state changes."""
        if callback in self._observers:
            self._observers.remove(callback)

    def get_theme_preference(self) -> str:
        """Retrieve the user's theme preference."""
        if self.project_state and self.project_state.project_metadata:
            return self.project_state.project_metadata.theme_mode
        return "dark"  # default fallback

    def set_theme_preference(self, theme_choice: str) -> None:
        """Store the user's theme preference."""
        if self.project_state and self.project_state.project_metadata:
            self.project_state.project_metadata.theme_mode = theme_choice
            self.notify_observers()

    def set_plugin_styling_preferences(self, styling_preferences: Dict[str, Dict[str, Any]]) -> None:
        """Store plugin styling preferences."""
        self.project_state.settings['plugin_styling_preferences'] = styling_preferences
        self.notify_observers()

    def update_global_settings(self, new_settings: dict) -> None:
        # Update project_state.settings with new settings and notify observers
        self._project_state.settings.update(new_settings)
        logger.info("Global settings updated.")
        self.notify_observers()

    # New convenience method for retrieving sorted subjects
    def get_sorted_subjects(self) -> list:
        """Return a sorted list of subject metadata objects based on the current global sort mode."""
        return self.get_sorted_list("subjects")

