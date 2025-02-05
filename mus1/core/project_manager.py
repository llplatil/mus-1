"""
Project management for MUS1
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime
import yaml
import json
import shutil
import uuid
import re

from ...utils.logging_config import get_class_logger, get_logger
from .metadata import (
    MouseMetadata,
    ExperimentMetadata,
    BatchMetadata,
    ProjectState
)
from .state_manager import StateManager
from .data_manager import DataManager
import numpy as np
import dataclasses
from .metadata import MouseMetadata, ExperimentMetadata, BatchMetadata, TrackingData, ProjectState

class ProjectManager:
    """Manages project configuration and file operations"""
    
    def __init__(self, state_manager: 'StateManager', data_manager: 'DataManager'):
        """Initialize project manager"""
        self.logger = get_class_logger(self.__class__)
        self.logger.info("Initializing ProjectManager")
        
        if not isinstance(state_manager, StateManager):
            raise TypeError("state_manager must be StateManager instance")
        if not isinstance(data_manager, DataManager):
            raise TypeError("data_manager must be DataManager instance")
            
        self.state_manager = state_manager
        self.data_manager = data_manager
        
        # Default to user's home directory
        self.projects_root = Path.home() / "mus1_projects"
        self.projects_root.mkdir(exist_ok=True)  # Creates if missing
        
        self.project_root = None
        self.dlc_config_path: Optional[Path] = None
        self.logger.info(f"Projects directory: {self.projects_root}")
        
        self.logger.info("ProjectManager initialization complete")
        self.logger.debug("Connecting to StateManager signals")
        
        # Connect signals
        self._connect_signals()

    def _connect_signals(self):
        """Connect to state manager signals"""
        self.logger.debug("Connecting to StateManager signals")
        self.state_manager.mouse_added.connect(self._on_mouse_added)
        self.state_manager.experiment_added.connect(self._on_experiment_added)
        self.state_manager.batch_created.connect(self._on_batch_created)
        self.state_manager.experiment_updated.connect(self._on_experiment_updated)

    def set_projects_root(self, path: Path) -> None:
        """Change root directory for all projects"""
        if not path.exists():
            path.mkdir(parents=True)
        self.projects_root = path
        self.logger.info(f"Changed projects root to: {path}")

    def create_new_project(self, project_name: str) -> Path:
        """Create new MUS1 project with standard structure"""
        try:
            # 1. Sanitize name and create path
            safe_name = re.sub(r'[^\w\-]', '_', project_name)
            project_path = self.projects_root / safe_name
            
            if project_path.exists():
                raise ValueError(f"Project '{project_name}' already exists")
            
            # 2. Delegate directory creation to DataManager
            self.data_manager.prepare_project_directory(project_path)
            
            # 3. Initialize project config
            self._create_project_config()
            
            # 4. Update state
            self.state_manager.handle_project_creation(project_path)
            
            # Set as current project
            self.project_root = project_path
            
            self.logger.info(f"Created new project at {project_path}")
            return project_path
            
        except Exception as e:
            self.logger.error(f"Failed to create new project: {str(e)}")
            raise

    def open_existing_project(self, path: Path) -> None:
        """Open and initialize existing project"""
        try:
            # Delegate validation to DataManager
            if not self.data_manager.validate_project_directory(path):
                raise ValueError("Invalid project directory structure")
            
            # Set project root through DataManager
            self.data_manager.set_data_root(path)
            self.project_root = path
            
            # Load through unified method
            self.load_project(path)
            
            # Notify state manager after full load
            self.state_manager.handle_project_open(path)
            
        except Exception as e:
            self.logger.error(f"Failed to open project: {str(e)}")
            self._cleanup_failed_open()
            raise

    def _cleanup_failed_open(self) -> None:
        """Reset state after failed open"""
        self.project_root = None
        self.state_manager.initialize_state(ProjectState())  # Reset to empty

    def load_project(self, path: Path) -> None:
        """Load project data into managers"""
        try:
            # Load through DataManager's new interface
            config = self.data_manager.load_project_config(path)
            state = self.data_manager.load_project_state(path)
            
            # Update managers
            self.state_manager.initialize_state(state)
            
            # Load DLC config if exists
            dlc_config = path / "config" / "dlc_config.yaml"
            if dlc_config.exists():
                self.data_manager.load_dlc_config(dlc_config)
            
        except Exception as e:
            self.logger.error(f"Project load failed: {str(e)}")
            raise

    def add_mouse(self, mouse_id: str, metadata_dict: Optional[Dict] = None) -> str:
        """Add new mouse to project with optional metadata"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
            
        try:
            # Create mouse metadata
            metadata = MouseMetadata(
                id=mouse_id,
                **metadata_dict if metadata_dict else {}
            )
            
            # Create mouse directory structure first
            mouse_dir = self.project_root / "subjects" / mouse_id
            mouse_dir.mkdir(parents=True)
            (mouse_dir / "experiments").mkdir()
            
            # Save mouse metadata to file
            self._save_mouse_metadata(mouse_id, metadata)
            
            # Register with state manager after directory creation
            return self.state_manager.add_mouse(metadata)
            
        except Exception as e:
            self.logger.error(f"Failed to add mouse: {str(e)}")
            raise

    def _save_mouse_metadata(self, mouse_id: str, metadata: MouseMetadata) -> None:
        """Save mouse metadata to file"""
        metadata_file = self.project_root / "subjects" / mouse_id / "metadata.yaml"
        
        # Convert to dict, handling datetime
        metadata_dict = {
            'id': metadata.id,
            'sex': metadata.sex,
            'birth_date': metadata.birth_date.isoformat() if metadata.birth_date else None,
            'genotype': metadata.genotype,
            'in_training_set': metadata.in_training_set,
            'experiment_ids': list(metadata.experiment_ids)
        }
        
        with open(metadata_file, 'w') as f:
            yaml.dump(metadata_dict, f)

    def add_experiment(
        self,
        mouse_id: str,
        tracking_csv: Path,
        arena_image: Path,
        exp_type: str,
        phase: str,
        date: Optional[datetime] = None,
        frame_rate: Optional[int] = None,
        object_roles: Optional[Dict[str, str]] = None
    ) -> str:
        """Add new experiment with optional object role definitions"""
        if not self.project_root:
            raise RuntimeError("No project loaded")

        try:
            # 1. Validate inputs
            if mouse_id not in self.state_manager._subjects:
                raise ValueError(f"Mouse {mouse_id} not found")

            # 2. Validate experiment type and phase
            is_valid, error_msg = self.data_manager.validate_experiment_type(exp_type, phase)
            if not is_valid:
                raise ValueError(error_msg)

            # 3. Validate DLC CSV structure and required objects
            is_valid, error_msg = self.data_manager.validate_dlc_csv(tracking_csv, exp_type)
            if not is_valid:
                raise ValueError(f"Invalid tracking data: {error_msg}")

            # 4. Create experiment directory
            exp_id = str(uuid.uuid4())
            exp_dir = self._create_experiment_directory(mouse_id, exp_id)
            
            # 5. Copy files to project
            arena_dest = exp_dir / "arena.png"
            tracking_dest = exp_dir / "tracking.csv"
            shutil.copy2(arena_image, arena_dest)
            shutil.copy2(tracking_csv, tracking_dest)

            # 6. Get frame count without loading full file
            frame_count = self.data_manager.get_frame_count(tracking_dest)

            # 7. Create experiment metadata
            metadata = ExperimentMetadata(
                id=exp_id,
                date=date or datetime.now(),
                type=exp_type,
                phase=phase,
                mouse_id=mouse_id,
                arena_image_path=arena_dest,
                frame_rate=frame_rate,
                frame_count=frame_count,
                object_roles=object_roles or {}
            )

            # 8. Register with state manager
            return self.state_manager.add_experiment(metadata)

        except Exception as e:
            # Clean up on failure
            if 'exp_dir' in locals() and exp_dir.exists():
                shutil.rmtree(exp_dir)
            raise RuntimeError(f"Failed to add experiment: {str(e)}")

    def load_dlc_config(self, config_path: Path) -> None:
        """Orchestrate full config loading workflow"""
        try:
            # 1. Validate file structure
            if not self._validate_dlc_config_structure(config_path):
                raise ValueError("Invalid DLC config structure")
            
            # 2. Parse through DataManager
            config_data = self.data_manager.load_dlc_config(config_path)
            
            # 3. Update project state
            self._apply_dlc_config(config_data)
            
            # 4. Persist to project
            self._save_dlc_config(config_path)
            
        except Exception as e:
            self.logger.error(f"DLC config load failed: {str(e)}")
            raise

    def _apply_dlc_config(self, config_data: Dict) -> None:
        """Update state from parsed config"""
        # Body parts
        self.state_manager.set_available_body_parts(config_data["body_parts"])
        
        # Objects
        self.state_manager.update_tracked_objects(config_data["objects"]) #TODO: make sure this is optional im project view 
        
        # Experiment validation rules
        self.data_manager.update_experiment_requirements(
            config_data["experiment_settings"]
        )

    def _create_experiment_directory(self, mouse_id: str, exp_id: str) -> Path:
        """Create experiment directory structure"""
        exp_dir = self.project_root / "subjects" / mouse_id / "experiments" / exp_id
        exp_dir.mkdir(parents=True)
        return exp_dir

    def _create_project_config(self) -> None:
        """Create initial project configuration"""
        config = {
            'version': '0.1.0',
            'created_date': datetime.now().isoformat(),
            'settings': {
                'frame_rate': 60,
                'use_detected_rates': False #set as false by default to make app faster
            }
        }
        
        with open(self.project_root / "config" / "project_config.yaml", 'w') as f:
            yaml.dump(config, f)

    def create_batch(self, plugin_type: str, experiment_ids: Set[str], name: Optional[str] = None) -> str:
        """Create a new analysis batch"""
        self.logger.debug(f"Creating batch with plugin type: {plugin_type}")
        
        # Create batch metadata
        batch = BatchMetadata(
            id=f"batch_{uuid.uuid4().hex[:8]}",
            creation_date=datetime.now(),
            experiment_ids=experiment_ids,
            plugin_type=plugin_type,
            plugin_params=get_plugin(plugin_type).default_params(),
            name=name
        )
        
        # Validate using metadata's validation
        is_valid, error = batch.validate(self.state_manager._experiments)
        if not is_valid:
            raise ValueError(f"Invalid batch configuration: {error}")
        
        # Create batch directory structure
        batch_dir = self.project_root / "batches" / batch.id
        batch_dir.mkdir(parents=True)
        
        # Add to state through state manager's internal method
        self.state_manager._add_batch(batch)
        
        return batch.id

    def create_batch_from_experiments(self, experiment_ids: Set[str], 
                                    name: Optional[str] = None) -> str:
        """Create batch from existing experiments"""
        if not experiment_ids:
            raise ValueError("No experiments provided")
        
        # Get common plugin type from experiments
        experiments = [
            self.state_manager._experiments[exp_id] 
            for exp_id in experiment_ids
        ]
        plugin_type = experiments[0].type
        if not all(exp.type == plugin_type for exp in experiments):
            raise ValueError("All experiments must be of same type")
        
        return self.create_batch(plugin_type, experiment_ids, name)

    def save_project(self) -> None:
        """Save project state"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
            
        try:
            # Get serializable state
            state = self.state_manager.get_serializable_state()
            
            # Save state files
            state_dir = self.project_root / "state"
            state_dir.mkdir(exist_ok=True)
            
            # Save version-controlled state
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            state_file = state_dir / f"state_{timestamp}.json"
            
            with open(state_file, 'w') as f:
                json.dump(dataclasses.asdict(state), f, indent=2)
            
            # Update latest state symlink
            latest_link = state_dir / "latest.json"
            if latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(state_file.name)
            
            # Save large data separately
            self._save_experiment_data()
            
            self.state_manager.state_saved.emit()
            
        except Exception as e:
            self.logger.error(f"Failed to save project: {str(e)}")
            raise

    def _save_experiment_data(self) -> None:
        """Save large experiment data separately"""
        data_dir = self.project_root / "data"
        data_dir.mkdir(exist_ok=True)
        
        for exp_id, exp in self.state_manager._experiments.items():
            if exp.tracking_data:
                exp_data_file = data_dir / f"{exp_id}_tracking.npz"
                np.savez_compressed(
                    exp_data_file,
                    coordinates=exp.tracking_data['coordinates'],
                    likelihoods=exp.tracking_data['likelihoods']
                )

    def update_active_body_parts(self, body_parts: List[str]) -> None:
        """Update active body parts and save to project config"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
        
        try:
            # Update state
            self.state_manager.set_active_body_parts(body_parts)
            
            # Update project config
            config_path = self.project_root / "config" / "project_config.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            config['settings']['active_body_parts'] = body_parts
            
            with open(config_path, 'w') as f:
                yaml.dump(config, f)
            
        except Exception as e:
            self.logger.error(f"Failed to update active body parts: {str(e)}")
            raise

    def get_mouse_experiments_info(self, mouse_id: str) -> List[Dict[str, Any]]:
        """Get detailed info about all experiments for a mouse"""
        experiments = self.state_manager.get_sorted_mouse_experiments(mouse_id)
        
        return [
            {
                'id': exp.id,
                'date': exp.date,
                'type': exp.type,
                'phase': exp.phase,
                'week_of_life': exp.week_of_life,
                'frame_rate': exp.frame_rate,
                'has_tracking': bool(exp.tracking_data)
            }
            for exp in experiments
        ]

    def create_batch_from_subjects(
        self,
        name: str,
        experiment_type: str,
        tracked_body_part: str,
        subject_ids: List[str],
        frame_rate: Optional[int] = None
    ) -> str:
        """Create batch by selecting subjects"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
        if not self.dlc_config_path:
            raise RuntimeError("No DLC config loaded")

        try:
            # Get experiment defaults
            exp_defaults = self.data_manager.get_experiment_defaults(experiment_type)
            experiment_length = exp_defaults['length']

            # Get sorted experiments for timeline analysis
            all_experiments = []
            for subject_id in subject_ids:
                experiments = self.state_manager.get_sorted_mouse_experiments(
                    subject_id,
                    experiment_type=experiment_type
                )
                all_experiments.extend(experiments)
                
            # Create batch with timeline metadata
            batch_id = self.state_manager.create_batch_from_subjects(
                name=name,
                experiment_type=experiment_type,
                tracked_body_part=tracked_body_part,
                experiment_length=experiment_length,  # Use default length
                subject_ids=subject_ids,
                frame_rate=frame_rate
            )
            
            # Save timeline metadata for future visualization
            timeline_data = {
                'subjects': {
                    subject_id: {
                        'birth_date': self.state_manager._subjects[subject_id].birth_date.isoformat()
                        if self.state_manager._subjects[subject_id].birth_date else None
                    }
                    for subject_id in subject_ids
                },
                'experiments': [
                    {
                        'id': exp.id,
                        'subject_id': exp.mouse_id,
                        'date': exp.date.isoformat() if exp.date else None,
                        'week_of_life': exp.week_of_life,
                        'phase': exp.phase  # Include phase in timeline
                    }
                    for exp in all_experiments
                ],
                'experiment_type': experiment_type,
                'phases': exp_defaults['phases']  # Include valid phases
            }
            
            timeline_path = self.project_root / "batches" / batch_id / "timeline.yaml"
            with open(timeline_path, 'w') as f:
                yaml.dump(timeline_data, f)
                
            return batch_id
            
        except Exception as e:
            self.logger.error(f"Failed to create batch: {str(e)}")
            raise

    def create_batch_from_subject(
        self,
        name: str,
        subject_id: str,
        experiment_type: str,
        tracked_body_part: str
    ) -> str:
        """Create batch containing all matching experiments for a subject"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
            
        # Get all experiments of type for this subject
        experiments = self.state_manager.get_sorted_mouse_experiments(
            subject_id, 
            experiment_type=experiment_type
        )
        
        # Create batch directory
        batch_id = str(uuid.uuid4())
        batch_dir = self.project_root / "batches" / batch_id
        batch_dir.mkdir(parents=True)
        
        # Create batch metadata
        batch = BatchMetadata(
            id=batch_id,
            name=name,
            creation_date=datetime.now(),
            tracked_body_part=tracked_body_part,
            experiment_ids={exp.id for exp in experiments}
        )
        
        # Save batch config
        batch_config = {
            'id': batch_id,
            'name': name,
            'creation_date': batch.creation_date.isoformat(),
            'tracked_body_part': tracked_body_part,
            'experiment_ids': list(batch.experiment_ids),
            'subject_ids': [subject_id]
        }
        
        with open(batch_dir / "config.yaml", 'w') as f:
            yaml.dump(batch_config, f)
            
        # Update state
        self.state_manager._batches[batch_id] = batch
        self.state_manager.batch_created.emit(batch_id)
        return batch_id

    def add_experiment_to_project(
        self,
        metadata: ExperimentMetadata,
        tracking_data_path: Path
    ) -> str:
        """Add experiment to project with data"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
            
        # Calculate age if possible
        subject = self.state_manager._subjects.get(metadata.mouse_id)
        if subject and subject.birth_date and metadata.date:
            age_weeks = self.data_manager.calculate_age_at_date(
                subject.birth_date,
                metadata.date
            )
            metadata.week_of_life = age_weeks
            
        # Copy data to project
        exp_dir = self.project_root / "experiments" / metadata.id
        exp_dir.mkdir(parents=True)
        
        # Copy tracking data
        dest_path = exp_dir / "tracking_data.csv"
        if tracking_data_path.exists():
            with open(tracking_data_path, 'rb') as src, open(dest_path, 'wb') as dst:
                dst.write(src.read())
                
        # Add to state
        exp_id = self.state_manager.add_experiment(metadata)
        return exp_id

    def save_project_state(self) -> None:
        """Save current project state"""
        if not self.project_root:
            raise RuntimeError("No project loaded")
            
        state = self.state_manager.get_serializable_state()
        state_path = self.project_root / "project_state.json"
        
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
            
        self.state_manager.state_saved.emit()

    def _on_mouse_added(self, mouse_id: str) -> None:
        """Handle mouse addition"""
        if self.project_root:
            mouse_dir = self.project_root / "subjects" / mouse_id
            mouse_dir.mkdir(parents=True, exist_ok=True)
            
    def _on_experiment_added(self, mouse_id: str, exp_id: str) -> None:
        """Handle experiment addition"""
        if self.project_root:
            exp_dir = self.project_root / "experiments" / exp_id
            exp_dir.mkdir(parents=True, exist_ok=True)
            
    def _on_batch_created(self, batch_id: str) -> None:
        """Handle batch creation"""
        if self.project_root:
            batch = self.state_manager._batches[batch_id]
            self._setup_batch_directory(
                batch_id,
                batch.name,
                batch.experiment_type,
                batch.tracked_body_part,
                batch.experiment_length,
                batch.frame_rate
            )
            
    def _on_experiment_updated(self, exp_id: str) -> None:
        """Handle experiment updates"""
        if self.project_root:
            exp = self.state_manager._experiments[exp_id]
            exp_dir = self.project_root / "experiments" / exp_id
            # Update relevant files based on what changed
            self._save_experiment_metadata(exp_id, exp)

    def execute_batch(self, batch_id: str) -> None:
        """Execute batch analysis and save results"""
        self.logger.info(f"Executing batch {batch_id}")
        
        batch = self.state_manager._batches[batch_id]
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")
        
        try:
            # Update batch status
            batch.status = "running"
            self.state_manager.batch_updated.emit(batch_id)
            
            # Create batch output directory
            batch_dir = self.project_root / "batches" / batch_id
            results_dir = batch_dir / "results"
            plots_dir = results_dir / "plots"
            plots_dir.mkdir(parents=True, exist_ok=True)
            
            # Process batch data with visualizations
            results = self.data_manager.process_batch_data(
                batch_id,
                save_dir=plots_dir
            )
            
            # Save results
            results_file = results_dir / "analysis.json"
            with open(results_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
                
            # Create summary report
            self._create_batch_report(batch_id, results, results_dir)
            
            # Update batch status and results
            batch.status = "completed"
            batch.results = results
            self.state_manager.batch_updated.emit(batch_id)
            
        except Exception as e:
            self.logger.error(f"Batch execution failed: {str(e)}")
            batch.status = "failed"
            self.state_manager.batch_updated.emit(batch_id)
            raise

    def _create_batch_report(self, batch_id: str, results: Dict[str, Any], 
                            output_dir: Path) -> None:
        """Create batch analysis report"""
        batch = self.state_manager._batches[batch_id]
        
        report = {
            "batch_id": batch_id,
            "name": batch.name,
            "plugin_type": batch.plugin_type,
            "creation_date": batch.creation_date.isoformat(),
            "execution_date": datetime.now().isoformat(),
            "subjects": {}
        }
        
        # Summarize results by subject
        for subject_id, subject_data in results.items():
            mouse = self.state_manager._subjects[subject_id]
            
            report["subjects"][subject_id] = {
                "sex": mouse.sex,
                "birth_date": mouse.birth_date.isoformat(),
                "experiment_count": len(subject_data["experiments"]),
                "timeline": subject_data["timeline"],
                "plugin_results": subject_data["plugin_results"]
            }
        
        # Save report
        report_file = output_dir / "report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

    def get_existing_projects(self) -> List[Path]:
        """Get list of valid project paths in projects_root"""
        return [
            p for p in self.projects_root.iterdir() 
            if p.is_dir() and self.data_manager.validate_project_directory(p)
        ]

    def validate_project_name(self, name: str) -> Tuple[bool, str]:
        if not re.match(r"^[\w\- ]{3,50}$", name):
            return False, "Name must be 3-50 alphanumeric chars"
        return True, ""
 