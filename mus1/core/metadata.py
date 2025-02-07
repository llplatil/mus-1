"""Core metadata models for MUS1"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, List, Any, Optional, Tuple
import re
from collections import defaultdict
from ..utils import get_logger
import pandas as pd

logger = get_logger("core.metadata")

def init_metadata() -> bool:
    """Initialize metadata system
    
    Returns:
        bool: True if metadata system initialized successfully
    """
    try:
        logger.info("Initializing metadata system")
        
        # Verify all required dataclasses are properly defined
        required_classes = [
            MouseMetadata,
            ExperimentMetadata,
            BatchMetadata,
            ProjectState,
            PluginMetadata,
            TrackingData
        ]
        
        for cls in required_classes:
            if not hasattr(cls, '__dataclass_fields__'):
                logger.error(f"{cls.__name__} is not a proper dataclass")
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
    
@dataclass
class TrackingData:
    """Processed DLC tracking data for an experiment"""
    coordinates: Dict[str, Dict[str, List[float]]]  # body_part -> {x: [], y: []}
    likelihoods: Dict[str, List[float]]  # body_part -> [likelihood values]
    frame_count: int
    frame_rate: int
    duration: float  # User selected cutoff or calculated from frame_count/frame_rate
    @classmethod
    def from_dlc_csv(cls, csv_path: Path, body_parts: List[str], frame_rate: int) -> 'TrackingData':
        """Create from CSV with frame rate context"""
        # Read DLC CSV
        data = pd.read_csv(csv_path)
        frame_count = len(data)
        
        # Process coordinates and likelihoods
        coordinates = {}
        likelihoods = {}
        
        for part in body_parts:
            coordinates[part] = {
                'x': data[f'{part}_x'].tolist(),
                'y': data[f'{part}_y'].tolist()
            }
            likelihoods[part] = data[f'{part}_likelihood'].tolist()
            
        return cls(
            coordinates=coordinates,
            likelihoods=likelihoods,
            frame_rate=frame_rate,
            frame_count=frame_count,
            duration=frame_count / frame_rate
        )

@dataclass
class MouseMetadata:
    """Mouse/subject metadata"""
    # Required fields (no default)
    id: str  
    birth_date: datetime
    sex: str  # "M"/"F"
    
    # Optional fields (with defaults)
    genotype: Optional[str] = None
    notes: str = ""
    experiment_ids: Set[str] = field(default_factory=set)

    def validate(self) -> Tuple[bool, str]:
        """Validation rules specific to mouse data"""
        errors = []
        if not re.match(r"^[A-Z0-9\-]{3,20}$", self.id):
            errors.append("Invalid ID format")
        if self.sex.upper() not in {"M", "F"}:
            errors.append("Invalid sex")
        return len(errors) == 0, ", ".join(errors)

@dataclass
class ExperimentMetadata:
    """Experiment metadata with type-specific validation"""
    # Required fields
    id: str
    type: str  # Plugin identifier
    mouse_id: str
    date: datetime
    tracking_data: TrackingData
    
    # Optional fields
    phase: str = field(default="unset")
    object_roles: Dict[str, str] = field(default_factory=dict)
    frame_rate: Optional[int] = None
    start_time: float = 0.0  # Seconds
    end_time: Optional[float] = None
    duration: Optional[float] = None
    arena_image_path: Path = field(default=Path())

    @property
    def phase_type(self) -> str:
        """Get normalized phase type"""
        return self.phase.lower() if self.phase else "unset"
    
    def validate_phase(self) -> Tuple[bool, str]:
        """Phase validation if present"""
        if self.phase_type == "unset":
            return True, ""  # Phase not required for all experiments
            
        valid_phases = self._get_valid_phases()
        if self.phase_type not in valid_phases:
            return False, f"Invalid phase. Valid options: {valid_phases}"
        return True, ""

    def validate(self) -> Tuple[bool, str]:
        """Base validation for all experiments"""
        errors = []
        if not self.id:
            errors.append("Missing experiment ID")
        if not self.tracking_data:
            errors.append("Missing tracking data")
        return len(errors) == 0, " | ".join(errors)

    @property
    def analysis_ready(self) -> bool:
        """Quick check if ready for plugin processing"""
        return all([
            self.tracking_data,
            self.arena_image_path.exists(),
            len(self.object_roles) >= 2
        ])

    @property
    def age(self) -> Optional[float]:
        """Calculate age in weeks at experiment time"""
        if not hasattr(self, '_mouse'):
            return None
        delta = self.date - self._mouse.birth_date
        return delta.days / 7.0

    def _get_valid_phases(self) -> List[str]:
        """Get valid phases for this experiment type"""
        # Could be extended based on experiment type
        return ["habituation", "training", "test"]

@dataclass
class BatchMetadata:
    """Represents a group of experiments selected through UI criteria"""
    selection_criteria: Dict[str, Any]  # Saved search parameters
    experiment_ids: Set[str] = field(default_factory=set)
    analysis_type: str  # Plugin identifier
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ProjectState:
    """Global project state and configuration"""
    version: str = "0.1.0"
    last_modified: datetime = field(default_factory=datetime.now)
    
    settings: Dict[str, Any] = field(default_factory=lambda: {
        'global_frame_rate': 60,  # Default frame rate
        'global_frame_rate_enabled': True,
        'body_parts': [],  # Raw from DLC config
        'active_body_parts': [],  # User-selected subset
        'tracked_objects': [] 
    })
    
    subjects: Dict[str, MouseMetadata] = field(default_factory=dict)
    experiments: Dict[str, ExperimentMetadata] = field(default_factory=dict)
    batches: Dict[str, BatchMetadata] = field(default_factory=dict)
    
    # Quick lookup for mouse experiments
    @property
    def mouse_experiment_map(self) -> Dict[str, List[str]]:
        """Quick lookup: mouse_id -> [experiment_ids]"""
        mapping = defaultdict(list)
        for exp_id, exp in self.experiments.items():
            mapping[exp.mouse_id].append(exp_id)
        return mapping

    @property
    def experiment_mouse_map(self) -> Dict[str, str]:
        """Quick lookup: experiment_id -> mouse_id"""
        return {exp_id: exp.mouse_id for exp_id, exp in self.experiments.items()}

    def get_experiments_by_mouse(self, mouse_id: str) -> List[ExperimentMetadata]:
        """Indexed mouse experiment lookup"""
        return self._indexes['mouse_id'].get(mouse_id, [])

    def get_experiments_by_type(self, exp_type: str) -> List[ExperimentMetadata]:
        """Get all experiments of a specific type"""
        return [
            exp for exp in self.experiments.values()
            if exp.type == exp_type
        ]
    def get_experiments_by_age_range(self, min_age: int, max_age: int) -> List[ExperimentMetadata]:
        """Get experiments within age range in weeks""" #this is calcualted by the data manager based on the mouse birth date and the experiment date   
        return [
            exp for exp in self.experiments.values()
            if exp.age and min_age <= exp.age <= max_age
        ]
    def get_experiments_by_type_and_age_range(self, exp_type: str, min_age: int, max_age: int) -> List[ExperimentMetadata]:
        """Get experiments of a specific type within age range in weeks"""
        return [
            exp for exp in self.experiments.values()
            if exp.type == exp_type and exp.age and min_age <= exp.age <= max_age
        ]

    def query_experiments(
        self,
        *,
        mouse_id: Optional[str] = None,
        exp_type: Optional[str] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        phase: Optional[str] = None,
        required_objects: Optional[List[str]] = None
    ) -> List[ExperimentMetadata]:
        """Comprehensive experiment query with indexing"""
        # Use existing indexes where possible
        if mouse_id:
            candidates = self.get_experiments_by_mouse(mouse_id)
        elif exp_type:
            candidates = self.get_experiments_by_type(exp_type)
        else:
            candidates = list(self.experiments.values())
        
        results = []
        for exp in candidates:
            # Sequential filtering
            if date_range and not (date_range[0] <= exp.date <= date_range[1]):
                continue
            if phase and exp.phase != phase:
                continue
            if min_age is not None and exp.age < min_age:
                continue
            if max_age is not None and exp.age > max_age:
                continue
            if required_objects and not all(obj in exp.object_roles 
                                         for obj in required_objects):
                continue
            
            results.append(exp)
        
        return sorted(results, key=lambda x: x.date)

    def __post_init__(self):
        """Initialize query indexes"""
        self._indexes = {
            'mouse_id': defaultdict(list),
            'exp_type': defaultdict(list),
            'phase': defaultdict(list)
        }
        self._build_indexes()

    def _build_indexes(self):
        """Populate query indexes"""
        for exp in self.experiments.values():
            self._indexes['mouse_id'][exp.mouse_id].append(exp)
            self._indexes['exp_type'][exp.type].append(exp) 
            self._indexes['phase'][exp.phase].append(exp)

__all__ = [
    'init_metadata',
    'MouseMetadata',
    'ExperimentMetadata',
    'BatchMetadata',
    'ProjectState',
    'PluginMetadata',
    'TrackingData'
]