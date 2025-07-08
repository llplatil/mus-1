import logging
from pathlib import Path
import yaml
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

# Need access to ProjectManager to update state and potentially call other plugins
from ..core.project_manager import ProjectManager
from ..core.data_manager import DataManager  # for type annotation
from ..core.metadata import SubjectMetadata, Sex, ExperimentMetadata, PluginMetadata, ProjectState
from .base_plugin import BasePlugin
# DataManager might not be directly needed here if the Handler does all the reading
# from core.data_manager import DataManager

logger = logging.getLogger(__name__)

# Constants for clarity
HANDLER_PLUGIN_NAME = "DeepLabCutHandler"
HANDLER_CAPABILITY_EXTRACT_BODYPARTS = "extract_bodyparts"
HANDLER_PARAM_CONFIG_PATH = "config_file_path" # Param name expected by the Handler

class DlcProjectImporterPlugin(BasePlugin):
    """
    Imports configuration (primarily body parts) from an existing DeepLabCut project
    into the current MUS1 project by leveraging the DeepLabCutHandlerPlugin.
    This action affects the project's master list of body parts.
    """

    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="DlcProjectImporter",
            date_created=datetime.now(),
            version="0.2",
            description="Imports body parts from a DeepLabCut config.yaml into the project's master list.",
            author="Your Name / AI Assistant",
            supported_experiment_types=[],
            readable_data_formats=[],
            analysis_capabilities=['import_dlc_project_settings'], # Defines its action
            plugin_type="importer"
        )

    def analysis_capabilities(self) -> List[str]:
        return self.plugin_self_metadata().analysis_capabilities or []

    def readable_data_formats(self) -> List[str]:
        return [] # Orchestrates, doesn't read formats itself

    # --- Fields required by THIS plugin's capability ---
    def required_fields(self) -> List[str]:
        # This is the parameter the UI needs to collect for *this* plugin's action
        return ['dlc_project_config_path']

    def optional_fields(self) -> List[str]:
        return []

    def get_field_types(self) -> Dict[str, str]:
        return {
            'dlc_project_config_path': 'file' # UI uses file browser
        }

    def get_field_descriptions(self) -> Dict[str, str]:
        return {
            'dlc_project_config_path': 'Path to the main config.yaml file of the DeepLabCut project to import body parts from.'
        }

    # --- Validation (May need adaptation for project-level actions) ---
    def validate_parameters(self, params: Dict[str, Any]) -> None:
        """ Validates the parameters provided specifically for this plugin's action. """
        plugin_name = self.plugin_self_metadata().name
        if 'dlc_project_config_path' not in params or not params['dlc_project_config_path']:
            raise ValueError(f"{plugin_name}: Missing required parameter 'dlc_project_config_path'.")

        config_path = Path(params['dlc_project_config_path'])
        if not config_path.is_file():
             raise ValueError(f"{plugin_name}: Provided 'dlc_project_config_path' is not a valid file: {config_path}")
        if config_path.suffix.lower() not in ['.yaml', '.yml']:
             raise ValueError(f"{plugin_name}: 'dlc_project_config_path' must be a YAML file (.yaml or .yml).")

    # --- ADDED Implementation for Abstract Method ---
    def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
        """
        Placeholder implementation for BasePlugin abstract method.
        This importer plugin does not validate specific experiments.
        """
        logger.debug(f"validate_experiment called on importer plugin '{self.plugin_self_metadata().name}', but it does not operate on specific experiments. Passing.")
        pass # No experiment-specific validation needed for an importer

    # --- ADDED Implementation for Abstract Method ---
    def analyze_experiment(self, experiment: ExperimentMetadata, data_manager: DataManager, capability: str) -> Dict[str, Any]:
        """
        Placeholder implementation for BasePlugin abstract method.
        Importer plugins should use run_import, not analyze_experiment.
        """
        plugin_name = self.plugin_self_metadata().name
        error_msg = f"'analyze_experiment' is not applicable to the importer plugin '{plugin_name}'. Use 'run_project_level_plugin_action' instead."
        logger.error(error_msg)
        return {
            "status": "failed",
            "capability_executed": capability,
            "error": error_msg
        }

    # --- Execution Logic ---
    # This method is intended to be called by the ProjectManager when the user initiates
    # the 'import_dlc_project_settings' action from the UI.
    def run_import(self, params: Dict[str, Any], project_manager: ProjectManager) -> Dict[str, Any]:
         """
         Executes the import process. Assumes parameters are passed in `params`
         and access to ProjectManager is provided.

         Args:
             params: Dictionary containing parameters collected from the user (e.g., {'dlc_project_config_path': '...'}).
             project_manager: The instance of the ProjectManager orchestrating the action.

         Returns:
             A dictionary indicating success or failure and potentially the imported data.
         """
         plugin_name = self.plugin_self_metadata().name
         logger.info(f"Running import capability for {plugin_name}...")

         try:
             # 1. Validate parameters specific to this importer
             self.validate_parameters(params)
             dlc_config_path = params['dlc_project_config_path']
             logger.info(f"Using DLC config path: {dlc_config_path}")

             # 2. Load config.yaml directly to separate unique vs multianimal bodyparts
             with open(dlc_config_path, 'r') as cf:
                 cfg = yaml.safe_load(cf)

             unique_parts = cfg.get('uniquebodyparts', []) or []
             multi_parts = cfg.get('multianimalbodyparts', []) or []
             shared_parts = cfg.get('sharedbodyparts', []) or []

             # Ensure lists are flattened and free of None/empty
             unique_parts = [str(p).strip() for p in unique_parts if str(p).strip()]
             bodyparts_for_master = [str(p).strip() for p in (multi_parts + shared_parts) if str(p).strip()]

             logger.info(f"Config lists → unique_objects={unique_parts}, bodyparts={bodyparts_for_master}")

             # 2a. Add objects (unique bodyparts) to master tracked objects
             added_objects = []
             for obj_name in unique_parts:
                 try:
                     project_manager.add_tracked_object(obj_name)
                     added_objects.append(obj_name)
                 except ValueError:
                     # Already exists – ignore
                     pass

             # 2b. Add multi-animal bodyparts to master body-parts list
             if bodyparts_for_master:
                 if not project_manager.update_master_body_parts(bodyparts_for_master):
                     raise RuntimeError("Failed to update master body parts list.")

             extracted_bodyparts = bodyparts_for_master # for reporting

             # 3. Add subjects based on the 'individuals' field in config.yaml (cfg already loaded)
             logger.info("Creating subjects from 'individuals' list in config.yaml ...")
             individuals = cfg.get('individuals', [])
             added_subjects = []
             for subj_id in individuals:
                 subj_id = str(subj_id).strip()
                 if not subj_id:
                     continue
                 try:
                     project_manager.add_subject(subject_id=subj_id, in_training_set=True)
                     added_subjects.append(subj_id)
                 except ValueError:
                     # Already exists – skip
                     pass

             # 4. Add experiments from video_sets entries
             logger.info("Creating experiments from 'video_sets' entries …")
             video_sets: dict = cfg.get('video_sets', {})
             added_experiments = []
             for video_path_str in video_sets.keys():
                 base_name = Path(video_path_str).stem  # e.g., '689 fam_t1'
                 parts = base_name.replace('-', ' ').replace('_', ' ').split()
                 if not parts:
                     continue
                 subj_candidate = parts[0]
                 if not subj_candidate.isdigit():
                     logger.warning(f"Could not parse subject ID from video name '{base_name}', skipping experiment import.")
                     continue
                 subject_id = subj_candidate
                 # Determine session label (fam/nov/etc.) and timepoint if present
                 session_label = None
                 timepoint = None
                 for token in parts[1:]:
                     tl = token.lower()
                     if tl in ("fam", "nov", "fam_t1", "nov_t1"):
                         session_label = tl.split('_')[0]
                     if tl.startswith('t') and len(tl) > 1 and tl[1:].isdigit():
                         timepoint = tl
                 exp_type = session_label or 'unknown'
                 experiment_id = base_name  # unique enough

                 # Build plugin params for DLC handler
                 handler_params = {
                     'config_file_path': dlc_config_path
                 }
                 # Attempt to locate a tracking CSV/H5 next to video
                 candidate_csv = Path(video_path_str).with_suffix(".csv")
                 candidate_h5 = Path(video_path_str).with_suffix(".h5")
                 if candidate_csv.exists():
                     handler_params['tracking_file_path'] = str(candidate_csv)
                 elif candidate_h5.exists():
                     handler_params['tracking_file_path'] = str(candidate_h5)

                 plugin_params_nested = {HANDLER_PLUGIN_NAME: handler_params}

                 # Pick processing stage: recorded (video) or tracked if we found tracking file
                 processing_stage = 'tracked' if 'tracking_file_path' in handler_params else 'recorded'

                 try:
                     project_manager.add_experiment(
                         experiment_id=experiment_id,
                         subject_id=subject_id,
                         date_recorded=datetime.now(),
                         exp_type=exp_type,
                         processing_stage=processing_stage,
                         associated_plugins=[HANDLER_PLUGIN_NAME],
                         plugin_params=plugin_params_nested
                     )
                     added_experiments.append(experiment_id)
                 except ValueError as ve:
                     logger.warning(f"Skipping experiment '{experiment_id}': {ve}")

             message = (
                 f"Import complete. Added {len(added_subjects)} new subjects, {len(added_experiments)} new experiments, "
                 f"{len(bodyparts_for_master)} body parts, and {len(added_objects)} tracked objects."
             )
             logger.info(message)
             return {
                 "status": "success",
                 "message": message,
                 "imported_bodyparts": bodyparts_for_master,
                 "imported_objects": added_objects,
                 "added_subjects": added_subjects,
                 "added_experiments": added_experiments
             }

         except (ValueError, RuntimeError, NotImplementedError, Exception) as e:
             logger.error(f"Error during DLC project import ({plugin_name}): {e}", exc_info=True) # Include traceback for debugging
             return {"status": "failed", "error": str(e)}

    # --- Optional BasePlugin Methods ---
    def get_style_manifest(self) -> Optional[Dict[str, Any]]:
        return None

    # --- Compatibility with analyze_experiment (if needed) ---
    # If we MUST use analyze_experiment, it needs modification to accept
    # project_manager and potentially None for experiment/data_manager.
    # Example:
    # def analyze_experiment(self, experiment: Optional[Any], data_manager: Optional[DataManager], capability: str, params: Dict[str, Any], project_manager: ProjectManager) -> Dict[str, Any]:
    #      if capability == 'import_dlc_project_settings':
    #          # Note: We might need to fetch params differently if not passed directly
    #          actual_params = params # Or fetch from experiment.plugin_params[self.plugin_self_metadata().name]? Needs clarification how UI passes params for importers.
    #          return self.run_import(actual_params, project_manager)
    #      else:
    #          raise ValueError(f"Unknown capability: {capability}") 