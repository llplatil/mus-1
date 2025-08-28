from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Set, Tuple, Union
from pathlib import Path
import pandas as pd

# Forward reference for type hint
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.data_manager import DataManager

from ..core.metadata import ExperimentMetadata, ProjectState, PluginMetadata

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
            ValueError: If validation fails due to invalid parameter values.
            FileNotFoundError: If validation fails because required files are missing.
        """
        pass

    @abstractmethod
    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: 'DataManager', capability: str) -> Dict[str, Any]:
        """
        Run experiment-specific analysis based on the capability and return the results.
        
        Plugins should load necessary data on demand within this method using the
        provided `data_manager` and file paths stored in `experiment.plugin_params`.
        
        Args:
            experiment: The experiment metadata containing parameters.
            data_manager: The DataManager instance for data loading capabilities.
            capability: The specific capability requested (e.g., 'load_tracking_data', 'nor_index').
            
        Returns:
            A dictionary containing analysis results. The structure depends on the capability,
            but it is **highly recommended** to include the following standard keys:

            - 'status' (str): 'success' or 'failed'. REQUIRED.
            - 'error' (str, optional): Description of the error if status is 'failed'.
            - 'message' (str, optional): A user-friendly message about the outcome.
            - 'capability_executed' (str): The capability string that was run. REQUIRED.
            - 'output_file_paths' (Dict[str, str], optional): Dictionary mapping descriptive names
              (e.g., 'heatmap_png', 'syllable_results_h5') to their absolute file paths if the
              plugin saved output files.
            - ... (capability-specific results): Other key-value pairs containing the actual
              analysis outputs (e.g., calculated metrics, data summaries).
        """
        pass

    @abstractmethod
    def plugin_self_metadata(self) -> PluginMetadata:
        """
        Return the PluginMetadata object that describes this plugin.
        
        Must include fields like name, description, capabilities, readable formats.
        """
        pass

    @abstractmethod
    def readable_data_formats(self) -> List[str]:
        """Return a list of data format identifiers (e.g., 'dlc_csv', 'generic_csv') this plugin can read or process."""
        pass

    @abstractmethod
    def analysis_capabilities(self) -> List[str]:
        """Return a list of analysis capability identifiers (e.g., 'distance_speed', 'nor_index') this plugin provides."""
        pass

    def required_fields(self) -> List[str]:
        """
        Return a list of field names required as parameters for this plugin's capabilities.
        May depend on the specific capability being used. Implementations should document this.
        Default is empty list.
        """
        return []

    def optional_fields(self) -> List[str]:
        """
        Return a list of optional field names that can be used as parameters.
        May depend on the specific capability being used. Implementations should document this.
        Default is empty list.
        """
        return []

    def get_field_types(self) -> Dict[str, str]:
        """
        Return a dictionary mapping field names (from required/optional) to their data types
        (e.g., 'string', 'file', 'float', 'int', 'enum:value1,value2', 'dict').
        This helps the UI generate appropriate input widgets. Default is empty dict.
        """
        return {}

    def get_field_descriptions(self) -> Dict[str, str]:
        """
        Return a dictionary mapping field names (from required/optional) to their descriptions.
        Provides context/help text for users in the UI. Default is empty dict.
        """
        return {}
