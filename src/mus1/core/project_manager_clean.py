"""
Clean Project Manager using the new architecture.

This replaces the complex ProjectManager with a simple, focused implementation.
"""

from pathlib import Path
from typing import Optional, List
import json
import logging

from .metadata import ProjectConfig, Subject, Experiment, VideoFile
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
        logger.info(f"Adding subject {subject.id} to project {self.config.name}")
        saved_subject = self.repos.subjects.save(subject)
        logger.info(f"Subject {subject.id} added successfully")
        return saved_subject

    def get_subject(self, subject_id: str) -> Optional[Subject]:
        """Get subject by ID."""
        return self.repos.subjects.find_by_id(subject_id)

    def list_subjects(self) -> List[Subject]:
        """List all subjects."""
        return self.repos.subjects.find_all()

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
        """List all experiments."""
        return self.repos.experiments.find_all()

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
    # UTILITY METHODS
    # ===========================================

    def get_stats(self) -> dict:
        """Get project statistics."""
        return {
            "name": self.config.name,
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

    def cleanup(self):
        """Clean up resources."""
        # Close database connections
        pass
