"""Core metadata models for MUS1"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from datetime import datetime

from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from enum import Enum
from pydantic import BaseModel, Field, validator, root_validator
from collections import defaultdict
import logging
import pandas as pd

logger = logging.getLogger("mus1.core.metadata")

def init_metadata() -> bool:
    """
    Example: optional function to verify that all models/enums are fine.
    The rest of your data classes remain here (SubjectMetadata, etc.).
    """
    try:
        logger.info("Initializing metadata system")
        # ... do your checks ...
        logger.info("Metadata system initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed: {e}")
        return False

class HasDateAdded(Protocol):
    date_added: datetime

class HasName(Protocol):
    name: str

# Removed legacy enums for experiment sessions and arena image source
# Define constants instead
ARENA_SOURCE_DLC_EXPORT = "DLC_Export"
ARENA_SOURCE_MANUAL = "Manual"
ARENA_SOURCE_UNKNOWN = "Unknown"

@dataclass
class PluginMetadata:
    """Plugin metadata structure"""
    name: str
    date_created: datetime
    version: str
    description: str
    author: str
    supported_experiment_types: Optional[List[str]] = None
    supported_processing_stages: Optional[List[str]] = None
    supported_data_sources: Optional[List[str]] = None
    plugin_type: Optional[str] = None  # delinites plugin type (eg experiment type, batch type, etc.) and has supported_experiment_types as sub classes

class Sex(str, Enum):
    M = "M"
    F = "F"
    UNKNOWN = "Unknown"


class NORSessions(Enum):
    FAMILIARIZATION = "familiarization"
    RECOGNITION = "recognition"


class OFSessions(str, Enum):
    HABITUATION = "habituation"
    REEXPOSURE = "re-exposure"


class TrackingData(BaseModel):
    """
    Minimal representation of tracking-file info for an experiment.
    Actual numerical data can be loaded or processed elsewhere.
    """
    file_path: Path
    file_type: str = "csv"
    source: str = "Unknown"


class SubjectMetadata(BaseModel):
    """
    Represents a single subject.
    Advanced or cross-field validations (e.g., checking future birth_date)
    are done here at a basic level, while more elaborate checks happen outside.
    """
    id: str
    experiment_ids: Set[str] = set()

    sex: Sex = Sex.UNKNOWN
    birth_date: Optional[datetime] = None
    death_date: Optional[datetime] = None  # Add death date field
    genotype: Optional[str] = None
    treatment: Optional[str] = None
    notes: str = ""
    in_training_set: bool = False
    date_added: datetime = Field(default_factory=datetime.now)
    allowed_experiment_types: Set[str] = Field(default_factory=set)

    @validator("id")
    def validate_id(cls, v: str) -> str:
        if not v or len(v) < 3:
            raise ValueError("Subject ID must be at least 3 characters.")
        return v

    @validator("birth_date")
    def validate_birth_date(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v > datetime.now():
            raise ValueError("Birth date cannot be in the future.")
        return v
    
    @validator("death_date")
    def validate_death_date(cls, v: Optional[datetime], values) -> Optional[datetime]:
        if v and v > datetime.now():
            raise ValueError("Death date cannot be in the future.")
        birth_date = values.get("birth_date")
        if v and birth_date and v < birth_date:
            raise ValueError("Death date cannot be before birth date.")
        return v
        
    @property
    def age(self) -> Optional[int]:
        """Calculate age in days."""
        if not self.birth_date:
            return None
            
        end_date = self.death_date if self.death_date else datetime.now()
        delta = end_date - self.birth_date
        return delta.days


class ExperimentMetadata(BaseModel):
    """
    Represents a single experiment session.
    
    Core properties:
      - id: unique experiment ID
      - type: experiment type (as a string, e.g., "NOR", "OpenField")
      - subject_id: ID of the subject undergoing experiment
      - date_recorded: when the experiment was recorded
      - date_added: when the experiment was added to the project
    
    Plugin-specific properties:
      - plugin_params: Dictionary holding dynamic plugin-specific fields,
                      organized by plugin name (e.g., {"NORPlugin": {"session_stage": "familiarization"}})
      - plugin_metadata: List of PluginMetadata objects for the plugins used in this experiment
    
    Relationships:
      - batch_ids: IDs of batches this experiment belongs to
      - file_ids: IDs of files associated with this experiment
    """
    id: str
    type: str  # Used to be ExperimentType enum at metadata level now it should be ENUM at base plugin level
    subject_id: str
    date_recorded: datetime
    date_added: datetime = Field(default_factory=datetime.now)
    
    # Optional tracking data
    tracking_data: Optional[TrackingData] = None
    
    # Plugin-specific parameters and metadata
    plugin_params: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    plugin_metadata: List[PluginMetadata] = Field(default_factory=list)
    
    # New fields for hierarchical experiment creation
    processing_stage: str = ""
    data_source: str = ""
    associated_plugins: List[str] = Field(default_factory=list)
    
    # Relationships
    batch_ids: Set[str] = Field(default_factory=set)
    file_ids: Set[str] = Field(default_factory=set)
    
    @property
    def analysis_ready(self) -> bool:
        """Return True if the experiment is ready for analysis (i.e. tracking_data is present)."""
        return self.tracking_data is not None


class BatchMetadata(BaseModel):
    """
    Represents a group of experiments selected through some UI or search criteria.
    """
    id: str
    name: str = ""  # Added explicit name field separate from ID
    description: str = ""  # Added description field
    selection_criteria: Dict[str, Any]
    experiment_ids: Set[str] = set()
    analysis_type: Optional[str] = None  # Was ExperimentType enum
    date_added: datetime = Field(default_factory=datetime.now)
    parameters: Dict[str, Any] = {}
    likelihood_cutoff: float = 0.5

    # should be an override field of global threshold if selected and global on:
    likelihood_threshold: Optional[float] = None
    
    # Optional field for batch status tracking
    status: str = "created"  # Possible values: created, processing, completed
    processing_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None
    
    # Notes and results fields
    notes: str = ""
    results_summary: Optional[str] = None
    
    @property
    def experiment_count(self) -> int:
        """Returns the number of experiments in this batch."""
        return len(self.experiment_ids)
    
    @property
    def is_empty(self) -> bool:
        """Returns True if the batch contains no experiments."""
        return len(self.experiment_ids) == 0

class GlobalSortMode(str, Enum):
    NATURAL_ORDER = "Natural Order (Numbers as Numbers)"
    ALPHABETICAL = "Lexicographical Order (Numbers as Characters)"
    DATE_ADDED = "Date Added"

class ProjectMetadata(BaseModel):
    """
    Contains global or project-level settings that typically apply
    across all mice/experiments (like DLC configs, bodyparts, etc.).
    """
    dlc_configs: List[Path] = []
    master_body_parts: List[BodyPartMetadata] = Field(default_factory=list)

    @validator('master_body_parts', pre=True, each_item=True)
    def fix_master_body_parts(cls, v):
        if isinstance(v, str):
            return BodyPartMetadata(name=v)
        return v

    active_body_parts: List[BodyPartMetadata] = Field(default_factory=list)

    @validator('active_body_parts', pre=True, each_item=True)
    def fix_active_body_parts(cls, v):
        if isinstance(v, str):
            return BodyPartMetadata(name=v)
        return v

    # Update to have both master and active tracked objects
    master_tracked_objects: List[ObjectMetadata] = Field(default_factory=list)

    @validator('master_tracked_objects', pre=True, each_item=True)
    def fix_master_tracked_objects(cls, v):
        if isinstance(v, str):
            return ObjectMetadata(name=v)
        return v

    active_tracked_objects: List[ObjectMetadata] = Field(default_factory=list)

    @validator('active_tracked_objects', pre=True, each_item=True)
    def fix_active_tracked_objects(cls, v):
        if isinstance(v, str):
            return ObjectMetadata(name=v)
        return v

    # Keep tracked_objects for backward compatibility
    tracked_objects: List[ObjectMetadata] = Field(default_factory=list)

    @validator('tracked_objects', pre=True, each_item=True)
    def fix_tracked_objects(cls, v):
        if isinstance(v, str):
            return ObjectMetadata(name=v)
        return v

    # Global sort mode stored with the project
    global_sort_mode: GlobalSortMode = GlobalSortMode.ALPHABETICAL

    # Global frame rate settings
    global_frame_rate: int = 60
    global_frame_rate_enabled: bool = False  # Default to OFF
    
    # Theme preference (dark or light)
    theme_mode: str = "dark"
    
    # Basic metadata about the project
    project_name: str
    date_created: datetime

    @validator("project_name")
    def check_project_name(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Project name must be at least 3 characters")
        return v

    # Add new fields for treatments and genotypes
    master_treatments: List[TreatmentMetadata] = Field(default_factory=list)
    active_treatments: List[TreatmentMetadata] = Field(default_factory=list)
    master_genotypes: List[GenotypeMetadata] = Field(default_factory=list)
    active_genotypes: List[GenotypeMetadata] = Field(default_factory=list)


class ArenaImageMetadata(BaseModel):
    """
    Represents metadata for an arena image or video snippet.
    """
    path: Path
    date: datetime
    notes: str
    arena_markings: Dict[str, Any] = {}
    in_training_set: bool = False
    experiment_ids: Set[str] = set()
    source: str = ARENA_SOURCE_UNKNOWN

    # Distinguish between "image" and "video"
    media_type: str = "image"  # "image" or "video"


class VideoMetadata(BaseModel):
    """
    Metadata for an experiment-related video file.
    """
    path: Path
    date: datetime
    notes: str = ""
    experiment_ids: Set[str] = set()
    media_type: str = "video"


class ExternalConfigMetadata(BaseModel):
    """
    A placeholder for referencing external config/calibration files, etc.
    """
    path: Path
    config_type: str = "yaml"  # or "json", "csv", etc.
    description: str = ""
    date: datetime = Field(default_factory=datetime.now)


class ProjectState(BaseModel):
    """
    In-memory data structure for the runtime state of a project:
      - references to subjects, experiments, batches, etc.
      - merges or references the ProjectMetadata if needed.
    """
    version: str = "0.1.0"
    last_modified: datetime = Field(default_factory=datetime.now)

    # Settings can include global flags, additional user preferences, etc.
    settings: Dict[str, Any] = Field(
        default_factory=lambda: {
            "global_frame_rate": 60,
            "global_frame_rate_enabled": False,
            "global_sort_mode": "Lexicographical Order (Numbers as Characters)"
        }
    )

    subjects: Dict[str, SubjectMetadata] = Field(default_factory=dict)
    experiments: Dict[str, ExperimentMetadata] = Field(default_factory=dict)
    batches: Dict[str, BatchMetadata] = Field(default_factory=dict)
    arena_images: Dict[str, ArenaImageMetadata] = Field(default_factory=dict)
    experiment_videos: Dict[str, VideoMetadata] = Field(default_factory=dict)
    external_configs: Dict[str, ExternalConfigMetadata] = Field(default_factory=dict)

    project_metadata: Optional[ProjectMetadata] = None

    # New fields for controlling a global default threshold and whether to enforce it:
    likelihood_filter_enabled: bool = Field(default=False)
    default_likelihood_threshold: float = Field(default=0.5)

    supported_experiment_types: List[str] = Field(default_factory=list)

    # Store plugin metadata objects at runtime
    registered_plugin_metadatas: List[PluginMetadata] = Field(default_factory=list)


class BodyPartMetadata(BaseModel):
    name: str
    date_added: datetime = Field(default_factory=datetime.now)
    coordinates: Optional[dict] = None  # e.g., {'x': value, 'y': value}


class ObjectMetadata(BaseModel):
    name: str
    date_added: datetime = Field(default_factory=datetime.now)
    bounding_box: Optional[dict] = None  # e.g., {'x': value, 'y': value, 'width': w, 'height': h}


class TreatmentMetadata(BaseModel):
    name: str
    date_added: datetime = Field(default_factory=datetime.now)
    description: Optional[str] = None


class GenotypeMetadata(BaseModel):
    name: str
    date_added: datetime = Field(default_factory=datetime.now)
    description: Optional[str] = None

    