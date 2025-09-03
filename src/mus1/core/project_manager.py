import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Callable
import os
import shutil
import time
import importlib
 
import inspect
import platform
from pydantic.json import pydantic_encoder
 
import yaml

from .metadata import ProjectState, ProjectMetadata, Sex, ExperimentMetadata, ArenaImageMetadata, VideoMetadata, SubjectMetadata, BodyPartMetadata, ObjectMetadata, TreatmentMetadata, GenotypeMetadata, PluginMetadata
from .state_manager import StateManager  # so we can type hint or reference if needed
from .plugin_manager import PluginManager
from ..plugins.base_plugin import BasePlugin
from .logging_bus import LoggingEventBus
from .data_manager import DataManager # Assuming DataManager might be used internally later
from .lab_manager import LabManager
from pydantic import ValidationError

logger = logging.getLogger("mus1.core.project_manager")

class ProjectManager:
    def __init__(self, state_manager: StateManager, plugin_manager: PluginManager, data_manager: DataManager, lab_manager: LabManager | None = None):
        """
        Args:
            state_manager: The main StateManager.
            plugin_manager: The shared PluginManager instance.
            data_manager: The shared DataManager instance.
            lab_manager: Optional LabManager for lab-level resource inheritance.
        """
        self.state_manager = state_manager
        self.plugin_manager = plugin_manager
        self.data_manager = data_manager
        self.lab_manager = lab_manager
        self._current_project_root: Path | None = None
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("ProjectManager initialized with shared managers", "info", "ProjectManager")
        
        # Discover external plugins via entry points (preferred in dev/refactor)
        try:
            self.plugin_manager.discover_entry_points()
        except Exception:
            pass
        
        # Sync core components after init
        self._sync_core_components()
        
        # Decoupled plugin UI state from current state; not syncing plugin data into StateManager

    def get_projects_directory(self, custom_base: Path | None = None) -> Path:
        """Return the directory where MUS1 projects are stored.

        Precedence for the base directory is:
        1. *custom_base* argument (used by CLI `--base-dir` or tests).
        2. Environment variable ``MUS1_PROJECTS_DIR`` if set.
        3. Per-user config file (same location as shared) key `projects_root`.
        4. User home default: ``~/MUS1/projects`` (consistent local location).

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
                # Fallback to per-user config (same scheme as get_shared_directory)
                try:
                    if platform.system() == "Darwin":
                        config_dir = Path.home() / "Library/Application Support/mus1"
                    elif os.name == "nt":
                        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
                        config_dir = Path(appdata) / "mus1"
                    else:
                        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
                        config_dir = Path(xdg) / "mus1"
                    yaml_path = config_dir / "config.yaml"
                    proj_root = None
                    if yaml_path.exists():
                        try:
                            with open(yaml_path, "r", encoding="utf-8") as f:
                                data = yaml.safe_load(f) or {}
                                pr = data.get("projects_root")
                                if pr:
                                    proj_root = Path(str(pr)).expanduser()
                        except Exception:
                            proj_root = None
                    if proj_root:
                        base_dir = Path(proj_root).expanduser().resolve()
                    else:
                        # Default to consistent user-local location
                        base_dir = (Path.home() / "MUS1" / "projects").expanduser().resolve()
                except Exception:
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
        """Discover and register all available plugins dynamically by importing modules and packages under plugins."""
        
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

        # Iterate over items in the plugins directory (using the first path if multiple exist)
        plugin_dir_path = plugins_package_paths[0]
        entries = []
        try:
            entries = list(os.scandir(plugin_dir_path))
        except Exception:
            entries = []
        for entry in entries:
            # Module file
            if entry.is_file() and entry.name.endswith(".py") and entry.name not in ["base_plugin.py", "__init__.py"]:
                module_name_short = entry.name[:-3]
                full_module_name = f"{plugins_module_name}.{module_name_short}"
                try:
                    logger.debug(f"Attempting to import plugin module: {full_module_name}")
                    module = importlib.import_module(full_module_name)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if inspect.getmodule(obj) == module and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            if inspect.isabstract(obj):
                                logger.info(f"Skipping abstract plugin class {name} (incomplete implementation).")
                                continue
                            try:
                                plugin_instance = obj()
                                self.plugin_manager.register_plugin(plugin_instance)
                            except Exception as init_err:
                                logger.error(f"Failed to instantiate plugin class {name} from {full_module_name}: {init_err}", exc_info=True)
                except Exception as e:
                    logger.error(f"Failed to import plugin module {full_module_name}: {e}", exc_info=False)

            # Package directory
            elif entry.is_dir() and (Path(entry.path) / "__init__.py").exists():
                pkg_name = entry.name
                full_pkg_name = f"{plugins_module_name}.{pkg_name}"
                try:
                    logger.debug(f"Attempting to import plugin package: {full_pkg_name}")
                    pkg = importlib.import_module(full_pkg_name)
                    # Import submodules to surface classes
                    try:
                        import pkgutil
                        for finder, modname, ispkg in pkgutil.walk_packages(pkg.__path__, prefix=f"{full_pkg_name}."):
                            try:
                                submod = importlib.import_module(modname)
                                for name, obj in inspect.getmembers(submod, inspect.isclass):
                                    if inspect.getmodule(obj) == submod and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                                        if inspect.isabstract(obj):
                                            continue
                                        try:
                                            plugin_instance = obj()
                                            self.plugin_manager.register_plugin(plugin_instance)
                                        except Exception as init_err:
                                            logger.error(f"Failed to instantiate plugin class {name} from {modname}: {init_err}", exc_info=True)
                            except Exception:
                                continue
                    except Exception:
                        pass
                    # Also scan package __init__
                    for name, obj in inspect.getmembers(pkg, inspect.isclass):
                        if inspect.getmodule(obj) == pkg and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            if not inspect.isabstract(obj):
                                try:
                                    plugin_instance = obj()
                                    self.plugin_manager.register_plugin(plugin_instance)
                                except Exception as init_err:
                                    logger.error(f"Failed to instantiate plugin class {name} from {full_pkg_name}: {init_err}", exc_info=True)
                except Exception as e:
                    logger.error(f"Failed to import plugin package {full_pkg_name}: {e}", exc_info=False)

        # Log summary after attempting all plugins
        registered_plugins = self.plugin_manager.get_all_plugins()
        log_message = f"Plugin discovery complete. Registered {len(registered_plugins)} plugins."
        self.log_bus.log(log_message, "info", "ProjectManager") # Log as info
        logger.info(log_message)

        # After discovery, sync the metadata into the state manager
        self.state_manager.sync_plugin_metadatas(self.plugin_manager)

    def get_shared_directory(self, custom_root: Path | None = None) -> Path:
        """Return the directory for shared MUS1 projects.

        Precedence for the base directory is:
        1. custom_root argument (explicit override from caller/UI)
        2. Environment variable MUS1_SHARED_DIR
        3. Per-user config file in OS config dir (config.yaml with key 'shared_root')

        The returned directory is created if it does not exist.
        """
        if custom_root:
            base_dir = Path(custom_root).expanduser().resolve()
        else:
            env_dir = os.environ.get("MUS1_SHARED_DIR")
            if env_dir:
                base_dir = Path(env_dir).expanduser().resolve()
            else:
                # Fallback to per-user config
                if platform.system() == "Darwin":
                    config_dir = Path.home() / "Library/Application Support/mus1"
                elif os.name == "nt":
                    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
                    config_dir = Path(appdata) / "mus1"
                else:
                    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
                    config_dir = Path(xdg) / "mus1"
                yaml_path = config_dir / "config.yaml"
                shared_root = None
                if yaml_path.exists():
                    try:
                        with open(yaml_path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}
                            sr = data.get("shared_root")
                            if sr:
                                shared_root = Path(str(sr)).expanduser()
                    except Exception:
                        shared_root = None
                if not shared_root:
                    raise EnvironmentError("Shared root not configured. Set MUS1_SHARED_DIR or run 'mus1 setup shared'.")
                base_dir = Path(shared_root).expanduser().resolve()

        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

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
        try:
            import platform
            sysname = platform.system().lower()
            if sysname == "windows":
                # Best-effort detect WSL when running inside it
                try:
                    import os as _os
                    if "microsoft" in (open("/proc/version","r").read().lower() if Path("/proc/version").exists() else ""):
                        sysname = "wsl"
                except Exception:
                    pass
            new_state.host_os = sysname
        except Exception:
            new_state.host_os = None
        self.state_manager._project_state = new_state
        self._current_project_root = project_root
        # Keep DataManager aware of active project root for output paths
        try:
            self.data_manager.set_project_root(project_root)
        except Exception:
            pass

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
        lock_path = self._current_project_root / ".mus1-lock"
        data = self.state_manager.project_state.dict()

        start_time = time.time()
        lock_fd = None
        try:
            # Simple advisory lock using a lockfile with O_EXCL semantics
            while True:
                try:
                    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    break
                except FileExistsError:
                    if (time.time() - start_time) > 10.0:
                        raise RuntimeError(
                            f"Could not acquire project save lock at {lock_path} after 10s"
                        )
                    time.sleep(0.1)

            # Write PID into lock for debugging
            with os.fdopen(lock_fd, 'w') as lock_file:
                lock_file.write(str(os.getpid()))

            # Atomic write via temp file then rename
            tmp_path = state_path.with_suffix('.tmp')
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2, default=pydantic_encoder)
            os.replace(tmp_path, state_path)

            logger.info(f"Project saved to {state_path}")
        finally:
            try:
                if lock_fd is not None and not lock_file.closed:
                    # Already closed by context manager; keep safe
                    pass
            except Exception:
                pass
            try:
                if lock_path.exists():
                    os.unlink(lock_path)
            except Exception:
                # Best effort cleanup
                pass

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
        # Update DataManager project root
        try:
            self.data_manager.set_project_root(project_root)
        except Exception:
            pass
        # Update host_os each load
        try:
            import platform as _platform
            sysname = _platform.system().lower()
            if sysname == "windows":
                try:
                    if "microsoft" in (open("/proc/version","r").read().lower() if Path("/proc/version").exists() else ""):
                        sysname = "wsl"
                except Exception:
                    pass
            self.state_manager.project_state.host_os = sysname
        except Exception:
            pass
        logger.info("Project loaded and ready in memory.")

        # Sync plugins into the loaded state
        self._sync_core_components()

        # Notify observers about the project change to refresh UI components
        self.state_manager.notify_observers()

    def associate_with_lab(self, lab_id: str, config_dir: Path | None = None) -> None:
        """Associate the current project with a lab configuration.

        Args:
            lab_id: ID of the lab to associate with
            config_dir: Optional directory containing lab configs

        Raises:
            RuntimeError: If no project is loaded or lab association fails
        """
        if self._current_project_root is None:
            raise RuntimeError("No project loaded - cannot associate with lab")

        if self.lab_manager is None:
            raise RuntimeError("No LabManager available for lab association")

        try:
            # Load the lab configuration
            lab_config = self.lab_manager.load_lab(lab_id, config_dir)

            # Associate the project with the lab
            self.lab_manager.associate_project(self._current_project_root)

            # Update project metadata to reference the lab
            if self.state_manager.project_state.project_metadata:
                self.state_manager.project_state.project_metadata.lab_id = lab_id

            self.save_project()
            self.log_bus.log(f"Associated project with lab '{lab_config.metadata.name}'", "success", "ProjectManager")

        except FileNotFoundError:
            raise RuntimeError(f"Lab configuration '{lab_id}' not found")
        except Exception as e:
            self.log_bus.log(f"Failed to associate project with lab '{lab_id}': {e}", "error", "ProjectManager")
            raise RuntimeError(f"Failed to associate project with lab: {e}")

    def get_workers(self) -> list:
        """Get workers from the associated lab."""
        if not self.lab_manager or not self.lab_manager.current_lab:
            raise RuntimeError("No lab associated with this project")
        return self.lab_manager.current_lab.workers

    def get_credentials(self) -> dict:
        """Get credentials from the associated lab."""
        if not self.lab_manager or not self.lab_manager.current_lab:
            raise RuntimeError("No lab associated with this project")
        return self.lab_manager.current_lab.credentials

    def get_scan_targets(self) -> list:
        """Get scan targets from the associated lab."""
        if not self.lab_manager or not self.lab_manager.current_lab:
            raise RuntimeError("No lab associated with this project")
        return self.lab_manager.current_lab.scan_targets

    def get_master_subjects(self) -> dict:
        """Get master subjects from the associated lab."""
        if not self.lab_manager or not self.lab_manager.current_lab:
            raise RuntimeError("No lab associated with this project")
        return self.lab_manager.current_lab.master_subjects

    def get_lab_id(self) -> str | None:
        """Get the lab ID associated with the current project."""
        if self.state_manager.project_state.project_metadata:
            return getattr(self.state_manager.project_state.project_metadata, 'lab_id', None)
        return None

    def is_lab_associated(self) -> bool:
        """Check if the current project is associated with a lab."""
        return self.get_lab_id() is not None

    def get_lab_name(self) -> str | None:
        """Get the lab name associated with the current project."""
        lab_id = self.get_lab_id()
        if lab_id and self.lab_manager and self.lab_manager.current_lab:
            return self.lab_manager.current_lab.metadata.name
        return None

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
        exp_subtype: str | None,
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
                experiment_subtype=exp_subtype,
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
    def create_experiment_from_recording(
        self,
        *,
        recording_path: Path,
        subject_id: str,
        experiment_type: str,
        experiment_subtype: str | None = None,
    ) -> str:
        """Create an experiment auto-named from recording folder and link the recording.

        Returns the new experiment_id.
        """
        rec_dir = Path(recording_path).parent
        exp_id = rec_dir.name
        # Derive date from recording metadata if available, else from file mtime
        try:
            md = self.data_manager.read_recording_metadata(rec_dir)
            from datetime import datetime as _dt
            rt = ((md.get("times") or {}).get("recorded_time")) if md else None
            if rt:
                date_recorded = _dt.fromisoformat(str(rt))
            else:
                date_recorded = _dt.fromtimestamp(max(recording_path.stat().st_mtime, recording_path.stat().st_ctime))
        except Exception:
            from datetime import datetime as _dt
            date_recorded = _dt.fromtimestamp(max(recording_path.stat().st_mtime, recording_path.stat().st_ctime))

        self.add_experiment(
            experiment_id=exp_id,
            subject_id=subject_id,
            date_recorded=date_recorded,
            exp_type=experiment_type,
            exp_subtype=experiment_subtype,
            processing_stage="recorded",
            associated_plugins=[],
            plugin_params={},
        )

        # Link video to experiment
        self.link_video_to_experiment(experiment_id=exp_id, video_path=recording_path)
        return exp_id

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
        try:
            self.data_manager.set_project_root(new_path)
        except Exception:
            pass
        if self.state_manager.project_state and self.state_manager.project_state.project_metadata:
            self.state_manager.project_state.project_metadata.project_name = new_name
        self.save_project()

    def move_project_to_directory(self, new_parent_dir: Path) -> Path:
        """Move the current project directory under *new_parent_dir* preserving its folder name.

        Returns the new absolute project path.
        """
        if not self._current_project_root:
            raise ValueError("No current project loaded")
        new_parent_dir = Path(new_parent_dir).expanduser().resolve()
        if not new_parent_dir.exists():
            new_parent_dir.mkdir(parents=True, exist_ok=True)
        old_root = self._current_project_root
        new_root = new_parent_dir / old_root.name
        if new_root.exists():
            raise FileExistsError(f"Destination already exists: {new_root}")
        # Use shutil.move to support cross-filesystem moves
        shutil.move(str(old_root), str(new_root))
        self._current_project_root = new_root
        try:
            self.data_manager.set_project_root(new_root)
        except Exception:
            pass
        # Persist and notify
        self.save_project()
        self.state_manager.notify_observers()
        self.log_bus.log(f"Moved project to {new_root}", "info", "ProjectManager")
        return new_root

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
        host = os.uname().nodename if hasattr(os, "uname") else platform.node()
        seen_at = datetime.now()
        updated_any = False
        for path, hsh, start_time in video_iter:
            try:
                # If known in unassigned or experiment videos, update last_seen_locations only
                vm: Optional[VideoMetadata] = None
                if hsh in state.unassigned_videos:
                    vm = state.unassigned_videos[hsh]
                elif hsh in state.experiment_videos:
                    vm = state.experiment_videos[hsh]

                if vm is None:
                    # Read per-recording metadata.json if present
                    rec_dir = Path(path).parent
                    md: dict[str, Any] = {}
                    try:
                        md = self.data_manager.read_recording_metadata(rec_dir)
                    except Exception:
                        md = {}
                    # Populate from metadata if available
                    recorded_time = start_time
                    if md:
                        try:
                            times = md.get("times") or {}
                            rt = times.get("recorded_time")
                            if rt:
                                from datetime import datetime as _dt
                                recorded_time = _dt.fromisoformat(str(rt))
                        except Exception:
                            recorded_time = start_time
                    # Create video metadata entry
                    vm = VideoMetadata(
                        path=path,
                        date=recorded_time,
                        sample_hash=hsh,
                        size_bytes=path.stat().st_size,
                        last_modified=path.stat().st_mtime,
                        last_seen_locations=[],
                    )
                    state.unassigned_videos[hsh] = vm
                    new_count += 1
                    updated_any = True

                # update last_seen_locations for both new and existing
                try:
                    vm.last_seen_locations.append({
                        "path": str(Path(path).expanduser().resolve()),
                        "host": host,
                        "seen_at": seen_at.isoformat(),
                    })
                    updated_any = True
                except Exception:
                    pass
            except Exception as exc:
                logger.warning(f"Failed to register/update video {path}: {exc}")
        if new_count or updated_any:
            self.save_project()
            self.state_manager.notify_observers()
            self.log_bus.log(f"Registered {new_count} unassigned videos", "info", "ProjectManager")
        return new_count

    # ------------------------------------------------------------------
    # Ingestion helpers used by CLI/GUI
    # ------------------------------------------------------------------
    def ingest(
        self,
        *,
        project_path: Path,
        roots: list[Path] | None,
        dest_subdir: str = "recordings/raw",
        extensions: list[str] | None = None,
        exclude_dirs: list[str] | None = None,
        non_recursive: bool = False,
        preview: bool = False,
        emit_in_shared: Path | None = None,
        emit_off_shared: Path | None = None,
        parallel: bool = False,
        max_workers: int = 4,
        scan_progress_cb: Callable | None = None,
        dedup_progress_cb: Callable | None = None,
        stage_progress_cb: Callable | None = None,
        target_names: list[str] | None = None,
    ) -> Dict[str, Any]:
        """Scan → dedup → split, optionally stage off-shared into shared_root/dest_subdir, then register.

        Returns a result dict; no printing or CLI side-effects.
        """
        # Load project and resolve roots
        self.load_project(project_path)
        dm = self.data_manager

        # Scan: either via targets or filesystem roots
        videos: list[tuple[Path, str]] = []
        if target_names:
            # Use lab-level scan targets
            try:
                lab_targets = self.get_scan_targets()
                targets = [t for t in lab_targets if t.name in set(target_names)] if target_names else lab_targets
                if not targets:
                    return {"status": "failed", "error": "No matching scan targets configured in lab."}
                # Use scanners.remote helpers
                from .scanners.remote import collect_from_targets, collect_from_targets_parallel
                items = collect_from_targets_parallel(self.state_manager, dm, targets, extensions=extensions, exclude_dirs=exclude_dirs, non_recursive=non_recursive, max_workers=max_workers) if parallel else collect_from_targets(self.state_manager, dm, targets, extensions=extensions, exclude_dirs=exclude_dirs, non_recursive=non_recursive)
                videos.extend(items)
            except RuntimeError as e:
                return {"status": "failed", "error": f"No lab associated: {e}"}
            except Exception as e:
                return {"status": "failed", "error": f"Target scan failed: {e}"}
        else:
            try:
                from .scanners.video_discovery import default_roots_if_missing, select_local_scanner
                effective_roots = default_roots_if_missing(roots)
            except Exception:
                effective_roots = roots or []
            if not effective_roots:
                return {"status": "failed", "error": "No scan roots provided and no defaults available for this OS."}

            if parallel and len(effective_roots) > 1:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                scanner = select_local_scanner()
                def _scan(root: Path):
                    return list(scanner.iter_videos([root], extensions=extensions or None, recursive=not non_recursive, excludes=exclude_dirs or None, progress_cb=None))
                with ThreadPoolExecutor(max_workers=max_workers) as exe:
                    futs = {exe.submit(_scan, r): r for r in effective_roots}
                    for fut in as_completed(futs):
                        try:
                            videos.extend(fut.result())
                        except Exception:
                            continue
            else:
                scanner = select_local_scanner()
                for p, h in scanner.iter_videos(effective_roots, extensions=extensions or None, recursive=not non_recursive, excludes=exclude_dirs or None, progress_cb=scan_progress_cb):
                    videos.append((p, h))

        # Dedup and split
        dedup_gen = dm.deduplicate_video_list(videos, progress_cb=dedup_progress_cb)
        in_shared, off_shared = self.split_by_shared_root(dedup_gen)

        # Optional emit
        try:
            if emit_in_shared:
                dm.emit_jsonl(emit_in_shared, in_shared)
        except Exception:
            pass
        try:
            if emit_off_shared:
                dm.emit_jsonl(emit_off_shared, off_shared)
        except Exception:
            pass

        if preview:
            return {
                "status": "success",
                "preview": True,
                "in_shared_count": len(in_shared),
                "off_shared_count": len(off_shared),
                "project_path": str(project_path),
            }

        # Register in-shared
        added_in = self.register_unlinked_videos(iter(in_shared))

        # Resolve shared root
        sr = self.state_manager.project_state.shared_root
        if not sr:
            try:
                sr = self.get_shared_directory()
            except Exception as e:
                return {"status": "failed", "error": f"Shared root not configured and not resolvable: {e}"}
        shared_root = Path(sr).expanduser().resolve()

        # Writability test (no side effects)
        def _is_writable(p: Path) -> bool:
            try:
                p.mkdir(parents=True, exist_ok=True)
                test = p / ".mus1-write-test"
                test.write_text("ok", encoding="utf-8")
                test.unlink(missing_ok=True)
                return True
            except Exception:
                return False

        if off_shared and not _is_writable(shared_root):
            # Caller (CLI/GUI) can decide how to persist the off-shared list
            return {
                "status": "success",
                "in_shared_registered": added_in,
                "off_shared_pending": len(off_shared),
                "not_writable": True,
            }

        # Stage off-shared into shared_root/dest_subdir
        dest_base = (shared_root / dest_subdir).expanduser().resolve()
        staged_iter = dm.stage_files_to_shared(
            [(p, h) for p, h, _ in off_shared],
            shared_root=shared_root,
            dest_base=dest_base,
            overwrite=False,
            progress_cb=stage_progress_cb,
        )
        added_off = self.register_unlinked_videos(staged_iter)

        return {
            "status": "success",
            "in_shared_registered": added_in,
            "off_shared_staged_registered": added_off,
            "total_unassigned": len(self.state_manager.project_state.unassigned_videos),
            "not_writable": False,
        }

    def import_third_party_folder(
        self,
        *,
        project_path: Path,
        source_dir: Path,
        copy: bool = True,
        recursive: bool = True,
        verify_time: bool = False,
        provenance: str = "third_party_import",
    ) -> Dict[str, Any]:
        """Import a third-party processed folder into this project's media with provenance notes.

        - Hashes discovered media files under source_dir
        - Stages them into <project>/media per-recording folders
        - Registers as unassigned videos
        - Adds provenance info to per-recording metadata.json
        """
        self.load_project(project_path)
        dm = self.data_manager

        sd = Path(source_dir).expanduser().resolve()
        if not sd.exists() or not sd.is_dir():
            return {"status": "failed", "error": f"Source directory not found: {sd}"}

        # Collect media files
        exts = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}
        files: list[Path] = []
        if recursive:
            for p in sd.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    files.append(p)
        else:
            for p in sd.iterdir():
                if p.is_file() and p.suffix.lower() in exts:
                    files.append(p)
        if not files:
            return {"status": "success", "added": 0, "message": "No media files found to import."}

        # Hash and stage into media
        staged: list[tuple[Path, str]] = []
        for p in files:
            try:
                h = dm.compute_sample_hash(p)
                staged.append((p, h))
            except Exception:
                continue

        media_dir = (project_path / "media").expanduser().resolve()
        media_dir.mkdir(parents=True, exist_ok=True)
        gen = dm.stage_files_to_shared(
            staged,
            shared_root=project_path,  # treat project as shared root to allow existing-under-root logic
            dest_base=media_dir,
            overwrite=False,
            progress_cb=None,
            delete_source_on_success=not copy,
            namer=None,
            verify_time=verify_time,
        )
        added = self.register_unlinked_videos(gen)

        # Apply provenance and original path note
        try:
            for vm in list(self.state_manager.project_state.unassigned_videos.values()):
                p = Path(vm.path)
                if str(p).startswith(str(media_dir)):
                    md = dm.read_recording_metadata(p.parent)
                    if md:
                        prov = md.setdefault("provenance", {})
                        prov["source"] = provenance
                        notes = prov.get("notes", "")
                        if sd.as_posix() not in notes:
                            prov["notes"] = (notes + f"; imported_from={sd.as_posix()}").strip("; ")
                        dm.write_recording_metadata(p.parent, md)
        except Exception:
            pass

        return {"status": "success", "added": added}
    def split_by_shared_root(
        self,
        items: Iterable[tuple[Path, str, datetime]],
    ) -> tuple[list[tuple[Path, str, datetime]], list[tuple[Path, str, datetime]]]:
        """Split items into (in_shared, off_shared) based on project.shared_root.

        Returns:
            (in_shared, off_shared): lists of tuples suitable for registration/staging
        """
        sr = self.state_manager.project_state.shared_root
        sr_path = Path(sr).expanduser().resolve() if sr else None
        in_shared: list[tuple[Path, str, datetime]] = []
        off_shared: list[tuple[Path, str, datetime]] = []
        for p, h, ts in items:
            try:
                rp = Path(p).expanduser().resolve()
                if sr_path and str(rp).startswith(str(sr_path)):
                    in_shared.append((rp, h, ts))
                else:
                    off_shared.append((rp, h, ts))
            except Exception:
                off_shared.append((Path(p), h, ts))
        return in_shared, off_shared

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

    # ------------------------------------------------------------------
    # App-level APIs (GUI/services) for master library and MoSeq import
    # ------------------------------------------------------------------
    def build_master_library(
        self,
        *,
        project_path: Path,
        dest_subdir: str = "recordings/master",
        copy_exts: list[str] | None = None,
        move_exts: list[str] | None = None,
        filename_pattern: str = "{base}_{date:%Y%m%d}_{hash8}{ext}",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Create a flat master media library under the project's shared root.

        - Sources: known videos (unassigned + experiment_videos)
        - Policy: copy for copy_exts, move for move_exts
        - Naming: filename_pattern supports {subject},{experiment},{date:%Y%m%d},{hash8},{base},{ext}
        - Registers staged/moved videos as unassigned
        """
        from datetime import datetime as _dt

        # Ensure project and shared root
        self.load_project(project_path)
        sr = self.state_manager.project_state.shared_root or self.get_shared_directory()
        shared_root = Path(sr).expanduser().resolve()
        dest_base = (shared_root / dest_subdir).expanduser().resolve()

        ps = self.state_manager.project_state
        dm = self.data_manager

        # Materialize known videos with hashes and dates
        items: list[tuple[Path, str, _dt]] = []
        def _ensure(vm) -> tuple[Path, str, _dt] | None:
            try:
                p = Path(vm.path)
                if not p.exists():
                    return None
                h = vm.sample_hash or dm.compute_sample_hash(p)
                dt = getattr(vm, "date", None) or dm._extract_start_time(p)
                return (p, str(h), dt)
            except Exception:
                return None

        for vm in ps.unassigned_videos.values():
            t = _ensure(vm)
            if t:
                items.append(t)
        for vm in ps.experiment_videos.values():
            t = _ensure(vm)
            if t:
                items.append(t)

        if not items:
            return {"status": "success", "copied": 0, "moved": 0, "message": "No known videos"}

        # Build lookup for naming
        hash_to_vm = {h: vm for h, vm in ((vm.sample_hash, vm) for vm in list(ps.unassigned_videos.values()) + list(ps.experiment_videos.values())) if h}
        exp_by_id = ps.experiments

        def _namer(src_path: Path) -> str:
            # Deprecated: no-op; file will be placed under per-recording folder keeping original filename
            return Path(src_path).name

        copy_exts = [e.lower() for e in (copy_exts or [".mp4"])]
        move_exts = [e.lower() for e in (move_exts or [".mkv"])]
        allow = set(copy_exts + move_exts)
        src_copy: list[tuple[Path, str]] = []
        src_move: list[tuple[Path, str]] = []
        for p, h, _ in items:
            if p.suffix.lower() not in allow:
                continue
            if p.suffix.lower() in move_exts:
                src_move.append((p, h))
            else:
                src_copy.append((p, h))

        if dry_run:
            return {"status": "success", "planned_copy": len(src_copy), "planned_move": len(src_move), "destination": str(dest_base)}

        added_total = 0
        if src_copy:
            gen_copy = dm.stage_files_to_shared(src_copy, shared_root=shared_root, dest_base=dest_base, overwrite=False, progress_cb=None, delete_source_on_success=False, namer=_namer)
            added_total += self.register_unlinked_videos(gen_copy)
        if src_move:
            gen_move = dm.stage_files_to_shared(src_move, shared_root=shared_root, dest_base=dest_base, overwrite=False, progress_cb=None, delete_source_on_success=True, namer=_namer)
            added_total += self.register_unlinked_videos(gen_move)
        return {"status": "success", "registered": added_total, "destination": str(dest_base)}

    def import_moseq_media(
        self,
        *,
        project_path: Path,
        moseq_root: Path,
        dest_subdir: str = "recordings/master",
        require_proc: bool = True,
        filename_pattern: str = "{base}_{date:%Y%m%d}_{hash8}{ext}",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Import MoSeq .mkv sessions from moseq_root into a flat master library (move)."""
        from datetime import datetime as _dt

        self.load_project(project_path)
        sr = self.state_manager.project_state.shared_root or self.get_shared_directory()
        shared_root = Path(sr).expanduser().resolve()
        dest_base = (shared_root / dest_subdir).expanduser().resolve()

        dm = self.data_manager
        mr = Path(moseq_root).expanduser().resolve()
        if not mr.exists():
            return {"status": "failed", "error": f"MoSeq root not found: {mr}"}

        mkv_paths: list[Path] = []
        for p in mr.glob("**/*.mkv"):
            if not p.is_file():
                continue
            if require_proc and not (p.parent / "proc" / "results_00.mp4").exists():
                continue
            mkv_paths.append(p)

        if not mkv_paths:
            return {"status": "success", "moved": 0, "message": "No matching MoSeq .mkv files found"}

        if dry_run:
            return {"status": "success", "planned": len(mkv_paths), "destination": str(dest_base)}

        def _namer(src_path: Path) -> str:
            base = src_path.stem
            ext = src_path.suffix
            try:
                h = dm.compute_sample_hash(src_path)
                hash8 = h[:8]
            except Exception:
                hash8 = ""
            try:
                st = dm._extract_start_time(src_path)
            except Exception:
                st = _dt.fromtimestamp(src_path.stat().st_mtime)
            try:
                name = filename_pattern.format(base=base, ext=ext, date=st, hash8=hash8, subject="", experiment="")
            except Exception:
                name = f"{base}_{hash8}{ext}" if hash8 else f"{base}{ext}"
            if not name.endswith(ext):
                name = f"{name}{ext}"
            return Path(name).name

        src_move = []
        for p in mkv_paths:
            try:
                src_move.append((p, dm.compute_sample_hash(p)))
            except Exception:
                continue

        gen_move = dm.stage_files_to_shared(src_move, shared_root=shared_root, dest_base=dest_base, overwrite=False, progress_cb=None, delete_source_on_success=True, namer=_namer)
        added = self.register_unlinked_videos(gen_move)
        return {"status": "success", "moved": added, "destination": str(dest_base)}

    def run_project_level_plugin_action(self, plugin_name: str, capability_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a project-level action on a plugin (e.g., importers/utilities).
        Convention: the plugin exposes a callable method named 'run_import(params, project_manager)'.
        """
        self.log_bus.log(
            f"Attempting project-level action: Plugin='{plugin_name}', Capability='{capability_name}'",
            "info",
            "ProjectManager",
        )
        logger.info(
            f"Attempting project-level action: Plugin='{plugin_name}', Capability='{capability_name}' with params: {parameters}"
        )

        plugin = self.plugin_manager.get_plugin_by_name(plugin_name)
        if not plugin:
            msg = f"Plugin '{plugin_name}' not found."
            self.log_bus.log(f"Action failed: {msg}", "error", "ProjectManager")
            logger.error(msg)
            return {"status": "failed", "error": msg}

        # Optional: warn if capability is not advertised
        try:
            if capability_name not in (plugin.analysis_capabilities() or []):
                logger.warning(
                    f"Plugin '{plugin_name}' does not report capability '{capability_name}'. Proceeding with action call."
                )
        except Exception:
            pass

        # Prefer modern run_action() contract when available; otherwise fall back to run_import(params,...)
        try:
            if hasattr(plugin, "run_action") and callable(getattr(plugin, "run_action")):
                result = plugin.run_action(capability_name, parameters, self)
            else:
                action_method_name = "run_import"
                if not hasattr(plugin, action_method_name) or not callable(getattr(plugin, action_method_name)):
                    msg = (
                        f"Plugin '{plugin_name}' does not expose project-level action methods for '{capability_name}'."
                    )
                    self.log_bus.log(f"Action failed: {msg}", "error", "ProjectManager")
                    logger.error(msg)
                    return {"status": "failed", "error": msg}
                result = getattr(plugin, action_method_name)(params=parameters, project_manager=self)
            if not isinstance(result, dict):
                raise RuntimeError("Plugin action method returned invalid result format (expected dict).")
            if result.get("status") == "success":
                self.log_bus.log(
                    f"Project-level action '{capability_name}' completed successfully.",
                    "success",
                    "ProjectManager",
                )
                logger.info(f"Project-level action '{capability_name}' completed successfully.")
            else:
                err_msg = result.get("error", "Unknown error during plugin action.")
                self.log_bus.log(f"Project-level action failed: {err_msg}", "error", "ProjectManager")
                logger.error(f"Project-level action '{capability_name}' failed: {err_msg}")
            return result
        except Exception as e:
            msg = f"Error executing action '{action_method_name}' on plugin '{plugin_name}': {e}"
            self.log_bus.log(f"Action failed: {msg}", "error", "ProjectManager")
            logger.error(msg, exc_info=True)
            return {"status": "failed", "error": msg}

    # ------------------------------------------------------------------
    # Maintenance: Fix master filenames to true recording times
    # ------------------------------------------------------------------
    def fix_master_recording_times(
        self,
        *,
        project_path: Path,
        dest_subdir: str = "recordings/master",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Rename files under the master library to reflect true recording time and update project state.

        - Computes true recording time via DataManager._extract_start_time (ffprobe-based) per file
        - Ensures filename contains the correct YYYYMMDD_HHMM token before the hash8
        - Preserves trailing hash8; replaces/sets it to sample-hash if mismatched/missing
        - Updates VideoMetadata.date and path in project state for both unassigned and experiment videos
        - For experiments with exactly one linked video, updates ExperimentMetadata.date_recorded to the true time
        """
        import re
        from datetime import datetime as _dt

        self.load_project(project_path)
        sr = self.state_manager.project_state.shared_root or self.get_shared_directory()
        shared_root = Path(sr).expanduser().resolve()
        master_dir = (shared_root / dest_subdir).expanduser().resolve()
        if not master_dir.exists():
            return {"status": "failed", "error": f"Master directory not found: {master_dir}"}

        exts = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}
        files: list[Path] = []
        for p in master_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)

        dm = self.data_manager
        ps = self.state_manager.project_state

        # Build reverse index by hash for quick lookup
        hash_to_vm: dict[str, Any] = {}
        for d in (ps.unassigned_videos, ps.experiment_videos):
            for h, vm in d.items():
                if h:
                    hash_to_vm[h] = vm

        def _target_name(src: Path, true_dt: _dt, hash8: str) -> str:
            base = src.stem
            ext = src.suffix
            # Replace the last date token 20YYYYMMDD(_HHMM)? with true token; else insert before hash8 or at end
            ts_token = true_dt.strftime("%Y%m%d_%H%M")
            # Ensure trailing _hash8 exists and matches
            m_hash = re.search(r"([0-9a-f]{8})$", base)
            if m_hash:
                base_wo_hash = base[: m_hash.start()].rstrip("_")
                current_h8 = m_hash.group(1)
            else:
                base_wo_hash = base
                current_h8 = None

            # Replace or insert date token
            # Find last date-like token
            m_dt_iter = list(re.finditer(r"20\d{6}(?:_\d{4})?", base_wo_hash))
            if m_dt_iter:
                last = m_dt_iter[-1]
                new_base = base_wo_hash[: last.start()] + ts_token + base_wo_hash[last.end():]
                new_base = re.sub(r"__+", "_", new_base.strip("_"))
            else:
                # Insert before trailing hash or at end
                new_base = base_wo_hash
                if new_base and not new_base.endswith("_"):
                    new_base += "_"
                new_base += ts_token

            # Ensure hash8 at end
            final_h8 = hash8.lower()
            if current_h8 and current_h8.lower() == final_h8:
                new_name = f"{new_base}_{current_h8}{ext}"
            else:
                new_name = f"{new_base}_{final_h8}{ext}"
            return new_name

        renamed = 0
        updated_vm = 0
        updated_exp = 0

        for src in files:
            try:
                h = dm.compute_sample_hash(src)
                h8 = h[:8]
                true_dt = dm._extract_start_time(src)
                # Compute target name
                target = src.with_name(_target_name(src, true_dt, h8))
                if target != src:
                    if not dry_run:
                        # Disambiguate if exists with different content
                        candidate = target
                        n = 1
                        while candidate.exists() and candidate != src:
                            # If candidate matches same hash, reuse
                            try:
                                if dm.compute_sample_hash(candidate) == h:
                                    break
                            except Exception:
                                pass
                            candidate = target.with_stem(f"{target.stem}_{n}")
                            n += 1
                        if candidate != src and candidate != target and candidate.suffix != target.suffix:
                            candidate = target  # Fallback
                        if candidate != src:
                            src.rename(candidate)
                            dst = candidate
                        else:
                            dst = src
                    else:
                        dst = target
                    renamed += 1
                else:
                    dst = src

                # Update VM in state
                vm = hash_to_vm.get(h)
                if vm is not None:
                    try:
                        if getattr(vm, "path", None) != dst:
                            vm.path = Path(dst).resolve()
                            updated_vm += 1
                        # Always set true recording time
                        vm.date = true_dt
                        # Update experiments with exactly one video
                        if getattr(vm, "experiment_ids", None):
                            exp_ids = list(vm.experiment_ids)
                            if len(exp_ids) == 1:
                                exp_id = exp_ids[0]
                                if exp_id in ps.experiments:
                                    ps.experiments[exp_id].date_recorded = true_dt
                                    updated_exp += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Skipping file during fix_master_recording_times: {src} ({e})")
                continue

        if not dry_run:
            self.save_project()
            self.state_manager.notify_observers()

        return {
            "status": "success",
            "scanned": len(files),
            "renamed": renamed,
            "updated_recordings": updated_vm,
            "updated_experiments": updated_exp,
            "master_dir": str(master_dir),
            "dry_run": dry_run,
        }

    