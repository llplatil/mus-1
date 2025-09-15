"""
Setup Service Layer - Shared business logic for CLI and GUI setup workflows.

This module provides the core business logic for MUS1 setup, allowing both CLI
and GUI to share the same validation, configuration, and workflow logic.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import platform

from .config_manager import get_config_manager, set_config, get_config
from .metadata import Colony, Subject, Experiment, Worker, ScanTarget, WorkerProvider, ScanTargetKind
from .schema import model_to_colony


# ===========================================
# SETUP DTOs - Data Transfer Objects
# ===========================================

@dataclass
class UserProfileDTO:
    """Data transfer object for user profile setup."""
    name: str
    email: str
    organization: str
    default_projects_dir: Optional[Path] = None
    default_shared_dir: Optional[Path] = None

    def __post_init__(self):
        """Validate user profile data."""
        if not self.name or len(self.name.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        if not self.email or "@" not in self.email:
            raise ValueError("Valid email address required")
        if not self.organization or len(self.organization.strip()) < 2:
            raise ValueError("Organization must be at least 2 characters")


@dataclass
class SharedStorageDTO:
    """Data transfer object for shared storage setup."""
    path: Path
    create_if_missing: bool = True
    verify_permissions: bool = True

    def __post_init__(self):
        """Validate shared storage data."""
        if not self.path:
            raise ValueError("Shared storage path is required")


@dataclass
class LabDTO:
    """Data transfer object for lab creation."""
    id: str
    name: str
    creator_id: str
    institution: Optional[str] = None
    pi_name: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate lab data."""
        if not self.id or len(self.id.strip()) < 3:
            raise ValueError("Lab ID must be at least 3 characters")
        if not self.name or len(self.name.strip()) < 3:
            raise ValueError("Lab name must be at least 3 characters")
        if not self.creator_id:
            raise ValueError("Creator ID is required")


@dataclass
class ColonyDTO:
    """Data transfer object for colony creation."""
    id: str
    name: str
    genotype_of_interest: Optional[str] = None
    background_strain: Optional[str] = None
    lab_id: str = ""

    def __post_init__(self):
        """Validate colony data."""
        if not self.id or len(self.id.strip()) < 3:
            raise ValueError("Colony ID must be at least 3 characters")
        if not self.name or len(self.name.strip()) < 3:
            raise ValueError("Colony name must be at least 3 characters")
        if not self.lab_id:
            raise ValueError("Lab ID is required for colony")


@dataclass
class MUS1RootLocationDTO:
    """Data transfer object for MUS1 root location setup."""
    path: Path
    create_if_missing: bool = True
    copy_existing_config: bool = True

    def __post_init__(self):
        """Validate MUS1 root location data."""
        if not self.path:
            raise ValueError("MUS1 root path is required")


@dataclass
class SetupWorkflowDTO:
    """Complete setup workflow data transfer object."""
    mus1_root_location: Optional[MUS1RootLocationDTO] = None
    user_profile: Optional[UserProfileDTO] = None
    shared_storage: Optional[SharedStorageDTO] = None
    lab: Optional[LabDTO] = None
    colony: Optional[ColonyDTO] = None
    steps_completed: List[str] = None

    def __post_init__(self):
        if self.steps_completed is None:
            self.steps_completed = []


@dataclass
class SetupStatusDTO:
    """Status information for setup components."""
    mus1_root_configured: bool = False
    mus1_root_path: Optional[str] = None
    user_configured: bool = False
    user_name: Optional[str] = None
    shared_storage_configured: bool = False
    shared_storage_path: Optional[str] = None
    labs_count: int = 0
    projects_count: int = 0
    config_database_path: Optional[str] = None


# ===========================================
# SETUP SERVICE - Business Logic
# ===========================================

class SetupService:
    """
    Service class handling all setup-related business logic.

    This can be used by both CLI and GUI to ensure consistent behavior
    and avoid code duplication.
    """

    def __init__(self):
        # Don't cache config_manager - fetch fresh instance for each operation
        # This allows proper re-initialization after MUS1 root changes
        pass

    # ===========================================
    # MUS1 ROOT LOCATION MANAGEMENT
    # ===========================================

    def is_mus1_root_configured(self) -> bool:
        """Check if MUS1 root location is configured."""
        return bool(get_config("mus1.root_path"))

    def get_mus1_root_path(self) -> Optional[Path]:
        """Get configured MUS1 root path."""
        path_str = get_config("mus1.root_path")
        return Path(path_str) if path_str else None

    def setup_mus1_root_location(self, root_dto: MUS1RootLocationDTO) -> Dict[str, Any]:
        """
        Set up MUS1 root location.

        Args:
            root_dto: MUS1 root location configuration

        Returns:
            Dict with success status and details
        """
        # Validate/create directory
        if not root_dto.path.exists():
            if root_dto.create_if_missing:
                try:
                    root_dto.path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Failed to create MUS1 root directory: {e}"
                    }
            else:
                return {
                    "success": False,
                    "message": f"MUS1 root directory does not exist: {root_dto.path}"
                }

        # Verify it's a directory
        if not root_dto.path.is_dir():
            return {
                "success": False,
                "message": f"MUS1 root path is not a directory: {root_dto.path}"
            }

        # Create MUS1 subdirectories
        subdirs = ["config", "logs", "cache", "temp"]
        for subdir in subdirs:
            (root_dto.path / subdir).mkdir(exist_ok=True)

        # For custom locations, we need to set the MUS1_ROOT environment variable
        # so future processes know where to find the configuration
        if root_dto.path != self._get_default_mus1_root():
            import os
            os.environ["MUS1_ROOT"] = str(root_dto.path)

        # Save configuration (this will now be stored in the correct location)
        set_config("mus1.root_path", str(root_dto.path), scope="install")
        set_config("mus1.root_setup_date", datetime.now().isoformat(), scope="install")

        return {
            "success": True,
            "message": "MUS1 root location configured successfully",
            "path": root_dto.path,
            "config_path": str(get_config_manager().db_path)
        }

    def _get_default_mus1_root(self) -> Path:
        """Get the platform default MUS1 root location."""
        from .config_manager import _get_platform_default_mus1_root
        return _get_platform_default_mus1_root()

    # ===========================================
    # USER PROFILE MANAGEMENT
    # ===========================================

    def is_user_configured(self) -> bool:
        """Check if user profile is already configured."""
        return bool(get_config("user.name"))

    def get_user_profile(self) -> Optional[UserProfileDTO]:
        """Get current user profile if configured."""
        if not self.is_user_configured():
            return None

        return UserProfileDTO(
            name=get_config("user.name"),
            email=get_config("user.email"),
            organization=get_config("user.organization"),
            default_projects_dir=Path(get_config("user.default_projects_dir", "")) if get_config("user.default_projects_dir") else None,
            default_shared_dir=Path(get_config("user.default_shared_dir", "")) if get_config("user.default_shared_dir") else None
        )

    def setup_user_profile(self, user_dto: UserProfileDTO, force: bool = False) -> Dict[str, Any]:
        """
        Set up user profile.

        Args:
            user_dto: User profile data
            force: Whether to overwrite existing configuration

        Returns:
            Dict with success status and details
        """
        if self.is_user_configured() and not force:
            raise ValueError("User profile already exists. Use force=True to overwrite.")

        # Set platform-specific defaults
        if platform.system() == "Darwin":  # macOS
            if not user_dto.default_projects_dir:
                user_dto.default_projects_dir = Path.home() / "Documents" / "MUS1" / "Projects"
        else:
            if not user_dto.default_projects_dir:
                user_dto.default_projects_dir = Path.home() / "mus1-projects"

        # Generate user ID from email (this replaces the "dumbass lab ID" concept)
        user_id = user_dto.email.lower().replace("@", "_").replace(".", "_")

        # Create User entity in SQL database
        from .metadata import User
        from .repository import get_repository_factory
        from .config_manager import get_config_manager

        user_entity = User(
            id=user_id,
            name=user_dto.name,
            email=user_dto.email,
            organization=user_dto.organization,
            default_projects_dir=user_dto.default_projects_dir,
            default_shared_dir=user_dto.default_shared_dir,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # Save user to SQL database
        from .schema import Database
        config_manager = get_config_manager()
        db = Database(str(config_manager.db_path))
        repo_factory = get_repository_factory(db)
        saved_user = repo_factory.users.save(user_entity)

        # Save configuration (legacy support)
        set_config("user.id", user_id, scope="user")
        set_config("user.name", user_dto.name, scope="user")
        set_config("user.email", user_dto.email, scope="user")
        set_config("user.organization", user_dto.organization, scope="user")
        set_config("user.default_projects_dir", str(user_dto.default_projects_dir), scope="user")
        set_config("user.default_shared_dir", str(user_dto.default_shared_dir) if user_dto.default_shared_dir else None, scope="user")
        set_config("user.setup_date", datetime.now().isoformat(), scope="user")

        # Create default directories
        if user_dto.default_projects_dir:
            user_dto.default_projects_dir.mkdir(parents=True, exist_ok=True)

        return {
            "success": True,
            "message": "User profile configured successfully",
            "user": saved_user,
            "user_id": user_id,
            "config_path": str(get_config_manager().db_path)
        }

    # ===========================================
    # SHARED STORAGE MANAGEMENT
    # ===========================================

    def is_shared_storage_configured(self) -> bool:
        """Check if shared storage is configured."""
        return bool(get_config("storage.shared_root"))

    def get_shared_storage_path(self) -> Optional[Path]:
        """Get configured shared storage path."""
        path_str = get_config("storage.shared_root")
        return Path(path_str) if path_str else None

    def setup_shared_storage(self, storage_dto: SharedStorageDTO) -> Dict[str, Any]:
        """
        Set up shared storage.

        Args:
            storage_dto: Shared storage configuration

        Returns:
            Dict with success status and details
        """
        # Validate/create directory
        if not storage_dto.path.exists():
            if storage_dto.create_if_missing:
                try:
                    storage_dto.path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Failed to create directory: {e}"
                    }
            else:
                return {
                    "success": False,
                    "message": f"Directory does not exist: {storage_dto.path}"
                }

        # Verify it's a directory
        if not storage_dto.path.is_dir():
            return {
                "success": False,
                "message": f"Path is not a directory: {storage_dto.path}"
            }

        # Verify permissions if requested
        if storage_dto.verify_permissions:
            test_file = storage_dto.path / ".mus1_write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                return {
                    "success": False,
                    "message": f"No write permissions: {e}"
                }

        # Save configuration
        set_config("storage.shared_root", str(storage_dto.path), scope="user")
        set_config("storage.shared_setup_date", datetime.now().isoformat(), scope="user")

        return {
            "success": True,
            "message": "Shared storage configured successfully",
            "path": storage_dto.path,
            "config_path": str(get_config_manager().db_path)
        }

    # ===========================================
    # LAB MANAGEMENT
    # ===========================================

    def get_labs(self) -> Dict[str, Dict[str, Any]]:
        """Get all configured labs."""
        from .schema import Database
        from .repository import get_repository_factory

        config_manager = get_config_manager()
        db = Database(str(config_manager.db_path))
        repo_factory = get_repository_factory(db)

        # Get current user ID to filter labs by creator
        user_id = get_config("user.id", scope="user")
        if user_id:
            labs = repo_factory.labs.find_by_creator(user_id)
            # Convert to dict format for backward compatibility
            return {lab.id: {
                "id": lab.id,
                "name": lab.name,
                "institution": lab.institution,
                "pi_name": lab.pi_name,
                "created_at": lab.created_at.isoformat(),
                "projects": repo_factory.labs.get_projects(lab.id),
                "colonies": [model_to_colony(c).__dict__ for c in repo_factory.colonies.find_by_lab(lab.id)]
            } for lab in labs}
        else:
            # Fallback to all labs if no user context
            labs = repo_factory.labs.find_all()
            return {lab.id: {
                "id": lab.id,
                "name": lab.name,
                "institution": lab.institution,
                "pi_name": lab.pi_name,
                "created_at": lab.created_at.isoformat(),
                "projects": repo_factory.labs.get_projects(lab.id),
                "colonies": [model_to_colony(c).__dict__ for c in repo_factory.colonies.find_by_lab(lab.id)]
            } for lab in labs}

    def lab_exists(self, lab_id: str) -> bool:
        """Check if lab exists."""
        from .schema import Database
        from .repository import get_repository_factory

        config_manager = get_config_manager()
        db = Database(str(config_manager.db_path))
        repo_factory = get_repository_factory(db)

        lab = repo_factory.labs.find_by_id(lab_id)
        return lab is not None

    def create_lab(self, lab_dto: LabDTO) -> Dict[str, Any]:
        """
        Create a new lab.

        Args:
            lab_dto: Lab configuration data

        Returns:
            Dict with success status and details
        """
        if self.lab_exists(lab_dto.id):
            return {
                "success": False,
                "message": f"Lab '{lab_dto.id}' already exists"
            }

        # Create Lab entity in SQL database
        from .metadata import Lab
        from .schema import Database
        from .repository import get_repository_factory

        lab_entity = Lab(
            id=lab_dto.id,
            name=lab_dto.name,
            institution=lab_dto.institution,
            pi_name=lab_dto.pi_name,
            creator_id=lab_dto.creator_id,
            created_at=lab_dto.created_at or datetime.now()
        )

        # Save lab to SQL database
        config_manager = get_config_manager()
        db = Database(str(config_manager.db_path))
        repo_factory = get_repository_factory(db)
        saved_lab = repo_factory.labs.save(lab_entity)

        return {
            "success": True,
            "message": "Lab created successfully",
            "lab": saved_lab
        }

    def add_colony_to_lab(self, colony_dto: ColonyDTO) -> Dict[str, Any]:
        """
        Add a colony to an existing lab.

        Args:
            colony_dto: Colony configuration data

        Returns:
            Dict with success status and details
        """
        if not self.lab_exists(colony_dto.lab_id):
            return {
                "success": False,
                "message": f"Lab '{colony_dto.lab_id}' not found"
            }

        # Check if colony already exists in SQL database
        from .schema import Database
        from .repository import get_repository_factory

        config_manager = get_config_manager()
        db = Database(str(config_manager.db_path))
        repo_factory = get_repository_factory(db)

        existing_colony = repo_factory.colonies.find_by_id(colony_dto.id)
        if existing_colony:
            return {
                "success": False,
                "message": f"Colony '{colony_dto.id}' already exists"
            }

        # Create Colony entity in SQL database
        from .metadata import Colony
        colony_entity = Colony(
            id=colony_dto.id,
            name=colony_dto.name,
            lab_id=colony_dto.lab_id,
            genotype_of_interest=colony_dto.genotype_of_interest,
            background_strain=colony_dto.background_strain,
            date_added=datetime.now()
        )

        saved_colony = repo_factory.colonies.save(colony_entity)

        return {
            "success": True,
            "message": "Colony added to lab successfully",
            "colony": saved_colony,
            "lab": colony_dto.lab_id
        }

    # ===========================================
    # SETUP STATUS & WORKFLOW
    # ===========================================

    def get_setup_status(self) -> SetupStatusDTO:
        """Get comprehensive setup status."""
        labs = self.get_labs()
        projects_count = sum(len(lab.get("projects", [])) for lab in labs.values())

        return SetupStatusDTO(
            mus1_root_configured=self.is_mus1_root_configured(),
            mus1_root_path=get_config("mus1.root_path"),
            user_configured=self.is_user_configured(),
            user_name=get_config("user.name"),
            shared_storage_configured=self.is_shared_storage_configured(),
            shared_storage_path=get_config("storage.shared_root"),
            labs_count=len(labs),
            projects_count=projects_count,
            config_database_path=str(get_config_manager().db_path)
        )

    def run_setup_workflow(self, workflow_dto: SetupWorkflowDTO) -> Dict[str, Any]:
        """
        Run complete setup workflow.

        Args:
            workflow_dto: Complete workflow configuration

        Returns:
            Dict with workflow results
        """
        results = {
            "success": True,
            "steps_completed": [],
            "errors": []
        }

        try:
            # Step 1: MUS1 Root Location
            if workflow_dto.mus1_root_location:
                root_result = self.setup_mus1_root_location(workflow_dto.mus1_root_location)
                if root_result["success"]:
                    results["steps_completed"].append("mus1_root_location")
                else:
                    results["errors"].append(f"MUS1 root location: {root_result['message']}")

            # Step 2: User Profile
            if workflow_dto.user_profile:
                user_result = self.setup_user_profile(workflow_dto.user_profile)
                if user_result["success"]:
                    results["steps_completed"].append("user_profile")
                else:
                    results["errors"].append(f"User profile: {user_result['message']}")

            # Step 3: Shared Storage
            if workflow_dto.shared_storage:
                storage_result = self.setup_shared_storage(workflow_dto.shared_storage)
                if storage_result["success"]:
                    results["steps_completed"].append("shared_storage")
                else:
                    results["errors"].append(f"Shared storage: {storage_result['message']}")

            # Step 4: Lab
            if workflow_dto.lab:
                lab_result = self.create_lab(workflow_dto.lab)
                if lab_result["success"]:
                    results["steps_completed"].append("lab")
                else:
                    results["errors"].append(f"Lab: {lab_result['message']}")

            # Step 5: Colony
            if workflow_dto.colony:
                colony_result = self.add_colony_to_lab(workflow_dto.colony)
                if colony_result["success"]:
                    results["steps_completed"].append("colony")
                else:
                    results["errors"].append(f"Colony: {colony_result['message']}")

        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Workflow error: {str(e)}")

        return results


# ===========================================
# UTILITY FUNCTIONS
# ===========================================

def get_setup_service() -> SetupService:
    """Get the global setup service instance."""
    return SetupService()
