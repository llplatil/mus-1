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

    def plugin_custom_style(self) -> Optional[str]:
        """Return an optional CSS snippet for plugin-specific styling. Default is None."""
        return None

    def get_styling_preferences(self) -> Dict[str, Any]:
        """
        Return standardized styling preferences for this plugin.
        
        This replaces the need for custom CSS by providing a structured way
        for plugins to specify their styling needs.
        
        Returns:
            Dictionary with styling preferences using standardized keys:
            {
                "colors": {
                    "primary": "default"|"accent"|"custom-hex",  # Primary color theme
                    "secondary": "default"|"accent"|"custom-hex", # Secondary color
                    "backgrounds": {
                        "preprocessing": "default"|"subtle"|"prominent",
                        "analysis": "default"|"subtle"|"prominent", 
                        "results": "default"|"subtle"|"prominent"
                    }
                },
                "borders": {
                    "style": "default"|"rounded"|"sharp"|"none",
                    "width": "thin"|"medium"|"thick"
                },
                "spacing": {
                    "internal": "compact"|"default"|"spacious",
                    "between_elements": "compact"|"default"|"spacious"
                }
            }
        """
        # Default values - plugins can override this method to customize
        return {
            "colors": {
                "primary": "default", 
                "secondary": "default",
                "backgrounds": {
                    "preprocessing": "default",
                    "analysis": "default",
                    "results": "default"
                }
            },
            "borders": {
                "style": "default",
                "width": "medium"
            },
            "spacing": {
                "internal": "default",
                "between_elements": "default"
            }
        }

    def get_field_styling(self, field_name: str, processing_stage: str = None) -> Dict[str, str]:
        """
        Get styling properties for a field based on its status.
        
        Args:
            field_name: The name of the field to style
            processing_stage: Override the processing stage (uses field_stage_map by default)
            
        Returns:
            Dictionary with styling class names
        """
        is_required = field_name in self.required_fields()
        field_stage = processing_stage or self._get_field_processing_stage(field_name)
        plugin_id = self.plugin_self_metadata().name.replace(" ", "_").lower()
        
        styling = {
            "widget_class": f"plugin-field plugin-{plugin_id}-field",
            "status_class": "plugin-field-required" if is_required else "plugin-field-optional",
            "stage_class": f"plugin-stage-{field_stage}"
        }
        
        return styling
    
    def _get_field_processing_stage(self, field_name: str) -> str:
        """
        Determine processing stage for a field.
        
        Args:
            field_name: The field name to check
            
        Returns:
            String representing the processing stage ('preprocessing', 'analysis', 'results', or 'unknown')
        """
        field_to_stage_map = getattr(self, "field_stage_map", {})
        return field_to_stage_map.get(field_name, "unknown")

    def get_style_manifest(self) -> Optional[Dict[str, Any]]:
        """Return a style manifest for plugin-specific style overrides.

        By default, no style overrides are provided. Plugins can override this method
        to return a manifest of the form:
            {
                'base': { '$VARIABLE': 'value', ... }
            }
        """
        return None
