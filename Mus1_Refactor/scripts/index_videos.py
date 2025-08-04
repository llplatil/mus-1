import argparse
from pathlib import Path
import os
import re
import sys
from datetime import datetime

# Adjust sys.path to import from core
sys.path.append(str(Path(__file__).parent.parent))

from core.state_manager import StateManager
from core.plugin_manager import PluginManager
from core.data_manager import DataManager
from core.project_manager import ProjectManager

def parse_video_filename(filename):
    # Assume pattern: subjectID_expname.ext (e.g., 689_fam_t1.avi)
    match = re.match(r'(\d{3})_(\w+)', filename.stem)
    if match:
        return match.group(1), match.group(2)
    return None, None

def main():
    parser = argparse.ArgumentParser(description="Index and link videos to Mus1 project")
    parser.add_argument('project_path', help="Path to Mus1 project directory")
    parser.add_argument('scan_dir', help="Directory to scan for videos")
    args = parser.parse_args()

    # Init managers
    state_manager = StateManager()
    plugin_manager = PluginManager()
    data_manager = DataManager(state_manager, plugin_manager)
    project_manager = ProjectManager(state_manager, plugin_manager, data_manager)

    # Load project
    project_manager.load_project(Path(args.project_path))

    # Supported extensions
    video_exts = {'.mp4', '.avi', '.mov'}

    linked = 0
    for root, dirs, files in os.walk(args.scan_dir):
        for file in files:
            path = Path(root) / file
            if path.suffix.lower() in video_exts:
                subject_id, exp_name = parse_video_filename(path)
                if not subject_id or not exp_name:
                    print(f"Skipping {file}: could not parse filename")
                    continue

                # Add subject if not exists
                if subject_id not in state_manager.project_state.subjects:
                    project_manager.add_subject(subject_id=subject_id)

                # Create exp_id
                exp_id = f"{subject_id}_{exp_name}"

                # Add experiment if not exists
                if exp_id not in state_manager.project_state.experiments:
                    # Get file creation time for date_recorded
                    creation_time = datetime.fromtimestamp(path.stat().st_ctime)
                    project_manager.add_experiment(
                        experiment_id=exp_id,
                        subject_id=subject_id,
                        date_recorded=creation_time,
                        exp_type="OpenField",  # TODO: infer better
                        processing_stage="recorded",
                        associated_plugins=[],
                        plugin_params={},
                    )

                # Link video
                project_manager.link_video_to_experiment(experiment_id=exp_id, video_path=path)
                linked += 1

    project_manager.save_project()
    print(f"Linked {linked} videos to the project.")

if __name__ == "__main__":
    main() 