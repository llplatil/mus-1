"""
GUI Services Layer

This module provides services that bridge the GUI layer with the clean architecture.
These services handle the conversion between domain models and GUI-friendly DTOs,
and provide a clean interface for GUI components to interact with the business logic.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from ..core.metadata import Subject, Experiment, VideoFile, Sex, ProcessingStage
from ..core.project_manager_clean import ProjectManagerClean
from ..core.repository import RepositoryFactory
from ..core.logging_bus import LoggingEventBus


class SubjectDisplayDTO:
    """DTO for displaying subject information in GUI."""
    def __init__(self, subject: Subject):
        self.id = subject.id
        self.sex = subject.sex.value if subject.sex else ""
        self.genotype = subject.genotype or ""
        self.birth_date = subject.birth_date
        self.age_days = subject.age_days
        self.date_added = subject.date_added

    @property
    def sex_display(self) -> str:
        """Human-readable sex display."""
        return self.sex if self.sex else "Unknown"

    @property
    def age_display(self) -> str:
        """Human-readable age display."""
        if self.age_days is None:
            return "Unknown"
        elif self.age_days < 30:
            return f"{self.age_days} days"
        elif self.age_days < 365:
            months = self.age_days // 30
            return f"{months} months"
        else:
            years = self.age_days // 365
            return f"{years} years"


class ExperimentDisplayDTO:
    """DTO for displaying experiment information in GUI."""
    def __init__(self, experiment: Experiment):
        self.id = experiment.id
        self.subject_id = experiment.subject_id
        self.experiment_type = experiment.experiment_type
        self.date_recorded = experiment.date_recorded
        self.processing_stage = experiment.processing_stage.value if experiment.processing_stage else ""
        self.date_added = experiment.date_added


class GUISubjectService:
    """Service for GUI subject operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        self.project_manager = project_manager
        self.log_bus = LoggingEventBus.get_instance()

    def get_subjects_for_display(self) -> List[SubjectDisplayDTO]:
        """Get all subjects formatted for GUI display."""
        try:
            subjects = self.project_manager.list_subjects()
            return [SubjectDisplayDTO(subject) for subject in subjects]
        except Exception as e:
            self.log_bus.log(f"Error loading subjects: {e}", "error", "GUISubjectService")
            return []

    def add_subject(self, subject_id: str, sex: str, genotype: str = None,
                   birth_date: datetime = None) -> Optional[Subject]:
        """Add a new subject via GUI."""
        try:
            # Validate and convert sex enum
            sex_enum = None
            if sex:
                sex_upper = sex.upper()
                if sex_upper in ["MALE", "M"]:
                    sex_enum = Sex.MALE
                elif sex_upper in ["FEMALE", "F"]:
                    sex_enum = Sex.FEMALE
                elif sex_upper == "UNKNOWN":
                    sex_enum = Sex.UNKNOWN
                else:
                    self.log_bus.log(f"Invalid sex value: {sex}", "error", "GUISubjectService")
                    return None

            subject = Subject(
                id=subject_id,
                sex=sex_enum,
                genotype=genotype,
                birth_date=birth_date
            )

            saved_subject = self.project_manager.add_subject(subject)
            self.log_bus.log(f"Subject {subject_id} added successfully", "success", "GUISubjectService")
            return saved_subject

        except Exception as e:
            self.log_bus.log(f"Error adding subject {subject_id}: {e}", "error", "GUISubjectService")
            return None

    def get_subject_by_id(self, subject_id: str) -> Optional[SubjectDisplayDTO]:
        """Get a specific subject for display."""
        try:
            subject = self.project_manager.get_subject(subject_id)
            return SubjectDisplayDTO(subject) if subject else None
        except Exception as e:
            self.log_bus.log(f"Error getting subject {subject_id}: {e}", "error", "GUISubjectService")
            return None

    def remove_subject(self, subject_id: str) -> bool:
        """Remove a subject."""
        try:
            success = self.project_manager.remove_subject(subject_id)
            if success:
                self.log_bus.log(f"Subject {subject_id} removed successfully", "success", "GUISubjectService")
            else:
                self.log_bus.log(f"Failed to remove subject {subject_id}", "warning", "GUISubjectService")
            return success
        except Exception as e:
            self.log_bus.log(f"Error removing subject {subject_id}: {e}", "error", "GUISubjectService")
            return False


class GUIExperimentService:
    """Service for GUI experiment operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        self.project_manager = project_manager
        self.log_bus = LoggingEventBus.get_instance()

    def get_experiments_for_display(self) -> List[ExperimentDisplayDTO]:
        """Get all experiments formatted for GUI display."""
        try:
            experiments = self.project_manager.list_experiments()
            return [ExperimentDisplayDTO(exp) for exp in experiments]
        except Exception as e:
            self.log_bus.log(f"Error loading experiments: {e}", "error", "GUIExperimentService")
            return []

    def add_experiment(self, experiment_id: str, subject_id: str, experiment_type: str,
                      date_recorded: datetime, processing_stage: str = "planned") -> Optional[Experiment]:
        """Add a new experiment via GUI."""
        try:
            # Validate processing stage enum
            try:
                stage_enum = ProcessingStage(processing_stage.lower()) if processing_stage else ProcessingStage.PLANNED
            except ValueError:
                self.log_bus.log(f"Invalid processing stage: {processing_stage}", "error", "GUIExperimentService")
                return None

            experiment = Experiment(
                id=experiment_id,
                subject_id=subject_id,
                experiment_type=experiment_type,
                date_recorded=date_recorded,
                processing_stage=stage_enum
            )

            saved_experiment = self.project_manager.add_experiment(experiment)
            self.log_bus.log(f"Experiment {experiment_id} added successfully", "success", "GUIExperimentService")
            return saved_experiment

        except Exception as e:
            self.log_bus.log(f"Error adding experiment {experiment_id}: {e}", "error", "GUIExperimentService")
            return None

    def get_experiment_by_id(self, experiment_id: str) -> Optional[ExperimentDisplayDTO]:
        """Get a specific experiment for display."""
        try:
            experiment = self.project_manager.get_experiment(experiment_id)
            return ExperimentDisplayDTO(experiment) if experiment else None
        except Exception as e:
            self.log_bus.log(f"Error getting experiment {experiment_id}: {e}", "error", "GUIExperimentService")
            return None

    def get_experiments_by_subject(self, subject_id: str) -> List[ExperimentDisplayDTO]:
        """Get all experiments for a specific subject."""
        try:
            experiments = self.project_manager.get_experiments_by_subject(subject_id)
            return [ExperimentDisplayDTO(exp) for exp in experiments]
        except Exception as e:
            self.log_bus.log(f"Error getting experiments for subject {subject_id}: {e}", "error", "GUIExperimentService")
            return []

    def remove_experiment(self, experiment_id: str) -> bool:
        """Remove an experiment."""
        try:
            success = self.project_manager.remove_experiment(experiment_id)
            if success:
                self.log_bus.log(f"Experiment {experiment_id} removed successfully", "success", "GUIExperimentService")
            else:
                self.log_bus.log(f"Failed to remove experiment {experiment_id}", "warning", "GUIExperimentService")
            return success
        except Exception as e:
            self.log_bus.log(f"Error removing experiment {experiment_id}: {e}", "error", "GUIExperimentService")
            return False


class GUIProjectService:
    """Service for GUI project operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        self.project_manager = project_manager
        self.log_bus = LoggingEventBus.get_instance()

    def get_project_info(self) -> Dict[str, Any]:
        """Get project information for display."""
        try:
            subjects = self.project_manager.list_subjects()
            experiments = self.project_manager.list_experiments()
            videos = self.project_manager.list_videos()

            return {
                "name": self.project_manager.config.name,
                "path": str(self.project_manager.project_path),
                "subject_count": len(subjects),
                "experiment_count": len(experiments),
                "video_count": len(videos),
                "shared_root": str(self.project_manager.config.shared_root) if self.project_manager.config.shared_root else None
            }
        except Exception as e:
            self.log_bus.log(f"Error getting project info: {e}", "error", "GUIProjectService")
            return {}

    def get_project_statistics(self) -> Dict[str, Any]:
        """Get detailed project statistics."""
        try:
            return self.project_manager.get_statistics()
        except Exception as e:
            self.log_bus.log(f"Error getting project statistics: {e}", "error", "GUIProjectService")
            return {}


class GUIServiceFactory:
    """Factory for creating GUI services."""

    def __init__(self, project_manager: ProjectManagerClean):
        self.project_manager = project_manager

    def create_subject_service(self) -> GUISubjectService:
        """Create subject service."""
        return GUISubjectService(self.project_manager)

    def create_experiment_service(self) -> GUIExperimentService:
        """Create experiment service."""
        return GUIExperimentService(self.project_manager)

    def create_project_service(self) -> GUIProjectService:
        """Create project service."""
        return GUIProjectService(self.project_manager)
