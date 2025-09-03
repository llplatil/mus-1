"""Typer-based MUS1 command-line interface (experimental).

This CLI intentionally has *no* additional business logic – it delegates to
core managers so GUI and CLI share one code path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional, Iterable, Any
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
from .core.metadata import WorkerEntry, ScanTarget
from .core.job_provider import run_on_worker
from .core.credentials import load_credentials, set_credential, remove_credential
from .core.master_media import load_master_index, save_master_index, add_or_update_master_item
from .core.lab_manager import LabManager, LabConfig
import re
import importlib.metadata as importlib_metadata

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
lab_app = typer.Typer(help="Lab-level configuration and shared resources", context_settings=_ctx)

app.add_typer(scan_app, name="scan")
app.add_typer(project_app, name="project")
app.add_typer(setup_app, name="setup")
app.add_typer(workers_app, name="workers")
app.add_typer(targets_app, name="targets")
app.add_typer(lab_app, name="lab")
plugins_app = typer.Typer(help="Manage external MUS1 plugins (installed via pip entry points)", context_settings=_ctx)
app.add_typer(plugins_app, name="plugins")
assembly_app = typer.Typer(help="Project assembly via installed plugins (entry points).", context_settings=_ctx)
project_app.add_typer(assembly_app, name="assembly")

@app.callback(invoke_without_command=True)
def _root_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        is_eager=True,
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON where applicable"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Reduce output (implies no progress bars)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Increase output verbosity"),
):
    if version:
        builtins.print(MUS1_VERSION)
        raise typer.Exit()
    # Initialize and cache managers once at root
    _get_managers()
    # Store global output preferences
    if getattr(ctx, "obj", None) is None:
        ctx.obj = {}
    ctx.obj["output"] = {
        "json": bool(json_out),
        "quiet": bool(quiet),
        "verbose": bool(verbose),
    }
    # If no subcommand provided, fall through to Typer's default behaviour
    # (we don't force exit here to preserve existing UX).


@app.command("project-help", help="Show full help for the 'project' command group")
def project_help():
    # Typer wrapper doesn't expose get_help; use underlying Click command
    from typer.main import get_command
    cmd = get_command(project_app)
    builtins.print(cmd.get_help(ctx=typer.Context(cmd)))


@app.command("scan-help", help="Show full help for the 'scan' command group")
def scan_help():
    from typer.main import get_command
    cmd = get_command(scan_app)
    builtins.print(cmd.get_help(ctx=typer.Context(cmd)))

###############################################################################
# Shared helpers
###############################################################################


def _init_managers() -> tuple[StateManager, PluginManager, DataManager, ProjectManager]:
    from .core.lab_manager import LabManager
    state_manager = StateManager()
    plugin_manager = PluginManager()
    data_manager = DataManager(state_manager, plugin_manager)
    lab_manager = LabManager()
    project_manager = ProjectManager(state_manager, plugin_manager, data_manager, lab_manager)
    return state_manager, plugin_manager, data_manager, project_manager

def _get_managers() -> tuple[StateManager, PluginManager, DataManager, ProjectManager]:
    # Initialize managers directly without requiring context
    return _init_managers()

def _out_prefs(ctx: typer.Context) -> dict:
    return (getattr(ctx, "obj", None) or {}).get("output", {})
###############################################################################
# plugins manage
###############################################################################

@plugins_app.command("list", help="List installed MUS1 plugins discovered via entry points")
def plugins_list(ctx: typer.Context):
    try:
        eps = importlib_metadata.entry_points()
        candidates = eps.select(group="mus1.plugins") if hasattr(eps, "select") else eps.get("mus1.plugins", [])
        names = sorted([ep.name for ep in candidates])
        if not names:
            typer.echo("No external plugins installed.")
        else:
            typer.echo("Installed plugins:")
            for n in names:
                typer.echo(f"- {n}")
    except Exception as e:
        typer.secho(f"Failed to enumerate plugins: {e}", fg="red", err=True)

@plugins_app.command("install", help="Install a plugin package via pip and refresh discovery")
def plugins_install(
    package: str = typer.Argument(..., help="PyPI package spec, e.g., mus1-assembly-skeleton"),
    editable: bool = typer.Option(False, "--editable", "-e", help="Install in editable mode from local path"),
):
    # Non-interactive pip install
    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if editable:
            cmd.append("-e")
        cmd.append(package)
        subprocess.run(cmd, check=True)
        typer.echo(f"Installed: {package}")
    except subprocess.CalledProcessError as e:
        typer.secho(f"pip install failed: {e}", fg="red", err=True)
        raise typer.Exit(code=1)

@plugins_app.command("uninstall", help="Uninstall a plugin package via pip")
def plugins_uninstall(
    package: str = typer.Argument(..., help="Package name to uninstall, e.g., mus1-assembly-skeleton"),
    yes: bool = typer.Option(True, "--yes", "-y", help="Assume yes for pip uninstall"),
):
    try:
        cmd = [sys.executable, "-m", "pip", "uninstall", package]
        if yes:
            cmd.append("-y")
        subprocess.run(cmd, check=True)
        typer.echo(f"Uninstalled: {package}")
    except subprocess.CalledProcessError as e:
        typer.secho(f"pip uninstall failed: {e}", fg="red", err=True)
        raise typer.Exit(code=1)



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
    _, _, data_manager, _ = _get_managers()
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
    out_prefs = _out_prefs(typer.get_current_context())
    pbar = tqdm(desc="Scanning", unit="file", disable=(not progress) or (not sys.stderr.isatty()) or out_prefs.get("quiet", False))

    if output:
        with open(output, "a") as f:
            for path, hsh in items_gen:
                out = {"path": str(path), "hash": hsh}
                f.write(json.dumps(out) + "\n")
                pbar.update(1)
    else:
        for path, hsh in items_gen:
            out = {"path": str(path), "hash": hsh}
            typer.echo(json.dumps(out))
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
    _, _, data_manager, _ = _get_managers()

    source_stream = sys.stdin if input_file in (None, Path("-")) else open(input_file, "r", encoding="utf-8")
    records = list(_iter_json_lines(source_stream))
    tuples: List[tuple[Path, str]] = [(Path(rec["path"]), rec["hash"]) for rec in records]

    out_prefs = _out_prefs(typer.get_current_context())
    pbar = tqdm(total=len(tuples), desc="Dedup", unit="file", disable=(not sys.stderr.isatty()) or out_prefs.get("quiet", False))
    def _cb(done: int, total: int):
        pbar.update(1)

    for path, hsh, start_time in data_manager.deduplicate_video_list(tuples, progress_cb=_cb):
        out = {"path": str(path), "hash": hsh, "start_time": start_time.isoformat()}
        if out_prefs.get("json"):
            typer.echo(json.dumps(out))
        else:
            typer.echo(json.dumps(out))
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
    state_manager, _, data_manager, project_manager = _get_managers()

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


# Note: GUI is launched exclusively via the 'mus1-gui' entry point

###############################################################################
# project assembly (generic plugin-driven)
###############################################################################


@assembly_app.command("list", help="List plugins that expose project-level assembly actions")
def assembly_list(ctx: typer.Context):
    _, plugin_manager, _dm, _pm = _get_managers(ctx)
    plugins = plugin_manager.get_plugins_with_project_actions()
    out_prefs = (ctx.obj or {}).get("output", {})
    if out_prefs.get("json"):
        names = [p.plugin_self_metadata().name for p in plugins]
        typer.echo(json.dumps({"plugins": names}))
        return
    if not plugins:
        typer.echo("No assembly-capable plugins installed.")
        return
    typer.echo("Assembly-capable plugins:")
    for p in plugins:
        typer.echo(f"- {p.plugin_self_metadata().name}")


@assembly_app.command("list-actions", help="List project-level actions for an assembly plugin")
def assembly_list_actions(
    plugin: str = typer.Argument(..., help="Plugin name"),
):
    ctx = typer.get_current_context()
    _, plugin_manager, _dm, _pm = _get_managers(ctx)
    actions = plugin_manager.get_project_actions_for_plugin(plugin)
    out_prefs = (ctx.obj or {}).get("output", {})
    if out_prefs.get("json"):
        typer.echo(json.dumps({"plugin": plugin, "actions": actions}))
        return
    if not actions:
        typer.secho(f"No actions exposed by '{plugin}' or plugin not found.", fg="red", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Actions for {plugin}:")
    for a in actions:
        typer.echo(f"- {a}")


@assembly_app.command("run", help="Run a project-level assembly action with optional params.")
def assembly_run(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    plugin: str = typer.Option(None, "--plugin", "-p", help="Assembly plugin name"),
    action: str = typer.Option(None, "--action", "-a", help="Action name to run"),
    params_file: Optional[Path] = typer.Option(None, "--params-file", "-f", help="YAML dict of params"),
    param: Optional[List[str]] = typer.Option(None, "--param", help="KEY=VALUE pairs; repeat for multiple"),
):
    ctx = typer.get_current_context()
    state_manager, plugin_manager, _dm, project_manager = _get_managers(ctx)
    out_prefs = (ctx.obj or {}).get("output", {})
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve candidate plugins
    candidates = plugin_manager.get_plugins_with_project_actions()
    names = [p.plugin_self_metadata().name for p in candidates]
    if not names:
        typer.secho("No assembly-capable plugins installed.", fg="red", err=True)
        raise typer.Exit(code=1)

    if not plugin:
        if len(names) == 1:
            plugin = names[0]
        else:
            if out_prefs.get("json"):
                typer.echo(json.dumps({"error": "multiple_plugins", "plugins": names}))
                raise typer.Exit(code=2)
            typer.echo("Multiple assembly plugins installed. Select one:")
            for idx, n in enumerate(names, 1):
                typer.echo(f"{idx}) {n}")
            try:
                choice = int(typer.prompt("Enter choice number"))
                plugin = names[choice - 1]
            except Exception:
                raise typer.BadParameter("Invalid selection")

    # Resolve action if missing (prompt)
    if not action:
        actions = plugin_manager.get_project_actions_for_plugin(plugin)
        if not actions:
            raise typer.BadParameter(f"Plugin '{plugin}' exposes no actions")
        if out_prefs.get("json"):
            typer.echo(json.dumps({"plugin": plugin, "actions": actions}))
            raise typer.Exit(code=2)
        typer.echo(f"Actions for {plugin}:")
        for idx, a in enumerate(actions, 1):
            typer.echo(f"{idx}) {a}")
        try:
            choice = int(typer.prompt("Enter action number"))
            action = actions[choice - 1]
        except Exception:
            raise typer.BadParameter("Invalid selection")

    # Build params
    params: dict[str, Any] = {"project_path": str(project_path)}
    if params_file:
        pf = params_file.expanduser().resolve()
        if not pf.exists():
            raise typer.BadParameter(f"Params file not found: {pf}")
        with open(pf, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                params.update(loaded)
    if param:
        for item in param:
            if "=" not in item:
                raise typer.BadParameter(f"Invalid --param '{item}', expected KEY=VALUE")
            k, v = item.split("=", 1)
            params[k] = v

    result = project_manager.run_project_level_plugin_action(plugin, action, params)
    if result.get("status") != "success":
        msg = result.get("error", "Assembly action failed")
        if out_prefs.get("json"):
            typer.echo(json.dumps({"status": "failed", "error": msg}))
        else:
            typer.secho(msg, fg="red", err=True)
        raise typer.Exit(code=1)
    if out_prefs.get("json"):
        typer.echo(json.dumps(result))
    else:
        typer.echo(yaml.safe_dump(result, sort_keys=False))

###############################################################################
# project list
###############################################################################


@project_app.command("list")
def list_projects(
    base_dir: Optional[Path] = typer.Option(None, help="Base directory to search for projects (default: standard location)"),
    shared: bool = typer.Option(False, help="List projects from the shared directory (MUS1_SHARED_DIR)"),
):
    """List available MUS1 projects on this machine."""
    _, _, _, project_manager = _get_managers()
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
    out_prefs = _out_prefs(typer.get_current_context())
    if out_prefs.get("json"):
        typer.echo(json.dumps({"projects": [str(p) for p in projects]}))
        return
    if not projects:
        typer.echo("No MUS1 projects found.")
        return
    typer.echo("Available MUS1 projects:")
    for proj in projects:
        typer.echo(f"- {proj.name} ({proj})")


@project_app.command("associate-lab", help="Associate a project with a lab configuration")
def project_associate_lab(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    lab_id: str = typer.Option(..., "--lab-id", help="ID of the lab to associate with"),
    config_dir: Optional[Path] = typer.Option(None, "--config-dir", help="Directory containing lab configs"),
):
    """Associate a MUS1 project with a lab configuration for shared resources."""
    _, _, _, project_manager = _get_managers()

    if not project_path.exists():
        print(f"Error: Project not found: {project_path}")
        raise typer.Exit(code=1)

    try:
        # Load the project first
        project_manager.load_project(project_path)

        # Associate with lab
        project_manager.associate_with_lab(lab_id, config_dir)

        lab_name = "Unknown"
        if project_manager.lab_manager and project_manager.lab_manager.current_lab:
            lab_name = project_manager.lab_manager.current_lab.metadata.name

        print(f"Successfully associated project '{project_path}' with lab '{lab_name}' ({lab_id})")
        print("The project now inherits lab-level workers, credentials, and scan targets.")

    except Exception as e:
        print(f"Error associating project with lab: {e}")
        raise typer.Exit(code=1)


@project_app.command("lab-status", help="Show lab association status for a project")
def project_lab_status(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
):
    """Show lab association status and inherited resources for a project."""
    _, _, _, project_manager = _get_managers()

    if not project_path.exists():
        print(f"Error: Project not found: {project_path}")
        raise typer.Exit(code=1)

    try:
        # Load the project
        project_manager.load_project(project_path)

        lab_id = project_manager.get_lab_id()
        if not lab_id:
            print(f"Project '{project_path}' is not associated with any lab.")
            print("Use 'mus1 project associate-lab <project> --lab-id <lab_id>' to associate it.")
            return

        print(f"Project '{project_path}' is associated with lab '{lab_id}'")

        # Show inherited resources
        if project_manager.lab_manager and project_manager.lab_manager.current_lab:
            lab = project_manager.lab_manager.current_lab
            print(f"\nInherited from lab '{lab.metadata.name}':")
            print(f"- Workers: {len(lab.workers)}")
            print(f"- Credentials: {len(lab.credentials)}")
            print(f"- Scan targets: {len(lab.scan_targets)}")
            print(f"- Master subjects: {len(lab.master_subjects)}")
        else:
            print("Warning: Lab configuration could not be loaded.")

        # Show lab resources
        try:
            workers = project_manager.get_workers()
            targets = project_manager.get_scan_targets()
            subjects = project_manager.get_master_subjects()
            print("\nLab resources:")
            print(f"- Workers: {len(workers)}")
            print(f"- Scan targets: {len(targets)}")
            print(f"- Master subjects: {len(subjects)}")
        except RuntimeError as e:
            print(f"\nNo lab resources available: {e}")

    except Exception as e:
        print(f"Error getting lab status: {e}")
        raise typer.Exit(code=1)


 


"""Deprecated lab-specific commands removed per roadmap; use 'project assembly' surfaces instead."""


"""Deprecated lab-specific commands removed per roadmap; use 'project assembly' surfaces instead."""





"""Deprecated lab-specific commands removed per roadmap; use 'project assembly' surfaces instead."""


@project_app.command("cleanup-copies", help="Identify and optionally remove or archive redundant off-shared copies by policy.")
def project_cleanup_copies(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    policy: str = typer.Option("keep", "--policy", help="delete|keep|archive", show_default=True),
    scope: str = typer.Option("non-shared", "--scope", help="non-shared|all", show_default=True),
    dry_run: bool = typer.Option(True, "--dry-run", help="Preview actions only"),
    archive_dir: Optional[Path] = typer.Option(None, "--archive-dir", help="Destination for archived files when policy=archive"),
):
    state_manager, _, data_manager, project_manager = _get_managers()
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
    state_manager, plugin_manager, data_manager, project_manager = _get_managers()

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
    state_manager, _, _, project_manager = _get_managers()
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
    state_manager, _, _, project_manager = _get_managers()
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
    state_manager, _, data_manager, project_manager = _get_managers()

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
    state_manager, _, data_manager, project_manager = _get_managers()
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
    roots: List[Path] = typer.Argument(None, help="Directories or drive roots to scan (omit when using --target)"),
    dest_subdir: str = typer.Option("recordings/raw", "--dest-subdir", help="Destination under shared root for staging off-shared"),
    extensions: Optional[List[str]] = typer.Option(None, "--ext", help="Allowed extensions (.mp4 .avi …)"),
    exclude_dirs: Optional[List[str]] = typer.Option(None, "--exclude-dirs", help="Sub-strings for directories to skip"),
    non_recursive: bool = typer.Option(False, "--non-recursive", help="Disable recursive traversal"),
    preview: bool = typer.Option(False, "--preview", help="Preview only (no registration/staging)"),
    emit_in_shared: Optional[Path] = typer.Option(None, "--emit-in-shared", help="Write JSONL of items already under shared root"),
    emit_off_shared: Optional[Path] = typer.Option(None, "--emit-off-shared", help="Write JSONL of items not under shared root"),
    progress: bool = typer.Option(True, help="Show progress bars"),
    parallel: bool = typer.Option(False, "--parallel", help="Scan in parallel (per-target/threaded)"),
    max_workers: int = typer.Option(4, "--max-workers", help="Parallel workers for --parallel"),
    target_names: Optional[List[str]] = typer.Option(None, "--target", help="Scan configured targets by name (uses ProjectState.scan_targets)"),
):
    """Single-command ingest: scan→dedup→split, then preview or stage+register off-shared."""
    state_manager, _, _data_manager, project_manager = _get_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)

    scan_pbar = tqdm(desc="Scanning", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def scan_cb(done: int, total: int):
        try:
            scan_pbar.total = total
            scan_pbar.update(done - scan_pbar.n)
        except Exception:
            pass

    dedup_pbar = tqdm(desc="Deduping", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def dedup_cb(done: int, total: int):
        try:
            dedup_pbar.update(1)
        except Exception:
            pass

    stage_pbar = tqdm(desc="Staging", unit="file", disable=(not progress) or (not sys.stderr.isatty()))
    def stage_cb(done: int, total: int):
        try:
            stage_pbar.update(1)
        except Exception:
            pass

    result = project_manager.ingest(
        project_path=project_path,
        roots=roots or None,
        dest_subdir=dest_subdir,
        extensions=extensions,
        exclude_dirs=exclude_dirs,
        non_recursive=non_recursive,
        preview=preview,
        emit_in_shared=emit_in_shared,
        emit_off_shared=emit_off_shared,
        parallel=parallel,
        max_workers=max_workers,
        scan_progress_cb=scan_cb,
        dedup_progress_cb=dedup_cb,
        stage_progress_cb=stage_cb if progress else None,
        target_names=target_names,
    )
    scan_pbar.close(); dedup_pbar.close(); stage_pbar.close()

    if result.get("status") != "success":
        print(result.get("error", "Ingest failed"))
        raise typer.Exit(code=1)

    if result.get("preview"):
        builtins.print(
            f"Preview: {result.get('in_shared_count', 0)} items under shared, {result.get('off_shared_count', 0)} items off-shared. Project: {project_path}"
        )
        raise typer.Exit(code=0)

    if result.get("not_writable"):
        # If we weren't writable, try to help by emitting a default list if user didn't request it
        if not emit_off_shared:
            try:
                tmp = (Path.cwd() / "off_shared.auto.jsonl").resolve()
                # We cannot easily get the actual list here without changing core return; advise the user instead
                builtins.print(f"Shared root not writable on this host. Use --emit-off-shared to write the list, then stage from the host.")
            except Exception:
                pass
        else:
            builtins.print("Shared root not writable on this host. Use the emitted off-shared list to stage from the host.")
        raise typer.Exit(code=2)

    added_in = int(result.get("in_shared_registered", 0))
    added_off = int(result.get("off_shared_staged_registered", 0))
    total_unassigned = int(result.get("total_unassigned", 0))
    builtins.print(
        f"Ingest complete. Added {added_in} under-shared and {added_off} staged videos. Total unassigned: {total_unassigned}"
    )


"""Deprecated master library builder removed; Master Project concept is in development."""


@project_app.command("import-supported-3rdparty", help="Run an installed importer plugin for third-party or external media ingestion.")
def project_import_supported_3rdparty(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    plugin: Optional[str] = typer.Option(None, "--plugin", "-p", help="Importer plugin name (default: only importer if exactly one installed)"),
    params_file: Optional[Path] = typer.Option(None, "--params-file", "-f", help="YAML file of parameters to pass to the importer"),
    param: Optional[List[str]] = typer.Option(None, "--param", help="Additional KEY=VALUE pairs; repeat for multiple"),
    list_plugins: bool = typer.Option(False, "--list", help="List available importer plugins and exit"),
):
    state_manager, plugin_manager, _dm, project_manager = _get_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    project_manager.load_project(project_path)

    # Resolve importer plugins
    importers = plugin_manager.get_importer_plugins()
    names = [p.plugin_self_metadata().name for p in importers]
    if list_plugins:
        if not names:
            builtins.print("No importer plugins are installed.")
        else:
            builtins.print("Importer plugins:")
            for n in names:
                builtins.print(f"- {n}")
        raise typer.Exit(code=0)

    if not plugin:
        if len(names) == 1:
            plugin = names[0]
        else:
            builtins.print("Multiple importer plugins are installed. Use --plugin to select one:")
            for n in names:
                builtins.print(f"- {n}")
            raise typer.Exit(code=2)

    # Validate plugin exists
    target = plugin_manager.get_plugin_by_name(plugin)
    if not target:
        builtins.print(f"Importer plugin not found: {plugin}")
        raise typer.Exit(code=2)

    # Build parameters: YAML file first, then CLI --param overrides
    params: dict[str, Any] = {}
    if params_file:
        pf = params_file.expanduser().resolve()
        if not pf.exists():
            raise typer.BadParameter(f"Params file not found: {pf}")
        try:
            with open(pf, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    params.update(loaded)
        except Exception as e:
            raise typer.BadParameter(f"Failed to read params file: {e}")

    if param:
        for item in param:
            if "=" not in item:
                raise typer.BadParameter(f"Invalid --param '{item}', expected KEY=VALUE")
            k, v = item.split("=", 1)
            params[k] = v

    # Always include project_path for run_import
    params.setdefault("project_path", str(project_path))

    # Generic project-level action call → run_import on the plugin
    result = project_manager.run_project_level_plugin_action(
        plugin,
        "import",
        params,
    )
    if result.get("status") != "success":
        builtins.print(result.get("error", "Import failed."))
        raise typer.Exit(code=1)
    # Minimal standard summary if present
    dest = result.get("destination")
    moved = result.get("moved") or result.get("registered") or result.get("added") or 0
    if dest:
        builtins.print(f"Import complete via '{plugin}'. Items: {moved}. Destination: {dest}")
    else:
        builtins.print(f"Import complete via '{plugin}'. Items: {moved}")

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
    _state_manager, _plugin_manager, _data_manager, project_manager = _get_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    LoggingEventBus.get_instance().configure_default_file_handler(project_path)
    result = project_manager.import_third_party_folder(
        project_path=project_path,
        source_dir=source_dir,
        copy=copy,
        recursive=recursive,
        verify_time=verify_time,
        provenance=provenance,
    )
    if result.get("status") != "success":
        builtins.print(result.get("error", "Import failed."))
        raise typer.Exit(code=1)
    builtins.print(f"Third-party import complete. Added {int(result.get('added', 0))} items.")


"""Deprecated master maintenance CLI removed; Master Project concept is in development."""

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

@setup_app.command("labs", help="Configure your per-user labs root directory.")
def setup_labs(
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Writable labs root directory"),
    create: bool = typer.Option(False, help="Create the directory if it does not exist"),
):
    """Persist a per-user config pointing to your labs directory.

    This is stored in your OS user config dir and used when MUS1_LABS_DIR is not set.
    """
    # Determine target path
    if path is None:
        path = Path(typer.prompt("Enter labs root path (must be writable)"))
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
    data = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}
    data["labs_root"] = str(path)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)

    print(f"Saved labs root to {config_path}\nLab configurations will default to: {path}")

@setup_app.command("projects", help="Configure your per-user local projects root (non-shared).")
def setup_projects(
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Writable local projects root directory"),
    create: bool = typer.Option(False, help="Create the directory if it does not exist"),
):
    """Persist a per-user config pointing to your local projects directory.

    Used when MUS1_PROJECTS_DIR is not set.
    """
    if path is None:
        path = Path(typer.prompt("Enter local projects root path (must be writable)"))
    path = path.expanduser().resolve()

    if not path.exists():
        if create:
            path.mkdir(parents=True, exist_ok=True)
        else:
            raise typer.BadParameter(f"Path does not exist: {path}. Re-run with --create to make it.")

    # Validate write
    test_file = path / ".mus1-write-test"
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        test_file.unlink(missing_ok=True)
    except Exception as e:
        raise typer.BadParameter(f"Path is not writable: {path} ({e})")

    # Same config dir scheme as setup_shared
    if sys.platform == "darwin":
        config_dir = Path.home() / "Library/Application Support/mus1"
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        config_dir = Path(appdata) / "mus1"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        config_dir = Path(xdg) / "mus1"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Merge with existing config.yaml if present
    config_path = config_dir / "config.yaml"
    data = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
    data["projects_root"] = str(path)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    print(f"Saved local projects root to {config_path}\nLocal projects will default to: {path}")

###############################################################################
# lab management (lab-level shared configuration)
###############################################################################


def _get_lab_manager() -> LabManager:
    """Get or create a lab manager instance."""
    return LabManager()


@lab_app.command("create", help="Create a new lab configuration")
def lab_create(
    name: str = typer.Option(..., "--name", help="Human-readable lab name"),
    lab_id: Optional[str] = typer.Option(None, "--id", help="Lab identifier (auto-generated from name if not provided)"),
    description: str = typer.Option("", "--description", help="Lab description"),
    config_dir: Optional[Path] = typer.Option(None, "--config-dir", help="Directory to store lab configs"),
):
    """Create a new lab configuration with shared resources."""
    lab_manager = _get_lab_manager()
    try:
        lab_config = lab_manager.create_lab(
            name=name,
            lab_id=lab_id,
            description=description,
            config_dir=config_dir
        )
        print(f"Created lab '{name}' with ID '{lab_id or name.lower().replace(' ', '_').replace('-', '_')}'")
        print(f"Configuration saved to: {lab_manager.current_lab_path}")
    except FileExistsError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Error creating lab: {e}")
        raise typer.Exit(code=1)


@lab_app.command("list", help="List available lab configurations")
def lab_list(
    config_dir: Optional[Path] = typer.Option(None, "--config-dir", help="Directory containing lab configs"),
):
    """List all available lab configurations."""
    lab_manager = _get_lab_manager()
    labs = lab_manager.list_available_labs(config_dir)

    if not labs:
        print("No lab configurations found.")
        return

    print("Available labs:")
    for lab in labs:
        print(f"- {lab['name']} (ID: {lab['id']})")
        if lab['description']:
            print(f"  Description: {lab['description']}")
        print(f"  Projects: {lab['projects']}")
        print(f"  Path: {lab['path']}")
        print()


@lab_app.command("load", help="Load a lab configuration for current session")
def lab_load(
    lab_id: str = typer.Argument(..., help="Lab ID or path to lab config file"),
    config_dir: Optional[Path] = typer.Option(None, "--config-dir", help="Directory containing lab configs"),
):
    """Load a lab configuration for use in subsequent commands."""
    lab_manager = _get_lab_manager()
    try:
        lab_config = lab_manager.load_lab(lab_id, config_dir)
        print(f"Loaded lab '{lab_config.metadata.name}' ({lab_id})")
        print(f"Workers: {len(lab_config.workers)}")
        print(f"Credentials: {len(lab_config.credentials)}")
        print(f"Scan targets: {len(lab_config.scan_targets)}")
        print(f"Associated projects: {len(lab_config.associated_projects)}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Error loading lab: {e}")
        raise typer.Exit(code=1)


@lab_app.command("associate", help="Associate a project with the current lab")
def lab_associate(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    lab_id: Optional[str] = typer.Option(None, "--lab", help="Lab ID to associate with (if not already loaded)"),
):
    """Associate a MUS1 project with a lab configuration."""
    lab_manager = _get_lab_manager()

    # Load lab if specified
    if lab_id:
        try:
            lab_manager.load_lab(lab_id)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            raise typer.Exit(code=1)

    if lab_manager.current_lab is None:
        print("Error: No lab loaded. Use 'mus1 lab load <lab_id>' first or specify --lab")
        raise typer.Exit(code=1)

    try:
        lab_manager.associate_project(project_path)
        print(f"Associated project '{project_path}' with lab '{lab_manager.current_lab.metadata.name}'")
    except Exception as e:
        print(f"Error associating project: {e}")
        raise typer.Exit(code=1)


@lab_app.command("status", help="Show current lab configuration status")
def lab_status():
    """Show information about the currently loaded lab."""
    lab_manager = _get_lab_manager()

    if lab_manager.current_lab is None:
        print("No lab configuration currently loaded.")
        print("Use 'mus1 lab load <lab_id>' to load a lab configuration.")
        return

    lab = lab_manager.current_lab
    print(f"Current Lab: {lab.metadata.name}")
    print(f"Description: {lab.metadata.description or 'None'}")
    print(f"Created: {lab.metadata.created_at}")
    print(f"Updated: {lab.metadata.updated_at}")
    print(f"Config path: {lab_manager.current_lab_path}")
    print()

    print("Resources:")
    print(f"- Workers: {len(lab.workers)}")
    print(f"- Credentials: {len(lab.credentials)}")
    print(f"- Scan targets: {len(lab.scan_targets)}")
    print(f"- Master subjects: {len(lab.master_subjects)}")
    print(f"- Software installs: {len(lab.software_installs)}")
    print(f"- Associated projects: {len(lab.associated_projects)}")

    print("\nShared Storage:")
    storage = lab.shared_storage
    print(f"- Enabled: {storage.enabled}")
    if storage.enabled:
        print(f"- Mount point: {storage.mount_point or 'Not configured'}")
        print(f"- Volume name: {storage.volume_name or 'Not configured'}")
        print(f"- Projects root: {storage.projects_root}")
        print(f"- Media root: {storage.media_root}")
        print(f"- Auto-detect: {storage.auto_detect}")

        # Check if storage is currently available
        mount_point = lab_manager.detect_shared_storage_mount()
        if mount_point:
            print(f"- Status: Available at {mount_point}")
            projects_root = lab_manager.get_shared_projects_root()
            media_root = lab_manager.get_shared_media_root()
            if projects_root:
                print(f"- Projects directory: {projects_root}")
            if media_root:
                print(f"- Media directory: {media_root}")
        else:
            print("- Status: Not detected/mounted")

    if lab.associated_projects:
        print("\nAssociated projects:")
        for project_path in sorted(lab.associated_projects):
            print(f"- {project_path}")


@lab_app.command("add-worker", help="Add a worker to the current lab")
def lab_add_worker(
    name: str = typer.Option(..., "--name", help="Display name for the worker"),
    ssh_alias: str = typer.Option(..., "--ssh-alias", help="Host alias from ~/.ssh/config"),
    role: Optional[str] = typer.Option(None, help="Optional role tag (e.g., compute, storage)"),
    provider: str = typer.Option("ssh", help="Provider: ssh|wsl|local|ssh-wsl", show_default=True),
):
    """Add a compute worker to the lab configuration."""
    lab_manager = _get_lab_manager()

    if lab_manager.current_lab is None:
        print("Error: No lab loaded. Use 'mus1 lab load <lab_id>' first.")
        raise typer.Exit(code=1)

    try:
        worker = WorkerEntry(
            name=name,
            ssh_alias=ssh_alias,
            role=role,
            provider=provider
        )
        lab_manager.add_worker(worker)
        print(f"Added worker '{name}' to lab '{lab_manager.current_lab.metadata.name}'")
    except ValueError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Error adding worker: {e}")
        raise typer.Exit(code=1)


@lab_app.command("add-credential", help="Add SSH credentials to the current lab")
def lab_add_credential(
    alias: str = typer.Option(..., "--alias", help="SSH alias name"),
    user: Optional[str] = typer.Option(None, "--user", help="Username"),
    identity_file: Optional[Path] = typer.Option(None, "--identity-file", help="Path to SSH private key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description"),
):
    """Add SSH credentials to the lab configuration."""
    lab_manager = _get_lab_manager()

    if lab_manager.current_lab is None:
        print("Error: No lab loaded. Use 'mus1 lab load <lab_id>' first.")
        raise typer.Exit(code=1)

    try:
        lab_manager.add_credential(
            alias=alias,
            user=user,
            identity_file=str(identity_file) if identity_file else None,
            description=description
        )
        print(f"Added credentials for alias '{alias}' to lab '{lab_manager.current_lab.metadata.name}'")
    except Exception as e:
        print(f"Error adding credentials: {e}")
        raise typer.Exit(code=1)


@lab_app.command("add-target", help="Add a scan target to the current lab")
def lab_add_target(
    name: str = typer.Option(..., "--name", help="Target name"),
    kind: str = typer.Option(..., "--kind", help="local|ssh|wsl"),
    roots: List[Path] = typer.Option(..., "--root", help="Root paths to scan"),
    ssh_alias: Optional[str] = typer.Option(None, "--ssh-alias", help="SSH alias for remote targets"),
):
    """Add a scan target to the lab configuration."""
    lab_manager = _get_lab_manager()

    if lab_manager.current_lab is None:
        print("Error: No lab loaded. Use 'mus1 lab load <lab_id>' first.")
        raise typer.Exit(code=1)

    try:
        target = ScanTarget(
            name=name,
            kind=kind,
            roots=[str(r) for r in roots],
            ssh_alias=ssh_alias
        )
        lab_manager.add_scan_target(target)
        print(f"Added scan target '{name}' to lab '{lab_manager.current_lab.metadata.name}'")
    except ValueError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Error adding target: {e}")
        raise typer.Exit(code=1)


@lab_app.command("projects", help="List projects associated with the current lab")
def lab_projects():
    """List all projects associated with the current lab."""
    lab_manager = _get_lab_manager()

    if lab_manager.current_lab is None:
        print("Error: No lab loaded. Use 'mus1 lab load <lab_id>' first.")
        raise typer.Exit(code=1)

    try:
        projects = lab_manager.get_lab_projects()

        if not projects:
            print(f"No valid projects associated with lab '{lab_manager.current_lab.metadata.name}'.")
            return

        print(f"Projects associated with lab '{lab_manager.current_lab.metadata.name}':")
        for project in projects:
            print(f"- {project.name} ({project})")
    except Exception as e:
        print(f"Error listing lab projects: {e}")
        raise typer.Exit(code=1)


@lab_app.command("activate", help="Activate a lab configuration for current session")
def lab_activate(
    lab_id: str = typer.Argument(..., help="Lab ID or path to lab config file"),
    config_dir: Optional[Path] = typer.Option(None, "--config-dir", help="Directory containing lab configs"),
    skip_storage_check: bool = typer.Option(False, "--skip-storage-check", help="Skip shared storage mount check"),
):
    """Activate a lab configuration for use in subsequent commands.

    This loads the lab and checks for shared storage if configured.
    If shared storage is required but not found, activation will fail.
    """
    lab_manager = _get_lab_manager()

    try:
        # Load the lab configuration
        lab_config = lab_manager.load_lab(lab_id, config_dir)
        print(f"Loaded lab '{lab_config.metadata.name}' ({lab_id})")

        # Attempt to activate the lab
        if lab_manager.activate_lab(check_storage=not skip_storage_check):
            print(f"Successfully activated lab '{lab_config.metadata.name}'")

            # Show storage information
            if lab_config.shared_storage.enabled:
                mount_point = lab_manager.detect_shared_storage_mount()
                if mount_point:
                    print(f"Shared storage detected at: {mount_point}")
                    projects_root = lab_manager.get_shared_projects_root()
                    media_root = lab_manager.get_shared_media_root()
                    if projects_root:
                        print(f"Projects will be stored in: {projects_root}")
                    if media_root:
                        print(f"Media/data will be stored in: {media_root}")
                else:
                    print("Warning: Shared storage not detected. Projects will use local storage.")
            else:
                print("Lab configured for local storage only.")
        else:
            print(f"Error: Could not activate lab '{lab_config.metadata.name}'")
            print("Shared storage is configured but not currently mounted.")
            print("Please ensure the shared disk is attached and mounted, then try again.")
            print("Or use --skip-storage-check to activate without storage validation.")
            raise typer.Exit(code=1)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Error activating lab: {e}")
        raise typer.Exit(code=1)


@lab_app.command("configure-storage", help="Configure shared storage for the current lab")
def lab_configure_storage(
    mount_point: Optional[str] = typer.Option(None, "--mount-point", help="Expected mount point path (e.g., /Volumes/CuSSD3)"),
    volume_name: Optional[str] = typer.Option(None, "--volume-name", help="Volume name for detection (e.g., CuSSD3)"),
    projects_root: Optional[str] = typer.Option(None, "--projects-root", help="Directory name for projects on shared storage"),
    media_root: Optional[str] = typer.Option(None, "--media-root", help="Directory name for media/data on shared storage"),
    enabled: Optional[bool] = typer.Option(None, "--enabled/--disabled", help="Enable/disable shared storage for this lab"),
    auto_detect: Optional[bool] = typer.Option(None, "--auto-detect/--no-auto-detect", help="Enable/disable automatic detection"),
):
    """Configure shared storage settings for the current lab."""
    lab_manager = _get_lab_manager()

    if lab_manager.current_lab is None:
        print("Error: No lab loaded. Use 'mus1 lab load <lab_id>' or 'mus1 lab activate <lab_id>' first.")
        raise typer.Exit(code=1)

    try:
        lab_manager.set_shared_storage(
            mount_point=mount_point,
            volume_name=volume_name,
            projects_root=projects_root,
            media_root=media_root,
            enabled=enabled,
            auto_detect=auto_detect
        )
        print(f"Updated shared storage configuration for lab '{lab_manager.current_lab.metadata.name}'")

        # Show current configuration
        storage = lab_manager.current_lab.shared_storage
        print("\nCurrent shared storage configuration:")
        print(f"  Enabled: {storage.enabled}")
        print(f"  Mount point: {storage.mount_point or 'Not set'}")
        print(f"  Volume name: {storage.volume_name or 'Not set'}")
        print(f"  Projects root: {storage.projects_root}")
        print(f"  Media root: {storage.media_root}")
        print(f"  Auto-detect: {storage.auto_detect}")

    except Exception as e:
        print(f"Error configuring shared storage: {e}")
        raise typer.Exit(code=1)


###############################################################################
# workers management (typed in ProjectState.workers)
###############################################################################


def _load_project_for_workers(project_path: Path) -> tuple[StateManager, ProjectManager]:
    state_manager, _, _, project_manager = _get_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    return state_manager, project_manager


@workers_app.command("list", help="[DEPRECATED] Use 'mus1 lab status' instead")
def workers_list(project_path: Path = typer.Argument(..., help="Path to MUS1 project")):
    print("ERROR: Project-level worker management is deprecated.")
    print("Use 'mus1 lab status' to see lab-level workers.")
    print("Use 'mus1 lab add-worker' to add workers to labs.")
    raise typer.Exit(code=1)


@workers_app.command("add", help="[DEPRECATED] Use 'mus1 lab add-worker' instead")
def workers_add(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", help="Display name for the worker"),
    ssh_alias: str = typer.Option(..., "--ssh-alias", help="Host alias from ~/.ssh/config"),
    role: Optional[str] = typer.Option(None, help="Optional role tag (e.g., compute, storage)"),
    provider: str = typer.Option("ssh", help="Provider for executing commands: ssh|wsl|local|ssh-wsl", show_default=True),
    test: bool = typer.Option(False, help="Test SSH connectivity to the alias (BatchMode)")
):
    print("ERROR: Project-level worker management is deprecated.")
    print("Use 'mus1 lab add-worker' to add workers to labs.")
    raise typer.Exit(code=1)


@workers_app.command("detect-os", help="[DEPRECATED] Worker management moved to labs")
def workers_detect_os(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", "-n", help="Worker name to probe"),
    timeout: int = typer.Option(10, "--timeout", help="Timeout in seconds for SSH commands"),
):
    print("ERROR: Project-level worker management is deprecated.")
    print("Worker management has moved to labs. Use 'mus1 lab add-worker' to add workers.")
    raise typer.Exit(code=1)


@workers_app.command("remove", help="[DEPRECATED] Worker management moved to labs")
def workers_remove(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Argument(..., help="Worker name to remove"),
):
    print("ERROR: Project-level worker management is deprecated.")
    print("Worker management has moved to labs. Use lab-level commands instead.")
    raise typer.Exit(code=1)


@workers_app.command("run", help="Run a command on a lab worker")
def workers_run(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", "-n", help="Worker name to use"),
    command: List[str] = typer.Argument(..., metavar="COMMAND...", help="Command (and args) to execute remotely. Use '--' to separate from options."),
    cwd: Optional[Path] = typer.Option(None, "--cwd", help="Remote working directory"),
    env: Optional[List[str]] = typer.Option(None, "--env", help="Environment variables as KEY=VALUE; repeat for multiple"),
    timeout: Optional[int] = typer.Option(None, "--timeout", help="Timeout in seconds"),
    tty: bool = typer.Option(False, "--tty", help="Allocate a TTY (ssh -tt)"),
):
    # This one we can keep but redirect to use lab workers
    _, project_manager = _load_project_for_workers(project_path)

    try:
        workers = project_manager.get_workers()
        worker = next(w for w in workers if w.name == name)
    except StopIteration:
        raise typer.BadParameter(f"No worker named '{name}' found in associated lab")
    except RuntimeError as e:
        print(f"Error: {e}")
        print("Make sure the project is associated with a lab using 'mus1 project associate-lab'")
        raise typer.Exit(code=1)

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
    state_manager, _, _, project_manager = _get_managers()
    if not project_path.exists():
        raise typer.BadParameter(f"Project not found: {project_path}")
    project_manager.load_project(project_path)
    return state_manager, project_manager


@targets_app.command("list", help="[DEPRECATED] Use 'mus1 lab status' instead")
def targets_list(project_path: Path = typer.Argument(..., help="Path to MUS1 project")):
    print("ERROR: Project-level target management is deprecated.")
    print("Use 'mus1 lab status' to see lab-level scan targets.")
    print("Use 'mus1 lab add-target' to add targets to labs.")
    raise typer.Exit(code=1)


@targets_app.command("add", help="[DEPRECATED] Use 'mus1 lab add-target' instead")
def targets_add(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Option(..., "--name", help="Target name"),
    kind: str = typer.Option(..., "--kind", help="local|ssh|wsl"),
    roots: List[Path] = typer.Option(..., "--root", help="Root(s) to scan; repeat for multiple"),
    ssh_alias: Optional[str] = typer.Option(None, "--ssh-alias", help="SSH alias for ssh/wsl targets"),
):
    print("ERROR: Project-level target management is deprecated.")
    print("Use 'mus1 lab add-target' to add scan targets to labs.")
    raise typer.Exit(code=1)


@targets_app.command("remove", help="[DEPRECATED] Target management moved to labs")
def targets_remove(
    project_path: Path = typer.Argument(..., help="Path to MUS1 project"),
    name: str = typer.Argument(..., help="Target name to remove"),
):
    print("ERROR: Project-level target management is deprecated.")
    print("Target management has moved to labs. Use lab-level commands instead.")
    raise typer.Exit(code=1)

###############################################################################
# project scan-from-targets
###############################################################################


"""Deprecated: 'scan-from-targets' merged into 'ingest' via --target option."""

@project_app.command("media-index", help="Index loose media in <project>/media: create per-recording folders and metadata.json; register as unassigned.")
def project_media_index(
    project_path: Path = typer.Argument(..., help="Existing MUS1 project directory"),
    progress: bool = typer.Option(True, help="Show progress"),
    provenance: str = typer.Option("scan_and_move", "--provenance", help="Provenance label to store in metadata"),
):
    state_manager, plugin_manager, data_manager, project_manager = _get_managers()

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
    state_manager, plugin_manager, data_manager, project_manager = _get_managers()
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

@app.command("credentials-set", help="[DEPRECATED] Use 'mus1 lab add-credential' instead")
def credentials_set(
    alias: str = typer.Argument(..., help="SSH alias name (matches ScanTarget.ssh_alias)"),
    user: Optional[str] = typer.Option(None, "--user", help="Username for SSH"),
    identity_file: Optional[Path] = typer.Option(None, "--identity-file", help="Path to SSH private key"),
):
    print("ERROR: Per-user credentials management is deprecated.")
    print("Use 'mus1 lab add-credential' to add credentials to labs.")
    raise typer.Exit(code=1)


@app.command("credentials-list", help="[DEPRECATED] Use 'mus1 lab status' instead")
def credentials_list():
    print("ERROR: Per-user credentials management is deprecated.")
    print("Use 'mus1 lab status' to see lab-level credentials.")
    raise typer.Exit(code=1)


@app.command("credentials-remove", help="[DEPRECATED] Credentials management moved to labs")
def credentials_remove(alias: str = typer.Argument(..., help="SSH alias name")):
    print("ERROR: Per-user credentials management is deprecated.")
    print("Credentials management has moved to labs. Use lab-level commands instead.")
    raise typer.Exit(code=1)


# -----------------------------------------------------------------------------
# assembly-driven scan by experiments (CSV-guided)
# -----------------------------------------------------------------------------

"""Deprecated lab-specific CSV-guided assembly scan removed per roadmap; use 'project assembly run'."""


# -----------------------------------------------------------------------------
# CSV → subjects + experiments (non-interactive)
# -----------------------------------------------------------------------------

"""Deprecated lab-specific CSV → experiments command removed per roadmap; use 'project assembly run'."""


"""Deprecated lab-specific link-media-by-csv command removed per roadmap; use 'project assembly run'."""

# -----------------------------------------------------------------------------
# master media list management (root-level)
# -----------------------------------------------------------------------------

"""Deprecated master media CLI removed; Master Project concept is in development."""


"""Deprecated master media CLI removed; Master Project concept is in development."""