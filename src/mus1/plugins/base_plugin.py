from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Set, Tuple, Union
from pathlib import Path
import pandas as pd

# Forward reference for type hint
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.plugin_manager_clean import PluginService
    from ..core.project_manager_clean import ProjectManagerClean

from ..core.metadata import Experiment, ProjectConfig, PluginMetadata

class BasePlugin(ABC):
    @abstractmethod
    def validate_experiment(self, experiment: Experiment, project_config: ProjectConfig) -> None:
        """
        Perform plugin-specific validations for the experiment.

        Each plugin should validate only its own parameters found in experiment.plugin_params[plugin_name].
        This allows multiple plugins to be used in a single experiment.

        Args:
            experiment: The experiment to validate
            project_config: The project configuration for context

        Raises:
            ValueError: If validation fails due to invalid parameter values.
            FileNotFoundError: If validation fails because required files are missing.
        """
        pass

    @abstractmethod
    def analyze_experiment(self, experiment: Experiment, plugin_service: 'PluginService',
                          capability: str, project_config: ProjectConfig) -> Dict[str, Any]:
        """
        Run experiment-specific analysis based on the capability and return the results.

        Plugins should load necessary data on demand within this method using the
        provided `plugin_service` which gives access to repositories and data access methods.

        Args:
            experiment: The experiment metadata containing parameters.
            plugin_service: The PluginService instance for clean data access.
            capability: The specific capability requested (e.g., 'load_tracking_data', 'nor_index').
            project_config: The project configuration for context.

        Returns:
            A dictionary containing analysis results. The structure depends on the capability,
            but it is **highly recommended** to include the following standard keys:

            - 'status' (str): 'success' or 'failed'. REQUIRED.
            - 'error' (str, optional): Description of the error if status is 'failed'.
            - 'message' (str, optional): A user-friendly message about the outcome.
            - 'capability_executed' (str): The capability string that was run. REQUIRED.
            - 'result_data' (Dict[str, Any], optional): The actual analysis results data.
            - 'output_file_paths' (List[str], optional): List of output file paths if the
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

    # -------------------------------
    # Project-level action contracts
    # -------------------------------
    def supported_project_actions(self) -> List[str]:
        """
        Optional: Return a list of project-level action identifiers this plugin supports
        (e.g., 'subjects_from_csv_folder', 'link_media_by_csv').

        CLI/GUI can query these to present available actions to users.
        Default: no project-level actions.
        """
        return []

    def run_action(self, action: str, params: Dict[str, Any], project_manager: 'ProjectManagerClean') -> Dict[str, Any]:
        """
        Optional: Execute a project-level action by name.

        Args:
            action: Action identifier, one of supported_project_actions().
            params: Arbitrary parameters passed from caller/CLI.
            project_manager: The ProjectManagerClean instance for core project operations.

        Returns:
            Dict containing at least 'status': 'success'|'failed'.

        Implement in concrete plugins that expose project-level actions.
        """
        raise NotImplementedError("Plugin does not implement project-level actions")