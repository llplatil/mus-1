"""
Lab-level configuration management for MUS1.

Consolidates shared resources across projects within a lab:
- Compute workers (SSH/local/WSL)
- Credentials for remote access
- Common scan targets
- Master subject registry
- Master experiment types
- 3rd party software installations
- Associated projects
"""
from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from .metadata import WorkerEntry, ScanTarget, SubjectMetadata, ExperimentMetadata, Sex


class LabMetadata(BaseModel):
    """Lab identification and metadata."""
    name: str = Field(..., description="Human-readable lab name")
    description: str = Field("", description="Lab description")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    contact: Optional[str] = Field(None, description="Lab contact information")
    institution: Optional[str] = Field(None, description="Institution/organization")


class LabCredentials(BaseModel):
    """Lab-level SSH credentials."""
    alias: str = Field(..., description="SSH alias name")
    user: Optional[str] = Field(None, description="Username")
    identity_file: Optional[str] = Field(None, description="Path to SSH private key")
    description: Optional[str] = Field(None, description="Description of this credential")


class LabSoftwareInstall(BaseModel):
    """3rd party software installation record."""
    name: str = Field(..., description="Software name")
    version: Optional[str] = Field(None, description="Version installed")
    path: Optional[str] = Field(None, description="Installation path")
    environment: Dict[str, str] = Field(default_factory=dict, description="Required environment variables")
    description: Optional[str] = Field(None, description="Installation notes")


class LabConfig(BaseModel):
    """Complete lab-level configuration."""
    metadata: LabMetadata
    workers: List[WorkerEntry] = Field(default_factory=list, description="Shared compute workers")
    credentials: Dict[str, LabCredentials] = Field(default_factory=dict, description="SSH credentials by alias")
    scan_targets: List[ScanTarget] = Field(default_factory=list, description="Common scan targets")
    master_subjects: Dict[str, SubjectMetadata] = Field(default_factory=dict, description="Master subject registry")
    master_experiment_types: List[str] = Field(default_factory=list, description="Common experiment types")
    software_installs: Dict[str, LabSoftwareInstall] = Field(default_factory=dict, description="3rd party software")
    associated_projects: Set[str] = Field(default_factory=set, description="Paths to associated projects")
    config_version: str = Field("1.0", description="Configuration schema version")


class LabManager:
    """Manages lab-level configuration and shared resources."""

    def __init__(self):
        self._lab_config: Optional[LabConfig] = None
        self._config_path: Optional[Path] = None

    @staticmethod
    def _get_default_lab_dir() -> Path:
        """Get the default directory for lab configurations."""
        if hasattr(Path, 'home'):
            base = Path.home()
        else:
            # Fallback for older Python
            import os
            base = Path(os.path.expanduser("~"))

        lab_dir = base / ".mus1" / "labs"
        lab_dir.mkdir(parents=True, exist_ok=True)
        return lab_dir

    def create_lab(
        self,
        name: str,
        lab_id: Optional[str] = None,
        description: str = "",
        config_dir: Optional[Path] = None
    ) -> LabConfig:
        """Create a new lab configuration."""
        if lab_id is None:
            # Generate simple ID from name
            lab_id = name.lower().replace(" ", "_").replace("-", "_")

        config_dir = config_dir or self._get_default_lab_dir()
        config_path = config_dir / f"{lab_id}.yaml"

        if config_path.exists():
            raise FileExistsError(f"Lab configuration already exists: {config_path}")

        lab_config = LabConfig(
            metadata=LabMetadata(
                name=name,
                description=description
            )
        )

        # Save the configuration
        self._save_lab_config(lab_config, config_path)
        self._lab_config = lab_config
        self._config_path = config_path

        return lab_config

    def load_lab(self, lab_id_or_path: str, config_dir: Optional[Path] = None) -> LabConfig:
        """Load an existing lab configuration."""
        config_dir = config_dir or self._get_default_lab_dir()

        # Try as full path first
        config_path = Path(lab_id_or_path)
        if not config_path.exists():
            # Try as lab ID
            config_path = config_dir / f"{lab_id_or_path}.yaml"
            if not config_path.exists():
                config_path = config_dir / f"{lab_id_or_path}.json"

        if not config_path.exists():
            raise FileNotFoundError(f"Lab configuration not found: {lab_id_or_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix.lower() == '.yaml':
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        lab_config = LabConfig(**data)
        self._lab_config = lab_config
        self._config_path = config_path

        return lab_config

    def save_lab(self) -> None:
        """Save the current lab configuration."""
        if self._lab_config is None or self._config_path is None:
            raise RuntimeError("No lab configuration loaded")

        self._lab_config.metadata.updated_at = datetime.now()
        self._save_lab_config(self._lab_config, self._config_path)

    def _save_lab_config(self, config: LabConfig, path: Path) -> None:
        """Save lab configuration to file."""
        data = config.dict()

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            if path.suffix.lower() == '.yaml':
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, f, indent=2, default=str)

    def list_available_labs(self, config_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        """List all available lab configurations."""
        config_dir = config_dir or self._get_default_lab_dir()
        labs = []

        for config_file in config_dir.glob("*.yaml"):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    labs.append({
                        "id": config_file.stem,
                        "name": data.get("metadata", {}).get("name", config_file.stem),
                        "description": data.get("metadata", {}).get("description", ""),
                        "path": str(config_file),
                        "projects": len(data.get("associated_projects", []))
                    })
            except Exception:
                continue

        # Also check JSON files
        for config_file in config_dir.glob("*.json"):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    labs.append({
                        "id": config_file.stem,
                        "name": data.get("metadata", {}).get("name", config_file.stem),
                        "description": data.get("metadata", {}).get("description", ""),
                        "path": str(config_file),
                        "projects": len(data.get("associated_projects", []))
                    })
            except Exception:
                continue

        return sorted(labs, key=lambda x: x["name"])

    def associate_project(self, project_path: Path) -> None:
        """Associate a project with this lab."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        project_path = project_path.resolve()
        self._lab_config.associated_projects.add(str(project_path))
        self.save_lab()

    def disassociate_project(self, project_path: Path) -> None:
        """Remove project association from this lab."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        project_path = project_path.resolve()
        self._lab_config.associated_projects.discard(str(project_path))
        self.save_lab()

    def get_lab_projects(self) -> List[Path]:
        """Get all projects associated with this lab."""
        if self._lab_config is None:
            return []

        projects = []
        for project_path_str in self._lab_config.associated_projects:
            project_path = Path(project_path_str)
            if project_path.exists() and (project_path / "project_state.json").exists():
                projects.append(project_path)

        return projects

    # Worker management
    def add_worker(self, worker: WorkerEntry) -> None:
        """Add a worker to the lab configuration."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        # Check for duplicate names
        for existing in self._lab_config.workers:
            if existing.name == worker.name:
                raise ValueError(f"Worker with name '{worker.name}' already exists")

        self._lab_config.workers.append(worker)
        self.save_lab()

    def remove_worker(self, worker_name: str) -> bool:
        """Remove a worker by name. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        original_count = len(self._lab_config.workers)
        self._lab_config.workers = [w for w in self._lab_config.workers if w.name != worker_name]

        if len(self._lab_config.workers) < original_count:
            self.save_lab()
            return True
        return False

    # Credential management
    def add_credential(self, alias: str, user: Optional[str] = None,
                      identity_file: Optional[str] = None, description: Optional[str] = None) -> None:
        """Add SSH credentials to the lab configuration."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        cred = LabCredentials(
            alias=alias,
            user=user,
            identity_file=identity_file,
            description=description
        )
        self._lab_config.credentials[alias] = cred
        self.save_lab()

    def remove_credential(self, alias: str) -> bool:
        """Remove SSH credentials by alias. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if alias in self._lab_config.credentials:
            del self._lab_config.credentials[alias]
            self.save_lab()
            return True
        return False

    # Scan target management
    def add_scan_target(self, target: ScanTarget) -> None:
        """Add a scan target to the lab configuration."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        # Check for duplicate names
        for existing in self._lab_config.scan_targets:
            if existing.name == target.name:
                raise ValueError(f"Scan target with name '{target.name}' already exists")

        self._lab_config.scan_targets.append(target)
        self.save_lab()

    def remove_scan_target(self, target_name: str) -> bool:
        """Remove a scan target by name. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        original_count = len(self._lab_config.scan_targets)
        self._lab_config.scan_targets = [t for t in self._lab_config.scan_targets if t.name != target_name]

        if len(self._lab_config.scan_targets) < original_count:
            self.save_lab()
            return True
        return False

    # Master subject management
    def add_master_subject(self, subject: SubjectMetadata) -> None:
        """Add a subject to the master registry."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if subject.id in self._lab_config.master_subjects:
            raise ValueError(f"Subject with ID '{subject.id}' already exists in master registry")

        self._lab_config.master_subjects[subject.id] = subject
        self.save_lab()

    def remove_master_subject(self, subject_id: str) -> bool:
        """Remove a subject from the master registry. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if subject_id in self._lab_config.master_subjects:
            del self._lab_config.master_subjects[subject_id]
            self.save_lab()
            return True
        return False

    def get_master_subject(self, subject_id: str) -> Optional[SubjectMetadata]:
        """Get a subject from the master registry."""
        if self._lab_config is None:
            return None
        return self._lab_config.master_subjects.get(subject_id)

    # Software management
    def add_software_install(self, name: str, version: Optional[str] = None,
                           path: Optional[str] = None, environment: Optional[Dict[str, str]] = None,
                           description: Optional[str] = None) -> None:
        """Add a software installation record."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        software = LabSoftwareInstall(
            name=name,
            version=version,
            path=path,
            environment=environment or {},
            description=description
        )
        self._lab_config.software_installs[name] = software
        self.save_lab()

    def remove_software_install(self, name: str) -> bool:
        """Remove a software installation record. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if name in self._lab_config.software_installs:
            del self._lab_config.software_installs[name]
            self.save_lab()
            return True
        return False

    # Property access
    @property
    def current_lab(self) -> Optional[LabConfig]:
        """Get the currently loaded lab configuration."""
        return self._lab_config

    @property
    def current_lab_path(self) -> Optional[Path]:
        """Get the path to the currently loaded lab configuration."""
        return self._config_path
