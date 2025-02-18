import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import os

from .metadata import ProjectState, ProjectMetadata, MouseMetadata, Sex, ExperimentType, ExperimentMetadata, SessionStage, ArenaImageMetadata, VideoMetadata
from .state_manager import StateManager  # so we can type hint or reference if needed
from plugins.base_plugin import PluginManager
from plugins.NOR_plugin import NORPlugin
from plugins.OF_plugin import OFPlugin

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
        # Register plugins using ExperimentType values
        self.plugin_manager.register_plugin("NOR", NORPlugin())
        self.plugin_manager.register_plugin("OpenField", OFPlugin())
        from plugins.BasicCSVPlot_plugin import BasicCSVPlotPlugin
        self.plugin_manager.register_plugin("BasicCSVPlot", BasicCSVPlotPlugin())

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
        else:
            logger.info(f"Creating a new mouse: {mouse_id}")
            new_mouse = MouseMetadata(
                id=mouse_id,
                sex=sex,
                genotype=genotype,
                treatment=treatment,
                notes=notes
            )
            self.state_manager.project_state.subjects[mouse_id] = new_mouse

        self.save_project()

        # Optionally refresh other views (experiments, etc.) if desired:
        # self.refresh_all_lists()

    def get_sorted_subjects(self, by: str = "id") -> list:
        """
        Returns a list of subject (mouse) metadata objects sorted either by 'id' or 'birthday'.
        If 'by' is 'id', numeric IDs appear first in ascending order, then alphabetical IDs.
        If 'by' is 'birthday', ascending order, with None birthdays at the end.
        """
        subjects_dict = self.state_manager.project_state.subjects
        subjects_list = list(subjects_dict.values())

        if by == "birthday":
            subjects_list.sort(key=lambda s: (s.birth_date is None, s.birth_date))
        else:  # default to "id"
            def parse_id_sort_key(subject):
                subject_id = subject.id
                index = 0
                while index < len(subject_id) and subject_id[index].isdigit():
                    index += 1
                if index > 0:
                    numeric_str = subject_id[:index]
                    numeric_prefix = int(numeric_str)
                    remainder = subject_id[index:]
                    return (0, numeric_prefix, remainder)
                else:
                    return (1, subject_id)
            subjects_list.sort(key=parse_id_sort_key)

        return subjects_list

    def get_sorted_experiments(self) -> list:
        """
        Returns experiments sorted according to the state manager's
        global_sort_mode setting (either 'name' or 'date').
        """
        return self.state_manager.get_experiments_list_sorted()

    def add_experiment(self, experiment_id, subject_id, date, exp_type, plugin_params):
        """
        Gathers the minimal experiment data, attaches plugin-specific fields,
        validates, and saves to project_state.
        """
        new_experiment = ExperimentMetadata(
            id=experiment_id,
            subject_id=subject_id,
            date_recorded=date,
            type=exp_type,
            plugin_params=plugin_params
        )

        # Validate subject existence
        if subject_id not in self.state_manager.project_state.subjects:
            raise ValueError(f"Subject '{subject_id}' not found in this project.")

        # Let PluginManager handle the check for a valid plugin
        self.plugin_manager.validate_experiment(new_experiment, self.state_manager.project_state)

        self.state_manager.project_state.experiments[experiment_id] = new_experiment
        self.save_project()
        return new_experiment

    def refresh_all_lists(self):
        """
        Placeholder for any logic or notifications needed so the UI
        can refresh both experiment and subject lists simultaneously.
        In a larger application, this might emit signals or call
        framework-specific update methods.
        """
        # For instance, you might:
        #  - reload self.state_manager.get_subject_ids()
        #  - reload self.state_manager.get_experiments_list()
        #  - notify any relevant views or widgets
        pass

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

    def update_master_body_parts(self, new_bodyparts: list) -> None:
        # Update master body parts with unique entries from new_bodyparts
        state = self.state_manager.project_state
        if state.project_metadata is not None:
            current_master = state.project_metadata.master_body_parts
            # Merge while preserving order and uniqueness
            updated = list(dict.fromkeys(current_master + new_bodyparts))
            state.project_metadata.master_body_parts = updated
        else:
            current_master = state.settings.get("body_parts", [])
            updated = list(dict.fromkeys(current_master + new_bodyparts))
            state.settings["body_parts"] = updated
        self.save_project()

    def update_active_body_parts(self, new_active_parts: list[str]) -> None:
        """
        Update the project's active body parts (subset of the master list).
        """
        state = self.state_manager.project_state
        if state.project_metadata is not None:
            # Overwrite the active_body_parts list with new_active_parts
            state.project_metadata.active_body_parts = new_active_parts
        else:
            # Fallback if no project_metadata is loaded
            state.settings["body_parts"] = new_active_parts

        self.save_project()
        logger.info(f"Active body parts updated to: {new_active_parts}")

    