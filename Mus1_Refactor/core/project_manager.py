import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import os
import importlib.util
import inspect

from .metadata import ProjectState, ProjectMetadata, MouseMetadata, Sex, ExperimentMetadata, ArenaImageMetadata, VideoMetadata
from .state_manager import StateManager  # so we can type hint or reference if needed
from core.plugin_manager import PluginManager
from plugins.base_plugin import BasePlugin

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
        
        # Plugins will be registered dynamically by scanning the plugins directory
        self._discover_and_register_plugins()
        
        # Sync state manager with plugin information
        self.state_manager.sync_supported_experiment_types(self.plugin_manager)
        self.state_manager.sync_plugin_metadatas(self.plugin_manager)
    
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

        logger.info(f"Registered {len(self.plugin_manager.get_all_plugins())} plugins")

    def create_project(self, project_root: Path, project_name: str) -> None:
        """
        Creates a new MUS1 project directory, initializes an empty ProjectState
        (including ProjectMetadata), and saves to project_state.json.

        Raises:
            FileExistsError: if the directory already exists.
        """
        # 1) Make sure the directory does not already exist
        if project_root.exists():
            raise FileExistsError(f"Directory '{project_root}' already exists.")

        # 2) Create the folder
        project_root.mkdir(parents=True, exist_ok=False)
        logger.info(f"Created project directory at {project_root}")

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
            # You can set DLC configs, body parts, etc. here if you like:
            dlc_configs=[],
            master_body_parts=[],
            active_body_parts=[],
            tracked_objects=[],
            global_frame_rate=60
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
            json.dump(data, f, indent=2, default=str)

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

        self.state_manager._project_state = loaded_state
        self._current_project_root = project_root
        logger.info("Project loaded and ready in memory.")

    def add_mouse(
        self,
        mouse_id: str,
        sex: Sex = Sex.UNKNOWN,
        genotype: Optional[str] = None,
        treatment: Optional[str] = None,
        notes: str = "",
        birth_date: Optional[datetime] = None,
        in_training_set: bool = False,
    ) -> None:
        """
        Create or update a MouseMetadata entry in the project's State.
        """
        existing = self.state_manager.project_state.subjects.get(mouse_id)
        if existing:
            logger.info(f"Updating existing mouse: {mouse_id}")
            existing.sex = sex
            existing.genotype = genotype
            existing.treatment = treatment
            existing.notes = notes
            existing.birth_date = birth_date
            existing.in_training_set = in_training_set
        else:
            # New mouse addition
            new_mouse = MouseMetadata(
                id=mouse_id,
                sex=sex,
                genotype=genotype,
                treatment=treatment,
                notes=notes,
                birth_date=birth_date,
                in_training_set=in_training_set
            )
            self.state_manager.project_state.subjects[mouse_id] = new_mouse
            logger.info(f"Added new mouse: {mouse_id}")
            self.refresh_all_lists()

        # Refresh UI lists to immediately display the updated subject list
        self.save_project()

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
        # Core logic to add a tracked object ensuring uniqueness
        if not new_object:
            raise ValueError("Object name cannot be empty.")
        state = self.state_manager.project_state
        if state.project_metadata is not None:
            if new_object in state.project_metadata.tracked_objects:
                raise ValueError(f"Object '{new_object}' already exists.")
            state.project_metadata.tracked_objects.append(new_object)
        else:
            objects = state.settings.get("tracked_objects", [])
            if new_object in objects:
                raise ValueError(f"Object '{new_object}' already exists.")
            objects.append(new_object)
            state.settings["tracked_objects"] = objects
        self.save_project()
    
    def update_tracked_objects(self, new_objects: list[str]) -> None:
        """
        Update the project's tracked objects list.
        """
        state = self.state_manager.project_state
        if state.project_metadata is not None:
            state.project_metadata.tracked_objects = new_objects
        else:
            state.settings["tracked_objects"] = new_objects
        self.save_project()
        logger.info(f"Tracked objects updated to: {new_objects}")
        # Notify observers about the change in tracked objects
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

    