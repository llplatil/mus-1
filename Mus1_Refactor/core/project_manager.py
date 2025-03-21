import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import os
import importlib.util
import inspect
import platform
from pydantic.json import pydantic_encoder

from .metadata import ProjectState, ProjectMetadata, Sex, ExperimentMetadata, ArenaImageMetadata, VideoMetadata, SubjectMetadata
from .state_manager import StateManager  # so we can type hint or reference if needed
from core.plugin_manager import PluginManager
from plugins.base_plugin import BasePlugin
from core.logging_bus import LoggingEventBus

logger = logging.getLogger("mus1.core.project_manager")

class ProjectManager:
    def __init__(self, state_manager: StateManager):
        """
        Args:
            state_manager: The main StateManager, which holds a ProjectState in memory.
        """
        self.state_manager = state_manager
        self._current_project_root: Path | None = None
        self.plugin_manager = PluginManager()
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("ProjectManager initialized", "info", "ProjectManager")
        
        # Plugins will be registered dynamically by scanning the plugins directory
        self._discover_and_register_plugins()
        
        # Decoupled plugin UI state from current state; not syncing plugin data into StateManager

    def _discover_and_register_plugins(self):
        """Discover and register all available plugins dynamically by scanning the plugins directory."""
        # Determine the plugins directory relative to the current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugins_dir = os.path.join(current_dir, "..", "plugins")

        # Iterate over all Python files in the plugins directory except base_plugin.py and __init__.py
        for filename in os.listdir(plugins_dir):
            if filename.endswith(".py") and filename not in ["base_plugin.py", "__init__.py"]:
                module_name = filename[:-3]
                module_path = os.path.join(plugins_dir, filename)

                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Import BasePlugin for checking subclass
                    from plugins.base_plugin import BasePlugin
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            self.plugin_manager.register_plugin(obj())

        self.log_bus.log(f"Registered {len(self.plugin_manager.get_all_plugins())} plugins", "success", "ProjectManager")
        logger.info(f"Registered {len(self.plugin_manager.get_all_plugins())} plugins")

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

    def load_project(self, project_root: Path) -> None:
        """
        Loads an existing project from project_state.json in project_root.
        Reconstructs the ProjectState and updates the StateManager.
        """
        logger.info(f"Loading project from {project_root}")
        state_path = project_root / "project_state.json"

        if not state_path.exists():
            logger.error(f"No project_state.json found at {state_path}")
            return

        with open(state_path, 'r') as f:
            data = json.load(f)

        # Pydantic reconstructs and validates the data according to ProjectState
        loaded_state = ProjectState(**data)
        logger.info("ProjectState loaded successfully from JSON.")

        # Make sure we completely replace the state_manager's project_state to ensure isolation
        # This is crucial for settings like frame_rate to be properly isolated between projects
        self.state_manager._project_state = loaded_state
        self._current_project_root = project_root
        logger.info("Project loaded and ready in memory.")
        
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

    def add_experiment(self, experiment_id, subject_id, date_recorded, exp_type, processing_stage, data_source, plugin_selections, plugin_params):
        # Core logic to add an experiment with hierarchical workflow
        # Compile associated plugin names from the selected plugins
        associated_plugins = [plugin.plugin_self_metadata().name for plugin in plugin_selections]

        new_experiment = ExperimentMetadata(
            id=experiment_id,
            type=exp_type,
            subject_id=subject_id,
            date_recorded=date_recorded,
            processing_stage=processing_stage,
            data_source=data_source,
            associated_plugins=associated_plugins,
            plugin_params=plugin_params
        )

        # Assign experiment to project state
        self.state_manager.project_state.experiments[experiment_id] = new_experiment

        # Update the corresponding subject with the new experiment id
        if subject_id in self.state_manager.project_state.subjects:
            self.state_manager.project_state.subjects[subject_id].experiment_ids.add(experiment_id)
            logger.info(f"Experiment {experiment_id} added to subject {subject_id}.")
        else:
            logger.warning(f"Subject {subject_id} not found when adding experiment {experiment_id}.")

        # Refresh UI and persist project data
        self.refresh_all_lists()
        self.save_project()
        self.state_manager.notify_observers()

        return new_experiment

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
        from core.metadata import BatchMetadata
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
        if not new_object:
            raise ValueError("Object name cannot be empty.")
        
        from core.metadata import ObjectMetadata
        state = self.state_manager.project_state
        
        # We now assume project_metadata exists – no fallback code.
        # Check duplicates in master list
        if any(obj.name == new_object for obj in state.project_metadata.master_tracked_objects):
            raise ValueError(f"Object '{new_object}' already exists in master list.")
        
        object_metadata = ObjectMetadata(name=new_object)
        state.project_metadata.master_tracked_objects.append(object_metadata)
        state.project_metadata.active_tracked_objects.append(object_metadata)
        
        self.save_project()
        self.state_manager.notify_observers()
    
    def update_tracked_objects(self, new_objects: list[str], list_type: str = "active") -> None:
        """Update the project's tracked objects list."""
        from core.metadata import ObjectMetadata
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

    def update_master_body_parts(self, new_bodyparts: list) -> None:
        from core.metadata import BodyPartMetadata
        state = self.state_manager.project_state
        if state.project_metadata is not None:
            master_list = []
            # Convert existing entries to BodyPartMetadata if they are strings
            for bp in state.project_metadata.master_body_parts:
                if isinstance(bp, str):
                    master_list.append(BodyPartMetadata(name=bp))
                else:
                    master_list.append(bp)

            # Add new body parts, converting strings if needed and avoiding duplicates
            for bp in new_bodyparts:
                if isinstance(bp, str):
                    if not any(existing.name == bp for existing in master_list):
                        master_list.append(BodyPartMetadata(name=bp))
                elif hasattr(bp, 'name'):
                    if not any(existing.name == bp.name for existing in master_list):
                        master_list.append(bp)

            state.project_metadata.master_body_parts = master_list
        else:
            state.settings["body_parts"] = new_bodyparts
        self.save_project()
        # Notify observers that master body parts have been updated
        self.state_manager.notify_observers()

    def update_active_body_parts(self, new_active_parts: list[str]) -> None:
        from core.metadata import BodyPartMetadata
        state = self.state_manager.project_state
        if state.project_metadata is not None:
            active_list = []
            for bp in new_active_parts:
                if isinstance(bp, str):
                    active_list.append(BodyPartMetadata(name=bp))
                elif hasattr(bp, 'name'):
                    active_list.append(bp)
            state.project_metadata.active_body_parts = active_list
        else:
            state.settings["body_parts"] = new_active_parts

        self.save_project()
        logger.info(f"Active body parts updated to: {new_active_parts}")
        # Notify observers that active body parts have been updated
        self.state_manager.notify_observers()

    def list_available_projects(self) -> list[Path]:
        base_dir = Path("projects")
        project_paths = []
        for item in base_dir.iterdir():
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

    def handle_apply_general_settings(self):
        """Apply the general settings."""
        sort_mode = self.sort_mode_dropdown.currentText()
        frame_rate_enabled = self.enable_frame_rate_checkbox.isChecked()
        frame_rate = self.frame_rate_spin.value()
        
        # Update the project-specific settings in the current project state
        if self.state_manager:
            # Store in project_metadata if it exists
            if self.state_manager.project_state.project_metadata:
                self.state_manager.project_state.project_metadata.global_frame_rate = frame_rate
                self.state_manager.project_state.project_metadata.global_frame_rate_enabled = frame_rate_enabled
                
            # Also store in the settings dictionary for backwards compatibility
            self.state_manager.project_state.settings.update({
                "global_sort_mode": sort_mode,
                "global_frame_rate_enabled": frame_rate_enabled,
                "global_frame_rate": frame_rate
            })
            
            # Save the project to persist these settings
            self.save_project()
            
            # Notify observers to update UI elements
            self.state_manager.notify_observers()
                
        self.navigation_pane.add_log_message("Applied general settings to current project.", "success")

    # New methods for Treatments and Genotypes
    def add_treatment(self, new_treatment: str) -> None:
        """
        Add a new treatment to the available treatments list.
        """
        if not new_treatment:
            raise ValueError("Treatment name cannot be empty.")
        state = self.state_manager.project_state
        # Initialize treatments dictionary in settings if not present
        treatments = state.settings.setdefault("treatments", {"available": [], "active": []})
        if new_treatment in treatments["available"]:
            raise ValueError(f"Treatment '{new_treatment}' already exists in available treatments.")
        treatments["available"].append(new_treatment)
        self.save_project()
        self.state_manager.notify_observers()

    def add_genotype(self, new_genotype: str) -> None:
        """
        Add a new genotype to the available genotypes list.
        """
        if not new_genotype:
            raise ValueError("Genotype name cannot be empty.")
        state = self.state_manager.project_state
        # Initialize genotypes dictionary in settings if not present
        genotypes = state.settings.setdefault("genotypes", {"available": [], "active": []})
        if new_genotype in genotypes["available"]:
            raise ValueError(f"Genotype '{new_genotype}' already exists in available genotypes.")
        genotypes["available"].append(new_genotype)
        self.save_project()
        self.state_manager.notify_observers()

    def update_active_treatments(self, active_treatments: list[str]) -> None:
        """
        Update the active treatments list.
        """
        state = self.state_manager.project_state
        treatments = state.settings.setdefault("treatments", {"available": [], "active": []})
        treatments["active"] = active_treatments
        self.save_project()
        self.state_manager.notify_observers()

    def update_active_genotypes(self, active_genotypes: list[str]) -> None:
        """
        Update the active genotypes list.
        """
        state = self.state_manager.project_state
        genotypes = state.settings.setdefault("genotypes", {"available": [], "active": []})
        genotypes["active"] = active_genotypes
        self.save_project()
        self.state_manager.notify_observers()

    def remove_treatment(self, treatment: str) -> None:
        """
        Remove a treatment from both the available and active lists.
        """
        state = self.state_manager.project_state
        treatments = state.settings.get("treatments", {"available": [], "active": []})
        if treatment in treatments["available"]:
            treatments["available"].remove(treatment)
        if treatment in treatments["active"]:
            treatments["active"].remove(treatment)
        self.save_project()
        self.state_manager.notify_observers()

    def remove_genotype(self, genotype: str) -> None:
        """
        Remove a genotype from both the available and active lists.
        """
        state = self.state_manager.project_state
        genotypes = state.settings.get("genotypes", {"available": [], "active": []})
        if genotype in genotypes["available"]:
            genotypes["available"].remove(genotype)
        if genotype in genotypes["active"]:
            genotypes["active"].remove(genotype)
        self.save_project()
        self.state_manager.notify_observers()

    