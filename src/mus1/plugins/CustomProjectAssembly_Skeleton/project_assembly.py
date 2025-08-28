from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional, Iterable, Tuple
from datetime import datetime

from ..plugins.base_plugin import BasePlugin
from ..core.metadata import ExperimentMetadata, ProjectState, PluginMetadata


class CustomProjectAssemblySkeleton(BasePlugin):
    """
    Skeleton project-assembly plugin. Copy/rename this package for your lab and
    implement CSV interpretation, smart scanning heuristics, and any per-lab rules.
    """

    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="CustomProjectAssembly_Skeleton",
            date_created=datetime.now(),
            version="0.0.1",
            description="Skeleton project assembly plugin with CSV parsing and smart scan hooks.",
            author="mus1",
            supported_experiment_types=[],
            supported_experiment_subtypes={},
            supported_processing_stages=[],
            readable_data_formats=["lab_experiments_csv"],
            analysis_capabilities=["assemble_project"],
            plugin_type="importer",
        )

    def readable_data_formats(self) -> List[str]:
        return ["lab_experiments_csv"]

    def analysis_capabilities(self) -> List[str]:
        return ["assemble_project"]

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        # Project-level plugin: not tied to individual experiments; no-op.
        return None

    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: 'DataManager', capability: str) -> Dict[str, Any]:
        # Not applicable; assembly happens at project-level (via CLI invoking project manager + plugin helpers)
        return {"status": "failed", "error": "Not applicable for experiment-level"}

    # --- Project assembly hooks (to be called from CLI/ProjectManager) ---

    def parse_experiments_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Parse lab experiments CSV to a normalized list of records.

        Output fields: subject_id (int), experiment_type (str), date (YYYY-MM-DD)
        """
        from .utils import extract_subject_experiment_records
        recs = extract_subject_experiment_records(csv_path)
        out: List[Dict[str, Any]] = []
        for sid, et, dt in recs:
            out.append({"subject_id": sid, "experiment_type": et, "date": dt})
        return out

    def suggest_recording_matches(self, *,
                                  project_media_dir: Path,
                                  subjects_to_find: List[str]) -> List[Tuple[Path, str]]:
        """Very simple heuristic: scan media folder for filenames containing subject IDs.

        Returns list of (path, subject_id) suggestions.
        """
        suggestions: List[Tuple[Path, str]] = []
        try:
            for p in project_media_dir.glob("**/*"):
                if not p.is_file():
                    continue
                name = p.name.lower()
                for sid in subjects_to_find:
                    if sid and sid.lower() in name:
                        suggestions.append((p, sid))
                        break
        except Exception:
            pass
        return suggestions

    def load_scan_hints(self) -> Dict[str, Any]:
        """Load optional config.yaml in this package for scan hints."""
        try:
            cfg = Path(__file__).parent / "config.yaml"
            if cfg.exists():
                import yaml
                with open(cfg, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return data.get("scan_hints", {}) or {}
        except Exception:
            pass
        return {}


