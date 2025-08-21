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
from datetime import datetime

import typer
from rich import print  # pretty help & errors
from tqdm import tqdm

from .core.state_manager import StateManager
from .core.plugin_manager import PluginManager
from .core.data_manager import DataManager
from .core.project_manager import ProjectManager
from .core.logging_bus import LoggingEventBus
from . import __version__ as MUS1_VERSION
import builtins
import os
import subprocess
import yaml
from .core.remote_scanner import collect_from_targets, collect_from_targets_parallel
from .core.metadata import WorkerEntry, ScanTarget
from .core.job_provider import run_on_worker

_ctx = {"help_option_names": ["-h", "--help", "-help"]}
app = typer.Typer(add_completion=False, rich_markup_mode="rich", context_settings=_ctx)
scan_app = typer.Typer(
    help="Video discovery utilities. On macOS, if no roots are provided, MUS1 will search common locations (~/Movies, ~/Videos, /Volumes).",
    context_settings=_ctx,
)
project_app = typer.Typer(help="Project-level operations", context_settings=_ctx)

setup_app = typer.Typer(help="One-time local setup helpers (per-user)", context_settings=_ctx)
workers_app = typer.Typer(help="Manage project worker entries (non-secret)", context_settings=_ctx)
targets_app = typer.Typer(help="Manage scan targets (local/ssh/wsl)", context_settings=_ctx)

app.add_typer(scan_app, name="scan")
app.add_typer(project_app, name="project")
app.add_typer(setup_app, name="setup")
app.add_typer(workers_app, name="workers")
app.add_typer(targets_app, name="targets")

@app.callback(invoke_without_command=True)
def _root_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        is_eager=True,
    )
):
    if version:
        builtins.print(MUS1_VERSION)
        raise typer.Exit()
    # If no subcommand provided, fall through to Typer's default behaviour
    # (we don't force exit here to preserve existing UX).


@app.command("project-help", help="Show full help for the 'project' command group")
def project_help():
    builtins.print(project_app.get_help(ctx=typer.Context(project_app)))


@app.command("scan-help", help="Show full help for the 'scan' command group")
def scan_help():
    builtins.print(scan_app.get_help(ctx=typer.Context(scan_app)))

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
        env = os.environ.get("MUS1_SHARED_DIR")
        if env:
            root = Path(env).expanduser()
        elif shared_root:
            root = shared_root.expanduser()
        else:
            # Try user config fallback via ProjectManager
            try:
                root = project_manager.get_shared_directory()
            except Exception:
                raise typer.BadParameter("Provide --shared-root, set MUS1_SHARED_DIR, or run 'mus1 setup shared' first")
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

@project_app.command("set-shared-root", help="Set or update the project's shared storage root path.")
def project_set_shared_root(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    shared_root: Path = typer.Argument(..., help="Directory considered the authoritative shared storage root"),
):
    """Configure the project to use a shared root. Only files under this root are auto-eligible for registration."""
    state_manager, _, _, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    # Configure project-scoped rotating log before further operations
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)
    sr = shared_root.expanduser().resolve()
    if not sr.exists() or not sr.is_dir():
        raise typer.BadParameter(f"Shared root does not exist or is not a directory: {sr}")
    state_manager.project_state.shared_root = sr
    project_manager.save_project()
    print(f"Set shared root to: {sr}")


@project_app.command("move-to-shared", help="Move the current project directory under the shared root (preserves folder name).")
def project_move_to_shared(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    shared_root: Optional[Path] = typer.Option(None, "--shared-root", help="Override shared root; otherwise use state or MUS1_SHARED_DIR/setup"),
):
    """Relocate the project into the shared root so it is accessible across the lab network."""
    state_manager, _, _, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    # Ensure project-scoped rotating log so CLI doesn’t warn about missing FileHandler
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)

    # Resolve shared root precedence: explicit arg -> state -> ProjectManager.get_shared_directory
    target_root: Path
    if shared_root:
        target_root = shared_root.expanduser().resolve()
    elif state_manager.project_state.shared_root:
        target_root = Path(state_manager.project_state.shared_root).expanduser().resolve()
    else:
        target_root = project_manager.get_shared_directory()

    if not target_root.exists():
        target_root.mkdir(parents=True, exist_ok=True)

    new_path = project_manager.move_project_to_directory(target_root)
    print(f"Project moved to: {new_path}")

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
    # Configure project-scoped rotating log before further operations
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
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


@project_app.command("stage-to-shared", help="Copy files listed in JSONL into the project's shared root, verify hash, then register unassigned videos.")
def project_stage_to_shared(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    video_list: Path = typer.Argument(..., metavar="LIST|-", help="JSON-lines list (from scan/dedup) or '-' for stdin"),
    dest_subdir: str = typer.Argument(..., help="Destination subdirectory under shared root (e.g., 'recordings/raw')"),
    overwrite: bool = typer.Option(False, help="Overwrite existing destination file if present"),
    progress: bool = typer.Option(True, help="Show progress bar"),
):
    """Stage off-shared files into shared storage and register them.

    This command assumes it is run on a machine that can access both the source paths
    and the project's shared root as local filesystem paths.
    """
    state_manager, _, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)

    sr = state_manager.project_state.shared_root
    if not sr:
        try:
            sr = project_manager.get_shared_directory()
        except Exception as e:
            raise typer.BadParameter(f"Shared root not configured for project and not resolvable: {e}")
    shared_root = Path(sr).expanduser().resolve()
    if not shared_root.exists():
        shared_root.mkdir(parents=True, exist_ok=True)

    dest_base = (shared_root / dest_subdir).expanduser().resolve()
    dest_base.mkdir(parents=True, exist_ok=True)

    # Read records
    stream = sys.stdin if video_list == Path("-") else open(video_list, "r", encoding="utf-8")
    records = list(_iter_json_lines(stream))

    # Build input list
    src_with_hashes: list[tuple[Path, str]] = []
    for rec in records:
        try:
            p = Path(rec.get("path", "")).expanduser()
            h = str(rec.get("hash"))
            if h and p.exists():
                src_with_hashes.append((p, h))
        except Exception:
            continue

    pbar = tqdm(total=len(src_with_hashes), desc="Staging", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def _cb(done: int, total: int):
        # keep tqdm in sync without over-updating
        pbar.update(done - pbar.n)

    staged_iter = data_manager.stage_files_to_shared(
        src_with_hashes,
        shared_root=shared_root,
        dest_base=dest_base,
        overwrite=overwrite,
        progress_cb=_cb if progress else None,
    )

    added = project_manager.register_unlinked_videos(staged_iter)
    pbar.close()
    print(f"Staged and added {added} videos. Unassigned total: {len(state_manager.project_state.unassigned_videos)}")


@project_app.command("ingest", help="Scan roots, dedup, split by shared, and either preview or stage+register off-shared items.")
def project_ingest(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    roots: List[Path] = typer.Argument(None, help="Directories or drive roots to scan"),
    dest_subdir: str = typer.Option("recordings/raw", "--dest-subdir", help="Destination under shared root for staging off-shared"),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, "--exclude-dirs", help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, "--non-recursive", help="Disable recursive traversal"),
    preview: bool = typer.Option(False, "--preview", help="Preview only (no registration/staging)"),
    emit_in_shared: Optional[Path] = typer.Option(None, "--emit-in-shared", help="Write JSONL of items already under shared root"),
    emit_off_shared: Optional[Path] = typer.Option(None, "--emit-off-shared", help="Write JSONL of items not under shared root"),
    progress: bool = typer.Option(True, help="Show progress bars"),
    parallel: bool = typer.Option(False, "--parallel", help="Scan multiple roots in parallel (per-target/threaded)"),
    max_workers: int = typer.Option(4, "--max-workers", help="Parallel workers for --parallel"),
):
    """Single-command ingest: scan→dedup→split, then preview or stage+register off-shared.

    If --preview is set, writes optional JSONLs and exits without changes.
    Otherwise, registers in-shared and stages off-shared into shared_root/dest_subdir, then registers them.
    """
    state_manager, _, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve roots defaults per-OS if not provided
    try:
        from .core.scanners.video_discovery import default_roots_if_missing
        effective_roots = default_roots_if_missing(roots)
    except Exception:
        effective_roots = roots or []
    if not effective_roots:
        raise typer.BadParameter("No scan roots provided and no defaults available for this OS. Please specify directories.")

    # Scan and dedup
    pbar = tqdm(desc="Scanning", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def scan_cb(done: int, total: int):
        pbar.total = total
        pbar.update(done - pbar.n)
    if parallel and len(effective_roots) > 1:
        # Per-root parallelism using threads, reusing discover_video_files inside tasks
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def _scan(root: Path):
            return list(
                data_manager.discover_video_files(
                    [root],
                    extensions=extensions,
                    recursive=not non_recursive,
                    excludes=exclude_dirs,
                    progress_cb=None,
                )
            )
        videos: list[tuple[Path, str]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            futs = {exe.submit(_scan, r): r for r in effective_roots}
            for fut in as_completed(futs):
                try:
                    videos.extend(fut.result())
                except Exception:
                    pass
        # no central scan progress when running per-root threads
    else:
        videos = list(
            data_manager.discover_video_files(
                effective_roots,
                extensions=extensions,
                recursive=not non_recursive,
                excludes=exclude_dirs,
                progress_cb=scan_cb,
            )
        )
    pbar.close()

    dedup_pbar = tqdm(total=len(videos), desc="Deduping", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def dedup_cb(done: int, total: int):
        dedup_pbar.update(1)
    dedup_gen = data_manager.deduplicate_video_list([(p, h) for p, h in videos], progress_cb=dedup_cb)
    in_shared, off_shared = project_manager.split_by_shared_root(dedup_gen)
    dedup_pbar.close()

    # Emit JSONLs if requested
    if emit_in_shared:
        data_manager.emit_jsonl(emit_in_shared, in_shared)
    if emit_off_shared:
        data_manager.emit_jsonl(emit_off_shared, off_shared)

    if preview:
        builtins.print(
            f"Preview: {len(in_shared)} items under shared, {len(off_shared)} items off-shared. Project: {project_path}"
        )
        raise typer.Exit(code=0)

    # Register in-shared
    added_in = project_manager.register_unlinked_videos(iter(in_shared))

    # Stage off-shared into shared root
    sr = state_manager.project_state.shared_root
    if not sr:
        try:
            sr = project_manager.get_shared_directory()
        except Exception as e:
            raise typer.BadParameter(f"Shared root not configured for project and not resolvable: {e}")
    shared_root = Path(sr).expanduser().resolve()
    dest_base = (shared_root / dest_subdir).expanduser().resolve()
    staged_iter = data_manager.stage_files_to_shared(
        [(p, h) for p, h, _ in off_shared],
        shared_root=shared_root,
        dest_base=dest_base,
        overwrite=False,
        progress_cb=None if not progress else (lambda done, total: None),
    )
    added_off = project_manager.register_unlinked_videos(staged_iter)

    builtins.print(
        f"Ingest complete. Added {added_in} under-shared and {added_off} staged videos. Total unassigned: {len(state_manager.project_state.unassigned_videos)}"
    )

def run():
    app()

###############################################################################
# setup shared (per-user config)
###############################################################################


@setup_app.command("shared", help="Configure your per-user shared projects root (no secrets).")
def setup_shared(
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Writable shared root directory"),
    create: bool = typer.Option(False, help="Create the directory if it does not exist"),
):
    """Persist a per-user config pointing to your shared projects directory.

    This is stored in your OS user config dir and used when MUS1_SHARED_DIR is not set.
    """
    # Determine target path
    if path is None:
        path = Path(typer.prompt("Enter shared root path (must be writable)"))
    path = path.expanduser().resolve()

    # Create if requested
    if not path.exists():
        if create:
            path.mkdir(parents=True, exist_ok=True)
        else:
            raise typer.BadParameter(f"Path does not exist: {path}. Re-run with --create to make it.")

    # Validate write access
    test_file = path / ".mus1-write-test"
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        test_file.unlink(missing_ok=True)
    except Exception as e:
        raise typer.BadParameter(f"Path is not writable: {path} ({e})")

    # Compute per-OS user config dir
    config_dir: Path
    if sys.platform == "darwin":
        config_dir = Path.home() / "Library/Application Support/mus1"
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        config_dir = Path(appdata) / "mus1"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        config_dir = Path(xdg) / "mus1"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "config.yaml"
    data = {"shared_root": str(path)}
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)

    print(f"Saved shared root to {config_path}\nShared projects will default to: {path}")

###############################################################################
# workers management (typed in ProjectState.workers)
###############################################################################


def _load_project_for_workers(project_path: Path) -> tuple[StateManager, ProjectManager]:
    state_manager, _, _, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    return state_manager, project_manager


@workers_app.command("list", help="List worker entries for a project")
def workers_list(project_path: Path = typer.Argument(..., help="Path to MUS1 project")):
    state_manager, _pm = _load_project_for_workers(project_path)
    workers = state_manager.project_state.workers or []
    if not workers:
        print("No workers configured.")
        return
    print("Workers:")
    for w in workers:
        role = w.role or ""
        print(f"- {w.name}  alias={w.ssh_alias}  role={role}  provider={w.provider}")


@workers_app.command("add", help="Add a worker entry (non-secret). Auth uses your ~/.ssh/config alias.")
def workers_add(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", help="Display name for the worker"),
    ssh_alias: str = typer.Option(..., "--ssh-alias", help="Host alias from ~/.ssh/config"),
    role: Optional[str] = typer.Option(None, help="Optional role tag (e.g., compute, storage)"),
    provider: str = typer.Option("ssh", help="Provider for executing commands: ssh|wsl|local|ssh-wsl", show_default=True),
    test: bool = typer.Option(False, help="Test SSH connectivity to the alias (BatchMode)")
):
    state_manager, project_manager = _load_project_for_workers(project_path)
    workers = state_manager.project_state.workers
    if any(w.name == name for w in workers):
        raise typer.BadParameter(f"Worker with name '{name}' already exists")

    we = WorkerEntry(name=name, ssh_alias=ssh_alias, role=role, provider=provider)  # type: ignore[arg-type]
    workers.append(we)

    if test:
        try:
            result = subprocess.run([
                "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", ssh_alias, "true"
            ], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"SSH test OK for '{ssh_alias}'")
            else:
                print(f"SSH test FAILED for '{ssh_alias}': {result.stderr.strip()}")
        except Exception as e:
            print(f"SSH test error: {e}")

    project_manager.save_project()
    print(f"Added worker '{name}' (alias={ssh_alias}).")


@workers_app.command("remove", help="Remove a worker entry by name")
def workers_remove(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Argument(..., help="Worker name to remove"),
):
    state_manager, project_manager = _load_project_for_workers(project_path)
    workers = state_manager.project_state.workers
    before = len(workers)
    workers = [w for w in workers if w.name != name]
    state_manager.project_state.workers = workers
    if len(workers) == before:
        print(f"No worker named '{name}' found.")
        return
    project_manager.save_project()
    print(f"Removed worker '{name}'.")


@workers_app.command("run", help="Run a command on a worker via its provider (ssh|wsl)")
def workers_run(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", "-n", help="Worker name to use"),
    command: List[str] = typer.Argument(..., metavar="COMMAND...", help="Command (and args) to execute remotely. Use '--' to separate from options."),
    cwd: Optional[Path] = typer.Option(None, "--cwd", help="Remote working directory"),
    env: Optional[List[str]] = typer.Option(None, "--env", help="Environment variables as KEY=VALUE; repeat for multiple"),
    timeout: Optional[int] = typer.Option(None, "--timeout", help="Timeout in seconds"),
    tty: bool = typer.Option(False, "--tty", help="Allocate a TTY (ssh -tt)"),
):
    state_manager, _pm = _load_project_for_workers(project_path)
    workers = state_manager.project_state.workers or []
    try:
        worker = next(w for w in workers if w.name == name)
    except StopIteration:
        raise typer.BadParameter(f"No worker named '{name}' found")

    env_map: Optional[dict] = None
    if env:
        env_map = {}
        for item in env:
            if "=" not in item:
                raise typer.BadParameter(f"Invalid env spec '{item}', expected KEY=VALUE")
            k, v = item.split("=", 1)
            env_map[k] = v

    try:
        result = run_on_worker(
            worker,
            command,
            cwd=cwd,
            env=env_map,
            timeout=timeout,
            allocate_tty=tty,
            stream_output=True,
            log_prefix=f"worker:{worker.name}",
        )
    except Exception as e:
        print(f"Error executing on worker '{name}': {e}")
        raise typer.Exit(code=1)

    raise typer.Exit(code=result.return_code)

###############################################################################
# targets management (typed in ProjectState.scan_targets)
###############################################################################


def _load_project_for_targets(project_path: Path) -> tuple[StateManager, ProjectManager]:
    state_manager, _, _, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    return state_manager, project_manager


@targets_app.command("list", help="List scan targets for a project")
def targets_list(project_path: Path = typer.Argument(..., help="Path to MUS1 project")):
    state_manager, _pm = _load_project_for_targets(project_path)
    targets = state_manager.project_state.scan_targets or []
    if not targets:
        builtins.print("No scan targets configured.")
        return
    builtins.print("Scan targets:")
    for t in targets:
        roots = ", ".join(str(r) for r in t.roots)
        alias = t.ssh_alias or ""
        builtins.print(f"- {t.name}  kind={t.kind}  alias={alias}  roots=[{roots}]")


@targets_app.command("add", help="Add a scan target (local/ssh/wsl)")
def targets_add(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", help="Target name"),
    kind: str = typer.Option(..., "--kind", help="local|ssh|wsl"),
    roots: List[Path] = typer.Option(..., "--root", help="Root(s) to scan; repeat for multiple"),
    ssh_alias: Optional[str] = typer.Option(None, "--ssh-alias", help="SSH alias for ssh/wsl targets"),
):
    state_manager, project_manager = _load_project_for_targets(project_path)
    targets = state_manager.project_state.scan_targets
    if any(t.name == name for t in targets):
        raise typer.BadParameter(f"Target with name '{name}' already exists")
    kind_l = kind.lower()
    if kind_l not in ("local", "ssh", "wsl"):
        raise typer.BadParameter("--kind must be one of: local, ssh, wsl")
    if kind_l in ("ssh", "wsl") and not ssh_alias:
        raise typer.BadParameter("--ssh-alias is required for ssh/wsl targets")
    t = ScanTarget(name=name, kind=kind_l, roots=[Path(r).expanduser() for r in roots], ssh_alias=ssh_alias)  # type: ignore[arg-type]
    targets.append(t)
    project_manager.save_project()
    print(f"Added target '{name}' ({kind_l}).")


@targets_app.command("remove", help="Remove a scan target by name")
def targets_remove(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Argument(..., help="Target name to remove"),
):
    state_manager, project_manager = _load_project_for_targets(project_path)
    targets = state_manager.project_state.scan_targets
    before = len(targets)
    targets = [t for t in targets if t.name != name]
    state_manager.project_state.scan_targets = targets
    if len(targets) == before:
        print(f"No target named '{name}' found.")
        return
    project_manager.save_project()
    print(f"Removed target '{name}'.")

###############################################################################
# project scan-from-targets
###############################################################################


@project_app.command("scan-from-targets", help="Scan configured targets, dedup, and add unassigned videos to project. Filters to shared_root if set.")
def project_scan_from_targets(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    target_names: Optional[List[str]] = typer.Option(None, "--target", help="Restrict to specific targets by name"),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, "--exclude-dirs", help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, "--non-recursive", help="Disable recursive traversal"),
    progress: bool = typer.Option(True, help="Show progress bars"),
    parallel: bool = typer.Option(False, "--parallel", help="Scan targets in parallel"),
    max_workers: int = typer.Option(4, "--max-workers", help="Parallel workers for --parallel"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview results without registering videos"),
    emit_in_shared: Optional[Path] = typer.Option(None, "--emit-in-shared", help="Write JSONL of items already under shared root"),
    emit_off_shared: Optional[Path] = typer.Option(None, "--emit-off-shared", help="Write JSONL of items not under shared root"),
):
    state_manager, _, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    # Configure project-scoped rotating log before further operations
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    targets = list(state_manager.project_state.scan_targets or [])
    if target_names:
        targets = [t for t in targets if t.name in set(target_names)]
    if not targets:
        print("No matching scan targets configured.")
        raise typer.Exit(code=1)

    if parallel:
        all_items = collect_from_targets_parallel(
            state_manager,
            data_manager,
            targets,
            extensions=extensions,
            exclude_dirs=exclude_dirs,
            non_recursive=non_recursive,
            max_workers=max_workers,
        )
    else:
        all_items = collect_from_targets(state_manager, data_manager, targets, extensions=extensions, exclude_dirs=exclude_dirs, non_recursive=non_recursive)

    # Deduplicate and split relative to shared_root (if configured)
    dedup_gen = data_manager.deduplicate_video_list(all_items)
    in_shared, off_shared = project_manager.split_by_shared_root(dedup_gen)

    # Optionally emit JSONL lists for review
    if emit_in_shared:
        data_manager.emit_jsonl(emit_in_shared, in_shared)
    if emit_off_shared:
        data_manager.emit_jsonl(emit_off_shared, off_shared)

    if dry_run:
        builtins.print(
            f"Dry run: {len(in_shared)} items under shared, {len(off_shared)} items off-shared. Project: {project_path}"
        )
        raise typer.Exit(code=0)

    # Register only items already under shared root
    added = project_manager.register_unlinked_videos(iter(in_shared))
    builtins.print(
        f"Added {added} unassigned videos to {project_path}. Total unassigned: {len(state_manager.project_state.unassigned_videos)}; Off-shared pending: {len(off_shared)}"
    )