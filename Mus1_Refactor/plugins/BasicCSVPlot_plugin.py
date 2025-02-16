from pathlib import Path
from datetime import datetime
from core.metadata import PluginMetadata
from .base_plugin import BasePlugin

class BasicCSVPlotPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="BasicCSVPlot",
            date_created=datetime(2025, 2, 15),
            version="1.0",
            description="A plugin for analyzing basic CSV files",
            author="Lukash Platil"
        )
    
    def required_fields(self): 
        """
        Return a list of fields required by this plugin for a valid experiment.
        """
        return ["csv_path"]

    def validate_experiment(self, experiment, project_state):
        """
        Validate the experiment by checking:
        - The CSV file path is valid (exists).
        - Experiment has overlapping body parts with project_state.project_metadata.master_body_parts.
        """
        csv_path = experiment.plugin_params.get("csv_path")
        if not csv_path or not Path(csv_path).exists():
            raise ValueError(f"CSV file path missing or not found: {csv_path}")

        # Assuming 'body_parts' is tracked in experiment or plugin_params
        # and 'master_body_parts' is in project_state.project_metadata.
        project_body_parts = set(getattr(project_state.project_metadata, "master_body_parts", []))
        experiment_body_parts = set(getattr(experiment, "body_parts", []))

        if not project_body_parts.intersection(experiment_body_parts):
            raise ValueError("No overlapping body parts found.")
        
        # ... other necessary validation ...

    def analyze_experiment(self, experiment, data_manager=None):
        """
        Optionally use data_manager to read the CSV file for analysis or plotting.
        """
        csv_path = experiment.plugin_params.get("csv_path")
        if not csv_path:
            return {"error": "No CSV path set"}

        if data_manager:
            try:
                df = data_manager.load_dlc_tracking_csv(Path(csv_path))
                return {"status": "success", "rows": len(df)}
            except Exception as e:
                return {"error": str(e)}
        else:
            return {"info": f"DataManager not provided. CSV path: {csv_path}"}