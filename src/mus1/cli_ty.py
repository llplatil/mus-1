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

_ctx = {"help_option_names": ["-h", "--help", "-help"]}
app = typer.Typer(add_completion=False, rich_markup_mode="rich", context_settings=_ctx)
scan_app = typer.Typer(
    help="Video discovery utilities. On macOS, if no roots are provided, MUS1 will search common locations (~/Movies, ~/Videos, /Volumes).",
    context_settings=_ctx,
)
project_app = typer.Typer(help="Project-level operations", context_settings=_ctx)

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

@scan_app.command("videos", help="Recursively scan roots for video files and stream JSON lines (path, hash). If no roots are given on macOS, defaults are used (~/Movies, ~/Videos, /Volumes).")
def scan_videos(
    roots: List[Path] = typer.Argument(None, help="Directories or drive roots to scan. Omit on macOS to use defaults."),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, help="Disable recursive traversal"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON lines file (default: stdout)"),
    progress: bool = typer.Option(True, help="Show progress bar (default: true if interactive)"),
):
    """Recursively scan *roots* for video files and stream JSON lines (path, hash)."""
    _, _, data_manager, _ = _init_managers()
    # If no roots were given, compute sensible defaults per OS
    try:
        from .core.scanners.video_discovery import default_roots_if_missing
        effective_roots = default_roots_if_missing(roots)
    except Exception:
        effective_roots = roots or []

    if not effective_roots:
        print("No scan roots provided and no defaults available for this OS. Please specify one or more directories.")
        raise typer.Exit(code=1)

    items_gen = data_manager.discover_video_files(
        effective_roots,
        extensions=extensions,
        recursive=not non_recursive,
        excludes=exclude_dirs,
    )

    pbar = tqdm(desc="Scanning", unit="file", disable=(not progress) or (not sys.stderr.isatty()))

    if output:
        with open(output, "a") as f:
            for path, hsh in items_gen:
                out = {"path": str(path), "hash": hsh}
                f.write(json.dumps(out) + "\n")
                pbar.update(1)
    else:
        for path, hsh in items_gen:
            out = {"path": str(path), "hash": hsh}
            print(json.dumps(out))
            pbar.update(1)
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

    source_stream = sys.stdin if input_file in (None, Path("-")) else open(input_file, "r", encoding="utf-8")
    records = list(_iter_json_lines(source_stream))
    tuples: List[tuple[Path, str]] = [(Path(rec["path"]), rec["hash"]) for rec in records]

    pbar = tqdm(total=len(tuples), desc="Dedup", unit="file", disable=not sys.stderr.isatty())
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

    # (2) read list once (materialize to avoid iterator exhaustion)
    stream = sys.stdin if video_list == Path("-") else open(video_list, "r", encoding="utf-8")
    records = list(_iter_json_lines(stream))
    def _coerce_start_time(rec: dict):
        st = rec.get("start_time")
        if st:
            try:
                from datetime import datetime
                return datetime.fromisoformat(str(st).rstrip("Z"))
            except Exception:
                pass
        return data_manager._extract_start_time(Path(rec["path"]))

    video_iter = (
        (Path(rec["path"]), rec["hash"], _coerce_start_time(rec))
        for rec in records
    )

    # (3) register
    added = project_manager.register_unlinked_videos(video_iter)
    print(f"Added {added} videos to project '{project_path}'. Unassigned total: {len(state_manager.project_state.unassigned_videos)}")

    if assign:
        # Placeholder for auto-assignment logic
        print("Auto-assignment is a placeholder for now.")

###############################################################################
# gui (launch the MUS1 GUI)
###############################################################################


@app.command("gui", help="Launch the MUS1 GUI application")
def launch_gui():
    """Start the PySide6 GUI (same as running mus1-gui)."""
    # Import lazily to avoid Qt import cost for CLI-only usage
    from .main import main as gui_main
    gui_main()

###############################################################################
# project list
###############################################################################


@project_app.command("list")
def list_projects(
    base_dir: Optional[Path] = typer.Option(None, help="Base directory to search for projects (default: standard location)"),
    shared: bool = typer.Option(False, help="List projects from the shared directory (MUS1_SHARED_DIR)"),
):
    """List available MUS1 projects on this machine."""
    _, _, _, project_manager = _init_managers()
    if shared and not base_dir:
        try:
            base_dir = project_manager.get_shared_directory()
        except Exception as e:
            print(f"Error resolving shared directory: {e}")
            base_dir = None
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


@project_app.command("create", help="Create a new MUS1 project. Defaults to ~/MUS1/projects unless --base-dir or MUS1_PROJECTS_DIR is set.")
def create_project(
    name: str = typer.Argument(..., help="Project name (folder name) or absolute path"),
    location: str = typer.Option("local", help="Where to create the project: local|shared|server (server is placeholder)", show_default=True),
    base_dir: Optional[Path] = typer.Option(None, help="Override base directory for local projects (default ~/MUS1/projects)"),
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
        import os
        env = os.environ.get("MUS1_SHARED_DIR")
        if env:
            root = Path(env).expanduser()
        elif shared_root:
            root = shared_root.expanduser()
        else:
            raise typer.BadParameter("Provide --shared-root or set MUS1_SHARED_DIR for shared location")
        target_path = root / name
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

@project_app.command("scan-and-add", help="Scan roots (or defaults on macOS), dedup, and add unassigned videos to project.")
def project_scan_and_add(
    project_path: Path = typer.Argument(..., help="Existing MUS1 project directory"),
    roots: List[Path] = typer.Argument(None, help="Directories or drive roots to scan. Omit on macOS to use defaults."),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, help="Disable recursive traversal"),
    progress: bool = typer.Option(True, help="Show progress bar (default: true if interactive)"),
):
    """Scan roots for videos, dedup, and add unassigned videos to project."""
    state_manager, _, data_manager, project_manager = _init_managers()

    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)

    # If no roots were given, compute sensible defaults per OS
    try:
        from .core.scanners.video_discovery import default_roots_if_missing
        effective_roots = default_roots_if_missing(roots)
    except Exception:
        effective_roots = roots or []

    if not effective_roots:
        raise typer.BadParameter("No scan roots provided and no defaults available for this OS. Please specify directories.")

    pbar = tqdm(desc="Scanning", unit="file", disable=(not progress) or (not sys.stderr.isatty()))

    def scan_cb(done: int, total: int):
        pbar.total = total
        pbar.update(done - pbar.n)

    videos = list(data_manager.discover_video_files(effective_roots, extensions=extensions, recursive=not non_recursive, excludes=exclude_dirs, progress_cb=scan_cb))
    pbar.close()

    dedup_pbar = tqdm(total=len(videos), desc="Deduping", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def dedup_cb(done: int, total: int):
        dedup_pbar.update(1)

    dedup_gen = data_manager.deduplicate_video_list([(p, h) for p, h in videos], progress_cb=dedup_cb)
    added = project_manager.register_unlinked_videos(dedup_gen)
    dedup_pbar.close()

    print(f"Added {added} unassigned videos to {project_path}. Total unassigned: {len(state_manager.project_state.unassigned_videos)}")


def run():
    app()