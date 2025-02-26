from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from pathlib import Path
import pandas as pd

from core.metadata import ExperimentMetadata, ProjectState, PluginMetadata

class BasePlugin(ABC):
    @abstractmethod
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Perform plugin-specific validations for the experiment."""
        pass

    @abstractmethod
    def analyze_experiment(self, experiment: ExperimentMetadata) -> Dict[str, Any]:
        """Run experiment-specific analysis and return the results."""
        pass

    @abstractmethod
    def plugin_self_metadata(self) -> PluginMetadata:
        """Return the PluginMetadata object that describes this plugin, including the high-level plugin_type
        which indicates which experiment type this plugin supports. Must be implemented by subclasses."""
        pass

    def required_fields(self) -> List[str]:
        """Return a list of required field names for this plugin's experiment. These will be used for UI validation.
        Override if needed. Default is empty list."""
        return []

    def optional_fields(self) -> List[str]:
        """Return a list of optional field names for this plugin's experiment. Override if needed. Default is empty list."""
        return []

    @staticmethod
    def extract_bodyparts_from_dlc_csv(csv_file: Path) -> set:
        """Extracts body parts from a DLC CSV file by reading the header (level 1) and returning a set of unique body parts."""
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        try:
            df = pd.read_csv(csv_file, header=[0,1,2], index_col=0)
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
        return set(df.columns.get_level_values(1))

class PluginManager:
    """A simple plugin manager to register and retrieve plugins."""
    def __init__(self):
        self.plugins = []

    def register_plugin(self, plugin_class):
        """Register a plugin class by instantiating it and storing the instance."""
        plugin_instance = plugin_class()
        self.plugins.append(plugin_instance)

    def get_plugins(self):
        """Return the list of registered plugin instances."""
        return self.plugins 