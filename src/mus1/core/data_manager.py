import logging
from pathlib import Path
import pandas as pd
from typing import Optional, Union, Dict, Any, List, TYPE_CHECKING
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

# Import for type checking only to avoid runtime dependency cycles
if TYPE_CHECKING:
    from .plugin_manager import PluginManager

# Import scanner modules
try:
     from .scanners.video_discovery import get_scanner
except ImportError:
     get_scanner = Any # Fallback for type checker

# Custom Exception for Frame Rate Resolution
class FrameRateResolutionError(Exception):
    """Custom exception raised when frame rate resolution fails."""
    pass

logger = logging.getLogger("mus1.core.data_manager")

class DataManager:
    def __init__(self, state_manager: Any, plugin_manager: 'PluginManager'):
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

    def read_hdf(self, file_path: Path, key: str = 'df_with_missing', **kwargs) -> pd.DataFrame:
        """
        Reads an HDF5 file (HDFStore) and returns a DataFrame.

        Args:
            file_path: Path to the HDF5 file (.h5/.hdf5)
            key: Dataset key to read (default 'df_with_missing' for DLC)
            **kwargs: Passed to pandas.read_hdf

        Raises:
            IOError/ValueError on read or structure errors
        """
        self._validate_file(file_path, [".h5", ".hdf5"], "HDF5 file")
        try:
            df = pd.read_hdf(file_path, key=key, **kwargs)
        except Exception as e:
            logger.error(f"Error reading HDF5 file {file_path}: {e}")
            raise IOError(f"Could not read HDF5 file {file_path}: {e}")

        # DLC commonly expects a 3-level MultiIndex (scorer, bodypart, coord)
        if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels < 3:
            logger.warning(
                f"HDF5 {file_path} columns are not a 3-level MultiIndex; got nlevels={getattr(df.columns, 'nlevels', 'N/A')}."
            )
        return df

    def get_experiment_data_path(self, experiment: Any) -> str:
        """
        Return a canonical path for storing experiment outputs under the current project.

        Layout: <project_root>/data/<subject_id>/<experiment_id>/
        """
        project_root = getattr(self.state_manager, '_current_project_root', None)
        if project_root is None and hasattr(self.state_manager, 'get_project_root'):
            project_root = self.state_manager.get_project_root()
        if project_root is None:
            # Fallback: try ProjectManager convention from ProjectManager instance if available
            project_root = getattr(getattr(self, 'project_manager', None), '_current_project_root', None)
        if project_root is None:
            raise RuntimeError("No current project loaded; cannot compute experiment data path.")
        base = Path(project_root) / 'data' / str(experiment.subject_id) / str(experiment.id)
        base.mkdir(parents=True, exist_ok=True)
        return str(base)

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

        # Fallback to project default if filtering is enabled (stored on ProjectState)
        if getattr(ps, "likelihood_filter_enabled", False):
             threshold = getattr(ps, "default_likelihood_threshold", None)
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
        # Delegate to shared utility to avoid duplication
        from .utils.file_hash import compute_sample_hash as _compute
        return _compute(file_path, chunk_size)

    # ------------------------------------------------------------------
    # Video discovery & deduplication helpers
    # ------------------------------------------------------------------
    def _extract_start_time(self, video_path: Path) -> datetime:
        """Return container-recorded time (DateUTC/creation_time) or fallback to mtime.

        Tries multiple common tag keys exposed by ffprobe for MP4/MKV:
        - creation_time (QuickTime/MP4)
        - date, DATE, date_utc, DATE_UTC (Matroska/others)
        """
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
            data = json.loads(result.stdout) if result.stdout else {}
            tags = (data.get("format", {}) or {}).get("tags", {}) or {}
            # Try a few common keys
            for key in ("creation_time", "DATE_UTC", "date_utc", "DATE", "date"):
                val = tags.get(key)
                if not val:
                    continue
                # Normalize: strip trailing Z and attempt parse
                try:
                    val_norm = val.strip()
                    val_norm = val_norm.rstrip("Z")
                    return datetime.fromisoformat(val_norm)
                except Exception:
                    # Some mkv tools emit 'UTC 2023-01-01 12:00:00'
                    if val_norm.upper().startswith("UTC "):
                        try:
                            return datetime.fromisoformat(val_norm[4:])
                        except Exception:
                            pass
            # As a minor fallback, try start_time-realtime but avoid expensive ops
        except Exception:
            pass
        return datetime.fromtimestamp(video_path.stat().st_mtime)

    def compute_full_hash(self, file_path: Path, chunk_size: int = 8 * 1024 * 1024, algorithm: str = "blake2b", digest_size: int = 32) -> str:
        from .utils.file_hash import compute_full_hash as _compute_full
        return _compute_full(file_path, chunk_size=chunk_size, algorithm=algorithm, digest_size=digest_size)

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

    def deduplicate_video_list(
        self,
        paths_with_hashes: Iterable[Tuple[Path, str]],
        *,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Iterator[Tuple[Path, str, datetime]]:
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

    def discover_video_files(
        self,
        roots: Iterable[str | Path],
        *,
        extensions: Iterable[str] | None = None,
        recursive: bool = True,
        excludes: Iterable[str] | None = None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Iterator[Tuple[Path, str]]:
        scanner = get_scanner()
        return scanner.iter_videos(roots, extensions=extensions, recursive=recursive, excludes=excludes, progress_cb=progress_cb)

    def stage_files_to_shared(
        self,
        src_with_hashes: Iterable[Tuple[Path, str]],
        *,
        shared_root: Path,
        dest_base: Path,
        overwrite: bool = False,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Iterator[Tuple[Path, str, datetime]]:
        """Copy files into shared storage and yield tuples suitable for registration.

        For each (source_path, hash):
          - If already under shared_root, keep as-is
          - Else copy to dest_base/<filename>
          - Verify hash after copy
          - Yield (dest_path, hash, start_time)
        """
        from .utils.file_hash import compute_sample_hash as _compute
        import shutil

        items = list(src_with_hashes)
        total = len(items)
        done = 0
        sr_resolved = shared_root.expanduser().resolve()
        dest_base = dest_base.expanduser().resolve()
        dest_base.mkdir(parents=True, exist_ok=True)

        for src, hsh in items:
            try:
                src_res = Path(src).expanduser().resolve()
            except Exception:
                done += 1
                if progress_cb:
                    progress_cb(done, total)
                continue

            # Determine destination
            try:
                if str(src_res).startswith(str(sr_resolved)):
                    dest = src_res
                else:
                    dest = dest_base / src_res.name
            except Exception:
                done += 1
                if progress_cb:
                    progress_cb(done, total)
                continue

            # If destination exists and overwrite is False, verify hash and reuse
            if dest.exists() and not overwrite:
                try:
                    if _compute(dest) == hsh:
                        yield (dest, hsh, self._extract_start_time(dest))
                        done += 1
                        if progress_cb:
                            progress_cb(done, total)
                        continue
                except Exception:
                    pass

            # Perform copy if needed
            if not dest.exists() or overwrite:
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_res, dest)
                except Exception:
                    done += 1
                    if progress_cb:
                        progress_cb(done, total)
                    continue

            # Verify hash post-copy
            try:
                if _compute(dest) != hsh:
                    # Hash mismatch: skip and remove partial if created
                    try:
                        if dest.exists() and not str(src_res).startswith(str(sr_resolved)):
                            dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    done += 1
                    if progress_cb:
                        progress_cb(done, total)
                    continue
            except Exception:
                done += 1
                if progress_cb:
                    progress_cb(done, total)
                continue

            # Success: yield for registration
            try:
                st = self._extract_start_time(dest)
            except Exception:
                st = datetime.fromtimestamp(max(dest.stat().st_mtime, dest.stat().st_ctime))
            yield (dest, hsh, st)
            done += 1
            if progress_cb:
                progress_cb(done, total)

    # ------------------------------------------------------------------
    # JSONL helpers (for CLI/GUI pipelines)
    # ------------------------------------------------------------------
    def emit_jsonl(self, out_path: Path, items: Iterable[Tuple[Path, str, datetime]]) -> None:
        """Write (path, hash, start_time) tuples to JSONL at out_path.

        Each line: {"path": str(path), "hash": hash, "start_time": ISO-8601}
        """
        out_path = out_path.expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        with open(out_path, "w", encoding="utf-8") as f:
            for p, h, ts in items:
                rec = {
                    "path": str(p),
                    "hash": h,
                    "start_time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                }
                f.write(json.dumps(rec) + "\n")

    