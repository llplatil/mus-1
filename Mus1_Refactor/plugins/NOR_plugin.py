from plugins.base_plugin import BasePlugin
from typing import Dict, Any
from core.metadata import ExperimentMetadata, ProjectState, NORSessions

class NORPlugin(BasePlugin):
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        # Expect plugin_params to be of type dict for NOR experiments
        plugin_params = getattr(experiment, 'plugin_params', None)
        if plugin_params and isinstance(plugin_params, dict):
            # For simplicity, assume the dict has a 'session_stage' and 'object_roles'
            session_stage = plugin_params.get('session_stage', NORSessions.FAMILIARIZATION)
            roles = plugin_params.get('object_roles', {})
            if session_stage == NORSessions.FAMILIARIZATION and len(set(roles.values())) > 1:
                raise ValueError("Familiarization stage requires identical object roles for NOR experiments.")

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        # Placeholder for NOR experiment analysis
        return {"result": "NOR analysis executed."} 