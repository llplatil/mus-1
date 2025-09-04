"""
Copperlab Assembly Plugin - Integrated Implementation

A comprehensive plugin for assembling Copperlab projects from CSV data sources.
Integrates the complete data processing pipeline with project state management.
"""

from __future__ import annotations

import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import re
import logging
import json
import argparse

from mus1.plugins.base_plugin import BasePlugin
from mus1.core.metadata import PluginMetadata, ExperimentMetadata, ProjectState

logger = logging.getLogger("mus1.plugins.CopperlabAssembly")


class CopperlabAssembly(BasePlugin):
    """Integrated Copperlab assembly plugin with full pipeline support."""

    # Experiment type mappings
    EXPERIMENT_TYPE_MAPPING = {
        "open field/arean habitation": "OF",
        "novel object | familiarization session": "FAM",
        "novel object | recognition session": "NOV",
        "elevated zero maze": "EZM",
        "rota rod": "RR",
    }

    def __init__(self):
        super().__init__()
        self.plugin_root = Path(__file__).parent
        self.processing_dir = self.plugin_root / "processing"
        self.data_dir = self.plugin_root / "data"
        self.pipeline_script = self.processing_dir / "run_full_pipeline.sh"

    def plugin_self_metadata(self) -> PluginMetadata:
        """Plugin metadata for registration."""
        return PluginMetadata(
            name="CopperlabAssembly",
            date_created=datetime.now(),
            version="2.0.0",
            description="Copperlab project assembly plugin with integrated data processing pipeline",
            author="Copperlab",
            readable_data_formats=["lab_experiments_csv", "colony_csv", "behavior_csv", "treatment_csv"],
            analysis_capabilities=["assemble_project", "extract_subjects", "validate_experiments", "run_pipeline", "verify_project_state"],
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
        return ["assemble_project", "extract_subjects", "validate_experiments", "run_pipeline", "verify_project_state"]

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
    # CLI Integration Methods
    # -------------------------------

    def run_pipeline_command(self, args: List[str] = None) -> Dict[str, Any]:
        """Run the complete data processing pipeline via CLI."""
        try:
            if not self.pipeline_script.exists():
                return {
                    "status": "failed",
                    "error": f"Pipeline script not found: {self.pipeline_script}"
                }

            # Build command
            cmd = ["bash", str(self.pipeline_script)]
            if args:
                cmd.extend(args)

            logger.info(f"Running pipeline command: {' '.join(cmd)}")

            # Run the pipeline
            result = subprocess.run(
                cmd,
                cwd=self.plugin_root,
                capture_output=True,
                text=True,
                env={**dict(os.environ), "PYTHONPATH": str(self.plugin_root.parent.parent.parent / "src")}
            )

            if result.returncode == 0:
                return {
                    "status": "success",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "message": "Pipeline completed successfully"
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Pipeline failed with exit code {result.returncode}",
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }

        except Exception as e:
            logger.error(f"Error running pipeline: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    def verify_project_state(self, project_path: Path, expected_subjects: int = None, expected_experiments: int = None) -> Dict[str, Any]:
        """Verify that a project was created correctly with the expected data."""
        try:
            if not project_path.exists():
                return {
                    "status": "failed",
                    "error": f"Project directory does not exist: {project_path}"
                }

            # Look for project state files
            project_state_file = project_path / "project_state.json"
            if not project_state_file.exists():
                return {
                    "status": "failed",
                    "error": f"Project state file not found: {project_state_file}"
                }

            # Load project state
            with open(project_state_file, 'r') as f:
                project_state = json.load(f)

            # Extract actual counts
            actual_subjects = len(project_state.get("subjects", []))
            actual_experiments = len(project_state.get("experiments", []))

            # Verify counts if expected values provided
            verification_results = {
                "subjects_match": expected_subjects is None or actual_subjects == expected_subjects,
                "experiments_match": expected_experiments is None or actual_experiments == expected_experiments,
            }

            # Overall verification status
            all_verified = all(verification_results.values())

            return {
                "status": "success" if all_verified else "warning",
                "project_path": str(project_path),
                "actual_subjects": actual_subjects,
                "actual_experiments": actual_experiments,
                "expected_subjects": expected_subjects,
                "expected_experiments": expected_experiments,
                "verification_results": verification_results,
                "message": "Project state verification completed"
            }

        except Exception as e:
            logger.error(f"Error verifying project state: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    def get_clean_data_summary(self) -> Dict[str, Any]:
        """Get summary of the cleaned data."""
        try:
            clean_data_file = self.processing_dir / "clean_copperlab_data.json"
            if not clean_data_file.exists():
                return {
                    "status": "failed",
                    "error": f"Clean data file not found: {clean_data_file}"
                }

            with open(clean_data_file, 'r') as f:
                data = json.load(f)

            return {
                "status": "success",
                "total_subjects": len(data.get("subjects", [])),
                "total_experiments": len(data.get("experiments", [])),
                "metadata": data.get("metadata", {}),
                "subjects_preview": data.get("subjects", [])[:5],  # First 5 subjects
                "experiments_preview": data.get("experiments", [])[:5],  # First 5 experiments
            }

        except Exception as e:
            logger.error(f"Error reading clean data: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    # -------------------------------
    # Project-level actions (modern API)
    # -------------------------------
    def supported_project_actions(self) -> List[str]:
        """Supported project-level actions."""
        return [
            "run_full_pipeline",
            "run_pipeline_clean",
            "run_pipeline_ingest",
            "run_pipeline_verify",
            "verify_project_state",
            "get_clean_data_summary",
            "parse_experiments_csv",
            "extract_subjects_from_csv",
            "validate_csv_data",
            "create_experiments_from_csv",
        ]

    def run_action(self, action: str, params: Dict[str, Any], project_manager) -> Dict[str, Any]:
        """Execute project-level actions."""
        try:
            if action == "run_full_pipeline":
                return self.run_pipeline_command()
            elif action == "run_pipeline_clean":
                return self.run_pipeline_command(["clean"])
            elif action == "run_pipeline_ingest":
                return self.run_pipeline_command(["ingest"])
            elif action == "run_pipeline_verify":
                return self.run_pipeline_command(["verify"])
            elif action == "verify_project_state":
                project_path = params.get("project_path")
                if not project_path:
                    return {"status": "failed", "error": "project_path parameter required"}
                expected_subjects = params.get("expected_subjects")
                expected_experiments = params.get("expected_experiments")
                return self.verify_project_state(
                    Path(project_path),
                    expected_subjects,
                    expected_experiments
                )
            elif action == "get_clean_data_summary":
                return self.get_clean_data_summary()
            # Legacy actions for backward compatibility
            elif action == "parse_experiments_csv":
                return self._parse_experiments_csv(params)
            elif action == "extract_subjects_from_csv":
                return self._extract_subjects_from_csv(params, project_manager)
            elif action == "validate_csv_data":
                return self._validate_csv_data(params)
            elif action == "create_experiments_from_csv":
                return self._create_experiments_from_csv(params, project_manager)
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
            df = pd.read_csv(csv_path, encoding="utf-8", errors="ignore")
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
        for col in row:
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
            df = pd.read_csv(csv_path, encoding="utf-8", errors="ignore")
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
        for col in row:
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
            df = pd.read_csv(csv_path, encoding="utf-8", errors="ignore")
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
                    errors.append(f"Row {idx}: Invalid subject ID '{subject_id}'")

            # Validate experiment type
            if "experiment_type" in df.columns:
                exp_type = str(row.get("experiment_type", "")).strip()
                if exp_type and exp_type not in self.EXPERIMENT_TYPE_MAPPING.values():
                    warnings.append(f"Row {idx}: Unknown experiment type '{exp_type}'")

            # Validate date
            if "date" in df.columns:
                date_str = str(row.get("date", "")).strip()
                if date_str and not self._parse_date_manual(date_str):
                    errors.append(f"Row {idx}: Invalid date format '{date_str}'")

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

                    project_manager.add_subject(
                        subject_id=subject_data["id"],
                        sex=sex_enum,
                        birth_date=subject_data.get("birth_date"),
                        genotype=subject_data.get("genotype"),
                        treatment=subject_data.get("treatment")
                    )

                    approved_subjects.append(subject_data)
                except Exception as e:
                    logger.error(f"Failed to create subject {subject_data['id']}: {e}")

        return {
            "status": "success",
            "approved_subjects": approved_subjects,
            "count": len(approved_subjects)
        }

    # ---------------------------------------------------------------------
    # CLI Interface
    # ---------------------------------------------------------------------

    @staticmethod
    def main():
        """CLI entry point for the Copperlab plugin."""
        parser = argparse.ArgumentParser(
            description="Copperlab Assembly Plugin - Process and import Copperlab data into MUS1"
        )
        parser.add_argument(
            "action",
            choices=["pipeline", "clean", "ingest", "verify", "summary", "help"],
            help="Action to perform"
        )
        parser.add_argument(
            "--project-path",
            type=str,
            help="Path to MUS1 project for verification"
        )
        parser.add_argument(
            "--expected-subjects",
            type=int,
            help="Expected number of subjects for verification"
        )
        parser.add_argument(
            "--expected-experiments",
            type=int,
            help="Expected number of experiments for verification"
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Set logging level"
        )

        args = parser.parse_args()

        # Set up logging
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Create plugin instance
        plugin = CopperlabAssembly()

        try:
            if args.action == "pipeline":
                logger.info("Running complete Copperlab data processing pipeline...")
                result = plugin.run_pipeline_command()
            elif args.action == "clean":
                logger.info("Running data cleaning step...")
                result = plugin.run_pipeline_command(["clean"])
            elif args.action == "ingest":
                logger.info("Running data ingestion step...")
                result = plugin.run_pipeline_command(["ingest"])
            elif args.action == "verify":
                if not args.project_path:
                    logger.error("--project-path required for verification")
                    sys.exit(1)
                logger.info(f"Verifying project state at {args.project_path}...")
                result = plugin.verify_project_state(
                    Path(args.project_path),
                    args.expected_subjects,
                    args.expected_experiments
                )
            elif args.action == "summary":
                logger.info("Getting clean data summary...")
                result = plugin.get_clean_data_summary()
            elif args.action == "help":
                parser.print_help()
                sys.exit(0)

            # Print result
            if result["status"] == "success":
                print(f"✅ {result.get('message', 'Operation completed successfully')}")
                if "stdout" in result:
                    print("\nOutput:")
                    print(result["stdout"])
                if "total_subjects" in result:
                    print("\n📊 Summary:")
                    print(f"  Subjects: {result['total_subjects']}")
                    print(f"  Experiments: {result['total_experiments']}")
            else:
                print(f"❌ Operation failed: {result.get('error', 'Unknown error')}")
                if "stderr" in result and result["stderr"]:
                    print("\nError output:")
                    print(result["stderr"])
                sys.exit(1)

        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            sys.exit(1)


# CLI entry point
if __name__ == "__main__":
    CopperlabAssembly.main()


# End of CopperlabAssembly plugin implementation
