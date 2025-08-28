from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import inspect
import pandas as pd

from ..base_plugin import BasePlugin
from ...core.project_manager import ProjectManager
from ...core.metadata import PluginMetadata, ProjectState, ExperimentMetadata

logger = logging.getLogger(__name__)


class SubjectImporter(BasePlugin):
    """Project-assembly-scoped subject importer using CSV (pandas)."""

    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="CustomSubjectImporter",
            date_created=datetime.now(),
            version="1.0",
            description="Imports a list of subjects from a CSV into the current project (assembly plugin).",
            author="mus1",
            supported_experiment_types=[],
            readable_data_formats=["subjects_csv"],
            analysis_capabilities=["import_subjects"],
            plugin_type="importer",
        )

    def analysis_capabilities(self) -> List[str]:
        return ["import_subjects"]

    def readable_data_formats(self) -> List[str]:
        return ["subjects_csv"]

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        return None

    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: 'DataManager', capability: str) -> Dict[str, Any]:
        return {"status": "failed", "error": "Not applicable at experiment level"}

    def run_import(self, params: Dict[str, Any], project_manager: ProjectManager) -> Dict[str, Any]:
        plugin_name = self.plugin_self_metadata().name
        try:
            csv_path = Path(params.get("subjects_csv_path", "")).expanduser()
            if not csv_path.is_file():
                raise ValueError("subjects_csv_path must be an existing CSV file")

            if not getattr(project_manager, "_current_project_root", None):
                raise RuntimeError("No project loaded")

            df = pd.read_csv(csv_path, dtype={"subject_id": str})
            if 'subject_id' not in df.columns:
                raise ValueError("CSV must contain a 'subject_id' column.")
            df['subject_id'] = df['subject_id'].astype(str)
            df['subject_id'] = df['subject_id'].apply(lambda x: x.zfill(3) if x.isdigit() and len(x) < 3 else x)

            added_count = 0
            skipped_count = 0
            existing_subject_ids = set(project_manager.state_manager.project_state.subjects.keys())

            for _, row in df.iterrows():
                subject_id = str(row.get('subject_id', '')).strip()
                if not subject_id or subject_id.lower() == 'nan':
                    skipped_count += 1
                    continue
                if subject_id in existing_subject_ids:
                    skipped_count += 1
                    continue
                subject_args = row.to_dict()
                import pandas as _pd
                clean_args = {k: None if _pd.isna(v) else v for k, v in subject_args.items()}
                if clean_args.get('notes') is None:
                    clean_args['notes'] = ""
                for date_col in ['birth_date', 'death_date']:
                    if date_col in clean_args and clean_args[date_col]:
                        try:
                            clean_args[date_col] = _pd.to_datetime(clean_args[date_col]).to_pydatetime()
                        except Exception:
                            clean_args[date_col] = None
                valid_params = inspect.signature(project_manager.add_subject).parameters
                final_args = {k: v for k, v in clean_args.items() if k in valid_params}
                project_manager.add_subject(**final_args)
                added_count += 1
                existing_subject_ids.add(subject_id)

            return {"status": "success", "message": f"Added: {added_count}, Skipped: {skipped_count}", "added_count": added_count, "skipped_count": skipped_count}
        except Exception as e:
            logger.error(f"Subject import failed: {e}")
            return {"status": "failed", "error": str(e)}


