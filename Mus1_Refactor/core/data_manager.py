import logging
from pathlib import Path
import pandas as pd
from typing import Optional
import yaml
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO

logger = logging.getLogger("mus1.core.data_manager")

class DataManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self._likelihood_threshold = None 

    # -------------------------------------------------------------------------
    # New Helper Methods for Validation and Resolution
    # -------------------------------------------------------------------------
    
    def _validate_file(self, file_path: Path, expected_extensions: list[str], file_type: str) -> None:
        """
        Validate that the file exists and has one of the expected extensions.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"{file_type} not found: {file_path}")
        if file_path.suffix.lower() not in [ext.lower() for ext in expected_extensions]:
            raise ValueError(f"Expected a {file_type} with extension {expected_extensions}, got: {file_path.suffix}")

    def _resolve_frame_rate(self, frame_rate: Optional[int], experiment_id: Optional[str], batch_id: Optional[str]) -> int:
        """
        Determine the final frame rate using an explicit parameter or by checking experiment,
        batch, or project defaults.
        """
        ps = self.state_manager.project_state
        if frame_rate is not None:
            return frame_rate
        current_experiment = ps.experiments.get(experiment_id) if experiment_id else None
        current_batch = ps.batches.get(batch_id) if batch_id else None
        if current_experiment and current_experiment.frame_rate is not None:
            return current_experiment.frame_rate
        elif current_batch and getattr(current_batch, "frame_rate", None) is not None:
            return current_batch.frame_rate
        else:
            if ps.project_metadata and ps.settings.get("global_frame_rate_enabled", True):
                return ps.project_metadata.global_frame_rate
            else:
                return 60

    def _resolve_threshold(self, experiment_id: Optional[str], batch_id: Optional[str]) -> Optional[float]:
        """
        Determine the likelihood threshold based on an explicit internal threshold
        or by checking experiment, batch or project defaults.
        """
        ps = self.state_manager.project_state
        if self._likelihood_threshold is not None:
            return self._likelihood_threshold
        current_experiment = ps.experiments.get(experiment_id) if experiment_id else None
        current_batch = ps.batches.get(batch_id) if batch_id else None
        if current_experiment and current_experiment.likelihood_threshold is not None:
            return current_experiment.likelihood_threshold
        elif current_batch and current_batch.likelihood_threshold is not None:
            return current_batch.likelihood_threshold
        else:
            if ps.likelihood_filter_enabled:
                return ps.default_likelihood_threshold
            else:
                return None

    # -------------------------------------------------------------------------
    # Modified Methods Using the New Helpers
    # -------------------------------------------------------------------------

    def load_dlc_tracking_csv(
        self, 
        file_path: Path, 
        frame_rate: Optional[int] = None,
        experiment_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ):
        """
        Load and process a DLC CSV tracking file.
        Now we also look up the final frame rate from experiment/batch if not provided.
        """
        # Validate file using the new helper
        self._validate_file(file_path, [".csv"], "Tracking file")
        
        df = pd.read_csv(file_path, header=[0, 1, 2], index_col=0)

        # Resolve frame rate using the helper method
        final_frame_rate = self._resolve_frame_rate(frame_rate, experiment_id, batch_id)
        logger.info(f"Chosen frame_rate for {file_path} is: {final_frame_rate}")

        # Resolve likelihood threshold using the helper method
        final_threshold = self._resolve_threshold(experiment_id, batch_id)
        if final_threshold is not None:
            df = df[df.iloc[:, 2, 2] >= final_threshold]

        logger.info(f"Successfully processed DLC CSV: {file_path}")
        return df 

    def extract_bodyparts_from_dlc_config(self, config_file: Path) -> list:
        """Extracts body parts from a DLC config YAML file and returns a list of unique body parts."""
        # Validate config file using the helper (supporting YAML extensions)
        self._validate_file(config_file, [".yaml", ".yml"], "Config file")
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        bodyparts = config_data.get("bodyparts", [])
        if not isinstance(bodyparts, list):
            raise ValueError("Invalid format for bodyparts in config file")
        # Return unique bodyparts while preserving order
        unique_bodyparts = list(dict.fromkeys(bodyparts))
        return unique_bodyparts 

    def extract_bodyparts_from_dlc_csv(self, csv_file: Path) -> set:
        """Extracts body parts from a DLC CSV file by reading the header (level 1) and returning a set of unique body parts."""
        self._validate_file(csv_file, [".csv"], "CSV file")
        try:
            df = pd.read_csv(csv_file, header=[0,1,2], index_col=0)
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
        return set(df.columns.get_level_values(1)) 

    def validate_file_for_plugins(self, file_path: Path, plugins: list) -> dict:
        """Validate a file against the requirements of the given plugins.

        Args:
            file_path: Path to the file to validate.
            plugins: A list of plugin instances to validate against.

        Returns:
            A dict mapping plugin names to validation results.
        """
        results = {}
        for plugin in plugins:
            plugin_name = plugin.plugin_self_metadata().name
            try:
                # For demonstration, assume each plugin's validation is encapsulated in its validate_experiment method.
                # Here we simply check if the file exists and is a CSV (example logic).
                self._validate_file(file_path, ['.csv'], "Plugin file")
                results[plugin_name] = {"valid": True}
            except Exception as e:
                results[plugin_name] = {"valid": False, "error": str(e)}
        return results 

    def validate_arena_image(self, image_path: Path, allowed_sources: list, project_state) -> dict:
        """Validate an arena image against allowed sources and project state.

        Args:
            image_path: Path to the arena image.
            allowed_sources: List of allowed arena sources (strings).
            project_state: Current project state (used to determine the image source).

        Returns:
            A dict with validation results.

        Raises:
            ValueError: If validation fails.
        """
        self._validate_file(image_path, [".png", ".jpg", ".jpeg", ".tif", ".tiff"], "Arena image")
        # For demonstration, assume we derive the arena source from the image filename or metadata.
        arena_source = "DLC_Export" if "DLC" in image_path.stem else "Manual"

        if arena_source not in allowed_sources:
            supported = ", ".join(allowed_sources)
            raise ValueError(f"Arena image source '{arena_source}' not supported. Must be one of: {supported}")

        return {"valid": True, "source": arena_source, "path": str(image_path)}

    def import_subject_metadata_from_excel(self, excel_path: Path):
        """Import subject metadata from an Excel file and update the project state with SubjectMetadata entries."""
        from .metadata import SubjectMetadata

        df = pd.read_excel(excel_path)
        for _, row in df.iterrows():
            subject_id = row["Subject ID"]
            # Create a SubjectMetadata object from the row data and add it to the state
            self.state_manager.project_state.subjects[subject_id] = SubjectMetadata(
                id=subject_id,
                sex=row.get("Sex", "Unknown"),
                birth_date=row.get("Birth Date"),
                genotype=row.get("Genotype"),
                in_training_set=row.get("Training Set", False)
            )
        self.state_manager.notify_observers()

    