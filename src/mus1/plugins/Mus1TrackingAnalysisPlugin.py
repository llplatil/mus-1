from pathlib import Path
from datetime import datetime
# Relative imports to work inside 'Mus1_Refactor.plugins'
from ..core.metadata import PluginMetadata, ExperimentMetadata, ProjectState
from .base_plugin import BasePlugin
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple
import logging
from shapely.geometry import Point, Polygon, box, LineString
import traceback

# Assuming DataManager is importable for type hinting
try:
    from ..core.data_manager import DataManager
except ImportError:
    DataManager = Any # Placeholder if import fails during type checking

logger = logging.getLogger(__name__)

# Constants for clarity - Assuming DLC Handler provides the tracking file path
DATA_HANDLER_PLUGIN_NAME = "DeepLabCutHandler"
TRACKING_FILE_PARAM = "tracking_file_path" # Parameter name expected in the Handler's params
# NEW: Handler method name constant
HANDLER_GET_DATA_METHOD = "get_tracking_dataframe"

class Mus1TrackingAnalysisPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="Mus1TrackingAnalysis",
            date_created=datetime(2024, 7, 26),
            version="1.4",
            description="Core Mus1 plugin for analysis using standardized tracking data. Loads data on demand. Supports distance, speed, heatmaps, time in zones, object interaction, hemisphere analysis, gap filling, and specific paradigms (NOR, OF, EZM).",
            author="Lukash Platil / AI Assistant",
            supported_experiment_types=["NOR", "OpenField", "EZM"],
            supported_experiment_subtypes={
                "NOR": ["familiarization", "recognition"],
                "OpenField": ["habituation", "re-exposure"],
                # EZM does not have fixed subtypes in this phase; leave empty list or omit
            },
            readable_data_formats=['standard_tracking_df'],
            analysis_capabilities=[
                'distance_speed',
                'heatmap',
                'movement_plot',
                'time_in_zone',
                'time_near_object',
                'hemisphere_analysis',
                'nor_index',
                'of_metrics',
            ]
        )
    
    def analysis_capabilities(self) -> List[str]:
        """Return the list of analysis capabilities provided by this plugin."""
        return self.plugin_self_metadata().analysis_capabilities or []

    def readable_data_formats(self) -> List[str]:
        """Return the list of data formats this plugin conceptually reads."""
        return self.plugin_self_metadata().readable_data_formats or []

    def required_fields(self) -> List[str]:
        """
        Base required fields are minimal. Specific capabilities validate their own needs.
        """
        return []

    def optional_fields(self) -> List[str]:
        """
        Return a list of optional fields that can configure analyses.
        """
        return [
            "body_part",
            "arena_image",
            "notes",
            "arena_dimensions",
            "arena_zones",
            "object_roles",
            "session_stage",
            "proximity_threshold",
            "hemisphere_division",
            "gap_filling_method",
        ]
        
    def get_field_types(self) -> dict:
        """
        Return a dictionary mapping field names to their data types for UI generation.
        """
        return {
            "body_part": "string",
            "arena_image": "file",
            "notes": "text",
            "session_stage": "enum:familiarization,recognition",
            "object_roles": "dict",
            "arena_dimensions": "dict",
            "arena_zones": "dict",
            "proximity_threshold": "float",
            "hemisphere_division": "dict",
            "gap_filling_method": "enum:none,linear,spline,cubic",
        }

    def get_field_descriptions(self) -> dict:
        """
        Return a dictionary mapping field names to their descriptions.
        """
        return {
            "body_part": "Body part for primary analysis (e.g., 'nose'). Defaults to first tracked part if omitted.",
            "arena_image": "Optional background image for plots.",
            "notes": "User notes specific to this analysis run.",
            "session_stage": "Required for NOR analysis ('familiarization' or 'recognition').",
            "object_roles": "Required for Object Interaction/NOR. Maps tracked object name to role (JSON: {\"ObjNameInDLC\": \"familiar/novel\", ...}). Object names must match bodyparts in tracking data.",
            "arena_dimensions": "Required for OF. Arena size (JSON: {\"width\": float, \"height\": float, \"unit\": \"str\"}).",
            "arena_zones": "Required for Zone/OF analysis. Defines named zones (JSON: {\"zone_name\": {\"shape\": \"circle/rect/polygon\", \"coords\": [...]}, ...}). Coords: circle=[cx, cy, r], rect=[x, y, w, h], polygon=[[x1, y1], ...]",
            "proximity_threshold": "Distance threshold (in tracking data units) for object interaction.",
            "hemisphere_division": "Required for Hemisphere analysis. Defines dividing line (JSON: {\"type\": \"line\", \"coords\": [[x1, y1], [x2, y2]], \"side1_name\": \"Left\", ...})",
            "gap_filling_method": "Interpolation for missing data ('none', 'linear', 'spline', 'cubic'). Default: 'none'.",
        }

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """
        Perform plugin-specific validations *before* analyze_experiment is called.
        Checks parameters stored within experiment.plugin_params[plugin_name].
        Relies on ProjectManager calling this before execution.
        """
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})

        # Example: Check body_part parameter against project's master list
        body_part = plugin_params.get("body_part")
        if body_part and project_state.project_metadata and project_state.project_metadata.master_body_parts:
            valid_body_parts = {bp.name for bp in project_state.project_metadata.master_body_parts}
            if body_part not in valid_body_parts:
                # Log a warning, but don't raise here. Analyze will handle if the part isn't in the *loaded data*.
                logger.warning(f"validate_experiment ({plugin_name}): Specified body part '{body_part}' is not in the project's master list: {valid_body_parts}")

        # Example: Check required parameter formats if possible without loading data
        try:
            if "object_roles" in plugin_params and not isinstance(plugin_params["object_roles"], dict):
                 raise ValueError("'object_roles' parameter must be a valid dictionary (JSON object).")
            if "arena_zones" in plugin_params and not isinstance(plugin_params["arena_zones"], dict):
                 raise ValueError("'arena_zones' parameter must be a valid dictionary (JSON object).")
            # Add more format checks for dict parameters if needed
        except Exception as e:
            raise ValueError(f"Parameter format validation failed: {e}")

        # IMPORTANT: File existence for the *tracking data* should be checked here,
        # based on the associated Handler's parameters.
        handler_params = experiment.plugin_params.get(DATA_HANDLER_PLUGIN_NAME, {})
        tracking_file_path_str = handler_params.get(TRACKING_FILE_PARAM)
        if not tracking_file_path_str:
            raise ValueError(f"{plugin_name} requires the associated '{DATA_HANDLER_PLUGIN_NAME}' plugin "
                             f"to have the '{TRACKING_FILE_PARAM}' parameter set.")
        tracking_file_path = Path(tracking_file_path_str)
        if not tracking_file_path.exists():
            raise FileNotFoundError(f"Tracking data file specified by '{DATA_HANDLER_PLUGIN_NAME}' not found: {tracking_file_path}")
        if tracking_file_path.suffix.lower() not in ['.csv', '.h5', '.hdf5']:
             raise ValueError(f"Tracking data file must be .csv, .h5, or .hdf5. Found: {tracking_file_path.suffix}")

        logger.info(f"Basic validation passed for {plugin_name} on experiment {experiment.id}")

    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: DataManager, capability: str) -> Dict[str, Any]:
        """
        Performs analysis based on the requested capability. Loads tracking data on demand via DataManager and Handler plugin.
        """
        plugin_name = self.plugin_self_metadata().name
        analysis_result = {
            "status": "failed",
            "capability_executed": capability,
            "error": "Analysis did not complete." # Default error message
        }

        try:
            logger.info(f"Starting analysis capability '{capability}' for experiment '{experiment.id}' using {plugin_name}.")
            plugin_params = experiment.plugin_params.get(plugin_name, {}) # Params specific to this plugin

            # --- 1. Locate Tracking Data Path and Resolve Threshold ---
            handler_params = experiment.plugin_params.get(DATA_HANDLER_PLUGIN_NAME, {})
            tracking_file_path_str = handler_params.get(TRACKING_FILE_PARAM)

            if not tracking_file_path_str: # Should be caught by validate_experiment
                raise ValueError(f"Tracking file path missing from {DATA_HANDLER_PLUGIN_NAME} parameters.")

            tracking_file_path = Path(tracking_file_path_str)
            logger.info(f"Identified tracking data file path: {tracking_file_path}")

            # Resolve likelihood threshold using DataManager helper
            likelihood_threshold = data_manager.resolve_likelihood_threshold(experiment.id)
            analysis_result['likelihood_threshold_used'] = likelihood_threshold if likelihood_threshold is not None else 'None'


            # --- 2. Load Tracking Data via DataManager and Handler ---
            logger.info(f"Requesting DataManager to load data via handler '{DATA_HANDLER_PLUGIN_NAME}' method '{HANDLER_GET_DATA_METHOD}'.")
            try:
                 tracking_df = data_manager.call_handler_method(
                     handler_name=DATA_HANDLER_PLUGIN_NAME,
                     method_name=HANDLER_GET_DATA_METHOD,
                     # Pass necessary args for the handler's method
                     file_path=tracking_file_path,
                     likelihood_threshold=likelihood_threshold
                     # data_manager instance is passed automatically by call_handler_method if needed
                 )
            except FileNotFoundError as e:
                 logger.error(f"Handler reported file not found: {e}")
                 raise # Re-raise specific error
            except (ValueError, IOError) as e:
                 logger.error(f"Handler reported error loading data: {e}")
                 raise # Re-raise specific error
            except Exception as e:
                 logger.error(f"Unexpected error calling handler method via DataManager: {e}", exc_info=True)
                 raise RuntimeError(f"Failed to load data via handler: {e}")


            if tracking_df is None or tracking_df.empty:
                 raise ValueError(f"Loaded DataFrame via handler is empty or None from: {tracking_file_path}")

            logger.info(f"Successfully loaded tracking data via handler ({len(tracking_df)} frames).")


            # --- 3. Parameter Validation & Setup (using loaded data context) ---
            # Frame Rate
            resolved_frame_rate = data_manager.resolve_frame_rate(experiment_id=experiment.id)
            if isinstance(resolved_frame_rate, (int, float)) and resolved_frame_rate > 0:
                frame_rate = resolved_frame_rate
            else:
                logger.warning("Could not resolve frame rate, using default 60fps.")
                frame_rate = 60.0
            seconds_per_frame = 1.0 / frame_rate
            analysis_result['frame_rate_used'] = frame_rate # Record frame rate used

            # Body Part
            body_part_to_analyze = plugin_params.get("body_part")
            # Use the DataFrame loaded via the handler
            x_col, y_col = self._get_bodypart_columns(tracking_df, body_part_to_analyze) # Will raise ValueError if invalid
            actual_body_part_used = x_col[1] # Get name from the column tuple
            analysis_result["body_part_analyzed"] = actual_body_part_used
            if body_part_to_analyze is None:
                 analysis_result["info"] = f"Using default body part for analysis: {actual_body_part_used}"


            # --- 4. Gap Filling / Interpolation ---
            gap_method = plugin_params.get("gap_filling_method", "none").lower()
            # Use the specific bodypart columns from the handler-loaded DataFrame
            original_x_series = tracking_df[x_col].copy()
            original_y_series = tracking_df[y_col].copy()
            processed_x_series = original_x_series.copy()
            processed_y_series = original_y_series.copy()

            analysis_result["gap_filling_applied"] = gap_method
            if gap_method != "none":
                logger.info(f"Applying gap filling method: {gap_method}")
                try:
                    processed_x_series = self.handle_gaps(original_x_series, method=gap_method)
                    processed_y_series = self.handle_gaps(original_y_series, method=gap_method)
                    filled_x = original_x_series.isna().sum() - processed_x_series.isna().sum()
                    filled_y = original_y_series.isna().sum() - processed_y_series.isna().sum()
                    analysis_result["gaps_filled"] = {"x": filled_x, "y": filled_y}
                    logger.info(f"Gap filling '{gap_method}' completed. Filled {filled_x} in X, {filled_y} in Y.")
                except Exception as interp_error:
                    logger.warning(f"Failed gap filling '{gap_method}': {interp_error}. Proceeding with original data.")
                    analysis_result["gap_filling_warning"] = f"Failed: {interp_error}"
                    processed_x_series = original_x_series # Revert on error
                    processed_y_series = original_y_series

            # --- 5. Prepare DataFrame/Series for Analysis ---
            # analysis_df_subset = pd.DataFrame({'x': processed_x_series, 'y': processed_y_series}) # If needed

            # --- 6. Capability Execution ---
            capability_output = {} # Store capability-specific results

            if capability == 'distance_speed':
                # Use processed series directly
                speed_series = self.calculate_speed_from_series(processed_x_series, processed_y_series, frame_rate)
                total_distance = self.compute_total_distance_from_series(processed_x_series, processed_y_series)
                capability_output = {
                    "total_distance": total_distance,
                    "average_speed": float(speed_series.mean()) if not speed_series.empty else 0,
                    # "speed_series": speed_series.tolist() # Optional
                }

            elif capability == 'heatmap':
                 # Pass the processed series to the plotting function
                heat_map_fig = self.generate_heat_map_from_series(processed_x_series, processed_y_series)
                # Convert fig to bytes or save to file and return path
                heatmap_bytes = self._convert_fig_to_bytes(heat_map_fig)
                # Example saving:
                # heatmap_path = data_manager.get_analysis_output_path(experiment.id, f"{capability}_heatmap.png")
                # heat_map_fig.savefig(heatmap_path)
                # plt.close(heat_map_fig)
                # capability_output["output_file_paths"] = {"heatmap_png": str(heatmap_path)}
                capability_output["heatmap_png_bytes"] = heatmap_bytes # Returning bytes for now

            elif capability == 'movement_plot':
                 # Pass the processed series
                movement_fig = self.plot_movement_over_time_from_series(processed_x_series, processed_y_series)
                movement_bytes = self._convert_fig_to_bytes(movement_fig)
                capability_output["movement_plot_png_bytes"] = movement_bytes

            elif capability == 'time_in_zone':
                zones_def = plugin_params.get("arena_zones")
                arena_dims = plugin_params.get("arena_dimensions")
                if not zones_def: raise ValueError("'arena_zones' parameter required.")
                # Use the processed series for zone checks
                time_per_zone = self._calculate_time_in_zones_from_series(
                    processed_x_series, processed_y_series, zones_def, seconds_per_frame, arena_dims
                )
                capability_output["time_per_zone_seconds"] = time_per_zone

            elif capability == 'time_near_object':
                object_roles = plugin_params.get("object_roles")
                proximity_threshold = plugin_params.get("proximity_threshold", 10.0)
                if not object_roles: raise ValueError("'object_roles' parameter required.")
                if proximity_threshold <= 0: raise ValueError("proximity_threshold must be positive.")

                # Get object coords from ORIGINAL DataFrame (loaded via handler)
                # Ensure _get_object_coords uses the full tracking_df
                object_coords = self._get_object_coords(tracking_df, list(object_roles.keys()))
                # Use processed series for subject position
                time_near = self._calculate_time_near_objects_from_series(
                    processed_x_series, processed_y_series, object_coords, proximity_threshold, seconds_per_frame
                )
                capability_output["time_near_object_seconds"] = time_near
                capability_output["proximity_threshold"] = proximity_threshold
                capability_output["object_roles_used"] = object_roles

            elif capability == 'hemisphere_analysis':
                division_def = plugin_params.get("hemisphere_division")
                if not division_def or division_def.get("type") != "line" or "coords" not in division_def or len(division_def["coords"]) != 2:
                    raise ValueError("'hemisphere_division' definition invalid.")
                # Use processed series
                hemisphere_times = self._calculate_hemisphere_time_from_series(
                    processed_x_series, processed_y_series, division_def, seconds_per_frame
                )
                capability_output["hemisphere_times_seconds"] = hemisphere_times
                capability_output["division_definition"] = division_def

            elif capability == 'nor_index':
                session_stage = plugin_params.get("session_stage")
                object_roles = plugin_params.get("object_roles")
                proximity_threshold = plugin_params.get("proximity_threshold", 50.0)
                if not session_stage or not object_roles: raise ValueError("NOR requires 'session_stage' and 'object_roles'.")
                if proximity_threshold <= 0: raise ValueError("proximity_threshold must be positive.")

                familiar_objs = [k for k, v in object_roles.items() if v == 'familiar']
                novel_objs = [k for k, v in object_roles.items() if v == 'novel']

                if session_stage == 'recognition' and (not familiar_objs or not novel_objs):
                    raise ValueError("Recognition stage requires defined 'familiar' and 'novel' objects.")
                if session_stage == 'familiarization' and novel_objs:
                    logger.warning("Novel objects defined during familiarization, treating as familiar.")
                    familiar_objs.extend(novel_objs)
                    novel_objs = []

                all_object_ids = familiar_objs + novel_objs
                # Get object coords from ORIGINAL df
                object_coords = self._get_object_coords(tracking_df, all_object_ids)
                # Use processed series for subject position
                time_near = self._calculate_time_near_objects_from_series(
                    processed_x_series, processed_y_series, object_coords, proximity_threshold, seconds_per_frame
                )

                time_familiar_total = sum(time_near.get(obj_id, 0.0) for obj_id in familiar_objs)
                time_novel_total = sum(time_near.get(obj_id, 0.0) for obj_id in novel_objs)
                di = self._calculate_nor_di(time_novel_total, time_familiar_total)

                capability_output = {
                    "phase": session_stage,
                    "proximity_threshold": proximity_threshold,
                    "metrics": {
                        "discrimination_index": di,
                        "time_novel_seconds": time_novel_total,
                        "time_familiar_seconds": time_familiar_total,
                        "time_near_each_object": time_near
                    }
                }

            elif capability == 'of_metrics':
                arena_dims = plugin_params.get("arena_dimensions")
                if not arena_dims or not all(k in arena_dims for k in ["width", "height", "unit"]):
                     raise ValueError("OF requires 'arena_dimensions' (width, height, unit).")
                arena_zones = plugin_params.get("arena_zones", {})

                # Use processed series
                speed_series = self.calculate_speed_from_series(processed_x_series, processed_y_series, frame_rate)
                total_distance = self.compute_total_distance_from_series(processed_x_series, processed_y_series)

                time_in_center = 0.0
                if "center" in arena_zones: # Check if a 'center' zone is defined
                    time_per_zone = self._calculate_time_in_zones_from_series(
                        processed_x_series, processed_y_series, arena_zones, seconds_per_frame, arena_dims
                    )
                    time_in_center = time_per_zone.get("center", 0.0)
                else:
                     logger.warning("No zone named 'center' found in arena_zones for OF metrics.")

                                # Additional OF metrics
                entries_to_center = 0
                if "center" in arena_zones:
                    try:
                        center_def = arena_zones["center"]
                        shape = center_def.get("shape", "").lower()
                        coords = center_def.get("coords", [])
                        if shape == "circle" and len(coords) == 3:
                            center_geom = Point(coords[0], coords[1]).buffer(coords[2])
                        elif shape == "rect" and len(coords) == 4:
                            center_geom = box(coords[0], coords[1], coords[2], coords[3])
                        elif shape == "polygon" and len(coords) >= 3:
                            center_geom = Polygon(coords)
                        else:
                            center_geom = None
                        if center_geom is not None and center_geom.is_valid:
                            points_df = pd.DataFrame({
                                'x': processed_x_series,
                                'y': processed_y_series
                            }).dropna()
                            in_center = points_df.apply(lambda r: center_geom.contains(Point(r['x'], r['y'])), axis=1).astype(int)
                            # Count 0->1 transitions
                            shifted = in_center.shift(fill_value=0)
                            entries_to_center = int(((shifted == 0) & (in_center == 1)).sum())
                    except Exception as e:
                        logger.warning(f"Failed to compute entries_to_center: {e}")

                # Thigmotaxis/perimeter: time near walls within a margin
                thigmotaxis_time = 0.0
                perimeter_time = 0.0
                try:
                    width = float(arena_dims["width"]) if arena_dims and "width" in arena_dims else None
                    height = float(arena_dims["height"]) if arena_dims and "height" in arena_dims else None
                    if width and height:
                        margin = 0.1 * min(width, height)  # 10% border
                        x = pd.to_numeric(processed_x_series, errors='coerce')
                        y = pd.to_numeric(processed_y_series, errors='coerce')
                        in_border = (
                            (x <= margin) | (x >= (width - margin)) |
                            (y <= margin) | (y >= (height - margin))
                        )
                        thigmotaxis_time = float(in_border.sum()) * seconds_per_frame
                        # perimeter_time can be same as thigmotaxis here (alias for clarity)
                        perimeter_time = thigmotaxis_time
                except Exception as e:
                    logger.warning(f"Failed to compute thigmotaxis/perimeter metrics: {e}")

                capability_output = {
                    "metrics": {
                        "total_distance": total_distance,
                        "average_speed": float(speed_series.mean()) if not speed_series.empty else 0,
                        "time_in_center_seconds": time_in_center,
                        "entries_to_center": entries_to_center,
                        "thigmotaxis_time_seconds": thigmotaxis_time,
                        "perimeter_time_seconds": perimeter_time,
                    },
                    "arena_info": { "dimensions": arena_dims }
                }
# No 'extract_video_frames' for now

            else:
                raise ValueError(f"Unknown analysis capability requested: {capability}")

            # --- 7. Finalize Success Result ---
            analysis_result.update(capability_output) # Add capability-specific results
            analysis_result["status"] = "success"
            analysis_result["message"] = f"Capability '{capability}' completed successfully for body part '{actual_body_part_used}'."
            analysis_result.pop("error", None) # Remove default error message on success
            logger.info(f"Successfully completed '{capability}' for experiment '{experiment.id}'.")
            return analysis_result

        # --- Error Handling ---
        except FileNotFoundError as e:
             error_msg = f"Required file not found: {e}"
             logger.error(f"{error_msg} during analysis for experiment '{experiment.id}'", exc_info=False)
             analysis_result["error"] = error_msg
             return analysis_result
        except (ValueError, KeyError, TypeError, RuntimeError) as e: # Catch common data/param/runtime errors
             error_msg = f"Error during analysis: {e}"
             # Log traceback for RuntimeError which might hide underlying issues
             exc_info_flag = isinstance(e, RuntimeError)
             logger.error(f"{error_msg} during analysis for experiment '{experiment.id}'", exc_info=exc_info_flag)
             analysis_result["error"] = error_msg
             return analysis_result
        except Exception as e:
             error_msg = f"An unexpected error occurred: {e}"
             logger.error(f"{error_msg} during analysis capability '{capability}' for experiment '{experiment.id}'", exc_info=True)
             analysis_result["error"] = error_msg
             return analysis_result

    def handle_gaps(self, series: pd.Series, method: str = 'linear', order: Optional[int] = None) -> pd.Series:
        """
        Handle gaps in tracking data by interpolating missing values.

        Args:
            series: The Pandas Series with potential NaNs.
            method: Interpolation method ('linear', 'spline', 'cubic', 'polynomial', etc.).
                    See pandas.Series.interpolate documentation.
            order: Order for 'spline' or 'polynomial' interpolation.

        Returns:
            A new Pandas Series with gaps interpolated.
        """
        if method == 'none':
            return series.copy() # Return a copy if no interpolation

        # Ensure numeric type for interpolation
        numeric_series = pd.to_numeric(series, errors='coerce')

        if numeric_series.isna().all():
             logger.warning("Series contains only NaNs, cannot interpolate.")
             return numeric_series # Return the all-NaN series

        # Pandas interpolate handles various methods
        try:
            if method in ['spline', 'polynomial'] and order is None:
                 # Default order for spline/polynomial if not specified
                 order = 3 if method == 'spline' else 2
                 logger.debug(f"Using default order {order} for {method} interpolation.")

            if order is not None:
                 interpolated_series = numeric_series.interpolate(method=method, order=order, limit_direction='both')
            else:
                 interpolated_series = numeric_series.interpolate(method=method, limit_direction='both')

            # Check if interpolation actually filled any NaNs
            if numeric_series.isna().sum() > 0 and interpolated_series.isna().sum() == numeric_series.isna().sum():
                 logger.warning(f"Interpolation method '{method}' did not fill any NaNs. Check data or method.")
            elif interpolated_series.isna().any():
                 logger.warning(f"Interpolation method '{method}' left some NaNs unfilled (possibly at ends).")

            return interpolated_series
        except Exception as e:
            logger.error(f"Error during interpolation with method '{method}': {e}")
            raise # Re-raise the exception

    def calculate_speed_from_series(self, x_series: pd.Series, y_series: pd.Series, frame_rate: float) -> pd.Series:
        """Calculate speed from X and Y series."""
        dx = x_series.diff()
        dy = y_series.diff()
        # Ensure dx and dy are numeric before calculating distance
        dx = pd.to_numeric(dx, errors='coerce')
        dy = pd.to_numeric(dy, errors='coerce')
        distance = np.sqrt(dx**2 + dy**2).fillna(0)
        speed = distance * frame_rate
        return speed

    def compute_total_distance_from_series(self, x_series: pd.Series, y_series: pd.Series) -> float:
        """Compute total distance from X and Y series."""
        dx = x_series.diff()
        dy = y_series.diff()
        dx = pd.to_numeric(dx, errors='coerce')
        dy = pd.to_numeric(dy, errors='coerce')
        distance = np.sqrt(dx**2 + dy**2)
        return float(distance.sum(skipna=True))

    def generate_heat_map_from_series(self, x_series: pd.Series, y_series: pd.Series, bins: int = 50):
        """Generate a heat map from X and Y series."""
        x = x_series.dropna()
        y = y_series.dropna()
        fig, ax = plt.subplots()
        if x.empty or y.empty:
             ax.set_title("Heat Map (No Data)")
        else:
             heatmap, xedges, yedges = np.histogram2d(x, y, bins=bins)
             extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
             cax = ax.imshow(heatmap.T, extent=extent, origin='lower', cmap='hot', aspect='auto')
             fig.colorbar(cax, label='Frequency')
             ax.set_title("Heat Map of Positions")
        ax.set_xlabel("X coordinate")
        ax.set_ylabel("Y coordinate")
        return fig

    def plot_movement_over_time_from_series(self, x_series: pd.Series, y_series: pd.Series):
        """Plot cumulative movement from X and Y series."""
        fig, ax = plt.subplots()
        dx = x_series.diff().fillna(0)
        dy = y_series.diff().fillna(0)
        dx = pd.to_numeric(dx, errors='coerce').fillna(0)
        dy = pd.to_numeric(dy, errors='coerce').fillna(0)
        distances = np.sqrt(dx**2 + dy**2)
        cumulative_distance = distances.cumsum()

        if cumulative_distance.empty:
             ax.set_title("Cumulative Movement (No Data)")
        else:
             ax.plot(cumulative_distance.index, cumulative_distance) # Use index for x-axis (frames)
             ax.set_title("Cumulative Movement Over Time")
        ax.set_xlabel("Frame")
        ax.set_ylabel("Cumulative Distance")
        return fig

    def _convert_fig_to_bytes(self, fig) -> bytes:
        """
        Convert a matplotlib figure to PNG bytes.
        """
        if fig is None:
            return b""
        buf = BytesIO()
        try:
            fig.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            img_bytes = buf.getvalue()
        finally:
            plt.close(fig)
        return img_bytes

    def _get_bodypart_columns(self, df: pd.DataFrame, body_part_name: Optional[str]) -> Tuple[tuple, tuple]:
        """Finds the (scorer, bodypart, coord) tuples for x and y of the given body part."""
        if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
             raise ValueError("DataFrame columns are not the expected 3-level MultiIndex (scorer, bodyparts, coords).")

        available_bodyparts = df.columns.get_level_values(1).unique().tolist()
        # Ensure 'scorer' is not treated as a bodypart if it exists at this level
        if 'scorer' in available_bodyparts:
             available_bodyparts.remove('scorer')

        if not available_bodyparts:
             raise ValueError("No trackable body parts found in DataFrame columns.")

        if body_part_name:
            if body_part_name not in available_bodyparts:
                raise ValueError(f"Specified body part '{body_part_name}' not found in available parts: {available_bodyparts}")
            target_bp = body_part_name
        else:
            target_bp = available_bodyparts[0] # Default to first
            logger.debug(f"No body part specified, defaulting to first found: {target_bp}")

        # Find columns for the target body part
        possible_cols = df.columns[df.columns.get_level_values(1) == target_bp]
        try:
            x_col = possible_cols[possible_cols.get_level_values(2) == 'x'][0]
            y_col = possible_cols[possible_cols.get_level_values(2) == 'y'][0]
            return x_col, y_col
        except IndexError:
            # Provide more specific error message
            coords_found = possible_cols.get_level_values(2).unique().tolist()
            raise ValueError(f"Could not find both 'x' and 'y' coordinates for body part '{target_bp}'. Found: {coords_found}. Check DataFrame structure.")

    def _get_object_coords(self, df: pd.DataFrame, object_ids: List[str]) -> Dict[str, Tuple[float, float]]:
        """Gets the average x, y coordinates for stationary objects from the DataFrame."""
        # This should use the ORIGINAL, non-interpolated DataFrame 'df'
        coords = {}
        missing_objects = []
        for obj_id in object_ids:
            try:
                x_col, y_col = self._get_bodypart_columns(df, obj_id)
                # Use median for robustness against tracking glitches if object coords aren't perfectly static
                avg_x = df[x_col].median(skipna=True)
                avg_y = df[y_col].median(skipna=True)
                if pd.isna(avg_x) or pd.isna(avg_y):
                     logger.warning(f"Could not determine stable coordinates (median) for object '{obj_id}'. Trying mean.")
                     avg_x = df[x_col].mean(skipna=True)
                     avg_y = df[y_col].mean(skipna=True)
                     if pd.isna(avg_x) or pd.isna(avg_y):
                          logger.error(f"No valid coordinates found for object '{obj_id}' even using mean.")
                          missing_objects.append(obj_id)
                          continue # Skip this object
                coords[obj_id] = (float(avg_x), float(avg_y))
            except ValueError as e: # Catch error from _get_bodypart_columns if object not found
                logger.error(f"Error finding columns for object '{obj_id}': {e}")
                missing_objects.append(obj_id)
        if missing_objects:
            # Raise an error if any objects defined in parameters couldn't be found/processed
            raise ValueError(f"Could not get coordinates for required objects: {', '.join(missing_objects)}. Ensure they are tracked bodyparts.")
        return coords

    def _calculate_time_in_zones_from_series(self, x_series: pd.Series, y_series: pd.Series, zones_def: Dict, seconds_per_frame: float, arena_dims: Optional[Dict] = None) -> Dict[str, float]:
        """Calculates time spent in defined geometric zones using Shapely, taking Series input."""
        time_per_zone = {zone_name: 0.0 for zone_name in zones_def}
        shapely_zones = {}

        for zone_name, definition in zones_def.items():
            shape = definition.get("shape", "").lower()
            coords = definition.get("coords", [])
            try:
                if shape == "circle" and len(coords) == 3: # [cx, cy, radius]
                    shapely_zones[zone_name] = Point(coords[0], coords[1]).buffer(coords[2])
                elif shape == "rect" and len(coords) == 4: # [x_min, y_min, x_max, y_max]
                    shapely_zones[zone_name] = box(coords[0], coords[1], coords[2], coords[3])
                elif shape == "polygon" and len(coords) >= 3: # [[x1, y1], [x2, y2], ...]
                    shapely_zones[zone_name] = Polygon(coords)
                else:
                    logger.warning(f"Invalid shape ('{shape}') or coords for zone '{zone_name}'. Skipping.")
                    continue
            except Exception as e:
                 logger.warning(f"Error creating geometry for zone '{zone_name}': {e}. Skipping.")
                 continue

        # Combine x and y series, dropping frames where either is NaN
        points_df = pd.DataFrame({'x': x_series, 'y': y_series}).dropna()
        points = [Point(row.x, row.y) for _, row in points_df.iterrows()]

        for zone_name, zone_geom in shapely_zones.items():
            if zone_geom is None or not zone_geom.is_valid:
                logger.warning(f"Invalid geometry for zone '{zone_name}', skipping time calculation.")
                continue
            try:
                # Check containment for valid points
                frames_in_zone = sum(1 for p in points if zone_geom.contains(p))
                time_per_zone[zone_name] = frames_in_zone * seconds_per_frame
            except Exception as e:
                 logger.error(f"Error checking points in zone '{zone_name}': {e}")
                 time_per_zone[zone_name] = -1 # Indicate error

        return time_per_zone

    def _calculate_time_near_objects_from_series(self, x_series: pd.Series, y_series: pd.Series, object_coords: Dict[str, Tuple[float, float]], proximity_threshold: float, seconds_per_frame: float) -> Dict[str, float]:
        """Calculates time spent within proximity_threshold of objects using Series input."""
        time_near = {obj_id: 0.0 for obj_id in object_coords}
        squared_threshold = proximity_threshold ** 2

        # Combine series and drop NaNs to iterate over valid points only
        points_df = pd.DataFrame({'x': x_series, 'y': y_series}).dropna()

        for obj_id, (obj_x, obj_y) in object_coords.items():
            # Calculate squared distance for valid frames efficiently
            dist_sq = (points_df['x'] - obj_x)**2 + (points_df['y'] - obj_y)**2
            frames_near = (dist_sq <= squared_threshold).sum() # Sum boolean True values
            time_near[obj_id] = frames_near * seconds_per_frame

        return time_near

    def _calculate_hemisphere_time_from_series(self, x_series: pd.Series, y_series: pd.Series, division_def: Dict, seconds_per_frame: float) -> Dict[str, float]:
        """Calculates time on either side of a defined line using Series input."""
        if division_def.get("type") != "line" or len(division_def.get("coords", [])) != 2:
            raise ValueError("Invalid hemisphere_division definition for line type.")

        coords = division_def["coords"]
        side1_name = division_def.get("side1_name", "side1")
        side2_name = division_def.get("side2_name", "side2")
        line_name = division_def.get("line_name", "dividing_line")
        (x1, y1), (x2, y2) = coords[0], coords[1]
        if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
            raise ValueError("Points defining the hemisphere line are identical.")

        # Line equation: ax + by + c = 0. Normal (a, b) = (dy, -dx)
        a, b = (y2 - y1), -(x2 - x1)
        c = -(a * x1 + b * y1)

        # Combine series and drop NaNs
        points_df = pd.DataFrame({'x': x_series, 'y': y_series}).dropna()

        # Evaluate line equation for valid points
        line_eval = a * points_df['x'] + b * points_df['y'] + c

        tolerance = 1e-9
        in_side1 = (line_eval < -tolerance).sum()
        in_side2 = (line_eval > tolerance).sum()
        on_line = (line_eval.abs() <= tolerance).sum()

        return {
            side1_name: in_side1 * seconds_per_frame,
            side2_name: in_side2 * seconds_per_frame,
            line_name: on_line * seconds_per_frame
        }

    def _calculate_nor_di(self, time_novel: float, time_familiar: float) -> Optional[float]:
        """Calculates Novel Object Recognition Discrimination Index (DI)."""
        total_time = time_novel + time_familiar
        if total_time > 0:
            return (time_novel - time_familiar) / total_time
        else:
            logger.warning("Total interaction time with familiar and novel objects is zero. DI cannot be calculated.")
            return None # Avoid division by zero 
