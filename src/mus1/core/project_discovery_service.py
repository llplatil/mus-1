"""
Project Discovery Service - Simplified project location resolution.

This service provides simple, deterministic project discovery using
a clear priority chain and single source of truth.
"""

from pathlib import Path
from typing import Optional, List
from .config_manager import get_config
from .config_manager import get_lab_storage_root


class ProjectDiscoveryService:
    """Simplified service for discovering and resolving project paths."""

    def find_project_path(self, project_name: str) -> Optional[Path]:
        """
        Find the full path for a project by name.

        Search order:
        1. Check lab configurations (single source of truth)
        2. Check user-configured default projects directory
        3. Check shared storage directory

        Args:
            project_name: Name of the project to find

        Returns:
            Path to the project directory, or None if not found
        """
        # Priority 1: Lab configurations (single source of truth)
        from .setup_service import get_setup_service
        setup_service = get_setup_service()
        labs = setup_service.get_labs()  # Now uses SQL data
        for lab_config in labs.values():
            projects = lab_config.get("projects", [])
            for project in projects:
                if project["name"] == project_name:
                    project_path = Path(project["path"])
                    if project_path.exists() and (project_path / "mus1.db").exists():
                        return project_path
                    # If lab-registered path doesn't exist, log warning but continue searching
                    import logging
                    logging.getLogger("mus1").warning(
                        f"Lab configuration has stale path for project '{project_name}': {project_path}"
                    )

        # Priority 2: User-configured default directory
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            project_path = Path(default_dir) / project_name
            if project_path.exists() and (project_path / "mus1.db").exists():
                return project_path

        # Priority 3: Shared storage root (scan entire root, not just Projects/)
        shared_root = get_config("storage.shared_root")
        if shared_root:
            shared_path = Path(shared_root)
            # First check if it's directly in shared root
            project_path = shared_path / project_name
            if project_path.exists() and (project_path / "mus1.db").exists():
                return project_path
            # Then check Projects subdirectory for backward compatibility
            project_path = shared_path / "Projects" / project_name
            if project_path.exists() and (project_path / "mus1.db").exists():
                return project_path

        return None

    def get_project_root_for_dialog(self, lab_id: Optional[str] = None) -> Path:
        """
        Get the appropriate project root directory for project selection dialogs.

        This is used as a hint for where to start browsing, but the dialog
        discovers projects from all configured locations.

        Args:
            lab_id: Optional lab identifier to bias toward a lab-specific root

        Returns:
            Path to use as the root for project dialogs
        """
        # Priority: lab-specific root, user default, shared storage root, then local projects
        if lab_id:
            lab_root = get_lab_storage_root(lab_id)
            if lab_root and lab_root.exists():
                return lab_root
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            return Path(default_dir)

        shared_root = get_config("storage.shared_root")
        if shared_root:
            return Path(shared_root)  # Return shared root directly, not Projects subdirectory

        # Fallback to current directory
        return Path.cwd() / "projects"

    def discover_existing_projects(self) -> List[Path]:
        """
        Discover all existing projects from configured locations.

        Priority:
        1. Lab-registered projects (most authoritative)
        2. Filesystem scan of user default directory
        3. Filesystem scan of shared storage root (not Projects subdirectory)
        4. Filesystem scan of lab-specific roots (if configured)

        Returns:
            List of project directory paths
        """
        projects = []

        # Priority 1: Lab configurations (single source of truth)
        from .setup_service import get_setup_service
        setup_service = get_setup_service()
        labs = setup_service.get_labs()  # Now uses SQL data
        for lab_config in labs.values():
            lab_projects = lab_config.get("projects", [])
            for project in lab_projects:
                project_path = Path(project["path"])
                if (project_path.exists() and
                    project_path not in projects and
                    (project_path / "mus1.db").exists()):
                    projects.append(project_path)

        # Priority 2: User default directory
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            self._discover_projects_in_directory(Path(default_dir), projects)

        # Priority 3: Shared storage root (scan entire shared root, not just Projects/)
        shared_root = get_config("storage.shared_root")
        if shared_root:
            self._discover_projects_in_directory(Path(shared_root), projects)

        # Priority 4: Lab-specific roots
        try:
            from .setup_service import get_setup_service
            labs = get_setup_service().get_labs()
            for lab_id in labs.keys():
                lab_root = get_lab_storage_root(lab_id)
                if lab_root:
                    self._discover_projects_in_directory(lab_root, projects)
        except Exception:
            pass

        # Priority 5: Local projects directory (fallback for unregistered projects)
        try:
            from .config_manager import resolve_mus1_root
            mus1_root = resolve_mus1_root()
            local_projects_dir = mus1_root / "projects"
            self._discover_projects_in_directory(local_projects_dir, projects)
        except Exception:
            pass

        return projects

    def _discover_projects_in_directory(self, directory: Path, projects: List[Path]):
        """Discover projects in a specific directory."""
        if not directory.exists():
            return

        for item in directory.iterdir():
            if (item.is_dir() and
                item not in projects and
                (item / "mus1.db").exists()):
                projects.append(item)


# Global service instance
_project_discovery_service = None

def get_project_discovery_service() -> ProjectDiscoveryService:
    """Get the global project discovery service instance."""
    global _project_discovery_service
    if _project_discovery_service is None:
        _project_discovery_service = ProjectDiscoveryService()
    return _project_discovery_service
