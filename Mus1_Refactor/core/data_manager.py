import logging
from pathlib import Path
import pandas as pd
from typing import Optional, Union, Dict, Any, List
import yaml
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO
import hashlib  # For fast file hashing
import subprocess
import json
from datetime import datetime
from typing import Callable, Iterable, Iterator, Tuple

# Import PluginManager type hint
try:
     from .plugin_manager import PluginManager
except ImportError:
     PluginManager = Any # Fallback for type checker

# Custom Exception for Frame Rate Resolution
class FrameRateResolutionError(Exception):
    """Custom exception raised when frame rate resolution fails."""
    pass

logger = logging.getLogger("mus1.core.data_manager")

class DataManager:
    def __init__(self, state_manager: Any, plugin_manager: PluginManager):
        self.state_manager = state_manager
        self.plugin_manager = plugin_manager # Store plugin manager instance
        # Keep threshold resolution logic here for now, plugins can call it
        # self._likelihood_threshold = None # This might be better managed per-call

    # --- Generic File Validation ---
    def _validate_file(self, file_path: Path, expected_extensions: list[str], file_type: str) -> None:
        """
        Validate that the file exists and has one of the expected extensions.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"{file_type} not found: {file_path}")
        if file_path.suffix.lower() not in [ext.lower() for ext in expected_extensions]:
            raise ValueError(f"Expected a {file_type} with extension {expected_extensions}, got: {file_path.suffix}")

    # --- Generic File Readers ---
    def read_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Reads a YAML file and returns its content as a dictionary."""
        self._validate_file(file_path, [".yaml", ".yml"], "YAML file")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("YAML content is not a dictionary.")
            logger.debug(f"Successfully read YAML file: {file_path}")
            return data
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {file_path}: {e}")
            raise ValueError(f"Invalid YAML format in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error reading YAML file {file_path}: {e}")
            raise IOError(f"Could not read YAML file {file_path}: {e}")

    def read_csv(self, file_path: Path, header_rows: Optional[List[int]] = None, index_col: Optional[int] = 0, **kwargs) -> pd.DataFrame:
        """
        Reads a CSV file into a Pandas DataFrame with flexible header options.

        Args:
            file_path: Path to the CSV file.
            header_rows: List of row numbers to use as the header (e.g., [0, 1, 2] for DLC).
                         If None, uses the first row as the header.
            index_col: Column number to use as the index.
            **kwargs: Additional keyword arguments passed directly to pd.read_csv.

        Returns:
            A Pandas DataFrame.
        """
        self._validate_file(file_path, [".csv"], "CSV file")
        try:
            # Determine header argument for pandas
            header_arg = header_rows if header_rows is not None else 0
            df = pd.read_csv(file_path, header=header_arg, index_col=index_col, **kwargs)
            logger.debug(f"Successfully read CSV file: {file_path} with header={header_arg}")
            return df
        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {e}")
            raise IOError(f"Could not read CSV file {file_path}: {e}")

    # --- NEW Method to Call Handler Helpers ---
    def call_handler_method(self, handler_name: str, method_name: str, **kwargs) -> Any:
         """
         Finds a handler plugin by name and calls a specified method on it.

         Args:
             handler_name: The unique name of the handler plugin (e.g., "DeepLabCutHandler").
             method_name: The name of the public method to call on the handler instance
                          (e.g., "get_tracking_dataframe").
             **kwargs: Keyword arguments to pass directly to the handler's method
                       (e.g., file_path=Path(...), likelihood_threshold=0.9).

         Returns:
             The result returned by the handler's method.

         Raises:
             ValueError: If the handler plugin or the specified method is not found.
             Exception: If an error occurs during the handler method execution.
         """
         logger.debug(f"Attempting to call method '{method_name}' on handler '{handler_name}' with args: {kwargs}")
         handler_instance = self.plugin_manager.get_plugin_by_name(handler_name)

         if not handler_instance:
             msg = f"Handler plugin '{handler_name}' not found by DataManager."
             logger.error(msg)
             raise ValueError(msg)

         if not hasattr(handler_instance, method_name):
             msg = f"Method '{method_name}' not found on handler plugin '{handler_name}'."
             logger.error(msg)
             raise ValueError(msg)

         method_to_call = getattr(handler_instance, method_name)
         if not callable(method_to_call):
              msg = f"Attribute '{method_name}' on handler plugin '{handler_name}' is not callable."
              logger.error(msg)
              raise ValueError(msg)

         try:
             # Pass self (DataManager instance) to the handler method if needed?
             # Check the signature of the target method. For get_tracking_dataframe,
             # we decided it needs file_path, data_manager, likelihood_threshold.
             # Let's ensure 'data_manager=self' is passed if the handler expects it.
             import inspect
             sig = inspect.signature(method_to_call)
             if 'data_manager' in sig.parameters:
                  kwargs['data_manager'] = self

             result = method_to_call(**kwargs)
             logger.debug(f"Successfully called method '{method_name}' on handler '{handler_name}'.")
             return result
         except Exception as e:
             logger.error(f"Error executing method '{method_name}' on handler '{handler_name}': {e}", exc_info=True)
             # Re-raise the exception so the calling plugin can handle it
             raise e # Or wrap it in a custom DataManager exception

    # --- Settings Resolution Helpers (Plugins can use these) ---
    def resolve_likelihood_threshold(self, experiment_id: Optional[str] = None, batch_id: Optional[str] = None) -> Optional[float]:
        """
        Determine the likelihood threshold based on experiment, batch or project defaults.
        (Made public for plugin use)
        """
        ps = self.state_manager.project_state
        # Check experiment first
        current_experiment = ps.experiments.get(experiment_id) if experiment_id else None
        if current_experiment and hasattr(current_experiment, 'likelihood_threshold') and current_experiment.likelihood_threshold is not None:
             logger.debug(f"Using likelihood threshold from experiment {experiment_id}: {current_experiment.likelihood_threshold}")
             return current_experiment.likelihood_threshold

        # Check batch next
        current_batch = ps.batches.get(batch_id) if batch_id else None
        if current_batch and hasattr(current_batch, 'likelihood_threshold') and current_batch.likelihood_threshold is not None:
             logger.debug(f"Using likelihood threshold from batch {batch_id}: {current_batch.likelihood_threshold}")
             return current_batch.likelihood_threshold

        # Fallback to project default if filtering is enabled
        if ps.project_metadata and ps.project_metadata.likelihood_filter_enabled:
             threshold = ps.project_metadata.default_likelihood_threshold
             logger.debug(f"Using project default likelihood threshold: {threshold}")
             return threshold
        elif ps.settings.get("likelihood_filter_enabled", False): # Check settings if metadata missing
             threshold = ps.settings.get("default_likelihood_threshold")
             logger.debug(f"Using project settings default likelihood threshold: {threshold}")
             return threshold

        logger.debug("Likelihood filtering disabled or no threshold found.")
        return None # No threshold applicable

    def resolve_frame_rate(self, frame_rate: Optional[int] = None, experiment_id: Optional[str] = None, batch_id: Optional[str] = None) -> Union[int, float, str]:
        """
        Determine the final frame rate. Returns rate as number or 'OFF'.
        (Made public for plugin use) - Changed return type hint slightly
        """
        # 1. Explicit frame_rate
        if frame_rate is not None:
            logger.info(f"Using explicitly provided frame rate: {frame_rate}")
            return frame_rate

        ps = self.state_manager.project_state

        # Retrieve global settings
        is_global_enabled = False
        global_rate = None
        if ps.project_metadata:
            is_global_enabled = ps.project_metadata.global_frame_rate_enabled
            global_rate = ps.project_metadata.global_frame_rate
        else: # Fallback to settings if metadata not loaded/available
            is_global_enabled = ps.settings.get("global_frame_rate_enabled", False)
            global_rate = ps.settings.get("global_frame_rate", None)

        # 2. Global enabled? Must have value.
        if is_global_enabled:
            if global_rate is None:
                raise FrameRateResolutionError("Global frame rate is enabled but no value is set.")
            logger.info(f"Using global frame rate: {global_rate}")
            return global_rate

        # 3. Global disabled, check experiment
        current_experiment = ps.experiments.get(experiment_id) if experiment_id else None
        if current_experiment and hasattr(current_experiment, "frame_rate") and current_experiment.frame_rate is not None:
            logger.info(f"Using experiment-specific frame rate: {current_experiment.frame_rate}")
            return current_experiment.frame_rate

        # 4. Check batch
        current_batch = ps.batches.get(batch_id) if batch_id else None
        if current_batch and hasattr(current_batch, "frame_rate") and current_batch.frame_rate is not None:
            logger.info(f"Using batch-specific frame rate: {current_batch.frame_rate}")
            return current_batch.frame_rate

        # 5. Otherwise, OFF
        logger.info("Frame rate functionality is disabled and no specific frame rate provided; returning 'OFF'")
        return "OFF"

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

    # ------------------------------------------------------------------
    # Fast file hashing utility (used for video integrity checks)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_sample_hash(file_path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
        """Compute a quick BLAKE2b hash from three sampled chunks.

        This mirrors the previous helper in ProjectManager but lives here so that
        hashing logic is reusable across core components without making
        ProjectManager heavier.

        Args:
            file_path: Path to the file to hash.
            chunk_size: Size (bytes) of each chunk to sample from start/middle/end.

        Returns:
            32-character hex digest string.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found for hashing: {file_path}")

        file_size = file_path.stat().st_size
        h = hashlib.blake2b(digest_size=16)

        with open(file_path, "rb") as f:
            # First chunk
            h.update(f.read(min(chunk_size, file_size)))

            # Middle chunk
            if file_size > chunk_size * 2:
                middle_pos = file_size // 2
                f.seek(max(0, middle_pos - chunk_size // 2))
                h.update(f.read(chunk_size))

            # Last chunk
            if file_size > chunk_size:
                f.seek(max(0, file_size - chunk_size))
                h.update(f.read(chunk_size))

        return h.hexdigest()

    # ------------------------------------------------------------------
    # Video discovery & deduplication helpers
    # ------------------------------------------------------------------
    def _extract_start_time(self, video_path: Path) -> datetime:
        """Return creation time from video metadata (ffprobe) or fallback to mtime."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            creation_time_str = data.get("format", {}).get("tags", {}).get("creation_time")
            if creation_time_str:
                return datetime.fromisoformat(creation_time_str.rstrip("Z"))
        except Exception:
            # Silently fall back – logging would be noisy during large scans
            pass
        return datetime.fromtimestamp(video_path.stat().st_mtime)

    def discover_video_files(
        self,
        roots: Iterable[str | Path],
        *,
        extensions: Iterable[str] | None = None,
        recursive: bool = True,
        excludes: Iterable[str] | None = None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Iterator[Tuple[Path, str]]:
        """Yield ``(path, sample_hash)`` for every video found under *roots*.

        This is deliberately lightweight: no hashing duplicates, no start-time
        extraction – those are handled by :py:meth:`deduplicate_video_list`.
        """
        DEFAULT_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}
        ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or DEFAULT_EXTS)}
        exclude_subs = set(excludes or [])

        # Collect first so we know *total* for the progress callback
        all_files: list[Path] = []
        for root in roots:
            root_path = Path(root).expanduser().resolve()
            if not root_path.is_dir():
                continue
            walker = root_path.rglob("*") if recursive else root_path.glob("*")
            for p in walker:
                try:
                    if p.is_dir():
                        continue
                    if any(sub in str(p) for sub in exclude_subs):
                        continue
                    if p.suffix.lower() in ext_set and p.is_file():
                        all_files.append(p)
                except OSError:
                    continue
        total = len(all_files)
        done = 0
        for p in all_files:
            try:
                sample_hash = self.compute_sample_hash(p)
                yield (p, sample_hash)
            finally:
                done += 1
                if progress_cb:
                    progress_cb(done, total)

    def deduplicate_video_list(
        self,
        paths_with_hashes: Iterable[Tuple[Path, str]],
        *,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Iterator[Tuple[Path, str, datetime]]:
        """Remove duplicate hashes and attach ``start_time``.

        Accepts an *iterator* of ``(Path, hash)`` – typically from
        :py:meth:`discover_video_files` – and yields only the first occurrence
        of each unique hash as ``(Path, hash, start_time)``.
        """
        unique: dict[str, Path] = {}
        paths = list(paths_with_hashes)  # Materialise so we can know total
        total = len(paths)
        done = 0
        for path, hsh in paths:
            if hsh in unique:
                # Already seen, skip
                pass
            else:
                unique[hsh] = path
                start_time = self._extract_start_time(path)
                yield (path, hsh, start_time)
            done += 1
            if progress_cb:
                progress_cb(done, total)

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

    def lazy_load_tracking_data(self, tracking_path: Path, experiment_id: Optional[str] = None) -> dict:
        """
        Lazy loading method for tracking data files. Instead of loading the entire data,
        this method loads only essential metadata and sets up a reference to the file.
        
        Args:
            tracking_path: Path to the tracking data file
            experiment_id: The experiment ID this tracking data belongs to
            
        Returns:
            A dictionary with metadata about the tracking data and a reference to the file
            
        Notes:
            This method is designed for the optimized large file approach.
            In a production implementation, this would:
            1. Extract only header information from CSV files
            2. Generate any required summary stats without loading all data
            3. Setup a mechanism to load data chunks when requested
            4. Implement caching for frequently accessed data
            
            The current implementation is a placeholder for the future expansion
            to properly handle very large datasets.
        """
        # Check if file exists
        self._validate_file(tracking_path, [".csv"], "Tracking file")
        
        # For now, just return basic metadata
        return {
            "path": str(tracking_path),
            "experiment_id": experiment_id,
            "file_type": tracking_path.suffix.lower(),
            "size_bytes": tracking_path.stat().st_size,
            "last_modified": tracking_path.stat().st_mtime,
            # In a full implementation, we might include:
            # - column names
            # - number of frames
            # - summary statistics (min/max/mean values)
            # - cached preview data (first/last few rows)
        }

    