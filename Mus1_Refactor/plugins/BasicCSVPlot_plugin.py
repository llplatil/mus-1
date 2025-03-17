from pathlib import Path
from datetime import datetime
from core.metadata import PluginMetadata
from plugins.base_plugin import BasePlugin
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO
from typing import Optional, Dict, Any

class BasicCSVPlotPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="BasicCSVPlot",
            date_created=datetime(2025, 2, 15),
            version="1.0",
            description="A plugin for analyzing basic CSV files",
            author="Lukash Platil",
            supported_experiment_types=["CSV", "NOR", "OpenField"],
            supported_processing_stages=["processing", "analyzed"],
            supported_data_sources=["DLC", "Manual"]
        )
    
    def required_fields(self):
        """
        Return a list of fields required by this plugin for a valid experiment.
        """
        return ["csv_path"]

    def optional_fields(self):
        """
        Return a list of optional fields that can be attached to an experiment.
        For example: body_part, extracted_image, video.
        """
        return ["body_part", "extracted_image", "video"]
        
    def get_supported_processing_stages(self) -> list:
        """Return processing stages this plugin supports."""
        return ["processing", "analyzed"]
        
    def get_field_types(self) -> dict:
        """
        Return a dictionary mapping field names to their data types.
        This helps the UI generate appropriate input widgets.
        """
        return {
            "csv_path": "file",
            "body_part": "string",
            "extracted_image": "file",
            "video": "file"
        }

    def get_field_descriptions(self) -> dict:
        """
        Return a dictionary mapping field names to their descriptions.
        This provides context for users when filling out the form.
        """
        return {
            "csv_path": "Path to the CSV file containing tracking data",
            "body_part": "Name of the body part to analyze (e.g., 'nose', 'tail')",
            "extracted_image": "Optional image file to overlay data on",
            "video": "Optional source video file"
        }

    def validate_experiment(self, experiment, project_state):
        """
        Validate the experiment by checking:
        - The CSV file path is valid (exists).
        - If a body_part is provided in plugin_params, it exists in the project's master body parts.
        - The CSV file contains tracked body parts that match at least one of the project's master body parts.
        """
        csv_path = experiment.plugin_params.get(self.plugin_self_metadata().name, {}).get("csv_path")
        if not csv_path or not Path(csv_path).exists():
            raise ValueError(f"CSV file path missing or not found: {csv_path}")

        body_part = experiment.plugin_params.get(self.plugin_self_metadata().name, {}).get("body_part")
        if body_part and project_state.project_metadata and project_state.project_metadata.master_body_parts:
            valid_body_parts = {bp.name for bp in project_state.project_metadata.master_body_parts}
            if body_part not in valid_body_parts:
                raise ValueError(f"Specified body part '{body_part}' is not in the project's master body parts: {valid_body_parts}")

        # New check: Validate that the CSV file tracks at least one body part from the project's master body parts
        tracked_body_parts = BasePlugin.extract_bodyparts_from_dlc_csv(Path(csv_path))
        if project_state.project_metadata and project_state.project_metadata.master_body_parts:
            project_body_parts = {bp.name for bp in project_state.project_metadata.master_body_parts}
            if not tracked_body_parts.intersection(project_body_parts):
                raise ValueError(f"The CSV file tracked body parts {tracked_body_parts} do not match any of the project's master body parts {project_body_parts}.")

        # Additional validations can be added as needed.

    def analyze_experiment(self, experiment, data_manager=None):
        """
        Loads the CSV using data_manager and performs analysis specific to BasicCSVPlot.
        If a body_part is specified in experiment.plugin_params, extracts its coordinate columns
        and computes movement metrics including total distance, cumulative movement plot, and heat map.
        Returns a dictionary with analysis results, including figures converted to PNG bytes.
        """
        plugin_name = self.plugin_self_metadata().name
        csv_path = experiment.plugin_params.get(plugin_name, {}).get("csv_path")
        if not csv_path:
            return {"error": "No CSV path set"}

        if not data_manager:
            return {"error": f"DataManager not provided. CSV path: {csv_path}"}

        try:
            df = data_manager.load_dlc_tracking_csv(Path(csv_path))
            analysis_result = {"status": "success", "rows": len(df)}

            # If a specific body part is provided, perform detailed analysis
            body_part = experiment.plugin_params.get(plugin_name, {}).get("body_part")
            if body_part:
                # Find x and y coordinate columns for the specified body part in the multi-index
                try:
                    x_col = [col for col in df.columns if col[1] == body_part and col[2] == 'x'][0]
                    y_col = [col for col in df.columns if col[1] == body_part and col[2] == 'y'][0]
                except IndexError:
                    return {"error": f"Coordinate columns for body part '{body_part}' not found in CSV."}

                # Assume a default frame_rate; this could be enhanced to extract from state
                frame_rate = 60

                # Perform movement calculations using plugin helper methods
                speed_series = self.calculate_speed(df, x_col, y_col, frame_rate)
                total_distance = self.compute_total_distance(df, x_col, y_col)
                movement_fig = self.plot_movement_over_time(df, x_col, y_col, frame_rate)
                heat_map_fig = self.generate_heat_map(df, x_col, y_col)

                analysis_result["body_part"] = body_part
                analysis_result["total_distance"] = total_distance
                analysis_result["average_speed"] = float(speed_series.mean())

                # Convert figures to PNG bytes so they can be passed to state/UI
                analysis_result["movement_plot"] = self._convert_fig_to_bytes(movement_fig)
                analysis_result["heat_map"] = self._convert_fig_to_bytes(heat_map_fig)

            # Include optional parameters if provided
            if "extracted_image" in experiment.plugin_params.get(plugin_name, {}):
                analysis_result["extracted_image"] = experiment.plugin_params[plugin_name]["extracted_image"]
            if "video" in experiment.plugin_params.get(plugin_name, {}):
                analysis_result["video"] = experiment.plugin_params[plugin_name]["video"]

            return analysis_result
        except Exception as e:
            return {"error": str(e)}

    def calculate_speed(self, df: pd.DataFrame, x_col: str, y_col: str, frame_rate: int = 60) -> pd.Series:
        """
        Calculate speed (distance per unit time) from raw tracking data.
        Computes the Euclidean distance between consecutive frames and multiplies by the frame_rate.
        """
        dx = df[x_col].diff()
        dy = df[y_col].diff()
        distance = np.sqrt(dx**2 + dy**2)
        speed = distance * frame_rate
        return speed

    def handle_gaps(self, series: pd.Series, method: str = 'linear') -> pd.Series:
        """
        Handle gaps in tracking data by interpolating missing values using the specified method.
        """
        return series.interpolate(method=method)

    def compute_total_distance(self, df: pd.DataFrame, x_col: str, y_col: str) -> float:
        """
        Compute the total distance traveled based on tracking data.
        """
        dx = df[x_col].diff()
        dy = df[y_col].diff()
        distance = np.sqrt(dx**2 + dy**2)
        return float(distance.sum())

    def generate_heat_map(self, df: pd.DataFrame, x_col: str, y_col: str, bins: int = 50):
        """
        Generate a heat map of positions from tracking data.
        Returns a matplotlib figure object displaying the heat map.
        """
        x = df[x_col].dropna()
        y = df[y_col].dropna()
        heatmap, xedges, yedges = np.histogram2d(x, y, bins=bins)
        extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
        
        fig, ax = plt.subplots()
        cax = ax.imshow(heatmap.T, extent=extent, origin='lower', cmap='hot', aspect='auto')
        fig.colorbar(cax)
        ax.set_title("Heat Map of Positions")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        return fig

    def plot_movement_over_time(self, df: pd.DataFrame, x_col: str, y_col: str, frame_rate: int = 60, start: int = 0, end: int = None):
        """
        Plot the cumulative movement over time from tracking data.
        Allows plotting over a subinterval specified by start and end frame indices.
        Returns a matplotlib figure object of the movement plot.
        """
        if end is None or end > len(df):
            end = len(df)
        sub_df = df.iloc[start:end]
        dx = sub_df[x_col].diff().fillna(0)
        dy = sub_df[y_col].diff().fillna(0)
        distances = np.sqrt(dx**2 + dy**2)
        cumulative_distance = distances.cumsum()
        
        fig, ax = plt.subplots()
        ax.plot(sub_df.index, cumulative_distance)
        ax.set_title("Cumulative Movement Over Time")
        ax.set_xlabel("Frame")
        ax.set_ylabel("Cumulative Distance")
        return fig

    def overlay_movement_on_arena_image(self, movement_fig, arena_image_path: Path, output_path: Path):
        """
        Overlay the movement plot on an arena image.
        Saves the final overlaid image to output_path and returns the resulting image.
        """
        buf = BytesIO()
        movement_fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        movement_img = Image.open(buf)
        
        if not arena_image_path.exists():
            raise FileNotFoundError(f"Arena image not found: {arena_image_path}")
        arena_img = Image.open(arena_image_path).convert("RGBA")
        
        movement_img = movement_img.resize(arena_img.size)
        movement_img = movement_img.convert("RGBA")
        
        overlaid_img = Image.alpha_composite(arena_img, movement_img)
        overlaid_img.save(output_path)
        return overlaid_img

    def _convert_fig_to_bytes(self, fig) -> bytes:
        """
        Convert a matplotlib figure to PNG bytes.
        """
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        return buf.getvalue()

    def get_styling_preferences(self) -> dict:
        """
        Specify styling preferences for the BasicCSVPlot plugin.
        
        This uses the standardized styling options defined in BasePlugin
        to ensure consistent appearance across the application.
        """
        return {
            "colors": {
                "primary": "accent",  # Use the accent color for primary elements
                "secondary": "default",
                "backgrounds": {
                    "preprocessing": "subtle",  # Use a subtle background for preprocessing
                    "analysis": "prominent",    # Make analysis sections stand out more
                    "results": "default"
                }
            },
            "borders": {
                "style": "rounded",  # Use rounded borders for a more polished look
                "width": "medium"
            },
            "spacing": {
                "internal": "spacious",  # Use more padding inside elements
                "between_elements": "default"
            }
        }

    def get_style_manifest(self) -> Optional[Dict[str, Any]]:
        """
        Return a style manifest for plugin-specific style overrides.
        This manifest is used by ThemeManager to append plugin CSS rules.

        The manifest here includes overrides for required vs optional field indicators
        and for a plugin-specific stage background.
        """
        return {
            "base": {
                "$PLUGIN_REQUIRED_COLOR": "#ff8787",  # Red color for required fields
                "$PLUGIN_OPTIONAL_COLOR": "#4dabf7",   # Blue color for optional fields
                "$PLUGIN_COMPONENT_ACCENT": "#BB86FC",   # Accent border for plugin components
                "$PLUGIN_ANALYSIS_BG": "#EEEEEE"        # Light gray background for analysis stage
            }
        } 