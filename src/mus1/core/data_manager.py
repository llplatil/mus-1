import logging
from pathlib import Path
import pandas as pd
from typing import Optional, Union, Dict, Any, List, TYPE_CHECKING
import yaml
import hashlib  # For fast file hashing
import subprocess
import json
import os
from datetime import datetime
from typing import Callable, Iterable, Iterator, Tuple
import re

# Import for type checking only to avoid runtime dependency cycles
if TYPE_CHECKING:
    from .plugin_manager import PluginManager

# Import scanner modules (no legacy fallbacks in dev)
from .scanners.video_discovery import get_scanner

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
        # Cache true recording time by sample hash to avoid repeated ffprobe calls
        self._recording_time_cache: dict[str, datetime] = {}
        # Track current project root for consistent output paths
        self._project_root: Optional[Path] = None

    def set_project_root(self, project_root: Path) -> None:
        """Set the current project root for this DataManager."""
        self._project_root = Path(project_root).expanduser().resolve()

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
        if self._project_root is None:
            raise RuntimeError("No current project loaded; cannot compute experiment data path.")
        base = Path(self._project_root) / 'data' / str(experiment.subject_id) / str(experiment.id)
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
    # File hashing utilities (fast sample + full-file) and change detection
    # ------------------------------------------------------------------
    @staticmethod
    def compute_sample_hash(file_path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
        # Delegate to shared utility to avoid duplication
        from .utils.file_hash import compute_sample_hash as _compute
        return _compute(file_path, chunk_size)

    @staticmethod
    def compute_full_hash(file_path: Path, *, algo: str = "blake2b", digest_size: int = 32, chunk_size: int = 8 * 1024 * 1024) -> str:
        """Compute and return a full-file hash using shared utility."""
        from .utils.file_hash import compute_full_hash as _compute_full
        return _compute_full(file_path, algo=algo, digest_size=digest_size, chunk_size=chunk_size)

    @staticmethod
    def file_identity_signature(file_path: Path) -> tuple[int, float]:
        from .utils.file_hash import file_identity_signature as _sig
        return _sig(file_path)

    # ------------------------------------------------------------------
    # Recording folder naming & sanitizer
    # ------------------------------------------------------------------
    @staticmethod
    def sanitize_component(name: str) -> str:
        s = name.strip()
        s = re.sub(r"[\\/:*?\"<>|]+", "-", s)
        s = re.sub(r"\s+", "_", s)
        return s or "unknown"

    @staticmethod
    def recording_folder_name(subject_id: str, recorded_date: datetime, sample_hash: str, hash_len: int = 8) -> str:
        subj = DataManager.sanitize_component(subject_id)
        date_str = recorded_date.strftime("%Y%m%d")
        h8 = (sample_hash or "").lower()[:hash_len]
        return f"{subj}-{date_str}-{h8}"

    # ------------------------------------------------------------------
    # Video discovery & deduplication helpers
    # ------------------------------------------------------------------
    def _extract_start_time(self, video_path: Path) -> datetime:
        """Return true recording time from container metadata when available; fallback to mtime.

        This probes multiple common tag locations across containers (QuickTime/MP4, Matroska, generic):
          - stream[0].tags.creation_time
          - format.tags.creation_time
          - format.tags.com.apple.quicktime.creationdate
          - format.tags.DATE_RECORDED / DATE_LOCAL / DATE
        """
        def _parse_dt(val: str) -> datetime | None:
            s = str(val).strip()
            try:
                # Normalize trailing Z to RFC 3339
                if s.endswith("Z") and "+" not in s:
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s)
            except Exception:
                pass
            # Try a few common fallback formats
            for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt)
                except Exception:
                    continue
            return None

        try:
            # Minimize output to just relevant tag fields
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    (
                        "format_tags=creation_time,com.apple.quicktime.creationdate,DATE_RECORDED,DATE_LOCAL,DATE:"
                        "stream_tags=creation_time"
                    ),
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout or "{}")
            # Prefer stream tag if present
            try:
                streams = data.get("streams") or []
                if streams:
                    stags = (streams[0] or {}).get("tags") or {}
                    v = stags.get("creation_time")
                    if v:
                        dt = _parse_dt(v)
                        if dt:
                            return dt
            except Exception:
                pass
            # Then check format-level tags
            tags = (data.get("format") or {}).get("tags") or {}
            for key in (
                "creation_time",
                "com.apple.quicktime.creationdate",
                "DATE_RECORDED",
                "DATE_LOCAL",
                "DATE",
            ):
                v = tags.get(key)
                if v:
                    dt = _parse_dt(v)
                    if dt:
                        return dt
        except Exception:
            # Silently fall back – logging would be noisy during large scans
            pass
        return datetime.fromtimestamp(video_path.stat().st_mtime)

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
                # Resolve and cache true recording time per unique hash
                start_time = self._recording_time_cache.get(hsh)
                if start_time is None:
                    start_time = self._extract_start_time(path)
                    try:
                        self._recording_time_cache[hsh] = start_time
                    except Exception:
                        pass
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
        delete_source_on_success: bool = False,
        namer: Callable[[Path], str] | None = None,
        verify_time: bool = False,
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

            # Decide recording time per policy: default to mtime; optionally verify with container tags
            try:
                mtime_dt = datetime.fromtimestamp(src_res.stat().st_mtime)
            except Exception:
                mtime_dt = datetime.fromtimestamp(max(src_res.stat().st_mtime, src_res.stat().st_ctime))
            recorded_time = mtime_dt
            recorded_time_source = "mtime"
            if verify_time:
                try:
                    st_extracted = self._extract_start_time(src_res)
                    # If close to mtime, keep mtime; else prefer container
                    if abs((st_extracted - mtime_dt).total_seconds()) > 60.0:
                        recorded_time = st_extracted
                        recorded_time_source = "container"
                except Exception:
                    pass

            # Determine destination
            try:
                if str(src_res).startswith(str(sr_resolved)):
                    # Already under shared_root. If not already under dest_base, we plan to relocate.
                    try:
                        src_under_dest = str(src_res).startswith(str(dest_base))
                    except Exception:
                        src_under_dest = False
                    if src_under_dest:
                        dest = src_res
                    else:
                        # Create per-recording folder using unknown subject placeholder
                        folder = self.recording_folder_name("unknown", recorded_time, hsh)
                        dest_dir = dest_base / folder
                        base_name = namer(src_res) if namer else src_res.name
                        dest = dest_dir / base_name
                else:
                    folder = self.recording_folder_name("unknown", recorded_time, hsh)
                    dest_dir = dest_base / folder
                    base_name = namer(src_res) if namer else src_res.name
                    dest = dest_dir / base_name
                # If a different file already exists with same name but different hash, disambiguate
                if dest.exists() and not overwrite:
                    try:
                        from .utils.file_hash import compute_sample_hash as _compute
                        if _compute(dest) != hsh:
                            stem = dest.stem
                            suffix = dest.suffix
                            counter = 1
                            while True:
                                candidate = dest_base / f"{stem}_{counter}{suffix}"
                                if not candidate.exists():
                                    dest = candidate
                                    break
                                # If candidate exists and matches hash, reuse it
                                try:
                                    if _compute(candidate) == hsh:
                                        dest = candidate
                                        break
                                except Exception:
                                    pass
                                counter += 1
                    except Exception:
                        pass
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

            # Perform data movement
            if not dest.exists() or overwrite:
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    # Fast-path: if we are moving (delete_source_on_success) and both source and destination are on the same device,
                    # prefer an atomic rename instead of copy to avoid slow, huge file copies.
                    same_device = False
                    try:
                        same_device = (src_res.stat().st_dev == dest_base.stat().st_dev)
                    except Exception:
                        same_device = False
                    if delete_source_on_success and same_device and str(src_res).startswith(str(sr_resolved)):
                        try:
                            # If overwrite requested and dest exists, remove it first
                            if overwrite and dest.exists():
                                dest.unlink(missing_ok=True)
                        except Exception:
                            pass
                        try:
                            os.replace(src_res, dest)
                            # After rename, treat as success and skip copy + post-hash
                            st = recorded_time
                            # Write/update recording metadata.json
                            try:
                                md = self.build_recording_metadata(
                                    video_path=dest,
                                    subject_id="unknown",
                                    experiment_type="",
                                    batch_links=[],
                                    sample_hash=hsh,
                                    full_hash=None,
                                    recorded_time=st,
                                    recorded_time_source=recorded_time_source,
                                )
                                self.write_recording_metadata(dest.parent, md)
                            except Exception:
                                pass
                            yield (dest, hsh, st)
                            done += 1
                            if progress_cb:
                                progress_cb(done, total)
                            continue
                        except Exception:
                            # Fallback to copy below if rename failed
                            pass
                    # Fallback: copy
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

            # Success: optionally delete source if requested and source is off-shared
            try:
                if delete_source_on_success and not str(src_res).startswith(str(sr_resolved)) and src_res.exists():
                    # Best-effort remove; ignore errors
                    src_res.unlink(missing_ok=True)
            except Exception:
                pass

            # Success: yield for registration
            try:
                st = recorded_time
                # Write/update recording metadata.json
                try:
                    md = self.build_recording_metadata(
                        video_path=dest,
                        subject_id="unknown",
                        experiment_type="",
                        batch_links=[],
                        sample_hash=hsh,
                        full_hash=None,
                        recorded_time=st,
                        recorded_time_source=recorded_time_source,
                    )
                    self.write_recording_metadata(dest.parent, md)
                except Exception:
                    pass
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

    # ------------------------------------------------------------------
    # Recording metadata.json I/O helpers
    # ------------------------------------------------------------------
    def read_recording_metadata(self, recording_dir: Path) -> Dict[str, Any]:
        meta_path = Path(recording_dir) / "metadata.json"
        if not meta_path.exists():
            return {}
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def write_recording_metadata(self, recording_dir: Path, metadata: Dict[str, Any]) -> None:
        recording_dir = Path(recording_dir)
        try:
            recording_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        meta_path = recording_dir / "metadata.json"
        # Ensure stable keys ordering for diffs
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, sort_keys=True, default=str)
        except Exception:
            # Best-effort; do not raise to avoid breaking pipelines
            pass

    def build_recording_metadata(
        self,
        *,
        video_path: Path,
        subject_id: str,
        experiment_type: str,
        batch_links: list[str] | None,
        sample_hash: str,
        full_hash: str | None,
        recorded_time: datetime | None,
        recorded_time_source: str | None,
    ) -> Dict[str, Any]:
        st = video_path.stat()
        meta: Dict[str, Any] = {
            "subject_id": subject_id,
            "experiment_type": experiment_type,
            "batch_links": list(batch_links or []),
            "provenance": {
                "source": "unknown",  # e.g., 'third_party_import', 'scan_and_move'
                "notes": "",
            },
            "file": {
                "path": str(video_path),
                "filename": video_path.name,
                "size_bytes": st.st_size,
                "last_modified": st.st_mtime,
                "sample_hash": sample_hash,
                "full_hash": full_hash,
            },
            "times": {
                "recorded_time": recorded_time.isoformat() if recorded_time else None,
                "recorded_time_source": recorded_time_source,
            },
            "processing_history": [],
            "experiment_links": [],
            "derived_files": {},
            "is_master_member": False,
        }
        return meta

    def append_processing_event(self, metadata: Dict[str, Any], *, stage: str, tool: str, details: Dict[str, Any] | None = None) -> None:
        events = metadata.setdefault("processing_history", [])
        events.append({
            "stage": stage,
            "tool": tool,
            "at": datetime.now().isoformat(),
            "details": details or {},
        })

    