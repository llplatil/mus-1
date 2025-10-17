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
    """Simplified service for discovering and resolving project paths.

    Implemented as a singleton for consistent global project discovery.
    """
    # The singleton instance
    _instance = None

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = ProjectDiscoveryService()
        return cls._instance

    def __init__(self):
        """Initialize the project discovery service."""
        # Only allow initialization if no instance exists
        if ProjectDiscoveryService._instance is not None:
            raise RuntimeError("ProjectDiscoveryService is a singleton! Use ProjectDiscoveryService.get_instance() instead.")
        ProjectDiscoveryService._instance = self

    def find_project_path(self, project_name: str) -> Optional[Path]:
        """
        Find the full path for a project by name.

        Search order:
        1. Check lab-registered projects (authoritative)
        2. Check user-configured default projects directory

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
        # Priority: lab-specific root (if configured), else user default; no global shared scan
        if lab_id:
            lab_root = get_lab_storage_root(lab_id)
            if lab_root and lab_root.exists():
                return lab_root
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            return Path(default_dir)

        # Fallback to current directory
        return Path.cwd() / "projects"

    def discover_existing_projects(self) -> List[Path]:
        """
        Discover all existing projects from configured locations.

        Priority:
        1. Lab-registered projects (authoritative)
        2. Filesystem scan of user default directory

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
    """Get the global project discovery service instance (singleton)."""
    return ProjectDiscoveryService.get_instance()

# Keep for backward compatibility but mark as deprecated
_project_discovery_service = None
