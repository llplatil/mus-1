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


class GUISubjectService:
    """Service for GUI subject operations."""

    def __init__(self, project_manager: ProjectManagerClean):
        self.project_manager = project_manager
        self.log_bus = LoggingEventBus.get_instance()

    def get_subjects_for_display(self) -> List[SubjectDisplayDTO]:
        """Get all subjects formatted for GUI display."""
        try:
            subjects = self.project_manager.list_subjects()

            # Build a lookup of colony names for efficient lookup
            colonies = self.project_manager.list_colonies()
            colony_lookup = {colony.id: colony.name for colony in colonies}

            return [SubjectDisplayDTO(subject, colony_lookup.get(subject.colony_id)) for subject in subjects]
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
        except Exception as e:
            self.log_bus.log(f"Error checking for existing default colony: {e}", "warning", "GUISubjectService")

        # Create default colony if it doesn't exist
        try:
            from ..core.metadata import Colony
            default_colony = Colony(
                id=default_colony_id,
                lab_id=self.project_manager.config.lab_id or "default_lab",
                name="Default Colony",
                background_strain="Unknown",
                genotype_of_interest="Unknown"
            )
            self.project_manager.add_colony(default_colony)
            self.log_bus.log(f"Created default colony '{default_colony_id}'", "info", "GUISubjectService")
            return default_colony_id
        except Exception as e:
            self.log_bus.log(f"Error creating default colony: {e}", "error", "GUISubjectService")
            # Try to find any existing colony to use as fallback
            try:
                colonies = self.project_manager.list_colonies()
                if colonies:
                    colony_id = colonies[0].id
                    self.log_bus.log(f"Using existing colony '{colony_id}' as fallback", "warning", "GUISubjectService")
                    return colony_id
            except Exception:
                pass

            # Last resort: create a colony with the project name
            project_colony_id = self.project_manager.config.name.replace(" ", "_").lower()
            try:
                from ..core.metadata import Colony
                project_colony = Colony(
                    id=project_colony_id,
                    lab_id=self.project_manager.config.lab_id or "default_lab",
                    name=f"{self.project_manager.config.name} Colony",
                    background_strain="Unknown",
                    genotype_of_interest="Unknown"
                )
                self.project_manager.add_colony(project_colony)
                self.log_bus.log(f"Created project-specific colony '{project_colony_id}'", "info", "GUISubjectService")
                return project_colony_id
            except Exception as e2:
                self.log_bus.log(f"Failed to create any colony: {e2}", "error", "GUISubjectService")
                # Return the project name anyway - this will cause validation errors but won't crash
                return project_colony_id

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
    def get_master_body_parts(self) -> List[str]:
        """Get master body parts from the project."""
        try:
            return self.project_manager.get_master_body_parts()
        except Exception as e:
            self.log_bus.log(f"Error getting master body parts: {e}", "error", "GUISubjectService")
            return []

    def get_active_body_parts(self) -> List[str]:
        """Get active body parts from the project."""
        try:
            return self.project_manager.get_active_body_parts()
        except Exception as e:
            self.log_bus.log(f"Error getting active body parts: {e}", "error", "GUISubjectService")
            return []

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

    # ---- Master metadata management (project level) ----
    def get_master_genotypes(self) -> List[str]:
        """Get available genotypes from the project."""
        try:
            return self.project_manager.get_available_genotypes()
        except Exception as e:
            self.log_bus.log(f"Error getting available genotypes: {e}", "error", "GUISubjectService")
            return []

    def get_master_treatments(self) -> List[str]:
        """Get available treatments from the project."""
        try:
            return self.project_manager.get_available_treatments()
        except Exception as e:
            self.log_bus.log(f"Error getting available treatments: {e}", "error", "GUISubjectService")
            return []

    def get_master_tracked_objects(self) -> List[str]:
        """Get master tracked objects from the project."""
        try:
            return self.project_manager.get_master_tracked_objects()
        except Exception as e:
            self.log_bus.log(f"Error getting master tracked objects: {e}", "error", "GUISubjectService")
            return []

    def update_master_genotypes(self, genotypes: List[str]) -> None:
        """Update available genotypes in the project."""
        try:
            self.project_manager.update_available_genotypes(genotypes)
        except Exception as e:
            self.log_bus.log(f"Error updating genotypes: {e}", "error", "GUISubjectService")

    def update_master_treatments(self, treatments: List[str]) -> None:
        """Update available treatments in the project."""
        try:
            self.project_manager.update_available_treatments(treatments)
        except Exception as e:
            self.log_bus.log(f"Error updating treatments: {e}", "error", "GUISubjectService")

    def update_master_tracked_objects(self, objects: List[str]) -> None:
        """Update master tracked objects in the project."""
        try:
            self.project_manager.update_master_tracked_objects(objects)
        except Exception as e:
            self.log_bus.log(f"Error updating master tracked objects: {e}", "error", "GUISubjectService")

    # ---- Colony-level metadata management ----
    def get_colony_genotypes(self, colony_id: str) -> List[str]:
        """Get genotypes available for a specific colony."""
        try:
            # For now, colonies inherit from project master lists
            # In the future, this could filter based on colony-specific settings
            return self.get_master_genotypes()
        except Exception as e:
            self.log_bus.log(f"Error getting colony genotypes for {colony_id}: {e}", "error", "GUISubjectService")
            return []

    def get_colony_treatments(self, colony_id: str) -> List[str]:
        """Get treatments available for a specific colony."""
        try:
            # For now, colonies inherit from project master lists
            return self.get_master_treatments()
        except Exception as e:
            self.log_bus.log(f"Error getting colony treatments for {colony_id}: {e}", "error", "GUISubjectService")
            return []

    def get_colony_tracked_objects(self, colony_id: str) -> List[str]:
        """Get tracked objects available for a specific colony."""
        try:
            # For now, colonies inherit from project master lists
            return self.get_master_tracked_objects()
        except Exception as e:
            self.log_bus.log(f"Error getting colony tracked objects for {colony_id}: {e}", "error", "GUISubjectService")
            return []

    def get_colony_body_parts(self, colony_id: str) -> List[str]:
        """Get body parts available for a specific colony."""
        try:
            # For now, colonies inherit from project master lists
            return self.get_master_body_parts()
        except Exception as e:
            self.log_bus.log(f"Error getting colony body parts for {colony_id}: {e}", "error", "GUISubjectService")
            return []

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

    def get_master_tracked_objects(self) -> List[str]:
        """Get master tracked objects from project manager."""
        try:
            return self.project_manager.get_master_tracked_objects()
        except Exception as e:
            self.log_bus.log(f"Error getting master tracked objects: {e}", "error", "GUISubjectService")
            return []

    def get_active_tracked_objects(self) -> List[str]:
        """Get active tracked objects from project manager."""
        try:
            return self.project_manager.get_active_tracked_objects()
        except Exception as e:
            self.log_bus.log(f"Error getting active tracked objects: {e}", "error", "GUISubjectService")
            return []


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
            self.log_bus.log(f"Error loading subjects: {e}", "error", "GUIExperimentService")
            return []

    def get_colonies_for_display(self) -> List[Dict[str, str]]:
        """Get all colonies formatted for GUI display."""
        try:
            # Get colonies from the project manager
            colonies = self.project_manager.list_colonies()
            result = [{
                "id": c.id,
                "name": c.name,
                "genotype_of_interest": c.genotype_of_interest,
                "background_strain": c.background_strain
            } for c in colonies]

            # If no colonies found for the project's lab, try to get all colonies
            # This allows showing colonies even when project has no lab_id set
            if not result:
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
        except Exception as e:
            self.log_bus.log(f"Error loading colonies: {e}", "error", "GUISubjectService")
            return []

    def update_subject_colony(self, subject_id: str, colony_id: Optional[str]) -> bool:
        """Update a subject's colony membership."""
        try:
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
        except Exception as e:
            self.log_bus.log(f"Error updating subject colony: {e}", "error", "GUISubjectService")
            return False

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
            experiments = self.project_manager.list_experiments_for_subject(subject_id)
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
            return self.project_manager.get_stats()
        except Exception as e:
            self.log_bus.log(f"Error getting project statistics: {e}", "error", "GUIProjectService")
            return {}


class LabService:
    """Service for GUI lab operations."""

    def __init__(self):
        self.setup_service = None
        self.log_bus = LoggingEventBus.get_instance()

    def set_services(self, setup_service):
        """Set the setup service."""
        self.setup_service = setup_service

    def get_labs(self) -> List[Dict[str, Any]]:
        """Get all labs for display."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        try:
            labs = self.setup_service.get_labs()
            return list(labs.values())
        except Exception as e:
            self.log_bus.log(f"Error loading labs: {e}", "error", "LabService")
            return []

    def get_lab_members(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get members of a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        try:
            result = self.setup_service.get_lab_members(lab_id)
            return result.get("members", [])
        except Exception as e:
            self.log_bus.log(f"Error loading lab members: {e}", "error", "LabService")
            return []

    def add_lab_member(self, lab_id: str, email: str, role: str = "member") -> bool:
        """Add a member to a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.add_lab_member(lab_id, email, role)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error adding lab member: {e}", "error", "LabService")
            return False

    def remove_lab_member(self, lab_id: str, user_id: str) -> bool:
        """Remove a member from a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.remove_lab_member(lab_id, user_id)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error removing lab member: {e}", "error", "LabService")
            return False

    def get_lab_colonies(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get colonies for a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        try:
            result = self.setup_service.get_lab_colonies(lab_id)
            return result.get("colonies", [])
        except Exception as e:
            self.log_bus.log(f"Error loading lab colonies: {e}", "error", "LabService")
            return []

    def create_colony(self, lab_id: str, colony_id: str, name: str, genotype: str = None, background: str = None) -> bool:
        """Create a new colony in a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
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
        except Exception as e:
            self.log_bus.log(f"Error creating colony: {e}", "error", "LabService")
            return False

    def update_colony(self, colony_id: str, name: str = None, genotype: str = None, background: str = None) -> bool:
        """Update an existing colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.update_colony(colony_id, name, genotype, background)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error updating colony: {e}", "error", "LabService")
            return False

    def get_colony_subjects(self, colony_id: str) -> List[Dict[str, Any]]:
        """Get subjects for a colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        try:
            result = self.setup_service.get_colony_subjects(colony_id)
            return result.get("subjects", [])
        except Exception as e:
            self.log_bus.log(f"Error loading colony subjects: {e}", "error", "LabService")
            return []

    def add_subject_to_colony(self, subject_id: str, colony_id: str) -> bool:
        """Add a subject to a colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.add_subject_to_colony(subject_id, colony_id)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error adding subject to colony: {e}", "error", "LabService")
            return False

    def remove_subject_from_colony(self, subject_id: str) -> bool:
        """Remove a subject from its colony."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.remove_subject_from_colony(subject_id)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error removing subject from colony: {e}", "error", "LabService")
            return False

    def get_lab_projects(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get projects registered with a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return []

        try:
            result = self.setup_service.get_lab_projects(lab_id)
            return result.get("projects", [])
        except Exception as e:
            self.log_bus.log(f"Error loading lab projects: {e}", "error", "LabService")
            return []

    def add_lab_project(self, lab_id: str, project_name: str, project_path: str) -> bool:
        """Add a project to a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.add_lab_project(lab_id, project_name, project_path)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error adding project to lab: {e}", "error", "LabService")
            return False

    def remove_lab_project(self, lab_id: str, project_name: str) -> bool:
        """Remove a project from a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.remove_lab_project(lab_id, project_name)
            if result["success"]:
                self.log_bus.log(result["message"], "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error removing project from lab: {e}", "error", "LabService")
            return False

    def create_lab(self, lab_id: str, name: str, institution: str = None, pi_name: str = None) -> bool:
        """Create a new lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
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
        except Exception as e:
            self.log_bus.log(f"Error creating lab: {e}", "error", "LabService")
            return False

    def update_lab(self, lab_id: str, name: str = None, institution: str = None, pi_name: str = None) -> bool:
        """Update an existing lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.update_lab(lab_id, name, institution, pi_name)
            if result["success"]:
                self.log_bus.log(f"Lab '{lab_id}' updated successfully", "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error updating lab: {e}", "error", "LabService")
            return False

    def associate_project_with_lab(self, lab_id: str, project_name: str, project_path: str) -> bool:
        """Associate a project with a lab."""
        if not self.setup_service:
            self.log_bus.log("Setup service not available", "error", "LabService")
            return False

        try:
            result = self.setup_service.add_lab_project(lab_id, project_name, project_path)
            if result["success"]:
                self.log_bus.log(f"Project '{project_name}' associated with lab '{lab_id}' successfully", "success", "LabService")
                return True
            else:
                self.log_bus.log(result["message"], "error", "LabService")
                return False
        except Exception as e:
            self.log_bus.log(f"Error associating project with lab: {e}", "error", "LabService")
            return False


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

    def create_lab_service(self) -> LabService:
        """Create lab service."""
        from ..core.setup_service import get_setup_service
        lab_service = LabService()
        lab_service.set_services(get_setup_service())
        return lab_service
