from plugins.base_plugin import BasePlugin
from typing import Dict, Any, List
from core.metadata import PluginMetadata, ExperimentMetadata, ProjectState
from datetime import datetime
from pathlib import Path
from enum import Enum

class NORSessions(Enum):
    FAMILIARIZATION = "familiarization"
    RECOGNITION = "recognition"

class NORPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="NOR",
            date_created=datetime(2025, 2, 16),
            version="1.0",
            description="A plugin for analyzing Novel Object Recognition experiments. Note: Validation not complete; additional fields like image and video may be required.",
            author="Lukash Platil",
            supported_experiment_types=["NOR"],
            supported_processing_stages=["processing", "analyzed"],
            supported_data_sources=["DLC", "Manual"]
        )
    
    def required_fields(self) -> List[str]:
        """Return a list of required fields for a NOR experiment."""
        return ["csv_path", "session_stage", "object_roles"]
    
    def optional_fields(self) -> List[str]:
        """Return a list of optional fields for a NOR experiment."""
        return ["arena_image", "video", "notes"]
        
    def get_supported_processing_stages(self) -> List[str]:
        """Return processing stages this plugin supports."""
        return ["processing", "analyzed"]
        
    def get_field_types(self) -> Dict[str, str]:
        """
        Return a dictionary mapping field names to their data types.
        This helps the UI generate appropriate input widgets.
        """
        return {
            "csv_path": "file",
            "session_stage": "enum:familiarization,recognition",
            "object_roles": "dict",  # Needs special UI handling for object-role mapping
            "arena_image": "file",
            "video": "file",
            "notes": "text"
        }
        
    def get_field_descriptions(self) -> Dict[str, str]:
        """
        Return a dictionary mapping field names to their descriptions.
        This provides context for users when filling out the form.
        """
        return {
            "csv_path": "Path to the CSV file containing tracking data",
            "session_stage": "The experiment session type (familiarization or recognition)",
            "object_roles": "Define which tracked object serves which role in the experiment",
            "arena_image": "Image of the experimental arena",
            "video": "Video recording of the experiment",
            "notes": "Any additional notes about the experiment"
        }
    
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform validation for a NOR experiment."""
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})
        
        csv_path = plugin_params.get("csv_path")
        if not csv_path:
            raise ValueError("CSV path is missing for NOR experiment.")
        if not Path(csv_path).exists():
            raise ValueError(f"CSV file not found at: {csv_path}")
        
        # Validate session stage and object roles
        session_stage = plugin_params.get("session_stage", NORSessions.FAMILIARIZATION.value)
        object_roles = plugin_params.get("object_roles", {})
        
        if not object_roles:
            raise ValueError("Object roles must be defined for NOR experiment.")
            
        if session_stage == NORSessions.FAMILIARIZATION.value:
            # In familiarization phase, all objects should have the same role
            if len(set(object_roles.values())) > 1:
                raise ValueError("Familiarization stage requires identical object roles for NOR experiments.")
        elif session_stage == NORSessions.RECOGNITION.value:
            # In recognition phase, we need both familiar and novel objects
            roles = set(object_roles.values())
            if "familiar" not in roles or "novel" not in roles:
                raise ValueError("Recognition stage requires both 'familiar' and 'novel' object roles.")

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Perform analysis for a NOR experiment."""
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})
        
        try:
            # Basic validation
            csv_path = plugin_params.get("csv_path")
            if not csv_path or not Path(csv_path).exists():
                return {"error": f"CSV file not found: {csv_path}"}
                
            session_stage = plugin_params.get("session_stage", NORSessions.FAMILIARIZATION.value)
            object_roles = plugin_params.get("object_roles", {})
            
            # Placeholder for actual analysis
            if session_stage == NORSessions.FAMILIARIZATION.value:
                return {
                    "status": "success",
                    "phase": "familiarization",
                    "message": "Familiarization session analyzed.",
                    "metrics": {
                        "total_objects": len(object_roles),
                        "exploration_time": "N/A (analysis not implemented)"
                    }
                }
            else:  # Recognition phase
                return {
                    "status": "success",
                    "phase": "recognition",
                    "message": "Recognition session analyzed.",
                    "metrics": {
                        "discrimination_index": "N/A (analysis not implemented)",
                        "novel_object_time": "N/A",
                        "familiar_object_time": "N/A"
                    }
                }
                
        except Exception as e:
            return {"error": str(e), "status": "failed"} 
        