import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable
import os
import importlib
import importlib.util
import inspect
import platform
from pydantic.json import pydantic_encoder
import pandas as pd

from .metadata import ProjectState, ProjectMetadata, Sex, ExperimentMetadata, ArenaImageMetadata, VideoMetadata, SubjectMetadata, BodyPartMetadata, ObjectMetadata, TreatmentMetadata, GenotypeMetadata, PluginMetadata
from .state_manager import StateManager  # so we can type hint or reference if needed
from .plugin_manager import PluginManager
from ..plugins.base_plugin import BasePlugin
from .logging_bus import LoggingEventBus
from .data_manager import DataManager # Assuming DataManager might be used internally later
from pydantic import ValidationError

logger = logging.getLogger("mus1.core.project_manager")

class ProjectManager:
    def __init__(self, state_manager: StateManager, plugin_manager: PluginManager, data_manager: DataManager):
        """
        Args:
            state_manager: The main StateManager.
            plugin_manager: The shared PluginManager instance.
            data_manager: The shared DataManager instance.
        """
        self.state_manager = state_manager
        self.plugin_manager = plugin_manager
        self.data_manager = data_manager
        self._current_project_root: Path | None = None
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("ProjectManager initialized with shared managers", "info", "ProjectManager")
        
        # Plugins will be registered dynamically by scanning the plugins directory
        self._discover_and_register_plugins()
        
        # Sync core components after init
        self._sync_core_components()
        
        # Decoupled plugin UI state from current state; not syncing plugin data into StateManager

    def get_projects_directory(self, custom_base: Path | None = None) -> Path:
        """Return the directory where MUS1 projects are stored.

        Precedence for the base directory is:
        1. *custom_base* argument (used by CLI `--base-dir` or tests).
        2. Environment variable ``MUS1_PROJECTS_DIR`` if set.
        3. User home default: ``~/MUS1/projects`` (consistent local location).

        The returned directory is created if it does not exist so callers can
        rely on its presence.
        """
        if custom_base:
            base_dir = Path(custom_base).expanduser().resolve()
        else:
            env_dir = os.environ.get("MUS1_PROJECTS_DIR")
            if env_dir:
                base_dir = Path(env_dir).expanduser().resolve()
            else:
                # Default to consistent user-local location
                base_dir = (Path.home() / "MUS1" / "projects").expanduser().resolve()

        # Ensure existence
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _sync_core_components(self):
        """Sync necessary info after initialization or project load."""
        self.state_manager.sync_plugin_metadatas(self.plugin_manager)
        self.state_manager.sync_supported_experiment_types(self.plugin_manager)
        # Add any other sync operations needed

    def _discover_and_register_plugins(self):
        """Discover and register all available plugins dynamically by importing them as modules."""
        
        try:
            # Get the parent package of the current module (e.g., 'Mus1_Refactor' from 'Mus1_Refactor.core')
            # Assumes the structure is consistent
            base_package_name = __package__.split('.')[0] 
            plugins_module_name = f"{base_package_name}.plugins"
            
            logger.debug(f"Attempting to import plugins package: {plugins_module_name}")
            plugins_package = importlib.import_module(plugins_module_name)
            
            # Check if it's actually a package (must have __path__)
            if not hasattr(plugins_package, '__path__'):
                 logger.error(f"Plugins module '{plugins_module_name}' is not a package (missing __init__.py or incorrect structure?). Plugin discovery aborted.")
                 return
                 
            # Get the filesystem path(s) of the plugins package
            plugins_package_paths = plugins_package.__path__ 
            logger.debug(f"Scanning for plugins in package: {plugins_module_name} located at {plugins_package_paths}")

        except (ImportError, AttributeError, IndexError) as e:
             logger.error(f"Could not determine plugins package path or name: {e}. Plugin discovery might fail.", exc_info=True)
             return

        # Iterate over files in the plugins directory (using the first path if multiple exist)
        plugin_dir_path = plugins_package_paths[0]
        for filename in os.listdir(plugin_dir_path):
            # Ensure it's a python file, not __init__ or the base class itself
            if filename.endswith(".py") and filename not in ["base_plugin.py", "__init__.py"]:
                module_name_short = filename[:-3] # e.g., DlcProjectImporterPlugin
                full_module_name = f"{plugins_module_name}.{module_name_short}" # e.g., Mus1_Refactor.plugins.DlcProjectImporterPlugin
                
                try:
                    logger.debug(f"Attempting to import plugin module: {full_module_name}")
                    # Import the module using its full dotted path
                    module = importlib.import_module(full_module_name)
                    
                    # Inspect the loaded module for BasePlugin subclasses
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        # Check if it's a class defined in *this specific module* (not imported into it)
                        # and if it's a subclass of BasePlugin (but not BasePlugin itself)
                        if inspect.getmodule(obj) == module and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            # Skip abstract plugin classes
                            if inspect.isabstract(obj):
                                logger.info(f"Skipping abstract plugin class {name} (incomplete implementation).")
                                continue
                            try:
                                plugin_instance = obj() # Instantiate the plugin
                                self.plugin_manager.register_plugin(plugin_instance)
                                # register_plugin method already logs success
                            except Exception as init_err:
                                logger.error(f"Failed to instantiate plugin class {name} from {full_module_name}: {init_err}", exc_info=True)

                except ImportError as import_err:
                    # Log import errors for specific plugin modules but continue to others
                    logger.error(f"Failed to import plugin module {full_module_name}: {import_err}", exc_info=False) # Keep log cleaner
                except Exception as e:
                     # Catch other potential errors during module processing
                     logger.error(f"An unexpected error occurred while processing plugin module {full_module_name}: {e}", exc_info=True)

        # Log summary after attempting all plugins
        registered_plugins = self.plugin_manager.get_all_plugins()
        log_message = f"Plugin discovery complete. Registered {len(registered_plugins)} plugins."
        self.log_bus.log(log_message, "info", "ProjectManager") # Log as info
        logger.info(log_message)

        # After discovery, sync the metadata into the state manager
        self.state_manager.sync_plugin_metadatas(self.plugin_manager)

    def create_project(self, project_root: Path, project_name: str) -> None:
        """
        Creates a new MUS1 project directory, initializes an empty ProjectState
        (including ProjectMetadata), and saves to project_state.json.

        Raises:
            FileExistsError: if the directory already exists.
        """
        # Convert project_root to a Path if it's not already one
        if not isinstance(project_root, Path):
            project_root = Path(project_root)

        # 1) Make sure the directory does not already exist
        if project_root.exists():
            self.log_bus.log(f"Error creating project: Directory '{project_root}' already exists", "error", "ProjectManager")
            raise FileExistsError(f"Directory '{project_root}' already exists.")

        # 2) Create the folder
        project_root.mkdir(parents=True, exist_ok=False)
        logger.info(f"Created project directory at {project_root}")
        self.log_bus.log(f"Created project directory at {project_root}", "info", "ProjectManager")

        # 3) (Optional) Create subfolders for organization
        #    You can remove these if you do not need subfolders by default
        (project_root / "subjects").mkdir()
        (project_root / "experiments").mkdir()
        (project_root / "batches").mkdir()
        (project_root / "data").mkdir()
        (project_root / "media").mkdir()
        (project_root / "external_configs").mkdir()
        (project_root / "project_notes").mkdir()
        logger.info("Created standard subfolders: subjects, experiments, batches, data, media, external_configs, project_notes")

        # 4) Create an empty (or minimal) ProjectState
        #    Here we attach a ProjectMetadata with the supplied name
        new_metadata = ProjectMetadata(
            project_name=project_name,
            date_created=datetime.now(),
            theme_mode='dark',
            # You can set DLC configs, body parts, etc. here if you like:
            dlc_configs=[],
            master_body_parts=[],
            active_body_parts=[],
            tracked_objects=[],
            global_frame_rate=60,
            global_frame_rate_enabled=False  # Default to OFF
        )

        new_state = ProjectState(project_metadata=new_metadata)
        self.state_manager._project_state = new_state
        self._current_project_root = project_root

        # 5) Immediately save the fresh project_state.json
        self.save_project()

        # Sync plugins into the new state
        self._sync_core_components()

    def save_project(self) -> None:
        """
        Serialize the current ProjectState to disk at _current_project_root/project_state.json.
        Logs a warning if no project root is currently set.
        """
        if not self._current_project_root:
            logger.warning("No current project directory set; cannot save.")
            return

        state_path = self._current_project_root / "project_state.json"
        data = self.state_manager.project_state.dict()

        with open(state_path, 'w') as f:
            json.dump(data, f, indent=2, default=pydantic_encoder)

        logger.info(f"Project saved to {state_path}")

    def load_project(self, project_root: Path, optimize_for_large_files: bool = False) -> None:
        """
        Loads an existing project from project_state.json in project_root.
        Reconstructs the ProjectState and updates the StateManager.
        
        Args:
            project_root: Path to the project directory
            optimize_for_large_files: If True, uses a more memory-efficient approach for large projects
                                     by referencing file paths instead of loading all content
        """
        logger.info(f"Loading project from {project_root}")
        state_path = project_root / "project_state.json"

        if not state_path.exists():
            logger.error(f"No project_state.json found at {state_path}")
            return

        with open(state_path, 'r') as f:
            data = json.load(f)

        # Use the optimize_for_large_files flag if needed
        if optimize_for_large_files:
            logger.info("Using memory-optimized loading for large project")
            # Future implementations could include lazy loading; for now, log a warning
            logger.warning("Optimized loading for large files not fully implemented yet")

        # Pydantic reconstructs and validates the data according to ProjectState
        loaded_state = ProjectState(**data)
        logger.info("ProjectState loaded successfully from JSON.")

        # Replace state_manager's project_state to ensure isolation
        self.state_manager._project_state = loaded_state
        self._current_project_root = project_root
        logger.info("Project loaded and ready in memory.")

        # Sync plugins into the loaded state
        self._sync_core_components()

        # Notify observers about the project change to refresh UI components
        self.state_manager.notify_observers()

    def add_subject(
        self,
        subject_id: str,
        sex: Sex = Sex.UNKNOWN,
        genotype: Optional[str] = None,
        treatment: Optional[str] = None,
        notes: str = "",
        birth_date: Optional[datetime] = None,
        in_training_set: bool = False,
        death_date: Optional[datetime] = None,
    ) -> None:
        """
        Create or update a SubjectMetadata entry in the project's state.
        Previously named add_mouse.
        """
        existing = self.state_manager.project_state.subjects.get(subject_id)
        if existing:
            logger.info(f"Updating existing subject: {subject_id}")
            self.log_bus.log(f"Updating existing subject: {subject_id}", "info", "ProjectManager")
            existing.sex = sex
            existing.genotype = genotype
            existing.treatment = treatment
            existing.notes = notes
            existing.birth_date = birth_date
            existing.death_date = death_date
            existing.in_training_set = in_training_set
        else:
            # New subject addition using the renamed SubjectMetadata
            new_subject = SubjectMetadata(
                id=subject_id,
                sex=sex,
                genotype=genotype,
                treatment=treatment,
                notes=notes,
                birth_date=birth_date,
                death_date=death_date,
                in_training_set=in_training_set
            )
            self.state_manager.project_state.subjects[subject_id] = new_subject
            logger.info(f"Added new subject: {subject_id}")
            self.log_bus.log(f"Added new subject: {subject_id}", "success", "ProjectManager")
            self.refresh_all_lists()

        self.save_project()
    
    # New method to remove a subject from the project state
    def remove_subject(self, subject_id: str) -> None:
        """
        Remove a subject by its ID from the project state.
        """
        if subject_id in self.state_manager.project_state.subjects:
            del self.state_manager.project_state.subjects[subject_id]
            logger.info(f"Removed subject: {subject_id}")
            self.log_bus.log(f"Removed subject: {subject_id}", "info", "ProjectManager")
        else:
            logger.warning(f"Subject {subject_id} not found - cannot remove")
            self.log_bus.log(f"Subject {subject_id} not found - cannot remove", "warning", "ProjectManager")
        self.save_project()
        self.state_manager.notify_observers()

    def add_experiment(
        self,
        experiment_id: str,
        subject_id: str,
        date_recorded: datetime,
        exp_type: str,
        processing_stage: str,
        associated_plugins: List[str], # New: list of plugin names
        plugin_params: Dict[str, Dict[str, Any]] # New: nested dictionary of parameters
    ) -> None:
        """Adds a new experiment to the project state."""
        # --- Validation ---
        if not experiment_id or not subject_id or not exp_type or not date_recorded or not processing_stage:
            raise ValueError("Missing required experiment information (ID, Subject, Type, Date, Stage).")

        if experiment_id in self.state_manager.project_state.experiments:
            raise ValueError(f"Experiment ID '{experiment_id}' already exists.")

        if subject_id not in self.state_manager.project_state.subjects:
            raise ValueError(f"Subject ID '{subject_id}' does not exist.")

        # Validate associated plugin names exist
        missing_plugins = []
        registered_plugin_names = [p.name for p in self.state_manager.get_plugin_metadatas()]
        for plugin_name in associated_plugins:
            if plugin_name not in registered_plugin_names:
                missing_plugins.append(plugin_name)
        if missing_plugins:
            raise ValueError(f"Unknown associated plugins: {', '.join(missing_plugins)}")

        # TODO: Consider adding plugin-specific validation call here later:
        # for plugin_name in associated_plugins:
        #     plugin = self.plugin_manager.get_plugin_by_name(plugin_name)
        #     if plugin and plugin_name in plugin_params:
        #         temp_exp_meta_for_validation = ExperimentMetadata(...) # Create partial meta if needed
        #         plugin.validate_experiment(temp_exp_meta_for_validation, self.state_manager.project_state)


        # --- Create Metadata ---
        try:
            experiment_metadata = ExperimentMetadata(
                id=experiment_id,
                subject_id=subject_id,
                type=exp_type,
                date_recorded=date_recorded,
                date_added=datetime.now(),
                processing_stage=processing_stage,
                associated_plugins=associated_plugins, # Use the provided list
                plugin_params=plugin_params, # Use the provided nested dictionary
                # data_source="", # Set default or derive differently if kept
                # plugin_metadata=[], # This field might be deprecated, use associated_plugins
                # data_files={}, # Removed field
            )
        except ValidationError as e:
            logger.error(f"Pydantic validation failed for experiment '{experiment_id}': {e}")
            raise ValueError(f"Invalid experiment data: {e}")

        # --- Update State ---
        self.state_manager.project_state.experiments[experiment_id] = experiment_metadata
        # Link experiment to subject
        self.state_manager.project_state.subjects[subject_id].experiment_ids.add(experiment_id)

        logger.info(f"Experiment '{experiment_id}' added for subject '{subject_id}'.")

        # Persist change
        self.save_project()
        self.state_manager.notify_observers()

    # ---------------------------------------------------------------------
    # Video Linking Utilities
    # ---------------------------------------------------------------------

    def link_video_to_experiment(self, *, experiment_id: str, video_path: Path, notes: str = "") -> None:
        """Link an existing local video file to a MUS1 experiment.

        The method records essential metadata (path, timestamps, quick hash) in
        ``ProjectState.experiment_videos`` and registers the association with
        the target experiment.  It **does not** copy or move the file.

        Args:
            experiment_id: ID of the experiment to link the video to.
            video_path: Path object pointing to the video on disk.
            notes: Optional free-text notes to store with the link.

        Raises:
            ValueError: If the experiment does not exist or the file is invalid.
        """

        if not self._current_project_root:
            raise ValueError("No current project loaded – cannot link video.")

        exp = self.state_manager.get_experiment_by_id(experiment_id)
        if exp is None:
            raise ValueError(f"Experiment '{experiment_id}' not found in project.")

        if not video_path.exists() or not video_path.is_file():
            raise ValueError(f"Video file not found: {video_path}")

        # Collect fast-to-compute fingerprint information
        size_bytes = video_path.stat().st_size
        last_modified = video_path.stat().st_mtime
        # Use DataManager hashing utility for identity
        sample_hash = self.data_manager.compute_sample_hash(video_path)

        # Use sample_hash as canonical key
        video_key = sample_hash

        # Avoid duplicate entry if already linked (by canonical key)
        existing_vm = self.state_manager.project_state.experiment_videos.get(video_key)
        if existing_vm:
            # Ensure experiment is listed in its experiment_ids
            existing_vm.experiment_ids.add(experiment_id)
        else:
            from .metadata import VideoMetadata  # Local import to avoid cycles
            vm = VideoMetadata(
                path=video_path.resolve(),
                date=datetime.now(),
                notes=notes,
                experiment_ids={experiment_id},
                size_bytes=size_bytes,
                last_modified=last_modified,
                sample_hash=sample_hash,
            )
            self.state_manager.project_state.experiment_videos[video_key] = vm

        # Update ExperimentMetadata.file_ids for quick reverse lookup
        exp.file_ids.add(video_key)

        # Persist and notify
        self.save_project()
        self.state_manager.notify_observers()
        logger.info(f"Linked video '{video_path.name}' to experiment '{experiment_id}'.")

    def create_batch(self, batch_id, batch_name=None, description=None, experiment_ids=None, selection_criteria=None):
        """
        Create a new batch of experiments.
        
        Args:
            batch_id (str): Unique identifier for the batch
            batch_name (str, optional): Descriptive name for the batch
            description (str, optional): Detailed description of the batch
            experiment_ids (list, optional): List of experiment IDs to include in the batch
            selection_criteria (dict, optional): Criteria used to select experiments
        
        Returns:
            BatchMetadata: The created batch metadata object
        """
        if not self._current_project_root:
            raise ValueError("No current project loaded")
            
        # Validate batch ID is unique
        if batch_id in self.state_manager.project_state.batches:
            raise ValueError(f"Batch ID '{batch_id}' already exists")
            
        # Create batch selection criteria if not provided
        if selection_criteria is None:
            selection_criteria = {"manual_selection": True}
            
        # Use empty list if no experiment IDs provided
        if experiment_ids is None:
            experiment_ids = []
            
        # Create batch metadata
        from .metadata import BatchMetadata
        from datetime import datetime
        
        new_batch = BatchMetadata(
            id=batch_id,
            name=batch_name or batch_id,
            description=description or "",
            selection_criteria=selection_criteria,
            experiment_ids=set(experiment_ids),
            date_added=datetime.now()
        )
        
        # Add batch to project state
        self.state_manager.project_state.batches[batch_id] = new_batch
        
        # Update experiment batch_ids references
        for exp_id in experiment_ids:
            if exp_id in self.state_manager.project_state.experiments:
                self.state_manager.project_state.experiments[exp_id].batch_ids.add(batch_id)
                logger.info(f"Added experiment {exp_id} to batch {batch_id}")
            else:
                logger.warning(f"Experiment {exp_id} not found when adding to batch {batch_id}")
                
        # Log creation
        logger.info(f"Created batch '{batch_id}' with {len(experiment_ids)} experiments")
        self.log_bus.log(f"Created batch '{batch_id}' with {len(experiment_ids)} experiments", "success", "ProjectManager")
        
        # Persist changes
        self.save_project()
        self.state_manager.notify_observers()
        
        return new_batch
        
    def get_batch(self, batch_id):
        """
        Get a batch by ID.
        
        Args:
            batch_id (str): The ID of the batch to retrieve
            
        Returns:
            BatchMetadata: The batch metadata object or None if not found
        """
        return self.state_manager.project_state.batches.get(batch_id)
        
    def get_batches(self):
        """
        Get all batches.
        
        Returns:
            dict: Dictionary of batch_id to BatchMetadata
        """
        return dict(self.state_manager.project_state.batches)
        
    def remove_from_batch(self, batch_id, experiment_id):
        """
        Remove an experiment from a batch.
        
        Args:
            batch_id (str): The ID of the batch
            experiment_id (str): The ID of the experiment to remove
        """
        if batch_id not in self.state_manager.project_state.batches:
            raise ValueError(f"Batch '{batch_id}' not found")
            
        # Remove from batch's experiment set
        if experiment_id in self.state_manager.project_state.batches[batch_id].experiment_ids:
            self.state_manager.project_state.batches[batch_id].experiment_ids.remove(experiment_id)
            
        # Remove batch reference from experiment
        if experiment_id in self.state_manager.project_state.experiments:
            if batch_id in self.state_manager.project_state.experiments[experiment_id].batch_ids:
                self.state_manager.project_state.experiments[experiment_id].batch_ids.remove(batch_id)
                
        # Persist changes
        self.save_project()
        self.state_manager.notify_observers()
        
    def delete_batch(self, batch_id):
        """
        Delete a batch and remove all references to it.
        
        Args:
            batch_id (str): The ID of the batch to delete
        """
        if batch_id not in self.state_manager.project_state.batches:
            raise ValueError(f"Batch '{batch_id}' not found")
            
        # Get all experiments in this batch
        batch = self.state_manager.project_state.batches[batch_id]
        exp_ids = list(batch.experiment_ids)
        
        # Remove batch reference from all experiments
        for exp_id in exp_ids:
            if exp_id in self.state_manager.project_state.experiments:
                if batch_id in self.state_manager.project_state.experiments[exp_id].batch_ids:
                    self.state_manager.project_state.experiments[exp_id].batch_ids.remove(batch_id)
                    
        # Delete the batch
        del self.state_manager.project_state.batches[batch_id]
        
        # Log deletion
        logger.info(f"Deleted batch '{batch_id}'")
        self.log_bus.log(f"Deleted batch '{batch_id}'", "info", "ProjectManager")
        
        # Persist changes
        self.save_project()
        self.state_manager.notify_observers()

    def rename_project(self, new_name: str) -> None:
        if not self._current_project_root:
            raise ValueError("No current project loaded")
        new_path = self._current_project_root.parent / new_name
        if new_path.exists():
            raise ValueError("A project with this name already exists")
        os.rename(self._current_project_root, new_path)
        self._current_project_root = new_path
        if self.state_manager.project_state and self.state_manager.project_state.project_metadata:
            self.state_manager.project_state.project_metadata.project_name = new_name
        self.save_project()

    def add_tracked_object(self, new_object: str) -> None:
        from .metadata import ObjectMetadata
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        if any(obj.name == new_object for obj in state.project_metadata.master_tracked_objects):
            raise ValueError(f"Object '{new_object}' already exists in master list.")
        object_metadata = ObjectMetadata(name=new_object)
        state.project_metadata.master_tracked_objects.append(object_metadata)

        self.save_project()
        self.state_manager.notify_observers()
    
    def update_tracked_objects(self, new_objects: list[str], list_type: str = "active") -> None:
        """Update the project's tracked objects list."""
        from .metadata import ObjectMetadata
        state = self.state_manager.project_state
        object_list = [ObjectMetadata(name=obj) if isinstance(obj, str) else obj
                       for obj in new_objects]
        
        if state.project_metadata is not None:
            if list_type in ["master", "both"]:
                state.project_metadata.master_tracked_objects = object_list
            if list_type in ["active", "both"]:
                state.project_metadata.active_tracked_objects = object_list
        else:
            # Remove fallback code; assume project_metadata always exists during development.
            raise RuntimeError("No project_metadata available.")
            
        self.save_project()
        logger.info(f"Updated {list_type} tracked objects to: {new_objects}")
        self.state_manager.notify_observers()

    def update_master_body_parts(self, new_bodyparts: list) -> bool:
        """
        Updates the project's master list of body parts by adding new, unique entries
        from the provided list. Does not remove existing body parts.

        Args:
            new_bodyparts: A list containing body part names (str) or BodyPartMetadata objects.

        Returns:
            True if the update was successful, False otherwise.
        """
        state = self.state_manager.project_state
        if state.project_metadata is None:
            logger.error("Cannot update master body parts: ProjectMetadata is not initialized.")
            return False

        try:
            # Current and target sets
            current_names = {bp.name for bp in state.project_metadata.master_body_parts}
            target_names: set[str] = set()

            # Normalise incoming list -> names list
            clean_new_parts: list[str] = []
            for bp_item in new_bodyparts:
                if isinstance(bp_item, str):
                    clean_new_parts.append(bp_item)
                elif isinstance(bp_item, BodyPartMetadata):
                    clean_new_parts.append(bp_item.name)
                elif isinstance(bp_item, dict) and 'name' in bp_item:
                    clean_new_parts.append(bp_item['name'])
                else:
                    logger.warning(f"Skipping invalid item in new_bodyparts list: {bp_item}")

            target_names = set(clean_new_parts)

            # If caller provided *fewer* parts than exist, assume replacement mode (supports deletion)
            replace_mode = len(target_names) < len(current_names)

            added_count = 0
            removed_count = 0

            if replace_mode:
                # Overwrite entire list preserving order of incoming list
                state.project_metadata.master_body_parts = [BodyPartMetadata(name=name) for name in clean_new_parts]
                removed_count = len(current_names - target_names)
                added_count = len(target_names - current_names)
            else:
                # Additive behaviour (original logic)
                for bp_name in clean_new_parts:
                    if bp_name not in current_names:
                        state.project_metadata.master_body_parts.append(BodyPartMetadata(name=bp_name))
                        current_names.add(bp_name)
                        added_count += 1

            if added_count or removed_count:
                logger.info(f"Master body-parts updated (added={added_count}, removed={removed_count}).")
                self.save_project()
                # Notify observers that master body parts have been updated
                self.state_manager.notify_observers()
            else:
                logger.info("Master body-parts list unchanged.")

            return True # Indicate success

        except Exception as e:
            logger.error(f"Failed to update master body parts list: {e}", exc_info=True)
            return False

    def update_active_body_parts(self, new_active_parts: list[str]) -> None:
        from .metadata import BodyPartMetadata
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("No project_metadata available.")
        active_list = []
        for bp in new_active_parts:
            if isinstance(bp, str):
                active_list.append(BodyPartMetadata(name=bp))
            elif hasattr(bp, 'name'):
                active_list.append(bp)
        state.project_metadata.active_body_parts = active_list

        self.save_project()
        logger.info(f"Active body parts updated to: {new_active_parts}")
        # Notify observers that active body parts have been updated
        self.state_manager.notify_observers()

    def list_available_projects(self, base_dir: Path | None = None) -> list[Path]:
        base_dir = self.get_projects_directory(base_dir)
        project_paths = []
        
        # Check if the base directory exists before iterating
        if not base_dir.is_dir():
            logger.warning(f"Projects directory not found at expected location: {base_dir}")
            return [] # Return empty list if the directory doesn't exist
            
        for item in base_dir.iterdir():
            # Ensure item is a directory and contains the project state file
            if item.is_dir() and (item / "project_state.json").exists():
                project_paths.append(item)

        # Example: Sort alphabetically by folder name
        project_paths.sort(key=lambda p: p.name.lower())

        return project_paths

    def refresh_all_lists(self):
        """Helper method to notify UI components that data has changed."""
        if hasattr(self.state_manager, 'notify_observers'):
            self.state_manager.notify_observers()

    def get_current_theme(self):
        """
        Retrieve the current theme from the state manager.
        
        Returns:
            str: Current theme preference ('dark', 'light', or 'os')
            
        This is different from get_effective_theme() which resolves 'os' to an actual theme.
        This method returns the raw preference stored in project metadata.
        """
        return self.state_manager.get_theme_preference()

    def apply_general_settings(self, *, sort_mode: str, frame_rate_enabled: bool, frame_rate: int) -> None:
        """Apply general settings (called by UI)."""
        if not self.state_manager:
            return
        if self.state_manager.project_state.project_metadata:
            self.state_manager.project_state.project_metadata.global_frame_rate = frame_rate
            self.state_manager.project_state.project_metadata.global_frame_rate_enabled = frame_rate_enabled
        self.state_manager.project_state.settings.update({
            "global_sort_mode": sort_mode,
            "global_frame_rate_enabled": frame_rate_enabled,
            "global_frame_rate": frame_rate,
        })
        self.save_project()
        self.state_manager.notify_observers()

    # New methods for Treatments and Genotypes
    def add_treatment(self, new_treatment: str) -> None:
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        if any(t.name == new_treatment for t in state.project_metadata.master_treatments):
            raise ValueError(f"Treatment '{new_treatment}' already exists in available treatments.")
        from .metadata import TreatmentMetadata
        state.project_metadata.master_treatments.append(TreatmentMetadata(name=new_treatment))
        self.save_project()
        self.state_manager.notify_observers()

    def add_genotype(self, new_genotype: str) -> None:
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        if any(g.name == new_genotype for g in state.project_metadata.master_genotypes):
            raise ValueError(f"Genotype '{new_genotype}' already exists in available genotypes.")
        from .metadata import GenotypeMetadata
        state.project_metadata.master_genotypes.append(GenotypeMetadata(name=new_genotype))
        self.save_project()
        self.state_manager.notify_observers()

    def update_active_treatments(self, active_treatments: list[str]) -> None:
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        from .metadata import TreatmentMetadata
        updated = [TreatmentMetadata(name=t) if isinstance(t, str) else t for t in active_treatments]
        state.project_metadata.active_treatments = updated
        self.save_project()
        self.state_manager.notify_observers()

    def update_active_genotypes(self, active_genotypes: list[str]) -> None:
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        from .metadata import GenotypeMetadata
        updated = [GenotypeMetadata(name=g) if isinstance(g, str) else g for g in active_genotypes]
        state.project_metadata.active_genotypes = updated
        self.save_project()
        self.state_manager.notify_observers()

    def remove_treatment(self, treatment: str) -> None:
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        state.project_metadata.master_treatments = [
            t for t in state.project_metadata.master_treatments if t.name != treatment
        ]
        state.project_metadata.active_treatments = [
            t for t in state.project_metadata.active_treatments if t.name != treatment
        ]
        self.save_project()
        self.state_manager.notify_observers()

    def remove_genotype(self, genotype: str) -> None:
        state = self.state_manager.project_state
        if state.project_metadata is None:
            raise RuntimeError("ProjectMetadata is not initialized.")
        state.project_metadata.master_genotypes = [
            g for g in state.project_metadata.master_genotypes if g.name != genotype
        ]
        state.project_metadata.active_genotypes = [
            g for g in state.project_metadata.active_genotypes if g.name != genotype
        ]
        self.save_project()
        self.state_manager.notify_observers()

    def run_analysis(self, experiment_id: str, capability_to_run: str) -> None:
        """
        Orchestrates running a specific analysis capability on an experiment.
        Finds the appropriate plugin, validates parameters, executes the plugin's
        analyze_experiment method (passing the DataManager), and updates the
        experiment state with results and processing stage.

        Args:
            experiment_id: The ID of the experiment to analyze.
            capability_to_run: The string identifier of the analysis capability to execute.

        Raises:
            ValueError: If the experiment, required plugins, or capability is not found/configured,
                        or if plugin validation fails.
            RuntimeError: If analysis execution fails or state update fails.
            FileNotFoundError: If essential data files referenced by parameters are missing.
        """
        self.log_bus.log(f"Attempting to run capability '{capability_to_run}' on experiment '{experiment_id}'...", "info", "ProjectManager")
        logger.info(f"Attempting to run capability '{capability_to_run}' on experiment '{experiment_id}'...")

        # --- 1. Get Experiment Metadata ---
        experiment = self.state_manager.get_experiment_by_id(experiment_id)
        if not experiment:
            msg = f"Analysis failed: Experiment '{experiment_id}' not found."
            self.log_bus.log(msg, "error", "ProjectManager")
            raise ValueError(msg)

        if not experiment.associated_plugins:
            msg = f"Analysis failed: Experiment '{experiment_id}' has no associated plugins."
            self.log_bus.log(msg, "error", "ProjectManager")
            raise ValueError(msg)

        # --- 2. Find Analysis Plugin ---
        analysis_plugin: Optional[BasePlugin] = None
        for plugin_name in experiment.associated_plugins:
            plugin = self.plugin_manager.get_plugin_by_name(plugin_name)
            # Ensure plugin exists and the capability is in its declared list
            if plugin and capability_to_run in plugin.analysis_capabilities():
                analysis_plugin = plugin
                break # Found a suitable plugin

        if not analysis_plugin:
            msg = f"No associated plugin found for experiment '{experiment_id}' that provides capability '{capability_to_run}'."
            self.log_bus.log(f"Analysis failed: {msg}", "error", "ProjectManager")
            raise ValueError(msg)

        plugin_display_name = analysis_plugin.plugin_self_metadata().name
        logger.debug(f"Found analysis plugin: {plugin_display_name}")

        # --- 3. Validate Experiment with Plugin (Pre-Analysis Check) ---
        try:
            logger.debug(f"Validating experiment parameters against plugin '{plugin_display_name}'...")
            # Pass the current project state for context if needed by validation logic
            analysis_plugin.validate_experiment(experiment, self.state_manager.project_state)
            logger.info(f"Plugin validation passed for '{plugin_display_name}'.")
        except ValueError as val_err:
            msg = f"Plugin validation failed for capability '{capability_to_run}' using '{plugin_display_name}': {val_err}"
            self.log_bus.log(f"Analysis aborted: {msg}", "error", "ProjectManager")
            logger.error(msg, exc_info=False) # No need for traceback for validation errors
            raise ValueError(msg) # Re-raise validation errors as ValueError
        except FileNotFoundError as fnf_err:
            msg = f"Plugin validation failed: Required file not found: {fnf_err}"
            self.log_bus.log(f"Analysis aborted: {msg}", "error", "ProjectManager")
            logger.error(msg, exc_info=False)
            raise FileNotFoundError(msg) # Re-raise file errors
        except Exception as e:
            msg = f"Unexpected error during plugin validation for '{plugin_display_name}': {e}"
            self.log_bus.log(f"Analysis aborted: {msg}", "error", "ProjectManager")
            logger.error(msg, exc_info=True) # Include traceback for unexpected errors
            raise RuntimeError(msg) # Raise other validation errors as RuntimeError

        # --- 4. Run Analysis (Plugin loads its own data) ---
        analysis_results: Dict[str, Any] = {}
        try:
             logger.info(f"Executing capability '{capability_to_run}' using plugin '{plugin_display_name}'...")
             # Pass the DataManager instance to the plugin.
             # The plugin is responsible for using it (or Handler helpers) to load necessary data
             # based on paths stored in experiment.plugin_params.
             analysis_results = analysis_plugin.analyze_experiment(
                 experiment=experiment,
                 data_manager=self.data_manager, # Pass DataManager instance
                 capability=capability_to_run
             )

             # --- 5. Check Results Status ---
             if not isinstance(analysis_results, dict) or analysis_results.get("status") != "success":
                 err_msg = analysis_results.get('error', 'Plugin execution failed or returned invalid status.')
                 self.log_bus.log(f"Analysis failed during execution: {err_msg}", "error", "ProjectManager")
                 logger.error(f"Plugin '{plugin_display_name}' failed execution for capability '{capability_to_run}': {err_msg}")
                 raise RuntimeError(f"Analysis failed: {err_msg}")

             self.log_bus.log(f"Capability '{capability_to_run}' executed successfully by '{plugin_display_name}' for '{experiment_id}'.", "success", "ProjectManager")
             logger.info(f"Capability '{capability_to_run}' executed successfully by '{plugin_display_name}'.")

        except FileNotFoundError as fnf_err:
             msg = f"Error executing capability '{capability_to_run}': Required data file not found: {fnf_err}"
             self.log_bus.log(f"Analysis failed: {msg}", "error", "ProjectManager")
             logger.error(msg, exc_info=False)
             raise FileNotFoundError(msg) # Re-raise file errors
        except Exception as e:
             msg = f"Error executing capability '{capability_to_run}' with plugin '{plugin_display_name}': {e}"
             self.log_bus.log(f"Analysis failed: {msg}", "error", "ProjectManager")
             logger.error(msg, exc_info=True) # Include traceback
             raise RuntimeError(f"Analysis execution failed: {e}")

        # --- 6. Update State ---
        try:
            # Ensure analysis_results exists before trying to update
            if experiment.analysis_results is None:
                experiment.analysis_results = {}

            # Store the results dictionary under the capability key
            experiment.analysis_results[capability_to_run] = analysis_results

            # Update processing stage based on capability (Refined Logic)
            # Data loading capabilities advance stage to 'tracked' if applicable.
            # Other analysis capabilities advance stage to 'interpreted' if applicable.
            current_stage = experiment.processing_stage
            new_stage = current_stage

            # Define known data loading capabilities (expand as needed)
            data_loading_capabilities = ['load_tracking_data'] # Example

            if capability_to_run in data_loading_capabilities:
                 # Only advance if currently planned or recorded
                 if current_stage in ["planned", "recorded"]:
                     new_stage = "tracked"
                     logger.info(f"Updating stage from '{current_stage}' to '{new_stage}' based on data loading.")
            else: # Assume it's an analysis/interpretation capability
                 # Only advance if currently planned, recorded, or tracked
                 if current_stage in ["planned", "recorded", "tracked"]:
                      new_stage = "interpreted"
                      logger.info(f"Updating stage from '{current_stage}' to '{new_stage}' based on analysis run.")

            if new_stage != current_stage:
                experiment.processing_stage = new_stage
                logger.debug(f"Experiment '{experiment_id}' stage updated to '{experiment.processing_stage}'.")
            else:
                 logger.debug(f"Experiment '{experiment_id}' stage remains '{current_stage}'.")

            # Save project state and notify observers
            self.save_project() # Save after successful analysis and state update
            self.state_manager.notify_observers() # Notify UI of changes
            self.log_bus.log(f"Experiment '{experiment_id}' updated successfully after analysis.", "info", "ProjectManager")
            logger.info(f"Experiment '{experiment_id}' state updated successfully after analysis.")

        except Exception as e:
            # Log error during state update, but analysis itself succeeded
            msg = f"Analysis succeeded, but failed to update experiment state for '{experiment_id}': {e}"
            self.log_bus.log(f"Post-analysis Error: {msg}", "error", "ProjectManager")
            logger.error(msg, exc_info=True)
            # Raise a runtime error because the state is now inconsistent
            raise RuntimeError(f"Failed to save analysis results or update state: {e}")

    # ------------------------------------------------------------------
    # Video ingestion helpers (unassigned → assigned workflow)
    # ------------------------------------------------------------------
    def register_unlinked_videos(self, video_iter: Iterable[tuple[Path, str, datetime]]) -> int:
        """Add newly discovered videos to *unassigned_videos*.
        Returns number of videos newly registered.
        """
        from .metadata import VideoMetadata  # Avoid circular ref
        state = self.state_manager.project_state
        new_count = 0
        for path, hsh, start_time in video_iter:
            if hsh in state.unassigned_videos or hsh in state.experiment_videos:
                continue
            try:
                vm = VideoMetadata(
                    path=path,
                    date=start_time,
                    sample_hash=hsh,
                    size_bytes=path.stat().st_size,
                    last_modified=path.stat().st_mtime,
                )
                state.unassigned_videos[hsh] = vm
                new_count += 1
            except Exception as exc:
                logger.warning(f"Failed to register video {path}: {exc}")
        if new_count:
            self.save_project()
            self.state_manager.notify_observers()
            self.log_bus.log(f"Registered {new_count} unassigned videos", "info", "ProjectManager")
        return new_count

    def link_unassigned_video(self, sample_hash: str, experiment_id: str) -> None:
        """Move a video from *unassigned_videos* into *experiment_videos* and link to an experiment."""
        state = self.state_manager.project_state
        if sample_hash not in state.unassigned_videos:
            raise ValueError(f"Video hash {sample_hash} not found in unassigned_videos")
        if experiment_id not in state.experiments:
            raise ValueError(f"Experiment {experiment_id} does not exist")

        vid_meta = state.unassigned_videos.pop(sample_hash)
        vid_meta.experiment_ids.add(experiment_id)
        state.experiment_videos[sample_hash] = vid_meta

        exp_meta = state.experiments[experiment_id]
        exp_meta.file_ids.add(sample_hash)

        self.save_project()
        self.state_manager.notify_observers()
        self.log_bus.log(
            f"Linked video {sample_hash} to experiment {experiment_id}",
            "success",
            "ProjectManager",
        )

    def run_project_level_plugin_action(self, plugin_name: str, capability_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a plugin capability that operates at the project level (e.g., importers),
        not tied to a specific experiment. It looks for a method like 'run_import'
        on the plugin instance.

        Args:
            plugin_name: The name of the plugin to run.
            capability_name: The specific capability identifier (used for logging/finding).
            parameters: A dictionary of parameters required by the plugin's action method.

        Returns:
            A dictionary containing the results or error information.
        """
        self.log_bus.log(f"Attempting project-level action: Plugin='{plugin_name}', Capability='{capability_name}'", "info", "ProjectManager")
        logger.info(f"Attempting project-level action: Plugin='{plugin_name}', Capability='{capability_name}' with params: {parameters}")

        # --- Find Plugin ---
        plugin = self.plugin_manager.get_plugin_by_name(plugin_name)
        if not plugin:
            msg = f"Plugin '{plugin_name}' not found."
            self.log_bus.log(f"Action failed: {msg}", "error", "ProjectManager")
            logger.error(msg)
            return {"status": "failed", "error": msg}

        # --- Check Capability (Optional but good practice) ---
        if capability_name not in plugin.analysis_capabilities():
             msg = f"Plugin '{plugin_name}' does not report capability '{capability_name}'."
             # Log as warning because the primary check is for the execution method
             logger.warning(msg)
             # Don't fail here, as the capability list might be for experiment analysis primarily

        # --- Find and Execute Action Method (Convention: 'run_import') ---
        # Based on DlcProjectImporterPlugin, we expect a 'run_import' method
        # We could make this more generic later if needed (e.g., 'run_<capability_name>')
        action_method_name = "run_import" # Convention based on the importer plugin
        if hasattr(plugin, action_method_name) and callable(getattr(plugin, action_method_name)):
            action_method = getattr(plugin, action_method_name)
            try:
                logger.debug(f"Executing '{action_method_name}' on plugin '{plugin_name}'...")
                # Call the method, passing the parameters and the ProjectManager instance
                result = action_method(params=parameters, project_manager=self)

                if not isinstance(result, dict):
                     logger.error(f"Plugin action method '{action_method_name}' returned non-dict type: {type(result)}")
                     raise RuntimeError("Plugin action method returned invalid result format.")

                status = result.get("status", "failed") # Default to failed if status missing
                if status == "success":
                    self.log_bus.log(f"Project-level action '{capability_name}' completed successfully.", "success", "ProjectManager")
                    logger.info(f"Project-level action '{capability_name}' completed successfully.")
                else:
                    err_msg = result.get('error', 'Unknown error during plugin action.')
                    self.log_bus.log(f"Project-level action failed: {err_msg}", "error", "ProjectManager")
                    logger.error(f"Project-level action '{capability_name}' failed: {err_msg}")

                return result # Return the dictionary from the plugin

            except Exception as e:
                msg = f"Error executing action '{action_method_name}' on plugin '{plugin_name}': {e}"
                self.log_bus.log(f"Action failed: {msg}", "error", "ProjectManager")
                logger.error(msg, exc_info=True)
                return {"status": "failed", "error": msg}
        else:
            msg = f"Plugin '{plugin_name}' does not have the required action method '{action_method_name}' for capability '{capability_name}'."
            self.log_bus.log(f"Action failed: {msg}", "error", "ProjectManager")
            logger.error(msg)
            return {"status": "failed", "error": msg}

    