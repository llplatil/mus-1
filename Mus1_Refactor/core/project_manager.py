import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from .metadata import ProjectState, ProjectMetadata, MouseMetadata, Sex, ExperimentType, ExperimentMetadata, SessionStage, ArenaImageMetadata, VideoMetadata
from .state_manager import StateManager  # so we can type hint or reference if needed

logger = logging.getLogger("mus1.core.project_manager")

class ProjectManager:
    def __init__(self, state_manager: StateManager):
        """
        Args:
            state_manager: The main StateManager, which holds a ProjectState in memory.
        """
        self.state_manager = state_manager
        self._current_project_root: Path | None = None

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

    def get_sorted_mice(self, by: str = "id") -> list[MouseMetadata]:
        """
        Returns a list of MouseMetadata objects sorted either by 'id' or 'birthday'.
        If 'by' is 'id', numeric IDs appear first in ascending order, then alphabetical IDs.
        If 'by' is 'birthday', ascending order, with None birthdays at the end.
        """
        mice_dict = self.state_manager.project_state.subjects
        mice_list = list(mice_dict.values())

        if by == "birthday":
            mice_list.sort(key=lambda m: (m.birth_date is None, m.birth_date))
        else:  # default to "id"
            def parse_id_sort_key(m: MouseMetadata):
                mouse_id = m.id
                index = 0
                while index < len(mouse_id) and mouse_id[index].isdigit():
                    index += 1
                if index > 0:
                    numeric_str = mouse_id[:index]
                    numeric_prefix = int(numeric_str)
                    remainder = mouse_id[index:]
                    return (0, numeric_prefix, remainder)
                else:
                    return (1, mouse_id)

            mice_list.sort(key=parse_id_sort_key)

        return mice_list

    def add_experiment(
        self,
        experiment_id: str,
        mouse_id: str,
        experiment_date: datetime,
        experiment_type: ExperimentType,
        session_stage: SessionStage = SessionStage.FAMILIARIZATION,
        notes: str = "",
        arena_image_id: Optional[str] = None,
        video_id: Optional[str] = None
    ) -> None:
        """
        Creates or updates an ExperimentMetadata entry in the project's State.
        Includes validation to ensure the specified mouse exists and can do the experiment_type.
        Optionally sets a session_stage, and can link an arena image or video if IDs are provided.
        """
        ps = self.state_manager.project_state

        if mouse_id not in ps.subjects:
            raise ValueError(f"Mouse ID '{mouse_id}' does not exist. Please add the mouse first.")

        mouse = ps.subjects[mouse_id]

        # Ensure this experiment type is allowed for this mouse (if the set is non-empty).
        # If 'allowed_experiment_types' is empty, we might treat that as "all are allowed," or
        # you could enforce that they must have the experiment in that set—your choice:
        if mouse.allowed_experiment_types and (experiment_type not in mouse.allowed_experiment_types):
            raise ValueError(
                f"Mouse {mouse_id} is not allowed to perform experiment type {experiment_type}."
            )

        existing = ps.experiments.get(experiment_id)
        if existing:
            logger.info(f"Updating existing experiment: {experiment_id}")
            existing.mouse_id = mouse_id
            existing.date = experiment_date
            existing.type = experiment_type
            existing.session_stage = session_stage
            existing.notes = notes
            self._link_image_and_video(existing, arena_image_id, video_id)
        else:
            logger.info(f"Creating a new experiment: {experiment_id}")
            new_exp = ExperimentMetadata(
                id=experiment_id,
                mouse_id=mouse_id,
                date=experiment_date,
                type=experiment_type,
                session_stage=session_stage,
                notes=notes
            )
            ps.experiments[experiment_id] = new_exp
            self._link_image_and_video(new_exp, arena_image_id, video_id)

        # Optionally, you can do something like: mouse.experiment_ids.add(experiment_id)
        # ps.subjects[mouse_id] = mouse

        # Optionally save the project
        # self.save_project()

    def _link_image_and_video(
        self,
        experiment: ExperimentMetadata,
        arena_image_id: Optional[str],
        video_id: Optional[str]
    ) -> None:
        """
        Helper method to link an ArenaImage or a Video to the given experiment,
        updating both references if they exist.
        """
        ps = self.state_manager.project_state
        if arena_image_id:
            if arena_image_id not in ps.arena_images:
                raise ValueError(f"Arena image {arena_image_id} does not exist in the project.")
            image_meta = ps.arena_images[arena_image_id]
            image_meta.experiment_ids.add(experiment.id)
            experiment.arena_image_path = image_meta.path

        if video_id:
            if video_id not in ps.experiment_videos:
                raise ValueError(f"Video {video_id} does not exist in the project.")
            vid_meta = ps.experiment_videos[video_id]
            vid_meta.experiment_ids.add(experiment.id)