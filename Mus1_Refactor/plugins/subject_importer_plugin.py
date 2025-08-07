import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import inspect

from .base_plugin import BasePlugin
from ..core.project_manager import ProjectManager
from ..core.metadata import PluginMetadata, ProjectState, ExperimentMetadata

logger = logging.getLogger(__name__)

class SubjectImporterPlugin(BasePlugin):
    """
    A plugin to import subjects in bulk from a CSV file into a project.
    This action affects the project's list of subjects.
    """

    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="SubjectImporter",
            date_created=datetime.now(),
            version="1.0",
            description="Imports a list of subjects from a specified CSV file.",
            author="AI Assistant",
            supported_experiment_types=[],
            readable_data_formats=[],
            analysis_capabilities=['import_subjects'],
            plugin_type="importer"
        )

    def analysis_capabilities(self) -> List[str]:
        return self.plugin_self_metadata().analysis_capabilities or []

    def readable_data_formats(self) -> List[str]:
        return []

    def required_fields(self) -> List[str]:
        return ['subjects_csv_path']

    def optional_fields(self) -> List[str]:
        return []

    def get_field_types(self) -> Dict[str, str]:
        return {'subjects_csv_path': 'file'}

    def get_field_descriptions(self) -> Dict[str, str]:
        return {'subjects_csv_path': 'Path to the CSV file containing subject information.'}

    def validate_parameters(self, params: Dict[str, Any]) -> None:
        """ Validates the parameters provided specifically for this plugin's action. """
        plugin_name = self.plugin_self_metadata().name
        if 'subjects_csv_path' not in params or not params['subjects_csv_path']:
            raise ValueError(f"{plugin_name}: Missing required parameter 'subjects_csv_path'.")

        file_path = Path(params['subjects_csv_path'])
        if not file_path.is_file():
            raise ValueError(f"{plugin_name}: Provided 'subjects_csv_path' is not a valid file: {file_path}")
        if file_path.suffix.lower() != '.csv':
            raise ValueError(f"{plugin_name}: 'subjects_csv_path' must be a CSV file (.csv).")

    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """
        Placeholder. This importer plugin does not validate specific experiments.
        """
        logger.debug(f"validate_experiment called on importer plugin '{self.plugin_self_metadata().name}', but it does not operate on specific experiments. Passing.")
        pass

    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: 'DataManager', capability: str) -> Dict[str, Any]:
        """
        Placeholder. Importer plugins should use run_import, not analyze_experiment.
        """
        plugin_name = self.plugin_self_metadata().name
        error_msg = f"'analyze_experiment' is not applicable to the importer plugin '{plugin_name}'. Use 'run_project_level_plugin_action' instead."
        logger.error(error_msg)
        return {"status": "failed", "capability_executed": capability, "error": error_msg}

    def run_import(self, params: Dict[str, Any], project_manager: ProjectManager) -> Dict[str, Any]:
        """
        Executes the subject import process.
        """
        plugin_name = self.plugin_self_metadata().name
        logger.info(f"Running import capability for {plugin_name}...")
        
        try:
            self.validate_parameters(params)

            # Ensure a project is currently open so subjects can be persisted.
            if not getattr(project_manager, "_current_project_root", None):
                raise RuntimeError("No project is currently open. Please create or load a project before importing subjects.")

            csv_path = params['subjects_csv_path']
            
            try:
                df = pd.read_csv(csv_path, dtype={"subject_id": str})
                if 'subject_id' not in df.columns:
                    raise ValueError("CSV must contain a 'subject_id' column.")
                df['subject_id'] = df['subject_id'].astype(str)
                df['subject_id'] = df['subject_id'].apply(lambda x: x.zfill(3) if x.isdigit() and len(x) < 3 else x)
            except Exception as e:
                logger.error(f"Failed to read or parse CSV file at {csv_path}: {e}")
                raise IOError(f"Failed to read or parse CSV file at {csv_path}: {e}")

            added_count = 0
            skipped_count = 0
            existing_subject_ids = set(project_manager.state_manager.project_state.subjects.keys())

            for index, row in df.iterrows():
                subject_id = str(row.get('subject_id', '')).strip()
                if not subject_id or subject_id.lower() == 'nan':
                    logger.warning(f"Skipping row {index+2} with missing or invalid subject_id.")
                    skipped_count += 1
                    continue

                if subject_id in existing_subject_ids:
                    skipped_count += 1
                    continue
                
                try:
                    subject_args = row.to_dict()
                    clean_args = {k: None if pd.isna(v) else v for k, v in subject_args.items()}
                    
                    # Ensure notes is an empty string instead of None so that pydantic validation passes
                    if clean_args.get('notes') is None:
                        clean_args['notes'] = ""
                    
                    for date_col in ['birth_date', 'death_date']:
                        if date_col in clean_args and clean_args[date_col]:
                             try:
                                 clean_args[date_col] = pd.to_datetime(clean_args[date_col]).to_pydatetime()
                             except (ValueError, TypeError):
                                 logger.warning(f"Could not parse date '{clean_args[date_col]}' for subject '{subject_id}'. Setting to None.")
                                 clean_args[date_col] = None
                    
                    valid_params = inspect.signature(project_manager.add_subject).parameters
                    final_args = {k: v for k, v in clean_args.items() if k in valid_params}
                    
                    project_manager.add_subject(**final_args)
                    
                    added_count += 1
                    existing_subject_ids.add(subject_id)
                except Exception as e:
                    logger.error(f"Error processing subject '{subject_id}' on row {index+2}: {e}")
                    skipped_count += 1
            
            # After processing all subjects, register any new genotypes found in the CSV
            if 'genotype' in df.columns:
                unique_genotypes = set(df['genotype'].dropna().astype(str).str.strip())
                # Remove blanks / empty strings
                unique_genotypes = {g for g in unique_genotypes if g}
                for genotype_name in unique_genotypes:
                    try:
                        project_manager.add_genotype(genotype_name)
                    except ValueError:
                        # Genotype already exists – ignore
                        pass
                    except RuntimeError as e:
                        logger.warning(f"Could not add genotype '{genotype_name}': {e}")

            message = f"Subject import complete. Added: {added_count}, Skipped (existing or errors): {skipped_count}"
            logger.info(message)
            return {"status": "success", "message": message, "added_count": added_count, "skipped_count": skipped_count}

        except (ValueError, IOError, Exception) as e:
            logger.error(f"Error during subject import ({plugin_name}): {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    def get_style_manifest(self) -> Optional[Dict[str, Any]]:
        return None