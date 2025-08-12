import logging
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Set
from datetime import datetime

from ..core.metadata import PluginMetadata, ExperimentMetadata
from .base_plugin import BasePlugin
from ..core.data_manager import DataManager

# Backwards-compat alias if other code imported DeepLabCutPlugin name
__all__ = ["DeepLabCutHandlerPlugin"]

logger = logging.getLogger(__name__)

class DeepLabCutHandlerPlugin(BasePlugin):
    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="DeepLabCutHandler",
            date_created=datetime(2024, 7, 26),
            version="1.0",
            description="Handles reading and interpreting DeepLabCut specific file formats (config.yaml, tracking CSV/HDF5). Provides standardized data for analysis plugins.",
            author="Your Name",
            supported_experiment_types=[], # Doesn't analyze specific types, just reads data
            readable_data_formats=['dlc_config', 'dlc_csv', 'dlc_hdf5'], # Formats it understands
            analysis_capabilities=['load_tracking_data', 'extract_bodyparts'], # Actions it can perform
            plugin_type="handler"
        )

    def analysis_capabilities(self) -> List[str]:
        """Return the list of analysis capabilities provided by this plugin."""
        # Simply return the list defined in the metadata
        return self.plugin_self_metadata().analysis_capabilities or []

    def readable_data_formats(self) -> List[str]:
        """Return the list of data formats this plugin can read/process."""
        # Simply return the list defined in the metadata
        return self.plugin_self_metadata().readable_data_formats or []

    def required_fields(self) -> List[str]:
        """Fields that are generally required: tracking_file_path is needed once the experiment reaches 'tracked' stage."""
        return ['tracking_file_path']

    def optional_fields(self) -> List[str]:
        return ['config_file_path', 'likelihood_threshold_override']

    def get_field_types(self) -> Dict[str, str]:
        return {
            'tracking_file_path': 'file:csv|h5|hdf5',
'config_file_path': 'file:yaml|yml',
'likelihood_threshold_override': 'float'
        }

    def get_field_descriptions(self) -> Dict[str, str]:
        return {
            'tracking_file_path': 'Path to the DLC tracking CSV or HDF5 file.',
            'config_file_path': 'Optional path to the DLC config.yaml file (for body part extraction).',
            'likelihood_threshold_override': 'Optionally override the project/experiment likelihood threshold for this load.'
        }

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: Any) -> None:
        """ Basic validation for parameters passed to this plugin. """
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})

        # Check file existence more strictly if load_tracking_data is the intended goal implicitly
        # For now, analyze_experiment handles the strict check.
        tracking_path_str = plugin_params.get('tracking_file_path')

        # Enforce presence when experiment is at or beyond 'tracked' stage
        stage_requires_file = experiment.processing_stage in ("tracked", "interpreted")
        if stage_requires_file and not tracking_path_str:
            raise ValueError("'tracking_file_path' parameter is required once the experiment reaches the 'tracked' stage. Please attach the DLC tracking file before running analysis.")

        if tracking_path_str:
             tracking_path = Path(tracking_path_str)
             if not tracking_path.exists():
                  logger.warning(f"validate_experiment: Tracking file path '{tracking_path}' does not exist (will fail in analyze_experiment if needed).")
        # Add checks for config_file_path if extract_bodyparts is implicitly the goal

    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: DataManager, capability: str) -> Dict[str, Any]:
        """ Executes the requested DLC handling capability. """
        plugin_name = self.plugin_self_metadata().name
        plugin_params = experiment.plugin_params.get(plugin_name, {})
        results = {"status": "success", "capability_executed": capability}

        try:
            if capability == 'extract_bodyparts':
                config_path_str = plugin_params.get('config_file_path')
                csv_path_str = plugin_params.get('tracking_file_path') # Can extract from CSV too

                if config_path_str:
                    config_path = Path(config_path_str)
                    bodyparts = self._extract_bodyparts_from_config(config_path, data_manager)
                    results['bodyparts'] = bodyparts
                    results['source'] = 'config.yaml'
                elif csv_path_str:
                    csv_path = Path(csv_path_str)
                    bodyparts = self._extract_bodyparts_from_csv(csv_path, data_manager)
                    results['bodyparts'] = list(bodyparts) # Convert set to list for consistency
                    results['source'] = 'tracking.csv'
                else:
                    raise ValueError("Requires 'config_file_path' or 'tracking_file_path' parameter for body part extraction.")

            elif capability == 'load_tracking_data':
                tracking_path_str = plugin_params.get('tracking_file_path')
                if not tracking_path_str:
                    raise ValueError("Requires 'tracking_file_path' parameter.")
                tracking_path = Path(tracking_path_str)
                if not tracking_path.exists():
                    raise FileNotFoundError(f"Tracking file specified by '{plugin_name}' not found: {tracking_path}")

                # Validate file type implicitly via the helper call below if needed,
                # or add explicit check here.
                # The main purpose now is just to confirm the source is valid.
                # We won't load the full data here.
                # Optionally, get basic info without full load (e.g., check header)
                file_suffix = tracking_path.suffix.lower()
                if file_suffix not in ['.csv', '.h5', '.hdf5']:
                    raise ValueError(f"Unsupported file type for DLC tracking data: {file_suffix}")

                results['message'] = f"Tracking data source ({tracking_path.name}) validated successfully."
                results['validated_path'] = str(tracking_path)
                # Do NOT include results['tracking_dataframe'] here anymore

            else:
                raise ValueError(f"Unknown capability requested: {capability}")

            return results

        except Exception as e:
            logger.error(f"Error during DLC capability '{capability}': {e}", exc_info=True) # Add traceback
            return {"error": str(e), "status": "failed", "capability_executed": capability}

    # --- NEW Public Helper Method ---
    def get_tracking_dataframe(self, file_path: Path, data_manager: DataManager, likelihood_threshold: Optional[float]) -> pd.DataFrame:
        """
        Loads DLC tracking data (CSV or HDF5) using DataManager and applies likelihood filtering.
        This is the primary method analysis plugins should call via DataManager.
        """
        logger.info(f"Handler '{self.plugin_self_metadata().name}' loading tracking data from: {file_path}")
        file_suffix = file_path.suffix.lower()
        df = None

        if not file_path.exists():
            raise FileNotFoundError(f"Tracking data file not found by handler: {file_path}")

        if file_suffix == '.csv':
            # Use DataManager's generic reader
            df = data_manager.read_csv(file_path, header_rows=[0, 1, 2], index_col=0)
        elif file_suffix in ['.h5', '.hdf5']:
            # Assuming standard DLC HDF5 structure with key 'df_with_missing'
            # Use direct pandas read or a future DataManager HDF5 helper
            try:
                df = data_manager.read_hdf(file_path, key='df_with_missing')
                # HDF5 might already have multi-index columns, verify structure
                if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
                     logger.warning(f"HDF5 file {file_path} does not have expected 3-level MultiIndex columns. Attempting to continue.")
            except Exception as e:
                logger.error(f"Error reading HDF5 file {file_path}: {e}")
                raise IOError(f"Could not read HDF5 file {file_path}: {e}")
        else:
            raise ValueError(f"Unsupported file type for DLC tracking data: {file_suffix}")

        if df is None or df.empty:
             raise ValueError(f"Failed to load DataFrame or loaded DataFrame is empty from: {file_path}")

        # Apply likelihood filtering if a threshold is provided
        if likelihood_threshold is not None and likelihood_threshold > 0:
            logger.info(f"Applying likelihood threshold: {likelihood_threshold}")
            df = self._apply_likelihood_filter(df, likelihood_threshold) # Use helper
        else:
             logger.info("No likelihood threshold applied.")


        logger.info(f"Handler successfully loaded and processed DLC tracking data from: {file_path}")
        return df

    # --- Internal Helpers ---
    def _apply_likelihood_filter(self, df: pd.DataFrame, threshold: float) -> pd.DataFrame:
        """Applies likelihood filtering in place (or returns modified copy)."""
        if isinstance(df.columns, pd.MultiIndex) and df.columns.nlevels == 3:
            likelihood_cols = df.columns[df.columns.get_level_values(2) == 'likelihood']
            if not likelihood_cols.empty:
                # Find rows where *any* likelihood is below threshold
                # Ensure likelihoods are numeric before comparison
                likelihood_df = df[likelihood_cols].apply(pd.to_numeric, errors='coerce')
                mask = (likelihood_df < threshold).any(axis=1)

                # Set corresponding x, y values to NaN
                # Important: Operate on a copy if you want to avoid modifying the original df passed in
                df_filtered = df.copy()
                coord_level = df_filtered.columns.get_level_values(2)
                coord_cols_mask = coord_level.isin(['x', 'y'])
                # Use .loc for safe setting with boolean mask and column mask
                df_filtered.loc[mask, coord_cols_mask] = np.nan
                logger.info(f"Applied thresholding, {mask.sum()} rows affected.")
                return df_filtered
            else:
                logger.warning("Could not find 'likelihood' columns in the expected structure for thresholding.")
        else:
             logger.warning("Cannot apply likelihood threshold: DataFrame columns are not a 3-level MultiIndex.")
        return df # Return original if filtering couldn't be applied

    def _extract_bodyparts_from_config(self, config_path: Path, data_manager: DataManager) -> List[str]:
        """Extracts body parts from a DLC config YAML file using DataManager.

        This method now supports both single-animal and multi-animal DLC project
        configurations.  In multi-animal projects the canonical key "bodyparts"
        is often the *string* "MULTI!" and the actual body-part names are stored
        in the lists ``uniquebodyparts`` and ``multianimalbodyparts``.
        """
        try:
            config_data = data_manager.read_yaml(config_path)

            # --- 1. Attempt the simple/single-animal case first ---
            bodyparts: Any = config_data.get("bodyparts")
            if isinstance(bodyparts, list):
                candidate_parts = bodyparts
            else:
                # --- 2. Multi-animal or legacy structures ---
                candidate_parts: List[str] = []

                # 2a. Multi-animal projects – combine unique & multi-animal parts
                if config_data.get("multianimalproject", False):
                    for key in ("uniquebodyparts", "multianimalbodyparts", "sharedbodyparts"):
                        val = config_data.get(key)
                        if isinstance(val, list):
                            candidate_parts.extend(val)

                # 2b. Older DLC versions – fall back to all_joints_names
                if not candidate_parts and "all_joints" in config_data and "all_joints_names" in config_data:
                    val = config_data.get("all_joints_names")
                    if isinstance(val, list):
                        candidate_parts.extend(val)

                # Update the primary variable for consistency below
                bodyparts = candidate_parts

            # Validate result – must be a non-empty list at this point
            if not isinstance(bodyparts, list) or not bodyparts:
                raise ValueError("Could not locate a list of body-parts in the config file.")

            # Return unique body-parts while preserving first occurrence order
            unique_bodyparts = list(dict.fromkeys(bodyparts))
            logger.info(f"Extracted bodyparts from {config_path}: {unique_bodyparts}")
            return unique_bodyparts

        except (ValueError, IOError, KeyError) as e:
            logger.error(f"Failed to extract bodyparts from config {config_path}: {e}")
            raise ValueError(f"Failed to extract bodyparts from {config_path}: {e}")


    def _extract_bodyparts_from_csv(self, csv_path: Path, data_manager: DataManager) -> Set[str]:
        """Extracts body parts from a DLC CSV header using DataManager."""
        def _try_read(header_rows):
            return data_manager.read_csv(csv_path, header_rows=header_rows, nrows=1)
        try:
            # First attempt with 4 header rows (multi-animal). Fallback to 3 if it fails.
            try:
                df_header = _try_read([0, 1, 2, 3])
            except Exception as first_err:
                logger.debug(f"Reading with 4 header rows failed ({first_err}); trying 3-row header.")
                df_header = _try_read([0, 1, 2])

            nlevels = df_header.columns.nlevels
            if nlevels == 4:
                bodyparts = set(df_header.columns.get_level_values(2))  # (scorer, individual, bodypart, coord)
            elif nlevels == 3:
                bodyparts = set(df_header.columns.get_level_values(1))  # (scorer, bodypart, coord)
            else:
                logger.warning(f"Unexpected number of column levels ({nlevels}) in {csv_path}; attempting generic extraction.")
                bodyparts = set(df_header.columns.get_level_values(max(0, nlevels - 2)))

            bodyparts.discard('scorer')
            logger.info(f"Extracted bodyparts from {csv_path} header: {bodyparts}")
            return bodyparts
        except (ValueError, IOError, IndexError) as e:
            logger.error(f"Failed to extract bodyparts from CSV header {csv_path}: {e}")
            raise ValueError(f"Failed to extract bodyparts from CSV header {csv_path}: {e}")

    def get_bodyparts(self, *, config_path: Path | None = None, tracking_path: Path | None = None, data_manager: DataManager | None = None) -> List[str]:
        """Public helper that returns unique body-part names from a DLC config.yaml or a tracking CSV/HDF5 header.

        This is the method other plugins (importers, analyzers) should call via
        DataManager.call_handler_method("DeepLabCutHandler", "get_bodyparts", ...)
        """
        if data_manager is None:
            raise ValueError("data_manager must be provided (passed automatically by DataManager.call_handler_method).")

        if config_path:
            return self._extract_bodyparts_from_config(Path(config_path), data_manager)
        if tracking_path:
            return list(self._extract_bodyparts_from_csv(Path(tracking_path), data_manager))

        raise ValueError("Either config_path or tracking_path must be provided to get bodyparts.")

    # --- BasePlugin Methods ---
    # (get_style_manifest can return None or empty dict)
    def get_style_manifest(self) -> Optional[Dict[str, Any]]:
        return None 