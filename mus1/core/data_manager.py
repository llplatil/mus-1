"""
Data management and processing for MUS1
Handles data loading, validation, and processing.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
import yaml
import matplotlib.pyplot as plt
from ...utils.logging_config import get_class_logger, get_logger
from . import metadata  # Import entire metadata module
from .state_manager import StateManager
from ..plugins import get_plugin
import re
import shutil
import json
from .metadata import ProjectState, ExperimentMetadata, TrackingData

class DataManager: 
    """Manages data validation, processing, and analysis"""
    
    def __init__(self, state_manager: StateManager):
        self.logger = get_class_logger(self.__class__)
        self.logger.info("Initializing DataManager")
        
        if not isinstance(state_manager, StateManager):
            raise TypeError("state_manager must be StateManager instance")
            
        self.state_manager = state_manager
        self._likelihood_threshold = 0.9 #TODO: this is should be an optiona global setting that will be used to filter low confidence points in tracking data. We will need to make this a per experiment setting later. 
        self._schema = self._load_experiment_schema()
        
        # Will be set when DLC config is loaded
        self.dlc_bodyparts = []
        self.tracked_objects = []  # Store object names from DLC config
        
        self.logger.info("DataManager initialization complete")

    def _load_experiment_schema(self) -> Dict:
        """Load experiment schema from YAML config"""
        schema_path = Path(__file__).parent.parent / "config/experiment_schema.yml"
        try:
            with open(schema_path) as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load schema: {str(e)}")
            return {}

    def validate_tracking_data(self, data: TrackingData) -> bool:
        """Essential quality checks"""
        return all([
            data.frame_count > 0,
            data.duration > 0,
            len(data.coordinates) >= self._schema.get('min_body_parts', 1)
        ])

    def load_tracking_data(self, file_path: Path, body_parts: Optional[List[str]] = None) -> TrackingData:
        """Load and validate tracking data from file"""
        try:
            # Get parts to load
            parts_to_load = body_parts or self.state_manager.get_active_body_parts()
            
            # Read DLC CSV
            df = pd.read_csv(file_path, header=[0,1,2])
            scorer = df.columns.get_level_values(0)[0]
            
            # Extract data
            coordinates = {}
            likelihoods = {}
            
            for part in parts_to_load:
                x = df[scorer][part]['x'].values
                y = df[scorer][part]['y'].values
                likelihood = df[scorer][part]['likelihood'].values
                
                # Filter low confidence points
                mask = likelihood < self._likelihood_threshold
                x[mask] = np.nan
                y[mask] = np.nan
                
                coordinates[part] = {'x': x.tolist(), 'y': y.tolist()}
                likelihoods[part] = likelihood.tolist()
            
            # Create tracking data object
            frame_count = len(df)
            frame_rate = self._detect_frame_rate(df) or self.state_manager._global_frame_rate
            duration = frame_count / frame_rate
            
            return TrackingData(
                coordinates=coordinates,
                likelihoods=likelihoods,
                frame_count=frame_count,
                frame_rate=frame_rate,
                duration=duration
            )
            
        except Exception as e:
            self.logger.error(f"Failed to load tracking data: {str(e)}")
            raise

    def _detect_frame_rate(self, df: pd.DataFrame) -> Optional[int]:
        """Detect frame rate from tracking data"""
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                time_diff = df.index.to_series().diff().median()
                return int(round(1 / time_diff.total_seconds()))
            return None
        except:
            return None

    def process_batch_data(self, batch_id: str, save_dir: Path) -> Dict:
        """Use active body parts if specified"""
        active_parts = self.state_manager._project_state.settings.get('active_body_parts')
        body_parts = active_parts or self.get_body_parts()
        
        # Processing logic using filtered body_parts...

    def _process_subject_experiments(
        self,
        subject_id: str,
        experiments: List[ExperimentMetadata],
        batch: BatchMetadata,
        save_dir: Optional[Path]
    ) -> Dict[str, Any]:
        """Process experiments for a single subject"""
        subject_data = {
            'experiments': {},
            'timeline': [],
            'plugin_results': {}
        }
        
        # Sort experiments by date
        experiments.sort(key=lambda x: x.date)
        
        for exp in experiments:
            # Process experiment data
            if exp.tracking_data:
                # Validate tracking data first
                is_valid, error = self.validate_tracking_data(
                    exp.tracking_data
                )
                if not is_valid:
                    self.logger.warning(f"Skipping {exp.id}: {error}")
                    continue
                    
                # Process with plugin
                subject_data['plugin_results'][exp.id] = self._process_with_plugin(
                    exp, batch.plugin_params
                )
            
            # Add to timeline
            subject_data['experiments'][exp.id] = {
                'date': exp.date,
                'phase': exp.phase,
                'age_weeks': self._calculate_age_weeks(
                    exp.date,
                    self.state_manager._subjects[subject_id].birth_date
                )
            }
            
            subject_data['timeline'].append({
                'exp_id': exp.id,
                'age_weeks': subject_data['experiments'][exp.id]['age_weeks'],
                'phase': exp.phase
            })
            
        return subject_data

    def _process_with_plugin(self, exp: ExperimentMetadata, params: Dict[str, Any]) -> Any:
        """Process experiment data with the selected plugin"""
        plugin = get_plugin(exp.plugin_type)()
        return plugin.process_experiment(exp.tracking_data, params)

    def _calculate_age_weeks(self, date: datetime, birth_date: datetime) -> int:
        """Calculate age in weeks at a given date"""
        age_delta = date - birth_date
        return age_delta.days // 7  # Convert to weeks

    def detect_frame_rate(self, df: pd.DataFrame) -> int:
        """Detect frame rate from tracking data timestamps if available"""
        try:
            # If index is timestamp-based, calculate FPS
            if isinstance(df.index, pd.DatetimeIndex):
                time_diff = df.index.to_series().diff().median()
                return int(round(1 / time_diff.total_seconds()))
            # If index is frame numbers, try to detect from metadata
            # ... add more detection methods as needed
            
            # If can't detect, return None to use global default
            return None
        except Exception as e:
            self.logger.warning(f"Could not detect frame rate: {str(e)}")
            return None

    def load_dlc_tracking(self, file_path: Path, frame_rate: Optional[int] = None) -> Dict[str, Any]:
        """Load and process DLC tracking data"""
        if not file_path.exists():
            raise FileNotFoundError(f"Tracking file not found: {file_path}")
        if not file_path.suffix == '.csv':
            raise ValueError(f"Expected CSV file, got: {file_path.suffix}")
        try:
            df = pd.read_csv(file_path, header=[0,1,2], index_col=0)
            
            # Get frame rate based on hierarchy without detection
            effective_frame_rate = frame_rate or self.state_manager.get_frame_rate()
            
            # Basic validation against available parts first
            scorer = df.columns.get_level_values(0)[0]
            available_parts = self.state_manager.get_available_body_parts()
            
            file_parts = set(df.columns.get_level_values(1))
            if not file_parts.issubset(set(available_parts)):
                invalid_parts = file_parts - set(available_parts)
                raise ValueError(f"Invalid body parts in tracking data: {invalid_parts}")
            
            # Get active parts for processing
            active_parts = self.state_manager.get_active_body_parts()
            
            frame_count = len(df)
            processed_data = {
                'coordinates': {},
                'likelihoods': {},
                'frame_count': frame_count,
                'frame_rate': effective_frame_rate,
                'duration': frame_count // effective_frame_rate,
                'processed_parts': active_parts.copy()
            }
            
            # Only process active body parts
            for body_part in active_parts:
                if body_part in file_parts:
                    x = df[scorer][body_part]['x'].values
                    y = df[scorer][body_part]['y'].values
                    likelihood = df[scorer][body_part]['likelihood'].values
                    
                    # Handle missing/low confidence points
                    mask = likelihood < self._likelihood_threshold
                    x[mask] = np.nan
                    y[mask] = np.nan
                    
                    processed_data['coordinates'][body_part] = {
                        'x': x.tolist(),
                        'y': y.tolist()
                    }
                    processed_data['likelihoods'][body_part] = likelihood.tolist()
            
            return processed_data
            
        except Exception as e:
            self.logger.error(f"Failed to load tracking data: {str(e)}")
            raise

    def validate_tracking_data(self, data: TrackingData, experiment_type: str) -> Tuple[bool, str]:
        """Final quality check before analysis"""
        try:
        
          if not data.frame_count > 0:
              return False, "No frames detected"
          if data.duration <= 0:
              return False, "Invalid duration"
         return True, ""

    def _get_body_parts(self, df: pd.DataFrame) -> List[str]:
        """Extract unique body parts from DLC dataframe"""
        return list(set(df.columns.get_level_values(1)))

    def get_frame_rate(self) -> int:
        """Get current frame rate setting"""
        return self._frame_rate

    def detect_frame_rate_for_experiment(self, experiment_id: str) -> Optional[int]:
        """Lazy frame rate detection - only when requested"""
        try:
            exp = self.state_manager._experiments.get(experiment_id)
            if not exp or not exp.tracking_data:
                return None
            
            raw_data = exp.tracking_data.get('raw_data')
            if not raw_data:
                return None
            
            return self.detect_frame_rate(raw_data)
        except Exception as e:
            self.logger.warning(f"Frame rate detection failed: {str(e)}")
            return None

    def reprocess_tracking_data(self, experiment_id: str) -> None:
        """Reprocess experiment data with current active body parts"""
        try:
            exp = self.state_manager._experiments.get(experiment_id)
            if not exp or not exp.tracking_data or 'raw_data' not in exp.tracking_data:
                return
                
            # Get current active parts
            active_parts = self.state_manager.get_active_body_parts()
            current_parts = exp.tracking_data.get('processed_parts', [])
            
            # Only reprocess if active parts have changed
            if set(active_parts) != set(current_parts):
                raw_data = exp.tracking_data['raw_data']
                frame_rate = exp.get_effective_frame_rate()
                
                # Reprocess with current active parts
                new_data = self.load_dlc_tracking(raw_data, frame_rate)
                
                # Update experiment data
                exp.tracking_data.update({
                    'coordinates': new_data['coordinates'],
                    'likelihoods': new_data['likelihoods'],
                    'processed_parts': active_parts
                })
                
                self.state_manager.experiment_updated.emit(experiment_id)
                
        except Exception as e:
            self.logger.error(f"Failed to reprocess tracking data: {str(e)}")
            raise

    def load_dlc_config(self, config_path: Path) -> Dict:
        """Return structured config data without state updates"""
        config = yaml.safe_load(config_path.read_text())
        
        return {
            "body_parts": config.get("bodyparts", []),
            "objects": self._detect_objects(
                config.get("bodyparts", []),
                self._schema["object_keywords"]
            ),
            "experiment_settings": self._match_experiment_requirements(config)
        }

    def _detect_objects(self, body_parts: List[str], keywords: List[str]) -> List[str]:
        """Detect objects in body parts list"""
        return [part for part in body_parts if any(keyword in part.lower() for keyword in keywords)]

    def _match_experiment_requirements(self, config: Dict) -> Dict:
        """Match experiment requirements based on config"""
        # Implementation of this method depends on the structure of the config
        # This is a placeholder and should be implemented based on your specific config format
        return {}

    def validate_dlc_csv(self, file_path: Path, exp_type: str) -> Tuple[bool, Optional[str]]:
        """Validate DLC CSV matches config and has minimum required points"""
        if not self.dlc_bodyparts:
            return False, "No DLC config loaded - please load config first"
            
        try:
            # Read CSV headers
            df = pd.read_csv(file_path, header=[0,1,2], nrows=1)
            csv_parts = set(df.columns.get_level_values(1))
            
            # Validate against DLC config
            if not csv_parts.issubset(set(self.dlc_bodyparts)):
                invalid = csv_parts - set(self.dlc_bodyparts)
                return False, f"CSV contains parts not in DLC config: {invalid}"
                
            # Check minimum required points
            required_count = self._schema["experiments"][exp_type]["required_count"]
            if len(csv_parts) < required_count:
                return False, f"Need at least {required_count} tracked points, found {len(csv_parts)}"
                
            return True, None
            
        except Exception as e:
            return False, f"Failed to validate CSV: {str(e)}"

    def get_frame_count(self, file_path: Path) -> int:
        """Get total frame count without loading entire file"""
        try:
            # Use pandas to count lines efficiently
            with open(file_path) as f:
                return sum(1 for _ in f) - 3  # Subtract header rows
        except Exception as e:
            self.logger.error(f"Failed to get frame count: {str(e)}")
            raise

    def load_tracking_for_visualization(
        self,
        file_path: Path,
        body_parts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Load tracking data optimized for visualization.
        Only loads specified body parts or active body parts if none specified.
        Returns processed coordinates ready for plotting.
        """
        try:
            # Use only specified body parts or active ones
            parts_to_load = body_parts or self.state_manager.get_active_body_parts()
            
            # Read only needed columns for memory efficiency
            usecols = []
            scorer = None  # Will be set from first row
            
            # First read header to get scorer
            df_header = pd.read_csv(file_path, nrows=0)
            scorer = df_header.columns.get_level_values(0)[0]
            
            for part in parts_to_load:
                usecols.extend([
                    (scorer, part, 'x'),
                    (scorer, part, 'y'),
                    (scorer, part, 'likelihood')
                ])
            
            df = pd.read_csv(
                file_path,
                header=[0,1,2],
                usecols=usecols
            )
            
            return self._process_tracking_data(df, parts_to_load, scorer)
            
        except Exception as e:
            self.logger.error(f"Failed to load tracking for visualization: {str(e)}")
            raise

    def _process_tracking_data(
        self,
        df: pd.DataFrame,
        parts_to_load: List[str],
        scorer: str
    ) -> Dict[str, Any]:
        """Process loaded tracking data into standard format"""
        plot_data = {
            'coordinates': {},
            'frame_count': len(df)
        }
        
        for part in parts_to_load:
            x = df[scorer][part]['x'].values
            y = df[scorer][part]['y'].values
            likelihood = df[scorer][part]['likelihood'].values
            
            # Filter low confidence points
            mask = likelihood < self._likelihood_threshold
            x[mask] = np.nan
            y[mask] = np.nan
            
            plot_data['coordinates'][part] = {
                'x': x.tolist(),
                'y': y.tolist()
            }
        
        return plot_data

    def validate_experiment_type(self, exp_type: str, phase: str) -> Tuple[bool, str]:
        """Validate experiment type and phase"""
        # Get available body parts from state manager
        available_parts = set(self.state_manager.get_available_body_parts())
        
        # Check experiment type exists
        if exp_type not in self._schema["experiments"]:
            return False, f"Invalid experiment type: {exp_type}"
        
        # Check phase is valid for type
        valid_phases = self._schema["experiments"][exp_type]["phases"]
        if phase not in valid_phases:
            return False, f"Invalid phase '{phase}' for {exp_type}. Valid phases: {valid_phases}"
        
        # Check required body parts are available
        required_parts = set(self._schema["experiments"][exp_type]["required_body_parts"])
        if not required_parts.issubset(available_parts):
            missing = required_parts - available_parts
            return False, f"Missing required body parts for {exp_type}: {missing}"
        
        return True, ""

    def get_required_objects(self, exp_type: str) -> List[str]:
        """Get required tracked objects for experiment type"""
        if exp_type not in self._schema["experiments"]:
            raise ValueError(f"Invalid experiment type: {exp_type}")
        return self._schema["experiments"][exp_type]["required_body_parts"]

    def _save_movement_plot(
        self,
        coordinates: Dict[str, List[float]],
        arena_image: Path,
        save_path: Path
    ) -> None:
        """Generate and save movement plot overlaid on arena image"""
        try:
            # Load arena image
            img = plt.imread(str(arena_image))
            
            # Create plot
            fig, ax = plt.subplots()
            ax.imshow(img)
            
            # Plot movement path
            ax.plot(coordinates['x'], coordinates['y'], 'r-', alpha=0.5, linewidth=1)
            
            # Save and close
            plt.savefig(save_path)
            plt.close(fig)
            
        except Exception as e:
            self.logger.error(f"Failed to save movement plot: {str(e)}")
            raise

    def get_experiment_defaults(self, exp_type: str) -> Dict[str, Any]:
        """Get default settings for experiment type"""
        if exp_type not in self._schema["experiments"]:
            raise ValueError(f"Invalid experiment type: {exp_type}")
            
        return {
            'phases': self._schema["experiments"][exp_type]["phases"],
            'optional_objects': self._schema["experiments"][exp_type]["object_roles"]["optional"],
            'default_length': self._schema["experiments"][exp_type]["default_length"]
        }

    def validate_project_state(self) -> Tuple[bool, List[str]]:
        """Validate loaded project state"""
        errors = []
        
        # Check experiments have valid types/phases
        for exp_id, exp in self.state_manager._experiments.items():
            is_valid, error = self.validate_experiment_type(exp.type, exp.phase)
            if not is_valid:
                errors.append(f"Experiment {exp_id}: {error}")
                
        # Check required objects are in available body parts
        available_parts = set(self.state_manager.get_available_body_parts())
        for exp_type in self._schema["experiments"]:
            required = set(self._schema["experiments"][exp_type]["required_body_parts"])
            if not required.issubset(available_parts):
                missing = required - available_parts
                errors.append(f"Missing required body parts for {exp_type}: {missing}")
                
        return len(errors) == 0, errors

    def calculate_age_at_date(self, birth_date: datetime, test_date: datetime) -> Optional[int]:
        """Calculate age in weeks at test date"""
        if not birth_date or not test_date:
            return None
        age_delta = test_date - birth_date
        return age_delta.days // 7  # Convert to weeks
    
    def get_experiment_age(self, experiment: ExperimentMetadata, subject: MouseMetadata) -> Optional[int]:
        """Get subject age at time of experiment"""
        if not subject.birth_date or not experiment.date:
            return None
        return self.calculate_age_at_date(subject.birth_date, experiment.date)

    def set_data_root(self, project_root: Path) -> None:
        """Set data root directory based on project location"""
        self.data_root = project_root / "data"
        self.data_root.mkdir(exist_ok=True)

    def prepare_project_directory(self, project_path: Path) -> None:
        """Prepare directory for new project"""
        try:
            if project_path.exists():
                raise ValueError(f"Project already exists at {project_path}")
            
            # Create standard project structure
            self._create_project_structure(project_path)
            
            # Set this as current data root
            self.set_data_root(project_path)
            
            self.logger.info(f"Prepared project directory at {project_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to prepare project directory: {str(e)}")
            raise

    def _create_project_structure(self, path: Path) -> None:
        """Create standard project directory structure"""
        try:
            path.mkdir(parents=True)
            (path / "subjects").mkdir()
            (path / "experiments").mkdir()
            (path / "config").mkdir()
            (path / "data").mkdir()
            (path / "batches").mkdir()
            
            self.logger.debug(f"Created project structure in {path}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to create project structure: {str(e)}")

    def validate_project_directory(self, path: Path) -> bool:
        """Checks path has MUS1 project structure"""
        # Doesn't need to know about projects_root, just validates any given path
        try:
            if not path.is_dir():
                self.logger.warning("Project path is not a directory")
                return False
            
            # Check for required directories
            required_dirs = ["subjects", "experiments", "config", "data", "batches"]
            for dir_name in required_dirs:
                if not (path / dir_name).is_dir():
                    self.logger.warning(f"Missing required directory: {dir_name}")
                    return False
            
            # Check for project config
            if not (path / "config" / "project_config.yaml").exists():
                self.logger.warning("Missing project configuration file")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Project validation failed: {str(e)}")
            return False

    def load_project_config(self, path: Path) -> Dict[str, Any]:
        """Load project configuration"""
        config_path = path / "config" / "project_config.yaml"
        if not config_path.exists():
            raise FileNotFoundError("Project config missing")
        
        with open(config_path) as f:
            return yaml.safe_load(f)

    def load_project_state(self, path: Path) -> ProjectState:
        """Load serialized project state"""
        state_file = path / "state" / "latest.json"
        if not state_file.exists():
            return ProjectState()  # Return fresh state
        
        with open(state_file) as f:
            state_dict = json.load(f)
        
        # Convert nested dataclasses
        return self._deserialize_state(state_dict)

    def _deserialize_state(self, state_dict: Dict) -> ProjectState:
        """Deserialize project state with tracking data"""
        experiments = {}
        for exp_id, exp_data in state_dict.get('experiments', {}).items():
            if 'tracking_data' in exp_data:
                exp_data['tracking_data'] = TrackingData(**exp_data['tracking_data'])
            experiments[exp_id] = ExperimentMetadata(**exp_data)
            
        return ProjectState(**state_dict)

    def get_effective_frame_rate(self, experiment: ExperimentMetadata) -> int:
        """Resolve frame rate hierarchy"""
        return next((
            rate for rate in [
                experiment.frame_rate,
                self.state_manager.settings.get('global_frame_rate'),
                60  # Final fallback
            ] if rate is not None
        ), 60)

    def calculate_experiment_duration(self, experiment: ExperimentMetadata) -> float:
        """Calculate duration from available data"""
        # Priority 1: User-specified duration
        if experiment.duration:
            return experiment.duration
            
        # Priority 2: Tracking data frames
        if experiment.tracking_data and experiment.tracking_data.frame_count:
            return experiment.tracking_data.frame_count / self.get_effective_frame_rate(experiment)
            
        # Priority 3: Start/end times
        if experiment.end_time:
            return experiment.end_time - experiment.start_time
            
        return 0.0

    def process_dlc_file(self, file_path: Path, experiment: ExperimentMetadata) -> TrackingData:
        """End-to-end DLC file processing with validation"""
        df = self._read_dlc_csv(file_path)
        self._validate_dlc_structure(df)
        
        coordinates, likelihoods = self._parse_dlc_data(df)
        frame_count = len(next(iter(coordinates.values())))
        frame_rate = self.get_effective_frame_rate(experiment)
        
        tracking_data = TrackingData(
            coordinates=coordinates,
            likelihoods=likelihoods,
            frame_count=frame_count,
            frame_rate=frame_rate,
            duration=frame_count / frame_rate
        )
        
        if not self.validate_tracking_data(tracking_data):
            raise ValueError("Tracking data validation failed")
            
        return tracking_data

    def _read_dlc_csv(self, path: Path) -> pd.DataFrame:
        """Read raw DLC CSV into DataFrame"""
        try:
            return pd.read_csv(path, header=[0,1,2], index_col=0)
        except Exception as e:
            self.logger.error(f"CSV read failed: {str(e)}")
            raise

    def _validate_dlc_structure(self, df: pd.DataFrame) -> None:
        """Validate basic DLC file structure"""
        if df.empty or len(df.columns.levels) != 3:
            raise ValueError("Invalid DLC file structure")

    def _parse_dlc_data(self, df: pd.DataFrame) -> Tuple[Dict, Dict]:
        """Extract coordinates and likelihoods"""
        scorer = df.columns.get_level_values(0)[0]
        coordinates = {}
        likelihoods = {}
        
        for bodypart in df.columns.get_level_values(1).unique():
            coords = df[scorer][bodypart]
            coordinates[bodypart] = {
                'x': coords['x'].tolist(),
                'y': coords['y'].tolist()
            }
            likelihoods[bodypart] = coords['likelihood'].tolist()
            
        return coordinates, likelihoods

    def calculate_duration(self, frame_count: int, experiment: ExperimentMetadata) -> float:
        """Pure duration calculation"""
        return frame_count / self.get_effective_frame_rate(experiment)

