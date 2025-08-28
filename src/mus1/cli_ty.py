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
from .core.credentials import load_credentials, set_credential, remove_credential
from .core.master_media import load_master_index, save_master_index, add_or_update_master_item

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


@project_app.command("resolve-subjects", help="Suggest 3-digit subject IDs from master library and interactively add them.")
def project_resolve_subjects(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    library_path: Optional[Path] = typer.Option(None, "--library-path", help="Override path for master library (defaults to <shared_root>/recordings/master)"),
):
    state_manager, _, _, project_manager = _init_managers()
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve library path: default to shared_root/recordings/master
    if library_path is None:
        try:
            sr = project_manager.state_manager.project_state.shared_root or project_manager.get_shared_directory()
        except Exception as e:
            print(f"Shared root not configured: {e}. Run 'mus1 project set-shared-root' first.")
            raise typer.Exit(code=1)
        library_path = (Path(sr).expanduser().resolve() / "recordings" / "master").resolve()

    if not library_path.exists():
        print(f"Library path not found: {library_path}")
        raise typer.Exit(code=1)

    result = project_manager.run_project_level_plugin_action(
        "CustomMetadataResolver",
        "suggest_subjects",
        {
            "action": "suggest_subjects",
            "project_path": str(project_path),
            "library_path": str(library_path),
        },
    )

    if result.get("status") != "success":
        print(result.get("error", "Failed to resolve subjects"))
        raise typer.Exit(code=1)

    suggestions = result.get("suggestions", []) or []
    if not suggestions:
        print("No new subject IDs suggested from master library.")
        return

    added = 0
    skipped = 0
    for sid in suggestions:
        if typer.confirm(f"Add subject {sid}?", default=False):
            project_manager.add_subject(subject_id=sid)
            added += 1
        else:
            skipped += 1
    print(f"Added: {added}, Skipped: {skipped}")


@project_app.command("assign-subject", help="Create a minimal experiment and link a recording to a subject.")
def project_assign_subject(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    recording_path: Path = typer.Argument(..., help="Path to a recording file under shared/master"),
    subject_id: str = typer.Argument(..., help="Subject ID (e.g., 690)"),
    experiment_id: Optional[str] = typer.Option(None, "--experiment-id", help="Override experiment ID (default: recording basename)"),
    exp_type: str = typer.Option("Unknown", "--type", help="Experiment type label"),
    create_subject: bool = typer.Option(False, "--create-subject", help="Create subject if missing"),
):
    _, _, _, project_manager = _init_managers()
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    if subject_id not in project_manager.state_manager.project_state.subjects:
        if not create_subject:
            raise typer.BadParameter(f"Subject '{subject_id}' not found. Use --create-subject to add.")
        project_manager.add_subject(subject_id=subject_id)

    result = project_manager.run_project_level_plugin_action(
        "CustomMetadataResolver",
        "assign_subject_to_recording",
        {
            "action": "assign_subject_to_recording",
            "project_path": str(project_path),
            "subject_id": subject_id,
            "recording_path": str(recording_path),
            "experiment_id": experiment_id,
            "exp_type": exp_type,
        },
    )

    if result.get("status") != "success":
        print(result.get("error", "Failed to assign subject to recording"))
        raise typer.Exit(code=1)

    eid = result.get("experiment_id")
    print(f"Linked {recording_path} to experiment {eid}")


@project_app.command("assign-subject-sex", help="Set sex for a subject (M/F, case-insensitive).")
def project_assign_subject_sex(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    subject_id: str = typer.Argument(..., help="Subject ID"),
    sex: str = typer.Argument(..., help="M or F"),
):
    _, _, _, project_manager = _init_managers()
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    result = project_manager.run_project_level_plugin_action(
        "CustomMetadataResolver",
        "assign_subject_sex",
        {
            "action": "assign_subject_sex",
            "project_path": str(project_path),
            "subject_id": subject_id,
            "sex": sex,
        },
    )

    if result.get("status") != "success":
        print(result.get("error", "Failed to assign subject sex"))
        raise typer.Exit(code=1)

    print(f"Updated {subject_id} sex to {result.get('sex')}")


@project_app.command("assign-subjects-from-master", help="Propose subject assignments for recordings in master by filename and interactively accept.")
def project_assign_subjects_from_master(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    library_path: Optional[Path] = typer.Option(None, "--library-path", help="Override path for master library (defaults to <shared_root>/recordings/master)"),
    create_subject: bool = typer.Option(False, "--create-subject", help="Create subject on accept if missing"),
):
    _, _, _, project_manager = _init_managers()
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve library path default
    if library_path is None:
        try:
            sr = project_manager.state_manager.project_state.shared_root or project_manager.get_shared_directory()
        except Exception as e:
            print(f"Shared root not configured: {e}. Run 'mus1 project set-shared-root' first.")
            raise typer.Exit(code=1)
        library_path = (Path(sr).expanduser().resolve() / "recordings" / "master").resolve()
    if not library_path.exists():
        print(f"Library path not found: {library_path}")
        raise typer.Exit(code=1)

    result = project_manager.run_project_level_plugin_action(
        "CustomMetadataResolver",
        "propose_subject_assignments_from_master",
        {
            "action": "propose_subject_assignments_from_master",
            "project_path": str(project_path),
            "library_path": str(library_path),
        },
    )
    if result.get("status") != "success":
        print(result.get("error", "Failed to generate subject assignment proposals"))
        raise typer.Exit(code=1)

    proposals = result.get("proposals", []) or []
    if not proposals:
        print("No subject assignment proposals found.")
        return

    accepted = 0
    skipped = 0
    for p in proposals:
        rec = p.get("recording_path")
        sid = p.get("subject_id")
        if not rec or not sid:
            continue
        if typer.confirm(f"Assign subject {sid} to recording {rec}?", default=False):
            if sid not in project_manager.state_manager.project_state.subjects and create_subject:
                project_manager.add_subject(subject_id=sid)
            result2 = project_manager.run_project_level_plugin_action(
                "CustomMetadataResolver",
                "assign_subject_to_recording",
                {
                    "action": "assign_subject_to_recording",
                    "project_path": str(project_path),
                    "subject_id": sid,
                    "recording_path": str(rec),
                    "experiment_id": None,
                    "exp_type": "Unknown",
                },
            )
            if result2.get("status") == "success":
                accepted += 1
            else:
                print(f"Failed to assign {sid} to {rec}: {result2.get('error')}")
        else:
            skipped += 1
    print(f"Assignments accepted: {accepted}, Skipped: {skipped}")


@project_app.command("assign-subject-sex-by-master-filename-metadata", help="Propose subject sex from master filenames and interactively accept.")
def project_assign_subject_sex_by_master(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    library_path: Optional[Path] = typer.Option(None, "--library-path", help="Override path for master library (defaults to <shared_root>/recordings/master)"),
):
    _, _, _, project_manager = _init_managers()
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    if library_path is None:
        try:
            sr = project_manager.state_manager.project_state.shared_root or project_manager.get_shared_directory()
        except Exception as e:
            print(f"Shared root not configured: {e}. Run 'mus1 project set-shared-root' first.")
            raise typer.Exit(code=1)
        library_path = (Path(sr).expanduser().resolve() / "recordings" / "master").resolve()
    if not library_path.exists():
        print(f"Library path not found: {library_path}")
        raise typer.Exit(code=1)

    result = project_manager.run_project_level_plugin_action(
        "CustomMetadataResolver",
        "propose_subject_sex_from_master",
        {
            "action": "propose_subject_sex_from_master",
            "project_path": str(project_path),
            "library_path": str(library_path),
        },
    )
    if result.get("status") != "success":
        print(result.get("error", "Failed to generate subject sex proposals"))
        raise typer.Exit(code=1)

    proposals = result.get("proposals", []) or []
    if not proposals:
        print("No subject sex proposals found.")
        return

    updated = 0
    skipped = 0
    for p in proposals:
        sid = p.get("subject_id")
        sex = p.get("sex")
        if not sid or sex not in {"M", "F"}:
            continue
        if typer.confirm(f"Set subject {sid} sex to {sex}?", default=False):
            res2 = project_manager.run_project_level_plugin_action(
                "CustomMetadataResolver",
                "assign_subject_sex",
                {
                    "action": "assign_subject_sex",
                    "project_path": str(project_path),
                    "subject_id": sid,
                    "sex": sex,
                },
            )
            if res2.get("status") == "success":
                updated += 1
            else:
                print(f"Failed to set sex for {sid}: {res2.get('error')}")
        else:
            skipped += 1
    print(f"Sex updates accepted: {updated}, Skipped: {skipped}")


@project_app.command("cleanup-copies", help="Identify and optionally remove or archive redundant off-shared copies by policy.")
def project_cleanup_copies(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    policy: str = typer.Option("keep", "--policy", help="delete|keep|archive", show_default=True),
    scope: str = typer.Option("non-shared", "--scope", help="non-shared|all", show_default=True),
    dry_run: bool = typer.Option(True, "--dry-run", help="Preview actions only"),
    archive_dir: Optional[Path] = typer.Option(None, "--archive-dir", help="Destination for archived files when policy=archive"),
):
    state_manager, _, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)

    sr = state_manager.project_state.shared_root
    sr_path = Path(sr).expanduser().resolve() if sr else None
    videos = state_manager.project_state.unassigned_videos | state_manager.project_state.experiment_videos
    total = 0
    actions: list[str] = []
    for hsh, vm in videos.items():
        locations = vm.last_seen_locations or []
        off_shared_paths: list[Path] = []
        for loc in locations:
            p = Path(loc.get("path", ""))
            try:
                rp = p.expanduser().resolve()
            except Exception:
                rp = p
            if scope == "all" or (sr_path and not str(rp).startswith(str(sr_path))):
                off_shared_paths.append(rp)
        if not off_shared_paths:
            continue
        total += len(off_shared_paths)
        for p in off_shared_paths:
            if policy == "keep":
                actions.append(f"KEEP {p}")
            elif policy == "delete":
                actions.append(f"DELETE {p}")
                if not dry_run:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
            elif policy == "archive":
                if not archive_dir:
                    actions.append(f"ARCHIVE (missing --archive-dir) {p}")
                else:
                    dest = archive_dir.expanduser().resolve() / p.name
                    actions.append(f"ARCHIVE {p} -> {dest}")
                    if not dry_run:
                        try:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            import shutil
                            shutil.move(str(p), str(dest))
                        except Exception:
                            pass
            else:
                actions.append(f"UNKNOWN_POLICY {p}")

    builtins.print(f"Cleanup candidates: {total} off-shared copies (policy={policy}, scope={scope}, dry_run={dry_run}).")
    for a in actions:
        builtins.print(a)

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
    # Ensure project-scoped rotating log so CLI doesn't warn about missing FileHandler
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

@project_app.command("scan-and-move", help="Scan roots, dedup, then move discovered videos into <project>/media per-recording folders and register as unassigned.")
def project_scan_and_move(
    project_path: Path = typer.Argument(..., help="Existing MUS1 project directory"),
    roots: List[Path] = typer.Argument(None, help="Directories or drive roots to scan. Omit on macOS to use defaults."),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, help="Disable recursive traversal"),
    progress: bool = typer.Option(True, help="Show progress bar (default: true if interactive)"),
    verify_time: bool = typer.Option(False, "--verify-time", help="Probe container time and prefer it if it differs from mtime"),
):
    """Scan roots for videos, dedup, move into media/, and register unassigned."""
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
    dedup_pbar.close()

    # Stage into media/ using per-recording folder convention
    media_dir = (project_path / "media").expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)
    staged_iter = data_manager.stage_files_to_shared(
        ((p, h) for p, h, _ in dedup_gen),
        shared_root=project_path,
        dest_base=media_dir,
        overwrite=False,
        progress_cb=None,
        delete_source_on_success=False,
        namer=None,
        verify_time=verify_time,
    )
    added = project_manager.register_unlinked_videos(staged_iter)

    print(f"Moved and registered {added} videos into media/. You can now run 'project media assign' if desired.")


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

    # Auto-host decision: if shared_root is not writable here, emit off-shared list and exit unless preview already handled
    def _is_writable(p: Path) -> bool:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".mus1-write-test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return True
        except Exception:
            return False

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
    if not _is_writable(shared_root):
        # Not host: emit off-shared list if not already requested and exit with guidance
        if not emit_off_shared:
            tmp = (Path.cwd() / "off_shared.auto.jsonl").resolve()
            data_manager.emit_jsonl(tmp, off_shared)
            builtins.print(f"Shared root not writable on this host. Wrote off-shared list to {tmp}. Stage from the host machine.")
        else:
            builtins.print(f"Shared root not writable on this host. Use the emitted off-shared list to stage from the host.")
        raise typer.Exit(code=2)
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


@project_app.command("build-master-library", help="Create/update master media under shared root using per-recording folders (pattern options deprecated).")
def project_build_master_library(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    dest_subdir: str = typer.Option("recordings/master", "--dest-subdir", help="Destination under shared root for the master library"),
    ext_copy: Optional[List[str]] = typer.Option([".mp4"], "--ext-copy", help="Extensions to COPY into master library (repeatable)"),
    ext_move: Optional[List[str]] = typer.Option([".mkv"], "--ext-move", help="Extensions to MOVE into master library (repeatable)"),
    pattern: str = typer.Option("{base}_{date:%Y%m%d}_{hash8}{ext}", "--pattern", help="[DEPRECATED] Ignored; per-recording folders are used."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without copying/moving or registering"),
    progress: bool = typer.Option(True, help="Show progress bars"),
):
    """Build a canonical, flat master library from the project's known videos.

    - Sources: both unassigned_videos and experiment_videos in the project state
    - Policy: copy for --ext-copy, move for --ext-move
    - Naming: canonical based on subject/experiment/date/hash to avoid collisions
    - Output: files placed under shared_root/dest_subdir, registered as unassigned videos
    """
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()

    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve shared root
    sr = state_manager.project_state.shared_root
    if not sr:
        try:
            sr = project_manager.get_shared_directory()
        except Exception as e:
            raise typer.BadParameter(f"Shared root not configured for project and not resolvable: {e}")
    shared_root = Path(sr).expanduser().resolve()
    dest_base = (shared_root / dest_subdir).expanduser().resolve()

    # Gather known videos (hash/path/date) from state
    ps = state_manager.project_state
    items: list[tuple[Path, str, datetime]] = []

    def _ensure_hash_and_tuple(vm) -> Optional[tuple[Path, str, datetime]]:
        try:
            p = Path(vm.path)
            if not p.exists():
                return None
            h = vm.sample_hash or data_manager.compute_sample_hash(p)
            dt = getattr(vm, "date", None) or data_manager._extract_start_time(p)
            return (p, str(h), dt)
        except Exception:
            return None

    for vm in ps.unassigned_videos.values():
        tup = _ensure_hash_and_tuple(vm)
        if tup:
            items.append(tup)
    for vm in ps.experiment_videos.values():
        tup = _ensure_hash_and_tuple(vm)
        if tup:
            items.append(tup)

    if not items:
        print("No known videos in project state.")
        raise typer.Exit(code=0)

    # Build lookup maps for naming
    hash_to_vm = {h: vm for h, vm in ((vm.sample_hash, vm) for vm in list(ps.unassigned_videos.values()) + list(ps.experiment_videos.values())) if h}
    exp_by_id = ps.experiments

    def _namer(src_path: Path) -> str:
        # Try to find hash via quick compute; if expensive, we fall back to base
        try:
            h = data_manager.compute_sample_hash(src_path)
        except Exception:
            h = None
        vm = hash_to_vm.get(h) if h else None
        subject = "unknown"
        experiment = "unknown"
        date_val: datetime | None = None
        if vm:
            date_val = getattr(vm, "date", None)
            exp_id = next(iter(vm.experiment_ids), None) if hasattr(vm, "experiment_ids") else None
            if exp_id and exp_id in exp_by_id:
                experiment = exp_id
                subject = exp_by_id[exp_id].subject_id
                if not date_val:
                    date_val = exp_by_id[exp_id].date_recorded
        if not date_val:
            try:
                date_val = data_manager._extract_start_time(src_path)
            except Exception:
                date_val = datetime.fromtimestamp(src_path.stat().st_mtime)
        base = src_path.stem
        ext = src_path.suffix
        hash8 = (h or "").replace(" ", "")[:8] if h else ""
        # Render pattern safely
        try:
            name = pattern.format(
                subject=subject,
                experiment=experiment,
                date=date_val,
                hash8=hash8,
                base=base,
                ext=ext,
            )
        except Exception:
            name = f"{base}_{hash8}{ext}" if hash8 else f"{base}{ext}"
        # Ensure extension is present
        if not name.endswith(ext):
            name = f"{name}{ext}"
        # Strip directory parts if pattern introduced any
        return Path(name).name

    # Split by extension policy
    ext_copy = [e.lower() for e in (ext_copy or [])]
    ext_move = [e.lower() for e in (ext_move or [])]
    allow = set(ext_copy + ext_move) if (ext_copy or ext_move) else None
    src_copy: list[tuple[Path, str]] = []
    src_move: list[tuple[Path, str]] = []
    for p, h, _ in items:
        if allow and p.suffix.lower() not in allow:
            continue
        if p.suffix.lower() in ext_move:
            src_move.append((p, h))
        else:
            src_copy.append((p, h))

    print(f"Planning master library at: {dest_base}")
    print(f"Copy: {len(src_copy)} files | Move: {len(src_move)} files")

    if dry_run:
        raise typer.Exit(code=0)

    # Execute copy stage
    added_total = 0
    pbar_total = len(src_copy) + len(src_move)
    pbar = tqdm(total=pbar_total, desc="Building master library", disable=(not progress) or (not sys.stderr.isatty()))

    def _tick(done: int, total: int):
        pbar.update(1)

    def _reg(gen):
        nonlocal added_total
        added = project_manager.register_unlinked_videos(gen)
        added_total += added

    if src_copy:
        gen_copy = data_manager.stage_files_to_shared(src_copy, shared_root=shared_root, dest_base=dest_base, overwrite=False, progress_cb=_tick, delete_source_on_success=False, namer=_namer)
        _reg(gen_copy)
    if src_move:
        gen_move = data_manager.stage_files_to_shared(src_move, shared_root=shared_root, dest_base=dest_base, overwrite=False, progress_cb=_tick, delete_source_on_success=True, namer=_namer)
        _reg(gen_move)

    pbar.close()
    print(f"Master library build complete. Newly registered: {added_total}. Unassigned total: {len(state_manager.project_state.unassigned_videos)}")
    if pattern:
        typer.echo("Note: --pattern is deprecated and ignored; folder-based naming is enforced.")


@project_app.command("import-moseq-media", help="Move MoSeq2 .mkv recordings into master using per-recording folders (pattern deprecated).")
def project_import_moseq_media(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    moseq_root: Path = typer.Argument(..., help="Path to MoSeq media root (e.g., /path/to/moseq_media)"),
    dest_subdir: str = typer.Option("recordings/master", "--dest-subdir", help="Destination under shared root for the master library"),
    require_proc: bool = typer.Option(True, "--require-proc/--no-require-proc", help="Only include sessions that have proc/results_00.mp4"),
    pattern: str = typer.Option("{base}_{date:%Y%m%d}_{hash8}{ext}", "--pattern", help="[DEPRECATED] Ignored; folder-based naming is enforced."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without moving or registering"),
    progress: bool = typer.Option(True, help="Show progress bars"),
    provenance: str = typer.Option("third_party_import", "--provenance", help="Provenance label to store in metadata"),
):
    from datetime import datetime as _dt
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()

    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve shared root
    sr = state_manager.project_state.shared_root
    if not sr:
        try:
            sr = project_manager.get_shared_directory()
        except Exception as e:
            raise typer.BadParameter(f"Shared root not configured for project and not resolvable: {e}")
    shared_root = Path(sr).expanduser().resolve()
    dest_base = (shared_root / dest_subdir).expanduser().resolve()

    mr = Path(moseq_root).expanduser().resolve()
    if not mr.exists():
        raise typer.BadParameter(f"MoSeq root not found: {mr}")

    # Find mkv sessions: expect layout like <mr>/<session>/<session>.mkv with optional proc/results_00.mp4
    mkv_paths: list[Path] = []
    for p in mr.glob("**/*.mkv"):
        if p.is_file():
            if require_proc:
                proc = p.parent / "proc" / "results_00.mp4"
                if not proc.exists():
                    continue
            mkv_paths.append(p)

    if not mkv_paths:
        print("No matching MoSeq .mkv files found.")
        raise typer.Exit(code=0)

    # Build items with hashes
    items: list[tuple[Path, str, _dt]] = []
    for p in mkv_paths:
        try:
            h = data_manager.compute_sample_hash(p)
            # Derive date from parent dir if looks like *_YYYYMMDD_*
            date_val: _dt | None = None
            try:
                s = p.parent.name
                import re
                m = re.search(r"(20\d{6})", s)
                if m:
                    yyyy = int(m.group(1)[0:4])
                    mm = int(m.group(1)[4:6])
                    dd = int(m.group(1)[6:8])
                    from datetime import datetime as _d
                    date_val = _d(yyyy, mm, dd)
            except Exception:
                date_val = None
            if not date_val:
                date_val = data_manager._extract_start_time(p)
            items.append((p, h, date_val))
        except Exception:
            continue

    print(f"Planning MoSeq import to: {dest_base}")
    print(f"Move count: {len(items)} files")
    if dry_run:
        raise typer.Exit(code=0)

    # Namer preserving base and appending date/hash
    def _namer(src_path: Path) -> str:
        base = src_path.stem
        ext = src_path.suffix
        try:
            h = data_manager.compute_sample_hash(src_path)
            hash8 = h[:8]
        except Exception:
            hash8 = ""
        # try to reuse precomputed date from items via simple cache
        try:
            # This is best-effort; the destination naming is independent of exact date if unavailable
            st = data_manager._extract_start_time(src_path)
        except Exception:
            from datetime import datetime as _d
            st = _d.fromtimestamp(src_path.stat().st_mtime)
        try:
            name = pattern.format(base=base, ext=ext, date=st, hash8=hash8, subject="", experiment="")
        except Exception:
            name = f"{base}_{hash8}{ext}" if hash8 else f"{base}{ext}"
        if not name.endswith(ext):
            name = f"{name}{ext}"
        return Path(name).name

    # Execute stage (move)
    src_move = [(p, h) for (p, h, _) in items]
    pbar_total = len(src_move)
    pbar = tqdm(total=pbar_total, desc="Importing MoSeq", disable=(not progress) or (not sys.stderr.isatty()))
    def _tick(done: int, total: int):
        pbar.update(1)
    gen_move = data_manager.stage_files_to_shared(src_move, shared_root=shared_root, dest_base=dest_base, overwrite=False, progress_cb=_tick, delete_source_on_success=True, namer=_namer)
    added = project_manager.register_unlinked_videos(gen_move)
    pbar.close()

    # Update provenance on new items
    try:
        for vm in list(state_manager.project_state.unassigned_videos.values()):
            p = Path(vm.path)
            if str(p).startswith(str(dest_base)):
                md = data_manager.read_recording_metadata(p.parent)
                if md:
                    md.setdefault("provenance", {})["source"] = provenance
                    data_manager.write_recording_metadata(p.parent, md)
    except Exception:
        pass

    print(f"MoSeq import complete. Moved and registered: {added}. Unassigned total: {len(state_manager.project_state.unassigned_videos)}")


@project_app.command("import-third-party-folder", help="Import a third-party processed folder into this project's media with provenance notes.")
def project_import_third_party_folder(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    source_dir: Path = typer.Argument(..., help="Path to third-party folder to import"),
    copy: bool = typer.Option(True, "--copy/--move", help="Copy (default) or move into media"),
    recursive: bool = typer.Option(True, "--recursive/--non-recursive", help="Recursively search for media files"),
    verify_time: bool = typer.Option(False, "--verify-time", help="Probe container time and prefer on mismatch"),
    provenance: str = typer.Option("third_party_import", "--provenance", help="Provenance label to store in metadata"),
    progress: bool = typer.Option(True, help="Show progress bars"),
):
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    sd = Path(source_dir).expanduser().resolve()
    if not sd.exists() or not sd.is_dir():
        raise typer.BadParameter(f"Source directory not found: {sd}")

    # Collect media files
    exts = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}
    files: list[Path] = []
    if recursive:
        for p in sd.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    else:
        for p in sd.iterdir():
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    if not files:
        print("No media files found to import.")
        raise typer.Exit(code=0)

    # Hash and stage into media
    staged: list[tuple[Path, str]] = []
    pbar = tqdm(total=len(files), desc="Hashing", disable=(not progress) or (not sys.stderr.isatty()))
    for p in files:
        try:
            h = data_manager.compute_sample_hash(p)
            staged.append((p, h))
        except Exception:
            pass
        pbar.update(1)
    pbar.close()

    media_dir = (project_path / "media").expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)
    gen = data_manager.stage_files_to_shared(
        staged,
        shared_root=project_path,
        dest_base=media_dir,
        overwrite=False,
        progress_cb=None,
        delete_source_on_success=not copy,
        namer=None,
        verify_time=verify_time,
    )
    added = project_manager.register_unlinked_videos(gen)

    # Apply provenance and original path note
    try:
        for vm in list(state_manager.project_state.unassigned_videos.values()):
            p = Path(vm.path)
            if str(p).startswith(str(media_dir)):
                md = data_manager.read_recording_metadata(p.parent)
                if md:
                    prov = md.setdefault("provenance", {})
                    prov["source"] = provenance
                    notes = prov.get("notes", "")
                    if sd.as_posix() not in notes:
                        prov["notes"] = (notes + f"; imported_from={sd.as_posix()}").strip("; ")
                    data_manager.write_recording_metadata(p.parent, md)
    except Exception:
        pass

    print(f"Third-party import complete. Added {added} items. Unassigned total: {len(state_manager.project_state.unassigned_videos)}")


@project_app.command("fix-master-times", help="Rename master library media files to reflect true recording time and update project state.")
def project_fix_master_times(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    dest_subdir: str = typer.Option("recordings/master", "--dest-subdir", help="Master library subdir under shared root"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without renaming or saving"),
    progress: bool = typer.Option(True, help="Show progress"),
):
    state_manager, _, data_manager, project_manager = _init_managers()

    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")

    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    res = project_manager.fix_master_recording_times(
        project_path=project_path,
        dest_subdir=dest_subdir,
        dry_run=dry_run,
    )
    if res.get("status") != "success":
        print(f"[red]Failed:[/red] {res.get('error')}")
        raise typer.Exit(code=1)
    print(
        f"Scanned {res['scanned']} files. Renamed {res['renamed']}. Updated recordings: {res['updated_recordings']}. Updated experiments: {res['updated_experiments']}."
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
    verify_time: bool = typer.Option(False, "--verify-time", help="Probe container time and prefer on mismatch"),
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
    # If not writable here and there are off-shared, emit guidance
    def _is_writable(p: Path) -> bool:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".mus1-write-test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    sr = state_manager.project_state.shared_root
    writable = _is_writable(Path(sr)) if sr else False
    if off_shared and not writable:
        builtins.print(f"Note: {len(off_shared)} items are off-shared and shared_root is not writable here. Use project ingest on the host to stage.")

    builtins.print(f"Added {added} unassigned videos to {project_path}. Total unassigned: {len(state_manager.project_state.unassigned_videos)}; Off-shared pending: {len(off_shared)}")
    # If user wants to stage off-shared now into media, they can run scan-and-move with --verify-time={verify_time}

@project_app.command("media-index", help="Index loose media in <project>/media: create per-recording folders and metadata.json; register as unassigned.")
def project_media_index(
    project_path: Path = typer.Argument(..., help="Existing MUS1 project directory"),
    progress: bool = typer.Option(True, help="Show progress"),
    provenance: str = typer.Option("scan_and_move", "--provenance", help="Provenance label to store in metadata"),
):
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()

    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    media_dir = (project_path / "media").expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)

    # Find top-level loose media files (not inside per-recording folders)
    exts = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}
    loose: list[Path] = []
    for entry in media_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in exts:
            loose.append(entry)

    if not loose:
        print("No loose media files found in media/.")
        return

    pbar = tqdm(total=len(loose), desc="Indexing", unit="file", disable=(not progress) or (not sys.stderr.isatty()))

    staged: list[tuple[Path, str]] = []
    for p in loose:
        try:
            h = data_manager.compute_sample_hash(p)
            staged.append((p, h))
        except Exception:
            pass
        pbar.update(1)
    pbar.close()

    # Stage (move) into per-recording folders under media/
    staged_iter = data_manager.stage_files_to_shared(
        staged,
        shared_root=project_path,  # treat project as shared root to allow existing-under-root logic
        dest_base=media_dir,
        overwrite=False,
        progress_cb=None,
        delete_source_on_success=True,
        namer=None,
    )

    # Post-update provenance in metadata for staged items
    added = project_manager.register_unlinked_videos(staged_iter)
    try:
        for vm in list(state_manager.project_state.unassigned_videos.values()):
            p = Path(vm.path)
            if str(p).startswith(str(media_dir)):
                md = data_manager.read_recording_metadata(p.parent)
                if md:
                    md.setdefault("provenance", {})["source"] = provenance
                    data_manager.write_recording_metadata(p.parent, md)
    except Exception:
        pass
    print(f"Indexed and registered {added} media files.")


@project_app.command("media-assign", help="Interactively assign unassigned media to subjects/experiment types; rename folders accordingly.")
def project_media_assign(
    project_path: Path = typer.Argument(..., help="Existing MUS1 project directory"),
    prompt_on_time_mismatch: bool = typer.Option(False, "--prompt-on-time-mismatch", help="If container time differs from mtime and metadata lacks CSV date, prompt user for manual date or UNK"),
    set_provenance: Optional[str] = typer.Option(None, "--set-provenance", help="Override provenance.source in metadata for assigned items"),
):
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    ps = state_manager.project_state
    if not ps.unassigned_videos:
        print("No unassigned media to assign.")
        return

    media_dir = (project_path / "media").expanduser().resolve()

    for h, vm in list(ps.unassigned_videos.items()):
        p = Path(vm.path)
        print(f"\nAssign: {p.name}")
        subject_id = typer.prompt("Subject ID", default="unknown").strip()
        experiment_type = typer.prompt("Experiment type", default="").strip()

        # Update recording metadata.json and folder name if under media/
        try:
            if str(p).startswith(str(media_dir)):
                rec_dir = p.parent
                md = data_manager.read_recording_metadata(rec_dir)
                md["subject_id"] = subject_id or "unknown"
                md["experiment_type"] = experiment_type
                # Optional: prompt for recorded_time when metadata lacks CSV-derived date but we detect mismatch
                if prompt_on_time_mismatch:
                    times = md.get("times") or {}
                    rt = times.get("recorded_time")
                    src = times.get("recorded_time_source")
                    try:
                        from datetime import datetime as _dt
                        mtime_dt = _dt.fromtimestamp(p.stat().st_mtime)
                        container_dt = data_manager._extract_start_time(p)
                        # If no CSV date present and times disagree by > 60s, prompt
                        if (rt is None) and abs((container_dt - mtime_dt).total_seconds()) > 60.0:
                            ans = typer.prompt("Recording date differs (container vs mtime). Enter ISO date (YYYY-MM-DD) or 'UNK'", default="UNK").strip()
                            if ans.upper() != "UNK":
                                try:
                                    new_dt = _dt.fromisoformat(ans)
                                    md.setdefault("times", {})["recorded_time"] = new_dt.isoformat()
                                    md["times"]["recorded_time_source"] = "manual"
                                except Exception:
                                    pass
                    except Exception:
                        pass
                if set_provenance:
                    md.setdefault("provenance", {})["source"] = set_provenance
                data_manager.write_recording_metadata(rec_dir, md)

                # Rename folder to canonical subject-YYYYMMDD-hash8 if subject provided
                try:
                    recorded_str = ((md.get("times") or {}).get("recorded_time"))
                    from datetime import datetime as _dt
                    if recorded_str:
                        recorded_dt = _dt.fromisoformat(recorded_str)
                    else:
                        recorded_dt = vm.date
                    new_folder = data_manager.recording_folder_name(subject_id or "unknown", recorded_dt, h)
                    target_dir = rec_dir.parent / new_folder
                    if target_dir != rec_dir:
                        try:
                            rec_dir.rename(target_dir)
                            # Update path in VM
                            vm.path = (target_dir / p.name)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        # Optional: create experiment immediately and link media
        do_link = typer.confirm("Create experiment and link this recording now?", default=False)
        if do_link:
            try:
                exp_id = project_manager.create_experiment_from_recording(
                    recording_path=p,
                    subject_id=subject_id or "unknown",
                    experiment_type=experiment_type or "",
                    experiment_subtype=None,
                )
                print(f"Created and linked experiment: {exp_id}")
            except Exception as e:
                print(f"Failed to create/link experiment: {e}")

    project_manager.save_project()
    state_manager.notify_observers()
    print("Assignment pass complete.")

# -----------------------------------------------------------------------------
# credentials management
# -----------------------------------------------------------------------------

@app.command("credentials-set", help="Set or update credentials for an ssh alias (stored in ~/.mus1/credentials.json)")
def credentials_set(
    alias: str = typer.Argument(..., help="SSH alias name (matches ScanTarget.ssh_alias)"),
    user: Optional[str] = typer.Option(None, "--user", help="Username for SSH"),
    identity_file: Optional[Path] = typer.Option(None, "--identity-file", help="Path to SSH private key"),
):
    set_credential(alias, user=user, identity_file=str(identity_file) if identity_file else None)
    print(f"Credentials set for alias '{alias}'.")


@app.command("credentials-list", help="List stored credentials aliases")
def credentials_list():
    creds = load_credentials()
    if not creds:
        print("No credentials stored.")
        return
    for k, v in creds.items():
        print(f"{k}: user={v.get('user','')}, identity_file={v.get('identity_file','')}")


@app.command("credentials-remove", help="Remove credentials for an alias")
def credentials_remove(alias: str = typer.Argument(..., help="SSH alias name")):
    ok = remove_credential(alias)
    if ok:
        print(f"Removed credentials for '{alias}'.")
    else:
        print(f"No credentials found for '{alias}'.")


# -----------------------------------------------------------------------------
# assembly-driven scan by experiments (CSV-guided)
# -----------------------------------------------------------------------------

@project_app.command("assembly-scan-by-experiments", help="Use assembly plugin to parse experiments CSV and import matching media into project/media.")
def project_assembly_scan_by_experiments(
    project_path: Path = typer.Argument(..., help="Existing MUS1 project directory"),
    experiments_csv: List[Path] = typer.Argument(..., help="One or more experiment CSV files"),
    roots: Optional[List[Path]] = typer.Option(None, "--roots", help="Optional roots to scan. If omitted, assembly plugin scan_hints.roots (if any) will be used."),
    verify_time: bool = typer.Option(False, "--verify-time", help="Probe container time and prefer on mismatch"),
    provenance: str = typer.Option("assembly_guided_import", "--provenance", help="Provenance label for imported media"),
    progress: bool = typer.Option(True, help="Show progress"),
):
    state_manager, plugin_manager, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve assembly plugin
    asm = plugin_manager.get_plugin_by_name("CustomProjectAssembly_Skeleton")
    if not asm or not hasattr(asm, "parse_experiments_csv"):
        raise typer.BadParameter("Assembly plugin not found (CustomProjectAssembly_Skeleton)")

    # Parse CSVs → subject IDs
    subjects: set[str] = set()
    for csvp in experiments_csv:
        recs = asm.parse_experiments_csv(Path(csvp).expanduser().resolve())
        for r in recs:
            sid = str(r.get("subject_id", "")).strip()
            if sid:
                subjects.add(sid)
    if not subjects:
        print("No subjects extracted from CSVs.")
        raise typer.Exit(code=0)

    # Resolve roots from config if not provided
    if not roots:
        try:
            hints = asm.load_scan_hints() or {}
            cfg_roots = hints.get("roots") or []
            if cfg_roots:
                roots = [Path(r).expanduser() for r in cfg_roots]
        except Exception:
            roots = None

    # If roots are provided, scan and filter by subject-id substrings
    items: list[tuple[Path, str]] = []
    if roots:
        pbar = tqdm(desc="Scanning", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
        def _tick(done: int, total: int):
            pbar.total = total
            pbar.update(done - pbar.n)
        vids = list(data_manager.discover_video_files(roots, extensions=None, recursive=True, excludes=None, progress_cb=_tick))
        pbar.close()
        for p, h in vids:
            name = p.name.lower()
            if any(s.lower() in name for s in subjects):
                items.append((p, h))

    if not items and roots:
        print("No media matched subject IDs under provided roots.")
        raise typer.Exit(code=0)

    # Stage matched items into media
    media_dir = (project_path / "media").expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)
    staged_iter = data_manager.stage_files_to_shared(
        items,
        shared_root=project_path,
        dest_base=media_dir,
        overwrite=False,
        progress_cb=None,
        delete_source_on_success=False,
        namer=None,
        verify_time=verify_time,
    )
    added = project_manager.register_unlinked_videos(staged_iter)

    # Apply provenance to staged items
    try:
        for vm in list(state_manager.project_state.unassigned_videos.values()):
            p = Path(vm.path)
            if str(p).startswith(str(media_dir)):
                md = data_manager.read_recording_metadata(p.parent)
                if md:
                    md.setdefault("provenance", {})["source"] = provenance
                    data_manager.write_recording_metadata(p.parent, md)
    except Exception:
        pass

    print(f"Assembly scan complete. Added {added} items. Unassigned total: {len(state_manager.project_state.unassigned_videos)}")


# -----------------------------------------------------------------------------
# master media list management (root-level)
# -----------------------------------------------------------------------------

@app.command("master-accept-current", help="Accept current project's media as the master media list")
def master_accept_current(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
):
    state_manager, _, data_manager, project_manager = _init_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    idx = load_master_index()
    media_dir = (project_path / "media").expanduser().resolve()
    for p in media_dir.glob("**/*"):
        if p.is_file():
            try:
                h = data_manager.compute_sample_hash(p)
                md = data_manager.read_recording_metadata(p.parent)
                add_or_update_master_item(
                    idx,
                    sample_hash=h,
                    info={
                        "recorded_time": (md.get("times") or {}).get("recorded_time") if md else None,
                        "subject_id": md.get("subject_id") if md else None,
                        "experiment_type": md.get("experiment_type") if md else None,
                        "known_locations": [p],
                    },
                )
            except Exception:
                pass
    save_master_index(idx)
    print("Master media list updated from current project.")


@app.command("master-add-unique", help="Add unique items from another project's media into the master list")
def master_add_unique(
    other_project: Path = typer.Argument(..., help="Path to other MUS1 project"),
):
    state_manager, _, data_manager, project_manager = _init_managers()
    if not other_project.exists():
        raise typer.BadParameter(f"Project not found: {other_project}")
    idx = load_master_index()
    items = idx.get("items", {})
    media_dir = (other_project / "media").expanduser().resolve()
    for p in media_dir.glob("**/*"):
        if p.is_file():
            try:
                h = data_manager.compute_sample_hash(p)
                if h in items:
                    continue
                md = data_manager.read_recording_metadata(p.parent)
                add_or_update_master_item(
                    idx,
                    sample_hash=h,
                    info={
                        "recorded_time": (md.get("times") or {}).get("recorded_time") if md else None,
                        "subject_id": md.get("subject_id") if md else None,
                        "experiment_type": md.get("experiment_type") if md else None,
                        "known_locations": [p],
                    },
                )
            except Exception:
                pass
    save_master_index(idx)
    print("Master media list unique items added.")