"""Typer-based MUS1 command-line interface (experimental).

Provides:
    mus1 scan videos …       – walk roots and stream (path, hash) JSON lines
    mus1 scan dedup …        – deduplicate list / stdin adding start_time
    mus1 project add-videos  – register unassigned videos into a project

This CLI intentionally has *no* additional business logic – it delegates to
DataManager and ProjectManager so GUI and CLI share one code path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional, Iterable

import typer
from rich import print  # pretty help & errors
from tqdm import tqdm

from .core.state_manager import StateManager
from .core.plugin_manager import PluginManager
from .core.data_manager import DataManager
from .core.project_manager import ProjectManager
from .core.logging_bus import LoggingEventBus

app = typer.Typer(add_completion=False, rich_markup_mode="rich")
scan_app = typer.Typer(help="Video discovery utilities")
project_app = typer.Typer(help="Project-level operations")

app.add_typer(scan_app, name="scan")
app.add_typer(project_app, name="project")

###############################################################################
# Shared helpers
###############################################################################


def _init_managers() -> tuple[StateManager, PluginManager, DataManager, ProjectManager]:
    state_manager = StateManager()
    plugin_manager = PluginManager()
    data_manager = DataManager(state_manager, plugin_manager)
    project_manager = ProjectManager(state_manager, plugin_manager, data_manager)
    return state_manager, plugin_manager, data_manager, project_manager


def _iter_json_lines(stream) -> Iterable[dict]:
    """Yield dicts from JSON-lines *stream*."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            # Skip any non-JSON noise (e.g., logs/progress) that might leak to stdout
            continue

###############################################################################
# scan videos
###############################################################################


@scan_app.command("videos")
def scan_videos(
    roots: List[Path] = typer.Argument(..., help="Directories or drive roots to scan"),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, help="Disable recursive traversal"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON lines file (default: stdout)"),
    progress: bool = typer.Option(True, help="Show progress bar (default: true if interactive)"),
    min_size: Optional[int] = typer.Option(None, help="Minimum file size in bytes"),
    max_age: Optional[int] = typer.Option(None, help="Maximum age in days"),
):
    """Recursively scan *roots* for video files and stream JSON lines (path, hash)."""
    _, _, data_manager, _ = _init_managers()
    video_iter = data_manager.discover_video_files(
        roots,
        extensions=extensions,
        recursive=not non_recursive,
        excludes=exclude_dirs,
    )
    # Materialise to know total for progress bar
    all_items = list(video_iter)
    pbar = tqdm(total=len(all_items), desc="Hashing", unit="file")

    def _cb(done: int, total: int):
        pbar.update(1)

    for path, hsh in data_manager.discover_video_files(
        roots,
        extensions=extensions,
        recursive=not non_recursive,
        excludes=exclude_dirs,
        progress_cb=_cb,
    ):
        out = {"path": str(path), "hash": hsh}
        if output:
            with open(output, "a") as f:
                f.write(json.dumps(out) + "\n")
        else:
            print(json.dumps(out))
    pbar.close()

###############################################################################
# scan dedup
###############################################################################


@scan_app.command("dedup")
def scan_dedup(
    input_file: Optional[Path] = typer.Argument(
        None,
        metavar="[FILE|-]",
        help="Video list JSON lines. Omit or '-' for stdin.",
    )
):
    """Remove duplicate hashes and attach start_time (ISO-8601)."""
    _, _, data_manager, _ = _init_managers()

    source_iter = _iter_json_lines(sys.stdin if input_file in (None, Path("-")) else open(input_file, "r", encoding="utf-8"))
    tuples: List[tuple[Path, str]] = []
    for entry in source_iter:
        path = Path(entry["path"])
        hsh = entry["hash"]
        tuples.append((path, hsh))

    pbar = tqdm(total=len(tuples), desc="Dedup", unit="file")
    def _cb(done: int, total: int):
        pbar.update(1)

    for path, hsh, start_time in data_manager.deduplicate_video_list(tuples, progress_cb=_cb):
        out = {"path": str(path), "hash": hsh, "start_time": start_time.isoformat()}
        print(json.dumps(out))
    pbar.close()

###############################################################################
# project add-videos
###############################################################################


@project_app.command("add-videos")
def add_videos(
    project_path: Path = typer.Argument(..., help="Existing or new MUS1 project directory"),
    video_list: Path = typer.Argument(..., metavar="LIST|-", help="JSON-lines list or '-' for stdin"),
    assign: bool = typer.Option(False, help="Immediately assign videos to experiments based on metadata (placeholder)"),
):
    """Register unassigned videos in *project* from JSON lines produced by scan pipeline."""
    state_manager, _, data_manager, project_manager = _init_managers()

    # (1) resolve project path to default projects dir if not absolute/exists
    if not project_path.is_absolute() and not project_path.exists():
        default_dir = project_manager.get_projects_directory()
        candidate = default_dir / project_path
        project_path = candidate

    # load or create project
    if project_path.exists():
        project_manager.load_project(project_path)
    else:
        project_manager.create_project(project_path, project_path.name)
    # configure rotating log inside project folder
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)

    # (2) read list
    stream = sys.stdin if video_list == Path("-") else open(video_list, "r", encoding="utf-8")
    records = list(_iter_json_lines(stream))
    video_iter = (
        (Path(rec["path"]), rec["hash"], data_manager._extract_start_time(Path(rec["path"])))
        for rec in records
    )

    # (3) register
    project_manager.register_unlinked_videos(video_iter)
    print(f"Added videos to project '{project_path}'. Current unassigned count: {len(state_manager.project_state.unassigned_videos)}")

    if assign:
        # Placeholder for auto-assignment logic
        print("Auto-assignment is a placeholder for now.")

###############################################################################
# project list
###############################################################################


@project_app.command("list")
def list_projects(
    base_dir: Optional[Path] = typer.Option(None, help="Base directory to search for projects (default: standard location)"),
):
    """List available MUS1 projects on this machine."""
    _, _, _, project_manager = _init_managers()
    if base_dir:
        projects = project_manager.list_available_projects(base_dir)
    else:
        projects = project_manager.list_available_projects()
    if not projects:
        print("No MUS1 projects found.")
    else:
        print("Available MUS1 projects:")
        for proj in projects:
            print(f"- {proj.name} ({proj})")

###############################################################################
# project create
###############################################################################


@project_app.command("create")
def create_project(
    name: str = typer.Argument(..., help="Project name (folder name) or absolute path"),
    location: str = typer.Option("local", help="Where to create the project: local|shared|server (server is placeholder)", show_default=True),
    base_dir: Optional[Path] = typer.Option(None, help="Override base directory for local projects"),
    shared_root: Optional[Path] = typer.Option(None, help="Root directory for shared projects (or set MUS1_SHARED_DIR)"),
):
    """Create a new MUS1 project locally or on a shared location (server placeholder)."""
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()

    # Resolve destination path
    target_path: Path
    if location.lower() == "local":
        projects_dir = project_manager.get_projects_directory(base_dir)
        target_path = projects_dir / name
    elif location.lower() == "shared":
        root = shared_root or Path(typer.get_app_dir("mus1_shared_root_fallback"))  # placeholder if env not set
        env_shared = Path((typer.get_app_dir("mus1_shared_root_env_unused") or "."))  # no-op
        env_var = typer.get_app_dir("mus1_shared_root_env_unused_again")  # no-op
        # Prefer env MUS1_SHARED_DIR if set
        import os
        env = os.environ.get("MUS1_SHARED_DIR")
        if env:
            root = Path(env).expanduser()
        if not shared_root and not env:
            raise typer.BadParameter("Provide --shared-root or set MUS1_SHARED_DIR for shared location")
        target_path = Path(root).expanduser() / name
    elif location.lower() == "server":
        print("Server project creation is a placeholder. Create locally and sync via your workflow.")
        projects_dir = project_manager.get_projects_directory(base_dir)
        target_path = projects_dir / name
    else:
        raise typer.BadParameter("location must be one of: local, shared, server")

    if target_path.exists():
        print(f"Path already exists: {target_path}")
        raise typer.Exit(code=1)

    project_manager.create_project(target_path, name)
    print(f"Created project at: {target_path}")

###############################################################################
# Entrypoint
###############################################################################


def run():  # called by __main__.py
    app()
