import logging
from pathlib import Path
import pandas as pd
from typing import Optional
import yaml

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