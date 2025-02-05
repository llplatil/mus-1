"""Novel Object Recognition analysis implementation"""
#TODO: Look how project deisgnations and object roles are defined in core metadata and coordinate it with this plugin

from typing import Dict, Any, Optional, Tuple
from ..base_plugin import BasePlugin, PluginMetadata
import numpy as np
import pandas as pd

class NORPlugin(BasePlugin):
    """Novel Object Recognition analysis plugin"""
    
    # Define plugin metadata
    metadata = PluginMetadata(
        name="nor",
        version="0.1.0",
        description="Novel Object Recognition Analysis",
        author="MUS1 Team"
    )
    
    def __init__(self):
        super().__init__()
        self.logger.info(f"Initialized {self.metadata.name} plugin v{self.metadata.version}")
        
        #placeholder for explaiantion of what we learend from last NOR Analysis Script buildout 
        #TODO: Verify code works unti then we will pas it in main_dev Add explanation here

    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """Get default parameters for NOR analysis"""
        return {
            "habituation_time": 600,  # 10 minutes in seconds
            "test_duration": 600,     # 10 minutes in seconds
            "interaction_radius": 50,  # pixels
            "min_interaction_time": 1.0  # seconds
        }
    
    def process_experiment(self, tracking_data: Dict[str, Any], 
                         params: Dict[str, Any]) -> Dict[str, Any]:
        """Process experiment data for NOR analysis"""
        try:
            # Merge default and provided parameters
            analysis_params = {**self.default_params(), **params}
            
            # Get object roles and validate
            exp_id = tracking_data.get('experiment_id')
            if not exp_id:
                raise ValueError("No experiment ID in tracking data")
                
            object_roles = self.state_manager.get_object_roles(exp_id)
            if not self._validate_object_roles(object_roles):
                raise ValueError("Invalid object role configuration")
            
            # Calculate interactions
            interactions = self._calculate_object_interactions(
                tracking_data,
                object_roles,
                analysis_params
            )
            
            return {
                'interactions': interactions,
                'parameters': analysis_params,
                'metadata': {
                    'plugin_version': self.metadata.version,
                    'object_roles': object_roles
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to process experiment: {str(e)}")
            raise

    def _validate_object_roles(self, object_roles: Dict[str, str]) -> bool:
        """Validate object role configuration"""
        if not object_roles:
            self.logger.error("No object roles defined")
            return False
            
        required_roles = {'novel', 'familiar'}
        defined_roles = set(object_roles.values())
        
        if not required_roles.issubset(defined_roles):
            missing = required_roles - defined_roles
            self.logger.error(f"Missing required object roles: {missing}")
            return False
            
        return True

    def _calculate_object_interactions(
        self,
        tracking_data: Dict[str, Any],
        object_roles: Dict[str, str],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate object interactions from tracking data"""
        try:
            # Get trajectories for analysis
            nose_trajectory = self.get_trajectory('nose', tracking_data)
            if nose_trajectory is None:
                raise ValueError("Failed to get nose trajectory")
                
            # Calculate interactions for each object
            interactions = {}
            for obj_name, role in object_roles.items():
                obj_coords = self._get_object_coordinates(obj_name, tracking_data)
                if obj_coords is None:
                    self.logger.warning(f"No coordinates for object: {obj_name}")
                    continue
                    
                interactions[role] = self._analyze_interactions(
                    nose_trajectory,
                    obj_coords,
                    params['interaction_radius'],
                    params['min_interaction_time']
                )
            
            return interactions
            
        except Exception as e:
            self.logger.error(f"Failed to calculate interactions: {str(e)}")
            raise

    def _analyze_interactions(
        self,
        nose_trajectory: Tuple[np.ndarray, np.ndarray],
        object_coords: Tuple[float, float],
        radius: float,
        min_time: float
    ) -> Dict[str, Any]:
        """Analyze interactions between nose and object"""
        # TODO: Implement interaction analysis
        # This will be implemented based on the previous NOR analysis script
        pass

    def get_object_interactions(self, exp_id: str) -> Dict[str, Any]:
        """Get interaction data for novel and familiar objects"""
        exp = self.state_manager.get_experiment(exp_id)
        object_roles = self.state_manager.get_object_roles(exp_id)
        
        if not object_roles:
            self.logger.warning(f"No object roles defined for experiment {exp_id}")
            return {}
            
        novel_object = next((obj for obj, role in object_roles.items() 
                           if role == 'novel'), None)
        familiar_object = next((obj for obj, role in object_roles.items() 
                              if role == 'familiar'), None)
                              
        if not (novel_object and familiar_object):
            self.logger.error("Missing novel or familiar object definition")
            return {}
            
        # Get trajectories and calculate interactions
        # ... analysis code ... 

    def validate_metadata(self, metadata: ExperimentMetadata) -> Tuple[bool, str]:
        """Comprehensive NOR validation"""
        errors = []
        
        # Required checks
        if not metadata.arena_image_path:
            errors.append("Missing arena image reference")
        
        if len(metadata.tracking_data.coordinates) < 1:
            errors.append("No body parts specified for tracking")
        
        # Object role validation
        if metadata.object_roles:
            required_roles = {'novel', 'familiar'}
            if not required_roles.issubset(metadata.object_roles.values()):
                errors.append(f"Missing required object roles: {required_roles}")
        else:
            errors.append("No object roles defined")
        
        # Conditional phase validation
        if metadata.phase:  # Only validate if phase is set
            valid_phases = {'familiarization', 'recognition'}
            if metadata.phase.lower() not in valid_phases:
                errors.append(f"Invalid phase. Valid options: {valid_phases}")
        
        # Plugin-specific requirements
        if 'nose' not in metadata.tracking_data.coordinates:
            errors.append("Nose tracking required for NOR analysis")
        
        return len(errors) == 0, " | ".join(errors) 