from plugins.base_plugin import BasePlugin
from typing import Dict, Any
from core.metadata import PluginMetadata, ExperimentMetadata, ProjectState
from datetime import datetime
from pathlib import Path
from enum import Enum

class OFSessions(Enum):
    HABITUATION = "habituation"
    REEXPOSURE = "re-exposure"

class OFPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="OF",
            date_created=datetime(2025, 2, 17),
            version="1.0",
            description="A plugin for analyzing OF experiments. Note: Validation and analysis are minimal; additional fields (like image/video) may be required.",
            author="Lukash Platil"
        )
        
    def required_fields(self):
        """Return a list of required fields for an Open Field experiment."""
        return ["csv_path", "session_stage"]
        
    def optional_fields(self):
        """Return a list of optional fields for an Open Field experiment. (Not complete; may require arena markings, image, and video.)"""
        return ["arena_markings", "image", "video"]
        
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform minimal validation for an Open Field experiment."""
        plugin_params = experiment.plugin_params
        csv_path = plugin_params.get("csv_path")
        if not csv_path:
            raise ValueError("CSV path is missing for Open Field experiment.")
        if not Path(csv_path).exists():
            raise ValueError(f"CSV file not found at: {csv_path}")
        
        # Validate session_stage: use OFSessions.HABITUATION as default
        session_stage = plugin_params.get("session_stage", OFSessions.HABITUATION.value)
        # Minimal validation: currently no specific rules for OF

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Perform analysis for an Open Field experiment. Placeholder implementation."""
        return {"result": "Open Field analysis executed. (Analysis logic not complete)"}

    # Optional alias if needed
    def plugin_self_meta(self) -> PluginMetadata:
        return self.plugin_self_metadata() 