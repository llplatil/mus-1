from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from mus1.core.app_initializer import initialize_mus1_app


def run_import(copperlab_csv_dir: Path, project_path: Path) -> Dict[str, Any]:
    copperlab_csv_dir = copperlab_csv_dir.expanduser().resolve()
    project_path = project_path.expanduser().resolve()

    if not copperlab_csv_dir.exists() or not copperlab_csv_dir.is_dir():
        return {"status": "failed", "error": f"CSV directory not found: {copperlab_csv_dir}"}

    _state, plugin_manager, _dm, project_manager, _theme, _log = initialize_mus1_app()

    if not project_path.exists():
        project_manager.create_project(project_path, project_path.name)
    else:
        project_manager.load_project(project_path)

    # Find plugin
    candidates = plugin_manager.get_plugins_with_project_actions()
    plugin_name = None
    for p in candidates:
        if p.plugin_self_metadata().name == "CopperlabAssembly":
            plugin_name = "CopperlabAssembly"
            break
    if not plugin_name:
        return {"status": "failed", "error": "CopperlabAssembly plugin not found"}

    # 1) Extract subjects
    subjects_res = project_manager.run_project_level_plugin_action(
        plugin_name, "extract_subjects_from_csv", {"csv_dir": str(copperlab_csv_dir)}
    )
    if subjects_res.get("status") != "success":
        return subjects_res

    subjects: List[Dict[str, Any]] = subjects_res.get("subjects", [])

    # Approve all subjects
    approve_res = project_manager.run_project_level_plugin_action(
        plugin_name,
        "approve_subjects",
        {"subjects_data": subjects, "subject_ids": [s["id"] for s in subjects]},
    )
    if approve_res.get("status") != "success":
        return approve_res

    # 2) Parse experiments for each CSV in the folder and aggregate
    experiments: List[Dict[str, Any]] = []
    for csv_file in copperlab_csv_dir.glob("*.csv"):
        parse_res = project_manager.run_project_level_plugin_action(
            plugin_name, "parse_experiments_csv", {"csv_path": str(csv_file)}
        )
        if parse_res.get("status") == "success":
            experiments.extend(parse_res.get("experiments", []))

    # 3) Create experiments (planned; subjects must exist)
    create_res = project_manager.run_project_level_plugin_action(
        plugin_name, "create_experiments_from_csv", {"experiments_data": experiments}
    )
    if create_res.get("status") != "success":
        return create_res

    return {
        "status": "success",
        "subjects_added": approve_res.get("count", 0),
        "experiments_created": create_res.get("count", 0),
        "project": str(project_path),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import Copperlab CSV data into MUS1 project")
    parser.add_argument("csv_dir", type=Path, help="Path to copperlab_csv_all directory")
    parser.add_argument("project_path", type=Path, help="Path to target MUS1 project (will be created if missing)")
    args = parser.parse_args()

    result = run_import(args.csv_dir, args.project_path)
    print(json.dumps(result))

