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
        if not file_path.exists():
            raise FileNotFoundError(f"Tracking file not found: {file_path}")
        if file_path.suffix.lower() != ".csv":
            raise ValueError(f"Expected CSV, got: {file_path.suffix}")

        df = pd.read_csv(file_path, header=[0, 1, 2], index_col=0)

        # ------------------------------------------------
        # Determine final frame rate from multiple sources
        # ------------------------------------------------
        final_frame_rate = None

        # 1) If caller explicitly passed a frame_rate, use it
        if frame_rate is not None:
            final_frame_rate = frame_rate
        else:
            ps = self.state_manager.project_state
            current_experiment = None
            current_batch = None

            # 2) Identify the experiment/batch from state_manager (if IDs are given)
            if experiment_id:
                current_experiment = ps.experiments.get(experiment_id)
            if batch_id:
                current_batch = ps.batches.get(batch_id)

            # 3) If experiment has an override, use it
            if current_experiment and current_experiment.frame_rate is not None:
                final_frame_rate = current_experiment.frame_rate
            # 4) otherwise if batch has an override, use it
            elif current_batch and getattr(current_batch, "frame_rate", None) is not None:
                final_frame_rate = current_batch.frame_rate
            # 5) otherwise use the project's global frame_rate
            else:
                # fallback to project metadata if global frame rate is enabled
                if ps.project_metadata and ps.settings.get("global_frame_rate_enabled", True):
                    final_frame_rate = ps.project_metadata.global_frame_rate
                else:
                    final_frame_rate = 60  # fallback if disabled or missing

        # ------------------------------------------------
        # For demonstration, just log the final_frame_rate
        # ------------------------------------------------
        logger.info(f"Chosen frame_rate for {file_path} is: {final_frame_rate}")

        # --------------------------------
        # Next, handle the threshold logic
        # --------------------------------
        final_threshold = None
        if self._likelihood_threshold is not None:
            final_threshold = self._likelihood_threshold
        else:
            current_experiment = None
            current_batch = None
            # If you have logic to identify experiment/batch from the file_path,
            # or if you use the same experiment_id/batch_id:
            if experiment_id:
                current_experiment = ps.experiments.get(experiment_id)
            if batch_id:
                current_batch = ps.batches.get(batch_id)

            if current_experiment and current_experiment.likelihood_threshold is not None:
                final_threshold = current_experiment.likelihood_threshold
            elif current_batch and current_batch.likelihood_threshold is not None:
                final_threshold = current_batch.likelihood_threshold
            else:
                if ps.likelihood_filter_enabled:
                    final_threshold = ps.default_likelihood_threshold

        if final_threshold is not None:
            df = df[df.iloc[:, 2, 2] >= final_threshold]

        logger.info(f"Successfully processed DLC CSV: {file_path}")
        return df 

    def extract_bodyparts_from_dlc_config(self, config_file: Path) -> list:
        """Extracts body parts from a DLC config YAML file and returns a list of unique body parts."""
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
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
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
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
                if not file_path.exists():
                    raise ValueError(f"File not found: {file_path}")
                if file_path.suffix.lower() != '.csv':
                    raise ValueError(f"Expected a CSV file, got: {file_path.suffix}")
                # If no exception, mark as valid
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
        if not image_path.exists():
            raise ValueError(f"Arena image not found: {image_path}")

        # For demonstration, assume we derive the arena source from the image filename or metadata.
        arena_source = "DLC_Export" if "DLC" in image_path.stem else "Manual"

        if arena_source not in allowed_sources:
            supported = ", ".join(allowed_sources)
            raise ValueError(f"Arena image source '{arena_source}' not supported. Must be one of: {supported}")

        return {"valid": True, "source": arena_source, "path": str(image_path)}

    def import_mouse_metadata_from_excel(self, excel_path: Path):
        """Import mouse metadata from an Excel file and update the project state with MouseMetadata entries."""
        from .metadata import MouseMetadata
        df = pd.read_excel(excel_path)
        for _, row in df.iterrows():
            mouse_id = row["Mouse ID"]
            sex = row.get("Sex", "UNKNOWN")
            genotype = row.get("Genotype", "")
            treatment = row.get("Treatment", "")
            birth_date = pd.to_datetime(row.get("Birth Date"), errors='coerce')
            notes = row.get("Notes", "")
            self.state_manager.project_state.subjects[mouse_id] = MouseMetadata(
                id=mouse_id,
                sex=sex,
                genotype=genotype,
                treatment=treatment,
                notes=notes,
                birth_date=birth_date,
                in_training_set=False
            )
        self.state_manager.notify_observers()

    