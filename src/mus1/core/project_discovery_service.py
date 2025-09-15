"""
Project Discovery Service - Simplified project location resolution.

This service provides simple, deterministic project discovery using
a clear priority chain and single source of truth.
"""

from pathlib import Path
from typing import Optional, List
from .config_manager import get_config


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

        # Priority 2: User-configured default directory
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            project_path = Path(default_dir) / project_name
            if project_path.exists() and (project_path / "mus1.db").exists():
                return project_path

        # Priority 3: Shared storage
        shared_root = get_config("storage.shared_root")
        if shared_root:
            project_path = Path(shared_root) / "Projects" / project_name
            if project_path.exists() and (project_path / "mus1.db").exists():
                return project_path

        return None

    def get_project_root_for_dialog(self) -> Path:
        """
        Get the appropriate project root directory for project selection dialogs.

        Returns:
            Path to use as the root for project dialogs
        """
        # Priority: user-configured default, then shared storage, then fallback
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            return Path(default_dir)

        shared_root = get_config("storage.shared_root")
        if shared_root:
            return Path(shared_root) / "Projects"

        # Fallback to current directory
        return Path.cwd() / "projects"

    def discover_existing_projects(self) -> List[Path]:
        """
        Discover all existing projects from configured locations.

        Returns:
            List of project directory paths
        """
        projects = []

        # Check lab configurations first
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

        # Check user default directory
        default_dir = get_config("user.default_projects_dir")
        if default_dir:
            self._discover_projects_in_directory(Path(default_dir), projects)

        # Check shared storage
        shared_root = get_config("storage.shared_root")
        if shared_root:
            shared_projects_dir = Path(shared_root) / "Projects"
            self._discover_projects_in_directory(shared_projects_dir, projects)

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
