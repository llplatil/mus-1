"""
Copperlab Assembly Plugin - Clean Implementation

A streamlined plugin for assembling Copperlab projects from CSV data sources.
Focuses on core functionality: subject extraction, experiment parsing, and data validation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import re
import logging
import pandas as pd

from mus1.plugins.base_plugin import BasePlugin
from mus1.core.metadata import PluginMetadata, ExperimentMetadata, ProjectState

logger = logging.getLogger("mus1.plugins.CopperlabAssembly")


class CopperlabAssembly(BasePlugin):
    """Clean Copperlab assembly plugin implementation."""

    # Experiment type mappings
    EXPERIMENT_TYPE_MAPPING = {
        "open field/arean habitation": "OF",
        "novel object | familiarization session": "FAM",
        "novel object | recognition session": "NOV",
        "elevated zero maze": "EZM",
        "rota rod": "RR",
    }

    def plugin_self_metadata(self) -> PluginMetadata:
        """Plugin metadata for registration."""
        return PluginMetadata(
            name="CopperlabAssembly",
            date_created=datetime.now(),
            version="1.0.0",
            description="Copperlab project assembly plugin for automated subject and experiment management",
            author="Copperlab",
            readable_data_formats=["lab_experiments_csv", "colony_csv", "behavior_csv", "treatment_csv"],
            analysis_capabilities=["assemble_project", "extract_subjects", "validate_experiments"],
            plugin_type="importer",
            supported_experiment_types=["RR", "OF", "NOV", "EZM", "FAM"],
            supported_experiment_subtypes={
                "RR": ["constant_speed", "accelerating"],
                "OF": ["circular_arena"],
                "NOV": ["FAM", "NOV", "recognition"],
                "EZM": ["standard", "plus_maze"],
                "FAM": ["familiarization"]
            },
            supported_processing_stages=["planned", "recorded", "tracked", "interpreted"],
        )

    def readable_data_formats(self) -> List[str]:
        """Supported data formats."""
        return ["lab_experiments_csv", "colony_csv", "behavior_csv", "treatment_csv"]

    def analysis_capabilities(self) -> List[str]:
        """Supported analysis capabilities."""
        return ["assemble_project", "extract_subjects", "validate_experiments"]

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """Validate experiment metadata."""
        # Basic validation - can be extended
        if not experiment.subject_id:
            raise ValueError(f"Experiment {experiment.experiment_id} missing subject_id")
        if not experiment.exp_type:
            raise ValueError(f"Experiment {experiment.experiment_id} missing experiment type")

    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager, capability: str) -> Dict[str, Any]:
        """Analyze individual experiment - not used for assembly."""
        return {
            "status": "failed",
            "error": "Not applicable at experiment-level",
            "capability_executed": capability
        }

    # -------------------------------
    # Project-level actions (modern API)
    # -------------------------------
    def supported_project_actions(self) -> List[str]:
        """Supported project-level actions."""
        return [
            "parse_experiments_csv",
            "extract_subjects_from_csv",
            "validate_csv_data",
            "create_experiments_from_csv",
            "get_subject_extraction_batch",
            "approve_subjects",
        ]

    def run_action(self, action: str, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        """Execute project-level actions."""
        try:
            if action == "parse_experiments_csv":
                return self._parse_experiments_csv(params)
            elif action == "extract_subjects_from_csv":
                return self._extract_subjects_from_csv(params, project_manager)
            elif action == "validate_csv_data":
                return self._validate_csv_data(params)
            elif action == "create_experiments_from_csv":
                return self._create_experiments_from_csv(params, project_manager)
            elif action == "get_subject_extraction_batch":
                return self._get_subject_extraction_batch(params, project_manager)
            elif action == "approve_subjects":
                return self._approve_subjects(params, project_manager)
            else:
                return {
                    "status": "failed",
                    "error": f"Unknown action: {action}",
                    "available_actions": self.supported_project_actions()
                }
        except Exception as e:
            logger.error(f"Error executing action {action}: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "action": action
            }

    # ---------------------------------------------------------------------
    # Core CSV parsing functionality
    # ---------------------------------------------------------------------

    def _parse_experiments_csv(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Parse experiments from CSV file."""
        csv_path_str = params.get("csv_path")
        if not csv_path_str:
            return {"status": "failed", "error": "csv_path parameter required"}

        csv_path = Path(csv_path_str).expanduser().resolve()
        if not csv_path.exists():
            return {"status": "failed", "error": f"CSV file not found: {csv_path}"}

        try:
            experiments = self._parse_csv_experiments(csv_path)
            return {
                "status": "success",
                "experiments": experiments,
                "count": len(experiments)
            }
        except Exception as e:
            return {"status": "failed", "error": f"Failed to parse CSV: {e}"}

    def _parse_csv_experiments(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Parse experiment data from CSV file."""
        try:
            df = pd.read_csv(csv_path, encoding="utf-8", encoding_errors="ignore")
        except Exception:
            # Fallback to manual parsing if pandas fails
            return self._parse_csv_manual(csv_path)

        experiments = []
        current_section = None

        for _, row in df.iterrows():
            section_key = str(row.iloc[0]).strip().lower() if len(row) > 0 else ""

            # Check if this is a section header
            if section_key in self.EXPERIMENT_TYPE_MAPPING:
                current_section = self.EXPERIMENT_TYPE_MAPPING[section_key]
                continue

            # Parse experiment data if we have a current section
            if current_section and len(row) >= 5:
                subject_id = self._extract_subject_id_from_row(row)
                date = self._extract_date_from_row(row)

                if subject_id and date:
                    experiments.append({
                        "subject_id": subject_id,
                        "experiment_type": current_section,
                        "date": date.strftime("%Y-%m-%d"),
                        "source_file": csv_path.name
                    })

        # Sort by subject ID, date, experiment type
        experiments.sort(key=lambda x: (
            int(x["subject_id"]) if x["subject_id"].isdigit() else 0,
            x["date"],
            x["experiment_type"]
        ))

        return experiments

    def _parse_csv_manual(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Manual CSV parsing fallback."""
        content = csv_path.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        experiments = []
        current_section = None

        for line in lines:
            cols = [col.strip() for col in line.split(",")]
            if not cols:
                continue

            section_key = cols[0].strip().lower()

            # Check if this is a section header
            if section_key in self.EXPERIMENT_TYPE_MAPPING:
                current_section = self.EXPERIMENT_TYPE_MAPPING[section_key]
                continue

            # Parse experiment data
            if current_section and len(cols) >= 5:
                subject_id = self._extract_subject_id_manual(cols)
                date = self._parse_date_manual(cols[4] if len(cols) > 4 else "")

                if subject_id and date:
                    experiments.append({
                        "subject_id": subject_id,
                        "experiment_type": current_section,
                        "date": date.strftime("%Y-%m-%d"),
                        "source_file": csv_path.name
                    })

        return experiments

    def _extract_subject_id_from_row(self, row) -> Optional[str]:
        """Extract subject ID from DataFrame row."""
        import math
        for col in row:
            # Handle numeric values read by pandas (e.g., 974.0)
            if isinstance(col, (int, float)) and not (isinstance(col, float) and math.isnan(col)):
                try:
                    val = int(col)
                    if 0 < val < 1000:
                        return f"{val:03d}"
                except Exception:
                    pass
            col_str = str(col).strip()
            if col_str and col_str.isdigit() and len(col_str) <= 3:
                return f"{int(col_str):03d}"
        return None

    def _extract_subject_id_manual(self, cols: List[str]) -> Optional[str]:
        """Extract subject ID from CSV columns."""
        if cols and cols[0].strip().isdigit():
            subject_id = cols[0].strip()
            if len(subject_id) <= 3:
                return f"{int(subject_id):03d}"
        return None

    def _extract_date_from_row(self, row) -> Optional[datetime]:
        """Extract date from DataFrame row."""
        for col in row:
            date = self._parse_date_manual(str(col).strip())
            if date:
                return date
        return None

    def _parse_date_manual(self, date_str: str) -> Optional[datetime]:
        """Parse date string in various formats."""
        if not date_str:
            return None

        formats = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    # ---------------------------------------------------------------------
    # Subject extraction functionality
    # ---------------------------------------------------------------------

    def _extract_subjects_from_csv(self, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        """Extract subjects from CSV files."""
        csv_dir_str = params.get("csv_dir")
        if not csv_dir_str:
            return {"status": "failed", "error": "csv_dir parameter required"}

        csv_dir = Path(csv_dir_str).expanduser().resolve()
        if not csv_dir.exists() or not csv_dir.is_dir():
            return {"status": "failed", "error": f"CSV directory not found: {csv_dir}"}

        try:
            subjects = self._extract_subjects_from_directory(csv_dir)
            return {
                "status": "success",
                "subjects": subjects,
                "count": len(subjects)
            }
        except Exception as e:
            return {"status": "failed", "error": f"Failed to extract subjects: {e}"}

    def _extract_subjects_from_directory(self, csv_dir: Path) -> List[Dict[str, Any]]:
        """Extract subject data from all CSV files in directory."""
        subjects = {}

        for csv_file in csv_dir.glob("*.csv"):
            try:
                file_subjects = self._extract_subjects_from_single_csv(csv_file)
                # Merge subjects, preferring newer data
                for subject in file_subjects:
                    subject_id = subject["id"]
                    if subject_id not in subjects:
                        subjects[subject_id] = subject
                    else:
                        # Merge data, preferring non-empty values
                        existing = subjects[subject_id]
                        for key, value in subject.items():
                            if key != "id" and value and not existing.get(key):
                                existing[key] = value
            except Exception as e:
                logger.warning(f"Failed to process {csv_file}: {e}")
                continue

        return list(subjects.values())

    def _extract_subjects_from_single_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Extract subjects from a single CSV file."""
        try:
            df = pd.read_csv(csv_path, encoding="utf-8", encoding_errors="ignore")
        except Exception:
            return []

        subjects = []

        for _, row in df.iterrows():
            subject = self._extract_subject_from_row(row, csv_path.name)
            if subject:
                subjects.append(subject)

        return subjects

    def _extract_subject_from_row(self, row, source_file: str) -> Optional[Dict[str, Any]]:
        """Extract subject data from a DataFrame row."""
        subject_id = None
        sex = None
        birth_date = None
        genotype = None
        treatment = None

        # Extract subject ID
        import math
        for col in row:
            # Prefer numeric detection first
            if isinstance(col, (int, float)) and not (isinstance(col, float) and math.isnan(col)):
                try:
                    val = int(col)
                    if 0 < val < 1000:
                        subject_id = f"{val:03d}"
                        break
                except Exception:
                    pass
            col_str = str(col).strip()
            if col_str and col_str.isdigit() and len(col_str) <= 3:
                subject_id = f"{int(col_str):03d}"
                break

        if not subject_id:
            return None

        # Extract other data
        for col_name, col_value in row.items():
            col_name_lower = str(col_name).lower().strip()
            value = str(col_value).strip() if pd.notna(col_value) else ""

            if not value:
                continue

            if "sex" in col_name_lower:
                sex = value.upper()[0] if value.upper() in ["M", "F", "MALE", "FEMALE"] else None
            elif any(date_key in col_name_lower for date_key in ["dob", "birth", "date"]):
                birth_date = self._parse_date_manual(value)
                if birth_date:
                    birth_date = birth_date.strftime("%Y-%m-%d")
            elif "genotype" in col_name_lower:
                genotype = value
            elif "treatment" in col_name_lower:
                treatment = value

        return {
            "id": subject_id,
            "sex": sex,
            "birth_date": birth_date,
            "genotype": genotype,
            "treatment": treatment,
            "source_file": source_file
        }

    # ---------------------------------------------------------------------
    # Validation functionality
    # ---------------------------------------------------------------------

    def _validate_csv_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate CSV data for consistency."""
        csv_path_str = params.get("csv_path")
        if not csv_path_str:
            return {"status": "failed", "error": "csv_path parameter required"}

        csv_path = Path(csv_path_str).expanduser().resolve()
        if not csv_path.exists():
            return {"status": "failed", "error": f"CSV file not found: {csv_path}"}

        try:
            validation_result = self._validate_csv_file(csv_path)
            return {
                "status": "success" if not validation_result["errors"] else "warning",
                "validation": validation_result
            }
        except Exception as e:
            return {"status": "failed", "error": f"Validation failed: {e}"}

    def _validate_csv_file(self, csv_path: Path) -> Dict[str, Any]:
        """Validate a CSV file for data consistency."""
        try:
            df = pd.read_csv(csv_path, encoding="utf-8", encoding_errors="ignore")
        except Exception as e:
            return {"errors": [f"Failed to read CSV: {e}"], "warnings": [], "stats": {}}

        errors = []
        warnings = []
        stats = {"rows": len(df), "columns": len(df.columns)}

        # Check for required columns
        required_cols = ["subject_id", "experiment_type", "date"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            errors.append(f"Missing required columns: {missing_cols}")

        # Validate data types and formats
        for idx, row in df.iterrows():
            # Validate subject ID
            if "subject_id" in df.columns:
                subject_id = str(row.get("subject_id", "")).strip()
                if not subject_id.isdigit() or len(subject_id) > 3:
                    errors.append(f"Row {idx}: Invalid subject ID {subject_id}")

            # Validate experiment type
            if "experiment_type" in df.columns:
                exp_type = str(row.get("experiment_type", "")).strip()
                if exp_type and exp_type not in self.EXPERIMENT_TYPE_MAPPING.values():
                    warnings.append(f"Row {idx}: Unknown experiment type {exp_type}")

            # Validate date
            if "date" in df.columns:
                date_str = str(row.get("date", "")).strip()
                if date_str and not self._parse_date_manual(date_str):
                    errors.append(f"Row {idx}: Invalid date format {date_str}")

        return {
            "errors": errors,
            "warnings": warnings,
            "stats": stats
        }

    # ---------------------------------------------------------------------
    # Experiment creation functionality
    # ---------------------------------------------------------------------

    def _create_experiments_from_csv(self, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        """Create experiments from CSV data."""
        experiments_data = params.get("experiments_data", [])
        if not experiments_data:
            return {"status": "failed", "error": "experiments_data parameter required"}

        try:
            created_experiments = []
            for exp_data in experiments_data:
                experiment = self._create_single_experiment(exp_data, project_manager)
                if experiment:
                    created_experiments.append(experiment)

            return {
                "status": "success",
                "created_experiments": created_experiments,
                "count": len(created_experiments)
            }
        except Exception as e:
            return {"status": "failed", "error": f"Failed to create experiments: {e}"}

    def _create_single_experiment(self, exp_data: Dict[str, Any], project_manager) -> Optional[Dict[str, Any]]:
        """Create a single experiment from data."""
        try:
            subject_id = exp_data.get("subject_id")
            exp_type = exp_data.get("experiment_type")
            date_str = exp_data.get("date")

            if not all([subject_id, exp_type, date_str]):
                return None

            # Parse date
            date = self._parse_date_manual(date_str)
            if not date:
                return None

            # Create experiment ID
            experiment_id = f"{subject_id}_{exp_type}_{date.strftime('%Y%m%d')}"

            # Add experiment to project
            project_manager.add_experiment(
                experiment_id=experiment_id,
                subject_id=subject_id,
                date_recorded=date,
                exp_type=exp_type,
                exp_subtype=None,
                processing_stage="planned",
                associated_plugins=[self.plugin_self_metadata().name],
                plugin_params={}
            )

            return {
                "experiment_id": experiment_id,
                "subject_id": subject_id,
                "experiment_type": exp_type,
                "date": date_str
            }
        except Exception as e:
            logger.error(f"Failed to create experiment: {e}")
            return None

    # ---------------------------------------------------------------------
    # Subject batch processing functionality
    # ---------------------------------------------------------------------

    def _get_subject_extraction_batch(self, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        """Get a batch of subjects for review."""
        subjects_data = params.get("subjects_data", [])
        batch_size = int(params.get("batch_size", 10))
        offset = int(params.get("offset", 0))

        if not subjects_data:
            return {"status": "failed", "error": "subjects_data parameter required"}

        # Get batch
        batch = subjects_data[offset:offset + batch_size]

        return {
            "status": "success",
            "batch": batch,
            "batch_size": len(batch),
            "offset": offset,
            "total": len(subjects_data),
            "has_more": offset + batch_size < len(subjects_data)
        }

    def _approve_subjects(self, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        """Approve and create subjects in the lab."""
        subjects_data = params.get("subjects_data", [])
        subject_ids = params.get("subject_ids", [])

        if not subjects_data or not subject_ids:
            return {"status": "failed", "error": "subjects_data and subject_ids parameters required"}

        approved_subjects = []
        for subject_data in subjects_data:
            if subject_data["id"] in subject_ids:
                try:
                    # Create subject in lab
                    sex_enum = None
                    if subject_data.get("sex") == "M":
                        from mus1.core.metadata import Sex
                        sex_enum = Sex.M
                    elif subject_data.get("sex") == "F":
                        from mus1.core.metadata import Sex
                        sex_enum = Sex.F

                    kwargs = dict(
                        subject_id=subject_data["id"],
                        birth_date=subject_data.get("birth_date"),
                        genotype=subject_data.get("genotype"),
                        treatment=subject_data.get("treatment"),
                    )
                    if sex_enum is not None:
                        kwargs["sex"] = sex_enum
                    project_manager.add_subject(**kwargs)

                    approved_subjects.append(subject_data)
                except Exception as e:
                    logger.error(f"Failed to create subject {subject_data['id']}: {e}")

        return {
            "status": "success",
            "approved_subjects": approved_subjects,
            "count": len(approved_subjects)
        }

# End of CopperlabAssembly plugin implementation

