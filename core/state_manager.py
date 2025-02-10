"""State management for MUS1""" 

from PySide6.QtCore import QObject, Signal
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
import uuid
import yaml

from ...utils.logging_config import get_class_logger
from . import get_core_path
from . import metadata

class StateManager(QObject):
    """Centralized state management with Qt signals"""
    
    # Startup coordination signals
    core_ready = Signal()  # Core systems initialized
    project_view_ready = Signal()  # Project view ready to display
    
    # Project lifecycle signals
    project_created = Signal(Path)  # When new project created
    project_opened = Signal(Path)   # When existing project opened
    project_closed = Signal()       # When project closed
    project_state_changed = Signal(bool)  # Project loaded/unloaded

    # DLC and global settings signals
    dlc_config_loaded = Signal(Path)  # When DLC config is loaded
    frame_rate_changed = Signal(int)  # When global frame rate changes
    body_parts_updated = Signal(list)  # When body parts list changes
    tracked_objects_updated = Signal(list)  # When tracked objects change
    
    # Data modification signals
    mouse_added = Signal(str)       # mouse_id
    experiment_added = Signal(str, str)  # mouse_id, experiment_id
    batch_created = Signal(str)     # batch_id
    
    # Update signals
    experiment_updated = Signal(str)  # experiment_id
    batch_updated = Signal(str)     # batch_id
    settings_updated = Signal(dict)  # changed settings
    
    # State signals
    state_loaded = Signal()         # After loading state
    state_saved = Signal()          # After saving state
    
    def __init__(self):
        """Initialize state manager"""
        super().__init__()
        self.logger = get_class_logger(self.__class__)
        self.logger.info("Initializing StateManager")
        
        # Initialize empty project state
        self._project_state = metadata.ProjectState()
        self._current_project_path: Optional[Path] = None
        
        # Initialize settings
        self._global_frame_rate = 60
        self._active_body_parts: List[str] = []
        self._tracked_objects: List[str] = []
        
        # Load default settings if available
        self._load_default_settings()
        
        self.logger.info("StateManager initialization complete")
    
    def _load_default_settings(self) -> None:
        """Load default settings from config"""
        settings_path = get_core_path() / "config" / "default_settings.yaml"
        if settings_path.exists():
            with open(settings_path) as f:
                defaults = yaml.safe_load(f)
                self._global_frame_rate = defaults.get('frame_rate', 60)
    
    def initialize_state(self, state: metadata.ProjectState) -> None:
        """Initialize with new project state"""
        self._project_state = state
        self.state_loaded.emit()
        
    def get_current_project(self) -> Optional[Path]:
        """Get current project path"""
        return self._current_project_path
        
    # Mouse operations
    def add_mouse(self, metadata: metadata.MouseMetadata) -> None:
        """Add new mouse to state and notify UI"""
        # Add to state
        self._project_state.subjects[metadata.id] = metadata
        
        # Emit signals for UI update
        self.mouse_added.emit(metadata.id)
        
        # Update related UI elements
        self._update_mouse_lists()

    def _update_mouse_lists(self) -> None:
        """Update UI elements showing mouse lists"""
        mouse_ids = sorted(self._project_state.subjects.keys())
        self.mouse_list_updated.emit(mouse_ids)

    def get_mouse(self, mouse_id: str) -> Optional[metadata.MouseMetadata]:
        """Get mouse metadata by ID"""
        return self._project_state.subjects.get(mouse_id)
        
    def add_experiment(self, experiment: metadata.ExperimentMetadata) -> None:
        """Full validation workflow"""
        # 1. Base metadata validation
        valid_base, error_base = experiment.validate()
        if not valid_base:
            raise ValueError(f"Metadata validation failed: {error_base}")
        
        # 2. Plugin-specific validation
        if plugin := get_plugin(experiment.type):
            valid_plugin, error_plugin = plugin.validate_metadata(experiment)
            if not valid_plugin:
                raise ValueError(f"Plugin validation failed: {error_plugin}")
        
        # 3. Data integrity validation
        valid_data, error_data = self.data_manager.validate_experiment(experiment)
        if not valid_data:
            raise ValueError(f"Data validation failed: {error_data}")
        
        # 4. Process tracking data through DataManager
        tracking_data = self.data_manager.process_dlc_file(
            experiment.tracking_path, 
            experiment
        )
        experiment.tracking_data = tracking_data
        
        # 5. Store if all validations pass
        self._project_state.experiments[experiment.id] = experiment
        self.experiment_added.emit(experiment.id)
        
    def update_experiment_tracking(self, exp_id: str, 
                                 tracking_data: metadata.TrackingData) -> None:
        """Update experiment with tracking data"""
        if exp_id not in self._project_state.experiments:
            raise KeyError(f"Unknown experiment: {exp_id}")
            
        exp = self._project_state.experiments[exp_id]
        exp.tracking_data = tracking_data
        self.experiment_updated.emit(exp_id)
        
    # Batch operations
    def create_batch(self, metadata: metadata.BatchMetadata) -> None:
        """Create new analysis batch"""
        # Verify all experiments exist
        missing = metadata.experiment_ids - set(self._project_state.experiments.keys())
        if missing:
            raise ValueError(f"Unknown experiments: {missing}")
            
        self._project_state.batches[metadata.id] = metadata
        self.batch_created.emit(metadata.id)
        
    def update_batch_status(self, batch_id: str, status: str) -> None:
        """Update batch status"""
        if batch_id not in self._project_state.batches:
            raise KeyError(f"Unknown batch: {batch_id}")
            
        self._project_state.batches[batch_id].status = status
        self.batch_updated.emit(batch_id)
        
    # Settings operations
    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Update project settings"""
        self._project_state.settings.update(settings)
        self.settings_updated.emit(settings)
        
    def get_settings(self) -> Dict[str, Any]:
        """Get current project settings"""
        return self._project_state.settings.copy()
        
    # Project state operations
    def handle_project_creation(self, project_path: Path) -> None:
        """Handle new project being created"""
        self._current_project_path = project_path
        self.project_created.emit(project_path)
        
    def handle_project_open(self, project_path: Path) -> None:
        """Finalize project open sequence"""
        self._current_project_path = project_path
        self.project_opened.emit(project_path)
        self._verify_state_consistency()

    def _verify_state_consistency(self) -> None:
        """Validate loaded state relationships"""
        # Check experiment-mouse links
        for exp in self._project_state.experiments.values():
            if exp.mouse_id not in self._project_state.subjects:
                self.logger.warning(f"Orphaned experiment {exp.id} - missing mouse {exp.mouse_id}")
        
        # Check batch-experiment links
        for batch in self._project_state.batches.values():
            missing = batch.experiment_ids - set(self._project_state.experiments.keys())
            if missing:
                self.logger.warning(f"Batch {batch.id} references missing experiments: {missing}")
        
        # Check object role assignments: this is an optional field so we need to check for it
        for exp in self._project_state.experiments.values():
            if exp.type == 'NOR' and not exp.object_roles:
                self.logger.warning(f"NOR experiment {exp.id} missing object roles")
        
            # Validate tracking data references
            if exp.tracking_data and exp.tracking_data.frame_count == 0:
                self.logger.error(f"Experiment {exp.id} has empty tracking data")

    # DLC Configuration methods
    def load_dlc_config(self, config_path: Path) -> None:
        """Load DLC configuration without object filtering"""
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        body_parts = config.get('bodyparts', [])
        
        self.update_settings({
            'body_parts': body_parts,
            'active_body_parts': body_parts  # Default to all
        })
        self.dlc_config_loaded.emit(config_path)

    def _is_tracked_object(self, body_part: str) -> bool:
        return any(obj in body_part.lower() 
                   for obj in self._project_state.settings.get('object_keywords', []))

    #TODO: connect global fram rate selection to other parts of app if true (user chooses to use global frame rate)
    def set_global_frame_rate(self, frame_rate: int) -> None:
        """Set global frame rate for project"""
        if frame_rate <= 0:
            raise ValueError("Frame rate must be positive")
            
        self.update_settings({'frame_rate': frame_rate})
        self.frame_rate_changed.emit(frame_rate)
        
    def get_global_frame_rate(self) -> int:
        """Get current global frame rate"""
        return self._project_state.settings['frame_rate']

    # Body parts management
    def get_body_parts(self) -> List[str]:
        """Get current list of body parts"""
        return self._project_state.settings['body_parts'].copy()
        
    def update_body_parts(self, body_parts: List[str]) -> None:
        """Update body parts list"""
        self.update_settings({'body_parts': body_parts})
        self.body_parts_updated.emit(body_parts)
        
    def get_tracked_objects(self) -> List[str]:
        """Get current list of tracked objects"""
        return self._project_state.settings['tracked_objects'].copy()
        
    def update_tracked_objects(self, objects: List[str]) -> None:
        """Update tracked objects list"""
        self.update_settings({'tracked_objects': objects})
        self.tracked_objects_updated.emit(objects)

    # Settings validation
    def validate_experiment_settings(self, exp_type: str, body_parts: List[str]) -> bool:
        """Validate experiment has required body parts for type"""
        required = {
            'NOR': [familiarization, novel_object],  # fix spelling 
            'Open Field': ['time_tracked'] #TODO: we need to define what this is as either a global state for cutoff of amount of time tracked or user sets exact param he interested for that experiment 
        }
        return all(bp in body_parts for bp in required.get(exp_type, []))

    def set_active_body_parts(self, parts: List[str]) -> None:
        """Update active body parts for processing"""
        self._project_state.settings['active_body_parts'] = parts
        self.body_parts_updated.emit(parts)

    def get_required_body_parts(self, experiment_type: str) -> List[str]:
        """Get required body parts for experiment type"""
        return self._project_state.settings.get('required_body_parts', {}).get(experiment_type, [])

    def get_mouse_ids(self) -> List[str]:
        """Get sorted list of all mouse IDs"""
        return sorted(self._project_state.subjects.keys())

    def get_experiments_for_mouse(self, mouse_id: str) -> List[metadata.ExperimentMetadata]:
        """Get all experiments for a mouse"""
        return [exp for exp in self._project_state.experiments.values() 
                if exp.mouse_id == mouse_id]

    def add_tracked_object(self, obj_name: str) -> None:
        """Add user-defined object to tracking list"""
        if obj_name not in self._project_state.settings['tracked_objects']:
            self._project_state.settings['tracked_objects'].append(obj_name)
            self.tracked_objects_updated.emit(self._project_state.settings['tracked_objects'])

    def remove_tracked_object(self, obj_name: str) -> None:
        """Remove object from tracking list"""
        if obj_name in self._project_state.settings['tracked_objects']:
            self._project_state.settings['tracked_objects'].remove(obj_name)
            self.tracked_objects_updated.emit(self._project_state.settings['tracked_objects'])

    # Add these methods to ensure proper state transitions #TODO: current state of dropdowns for mouse IDs, bodyparts, objects, experiments, batches, etc. should be in StateManager and remove redundancy 
    def set_available_body_parts(self, parts: List[str]) -> None:
        """Single source of truth for body parts"""
        # Validate against current project schema
        required = self._project_state.settings.get("required_body_parts", [])
        missing = [bp for bp in required if bp not in parts]
        
        if missing:
            raise ValueError(f"Config missing required body parts: {missing}")
        
        self._project_state.settings.update({
            "available_body_parts": parts,
            "active_body_parts": parts  # Default to all
        })
        self.body_parts_updated.emit(parts)

    def query_experiments(self, criteria: Dict) -> List[metadata.ExperimentMetadata]:
        """Single query endpoint delegating to ProjectState"""
        return self._project_state.query_experiments(**criteria)

    def update_global_frame_rate(self, fps: int) -> None:
        """Update global frame rate with validation"""
        if not 1 <= fps <= 240:
            raise ValueError("Frame rate must be between 1-240 FPS")
        
        self.update_settings({'global_frame_rate': fps})
        self.settings_updated.emit({'global_frame_rate': fps})

    def validate_experiment_frame_rate(self, experiment: metadata.ExperimentMetadata) -> bool:
        """Validate experiment-specific frame rate"""
        if experiment.frame_rate and not 1 <= experiment.frame_rate <= 240:
            return False
        return True

    #TODO: add support for current lists

    def get_experiments_by_mouse(self, mouse_id: str) -> List[metadata.ExperimentMetadata]:
        """Indexed mouse experiment lookup"""
        return self._indexes['mouse_id'].get(mouse_id, [])

    def get_experiments_by_type(self, exp_type: str) -> List[metadata.ExperimentMetadata]:
        """Get all experiments of a specific type"""
        return [
            exp for exp in self.experiments.values()
            if exp.type == exp_type
        ]
    def get_experiments_by_age_range(self, min_age: int, max_age: int) -> List[metadata.ExperimentMetadata]:
        """Get experiments within age range in weeks""" #this is calcualted by the data manager based on the mouse birth date and the experiment date   
        return [
            exp for exp in self.experiments.values()
            if exp.age and min_age <= exp.age <= max_age
        ]
    def get_experiments_by_type_and_age_range(self, exp_type: str, min_age: int, max_age: int) -> List[metadata.ExperimentMetadata]:
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
        required_objects: Optional[List[str]] = None,
        sex: Optional[str] = None,  # Added to filter by mouse sex
        genotype: Optional[str] = None,  # Added to filter by genotype
        treatment: Optional[str] = None,  # Added to filter by treatment
        in_training_set: Optional[bool] = None  # Added to filter by training status
    ) -> List[metadata.ExperimentMetadata]:
        """Comprehensive experiment query with indexing
        
        All parameters are optional to match mouse schema flexibility.
        Age filtering requires mouse to have birth_date set.
        """
        # Use existing indexes where possible
        if mouse_id:
            candidates = self.get_experiments_by_mouse(mouse_id)
        elif exp_type:
            candidates = self.get_experiments_by_type(exp_type)
        else:
            candidates = list(self.experiments.values())
        
        results = []
        for exp in candidates:
            # Get associated mouse data
            mouse = self.subjects.get(exp.mouse_id)
            if not mouse:
                continue
            
            # Sequential filtering with optional field awareness
            if date_range and not (date_range[0] <= exp.date <= date_range[1]):
                continue
            
            if phase and exp.phase != phase:
                continue
            
            # Age filtering only if mouse has birth_date
            if (min_age is not None or max_age is not None) and not mouse.birth_date:
                continue
            
            age_weeks = self.data_manager.calculate_age_weeks(exp.mouse_id, exp.date)
            if min_age is not None and (age_weeks is None or age_weeks < min_age):
                continue
            if max_age is not None and (age_weeks is None or age_weeks > max_age):
                continue
            
            # Mouse attribute filtering
            if sex is not None and mouse.sex != sex:
                continue
            if genotype is not None and mouse.genotype != genotype:
                continue
            if treatment is not None and mouse.treatment != treatment:
                continue
            if in_training_set is not None and mouse.in_training_set != in_training_set:
                continue
            
            if required_objects and not all(obj in exp.object_roles for obj in required_objects):
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