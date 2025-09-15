"""
Clean Project Manager using the new architecture.

This replaces the complex ProjectManager with a simple, focused implementation.
"""

from pathlib import Path
from typing import Optional, List
import json
import logging

from .metadata import ProjectConfig, Subject, Experiment, VideoFile, Colony
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
            with open(self.config_path) as f:
                data = json.load(f)
            return ProjectConfig(
                name=data["name"],
                shared_root=Path(data["shared_root"]) if data.get("shared_root") else None,
                lab_id=data.get("lab_id")
            )
        else:
            # Create default config
            config = ProjectConfig(name=self.project_path.name)
            self._save_config(config)
            return config

    def _save_config(self, config: ProjectConfig):
        """Save project config to disk."""
        data = {
            "name": config.name,
            "shared_root": str(config.shared_root) if config.shared_root else None,
            "lab_id": config.lab_id,
            "date_created": config.date_created.isoformat()
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
        # Get sort mode from project config, default to date_added desc
        sort_mode = self.config.settings.get("global_sort_mode", "date_added")
        sort_order = "desc"  # Default to descending for most sorts

        # For subjects, we need to map the sort mode to appropriate field
        if sort_mode == "Natural Order (Numbers as Numbers)":
            sort_by = "id"  # Sort by ID which handles numbers naturally
        elif sort_mode == "Lexicographical Order (Numbers as Characters)":
            sort_by = "id"  # Same field, but could be handled differently in repo
        elif sort_mode == "Date Added":
            sort_by = "date_added"
        elif sort_mode == "By ID":
            sort_by = "id"
        else:
            sort_by = "date_added"

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
        # Get sort mode from project config, default to date_recorded desc
        sort_mode = self.config.settings.get("global_sort_mode", "date_added")
        sort_order = "desc"  # Default to descending for most sorts

        # For experiments, we need to map the sort mode to appropriate field
        if sort_mode == "Natural Order (Numbers as Numbers)":
            sort_by = "date_recorded"  # Sort by date recorded for experiments
        elif sort_mode == "Lexicographical Order (Numbers as Characters)":
            sort_by = "experiment_type"  # Sort by experiment type
        elif sort_mode == "Date Added":
            sort_by = "date_added"
        elif sort_mode == "By ID":
            sort_by = "date_recorded"  # Use date recorded as primary sort
        else:
            sort_by = "date_recorded"

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
