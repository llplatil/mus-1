"""
Clean Project Manager using the new architecture.

This replaces the complex ProjectManager with a simple, focused implementation.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import logging
from datetime import datetime

from .metadata import ProjectConfig, Subject, Experiment, VideoFile, Colony, Worker, ScanTarget
from .repository import RepositoryFactory
from .schema import Database

logger = logging.getLogger(__name__)

class ProjectManagerClean:
    """Clean project manager with focused responsibilities."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.config_path = project_path / "project.json"
        self.db_path = project_path / "mus1.db"

        # Initialize database
        self.db = Database(str(self.db_path))
        self.db.create_tables()

        # Initialize repositories
        self.repos = RepositoryFactory(self.db)

        # Load or create project config
        self.config = self._load_or_create_config()

    def _load_or_create_config(self) -> ProjectConfig:
        """Load existing config or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                config = ProjectConfig(
                    name=data["name"],
                    shared_root=Path(data["shared_root"]) if data.get("shared_root") else None,
                    lab_id=data.get("lab_id")
                )
                # Load settings if they exist
                if "settings" in data:
                    try:
                        config.settings.update(self._deserialize_settings_from_json(data["settings"]))
                    except Exception as e:
                        logger.warning(f"Failed to deserialize settings from {self.config_path}, using defaults: {e}")
                        # Continue with empty settings - they'll be saved with proper serialization later
                return config
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {self.config_path}: {e}")
                # Create a backup and start fresh
                backup_path = self.config_path.with_suffix('.json.backup')
                try:
                    import shutil
                    shutil.copy2(self.config_path, backup_path)
                    logger.info(f"Backed up corrupted config to {backup_path}")
                except Exception:
                    pass  # Continue even if backup fails

                # Create default config
                config = ProjectConfig(name=self.project_path.name)
                self._save_config(config)
                logger.info("Created new config due to JSON corruption")
                return config
            except Exception as e:
                logger.error(f"Error loading config from {self.config_path}: {e}")
                # Create default config as fallback
                config = ProjectConfig(name=self.project_path.name)
                self._save_config(config)
                return config
        else:
            # Create default config
            config = ProjectConfig(name=self.project_path.name)
            self._save_config(config)
            return config

    def _serialize_settings_for_json(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively serialize settings for JSON storage, handling Path objects and other non-serializable types."""
        def serialize_value(value):
            if isinstance(value, Path):
                return {"__path__": str(value)}
            elif isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [serialize_value(item) for item in value]
            else:
                return value

        return serialize_value(settings)

    def _deserialize_settings_from_json(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively deserialize settings from JSON storage, restoring Path objects."""
        def deserialize_value(value):
            if isinstance(value, dict):
                # Handle new serialized Path objects
                if "__path__" in value and len(value) == 1:
                    return Path(value["__path__"])
                else:
                    return {k: deserialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [deserialize_value(item) for item in value]
            else:
                return value

        return deserialize_value(settings)

    def _save_config(self, config: ProjectConfig):
        """Save project config to disk."""
        data = {
            "name": config.name,
            "shared_root": str(config.shared_root) if config.shared_root else None,
            "lab_id": config.lab_id,
            "date_created": config.date_created.isoformat(),
            "settings": self._serialize_settings_for_json(config.settings)
        }
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)

    # ===========================================
    # SUBJECT OPERATIONS
    # ===========================================

    def add_subject(self, subject: Subject) -> Subject:
        """Add a subject to the project."""
        # Validate that the subject's colony exists
        colony = self.get_colony(subject.colony_id)
        if not colony:
            raise ValueError(f"Colony {subject.colony_id} does not exist")

        logger.info(f"Adding subject {subject.id} to project {self.config.name}")
        saved_subject = self.repos.subjects.save(subject)
        logger.info(f"Subject {subject.id} added successfully")
        return saved_subject

    def get_subject(self, subject_id: str) -> Optional[Subject]:
        """Get subject by ID."""
        return self.repos.subjects.find_by_id(subject_id)

    def list_subjects(self) -> List[Subject]:
        """List all subjects with sorting from project config."""
        # Get sort mode from project config, default to "Newest First"
        sort_mode = self.config.settings.get("global_sort_mode", "Newest First")

        # Map UI sort modes to repository sort fields and orders
        if sort_mode == "Newest First":
            sort_by = "date_added"
            sort_order = "desc"
        elif sort_mode == "Recording Date":
            # For subjects, recording date doesn't make sense, fall back to date_added
            sort_by = "date_added"
            sort_order = "desc"
        elif sort_mode == "ID Order":
            sort_by = "id"  # Natural sort for IDs (handles numbers well)
            sort_order = "asc"
        elif sort_mode == "By Type":
            # For subjects, sort by designation (type/category)
            sort_by = "designation"
            sort_order = "asc"
        else:
            # Default fallback
            sort_by = "date_added"
            sort_order = "desc"

        return self.repos.subjects.find_all(sort_by=sort_by, sort_order=sort_order)

    def remove_subject(self, subject_id: str) -> bool:
        """Remove subject from project."""
        logger.info(f"Removing subject {subject_id} from project {self.config.name}")

        # Check if subject has experiments
        experiments = self.repos.experiments.find_by_subject(subject_id)
        if experiments:
            logger.warning(f"Subject {subject_id} has {len(experiments)} experiments, cannot remove")
            return False

        success = self.repos.subjects.delete(subject_id)
        if success:
            logger.info(f"Subject {subject_id} removed successfully")
        return success

    # ===========================================
    # EXPERIMENT OPERATIONS
    # ===========================================

    def add_experiment(self, experiment: Experiment) -> Experiment:
        """Add an experiment to the project."""
        # Validate subject exists
        subject = self.get_subject(experiment.subject_id)
        if not subject:
            raise ValueError(f"Subject {experiment.subject_id} does not exist")

        logger.info(f"Adding experiment {experiment.id} for subject {experiment.subject_id}")
        saved_experiment = self.repos.experiments.save(experiment)
        logger.info(f"Experiment {experiment.id} added successfully")
        return saved_experiment

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get experiment by ID."""
        return self.repos.experiments.find_by_id(experiment_id)

    def list_experiments(self) -> List[Experiment]:
        """List all experiments with sorting from project config."""
        # Get sort mode from project config, default to "Recording Date"
        sort_mode = self.config.settings.get("global_sort_mode", "Recording Date")

        # Map UI sort modes to repository sort fields and orders
        if sort_mode == "Newest First":
            # For experiments, "Newest First" means most recently added to system
            sort_by = "date_added"
            sort_order = "desc"
        elif sort_mode == "Recording Date":
            sort_by = "date_recorded"  # Primary sort for experiments - chronological
            sort_order = "desc"  # Most recent recordings first
        elif sort_mode == "ID Order":
            # For experiments, sort by date_recorded since ID contains subject info
            sort_by = "date_recorded"
            sort_order = "desc"
        elif sort_mode == "By Type":
            # For experiments, sort by experiment type
            sort_by = "experiment_type"
            sort_order = "asc"
        else:
            # Default fallback
            sort_by = "date_recorded"
            sort_order = "desc"

        return self.repos.experiments.find_all(sort_by=sort_by, sort_order=sort_order)

    def list_experiments_for_subject(self, subject_id: str) -> List[Experiment]:
        """List experiments for a specific subject."""
        return self.repos.experiments.find_by_subject(subject_id)

    def remove_experiment(self, experiment_id: str) -> bool:
        """Remove experiment from project."""
        logger.info(f"Removing experiment {experiment_id} from project {self.config.name}")
        success = self.repos.experiments.delete(experiment_id)
        if success:
            logger.info(f"Experiment {experiment_id} removed successfully")
        return success

    # ===========================================
    # VIDEO OPERATIONS
    # ===========================================

    def add_video(self, video: VideoFile) -> VideoFile:
        """Add a video file to the project."""
        # Check for duplicates
        existing = self.repos.videos.find_by_hash(video.hash)
        if existing:
            logger.warning(f"Video with hash {video.hash} already exists: {existing.path}")
            return existing

        logger.info(f"Adding video {video.path} to project {self.config.name}")
        saved_video = self.repos.videos.save(video)
        logger.info(f"Video {video.path} added successfully")
        return saved_video

    def get_video_by_hash(self, hash_value: str) -> Optional[VideoFile]:
        """Get video by hash."""
        return self.repos.videos.find_by_hash(hash_value)

    def find_duplicate_videos(self) -> List[dict]:
        """Find videos with duplicate hashes."""
        return self.repos.videos.find_duplicates()

    def link_video_to_experiment(self, experiment_id: str, video_path: Path, notes: str = "") -> bool:
        """Link a video file to an experiment.

        Args:
            experiment_id: The experiment to link the video to
            video_path: Path to the video file
            notes: Optional notes about the linking

        Returns:
            True if linking was successful, False otherwise
        """
        try:
            # Validate experiment exists
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                logger.error(f"Experiment {experiment_id} does not exist")
                return False

            # Check if video file exists
            if not video_path.exists():
                logger.error(f"Video file does not exist: {video_path}")
                return False

            # Compute hash for the video file
            from .utils.file_hash import compute_sample_hash
            try:
                video_hash = compute_sample_hash(video_path)
            except Exception as e:
                logger.error(f"Failed to compute hash for video {video_path}: {e}")
                return False

            # Check if video already exists by hash first
            existing_video = self.repos.videos.find_by_hash(video_hash)
            if existing_video:
                logger.info(f"Video {video_path} already exists in project (hash: {video_hash})")
                # Check if already associated with this experiment
                if self._is_video_associated_with_experiment(experiment_id, existing_video):
                    logger.info(f"Video {video_path} already associated with experiment {experiment_id}")
                else:
                    # Associate existing video with experiment
                    self._associate_video_with_experiment(experiment_id, existing_video)
                    logger.info(f"Associated existing video {video_path} with experiment {experiment_id}")
                return True

            # Check if video exists by path (might have been saved with empty hash previously)
            existing_video_by_path = self.repos.videos.find_by_path(video_path)
            if existing_video_by_path:
                logger.info(f"Video {video_path} exists in project but with different hash (old: {existing_video_by_path.hash}, new: {video_hash})")
                # Update the existing video record with correct hash and metadata
                try:
                    stat = video_path.stat()
                    updated_video = VideoFile(
                        path=video_path,
                        hash=video_hash,
                        size_bytes=stat.st_size,
                        last_modified=stat.st_mtime
                    )
                    # Update the video in database
                    self.repos.videos.save(updated_video)  # This will update due to merge behavior
                    logger.info(f"Updated video metadata for {video_path}")

                    # Check if already associated with this experiment
                    if self._is_video_associated_with_experiment(experiment_id, updated_video):
                        logger.info(f"Video {video_path} already associated with experiment {experiment_id}")
                    else:
                        # Associate video with experiment
                        self._associate_video_with_experiment(experiment_id, updated_video)
                        logger.info(f"Associated updated video {video_path} with experiment {experiment_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to update existing video {video_path}: {e}")
                    return False

            # Get file metadata
            try:
                stat = video_path.stat()
                video_file = VideoFile(
                    path=video_path,
                    hash=video_hash,
                    size_bytes=stat.st_size,
                    last_modified=stat.st_mtime
                )
            except Exception as e:
                logger.error(f"Failed to get file metadata for {video_path}: {e}")
                return False

            # Save the video record
            try:
                saved_video = self.repos.videos.save(video_file)
                logger.info(f"Video {video_path} saved, now linking to experiment {experiment_id}")

                # Create experiment-video association
                self._associate_video_with_experiment(experiment_id, saved_video)
                logger.info(f"Video {video_path} linked to experiment {experiment_id}: {notes}")
                return True
            except Exception as e:
                logger.error(f"Failed to save video record for {video_path}: {e}")
                return False

        except Exception as e:
            logger.error(f"Error linking video to experiment: {e}")
            return False

    def _associate_video_with_experiment(self, experiment_id: str, video: VideoFile) -> None:
        """Create an association between an experiment and a video."""
        from sqlalchemy import text
        with self.db.get_session() as session:
            # Get the video ID by querying with the path
            result = session.execute(
                text("SELECT id FROM videos WHERE path = :path"),
                {"path": str(video.path)}
            ).fetchone()

            if result:
                video_id = result[0]
                # Insert into association table
                session.execute(
                    text("""
                        INSERT OR IGNORE INTO experiment_videos (experiment_id, video_id)
                        VALUES (:experiment_id, :video_id)
                    """),
                    {"experiment_id": experiment_id, "video_id": video_id}
                )
                session.commit()
            else:
                logger.error(f"Could not find video ID for path: {video.path}")

    def _is_video_associated_with_experiment(self, experiment_id: str, video: VideoFile) -> bool:
        """Check if a video is already associated with an experiment."""
        from sqlalchemy import text
        with self.db.get_session() as session:
            # Get the video ID first
            result = session.execute(
                text("SELECT id FROM videos WHERE path = :path"),
                {"path": str(video.path)}
            ).fetchone()

            if not result:
                return False

            video_id = result[0]
            association = session.execute(
                text("""
                    SELECT 1 FROM experiment_videos
                    WHERE experiment_id = :experiment_id AND video_id = :video_id
                    LIMIT 1
                """),
                {"experiment_id": experiment_id, "video_id": video_id}
            ).fetchone()
            return association is not None

    # ===========================================
    # WORKER OPERATIONS
    # ===========================================

    def add_worker(self, worker: 'Worker') -> 'Worker':
        """Add a worker to the project."""
        logger.info(f"Adding worker {worker.name} to project {self.config.name}")
        saved_worker = self.repos.workers.save(worker)
        logger.info(f"Worker {worker.name} added successfully")
        return saved_worker

    def get_worker(self, name: str) -> Optional['Worker']:
        """Get worker by name."""
        return self.repos.workers.find_by_name(name)

    def list_workers(self) -> List['Worker']:
        """List all workers."""
        return self.repos.workers.find_all()

    # ===========================================
    # SCAN TARGET OPERATIONS
    # ===========================================

    def add_scan_target(self, target: 'ScanTarget') -> 'ScanTarget':
        """Add a scan target to the project."""
        logger.info(f"Adding scan target {target.name} to project {self.config.name}")
        saved_target = self.repos.scan_targets.save(target)
        logger.info(f"Scan target {target.name} added successfully")
        return saved_target

    def get_scan_target(self, name: str) -> Optional['ScanTarget']:
        """Get scan target by name."""
        return self.repos.scan_targets.find_by_name(name)

    def list_scan_targets(self) -> List['ScanTarget']:
        """List all scan targets."""
        return self.repos.scan_targets.find_all()

    # ===========================================
    # PROJECT CONFIGURATION
    # ===========================================

    def set_shared_root(self, shared_root: Path):
        """Set the shared storage root."""
        if not shared_root.exists():
            raise ValueError(f"Shared root {shared_root} does not exist")

        logger.info(f"Setting shared root to {shared_root} for project {self.config.name}")
        self.config.shared_root = shared_root
        self._save_config(self.config)

    def set_lab_id(self, lab_id: str):
        """Associate project with a lab."""
        logger.info(f"Associating project {self.config.name} with lab {lab_id}")
        self.config.lab_id = lab_id
        self._save_config(self.config)

    # ===========================================
    # COLONY OPERATIONS
    # ===========================================

    def add_colony(self, colony: Colony) -> Colony:
        """Add a colony to the project."""
        # Validate that colony belongs to the same lab as the project
        if self.config.lab_id and colony.lab_id != self.config.lab_id:
            raise ValueError(f"Colony {colony.id} belongs to lab {colony.lab_id}, but project is associated with lab {self.config.lab_id}")

        logger.info(f"Adding colony {colony.id} to project {self.config.name}")
        saved_colony = self.repos.colonies.save(colony)
        logger.info(f"Colony {colony.id} added successfully")
        return saved_colony

    def get_colony(self, colony_id: str) -> Optional[Colony]:
        """Get colony by ID."""
        return self.repos.colonies.find_by_id(colony_id)

    def list_colonies(self) -> List[Colony]:
        """List all colonies in the project."""
        if self.config.lab_id:
            # If project has a lab_id, only show colonies from that lab
            return self.repos.colonies.find_by_lab(self.config.lab_id)
        else:
            # If no lab_id, show all colonies (for backward compatibility)
            return self.repos.colonies.find_all()

    def list_subjects_from_colony(self, colony_id: str) -> List[Subject]:
        """List all subjects from a specific colony."""
        return self.repos.subjects.find_by_colony(colony_id)

    def import_subjects_from_colony(self, colony_id: str, subject_ids: Optional[List[str]] = None) -> List[Subject]:
        """Import subjects from a colony into the project.

        Args:
            colony_id: The colony to import subjects from
            subject_ids: Specific subject IDs to import (None = import all)

        Returns:
            List of imported subjects
        """
        # Validate that colony exists and belongs to the project's lab
        colony = self.get_colony(colony_id)
        if not colony:
            raise ValueError(f"Colony {colony_id} does not exist")

        if self.config.lab_id and colony.lab_id != self.config.lab_id:
            raise ValueError(f"Colony {colony_id} belongs to lab {colony.lab_id}, but project is associated with lab {self.config.lab_id}")

        # Get subjects from colony
        colony_subjects = self.list_subjects_from_colony(colony_id)

        # Filter by specific IDs if provided
        if subject_ids:
            subject_id_set = set(subject_ids)
            colony_subjects = [s for s in colony_subjects if s.id in subject_id_set]

        # Import subjects that don't already exist in the project
        imported_subjects = []
        for subject in colony_subjects:
            if not self.get_subject(subject.id):
                # Subject doesn't exist in project, add it
                imported_subject = self.add_subject(subject)
                imported_subjects.append(imported_subject)
            else:
                # Subject already exists, just add to imported list for return
                imported_subjects.append(subject)

        logger.info(f"Imported {len(imported_subjects)} subjects from colony {colony_id} into project {self.config.name}")
        return imported_subjects

    def remove_colony(self, colony_id: str) -> bool:
        """Remove colony from project."""
        logger.info(f"Removing colony {colony_id} from project {self.config.name}")

        # Check if colony has subjects in this project
        subjects = self.list_subjects_from_colony(colony_id)
        if subjects:
            logger.warning(f"Colony {colony_id} has {len(subjects)} subjects, cannot remove")
            return False

        success = self.repos.colonies.delete(colony_id)
        if success:
            logger.info(f"Colony {colony_id} removed successfully")
        return success

    # ===========================================
    # UTILITY METHODS
    # ===========================================

    def get_stats(self) -> dict:
        """Get project statistics."""
        return {
            "name": self.config.name,
            "colonies": len(self.list_colonies()),
            "subjects": len(self.list_subjects()),
            "experiments": len(self.list_experiments()),
            "videos": len(self.find_duplicate_videos()),  # This is approximate
            "workers": len(self.list_workers()),
            "scan_targets": len(self.list_scan_targets()),
            "shared_root": str(self.config.shared_root) if self.config.shared_root else None,
            "lab_id": self.config.lab_id
        }

    def list_videos(self) -> List[VideoFile]:
        """List all videos in the project."""
        return self.repos.videos.find_all()

    def get_videos_for_experiment(self, experiment_id: str) -> List[VideoFile]:
        """Get all videos associated with a specific experiment."""
        from sqlalchemy import text
        with self.db.get_session() as session:
            # Query videos through the association table
            results = session.execute(
                text("""
                    SELECT v.path, v.hash, v.recorded_time, v.size_bytes, v.last_modified, v.date_added
                    FROM videos v
                    JOIN experiment_videos ev ON v.id = ev.video_id
                    WHERE ev.experiment_id = :experiment_id
                """),
                {"experiment_id": experiment_id}
            ).fetchall()

            videos = []
            for row in results:
                videos.append(VideoFile(
                    path=Path(row[0]),
                    hash=row[1],
                    recorded_time=row[2],
                    size_bytes=row[3],
                    last_modified=row[4],
                    date_added=row[5]
                ))
            return videos

    def create_batch(self, batch_id: str, experiment_ids: List[str], batch_name: str = None, description: str = None, selection_criteria: Dict[str, Any] = None) -> str:
        """Create a new batch of experiments.

        Args:
            batch_id: Unique identifier for the batch
            experiment_ids: List of experiment IDs to include in the batch
            batch_name: Optional human-readable name for the batch
            description: Optional description of the batch
            selection_criteria: Optional criteria used to select experiments

        Returns:
            The batch ID that was created

        Raises:
            ValueError: If batch_id already exists or if any experiment_ids are invalid
        """
        # Validate batch_id doesn't already exist
        # For now, we'll store batches in project settings since there's no dedicated batch table
        batches = self.config.settings.get('batches', {})
        if batch_id in batches:
            raise ValueError(f"Batch '{batch_id}' already exists")

        # Validate all experiment IDs exist
        for exp_id in experiment_ids:
            if not self.get_experiment(exp_id):
                raise ValueError(f"Experiment '{exp_id}' does not exist")

        # Create batch record
        batch_record = {
            'id': batch_id,
            'name': batch_name,
            'description': description,
            'experiment_ids': experiment_ids,
            'selection_criteria': selection_criteria or {},
            'created_at': datetime.now().isoformat(),
            'status': 'created'
        }

        # Store in project settings
        if 'batches' not in self.config.settings:
            self.config.settings['batches'] = {}
        self.config.settings['batches'][batch_id] = batch_record
        self._save_config(self.config)

        logger.info(f"Created batch '{batch_id}' with {len(experiment_ids)} experiments")
        return batch_id

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get batch information by ID."""
        batches = self.config.settings.get('batches', {})
        return batches.get(batch_id)

    def list_batches(self) -> List[Dict[str, Any]]:
        """List all batches in the project."""
        batches = self.config.settings.get('batches', {})
        return list(batches.values())

    def save_project(self):
        """Save project configuration and state."""
        try:
            self._save_config(self.config)
            logger.info(f"Project {self.config.name} saved successfully")
        except Exception as e:
            logger.error(f"Failed to save project {self.config.name}: {e}")
            raise

    def rename_project(self, new_name: str) -> bool:
        """Rename the project."""
        try:
            if not new_name or len(new_name.strip()) < 3:
                raise ValueError("Project name must be at least 3 characters")

            old_name = self.config.name
            self.config.name = new_name.strip()

            # Rename the project directory
            parent_dir = self.project_path.parent
            new_path = parent_dir / new_name

            if new_path.exists():
                raise ValueError(f"Directory {new_path} already exists")

            import shutil
            shutil.move(str(self.project_path), str(new_path))

            # Update our internal path
            self.project_path = new_path
            self.config_path = new_path / "project.json"
            self.db_path = new_path / "mus1.db"

            # Save the updated config
            self.save_project()

            logger.info(f"Project renamed from '{old_name}' to '{new_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to rename project: {e}")
            raise

    def move_project_to_directory(self, destination: Path) -> Path:
        """Move project to a new directory."""
        try:
            if not destination.exists():
                destination.mkdir(parents=True, exist_ok=True)

            new_project_path = destination / self.config.name

            if new_project_path.exists():
                raise ValueError(f"Project directory {new_project_path} already exists")

            import shutil
            shutil.move(str(self.project_path), str(new_project_path))

            # Update our internal path
            self.project_path = new_project_path
            self.config_path = new_project_path / "project.json"
            self.db_path = new_project_path / "mus1.db"

            # Save the updated config
            self.save_project()

            logger.info(f"Project moved to {new_project_path}")
            return new_project_path

        except Exception as e:
            logger.error(f"Failed to move project: {e}")
            raise

    def register_unlinked_videos(self, videos_iter) -> int:
        """Register videos that are not yet linked to experiments."""
        try:
            count = 0
            for video in videos_iter:
                # Assuming video is a tuple (path, hash, timestamp)
                if len(video) >= 2:
                    path, hash_value = video[0], video[1]
                    # Create VideoFile entity and save it
                    video_file = VideoFile(path=Path(path), hash=hash_value)
                    self.repos.videos.save(video_file)
                    count += 1

            logger.info(f"Registered {count} unlinked videos")
            return count

        except Exception as e:
            logger.error(f"Failed to register unlinked videos: {e}")
            return 0

    def cleanup(self):
        """Clean up resources."""
        # Close database connections
        pass

    # --- Treatment and Genotype Management ---

    def add_treatment(self, name: str) -> None:
        """Add a treatment to the project's available treatments."""
        if not name or not name.strip():
            raise ValueError("Treatment name cannot be empty")

        name = name.strip()
        treatments = self.config.settings.get('available_treatments', [])
        if name not in treatments:
            treatments.append(name)
            self.config.settings['available_treatments'] = treatments
            self._save_config(self.config)
            logger.info(f"Added treatment '{name}' to project {self.config.name}")

    def add_genotype(self, name: str) -> None:
        """Add a genotype to the project's available genotypes."""
        if not name or not name.strip():
            raise ValueError("Genotype name cannot be empty")

        name = name.strip()
        genotypes = self.config.settings.get('available_genotypes', [])
        if name not in genotypes:
            genotypes.append(name)
            self.config.settings['available_genotypes'] = genotypes
            self._save_config(self.config)
            logger.info(f"Added genotype '{name}' to project {self.config.name}")

    def get_available_treatments(self) -> List[str]:
        """Get all available treatments for this project."""
        return self.config.settings.get('available_treatments', [])

    def get_available_genotypes(self) -> List[str]:
        """Get all available genotypes for this project."""
        return self.config.settings.get('available_genotypes', [])

    def remove_treatment(self, name: str) -> bool:
        """Remove a treatment from available treatments."""
        treatments = self.config.settings.get('available_treatments', [])
        if name in treatments:
            treatments.remove(name)
            self.config.settings['available_treatments'] = treatments
            self._save_config(self.config)
            logger.info(f"Removed treatment '{name}' from project {self.config.name}")
            return True
        return False

    def remove_genotype(self, name: str) -> bool:
        """Remove a genotype from available genotypes."""
        genotypes = self.config.settings.get('available_genotypes', [])
        if name in genotypes:
            genotypes.remove(name)
            self.config.settings['available_genotypes'] = genotypes
            self._save_config(self.config)
            logger.info(f"Removed genotype '{name}' from project {self.config.name}")
            return True
        return False

    # --- Body Parts and Objects Management (placeholders) ---

    def update_active_body_parts(self, active_list: List[str]) -> None:
        """Update active body parts in the project."""
        self.config.settings['active_body_parts'] = active_list
        self._save_config(self.config)
        logger.info(f"Updated active body parts: {active_list}")

    def update_master_body_parts(self, master_list: List[str]) -> None:
        """Update master body parts in the project."""
        self.config.settings['master_body_parts'] = master_list
        self._save_config(self.config)
        logger.info(f"Updated master body parts: {master_list}")

    def get_active_body_parts(self) -> List[str]:
        """Get active body parts for this project."""
        return self.config.settings.get('active_body_parts', [])

    def get_master_body_parts(self) -> List[str]:
        """Get master body parts for this project."""
        return self.config.settings.get('master_body_parts', [])

    def update_tracked_objects(self, items: List[str], list_type: str) -> None:
        """Update tracked objects in the project."""
        self.config.settings[f'{list_type}_tracked_objects'] = items
        self._save_config(self.config)
        logger.info(f"Updated {list_type} tracked objects: {items}")

    def get_tracked_objects(self, list_type: str = "active") -> List[str]:
        """Get tracked objects for this project.

        Args:
            list_type: Either "active" or "master" to get respective lists

        Returns:
            List of tracked object names
        """
        key = f"{list_type}_tracked_objects"
        return self.config.settings.get(key, [])

    def get_master_tracked_objects(self) -> List[str]:
        """Get master tracked objects for this project."""
        return self.get_tracked_objects("master")

    def get_active_tracked_objects(self) -> List[str]:
        """Get active tracked objects for this project."""
        return self.get_tracked_objects("active")

    def add_tracked_object(self, name: str) -> None:
        """Add a tracked object to the project."""
        if not name or not name.strip():
            raise ValueError("Tracked object name cannot be empty")

        name = name.strip()
        objects = self.config.settings.get('tracked_objects', [])
        if name not in objects:
            objects.append(name)
            self.config.settings['tracked_objects'] = objects
            self._save_config(self.config)
            logger.info(f"Added tracked object '{name}' to project {self.config.name}")
