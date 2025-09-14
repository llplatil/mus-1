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
from pydantic import BaseModel, Field, validator
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
class Subject:
    """Core subject entity."""
    id: str
    sex: Sex = Sex.UNKNOWN
    birth_date: Optional[datetime] = None
    death_date: Optional[datetime] = None
    genotype: Optional[str] = None
    treatment: Optional[str] = None
    notes: str = ""
    date_added: datetime = field(default_factory=datetime.now)

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

class SubjectDTO(BaseModel):
    """Data transfer object for subject data."""
    id: str
    sex: Sex = Sex.UNKNOWN
    birth_date: Optional[datetime] = None
    death_date: Optional[datetime] = None
    genotype: Optional[str] = None
    treatment: Optional[str] = None
    notes: str = ""
    date_added: datetime = Field(default_factory=datetime.now)

    @validator("id")
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

    @validator("id")
    def validate_id(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Experiment ID must be at least 3 characters")
        return v.strip()

    @validator("date_recorded")
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
    