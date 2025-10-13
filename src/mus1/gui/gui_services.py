"""
GUI Services Layer

This module provides services that bridge the GUI layer with the clean architecture.
These services handle the conversion between domain models and GUI-friendly DTOs,
and provide a clean interface for GUI components to interact with the business logic.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from ..core.metadata import Subject, Experiment, VideoFile, Sex, ProcessingStage, SubjectDesignation
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
                   birth_date: datetime = None, colony_id: str = None,
                   notes: str = "", designation: str = "experimental") -> Optional[Subject]:
        """Add a new subject via GUI.

        This method creates subjects with comprehensive metadata that's compatible
        with both manual entry and future plugin-based bulk import operations.
        """
        try:
            # Validate subject ID
            if not subject_id or not subject_id.strip():
                self.log_bus.log("Subject ID cannot be empty", "error", "GUISubjectService")
                return None

            subject_id = subject_id.strip()

            # Check for duplicate subject ID
            existing = self.project_manager.get_subject(subject_id)
            if existing:
                self.log_bus.log(f"Subject ID '{subject_id}' already exists", "error", "GUISubjectService")
                return None

            # Validate and convert sex enum
            sex_enum = Sex.UNKNOWN
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

            # Validate and convert designation enum
            designation_enum = SubjectDesignation.EXPERIMENTAL
            if designation:
                designation_upper = designation.upper()
                if designation_upper == "EXPERIMENTAL":
                    designation_enum = SubjectDesignation.EXPERIMENTAL
                elif designation_upper == "BREEDING":
                    designation_enum = SubjectDesignation.BREEDING
                elif designation_upper == "CULLED":
                    designation_enum = SubjectDesignation.CULLED
                else:
                    self.log_bus.log(f"Invalid designation value: {designation}", "error", "GUISubjectService")
                    return None

            # Ensure a colony exists - use default if not specified
            if not colony_id:
                colony_id = self._ensure_default_colony()

            # Validate colony exists
            colony = self.project_manager.get_colony(colony_id)
            if not colony:
                self.log_bus.log(f"Colony '{colony_id}' does not exist", "error", "GUISubjectService")
                return None

            # Create subject with comprehensive metadata for future compatibility
            subject = Subject(
                id=subject_id,
                colony_id=colony_id,
                sex=sex_enum,
                designation=designation_enum,
                birth_date=birth_date,
                individual_genotype=genotype,
                notes=notes.strip() if notes else ""
            )

            saved_subject = self.project_manager.add_subject(subject)
            self.log_bus.log(f"Subject {subject_id} added to colony '{colony_id}' successfully", "success", "GUISubjectService")
            return saved_subject

        except ValueError as ve:
            self.log_bus.log(f"Validation error adding subject {subject_id}: {ve}", "error", "GUISubjectService")
            return None
        except Exception as e:
            self.log_bus.log(f"Error adding subject {subject_id}: {e}", "error", "GUISubjectService")
            return None

    def _ensure_default_colony(self) -> str:
        """Ensure a default colony exists and return its ID."""
        default_colony_id = "default"

        # Check if default colony exists
        try:
            existing_colony = self.project_manager.get_colony(default_colony_id)
            if existing_colony:
                return default_colony_id
        except Exception:
            pass

        # Create default colony if it doesn't exist
        try:
            from ..core.metadata import Colony
            default_colony = Colony(
                id=default_colony_id,
                lab_id=self.project_manager.config.lab_id or "default_lab",
                name="Default Colony",
                background_strain="Unknown",
                genotype="Unknown"
            )
            self.project_manager.add_colony(default_colony)
            self.log_bus.log(f"Created default colony '{default_colony_id}'", "info", "GUISubjectService")
            return default_colony_id
        except Exception as e:
            self.log_bus.log(f"Error creating default colony: {e}", "error", "GUISubjectService")
            # If we can't create a default colony, try to use the project name as colony ID
            # This is a fallback that assumes the project name is a valid colony ID
            return self.project_manager.config.name

    def bulk_import_subjects(self, subjects_data: List[Dict[str, Any]],
                           colony_id: str = None) -> Dict[str, Any]:
        """Bulk import subjects with comprehensive validation.

        This method is designed for plugin compatibility and ensures
        that bulk imports follow the same validation rules as manual entry.

        Args:
            subjects_data: List of dicts with subject data
            colony_id: Colony to import into (creates default if None)

        Returns:
            Dict with 'success_count', 'errors', and 'imported_subjects'
        """
        if not colony_id:
            colony_id = self._ensure_default_colony()

        # Validate colony exists
        colony = self.project_manager.get_colony(colony_id)
        if not colony:
            return {
                'success_count': 0,
                'errors': [f"Colony '{colony_id}' does not exist"],
                'imported_subjects': []
            }

        success_count = 0
        errors = []
        imported_subjects = []

        for i, subject_data in enumerate(subjects_data):
            try:
                # Extract and validate data with defaults compatible with manual entry
                subject_id = subject_data.get('id') or subject_data.get('subject_id')
                if not subject_id:
                    errors.append(f"Row {i+1}: Missing subject ID")
                    continue

                # Use the same validation logic as manual entry
                subject = self.add_subject(
                    subject_id=str(subject_id),
                    sex=subject_data.get('sex', 'UNKNOWN'),
                    genotype=subject_data.get('genotype') or subject_data.get('individual_genotype'),
                    birth_date=subject_data.get('birth_date'),
                    colony_id=colony_id,
                    notes=subject_data.get('notes', ''),
                    designation=subject_data.get('designation', 'experimental')
                )

                if subject:
                    success_count += 1
                    imported_subjects.append(subject)
                else:
                    errors.append(f"Row {i+1}: Failed to create subject '{subject_id}'")

            except Exception as e:
                errors.append(f"Row {i+1}: {str(e)}")

        result = {
            'success_count': success_count,
            'errors': errors,
            'imported_subjects': imported_subjects
        }

        self.log_bus.log(f"Bulk import completed: {success_count} subjects imported, {len(errors)} errors",
                        "info" if success_count > 0 else "warning", "GUISubjectService")

        return result

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

    # ---- Body parts and objects (shims for GUI use) ----
    def update_active_body_parts(self, active_list: list[str]) -> None:
        """Update active body parts in the project."""
        try:
            self.project_manager.update_active_body_parts(active_list)
        except Exception as e:
            self.log_bus.log(f"Error updating active body parts: {e}", "error", "GUISubjectService")

    def update_master_body_parts(self, master_list: list[str]) -> None:
        """Update master body parts in the project."""
        try:
            self.project_manager.update_master_body_parts(master_list)
        except Exception as e:
            self.log_bus.log(f"Error updating master body parts: {e}", "error", "GUISubjectService")

    def add_treatment(self, name: str) -> None:
        try:
            self.project_manager.add_treatment(name)
        except Exception as e:
            self.log_bus.log(f"Error adding treatment '{name}': {e}", "error", "GUISubjectService")

    def add_genotype(self, name: str) -> None:
        try:
            self.project_manager.add_genotype(name)
        except Exception as e:
            self.log_bus.log(f"Error adding genotype '{name}': {e}", "error", "GUISubjectService")

    def add_tracked_object(self, name: str) -> None:
        try:
            self.project_manager.add_tracked_object(name)
        except Exception as e:
            self.log_bus.log(f"Error adding object '{name}': {e}", "error", "GUISubjectService")

    def get_available_treatments(self) -> List[str]:
        """Get all available treatments for the project."""
        try:
            return self.project_manager.get_available_treatments()
        except Exception as e:
            self.log_bus.log(f"Error getting available treatments: {e}", "error", "GUISubjectService")
            return []

    def get_available_genotypes(self) -> List[str]:
        """Get all available genotypes for the project."""
        try:
            return self.project_manager.get_available_genotypes()
        except Exception as e:
            self.log_bus.log(f"Error getting available genotypes: {e}", "error", "GUISubjectService")
            return []

    def update_tracked_objects(self, items: list, list_type: str) -> None:
        try:
            self.project_manager.update_tracked_objects(items, list_type=list_type)
        except Exception as e:
            self.log_bus.log(f"Error updating tracked objects: {e}", "error", "GUISubjectService")


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

    def get_subjects_for_display(self) -> List[SubjectDisplayDTO]:
        """Get all subjects formatted for GUI display (needed for experiment subject selection)."""
        try:
            subjects = self.project_manager.list_subjects()
            return [SubjectDisplayDTO(sub) for sub in subjects]
        except Exception as e:
            self.log_bus.log(f"Error loading subjects: {e}", "error", "GUISubjectService")
            return []

    def get_colonies_for_display(self) -> List[Dict[str, str]]:
        """Get all colonies formatted for GUI display."""
        try:
            # For now, return a simple list with the default colony
            # In the future, this could return all colonies from the project manager
            return [{"id": "default", "name": "Default Colony", "background_strain": "Unknown"}]
        except Exception as e:
            self.log_bus.log(f"Error loading colonies: {e}", "error", "GUISubjectService")
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
