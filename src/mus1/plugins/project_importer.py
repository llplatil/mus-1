from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

from .base_plugin import BasePlugin
from ..core.metadata import Experiment, ProjectConfig, PluginMetadata


class ProjectImporterPlugin(BasePlugin):
    """Default MUS1 plugin for importing existing MUS1 projects to labs they were not previously associated with.

    This is a core MUS1 plugin that provides project-level actions to import/link
    data from another MUS1 project into the active project's lab scope. Focuses on
    enabling cross-lab project movement while maintaining data integrity.
    """

    def plugin_self_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="project_importer",
            date_created=datetime.now(),
            version="0.1.0",
            description="Default MUS1 plugin for importing existing MUS1 projects to labs they were not previously associated with",
            author="MUS1",
            plugin_type="importer",
            supported_experiment_types=[],
            readable_data_formats=[],
            analysis_capabilities=[],
        )

    def readable_data_formats(self) -> List[str]:
        # Not data-format driven; project-level actions only
        return []

    def analysis_capabilities(self) -> List[str]:
        # No experiment-level analysis in this plugin
        return []

    def required_fields(self) -> List[str]:
        """Fields required for this importer plugin."""
        return ["source_project_path"]

    def optional_fields(self) -> List[str]:
        """Optional fields for this importer plugin."""
        return ["target_lab_id", "import_subjects", "import_experiments"]

    def supported_project_actions(self) -> List[str]:
        return [
            "import_project_metadata",
            "link_project_videos",
        ]

    def run_action(self, action: str, params: Dict[str, Any], project_manager: 'ProjectManagerClean') -> Dict[str, Any]:
        try:
            if action == "import_project_metadata":
                src_path = Path(params.get("source_project_path", ""))
                if not src_path or not (src_path / "project.json").exists():
                    return {"status": "failed", "error": "Invalid source_project_path"}
                # For now, just report success with a stub; wire detailed import later
                return {"status": "success", "message": f"Validated source project at {src_path}"}

            if action == "link_project_videos":
                src_path = Path(params.get("source_project_path", ""))
                if not src_path or not (src_path / "mus1.db").exists():
                    return {"status": "failed", "error": "Invalid source_project_path"}
                # Stub: no-op linking placeholder
                return {"status": "success", "message": f"Ready to link videos from {src_path}"}

            return {"status": "failed", "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # Experiment-level methods are not used for this plugin
    def validate_experiment(self, experiment: Experiment, project_config: ProjectConfig) -> None:  # pragma: no cover
        return

    def analyze_experiment(self, experiment: Experiment, plugin_service: 'PluginService', capability: str, project_config: ProjectConfig) -> Dict[str, Any]:  # pragma: no cover
        return {"status": "failed", "error": "Not supported", "capability_executed": capability}


