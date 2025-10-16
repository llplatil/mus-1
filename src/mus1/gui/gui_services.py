"""
GUI Services Layer

This module provides services that bridge the GUI layer with the clean architecture.
These services handle the conversion between domain models and GUI-friendly DTOs,
and provide a clean interface for GUI components to interact with the business logic.
"""

from typing import List, Optional, Dict, Any, Callable, TypeVar
from datetime import datetime
from pathlib import Path
from functools import wraps

from ..core.metadata import Subject, Experiment, VideoFile, Sex, ProcessingStage, SubjectDesignation
from ..core.project_manager_clean import ProjectManagerClean
from ..core.repository import RepositoryFactory
from ..core.logging_bus import LoggingEventBus

T = TypeVar('T')


class BaseGUIService:
    """Base class for GUI services providing common error handling and logging patterns."""

    def __init__(self, service_name: str):
        self.log_bus = LoggingEventBus.get_instance()
        self.service_name = service_name

    def handle_error(self, operation: str, exception: Exception, default_return=None):
        """Common error handling pattern for GUI services.

        Args:
            operation: Description of the operation that failed
            exception: The exception that occurred
            default_return: Default value to return on error

        Returns:
            The default_return value
        """
        self.log_bus.log(f"Error {operation}: {exception}", "error", self.service_name)
        return default_return

    def safe_execute(self, operation: str, func: Callable[[], T], default_return=None) -> T:
        """Safely execute a function with common error handling.

        Args:
            operation: Description of the operation for error messages
            func: Function to execute (should take no arguments)
            default_return: Value to return on error

        Returns:
            Result of func() or default_return on error
        """
        try:
            return func()
        except Exception as e:
            return self.handle_error(operation, e, default_return)


def gui_service_error_handler(operation: str, default_return=None):
    """Decorator for GUI service methods that provides common error handling.

    Args:
        operation: Description of the operation for error messages
        default_return: Value to return on error
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                return self.handle_error(operation, e, default_return)
        return wrapper
    return decorator


class SubjectDisplayDTO:
    """DTO for displaying subject information in GUI."""
    def __init__(self, subject: Subject, colony_name: str = None):
        self.id = subject.id
        self.sex = subject.sex.value if subject.sex else ""
        self.genotype = subject.genotype or ""
        self.birth_date = subject.birth_date
        self.age_days = subject.age_days
        self.date_added = subject.date_added
        # Add colony information
        self.colony_id = subject.colony_id
        # Colony name will be resolved separately since subjects may not have colony relationship loaded
        self.colony_name = colony_name

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


class GUISubjectService(BaseGUIService):
    """Service for GUI subject operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        super().__init__("GUISubjectService")
        self.project_manager = project_manager

    @gui_service_error_handler("loading subjects", [])
    def get_subjects_for_display(self) -> List[SubjectDisplayDTO]:
        """Get all subjects formatted for GUI display."""
        subjects = self.project_manager.list_subjects()

        # Build a lookup of colony names for efficient lookup
        colonies = self.project_manager.list_colonies()
        colony_lookup = {colony.id: colony.name for colony in colonies}

        return [SubjectDisplayDTO(subject, colony_lookup.get(subject.colony_id)) for subject in subjects]

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

            # Validate colony exists if one is specified
            if colony_id:
                colony = self.project_manager.get_colony(colony_id)
                if not colony:
                    self.log_bus.log(f"Colony '{colony_id}' does not exist", "error", "GUISubjectService")
                    return None

            # Create subject with comprehensive metadata for future compatibility
            # colony_id is now optional - subjects can exist without colonies
            subject = Subject(
                id=subject_id,
                colony_id=colony_id,  # Can be None
                sex=sex_enum,
                designation=designation_enum,
                birth_date=birth_date,
                notes=notes.strip() if notes else ""
            )
            # Set genotype using property (for backward compatibility)
            if genotype:
                subject.genotype = genotype

            saved_subject = self.project_manager.add_subject(subject)
            colony_msg = f" to colony '{colony_id}'" if colony_id else ""
            self.log_bus.log(f"Subject {subject_id} added{colony_msg} successfully", "success", "GUISubjectService")
            return saved_subject

        except ValueError as ve:
            self.log_bus.log(f"Validation error adding subject {subject_id}: {ve}", "error", "GUISubjectService")
            return None
        except Exception as e:
            return self.handle_error(f"adding subject {subject_id}", e, None)


    def bulk_import_subjects(self, subjects_data: List[Dict[str, Any]],
                           colony_id: str) -> Dict[str, Any]:
        """Bulk import subjects with comprehensive validation.

        This method is designed for plugin compatibility and ensures
        that bulk imports follow the same validation rules as manual entry.

        Args:
            subjects_data: List of dicts with subject data
            colony_id: Colony to import into (required)

        Returns:
            Dict with 'success_count', 'errors', and 'imported_subjects'
        """
        if not colony_id:
            return {
                'success_count': 0,
                'errors': ['Colony ID is required for bulk import'],
                'imported_subjects': []
            }

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
        return self.safe_execute(
            f"getting subject {subject_id}",
            lambda: SubjectDisplayDTO(self.project_manager.get_subject(subject_id)) if self.project_manager.get_subject(subject_id) else None,
            None
        )

    def remove_subject(self, subject_id: str) -> bool:
        """Remove a subject."""
        def _remove():
            success = self.project_manager.remove_subject(subject_id)
            if success:
                self.log_bus.log(f"Subject {subject_id} removed successfully", "success", "GUISubjectService")
            else:
                self.log_bus.log(f"Failed to remove subject {subject_id}", "warning", "GUISubjectService")
            return success

        return self.safe_execute(f"removing subject {subject_id}", _remove, False)

    # ---- Body parts and objects (shims for GUI use) ----
    @gui_service_error_handler("getting master body parts", [])
    def get_master_body_parts(self) -> List[str]:
        """Get master body parts from the project."""
        return self.project_manager.get_master_body_parts()

    @gui_service_error_handler("getting active body parts", [])
    def get_active_body_parts(self) -> List[str]:
        """Get active body parts from the project."""
        return self.project_manager.get_active_body_parts()

    @gui_service_error_handler("updating active body parts", None)
    def update_active_body_parts(self, active_list: list[str]) -> None:
        """Update active body parts in the project."""
        self.project_manager.update_active_body_parts(active_list)

    @gui_service_error_handler("updating master body parts", None)
    def update_master_body_parts(self, master_list: list[str]) -> None:
        """Update master body parts in the project."""
        self.project_manager.update_master_body_parts(master_list)

    # ---- Master metadata management (project level) ----
    @gui_service_error_handler("getting available genotypes", [])
    def get_master_genotypes(self) -> List[str]:
        """Get available genotypes from the project."""
        return self.project_manager.get_available_genotypes()

    @gui_service_error_handler("getting available treatments", [])
    def get_master_treatments(self) -> List[str]:
        """Get available treatments from the project."""
        return self.project_manager.get_available_treatments()

    @gui_service_error_handler("getting master tracked objects", [])
    def get_master_tracked_objects(self) -> List[str]:
        """Get master tracked objects from the project."""
        return self.project_manager.get_master_tracked_objects()

    @gui_service_error_handler("updating genotypes", None)
    def update_master_genotypes(self, genotypes: List[str]) -> None:
        """Update available genotypes in the project."""
        self.project_manager.update_available_genotypes(genotypes)

    @gui_service_error_handler("updating treatments", None)
    def update_master_treatments(self, treatments: List[str]) -> None:
        """Update available treatments in the project."""
        self.project_manager.update_available_treatments(treatments)

    @gui_service_error_handler("updating master tracked objects", None)
    def update_master_tracked_objects(self, objects: List[str]) -> None:
        """Update master tracked objects in the project."""
        self.project_manager.update_master_tracked_objects(objects)

    # ---- Colony-level metadata management ----
    def get_colony_genotypes(self, colony_id: str) -> List[str]:
        """Get genotypes available for a specific colony."""
        return self.safe_execute(
            f"getting colony genotypes for {colony_id}",
            lambda: self.get_master_genotypes(),
            []
        )

    def get_colony_treatments(self, colony_id: str) -> List[str]:
        """Get treatments available for a specific colony."""
        return self.safe_execute(
            f"getting colony treatments for {colony_id}",
            lambda: self.get_master_treatments(),
            []
        )

    def get_colony_tracked_objects(self, colony_id: str) -> List[str]:
        """Get tracked objects available for a specific colony."""
        return self.safe_execute(
            f"getting colony tracked objects for {colony_id}",
            lambda: self.get_master_tracked_objects(),
            []
        )

    def get_colony_body_parts(self, colony_id: str) -> List[str]:
        """Get body parts available for a specific colony."""
        return self.safe_execute(
            f"getting colony body parts for {colony_id}",
            lambda: self.get_master_body_parts(),
            []
        )

    def add_treatment(self, name: str) -> None:
        """Add a treatment to the project."""
        self.safe_execute(
            f"adding treatment '{name}'",
            lambda: self.project_manager.add_treatment(name),
            None
        )

    def add_genotype(self, name: str) -> None:
        """Add a genotype to the project."""
        self.safe_execute(
            f"adding genotype '{name}'",
            lambda: self.project_manager.add_genotype(name),
            None
        )

    def add_tracked_object(self, name: str) -> None:
        """Add a tracked object to the project."""
        self.safe_execute(
            f"adding tracked object '{name}'",
            lambda: self.project_manager.add_tracked_object(name),
            None
        )

    @gui_service_error_handler("getting available treatments", [])
    def get_available_treatments(self) -> List[str]:
        """Get all available treatments for the project."""
        return self.project_manager.get_available_treatments()

    @gui_service_error_handler("getting available genotypes", [])
    def get_available_genotypes(self) -> List[str]:
        """Get all available genotypes for the project."""
        return self.project_manager.get_available_genotypes()

    def update_tracked_objects(self, items: list, list_type: str) -> None:
        """Update tracked objects in the project."""
        self.safe_execute(
            "updating tracked objects",
            lambda: self.project_manager.update_tracked_objects(items, list_type=list_type),
            None
        )

    def get_colonies_for_display(self, lab_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Get colonies formatted for GUI display. If lab_id provided, filter by that lab."""
        def _get_colonies():
            if lab_id:
                # Get colonies for specific lab
                try:
                    # Prefer using project manager repositories cleanly
                    colonies = self.project_manager.repos.colonies.find_by_lab(lab_id)
                except Exception:
                    # Fallback to listing project colonies if repo access fails
                    colonies = self.project_manager.list_colonies()
            else:
                # Get colonies from the project manager (uses project's lab_id if set)
                colonies = self.project_manager.list_colonies()
            result = [{
                "id": c.id,
                "name": c.name,
                "genotype_of_interest": c.genotype_of_interest,
                "background_strain": c.background_strain
            } for c in colonies]

            # If no colonies found for the project's lab, try to get all colonies
            # This allows showing colonies even when project has no lab_id set
            if not result and not lab_id:
                try:
                    all_colonies = self.project_manager.repos.colonies.find_all()
                    result = [{
                        "id": c.id,
                        "name": c.name,
                        "genotype_of_interest": c.genotype_of_interest,
                        "background_strain": c.background_strain
                    } for c in all_colonies]
                except Exception:
                    pass

            return result

        return self.safe_execute("loading colonies", _get_colonies, [])

    @gui_service_error_handler("getting master tracked objects", [])
    def get_master_tracked_objects(self) -> List[str]:
        """Get master tracked objects from project manager."""
        return self.project_manager.get_master_tracked_objects()

    @gui_service_error_handler("getting active tracked objects", [])
    def get_active_tracked_objects(self) -> List[str]:
        """Get active tracked objects from project manager."""
        return self.project_manager.get_active_tracked_objects()

    def update_subject_colony(self, subject_id: str, colony_id: Optional[str]) -> bool:
        """Update a subject's colony membership."""
        def _update_colony():
            # Get the subject
            subject = self.project_manager.get_subject(subject_id)
            if not subject:
                self.log_bus.log(f"Subject {subject_id} not found", "error", "GUISubjectService")
                return False

            # Update the colony_id
            subject.colony_id = colony_id

            # Save the subject
            self.project_manager.add_subject(subject)
            self.log_bus.log(f"Updated colony for subject {subject_id} to {colony_id}", "info", "GUISubjectService")
            return True

        return self.safe_execute(f"updating subject colony", _update_colony, False)


class GUIExperimentService(BaseGUIService):
    """Service for GUI experiment operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        super().__init__("GUIExperimentService")
        self.project_manager = project_manager

    @gui_service_error_handler("loading experiments", [])
    def get_experiments_for_display(self) -> List[ExperimentDisplayDTO]:
        """Get all experiments formatted for GUI display."""
        experiments = self.project_manager.list_experiments()
        return [ExperimentDisplayDTO(exp) for exp in experiments]

    @gui_service_error_handler("loading subjects", [])
    def get_subjects_for_display(self) -> List[SubjectDisplayDTO]:
        """Get all subjects formatted for GUI display (needed for experiment subject selection)."""
        subjects = self.project_manager.list_subjects()
        return [SubjectDisplayDTO(sub) for sub in subjects]

    def get_colonies_for_display(self, lab_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Get colonies formatted for GUI display. If lab_id provided, filter by that lab."""
        def _get_colonies():
            if lab_id:
                # Get colonies for specific lab
                colonies = self.repos.colonies.find_by_lab(lab_id)
            else:
                # Get colonies from the project manager (uses project's lab_id if set)
                colonies = self.project_manager.list_colonies()
            result = [{
                "id": c.id,
                "name": c.name,
                "genotype_of_interest": c.genotype_of_interest,
                "background_strain": c.background_strain
            } for c in colonies]

            # If no colonies found for the project's lab, try to get all colonies
            # This allows showing colonies even when project has no lab_id set
            if not result and not lab_id:
                try:
                    all_colonies = self.project_manager.repos.colonies.find_all()
                    result = [{
                        "id": c.id,
                        "name": c.name,
                        "genotype_of_interest": c.genotype_of_interest,
                        "background_strain": c.background_strain
                    } for c in all_colonies]
                except Exception:
                    pass

            return result

        return self.safe_execute("loading colonies", _get_colonies, [])

    def update_subject_colony(self, subject_id: str, colony_id: Optional[str]) -> bool:
        """Update a subject's colony membership."""
        def _update_colony():
            # Get the subject
            subject = self.project_manager.get_subject(subject_id)
            if not subject:
                self.log_bus.log(f"Subject {subject_id} not found", "error", "GUISubjectService")
                return False

            # Update the colony_id
            subject.colony_id = colony_id

            # Save the subject
            self.project_manager.add_subject(subject)
            self.log_bus.log(f"Updated colony for subject {subject_id} to {colony_id}", "info", "GUISubjectService")
            return True

        return self.safe_execute(f"updating subject colony", _update_colony, False)

    def add_experiment(self, experiment_id: str, subject_id: str, experiment_type: str,
                      date_recorded: datetime, processing_stage: str = "planned") -> Optional[Experiment]:
        """Add a new experiment via GUI."""
        def _add_experiment():
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

        return self.safe_execute(f"adding experiment {experiment_id}", _add_experiment, None)

    def get_experiment_by_id(self, experiment_id: str) -> Optional[ExperimentDisplayDTO]:
        """Get a specific experiment for display."""
        return self.safe_execute(
            f"getting experiment {experiment_id}",
            lambda: ExperimentDisplayDTO(self.project_manager.get_experiment(experiment_id)) if self.project_manager.get_experiment(experiment_id) else None,
            None
        )

    def get_experiments_by_subject(self, subject_id: str) -> List[ExperimentDisplayDTO]:
        """Get all experiments for a specific subject."""
        return self.safe_execute(
            f"getting experiments for subject {subject_id}",
            lambda: [ExperimentDisplayDTO(exp) for exp in self.project_manager.list_experiments_for_subject(subject_id)],
            []
        )

    def remove_experiment(self, experiment_id: str) -> bool:
        """Remove an experiment."""
        def _remove_experiment():
            success = self.project_manager.remove_experiment(experiment_id)
            if success:
                self.log_bus.log(f"Experiment {experiment_id} removed successfully", "success", "GUIExperimentService")
            else:
                self.log_bus.log(f"Failed to remove experiment {experiment_id}", "warning", "GUIExperimentService")
            return success

        return self.safe_execute(f"removing experiment {experiment_id}", _remove_experiment, False)


class GUIProjectService(BaseGUIService):
    """Service for GUI project operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        super().__init__("GUIProjectService")
        self.project_manager = project_manager

    def get_project_info(self) -> Dict[str, Any]:
        """Get project information for display."""
        def _get_info():
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

        return self.safe_execute("getting project info", _get_info, {})

    @gui_service_error_handler("getting project statistics", {})
    def get_project_statistics(self) -> Dict[str, Any]:
        """Get detailed project statistics."""
        return self.project_manager.get_stats()


class LabService(BaseGUIService):
    """Service for GUI lab operations."""

    def __init__(self):
        super().__init__("LabService")
        self.setup_service = None

    def set_services(self, setup_service):
        """Set the setup service."""
        self.setup_service = setup_service

    def get_labs(self) -> List[Dict[str, Any]]:
        """Get all labs for display."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        def _get_labs():
            labs = self.setup_service.get_labs()
            return list(labs.values())

        return self.safe_execute("loading labs", _get_labs, [])

    def get_lab_members(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get members of a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        def _get_lab_members():
            result = self.setup_service.get_lab_members(lab_id)
            return result.get("members", [])

        return self.safe_execute(f"getting lab members for {lab_id}", _get_lab_members, [])

    def add_lab_member(self, lab_id: str, email: str, role: str = "member") -> bool:
        """Add a member to a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _add_member():
            result = self.setup_service.add_lab_member(lab_id, email, role)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("adding lab member", _add_member, False)

    def remove_lab_member(self, lab_id: str, user_id: str) -> bool:
        """Remove a member from a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _remove_member():
            result = self.setup_service.remove_lab_member(lab_id, user_id)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("removing lab member", _remove_member, False)

    def get_lab_colonies(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get colonies for a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        def _get_lab_colonies():
            result = self.setup_service.get_lab_colonies(lab_id)
            return result.get("colonies", [])

        return self.safe_execute(f"getting lab colonies for {lab_id}", _get_lab_colonies, [])

    def create_colony(self, lab_id: str, colony_id: str, name: str, genotype: str = None, background: str = None) -> bool:
        """Create a new colony in a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _create_colony():
            from ..core.metadata import ColonyDTO
            colony_dto = ColonyDTO(
                id=colony_id,
                name=name,
                genotype_of_interest=genotype,
                background_strain=background,
                lab_id=lab_id
            )
            result = self.setup_service.create_colony(lab_id, colony_dto)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("creating colony", _create_colony, False)

    def update_colony(self, colony_id: str, name: str = None, genotype: str = None, background: str = None) -> bool:
        """Update an existing colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _update_colony():
            result = self.setup_service.update_colony(colony_id, name, genotype, background)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("updating colony", _update_colony, False)

    def get_colony_subjects(self, colony_id: str) -> List[Dict[str, Any]]:
        """Get subjects for a colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        def _get_colony_subjects():
            result = self.setup_service.get_colony_subjects(colony_id)
            return result.get("subjects", [])

        return self.safe_execute(f"getting colony subjects for {colony_id}", _get_colony_subjects, [])

    def add_subject_to_colony(self, subject_id: str, colony_id: str) -> bool:
        """Add a subject to a colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _add_subject_to_colony():
            result = self.setup_service.add_subject_to_colony(subject_id, colony_id)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("adding subject to colony", _add_subject_to_colony, False)

    def remove_subject_from_colony(self, subject_id: str) -> bool:
        """Remove a subject from its colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _remove_subject_from_colony():
            result = self.setup_service.remove_subject_from_colony(subject_id)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("removing subject from colony", _remove_subject_from_colony, False)

    def get_lab_projects(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get projects registered with a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        def _get_lab_projects():
            result = self.setup_service.get_lab_projects(lab_id)
            return result.get("projects", [])

        return self.safe_execute(f"getting lab projects for {lab_id}", _get_lab_projects, [])

    def add_lab_project(self, lab_id: str, project_name: str, project_path: str) -> bool:
        """Add a project to a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _add_lab_project():
            result = self.setup_service.add_lab_project(lab_id, project_name, project_path)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("adding project to lab", _add_lab_project, False)

    def remove_lab_project(self, lab_id: str, project_name: str) -> bool:
        """Remove a project from a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _remove_lab_project():
            result = self.setup_service.remove_lab_project(lab_id, project_name)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("removing project from lab", _remove_lab_project, False)

    def create_lab(self, lab_id: str, name: str, institution: str = None, pi_name: str = None) -> bool:
        """Create a new lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _create_lab():
            from ..core.metadata import LabDTO
            from ..core.config_manager import get_config

            user_id = get_config("user.id", scope="user")
            if not user_id:
                self.log_bus.log("No user configured", "error", "LabService")
                return False

            lab_dto = LabDTO(
                id=lab_id,
                name=name,
                institution=institution,
                pi_name=pi_name,
                creator_id=user_id
            )

            result = self.setup_service.create_lab(lab_dto)
            if result["success"]:
                self.log_bus.log(f"Lab '{name}' created successfully", "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("creating lab", _create_lab, False)

    def update_lab(self, lab_id: str, name: str = None, institution: str = None, pi_name: str = None) -> bool:
        """Update an existing lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _update_lab():
            result = self.setup_service.update_lab(lab_id, name, institution, pi_name)
            if result["success"]:
                self.log_bus.log(f"Lab '{lab_id}' updated successfully", "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("updating lab", _update_lab, False)

    def associate_project_with_lab(self, lab_id: str, project_name: str, project_path: str) -> bool:
        """Associate a project with a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        def _associate_project():
            result = self.setup_service.add_lab_project(lab_id, project_name, project_path)
            if result["success"]:
                self.log_bus.log(f"Project '{project_name}' associated with lab '{lab_id}' successfully", "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False

        return self.safe_execute("associating project with lab", _associate_project, False)


class GUIPluginService(BaseGUIService):
    """Service for GUI plugin operations."""

    def __init__(self, plugin_manager):
        super().__init__("GUIPluginService")
        self.plugin_manager = plugin_manager

    def get_importer_plugins(self) -> List[Dict[str, Any]]:
        """Get all importer plugins formatted for GUI."""
        def _get_importer_plugins():
            plugins = self.plugin_manager.get_importer_plugins()
            return [{
                "name": p.plugin_self_metadata().name,
                "description": p.plugin_self_metadata().description,
                "version": p.plugin_self_metadata().version,
                "capabilities": p.analysis_capabilities(),
                "required_fields": p.required_fields(),
                "optional_fields": p.optional_fields(),
                "plugin": p
            } for p in plugins]

        return self.safe_execute("getting importer plugins", _get_importer_plugins, [])

    def get_analysis_plugins_for_type(self, experiment_type: str) -> List[Dict[str, Any]]:
        """Get analysis plugins for a specific experiment type."""
        def _get_analysis_plugins():
            plugins = self.plugin_manager.get_analysis_plugins_for_type(experiment_type)
            return [{
                "name": p.plugin_self_metadata().name,
                "description": p.plugin_self_metadata().description,
                "version": p.plugin_self_metadata().version,
                "capabilities": p.analysis_capabilities(),
                "required_fields": p.required_fields(),
                "optional_fields": p.optional_fields(),
                "plugin": p
            } for p in plugins]

        return self.safe_execute(f"getting analysis plugins for type {experiment_type}", _get_analysis_plugins, [])

    def get_exporter_plugins(self) -> List[Dict[str, Any]]:
        """Get all exporter plugins formatted for GUI."""
        def _get_exporter_plugins():
            plugins = self.plugin_manager.get_exporter_plugins()
            return [{
                "name": p.plugin_self_metadata().name,
                "description": p.plugin_self_metadata().description,
                "version": p.plugin_self_metadata().version,
                "capabilities": p.analysis_capabilities(),
                "required_fields": p.required_fields(),
                "optional_fields": p.optional_fields(),
                "plugin": p
            } for p in plugins]

        return self.safe_execute("getting exporter plugins", _get_exporter_plugins, [])

    def execute_plugin(self, plugin, experiment_id: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a plugin with given parameters."""
        def _execute_plugin():
            if parameters is None:
                parameters = {}

            # Get experiment data
            experiment_data = self.plugin_manager.plugin_service.get_experiment_data(experiment_id)
            if not experiment_data:
                return {"success": False, "error": f"Experiment {experiment_id} not found"}

            # Execute plugin
            result = plugin.run(experiment_data, parameters)

            # Store result if successful
            if result.get("success", False):
                self.plugin_manager.plugin_service.save_analysis_result(
                    experiment_id=experiment_id,
                    plugin_name=plugin.plugin_self_metadata().name,
                    capability=list(plugin.analysis_capabilities())[0] if plugin.analysis_capabilities() else "unknown",
                    result_data=result.get("data", {}),
                    status="success"
                )

            return result

        return self.safe_execute(f"executing plugin {plugin.plugin_self_metadata().name}", _execute_plugin, {"success": False, "error": "Unknown error"})


class GUIServiceFactory:
    """Factory for creating GUI services."""

    def __init__(self, project_manager: ProjectManagerClean):
        self.project_manager = project_manager
        self._plugin_manager = None

    def set_plugin_manager(self, plugin_manager):
        """Set the plugin manager for this factory."""
        self._plugin_manager = plugin_manager

    def create_subject_service(self) -> GUISubjectService:
        """Create subject service."""
        return GUISubjectService(self.project_manager)

    def create_experiment_service(self) -> GUIExperimentService:
        """Create experiment service."""
        return GUIExperimentService(self.project_manager)

    def create_project_service(self) -> GUIProjectService:
        """Create project service."""
        return GUIProjectService(self.project_manager)

    def create_lab_service(self) -> LabService:
        """Create lab service."""
        from ..core.setup_service import get_setup_service
        lab_service = LabService()
        lab_service.set_services(get_setup_service())
        return lab_service

    def create_plugin_service(self):
        """Create plugin service."""
        if self._plugin_manager is None:
            raise ValueError("Plugin manager not set. Call set_plugin_manager() first.")
        return GUIPluginService(self._plugin_manager)
