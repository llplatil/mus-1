from plugins.base_plugin import BasePlugin
from typing import Dict, Any
from core.metadata import PluginMetadata, ExperimentMetadata, ProjectState, NORSessions
from datetime import datetime

class NORPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="NOR",
            date_created=datetime(2025, 2, 16),
            version="1.0",
            description="A plugin for analyzing NOR experiments",
            author="Lukash Platil"
        )
    
    def required_fields(self):
        return ["session_stage", "object_roles", "csv_path"]
    
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        # Expect plugin_params to be of type dict for NOR experiments
        plugin_params = getattr(experiment, 'plugin_params', None)
        if plugin_params and isinstance(plugin_params, dict):
            # Use NORSessions.FAMILIARIZATION as a default if not provided.
            session_stage = plugin_params.get('session_stage', NORSessions.FAMILIARIZATION)
            roles = plugin_params.get('object_roles', {})
            if session_stage == NORSessions.FAMILIARIZATION and len(set(roles.values())) > 1:
                raise ValueError("Familiarization stage requires identical object roles for NOR experiments.")

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        # Placeholder for NOR analysis
        return {"result": "NOR analysis executed."} 
        