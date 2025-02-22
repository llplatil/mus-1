from plugins.base_plugin import BasePlugin
from typing import Dict, Any
from core.metadata import PluginMetadata, ExperimentMetadata, ProjectState, NORSessions
from datetime import datetime
from pathlib import Path

class NORPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="NOR",
            date_created=datetime(2025, 2, 16),
            version="1.0",
            description="A plugin for analyzing NOR experiments. Note: Validation not complete; additional fields like image and video may be required.",
            author="Lukash Platil"
        )
    
    def required_fields(self):
        """Return a list of required fields for a NOR experiment."""
        return ["csv_path", "session_stage", "object_roles"]
    
    def optional_fields(self):
        """Return a list of optional fields for a NOR experiment. (Not complete; may require image and video.)"""
        return ["image", "video"]
    
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform validation for a NOR experiment."""
        plugin_params = experiment.plugin_params
        csv_path = plugin_params.get("csv_path")
        if not csv_path:
            raise ValueError("CSV path is missing for NOR experiment.")
        if not Path(csv_path).exists():
            raise ValueError(f"CSV file not found at: {csv_path}")
        
        # Validate session stage and object roles
        session_stage = plugin_params.get("session_stage", NORSessions.FAMILIARIZATION.value)
        object_roles = plugin_params.get("object_roles", {})
        if session_stage == NORSessions.FAMILIARIZATION.value:
            if len(set(object_roles.values())) > 1:
                raise ValueError("Familiarization stage requires identical object roles for NOR experiments.")

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Perform analysis for a NOR experiment. Placeholder implementation."""
        return {"result": "NOR analysis executed. (Analysis logic not complete)"} 
        