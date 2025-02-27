from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from pathlib import Path
import pandas as pd

from core.metadata import ExperimentMetadata, ProjectState, PluginMetadata

class BasePlugin(ABC):
    @abstractmethod
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """
        Perform plugin-specific validations for the experiment.
        
        Each plugin should validate only its own parameters found in experiment.plugin_params[plugin_name].
        This allows multiple plugins to be used in a single experiment.
        
        Args:
            experiment: The experiment metadata to validate
            project_state: The current project state for context
            
        Raises:
            ValueError: If validation fails
        """
        pass

    @abstractmethod
    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """
        Run experiment-specific analysis and return the results.
        
        Plugins should use DataManager for I/O operations when possible.
        
        Args:
            experiment: The experiment metadata to analyze
            
        Returns:
            Dictionary containing analysis results
        """
        pass

    @abstractmethod
    def plugin_self_metadata(self) -> PluginMetadata:
        """
        Return the PluginMetadata object that describes this plugin.
        
        Must include:
        - name: The name of the plugin
        - supported_experiment_types: List of experiment types this plugin supports
        
        Example:
            return PluginMetadata(
                name="NORPlugin",
                date_created=datetime.now(),
                version="1.0.0",
                description="Plugin for Novel Object Recognition experiments",
                author="Your Name",
                supported_experiment_types=["NOR", "OpenField"]
            )
        """
        pass

    def required_fields(self) -> List[str]:
        """Return a list of required field names for this plugin's experiment. Default is empty list."""
        return []

    def optional_fields(self) -> List[str]:
        """Return a list of optional field names for this plugin's experiment. Default is empty list."""
        return []

    def get_supported_experiment_types(self) -> List[str]:
        """Return experiment types this plugin supports."""
        meta = self.plugin_self_metadata()
        return meta.supported_experiment_types or []

    def get_supported_processing_stages(self) -> List[str]:
        """Return processing stages this plugin supports. Default to ['post-processing']."""
        meta = self.plugin_self_metadata()
        return meta.supported_processing_stages or ["post-processing"]

    def get_supported_data_sources(self) -> List[str]:
        """Return data sources this plugin supports. Default to ['DLC']."""
        meta = self.plugin_self_metadata()
        return meta.supported_data_sources or ["DLC"]

    def get_supported_arena_sources(self) -> List[str]:
        """Return arena image sources this plugin supports. Default to ['DLC_Export', 'Manual']."""
        return ["DLC_Export", "Manual"]

    @staticmethod
    def extract_bodyparts_from_dlc_csv(csv_file: Path) -> set:
        """Utility method to extract body parts from a DeepLabCut CSV file."""
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        try:
            df = pd.read_csv(csv_file, header=[0,1,2], index_col=0)
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
        return set(df.columns.get_level_values(1))
