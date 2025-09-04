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
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from .metadata import WorkerEntry, ScanTarget, SubjectMetadata, ExperimentMetadata, Sex, InheritancePattern


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


class LabSharedStorage(BaseModel):
    """Shared storage configuration for lab."""
    mount_point: Optional[str] = Field(None, description="Expected mount point path (e.g., /Volumes/CuSSD3)")
    volume_name: Optional[str] = Field(None, description="Volume name for detection (e.g., CuSSD3)")
    projects_root: str = Field("mus1_projects", description="Directory name for projects on shared storage")
    media_root: str = Field("mus1_media", description="Directory name for media/data on shared storage")
    enabled: bool = Field(True, description="Whether shared storage is enabled for this lab")
    auto_detect: bool = Field(True, description="Attempt automatic detection of shared storage")


class LabGenotype(BaseModel):
    """Genotype configuration for a specific gene."""
    model_config = {"use_enum_values": True}

    gene_name: str = Field(..., description="Gene name (e.g., ATP7B)")
    inheritance_pattern: InheritancePattern = Field(default=InheritancePattern.RECESSIVE, description="Inheritance pattern")
    alleles: List[str] = Field(default_factory=lambda: ["WT", "Het", "KO"], description="Available alleles")
    is_mutually_exclusive: bool = Field(True, description="Whether an animal can only have one allele")
    date_added: datetime = Field(default_factory=datetime.now)

    def validate_allele(self, allele: str) -> bool:
        """Check if an allele is valid for this genotype."""
        return allele in self.alleles


class LabConfig(BaseModel):
    """Complete lab-level configuration."""
    metadata: LabMetadata
    workers: List[WorkerEntry] = Field(default_factory=list, description="Shared compute workers")
    credentials: Dict[str, LabCredentials] = Field(default_factory=dict, description="SSH credentials by alias")
    scan_targets: List[ScanTarget] = Field(default_factory=list, description="Common scan targets")
    master_subjects: Dict[str, SubjectMetadata] = Field(default_factory=dict, description="Master subject registry")
    master_experiment_types: List[str] = Field(default_factory=list, description="Common experiment types")
    tracked_experiment_types: Set[str] = Field(default_factory=set, description="Experiment types tracked by this lab")
    tracked_treatments: Set[str] = Field(default_factory=set, description="Treatment names tracked by this lab")
    genotypes: Dict[str, LabGenotype] = Field(default_factory=dict, description="Lab genotype configurations by gene name")
    tracked_genotypes: Set[str] = Field(default_factory=set, description="Gene names tracked by this lab")
    software_installs: Dict[str, LabSoftwareInstall] = Field(default_factory=dict, description="3rd party software")
    associated_projects: Set[str] = Field(default_factory=set, description="Paths to associated projects")
    shared_storage: LabSharedStorage = Field(default_factory=LabSharedStorage, description="Shared storage configuration")
    config_version: str = Field("1.0", description="Configuration schema version")


class LabManager:
    """Manages lab-level configuration and shared resources."""

    def __init__(self):
        self._lab_config: Optional[LabConfig] = None
        self._config_path: Optional[Path] = None
        self._auto_load_current_lab()

    def __getstate__(self):
        """Prepare object for pickling."""
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state):
        """Restore object from pickle and reload current lab."""
        self.__dict__.update(state)
        # After unpickling, try to reload the current lab
        if hasattr(self, '_config_path') and self._config_path and self._config_path.exists():
            try:
                # Try to reload the lab from the saved path
                lab_id = self._config_path.stem
                self.load_lab(lab_id)
                # Also save it as current lab for future sessions
                self._save_current_lab()
            except Exception as e:
                # If reload fails, clear the state
                self._lab_config = None
                self._config_path = None

    def get_labs_directory(self, custom_dir: Path | None = None) -> Path:
        """Return the directory where MUS1 lab configurations are stored.

        Precedence for the base directory is:
        1. custom_dir argument (used by CLI --config-dir)
        2. Environment variable MUS1_LABS_DIR if set
        3. Per-user config file (same location as projects/shared) key 'labs_root'
        4. User home default: ~/.mus1/labs

        The returned directory is created if it does not exist so callers can
        rely on its presence.
        """
        if custom_dir:
            base_dir = Path(custom_dir).expanduser().resolve()
        else:
            env_dir = os.environ.get("MUS1_LABS_DIR")
            if env_dir:
                base_dir = Path(env_dir).expanduser().resolve()
            else:
                # Fallback to per-user config (same scheme as projects/shared)
                try:
                    import platform
                    if platform.system() == "Darwin":
                        config_dir = Path.home() / "Library/Application Support/mus1"
                    elif os.name == "nt":
                        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
                        config_dir = Path(appdata) / "mus1"
                    else:
                        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
                        config_dir = Path(xdg) / "mus1"
                    yaml_path = config_dir / "config.yaml"
                    labs_root = None
                    if yaml_path.exists():
                        try:
                            with open(yaml_path, "r", encoding="utf-8") as f:
                                data = yaml.safe_load(f) or {}
                                lr = data.get("labs_root")
                                if lr:
                                    labs_root = Path(str(lr)).expanduser()
                        except Exception:
                            labs_root = None
                    if labs_root:
                        base_dir = Path(labs_root).expanduser().resolve()
                    else:
                        # Default to consistent user-local location
                        base_dir = (Path.home() / ".mus1" / "labs").expanduser().resolve()
                except Exception:
                    base_dir = (Path.home() / ".mus1" / "labs").expanduser().resolve()

        # Ensure existence
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _get_current_lab_file(self) -> Path:
        """Get the path to the file storing the current lab information."""
        labs_dir = self.get_labs_directory()
        return labs_dir / ".current_lab"

    def _auto_load_current_lab(self) -> None:
        """Automatically load the previously activated lab if it exists."""
        current_lab_file = self._get_current_lab_file()
        if current_lab_file.exists():
            try:
                with open(current_lab_file, 'r', encoding='utf-8') as f:
                    current_lab_id = f.read().strip()
                    if current_lab_id:
                        # Try to load the lab, but don't fail if it doesn't exist
                        try:
                            self.load_lab(current_lab_id)
                            # If the lab has shared storage enabled, try to activate it
                            if self._lab_config and self._lab_config.shared_storage.enabled:
                                mount_point = self.detect_shared_storage_mount()
                                if mount_point:
                                    # Set environment variables for shared storage
                                    os.environ["MUS1_SHARED_STORAGE_MOUNT"] = str(mount_point)
                                    os.environ["MUS1_ACTIVE_LAB"] = self._lab_config.metadata.name
                        except (FileNotFoundError, Exception):
                            # Remove the stale current lab file
                            current_lab_file.unlink(missing_ok=True)
            except Exception:
                # If we can't read the file, remove it
                current_lab_file.unlink(missing_ok=True)

    def _save_current_lab(self) -> None:
        """Save the current lab ID to the current lab file."""
        current_lab_file = self._get_current_lab_file()
        if self._config_path:
            lab_id = self._config_path.stem
            with open(current_lab_file, 'w', encoding='utf-8') as f:
                f.write(lab_id)
        else:
            # Clear the current lab file if no lab is loaded
            current_lab_file.unlink(missing_ok=True)

    @staticmethod
    def _get_default_lab_dir() -> Path:
        """Get the default directory for lab configurations (deprecated, use get_labs_directory)."""
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

        config_dir = config_dir or self.get_labs_directory()
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
        config_dir = config_dir or self.get_labs_directory()

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

        # Save this as the current lab for future sessions
        self._save_current_lab()

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
        config_dir = config_dir or self.get_labs_directory()
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

    # Genotype management
    def add_genotype(self, genotype: LabGenotype) -> None:
        """Add a genotype configuration to the lab."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if genotype.gene_name in self._lab_config.genotypes:
            raise ValueError(f"Genotype for gene '{genotype.gene_name}' already exists")

        self._lab_config.genotypes[genotype.gene_name] = genotype
        self.save_lab()

    def remove_genotype(self, gene_name: str) -> bool:
        """Remove a genotype configuration. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if gene_name in self._lab_config.genotypes:
            del self._lab_config.genotypes[gene_name]
            self.save_lab()
            return True
        return False

    def get_genotype(self, gene_name: str) -> Optional[LabGenotype]:
        """Get a genotype configuration."""
        if self._lab_config is None:
            return None
        return self._lab_config.genotypes.get(gene_name)

    def get_all_genotypes(self) -> Dict[str, LabGenotype]:
        """Get all genotype configurations."""
        if self._lab_config is None:
            return {}
        return self._lab_config.genotypes.copy()

    def add_tracked_genotype(self, gene_name: str) -> None:
        """Add a gene name to the tracked genotypes list."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if gene_name not in self._lab_config.tracked_genotypes:
            self._lab_config.tracked_genotypes.add(gene_name)
            self.save_lab()

    def remove_tracked_genotype(self, gene_name: str) -> bool:
        """Remove a gene name from the tracked genotypes list. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if gene_name in self._lab_config.tracked_genotypes:
            self._lab_config.tracked_genotypes.remove(gene_name)
            self.save_lab()
            return True
        return False

    def get_tracked_genotypes(self) -> Set[str]:
        """Get the list of tracked genotype gene names."""
        if self._lab_config is None:
            return set()
        return self._lab_config.tracked_genotypes.copy()

    def add_tracked_treatment(self, treatment_name: str) -> None:
        """Add a treatment name to the tracked treatments list."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if treatment_name not in self._lab_config.tracked_treatments:
            self._lab_config.tracked_treatments.add(treatment_name)
            self.save_lab()

    def remove_tracked_treatment(self, treatment_name: str) -> bool:
        """Remove a treatment name from the tracked treatments list. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if treatment_name in self._lab_config.tracked_treatments:
            self._lab_config.tracked_treatments.remove(treatment_name)
            self.save_lab()
            return True
        return False

    def get_tracked_treatments(self) -> Set[str]:
        """Get the list of tracked treatment names."""
        if self._lab_config is None:
            return set()
        return self._lab_config.tracked_treatments.copy()

    def add_tracked_experiment_type(self, experiment_type: str) -> None:
        """Add an experiment type to the tracked list."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if experiment_type not in self._lab_config.tracked_experiment_types:
            self._lab_config.tracked_experiment_types.add(experiment_type)
            self.save_lab()

    def remove_tracked_experiment_type(self, experiment_type: str) -> bool:
        """Remove an experiment type from the tracked list. Returns True if removed."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if experiment_type in self._lab_config.tracked_experiment_types:
            self._lab_config.tracked_experiment_types.remove(experiment_type)
            self.save_lab()
            return True
        return False

    def get_tracked_experiment_types(self) -> Set[str]:
        """Get the list of tracked experiment types."""
        if self._lab_config is None:
            return set()
        return self._lab_config.tracked_experiment_types.copy()

    def validate_subject_genotype(self, subject: SubjectMetadata) -> List[str]:
        """Validate a subject's genotype against lab genotype configurations.

        Returns a list of validation errors (empty list if valid).
        """
        errors = []
        if self._lab_config is None:
            return ["No lab configuration loaded"]

        # Extract genotype info from subject's genotype field
        # This assumes genotype field contains gene-specific information
        genotype_str = subject.effective_genotype
        if genotype_str:
            # Parse genotype string (e.g., "ATP7B:WT" or "ATP7B:Het")
            if ":" in genotype_str:
                gene_part, allele_part = genotype_str.split(":", 1)
                gene_name = gene_part

                genotype_config = self.get_genotype(gene_name)
                if genotype_config:
                    if not genotype_config.validate_allele(allele_part):
                        errors.append(f"Invalid allele '{allele_part}' for gene '{gene_name}'. Valid alleles: {genotype_config.alleles}")
                else:
                    errors.append(f"No genotype configuration found for gene '{gene_name}'")

        return errors

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

    # Shared storage management
    def set_shared_storage(
        self,
        mount_point: Optional[str] = None,
        volume_name: Optional[str] = None,
        projects_root: Optional[str] = None,
        media_root: Optional[str] = None,
        enabled: Optional[bool] = None,
        auto_detect: Optional[bool] = None
    ) -> None:
        """Configure shared storage for the current lab."""
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if mount_point is not None:
            self._lab_config.shared_storage.mount_point = mount_point
        if volume_name is not None:
            self._lab_config.shared_storage.volume_name = volume_name
        if projects_root is not None:
            self._lab_config.shared_storage.projects_root = projects_root
        if media_root is not None:
            self._lab_config.shared_storage.media_root = media_root
        if enabled is not None:
            self._lab_config.shared_storage.enabled = enabled
        if auto_detect is not None:
            self._lab_config.shared_storage.auto_detect = auto_detect

        self.save_lab()

    def detect_shared_storage_mount(self) -> Optional[Path]:
        """Detect if the shared storage is currently mounted."""
        if self._lab_config is None or not self._lab_config.shared_storage.enabled:
            return None

        storage = self._lab_config.shared_storage

        # If mount point is specified, check if it exists
        if storage.mount_point:
            mount_path = Path(storage.mount_point)
            if mount_path.exists():
                return mount_path

        # If volume name is specified, try to find it
        if storage.volume_name and storage.auto_detect:
            # On macOS, check /Volumes
            if os.name == "posix" and platform.system() == "Darwin":
                volumes_dir = Path("/Volumes")
                if volumes_dir.exists():
                    for item in volumes_dir.iterdir():
                        if item.is_dir() and item.name == storage.volume_name:
                            return item

            # On Linux, check /mnt and /media
            elif os.name == "posix":
                for mount_base in ["/mnt", "/media"]:
                    mount_dir = Path(mount_base)
                    if mount_dir.exists():
                        for item in mount_dir.iterdir():
                            if item.is_dir() and item.name == storage.volume_name:
                                return item

            # On Windows, check drive letters
            elif os.name == "nt":
                import string
                for drive_letter in string.ascii_uppercase:
                    drive_path = Path(f"{drive_letter}:")
                    if drive_path.exists() and drive_path.name.rstrip(":") == storage.volume_name:
                        return drive_path

        return None

    def get_shared_projects_root(self) -> Optional[Path]:
        """Get the projects directory on shared storage if available."""
        mount_point = self.detect_shared_storage_mount()
        if mount_point and self._lab_config:
            return mount_point / self._lab_config.shared_storage.projects_root
        return None

    def get_shared_media_root(self) -> Optional[Path]:
        """Get the media directory on shared storage if available."""
        mount_point = self.detect_shared_storage_mount()
        if mount_point and self._lab_config:
            return mount_point / self._lab_config.shared_storage.media_root
        return None

    def activate_lab(self, check_storage: bool = True) -> bool:
        """Activate the current lab, optionally checking shared storage.

        Returns True if activation successful, False if shared storage check failed.
        """
        if self._lab_config is None:
            raise RuntimeError("No lab configuration loaded")

        if check_storage and self._lab_config.shared_storage.enabled:
            mount_point = self.detect_shared_storage_mount()
            if mount_point is None:
                return False

            # Set environment variables for shared storage
            os.environ["MUS1_SHARED_STORAGE_MOUNT"] = str(mount_point)
            os.environ["MUS1_ACTIVE_LAB"] = self._lab_config.metadata.name

            # Create shared directories if they don't exist
            projects_root = self.get_shared_projects_root()
            media_root = self.get_shared_media_root()

            if projects_root:
                projects_root.mkdir(parents=True, exist_ok=True)
            if media_root:
                media_root.mkdir(parents=True, exist_ok=True)

        else:
            # Clear shared storage env vars if not using shared storage
            os.environ.pop("MUS1_SHARED_STORAGE_MOUNT", None)
            os.environ["MUS1_ACTIVE_LAB"] = self._lab_config.metadata.name

        # Save this lab as the current lab
        self._save_current_lab()

        return True

    def deactivate_lab(self) -> None:
        """Deactivate the current lab."""
        os.environ.pop("MUS1_SHARED_STORAGE_MOUNT", None)
        os.environ.pop("MUS1_ACTIVE_LAB", None)
        self._lab_config = None
        self._config_path = None
        self._get_current_lab_file().unlink(missing_ok=True)

    # Property access
    @property
    def current_lab(self) -> Optional[LabConfig]:
        """Get the currently loaded lab configuration."""
        return self._lab_config

    @property
    def current_lab_path(self) -> Optional[Path]:
        """Get the path to the currently loaded lab configuration."""
        return self._config_path
