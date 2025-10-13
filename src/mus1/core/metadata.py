"""Clean metadata models for MUS1 SQLite backend

This module provides:
1. Domain Models: Business logic entities (dataclasses)
2. DTOs: Data Transfer Objects for API communication (Pydantic)
3. Enums: Constants and enumerations
4. No database concerns - those belong in schema.py
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
import logging

logger = logging.getLogger("mus1.core.metadata")

class HasDateAdded(Protocol):
    date_added: datetime

class HasName(Protocol):
    name: str

# ===========================================
# CORE ENUMS
# ===========================================

class ProcessingStage(str, Enum):
    """Experiment processing stages."""
    PLANNED = "planned"
    RECORDED = "recorded"
    TRACKED = "tracked"
    INTERPRETED = "interpreted"


class SubjectDesignation(str, Enum):
    """Subject designation for colony management vs experimental use."""
    EXPERIMENTAL = "experimental"
    BREEDING = "breeding"
    CULLED = "culled"

class InheritancePattern(str, Enum):
    """Genotype inheritance patterns."""
    DOMINANT = "Dominant"
    RECESSIVE = "Recessive"
    X_LINKED = "X-Linked"

class Sex(str, Enum):
    """Subject sex enumeration."""
    MALE = "M"
    FEMALE = "F"
    UNKNOWN = "Unknown"

class WorkerProvider(str, Enum):
    """Worker execution providers."""
    SSH = "ssh"
    WSL = "wsl"
    LOCAL = "local"
    SSH_WSL = "ssh-wsl"

class ScanTargetKind(str, Enum):
    """Types of scan targets."""
    LOCAL = "local"
    SSH = "ssh"
    WSL = "wsl"


# ===========================================
# DOMAIN MODELS (Business Logic)
# ===========================================

@dataclass
class User:
    """Core user entity for application-level user management."""
    id: str  # User key/identifier
    name: str
    email: str
    organization: Optional[str] = None
    default_projects_dir: Optional[Path] = None
    default_shared_dir: Optional[Path] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

@dataclass
class Lab:
    """Core lab entity for research group management."""
    id: str
    name: str
    creator_id: str  # Reference to creating user
    institution: Optional[str] = None
    pi_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class Workgroup:
    """Core workgroup entity for collaborative research."""
    id: str
    name: str
    share_key_hash: str  # Salted hash of shareable key
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class WorkgroupMember:
    """Workgroup membership entity."""
    workgroup_id: str
    member_email: str
    role: str = "member"  # 'admin', 'member', etc.
    added_at: datetime = field(default_factory=datetime.now)

@dataclass
class PluginMetadata:
    """Plugin metadata structure."""
    name: str
    date_created: datetime
    version: str
    description: str
    author: str
    supported_experiment_types: Optional[List[str]] = None
    readable_data_formats: List[str] = field(default_factory=list)
    analysis_capabilities: List[str] = field(default_factory=list)

@dataclass
class Colony:
    """Core colony entity representing a group of subjects with shared characteristics."""
    id: str
    name: str
    lab_id: str
    genotype_of_interest: Optional[str] = None
    background_strain: Optional[str] = None
    common_traits: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    date_added: datetime = field(default_factory=datetime.now)

    @property
    def full_description(self) -> str:
        """Get a full description of the colony."""
        desc_parts = [self.name]
        if self.genotype_of_interest:
            desc_parts.append(f"({self.genotype_of_interest})")
        if self.background_strain:
            desc_parts.append(f"on {self.background_strain}")
        return " ".join(desc_parts)


@dataclass
class Subject:
    """Core subject entity."""
    id: str
    colony_id: str
    sex: Sex = Sex.UNKNOWN
    designation: SubjectDesignation = SubjectDesignation.EXPERIMENTAL
    birth_date: Optional[datetime] = None
    death_date: Optional[datetime] = None
    individual_genotype: Optional[str] = None  # Individual-specific genotype if different from colony
    individual_treatment: Optional[str] = None  # Individual-specific treatment if different from colony
    notes: str = ""
    date_added: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Handle any post-initialization logic."""
        pass

    @property
    def genotype(self) -> Optional[str]:
        """Get the effective genotype (individual or colony default)."""
        return self.individual_genotype

    @genotype.setter
    def genotype(self, value: Optional[str]):
        """Set the genotype (maps to individual_genotype)."""
        self.individual_genotype = value

    @property
    def treatment(self) -> Optional[str]:
        """Get the effective treatment (individual or colony default)."""
        return self.individual_treatment  # For now, we'll handle colony treatment in repository queries

    @property
    def age_days(self) -> Optional[int]:
        """Calculate age in days."""
        if not self.birth_date:
            return None
        end_date = self.death_date if self.death_date else datetime.now()
        return (end_date - self.birth_date).days

@dataclass
class Experiment:
    """Core experiment entity."""
    id: str
    subject_id: str
    experiment_type: str
    date_recorded: datetime
    processing_stage: ProcessingStage = ProcessingStage.PLANNED
    experiment_subtype: Optional[str] = None
    notes: str = ""
    date_added: datetime = field(default_factory=datetime.now)

    @property
    def is_ready_for_analysis(self) -> bool:
        """Check if experiment is ready for analysis."""
        return self.processing_stage in [ProcessingStage.RECORDED, ProcessingStage.TRACKED]

@dataclass
class VideoFile:
    """Core video file entity."""
    path: Path
    hash: str
    recorded_time: Optional[datetime] = None
    size_bytes: int = 0
    last_modified: float = 0.0
    date_added: datetime = field(default_factory=datetime.now)

@dataclass
class Worker:
    """Worker configuration."""
    name: str
    ssh_alias: str
    role: Optional[str] = None
    provider: WorkerProvider = WorkerProvider.SSH
    os_type: Optional[str] = None

@dataclass
class ScanTarget:
    """Scan target configuration."""
    name: str
    kind: ScanTargetKind
    roots: List[Path]
    ssh_alias: Optional[str] = None


# ===========================================
# DATA TRANSFER OBJECTS (DTOs)
# ===========================================

class UserDTO(BaseModel):
    """Data transfer object for user data."""
    id: str
    name: str
    email: str
    organization: Optional[str] = None
    default_projects_dir: Optional[str] = None
    default_shared_dir: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class LabDTO(BaseModel):
    """Data transfer object for lab data."""
    id: str
    name: str
    creator_id: str
    institution: Optional[str] = None
    pi_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

class WorkgroupDTO(BaseModel):
    """Data transfer object for workgroup data."""
    id: str
    name: str
    share_key_hash: str
    created_at: datetime = Field(default_factory=datetime.now)

class ColonyDTO(BaseModel):
    """Data transfer object for colony data."""
    id: str
    name: str
    lab_id: str
    genotype_of_interest: Optional[str] = None
    background_strain: Optional[str] = None
    common_traits: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    date_added: datetime = Field(default_factory=datetime.now)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Colony ID must be at least 3 characters")
        return v.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Colony name must be at least 3 characters")
        return v.strip()


class SubjectDTO(BaseModel):
    """Data transfer object for subject data."""
    id: str
    colony_id: str
    sex: Sex = Sex.UNKNOWN
    designation: SubjectDesignation = SubjectDesignation.EXPERIMENTAL
    birth_date: Optional[datetime] = None
    death_date: Optional[datetime] = None
    individual_genotype: Optional[str] = None
    individual_treatment: Optional[str] = None
    notes: str = ""
    date_added: datetime = Field(default_factory=datetime.now)
    genotype: Optional[str] = None  # Alias for individual_genotype

    @model_validator(mode='before')
    @classmethod
    def handle_genotype_alias(cls, values):
        """Handle genotype parameter alias for backward compatibility."""
        if isinstance(values, dict):
            # Handle genotype alias for individual_genotype
            if 'genotype' in values and values['genotype'] is not None:
                if 'individual_genotype' not in values or values['individual_genotype'] is None:
                    values['individual_genotype'] = values['genotype']
        return values

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Subject ID must be at least 3 characters")
        return v.strip()

class ExperimentDTO(BaseModel):
    """Data transfer object for experiment data."""
    id: str
    subject_id: str
    experiment_type: str
    date_recorded: datetime
    processing_stage: ProcessingStage = ProcessingStage.PLANNED
    experiment_subtype: Optional[str] = None
    notes: str = ""
    date_added: datetime = Field(default_factory=datetime.now)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Experiment ID must be at least 3 characters")
        return v.strip()

    @field_validator("date_recorded")
    @classmethod
    def validate_date_recorded(cls, v: datetime) -> datetime:
        if v > datetime.now():
            raise ValueError("Recording date cannot be in the future")
        return v

class VideoFileDTO(BaseModel):
    """Data transfer object for video file data."""
    path: str  # Path as string for JSON serialization
    hash: str
    recorded_time: Optional[datetime] = None
    size_bytes: int = 0
    last_modified: float = 0.0
    date_added: datetime = Field(default_factory=datetime.now)


class WorkerDTO(BaseModel):
    """Data transfer object for worker data."""
    name: str
    ssh_alias: str
    role: Optional[str] = None
    provider: WorkerProvider = WorkerProvider.SSH
    os_type: Optional[str] = None

class ScanTargetDTO(BaseModel):
    """Data transfer object for scan target data."""
    name: str
    kind: ScanTargetKind
    roots: List[str]  # Paths as strings for JSON serialization
    ssh_alias: Optional[str] = None

# ===========================================
# SIMPLE UTILITY FUNCTIONS
# ===========================================

def validate_subject_id(subject_id: str) -> str:
    """Validate subject ID format."""
    if not subject_id or len(subject_id.strip()) < 3:
        raise ValueError("Subject ID must be at least 3 characters")
    return subject_id.strip()

def validate_experiment_id(experiment_id: str) -> str:
    """Validate experiment ID format."""
    if not experiment_id or len(experiment_id.strip()) < 3:
        raise ValueError("Experiment ID must be at least 3 characters")
    return experiment_id.strip()


# ===========================================
# PROJECT CONFIGURATION (Simple)
# ===========================================

@dataclass
class PluginResult:
    """Plugin analysis result."""
    experiment_id: str
    plugin_name: str
    capability: str
    result_data: Dict[str, Any]
    status: str  # 'success', 'failed', 'running'
    error_message: str = ""
    output_files: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

@dataclass
class ProjectConfig:
    """Simple project configuration."""
    name: str
    shared_root: Optional[Path] = None
    lab_id: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    date_created: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.name or len(self.name.strip()) < 3:
            raise ValueError("Project name must be at least 3 characters")
        self.name = self.name.strip()
    