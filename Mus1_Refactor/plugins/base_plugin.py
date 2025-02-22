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
        """
        Return the PluginMetadata object that describes this plugin
        (name, creation_date, version, etc.).
        """
        pass

    def required_fields(self) -> list:
        """
        Return a list of required field names for this plugin's experiment.
        These fields are used mainly for UI validation. The core experiment fields are defined in ExperimentMetadata,
        so there is no need to register them with the global state.
        Default is empty, override if needed.
        """
        return []

    def optional_fields(self) -> list:
        """
        Return a list of optional field names for this plugin's experiment.
        These extra fields can further extend the core ExperimentMetadata if needed.
        Default is empty, override if needed.
        """
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