import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from .base_plugin import BasePlugin
from ..core.metadata import PluginMetadata, Sex


logger = logging.getLogger(__name__)


class CustomMetadataResolverPlugin(BasePlugin):
    """Project-level helper for resolving subjects and simple assignments.

    Actions (via run_import):
      - suggest_subjects: scan master library, extract 3-digit IDs from filenames, return unique IDs not yet in project
      - assign_subject_to_recording: create a minimal experiment for subject and link a recording
      - assign_subject_sex: set subject sex to M/F (case-insensitive)
    """

    # Patterns to extract 3-digit IDs from filenames
    # Match a 3-digit token not part of a larger number, optionally followed by M/m
    # Works even when adjacent to underscores or letters (e.g., "259M", "_243_")
    _ID_PATTERNS = [
        re.compile(r"(?<!\d)(\d{3})(?:[mM])?(?!\d)"),
    ]

    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="CustomMetadataResolver",
            date_created=datetime.now(),
            version="0.1.0",
            description=(
                "Suggest subjects from master library; assign subject-to-recording; set subject sex."
            ),
            author="MUS1 Team",
            supported_experiment_types=[],
            readable_data_formats=[],
            analysis_capabilities=[
                "suggest_subjects",
                "assign_subject_to_recording",
                "assign_subject_sex",
                "propose_subject_assignments_from_master",
                "propose_subject_sex_from_master",
            ],
            plugin_type="importer",
        )

    def analysis_capabilities(self) -> List[str]:
        return [
            "suggest_subjects",
            "assign_subject_to_recording",
            "assign_subject_sex",
            "propose_subject_assignments_from_master",
            "propose_subject_sex_from_master",
        ]

    def readable_data_formats(self) -> List[str]:
        return []

    def validate_experiment(self, experiment, project_state) -> None:
        # Project-level utility; no experiment validation
        return None

    def analyze_experiment(self, experiment, data_manager, capability: str) -> Dict[str, Any]:
        # Not used for this project-level plugin
        return {"status": "failed", "error": "Not an experiment-level plugin"}

    def run_import(self, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        action = str(params.get("action", "")).strip().lower()
        try:
            if action == "suggest_subjects":
                return self._suggest_subjects(params, project_manager)
            if action == "assign_subject_to_recording":
                return self._assign_subject_to_recording(params, project_manager)
            if action == "assign_subject_sex":
                return self._assign_subject_sex(params, project_manager)
            if action == "propose_subject_assignments_from_master":
                return self._propose_subject_assignments_from_master(params, project_manager)
            if action == "propose_subject_sex_from_master":
                return self._propose_subject_sex_from_master(params, project_manager)
            return {"status": "failed", "error": f"Unknown action: {action}"}
        except Exception as e:
            logger.error(f"CustomMetadataResolver '{action}' failed: {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    # --- Actions ---

    def _suggest_subjects(self, params: Dict[str, Any], pm) -> Dict[str, Any]:
        """Return unique 3-digit IDs found in master library not yet in project."""
        library_path_val = params.get("library_path")
        if library_path_val:
            library_path = Path(library_path_val).expanduser().resolve()
        else:
            sr = pm.state_manager.project_state.shared_root or pm.get_shared_directory()
            library_path = (Path(sr).expanduser().resolve() / "recordings" / "master").resolve()

        if not library_path.exists():
            return {"status": "failed", "error": f"Library path not found: {library_path}"}

        dm = pm.data_manager
        items = list(dm.discover_video_files([library_path], extensions=None, recursive=True, excludes=None))
        existing = set(pm.state_manager.project_state.subjects.keys())

        candidates: set[str] = set()
        for path_obj, _hash in items:
            # Skip macOS AppleDouble sidecar files
            if Path(path_obj).name.startswith("._"):
                continue
            stem = Path(path_obj).stem
            sid: str | None = None
            for rx in self._ID_PATTERNS:
                m = rx.search(stem)
                if m:
                    sid = str(m.group(1))
                    break
            if sid and sid not in existing:
                candidates.add(sid)

        return {"status": "success", "suggestions": sorted(candidates)}

    def _assign_subject_to_recording(self, params: Dict[str, Any], pm) -> Dict[str, Any]:
        subject_id = str(params["subject_id"]).strip()
        recording_path = Path(params["recording_path"]).expanduser().resolve()
        if not recording_path.exists():
            return {"status": "failed", "error": f"Recording not found: {recording_path}"}
        if subject_id not in pm.state_manager.project_state.subjects:
            return {"status": "failed", "error": f"Subject not found: {subject_id}"}

        exp_type = str(params.get("exp_type", "Unknown"))
        experiment_id = str(params.get("experiment_id") or recording_path.stem)

        pm.add_experiment(
            experiment_id=experiment_id,
            subject_id=subject_id,
            date_recorded=datetime.now(),
            exp_type=exp_type,
            exp_subtype=None,
            processing_stage="recorded",
            associated_plugins=[],
            plugin_params={},
        )
        pm.link_video_to_experiment(experiment_id=experiment_id, video_path=recording_path, notes="")
        return {"status": "success", "experiment_id": experiment_id, "linked": str(recording_path)}

    def _assign_subject_sex(self, params: Dict[str, Any], pm) -> Dict[str, Any]:
        subject_id = str(params["subject_id"]).strip()
        sex_in = str(params["sex"]).strip().lower()
        if subject_id not in pm.state_manager.project_state.subjects:
            return {"status": "failed", "error": f"Subject not found: {subject_id}"}
        if sex_in not in {"m", "f"}:
            return {"status": "failed", "error": "sex must be 'M' or 'F'"}

        sex_val = Sex.M if sex_in == "m" else Sex.F
        pm.add_subject(subject_id=subject_id, sex=sex_val)
        return {"status": "success", "subject_id": subject_id, "sex": "M" if sex_val == Sex.M else "F"}

    # --- Proposal helpers for interactive CLI flows ---
    def _propose_subject_assignments_from_master(self, params: Dict[str, Any], pm) -> Dict[str, Any]:
        library_path_val = params.get("library_path")
        if library_path_val:
            library_path = Path(library_path_val).expanduser().resolve()
        else:
            sr = pm.state_manager.project_state.shared_root or pm.get_shared_directory()
            library_path = (Path(sr).expanduser().resolve() / "recordings" / "master").resolve()

        if not library_path.exists():
            return {"status": "failed", "error": f"Library path not found: {library_path}"}

        dm = pm.data_manager
        items = list(dm.discover_video_files([library_path], extensions=None, recursive=True, excludes=None))
        proposals: list[dict[str, str]] = []
        for path_obj, _hash in items:
            name = Path(path_obj).name
            if name.startswith("._"):
                continue
            stem = Path(path_obj).stem
            sid: str | None = None
            for rx in self._ID_PATTERNS:
                m = rx.search(stem)
                if m:
                    sid = str(m.group(1))
                    break
            if sid:
                proposals.append({"recording_path": str(Path(path_obj).resolve()), "subject_id": sid})

        # Deduplicate proposals per (path, sid)
        seen: set[tuple[str, str]] = set()
        uniq: list[dict[str, str]] = []
        for p in proposals:
            key = (p["recording_path"], p["subject_id"]) 
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        return {"status": "success", "proposals": uniq}

    def _propose_subject_sex_from_master(self, params: Dict[str, Any], pm) -> Dict[str, Any]:
        library_path_val = params.get("library_path")
        if library_path_val:
            library_path = Path(library_path_val).expanduser().resolve()
        else:
            sr = pm.state_manager.project_state.shared_root or pm.get_shared_directory()
            library_path = (Path(sr).expanduser().resolve() / "recordings" / "master").resolve()

        if not library_path.exists():
            return {"status": "failed", "error": f"Library path not found: {library_path}"}

        dm = pm.data_manager
        items = list(dm.discover_video_files([library_path], extensions=None, recursive=True, excludes=None))
        # Build subject -> observed sex tokens
        sex_map: dict[str, dict[str, int]] = {}
        for path_obj, _hash in items:
            name = Path(path_obj).name
            if name.startswith("._"):
                continue
            stem = Path(path_obj).stem
            # Tokenize by underscore
            tokens = stem.split("_")
            sid: str | None = None
            # Find first 3-digit token as subject id
            for t in tokens:
                if re.fullmatch(r"\d{3}", t):
                    sid = t
                    break
            if not sid:
                # fallback to regex anywhere
                m = self._ID_PATTERNS[0].search(stem)
                if m:
                    sid = m.group(1)
            if not sid:
                continue

            # Find nearby sex token 'M' or 'F'
            sex_tok: str | None = None
            # Search token list for 'M' or 'F'
            for t in tokens:
                if t in {"M", "F"}:
                    sex_tok = t
                    break
            if not sex_tok:
                continue

            d = sex_map.setdefault(sid, {"M": 0, "F": 0})
            d[sex_tok] += 1

        # Convert to proposals using majority vote, only for existing subjects
        proposals: list[dict[str, str]] = []
        existing_subjects = set(pm.state_manager.project_state.subjects.keys())
        for sid, counts in sex_map.items():
            if sid not in existing_subjects:
                continue
            sex_val = "M" if counts.get("M", 0) >= counts.get("F", 0) else "F"
            proposals.append({"subject_id": sid, "sex": sex_val})

        return {"status": "success", "proposals": proposals}


