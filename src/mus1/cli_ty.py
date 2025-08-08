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
        yield json.loads(line)

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

    # (1) load or create project
    if project_path.exists():
        project_manager.load_project(project_path)
    else:
        project_manager.create_project(project_path, project_path.name)
    # configure rotating log inside project folder
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)

    # (2) read list
    stream = sys.stdin if video_list == Path("-") else open(video_list, "r", encoding="utf-8")
    video_iter = (
        (Path(d["path"]), d["hash"], Path(d["path"]).stat().st_mtime and data_manager._extract_start_time(Path(d["path"])))
        for d in _iter_json_lines(stream)
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
# Entrypoint
###############################################################################


def run():  # called by __main__.py
    app()
