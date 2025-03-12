from plugins.base_plugin import BasePlugin
from typing import Dict, Any, List
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
            description="A plugin for analyzing Open Field experiments. Note: Validation and analysis are minimal; additional fields (like image/video) may be required.",
            author="Lukash Platil",
            supported_experiment_types=["OpenField"],
            supported_processing_stages=["processing", "analyzed"],
            supported_data_sources=["DLC", "Manual"]
        )
        
    def required_fields(self) -> List[str]:
        """Return a list of required fields for an Open Field experiment."""
        return ["csv_path", "session_stage", "arena_dimensions"]
        
    def optional_fields(self) -> List[str]:
        """Return a list of optional fields for an Open Field experiment."""
        return ["arena_image", "video", "arena_zones", "notes"]

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
            "session_stage": "enum:habituation,re-exposure",
            "arena_dimensions": "dict",  # Format: {"width": float, "height": float, "unit": "cm"}
            "arena_image": "file",
            "arena_zones": "dict",  # Format: {"center": {"x": float, "y": float, "radius": float}, ...}
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
            "session_stage": "The experiment session type (habituation or re-exposure)",
            "arena_dimensions": "Dimensions of the arena (width, height, unit)",
            "arena_image": "Image of the experimental arena",
            "arena_zones": "Definition of zones within the arena (e.g., center, corners)",
            "video": "Video recording of the experiment",
            "notes": "Any additional notes about the experiment"
        }
        
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform validation for an Open Field experiment."""
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})
        
        # Validate required fields
        csv_path = plugin_params.get("csv_path")
        if not csv_path:
            raise ValueError("CSV path is missing for Open Field experiment.")
        if not Path(csv_path).exists():
            raise ValueError(f"CSV file not found at: {csv_path}")
        
        # Validate session stage
        session_stage = plugin_params.get("session_stage", OFSessions.HABITUATION.value)
        if session_stage not in [s.value for s in OFSessions]:
            raise ValueError(f"Invalid session stage: {session_stage}. Must be one of: {[s.value for s in OFSessions]}")
        
        # Validate arena dimensions
        arena_dimensions = plugin_params.get("arena_dimensions", {})
        if not arena_dimensions:
            raise ValueError("Arena dimensions are required for Open Field experiment.")
            
        required_dimensions = ["width", "height", "unit"]
        for dim in required_dimensions:
            if dim not in arena_dimensions:
                raise ValueError(f"Arena dimensions must include {dim}.")
                
        # Validate arena zones if provided
        arena_zones = plugin_params.get("arena_zones", {})
        if arena_zones:
            for zone_name, zone_data in arena_zones.items():
                required_zone_data = ["x", "y"]
                if zone_name == "center" and "radius" not in zone_data:
                    raise ValueError("Center zone must include radius.")
                for data in required_zone_data:
                    if data not in zone_data:
                        raise ValueError(f"Zone '{zone_name}' must include {data}.")

    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Perform analysis for an Open Field experiment."""
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})
        
        try:
            # Basic validation
            csv_path = plugin_params.get("csv_path")
            if not csv_path or not Path(csv_path).exists():
                return {"error": f"CSV file not found: {csv_path}"}
                
            session_stage = plugin_params.get("session_stage", OFSessions.HABITUATION.value)
            arena_dimensions = plugin_params.get("arena_dimensions", {})
            arena_zones = plugin_params.get("arena_zones", {})
            
            # Placeholder for actual analysis
            return {
                "status": "success",
                "phase": session_stage,
                "message": f"Open Field {session_stage} session analyzed.",
                "metrics": {
                    "total_distance": "N/A (analysis not implemented)",
                    "average_speed": "N/A",
                    "time_in_center": "N/A",
                    "entries_to_center": "N/A",
                    "thigmotaxis": "N/A"  # Wall-hugging behavior
                },
                "arena_info": {
                    "dimensions": arena_dimensions,
                    "zones": arena_zones
                }
            }
                
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    # Optional alias if needed
    def plugin_self_meta(self) -> PluginMetadata:
        return self.plugin_self_metadata() 