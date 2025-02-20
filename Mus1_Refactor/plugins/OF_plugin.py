from plugins.base_plugin import BasePlugin
from typing import Dict, Any
from core.metadata import PluginMetadata, ExperimentMetadata, ProjectState, OFSessions
from datetime import datetime

class OFPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="OF",
            date_created=datetime(2025, 2, 17),
            version="1.0",
            description="A plugin for analyzing OF experiments",
            author="Lukash Platil"
        ) 

    def required_fields(self):
        return ["session_stage", "csv_path"]
    
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        # Minimal validation for OpenField: currently no special rules
        plugin_params = getattr(experiment, 'plugin_params', None)
        if plugin_params and isinstance(plugin_params, dict):
            session_stage = plugin_params.get('session_stage', OFSessions.HABITUATION)
            # No specific validation implemented for OF
        
    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        # Return a dummy analysis result
        return {"result": "OpenField analysis not implemented yet."} 

    def plugin_self_meta(self) -> PluginMetadata:
        return self.plugin_self_metadata() 