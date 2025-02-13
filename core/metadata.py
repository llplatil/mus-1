"""Core metadata models for MUS1"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, validator, root_validator
from collections import defaultdict
from ..utils import get_logger
import pandas as pd

logger = get_logger("core.metadata")

#TODO: use pathlib to handle paths to other files
def init_metadata() -> bool:
    """Initialize metadata system
    
    Returns:
        bool: True if metadata system initialized successfully
    """
    try:
        logger.info("Initializing metadata system")
        
        # Verify all required models are properly defined
        required_models = [
            MouseMetadata,
            ExperimentMetadata,
            BatchMetadata,
            ProjectState,
            ProjectMetadata,
            TrackingData,
            ArenaImageMetadata,
            NORPluginParams,
            OFPluginParams
        ]
        
        for model in required_models:
            if not issubclass(model, BaseModel):
                logger.error(f"{model.__name__} is not a proper Pydantic model")
                return False
                
        # Verify enums are properly defined
        required_enums = [
            ExperimentType,
            SessionStage,
            Sex,
            TrackingSource,
            ArenaImageSource,
            NORSessions,
            OFSessions
        ]
        
        for enum in required_enums:
            if not issubclass(enum, Enum):
                logger.error(f"{enum.__name__} is not a proper Enum")
                return False
                
        logger.info("Metadata system initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize metadata system: {e}")
        return False

@dataclass
class PluginMetadata:
    """Plugin metadata structure"""
    name: str
    version: str
    description: str
    author: str

class ExperimentType(str, Enum):
    NOR = "NOR"
    OPEN_FIELD = "OpenField"
    # Add more as needed

class SessionStage(str, Enum):
    """
    Enumerates the typical 'stage' or 'phase' of an experiment session.
    For NOR, we often have:
      - FAMILIARIZATION (familiar)
      - RECOGNITION (test)
    For Open Field, the second session might also be
      "re-test" after a period of weeks, etc.
    """
    FAMILIARIZATION = "familiarization"
    RECOGNITION = "recognition"
    HABITUATION = "habituation"
    REEXPOSURE = "re-exposure"
    # You can add other stages like "retest", "baseline", "habituation", etc.

class Sex(str, Enum):
    M = "M"
    F = "F"
    UNKNOWN = "Unknown"


class TrackingSource(str, Enum):
    DLC = "DLC"
    UNKNOWN = "Unknown"


class ArenaImageSource(str, Enum):
    DLC_EXPORT = "DLC_Export"
    MANUAL = "Manual"
    UNKNOWN = "Unknown"


class NORSessions(str, Enum):
    FAMILIARIZATION = "familiarization"
    RECOGNITION = "recognition"


class OFSessions(str, Enum):
    HABITUATION = "habituation"
    REEXPOSURE = "re-exposure"


class NORPluginParams(BaseModel):
    """
    NOR-specific params, including the session stage and object roles.
    Example logic: if stage = FAMILIARIZATION, both objects must be the same.
    """
    session_stage: NORSessions = NORSessions.FAMILIARIZATION
    object_roles: Dict[str, str] = {}

    @root_validator
    def ensure_objects_same_for_familiarization(cls, values):
        session_stage = values.get("session_stage")
        roles = values.get("object_roles", {})
        if session_stage == NORSessions.FAMILIARIZATION:
            # e.g., enforce that all object roles are 'familiar' or the same
            # This is just an example check — your real logic may differ
            unique_objects = set(roles.values())
            if len(unique_objects) > 1:
                raise ValueError("Familiarization stage requires identical object roles.")
        return values


class OFPluginParams(BaseModel):
    """
    Open Field-specific params, focusing on stage (habituation or re-exposure)
    and optional arena markings, etc.
    """
    session_stage: OFSessions = OFSessions.HABITUATION
    arena_markings: Dict[str, Any] = {}


class TrackingData(BaseModel):
    """
    Minimal representation of tracking-file info for an experiment.
    Actual numerical data can be loaded or processed elsewhere.
    """
    file_path: Path
    file_type: str = "csv"
    source: TrackingSource = TrackingSource.UNKNOWN


class MouseMetadata(BaseModel):
    """
    Represents a single subject (mouse).
    Advanced or cross-field validations (e.g., checking future birth_date)
    are done here at a basic level, while more elaborate checks happen outside.
    """
    id: str
    experiment_ids: Set[str] = set()

    sex: Sex = Sex.UNKNOWN
    birth_date: Optional[datetime] = None
    genotype: Optional[str] = None
    treatment: Optional[str] = None
    notes: str = ""
    in_training_set: bool = False

    @validator("id")
    def validate_id(cls, v: str) -> str:
        if not v or len(v) < 3:
            raise ValueError("Mouse ID must be at least 3 characters.")
        return v

    @validator("birth_date")
    def validate_birth_date(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v > datetime.now():
            raise ValueError("Birth date cannot be in the future.")
        return v


class ExperimentMetadata(BaseModel):
    """
    Represents a single experiment session.
    By adding a 'session_stage' and possibly 'session_index',
    we allow multiple sessions in the same environment or with the same type,
    but vary the stage/time as needed.
    """
    id: str
    type: ExperimentType
    mouse_id: str
    date: datetime
    tracking_data: TrackingData

    session_stage: SessionStage = SessionStage.FAMILIARIZATION
    """
    E.g., for NOR on the same day you could do:
       - session_stage=SessionStage.FAMILIARIZATION at 9 AM
       - session_stage=SessionStage.RECOGNITION at 10 AM
    For OF, when re-tested weeks later, you might still mark
    session_stage=SessionStage.FAMILIARIZATION (since it's a new environment or time).
    """

    # If you want to track repeated exposures over time, consider a session_index:
    session_index: int = 1
    """
    For example, if the mouse sees the same arena a second or third time,
    you can increment session_index=2, session_index=3, etc.
    """

    # Optional or plugin-specific fields
    frame_rate: Optional[int] = None
    start_time: float = 0.0
    end_time: Optional[float] = None
    duration: Optional[float] = None
    arena_image_path: Path = Path()
    notes: str = ""

    @property
    def phase_type(self) -> str:
        """
        A normalized phase type (lowercased).
        More specialized validation or enumerations
        should occur in plugin or advanced logic.
        """
        return self.session_stage.value.lower() if self.session_stage else "unset"

    @property
    def analysis_ready(self) -> bool:
        """
        A quick check to see if this experiment is typically 'ready' for analysis.
        Actual validations can be expanded or done in plugin code.
        """
        return (
            bool(self.tracking_data)
            and self.arena_image_path.exists()
            and len(self.object_roles) >= 2
        )


class BatchMetadata(BaseModel):
    """
    Represents a group of experiments selected through some UI or search criteria.
    """
    selection_criteria: Dict[str, Any]
    experiment_ids: Set[str] = set()
    analysis_type: Optional[ExperimentType] = None
    parameters: Dict[str, Any] = {}
    likelihood_cutoff: float = 0.5


class ProjectMetadata(BaseModel):
    """
    Contains global or project-level settings that typically apply
    across all mice/experiments (like DLC configs, bodyparts, etc.).
    """
    dlc_configs: List[Path] = []
    master_body_parts: List[str] = []
    active_body_parts: List[str] = []
    tracked_objects: List[str] = []

    # Global frame rate used unless an experiment specifies otherwise
    global_frame_rate: int = 60

    # Basic metadata about the project
    project_name: str
    date_created: datetime

    @validator("project_name")
    def check_project_name(cls, v: str) -> str:
        if not v or len(v) < 3:
            raise ValueError("Project name must be at least 3 characters.")
        return v


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
    source: ArenaImageSource = ArenaImageSource.UNKNOWN


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
            "global_frame_rate_enabled": True,
            "body_parts": [],
            "active_body_parts": [],
            "tracked_objects": []
        }
    )

    subjects: Dict[str, MouseMetadata] = Field(default_factory=dict)
    experiments: Dict[str, ExperimentMetadata] = Field(default_factory=dict)
    batches: Dict[str, BatchMetadata] = Field(default_factory=dict)

    # If desired, you could directly include ProjectMetadata or store a reference.
    project_metadata: Optional[ProjectMetadata] = None

    def get_experiments_by_mouse(self, mouse_id: str) -> List[ExperimentMetadata]:
        """
        Example advanced functionality. Can also be done as property-based logic.
        Moved from the metadata classes themselves, as recommended.
        """
        return [
            exp for exp in self.experiments.values()
            if exp.mouse_id == mouse_id
        ]

    def get_experiments_by_type(self, exp_type: ExperimentType) -> List[ExperimentMetadata]:
        return [
            exp for exp in self.experiments.values()
            if exp.type == exp_type
        ]

    