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
from .config_manager import set_lab_storage_root as cfg_set_lab_root
from .config_manager import set_lab_sharing_mode, get_lab_sharing_mode, get_lab_library_status
from .metadata import LabDTO, ColonyDTO  # Use Pydantic DTOs as single source
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


# Removed local LabDTO dataclass; use metadata.LabDTO


# Removed local ColonyDTO dataclass; use metadata.ColonyDTO


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
    steps_completed: Optional[List[str]] = None

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

    def _get_database(self):
        """Get the config database with ensured schema.

        The config database (config.db) also stores domain tables for users,
        labs, colonies, etc. Ensure those SQLAlchemy tables exist before any
        repository operations to avoid 'no such table' errors.
        """
        from .schema import Database
        from .config_manager import get_config_manager

        config_manager = get_config_manager()
        db = Database(str(config_manager.db_path))
        db.create_tables()
        return db

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

        # Optionally copy existing configuration into the new root
        # Only copy if requested and a valid source exists (has config/config.db)
        if root_dto.copy_existing_config:
            try:
                # Determine a candidate source to copy from: prefer currently bound config DB
                current_db_path = get_config_manager().db_path
                current_root = Path(current_db_path).parent.parent if current_db_path else None
                source_root_candidates = []
                if current_root and (current_root / "config" / "config.db").exists():
                    source_root_candidates.append(current_root)
                # Also consider the platform default if valid
                from .config_manager import _get_platform_default_mus1_root
                default_root = _get_platform_default_mus1_root()
                if (default_root / "config" / "config.db").exists():
                    source_root_candidates.append(default_root)

                # Pick the first existing candidate that is not the same as destination
                source_root = next((sr for sr in source_root_candidates if sr != root_dto.path), None)
                if source_root:
                    src_db = source_root / "config" / "config.db"
                    dst_db = root_dto.path / "config" / "config.db"
                    if src_db.exists() and not dst_db.exists():
                        import shutil
                        shutil.copy2(src_db, dst_db)
            except Exception:
                # Non-fatal; copying config is best-effort
                pass

        # For custom locations, we need to set the MUS1_ROOT environment variable
        # so future processes know where to find the configuration
        if root_dto.path != self._get_default_mus1_root():
            import os
            os.environ["MUS1_ROOT"] = str(root_dto.path)

        # Save configuration (this will now be stored in the correct location)
        set_config("mus1.root_path", str(root_dto.path), scope="install")
        set_config("mus1.root_setup_date", datetime.now().isoformat(), scope="install")

        # Reinitialize the global ConfigManager to point at the new root immediately
        try:
            from .config_manager import init_config_manager
            new_db_path = root_dto.path / "config" / "config.db"
            init_config_manager(new_db_path)
        except Exception:
            # Non-fatal; subsequent operations may recreate as needed
            pass

        # Write a stable root pointer file under platform default so future processes can rediscover
        try:
            from .config_manager import _get_platform_default_mus1_root, get_root_pointer_info
            default_root = _get_platform_default_mus1_root()
            pointer_dir = default_root / "config"
            pointer_dir.mkdir(parents=True, exist_ok=True)
            pointer_path = pointer_dir / "root_pointer.json"

            # Check for existing root pointer and handle cleanup/warnings
            existing_pointer = get_root_pointer_info()
            warning_messages: List[str] = []

            if existing_pointer["exists"]:
                if existing_pointer["valid"]:
                    # Valid existing pointer - warn about overwrite
                    warning_messages.append(f"Overwriting existing valid root pointer: {existing_pointer['target']}")
                else:
                    # Invalid existing pointer - warn and clean it up
                    warning_messages.append(f"Cleaning up invalid root pointer: {existing_pointer['target']}")
                    try:
                        existing_pointer["pointer_path"].unlink(missing_ok=True)
                    except Exception:
                        pass  # Non-fatal if we can't remove it

            # Write new root pointer
            with open(pointer_path, "w") as f:
                import json
                json.dump({"root": str(root_dto.path), "updated_at": datetime.now().isoformat()}, f)

            # Collect warnings; they will be included in the returned dict below
            collected_warnings = warning_messages

        except Exception as e:
            # Non-fatal; root pointer is best-effort
            collected_warnings = [f"Failed to update root pointer: {e}"]

        return {
            "success": True,
            "message": "MUS1 root location configured successfully",
            "path": root_dto.path,
            "config_path": str(get_config_manager().db_path),
            "warnings": collected_warnings if 'collected_warnings' in locals() and collected_warnings else []
        }

    def _get_default_mus1_root(self) -> Path:
        """Get the platform default MUS1 root location."""
        from .config_manager import _get_platform_default_mus1_root
        return _get_platform_default_mus1_root()

    # ===========================================
    # LEGACY USER PROFILE MIGRATION
    # ===========================================

    def migrate_legacy_user_profile_if_needed(self) -> Dict[str, Any]:
        """Migrate legacy user profile keys from ConfigManager to SQL and clear duplicates.

        Behavior:
        - If ConfigManager has legacy keys (user.name/email/organization/default dirs),
          create the SQL user if missing and set ConfigManager user.id.
        - Remove the legacy keys from ConfigManager to avoid drift.
        - No-op if no legacy keys are present or SQL user already exists.
        """
        try:
            name = get_config("user.name", scope="user")
            email = get_config("user.email", scope="user")
            organization = get_config("user.organization", scope="user")
            default_projects_dir = get_config("user.default_projects_dir", scope="user")
            default_shared_dir = get_config("user.default_shared_dir", scope="user")

            has_legacy = any([name, email, organization, default_projects_dir, default_shared_dir])
            if not has_legacy:
                return {"changed": False, "message": "No legacy user keys found"}

            if not email or "@" not in str(email):
                return {"changed": False, "message": "Legacy keys present but email missing; skipping"}

            # Check if SQL user exists
            db = self._get_database()
            from .repository import get_repository_factory
            repos = get_repository_factory(db)
            existing = repos.users.find_by_email(email)

            # Ensure directories are Paths
            from pathlib import Path as _Path
            proj_dir_path = _Path(default_projects_dir) if default_projects_dir else None
            shared_dir_path = _Path(default_shared_dir) if default_shared_dir else None

            if not existing:
                # Create SQL user from legacy keys
                from .metadata import User
                user_id = str(email).lower().replace("@", "_").replace(".", "_")
                user_entity = User(
                    id=user_id,
                    name=name or "",
                    email=email,
                    organization=organization or None,
                    default_projects_dir=proj_dir_path,
                    default_shared_dir=shared_dir_path,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                repos.users.save(user_entity)
                # Set active user id
                set_config("user.id", user_id, scope="user")

                # Create default directories if provided
                try:
                    if proj_dir_path:
                        proj_dir_path.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass

            # Remove legacy keys from ConfigManager
            try:
                from .config_manager import delete_config
                for key in ["user.name", "user.email", "user.organization", "user.default_projects_dir", "user.default_shared_dir"]:
                    delete_config(key, scope="user")
            except Exception:
                pass

            return {"changed": True, "message": "Legacy user keys migrated to SQL and cleared"}

        except Exception as e:
            return {"changed": False, "error": str(e)}

    # ===========================================
    # USER PROFILE MANAGEMENT
    # ===========================================

    def is_user_configured(self) -> bool:
        """Check if user profile is already configured.

        Configuration is considered present if an active user id is set in
        ConfigManager and a corresponding user exists in the SQL users table.
        """
        from .repository import get_repository_factory

        user_id = get_config("user.id", scope="user")
        if not user_id:
            return False

        db = self._get_database()
        repo_factory = get_repository_factory(db)
        return repo_factory.users.find_by_id(user_id) is not None

    def get_user_profile(self) -> Optional[UserProfileDTO]:
        """Get current user profile from SQL if configured."""
        if not self.is_user_configured():
            return None

        from .repository import get_repository_factory

        user_id = get_config("user.id", scope="user")
        db = self._get_database()
        repo_factory = get_repository_factory(db)
        user = repo_factory.users.find_by_id(user_id)
        if not user:
            return None

        return UserProfileDTO(
            name=user.name,
            email=user.email,
            organization=user.organization or "",
            default_projects_dir=user.default_projects_dir,
            default_shared_dir=user.default_shared_dir
        )

    def get_all_users(self) -> Dict[str, Dict[str, Any]]:
        """Get all configured users as a dictionary."""
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)
        user_repo = repo_factory.users

        users = user_repo.find_all()
        result = {}

        for user in users:
            result[user.id] = {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "organization": user.organization or "",
                "default_projects_dir": str(user.default_projects_dir) if user.default_projects_dir else None,
                "default_shared_dir": str(user.default_shared_dir) if user.default_shared_dir else None,
            }

        return result

    def update_lab(self, lab_id: str, name: Optional[str] = None, institution: Optional[str] = None,
                   pi_name: Optional[str] = None) -> Dict[str, Any]:
        """Update lab information in the database.

        Args:
            lab_id: The lab ID to update
            name: New lab name (optional)
            institution: New institution name (optional)
            pi_name: New PI name (optional)

        Returns:
            Dict with success status and details
        """
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Get existing lab
        lab_repo = repo_factory.labs
        lab = lab_repo.find_by_id(lab_id)
        if not lab:
            return {"success": False, "message": f"Lab '{lab_id}' not found"}

        # Apply updates
        if name is not None:
            lab.name = name
        if institution is not None:
            lab.institution = institution
        if pi_name is not None:
            lab.pi_name = pi_name

        # Save updated lab
        try:
            saved_lab = lab_repo.save(lab)
            return {
                "success": True,
                "message": "Lab updated successfully",
                "lab": saved_lab
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to update lab: {e}"}

    def update_user_profile(self, name: Optional[str] = None, organization: Optional[str] = None,
                            default_projects_dir: Optional[Path] = None,
                            default_shared_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Update current user's profile fields in SQL.

        Email-derived user id is treated as stable; email changes are not applied here.
        """
        if not self.is_user_configured():
            return {"success": False, "message": "No active user configured"}

        from .repository import get_repository_factory

        user_id = get_config("user.id", scope="user")
        db = self._get_database()
        repo_factory = get_repository_factory(db)
        user = repo_factory.users.find_by_id(user_id)
        if not user:
            return {"success": False, "message": "Active user not found"}

        # Apply updates
        if name is not None:
            user.name = name
        if organization is not None:
            user.organization = organization
        if default_projects_dir is not None:
            user.default_projects_dir = default_projects_dir
        if default_shared_dir is not None:
            user.default_shared_dir = default_shared_dir
        user.updated_at = datetime.now()

        saved = repo_factory.users.save(user)
        return {"success": True, "user": saved}

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
                user_dto.default_projects_dir = Path.home() / "Desktop" / "MUS1" / "Projects"
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
        db = self._get_database()
        repo_factory = get_repository_factory(db)
        saved_user = repo_factory.users.save(user_entity)

        # Save configuration: only the active user id is persisted in ConfigManager
        set_config("user.id", user_id, scope="user")

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
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Get current user ID to filter labs by creator
        user_id = get_config("user.id", scope="user")
        if user_id:
            labs = repo_factory.labs.find_for_user(user_id)
        else:
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
        from .repository import get_repository_factory

        db = self._get_database()
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
        from .repository import get_repository_factory

        lab_entity = Lab(
            id=lab_dto.id,
            name=lab_dto.name,
            institution=lab_dto.institution,
            pi_name=lab_dto.pi_name,
            creator_id=lab_dto.creator_id,
            created_at=lab_dto.created_at or datetime.now()
        )

        # Save lab to SQL database and add creator membership (admin)
        db = self._get_database()
        repo_factory = get_repository_factory(db)
        saved_lab = repo_factory.labs.save(lab_entity)
        try:
            repo_factory.labs.add_member(lab_dto.id, lab_dto.creator_id, role="admin")
        except Exception:
            pass

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
        from .repository import get_repository_factory

        db = self._get_database()
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

    def get_lab_members(self, lab_id: str) -> Dict[str, Any]:
        """
        Get all members of a lab with their user details.

        Args:
            lab_id: The lab ID

        Returns:
            Dict with members list and metadata
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found",
                "members": []
            }

        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Get members
        members = repo_factory.labs.list_members(lab_id)
        members_with_details = []

        for member in members:
            user = repo_factory.users.find_by_id(member['user_id'])
            if user:
                members_with_details.append({
                    'user_id': user.id,
                    'email': user.email,
                    'name': user.name,
                    'role': member['role'],
                    'joined_at': member['joined_at']
                })

        return {
            "success": True,
            "members": members_with_details
        }

    def add_lab_member(self, lab_id: str, user_email: str, role: str = "member") -> Dict[str, Any]:
        """
        Add a user as a member of a lab.

        Args:
            lab_id: The lab ID
            user_email: Email of the user to add
            role: Role for the user (admin, member)

        Returns:
            Dict with success status
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found"
            }

        if role not in ["admin", "member"]:
            return {
                "success": False,
                "message": "Invalid role. Must be 'admin' or 'member'"
            }

        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Find user by email
        user = repo_factory.users.find_by_email(user_email)
        if not user:
            return {
                "success": False,
                "message": f"User with email '{user_email}' not found"
            }

        # Check if already a member
        existing_members = repo_factory.labs.list_members(lab_id)
        if any(m['user_id'] == user.id for m in existing_members):
            return {
                "success": False,
                "message": f"User '{user_email}' is already a member of this lab"
            }

        # Add member
        repo_factory.labs.add_member(lab_id, user.id, role, datetime.now())

        return {
            "success": True,
            "message": f"User '{user_email}' added as {role} to lab",
            "user_id": user.id
        }

    def remove_lab_member(self, lab_id: str, user_id: str) -> Dict[str, Any]:
        """
        Remove a user from a lab.

        Args:
            lab_id: The lab ID
            user_id: The user ID to remove

        Returns:
            Dict with success status
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found"
            }

        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Verify user exists
        user = repo_factory.users.find_by_id(user_id)
        if not user:
            return {
                "success": False,
                "message": f"User '{user_id}' not found"
            }

        # Don't allow removing the creator
        lab = repo_factory.labs.find_by_id(lab_id)
        if lab and lab.creator_id == user_id:
            return {
                "success": False,
                "message": "Cannot remove the lab creator"
            }

        # Remove member
        success = repo_factory.labs.remove_member(lab_id, user_id)

        if success:
            return {
                "success": True,
                "message": f"User '{user.email}' removed from lab"
            }
        else:
            return {
                "success": False,
                "message": f"User '{user.email}' was not a member of this lab"
            }

    def get_lab_colonies(self, lab_id: str) -> Dict[str, Any]:
        """
        Get all colonies for a lab.

        Args:
            lab_id: The lab ID

        Returns:
            Dict with colonies list
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found",
                "colonies": []
            }

        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        colonies = repo_factory.colonies.find_by_lab(lab_id)

        return {
            "success": True,
            "colonies": [{
                "id": c.id,
                "name": c.name,
                "genotype_of_interest": c.genotype_of_interest,
                "background_strain": c.background_strain,
                "date_added": c.date_added.isoformat()
            } for c in colonies]
        }

    def get_colony_subjects(self, colony_id: str) -> Dict[str, Any]:
        """
        Get all subjects for a colony.

        Args:
            colony_id: The colony ID

        Returns:
            Dict with subjects list
        """
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        colony = repo_factory.colonies.find_by_id(colony_id)
        if not colony:
            return {
                "success": False,
                "message": f"Colony '{colony_id}' not found",
                "subjects": []
            }

        subjects = repo_factory.subjects.find_by_colony(colony_id)

        return {
            "success": True,
            "subjects": [{
                "id": s.id,
                "sex": s.sex.value if s.sex else "",
                "genotype": s.genotype,
                "birth_date": s.birth_date.isoformat() if s.birth_date else None,
                "date_added": s.date_added.isoformat()
            } for s in subjects]
        }

    def add_subject_to_colony(self, subject_id: str, colony_id: str) -> Dict[str, Any]:
        """
        Add a subject to a colony by updating its colony_id.

        Args:
            subject_id: The subject ID
            colony_id: The colony ID

        Returns:
            Dict with success status
        """
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Verify subject exists
        subject = repo_factory.subjects.find_by_id(subject_id)
        if not subject:
            return {
                "success": False,
                "message": f"Subject '{subject_id}' not found"
            }

        # Verify colony exists
        colony = repo_factory.colonies.find_by_id(colony_id)
        if not colony:
            return {
                "success": False,
                "message": f"Colony '{colony_id}' not found"
            }

        # Update subject's colony_id
        subject.colony_id = colony_id
        saved_subject = repo_factory.subjects.save(subject)

        return {
            "success": True,
            "message": f"Subject '{subject_id}' added to colony '{colony_id}'",
            "subject": saved_subject
        }

    def remove_subject_from_colony(self, subject_id: str) -> Dict[str, Any]:
        """
        Remove a subject from its current colony by setting colony_id to None.

        Args:
            subject_id: The subject ID

        Returns:
            Dict with success status
        """
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        # Verify subject exists
        subject = repo_factory.subjects.find_by_id(subject_id)
        if not subject:
            return {
                "success": False,
                "message": f"Subject '{subject_id}' not found"
            }

        old_colony_id = subject.colony_id
        subject.colony_id = None
        saved_subject = repo_factory.subjects.save(subject)

        return {
            "success": True,
            "message": f"Subject '{subject_id}' removed from colony '{old_colony_id}'",
            "subject": saved_subject
        }

    def create_colony(self, lab_id: str, colony_dto: ColonyDTO) -> Dict[str, Any]:
        """
        Create a new colony in a lab.

        Args:
            lab_id: The lab ID
            colony_dto: Colony data

        Returns:
            Dict with success status
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found"
            }

        colony_dto.lab_id = lab_id  # Ensure colony belongs to the lab
        return self.add_colony_to_lab(colony_dto)

    def update_colony(self, colony_id: str, name: Optional[str] = None,
                     genotype_of_interest: Optional[str] = None,
                     background_strain: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing colony.

        Args:
            colony_id: The colony ID
            name: New name (optional)
            genotype_of_interest: New genotype (optional)
            background_strain: New background strain (optional)

        Returns:
            Dict with success status
        """
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        colony = repo_factory.colonies.find_by_id(colony_id)
        if not colony:
            return {
                "success": False,
                "message": f"Colony '{colony_id}' not found"
            }

        # Apply updates
        if name is not None:
            colony.name = name
        if genotype_of_interest is not None:
            colony.genotype_of_interest = genotype_of_interest
        if background_strain is not None:
            colony.background_strain = background_strain

        saved_colony = repo_factory.colonies.save(colony)

        return {
            "success": True,
            "message": "Colony updated successfully",
            "colony": saved_colony
        }

    def get_lab_projects(self, lab_id: str) -> Dict[str, Any]:
        """
        Get all projects registered with a lab.

        Args:
            lab_id: The lab ID

        Returns:
            Dict with projects list
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found",
                "projects": []
            }

        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        projects = repo_factory.labs.get_projects(lab_id)

        return {
            "success": True,
            "projects": projects
        }

    def add_lab_project(self, lab_id: str, project_name: str, project_path: str) -> Dict[str, Any]:
        """
        Register a project with a lab.

        Args:
            lab_id: The lab ID
            project_name: Name of the project
            project_path: Path to the project

        Returns:
            Dict with success status
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found"
            }

        from pathlib import Path
        from .repository import get_repository_factory

        db = self._get_database()
        repo_factory = get_repository_factory(db)

        project_path_obj = Path(project_path)

        # Validate project path exists and has mus1.db
        if not project_path_obj.exists():
            return {
                "success": False,
                "message": f"Project path does not exist: {project_path}"
            }

        if not (project_path_obj / "mus1.db").exists():
            return {
                "success": False,
                "message": f"Invalid project directory (missing mus1.db): {project_path}"
            }

        # Check if project is already registered
        existing_projects = repo_factory.labs.get_projects(lab_id)
        if any(p['name'] == project_name for p in existing_projects):
            return {
                "success": False,
                "message": f"Project '{project_name}' is already registered with this lab"
            }

        # Add project to lab
        repo_factory.labs.add_project(lab_id, project_name, project_path_obj, datetime.now())

        return {
            "success": True,
            "message": f"Project '{project_name}' registered with lab"
        }

    def remove_lab_project(self, lab_id: str, project_name: str) -> Dict[str, Any]:
        """
        Remove a project registration from a lab.

        Args:
            lab_id: The lab ID
            project_name: Name of the project to remove

        Returns:
            Dict with success status
        """
        if not self.lab_exists(lab_id):
            return {
                "success": False,
                "message": f"Lab '{lab_id}' not found"
            }

        from .schema import LabProjectModel

        db = self._get_database()

        # Remove project association
        with db.get_session() as session:
            result = session.query(LabProjectModel).filter(
                LabProjectModel.lab_id == lab_id,
                LabProjectModel.name == project_name
            ).delete()
            session.commit()

            if result > 0:
                return {
                    "success": True,
                    "message": f"Project '{project_name}' removed from lab"
                }
            else:
                return {
                    "success": False,
                    "message": f"Project '{project_name}' was not registered with this lab"
                }

    # ===========================================
    # LAB STORAGE ROOT MANAGEMENT
    # ===========================================

    def set_lab_storage_root(self, lab_id: str, path: Path) -> Dict[str, Any]:
        """Set a per-lab storage root. Does not affect app config/logging roots."""
        if not lab_id:
            return {"success": False, "message": "lab_id is required"}
        if not path:
            return {"success": False, "message": "path is required"}
        try:
            cfg_set_lab_root(lab_id, path)
            return {"success": True, "lab_id": lab_id, "path": str(path)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def set_lab_sharing_preferences(self, lab_id: str, mode: str) -> Dict[str, Any]:
        """Set lab sharing mode: 'always_on' or 'peer_hosted'."""
        if not lab_id:
            return {"success": False, "message": "lab_id is required"}
        try:
            set_lab_sharing_mode(lab_id, mode)
            return {"success": True, "lab_id": lab_id, "mode": mode}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_lab_library_online_status(self, lab_id: str) -> Dict[str, Any]:
        """Return computed online/offline status for the lab shared library."""
        if not lab_id:
            return {"success": False, "message": "lab_id is required"}
        status = get_lab_library_status(lab_id)
        status.update({"success": True, "mode": get_lab_sharing_mode(lab_id)})
        return status

    def designate_shared_folder(self, path: Path, ensure_exists: bool = True, verify_permissions: bool = True) -> Dict[str, Any]:
        """Designate and validate a shared folder accessible to lab workers/compute.

        This sets the global shared storage root (storage.shared_root) and performs
        optional creation and write-permission checks.
        """
        try:
            if ensure_exists and not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            if not path.is_dir():
                return {"success": False, "message": f"Path is not a directory: {path}"}
            if verify_permissions:
                probe = path / ".mus1_write_test"
                probe.write_text("ok")
                probe.unlink(missing_ok=True)
            set_config("storage.shared_root", str(path), scope="user")
            set_config("storage.shared_setup_date", datetime.now().isoformat(), scope="user")
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def wipe_existing_configuration(self) -> Dict[str, Any]:
        """Dangerous: remove current MUS1 configuration directory contents.

        Deletes config.db and related files under the resolved MUS1 root. Caller must
        present a confirmation UI. Best-effort; returns details of what was removed.
        """
        try:
            from .config_manager import resolve_mus1_root
            root = resolve_mus1_root()
            removed: List[str] = []
            for rel in ["config/config.db", "config/root_pointer.json", "logs/mus1.log"]:
                p = root / rel
                if p.exists():
                    try:
                        p.unlink()
                        removed.append(str(p))
                    except Exception:
                        pass
            return {"success": True, "removed": removed}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ===========================================
    # LAB LIBRARY BROWSING (Recordings/Subjects)
    # ===========================================

    def get_lab_subjects(self, lab_id: str) -> Dict[str, Any]:
        """Return all subjects for a lab by aggregating subjects from its colonies."""
        try:
            from .repository import get_repository_factory
            db = self._get_database()
            repos = get_repository_factory(db)
            colonies = repos.colonies.find_by_lab(lab_id)
            subjects: List[Dict[str, Any]] = []
            for c in colonies:
                subs = repos.subjects.find_by_colony(c.id)
                for s in subs:
                    subjects.append({
                        "id": s.id,
                        "colony_id": s.colony_id,
                        "sex": getattr(s.sex, "value", str(s.sex)) if getattr(s, "sex", None) else None,
                        "genotype": getattr(s, "genotype", None),
                        "birth_date": getattr(s, "birth_date", None),
                        "date_added": getattr(s, "date_added", None),
                    })
            return {"success": True, "subjects": subjects}
        except Exception as e:
            return {"success": False, "message": str(e), "subjects": []}

    def list_lab_recordings(self, lab_id: Optional[str] = None, extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        """List video recordings under the lab storage root (or global shared storage).

        Returns a list of absolute Paths (as strings) to candidate video files.
        """
        try:
            roots: List[Path] = []
            # Prefer per-lab storage root when provided
            if lab_id:
                from .config_manager import get_lab_storage_root
                lab_root = get_lab_storage_root(lab_id)
                if lab_root and lab_root.exists():
                    roots.append(lab_root)
            # Fallback to global shared storage root
            if not roots:
                shared = self.get_shared_storage_path()
                if shared and shared.exists():
                    roots.append(shared)
            if not roots:
                return {"success": True, "recordings": []}

            # Use BaseScanner to discover videos
            from .scanners.video_discovery import get_scanner
            scanner = get_scanner()
            exts = list(extensions) if extensions else None
            paths: List[str] = []
            for root in roots:
                for p, _h in scanner.iter_videos([root], extensions=exts, recursive=True, excludes=None, progress_cb=None):
                    paths.append(str(p))
            # De-duplicate while preserving order
            seen = set()
            ordered = []
            for p in paths:
                if p not in seen:
                    ordered.append(p)
                    seen.add(p)
            return {"success": True, "recordings": ordered}
        except Exception as e:
            return {"success": False, "message": str(e), "recordings": []}

    # ===========================================
    # WORKERS MANAGEMENT (Wizard helper)
    # ===========================================

    def add_worker(self, name: str, ssh_alias: str, role: Optional[str] = None, provider: str = "ssh") -> Dict[str, Any]:
        """Persist a worker into the SQL workers table.

        Provider supports: ssh, wsl, local, ssh-wsl.
        """
        from .repository import get_repository_factory
        from .metadata import Worker, WorkerProvider

        db = self._get_database()
        repos = get_repository_factory(db)
        try:
            worker = Worker(
                name=name,
                ssh_alias=ssh_alias,
                role=role,
                provider=WorkerProvider(provider),
                os_type=None,
            )
            saved = repos.workers.save(worker)
            return {"success": True, "worker": saved}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ===========================================
    # SETUP STATUS & WORKFLOW
    # ===========================================

    def get_setup_status(self) -> SetupStatusDTO:
        """Get comprehensive setup status."""
        labs = self.get_labs()
        projects_count = sum(len(lab.get("projects", [])) for lab in labs.values())

        # Resolve user name from SQL when configured
        user_name = None
        if self.is_user_configured():
            profile = self.get_user_profile()
            user_name = profile.name if profile else None

        return SetupStatusDTO(
            mus1_root_configured=self.is_mus1_root_configured(),
            mus1_root_path=get_config("mus1.root_path"),
            user_configured=user_name is not None,
            user_name=user_name,
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
        from typing import TypedDict, List as _List
        class WorkflowResult(TypedDict):
            success: bool
            steps_completed: _List[str]
            errors: _List[str]

        results: WorkflowResult = {
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

        from typing import cast
        return cast(Dict[str, Any], results)


# ===========================================
# UTILITY FUNCTIONS
# ===========================================

def get_setup_service() -> SetupService:
    """Get the global setup service instance."""
    return SetupService()
