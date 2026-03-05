"""
Simplified MUS1 CLI - Core operations only.

This replaces the 2910-line grab-bag CLI with focused commands.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import typer
from rich import print as rich_print
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
import json
import platform
# from datetime import datetime  # not needed at module scope
import subprocess

from .metadata import ProjectConfig, SubjectDTO, ExperimentDTO, ColonyDTO, LabDTO
from .config_manager import get_config_manager, get_config
from .repository import SubjectRepository, ExperimentRepository
from .schema import Database
from .setup_service import (
    get_setup_service, MUS1RootLocationDTO,
    UserProfileDTO, SharedStorageDTO
)

app = typer.Typer(
    help="MUS1 - Simple video analysis system",
    add_completion=False,
)

# Setup subcommand group
setup_app = typer.Typer(help="Setup and configuration commands")
app.add_typer(setup_app, name="setup")

# Lab subcommand group
lab_app = typer.Typer(help="Lab and colony management commands")
app.add_typer(lab_app, name="lab")

# Project subcommand group
project_app = typer.Typer(help="Project management commands")
app.add_typer(project_app, name="project")

# Import subcommand group
import_app = typer.Typer(help="Dataset import commands")
app.add_typer(import_app, name="import")

# Web subcommand group
web_app = typer.Typer(help="Web (Streamlit) tools")
app.add_typer(web_app, name="web")

# Runs subcommand group
runs_app = typer.Typer(help="Run registry and run directory helpers")
app.add_typer(runs_app, name="runs")

# ===========================================
# CORE COMMANDS
# ===========================================

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """MUS1 - Web-based experiment browser and analysis tool."""
    if ctx.invoked_subcommand is None:
        rich_print("[bold blue]MUS1[/bold blue] - Experiment browser and analysis tool")
        rich_print("Use 'mus1 --help' for available commands")
        rich_print("Launch the web app: mus1 web experiment-browser")

# ===========================================
# RUN REGISTRY COMMANDS
# ===========================================

def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_slug(s: str) -> str:
    out = []
    for ch in str(s).strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        elif ch.isspace():
            out.append("_")
        # else drop
    slug = "".join(out).strip("._-")
    return slug or "run"


def _make_run_id(kind: str) -> str:
    from datetime import datetime, timezone
    import uuid

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    k = _safe_slug(kind)
    return f"{k}_{ts}_{short}"


@runs_app.command("init")
def runs_init(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
) -> None:
    """Initialize project-scoped runs root under `<project_path>/runs/`."""
    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    runs_root = project_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    rich_print("[green]✓[/green] Runs root ready")
    rich_print(f"[blue]ℹ[/blue] runs_root: {runs_root}")


@runs_app.command("new")
def runs_new(
    kind: str = typer.Argument(..., help="Run kind (e.g. ezm_unet, ml_tracking)"),
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    name: Optional[str] = typer.Option(None, help="Optional short run name/label"),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON only"),
) -> None:
    """Create a new run directory under `<project_path>/runs/<kind>/<run_id>/` and index it into the DB."""
    from .repository import get_repository_factory

    kind_slug = _safe_slug(kind)
    run_id = _make_run_id(kind_slug)

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)

    run_dir = project_path / "runs" / kind_slug / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    status = {
        "kind": kind_slug,
        "run_id": run_id,
        "state": "created",
        "name": name,
        "created_at": _utc_now_iso(),
    }
    (run_dir / "run_status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    meta = {
        "kind": kind_slug,
        "run_id": run_id,
        "name": name,
        "project_path": str(project_path),
        "run_dir": str(run_dir),
        "created_at": status["created_at"],
    }
    repos.external_artifacts.add(kind=f"{kind_slug}_run_dir", path=str(run_dir), meta=meta)

    if as_json:
        print(json.dumps({"kind": kind_slug, "run_id": run_id, "run_dir": str(run_dir)}))
        return

    rich_print("[green]✓[/green] Created run")
    rich_print(f"[blue]ℹ[/blue] kind: {kind_slug}")
    rich_print(f"[blue]ℹ[/blue] run_id: {run_id}")
    rich_print(f"[blue]ℹ[/blue] dir: {run_dir}")


@runs_app.command("list")
def runs_list(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    kind: Optional[str] = typer.Option(None, help="Filter by kind"),
    limit: int = typer.Option(20, help="Max entries to show (most recent)"),
) -> None:
    """Show the most recent DB-indexed run directories."""
    from .schema import ExternalArtifactModel

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()

    kind_slug = _safe_slug(kind) if kind else None
    kind_key = f"{kind_slug}_run_dir" if kind_slug else None

    with db.get_session() as session:
        q = session.query(ExternalArtifactModel).filter(ExternalArtifactModel.kind.like("%_run_dir"))
        if kind_key:
            q = q.filter(ExternalArtifactModel.kind == kind_key)
        q = q.order_by(ExternalArtifactModel.created_at.desc()).limit(int(limit))
        rows = q.all()

    if not rows:
        rich_print("[yellow]⚠[/yellow] No runs found.")
        return

    table = Table(title="Runs (most recent first)")
    table.add_column("kind", style="cyan")
    table.add_column("run_id", style="white")
    table.add_column("created_at", style="white")
    table.add_column("name", style="white")
    table.add_column("run_dir", style="green")
    for r in rows:
        try:
            meta = json.loads(r.meta_json or "{}")
        except Exception:
            meta = {}
        table.add_row(
            str(r.kind).removesuffix("_run_dir"),
            str(meta.get("run_id", "")),
            str(getattr(r, "created_at", "") or ""),
            str(meta.get("name", "")) if meta.get("name") else "",
            str(r.path),
        )
    rich_print(table)

# ===========================================
# ENHANCED PROJECT MANAGEMENT
# ===========================================

@project_app.command("init")
def init_project(
    name: str = typer.Argument(..., help="Project name"),
    path: Optional[Path] = typer.Option(None, help="Project directory"),
    lab_id: Optional[str] = typer.Option(None, help="Associate project with a lab"),
    use_shared: bool = typer.Option(False, "--use-shared", help="Use configured shared storage"),
    shared_root: Optional[Path] = typer.Option(None, help="Specific shared root path"),
):
    """Initialize a new MUS1 project with lab association and shared storage support."""
    _ = get_config_manager()

    # Determine project path
    if not path:
        if use_shared or shared_root:
            # Use provided shared_root explicitly (dev convenience); otherwise fall back to default user projects dir
            if shared_root:
                project_path = shared_root / "Projects" / name
            else:
                default_dir = get_config("user.default_projects_dir", str(Path.home() / "Documents" / "MUS1" / "Projects"))
                project_path = Path(default_dir) / name
        else:
            # Use default user projects directory
            default_dir = get_config("user.default_projects_dir", str(Path.home() / "Documents" / "MUS1" / "Projects"))
            project_path = Path(default_dir) / name
    else:
        project_path = path

    # Check for global project name uniqueness
    from .project_discovery_service import get_project_discovery_service
    discovery_service = get_project_discovery_service()
    existing_project_path = discovery_service.find_project_path(name)
    if existing_project_path:
        rich_print(f"[red]✗[/red] A project named '{name}' already exists at: {existing_project_path}")
        rich_print("[blue]ℹ[/blue] Please choose a different name or delete the existing project first")
        raise typer.Exit(1)

    # Check if project already exists at target location
    if (project_path / "mus1.db").exists() or (project_path / "project.json").exists():
        rich_print(f"[red]✗[/red] Project already exists at {project_path}")
        raise typer.Exit(1)

    # Validate lab association
    if lab_id:
        setup_service = get_setup_service()
        labs = setup_service.get_labs()
        if lab_id not in labs:
            rich_print(f"[red]✗[/red] Lab '{lab_id}' not found")
            rich_print("[blue]ℹ[/blue] Run 'mus1 lab list' to see available labs")
            raise typer.Exit(1)

    # Create project directory
    project_path.mkdir(parents=True, exist_ok=True)

    # Initialize SQLite database
    db_path = project_path / "mus1.db"
    db = Database(str(db_path))
    db.create_tables()

    # Create project configuration
    config = ProjectConfig(
        name=name,
        shared_root=shared_root if use_shared else None,
        lab_id=lab_id
    )

    # Save project config as JSON for compatibility
    config_path = project_path / "project.json"
    with open(config_path, 'w') as f:
        json.dump({
            "name": config.name,
            "shared_root": str(config.shared_root) if config.shared_root else None,
            "lab_id": config.lab_id,
            "date_created": config.date_created.isoformat(),
            "database_path": str(db_path)
        }, f, indent=2)

    # Register project with lab if specified
    if lab_id:
        try:
            setup_service.add_lab_project(lab_id, name, str(project_path))
        except Exception as e:
            rich_print(f"[yellow]⚠[/yellow] Could not register project with lab: {e}")
            rich_print("[blue]ℹ[/blue] Project created but lab association may need manual setup")

    rich_print("[green]✓[/green] Project created successfully!")
    rich_print(f"[blue]ℹ[/blue] Name: {name}")
    rich_print(f"[blue]ℹ[/blue] Path: {project_path}")
    rich_print(f"[blue]ℹ[/blue] Database: {db_path}")
    if lab_id:
        rich_print(f"[blue]ℹ[/blue] Associated with lab: {lab_id}")
    if config.shared_root:
        rich_print(f"[blue]ℹ[/blue] Shared root: {config.shared_root}")

    rich_print("\n[bold]Next steps:[/bold]")
    rich_print(f"1. Add subjects: 'mus1 add-subject <id> --project-path \"{project_path}\"'")
    rich_print(f"2. Add experiments: 'mus1 add-experiment <id> <subject_id> --project-path \"{project_path}\"'")
    rich_print(f"3. Import data: 'mus1 project import-data \"{project_path}\"'")

@project_app.command("list")
def list_projects():
    """List all MUS1 projects from configured locations."""
    _ = get_config_manager()

    # Get projects from user configuration
    labs = get_config("labs", scope="user") or {}
    projects_found = []

    # Collect projects from labs
    for lab_id, lab_config in labs.items():
        lab_projects = lab_config.get("projects", [])
        for project in lab_projects:
            projects_found.append({
                "name": project["name"],
                "path": project["path"],
                "lab": lab_id,
                "created": project.get("created_date", "Unknown"),
                "source": "lab_config"
            })

    # Also scan user default projects directory
    default_dirs = [
        get_config("user.default_projects_dir", str(Path.home() / "Documents" / "MUS1" / "Projects"))
    ]

    for dir_path in default_dirs:
        if dir_path:
            dir_path = Path(dir_path)
            if dir_path.exists():
                projects_dir = dir_path
                if projects_dir.exists():
                    for item in projects_dir.iterdir():
                        if item.is_dir() and (item / "mus1.db").exists():
                            # Check if already found in lab config
                            already_found = any(p["path"] == str(item) for p in projects_found)
                            if not already_found:
                                projects_found.append({
                                    "name": item.name,
                                    "path": str(item),
                                    "lab": "Unknown",
                                    "created": "Unknown",
                                    "source": "filesystem"
                                })

    if not projects_found:
        rich_print("[yellow]⚠[/yellow] No projects found")
        rich_print("[blue]ℹ[/blue] Create your first project with 'mus1 project init \"My Project\"'")
        return

    table = Table(title="MUS1 Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Lab", style="white")
    table.add_column("Path", style="white")
    table.add_column("Created", style="white")
    table.add_column("Source", style="green")

    for project in projects_found:
        table.add_row(
            project["name"],
            project["lab"],
            project["path"],
            project["created"][:10] if project["created"] != "Unknown" else "Unknown",
            project["source"]
        )

    rich_print(table)

@project_app.command("status")
def project_status(
    path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Show detailed project status."""
    config_path = path / "project.json"
    db_path = path / "mus1.db"

    if not config_path.exists() and not db_path.exists():
        rich_print(f"[red]✗[/red] No MUS1 project found at {path}")
        return

    # Load project config
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)

    # Load database stats
    stats = {"subjects": 0, "experiments": 0, "videos": 0}
    if db_path.exists():
        try:
            db = Database(str(db_path))
            stats["subjects"] = len(SubjectRepository(db).find_all())
            stats["experiments"] = len(ExperimentRepository(db).find_all())
            # Note: VideoFile repository not implemented yet, so we'll skip videos for now
        except Exception as e:
            rich_print(f"[yellow]⚠[/yellow] Could not read database: {e}")

    rich_print(f"[bold]Project:[/bold] {config.get('name', path.name)}")
    rich_print(f"[bold]Path:[/bold] {path}")
    rich_print(f"[bold]Created:[/bold] {config.get('date_created', 'Unknown')[:10] if config.get('date_created') else 'Unknown'}")
    if config.get('lab_id'):
        rich_print(f"[bold]Lab:[/bold] {config['lab_id']}")
    if config.get('shared_root'):
        rich_print(f"[bold]Shared root:[/bold] {config['shared_root']}")

    rich_print(f"\n[bold]Database:[/bold] {db_path}")
    rich_print(f"[bold]Subjects:[/bold] {stats['subjects']}")
    rich_print(f"[bold]Experiments:[/bold] {stats['experiments']}")
    rich_print(f"[bold]Videos:[/bold] {stats['videos']}")

@project_app.command("import-kpms-recordings")
def import_kpms_recordings_cmd(
    csv_paths: str = typer.Argument(..., help="Comma-separated paths to recordings CSV files"),
    workspace_root: Path = typer.Option(..., "--workspace-root", help="Workspace root directory"),
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Import KPMS recordings metadata from CSV files."""
    from .importers.kpms_recordings import import_kpms_recordings
    
    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No database found at {db_path}")
        rich_print("[blue]ℹ[/blue] Run 'mus1 project init' first")
        raise typer.Exit(1)
    
    # Parse CSV paths
    csv_file_paths = [Path(p.strip()) for p in csv_paths.split(',')]
    
    # Validate paths
    for csv_path in csv_file_paths:
        if not csv_path.exists():
            rich_print(f"[red]✗[/red] CSV file not found: {csv_path}")
            raise typer.Exit(1)
    
    if not workspace_root.exists():
        rich_print(f"[red]✗[/red] Workspace root not found: {workspace_root}")
        raise typer.Exit(1)
    
    rich_print(f"[blue]ℹ[/blue] Importing {len(csv_file_paths)} CSV file(s)...")
    rich_print(f"[blue]ℹ[/blue] Workspace root: {workspace_root}")
    rich_print(f"[blue]ℹ[/blue] Database: {db_path}")
    
    try:
        from .repository import get_repository_factory
        db = Database(str(db_path))
        db.create_tables()
        repos = get_repository_factory(db)

        stats = import_kpms_recordings(repos, csv_file_paths, workspace_root)
        
        rich_print("\n[bold green]✓ Import completed![/bold green]")
        rich_print(f"\n[bold]Summary:[/bold]")
        rich_print(f"  Total artifacts added: {stats['total_artifacts']}")
        rich_print(f"  Linked to experiments: {stats['total_linked_to_experiment']}")
        rich_print(f"  Linked to subjects: {stats['total_linked_to_subject']}")
        rich_print(f"  Unlinked: {stats['total_unlinked']}")
        
        if stats['sources']:
            rich_print(f"\n[bold]By source:[/bold]")
            for source_name, source_stats in stats['sources'].items():
                if 'error' in source_stats:
                    rich_print(f"  [red]✗[/red] {source_name}: {source_stats['error']}")
                else:
                    rich_print(f"  [green]✓[/green] {source_name}:")
                    rich_print(f"    Artifacts: {source_stats['artifacts_added']}")
                    rich_print(f"    Linked to exp: {source_stats['linked_to_experiment']}")
                    rich_print(f"    Linked to subject: {source_stats['linked_to_subject']}")
                    rich_print(f"    Unlinked: {source_stats['unlinked']}")
    
    except Exception as e:
        rich_print(f"[red]✗[/red] Import failed: {e}")
        import traceback
        rich_print(traceback.format_exc())
        raise typer.Exit(1)


@import_app.command("workspace-db-sync")
def workspace_db_sync(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    workspace_root: Path = typer.Option(..., help="WDMOSEQ2 repo root (contains data/, statistics_workspace/, keypoint_moseq_workspace/, etc.)"),
    kpms_csvs: Optional[str] = typer.Option(
        None,
        help="Comma-separated KPMS recordings.csv paths (defaults to keypoint_moseq_workspace/_reruns/... under workspace_root)",
    ),
    include_arena_zones: bool = typer.Option(
        False,
        help="Also index arena annotation JSONs (opt-in; disabled by default to keep sync metadata-focused).",
    ),
    include_run_indexes: bool = typer.Option(
        False,
        help="Also index project run output dirs (EZM U-Net + ML tracking) (opt-in; disabled by default).",
    ),
):
    """Sync workspace metadata into MUS1 DB from experiment_data (canonical source)."""
    from .repository import get_repository_factory
    from .importers.kpms_recordings import import_kpms_recordings
    from .importers.arena_zones import index_arena_zone_jsons
    from .importers.experiment_data import import_experiment_data
    from .importers.ezm_unet_runs import index_ezm_unet_runs
    from .importers.ml_tracking_runs import index_ml_tracking_runs

    if not project_path.exists():
        rich_print(f"[red]✗[/red] Project path does not exist: {project_path}")
        raise typer.Exit(1)

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    if kpms_csvs is None:
        kpms_paths = [
            workspace_root
            / "keypoint_moseq_workspace"
            / "_reruns"
            / "20260122_trim30s_ezm"
            / "metadata"
            / "recordings.csv",
            workspace_root
            / "keypoint_moseq_workspace"
            / "_reruns"
            / "20260122_trim30s_nor_nof"
            / "metadata"
            / "recordings.csv",
        ]
    else:
        kpms_paths = [Path(p.strip()) for p in kpms_csvs.split(",") if p.strip()]

    db = Database(str(db_path), use_fast_pragmas=True)
    db.create_tables()
    repos = get_repository_factory(db)

    qc_added = 0
    def _qc(code: str, details: dict):
        nonlocal qc_added
        try:
            repos.qc_events.add(scope="import", code=code, details=details)
            qc_added += 1
        except Exception:
            # If QC insert fails, don't block the sync.
            pass

    rich_print("[bold]Workspace DB sync[/bold]")
    rich_print(f"[blue]ℹ[/blue] Project: {project_path}")
    rich_print(f"[blue]ℹ[/blue] Workspace root: {workspace_root}")

    # 1) Experiment data (canonical source: data/experiment_data/{OF,EZM,NOR,NOF,RR})
    ed_root = project_path / "experiment_data"
    if not ed_root.is_dir():
        _qc("MISSING_INPUT", {"kind": "experiment_data", "path": str(ed_root)})
        rich_print(f"[yellow]⚠[/yellow] Missing experiment_data: {ed_root}")
        ed_stats = None
    else:
        ed_stats = import_experiment_data(
            repos,
            experiment_data_root=ed_root,
            tasks=("OF", "EZM", "NOR", "NOF", "RR"),
        )

    # 2) KPMS trim30s recordings index
    existing_kpms = [p for p in kpms_paths if p.exists()]
    missing_kpms = [p for p in kpms_paths if not p.exists()]
    for p in missing_kpms:
        _qc("MISSING_INPUT", {"kind": "kpms_recordings_csv", "path": str(p)})
        rich_print(f"[yellow]⚠[/yellow] Missing KPMS recordings CSV: {p}")
    if existing_kpms:
        kpms_stats = import_kpms_recordings(repos, existing_kpms, workspace_root)
    else:
        kpms_stats = None

    rich_print("\n[bold green]✓ Sync complete[/bold green]")
    if ed_stats is not None:
        rich_print(f"[blue]ℹ[/blue] Experiment_data JSONs scanned: {ed_stats.jsons_scanned}")
        rich_print(f"[blue]ℹ[/blue] Subjects upserted: {ed_stats.subjects_upserted}")
        rich_print(f"[blue]ℹ[/blue] Experiments upserted: {ed_stats.experiments_upserted}")
        rich_print(f"[blue]ℹ[/blue] Artifacts added: {ed_stats.artifacts_added}")
        rich_print(f"[blue]ℹ[/blue] RR assay_sessions created: {ed_stats.assay_sessions_created}")
        rich_print(f"[blue]ℹ[/blue] RR assay_measurements created: {ed_stats.assay_measurements_created}")
    if kpms_stats is not None:
        rich_print(f"[blue]ℹ[/blue] KPMS artifacts added: {kpms_stats['total_artifacts']}")
        rich_print(f"[blue]ℹ[/blue] KPMS linked to experiments: {kpms_stats['total_linked_to_experiment']}")
        rich_print(f"[blue]ℹ[/blue] KPMS linked to subjects: {kpms_stats['total_linked_to_subject']}")
        rich_print(f"[blue]ℹ[/blue] KPMS unlinked: {kpms_stats['total_unlinked']}")
    if ed_stats is not None:
        rich_print(f"[blue]ℹ[/blue] Experiment_data JSONs scanned: {ed_stats.jsons_scanned}")
        rich_print(f"[blue]ℹ[/blue] Experiment_data subjects upserted: {ed_stats.subjects_upserted}")
        rich_print(f"[blue]ℹ[/blue] Experiment_data experiments upserted: {ed_stats.experiments_upserted}")
        rich_print(f"[blue]ℹ[/blue] Experiment_data artifacts added: {ed_stats.artifacts_added}")
    if qc_added:
        rich_print(f"[yellow]⚠[/yellow] QC events added (sync inputs): {qc_added}")

    # Optional 4) Arena JSON indexing
    arena_stats = None
    if include_arena_zones:
        repo_root = Path(__file__).resolve().parents[3]
        contracts_root = repo_root / "workspace" / "contracts" / "ml_tracking_metadata_model"
        session_index_csv = contracts_root / "index" / "session_index_filtered.csv"
        arena_root = repo_root / "workspace" / "arena_zones"
        ezm_dir = arena_root / "ezm_per_video_v2"
        nor_nof_dir = arena_root / "nor_nof_per_video_v2"
        if not session_index_csv.exists():
            _qc("MISSING_INPUT", {"kind": "session_index_filtered_csv", "path": str(session_index_csv)})
            rich_print(f"[yellow]⚠[/yellow] Missing session index CSV for arena indexing: {session_index_csv}")
        else:
            arena_stats = index_arena_zone_jsons(
                repos,
                workspace_root=workspace_root,
                session_index_csv=session_index_csv,
                ezm_dir=ezm_dir,
                nor_nof_dir=nor_nof_dir,
            )

    # Optional 5) Run dir indexing (project-scoped runs only)
    ezm_run_stats = None
    ml_run_stats = None
    if include_run_indexes:
        ezm_run_stats = index_ezm_unet_runs(
            repos,
            workspace_root=workspace_root,
            runs_root=project_path / "runs" / "ezm_unet",
            only_latest=False,
        )
        ml_run_stats = index_ml_tracking_runs(
            repos,
            runs_root=project_path / "runs" / "ml_tracking",
            only_latest=False,
        )

    if arena_stats is not None:
        rich_print(f"[blue]ℹ[/blue] Arena JSONs scanned: {arena_stats.total_jsons}")
        rich_print(f"[blue]ℹ[/blue] Arena artifacts added: {arena_stats.artifacts_added}")
        rich_print(f"[blue]ℹ[/blue] Arena artifacts updated linkage: {arena_stats.artifacts_updated_linkage}")
        rich_print(f"[blue]ℹ[/blue] Arena QC events added: {arena_stats.qc_events_added}")
    if ezm_run_stats is not None:
        rich_print(f"[blue]ℹ[/blue] EZM runs indexed: {ezm_run_stats.runs_indexed}")
        rich_print(f"[blue]ℹ[/blue] EZM run artifacts added: {ezm_run_stats.artifacts_added}")
    if ml_run_stats is not None:
        rich_print(f"[blue]ℹ[/blue] ML tracking runs indexed: {ml_run_stats.runs_indexed}")
        rich_print(f"[blue]ℹ[/blue] ML tracking artifacts added: {ml_run_stats.artifacts_added}")

# ===========================================
# IMPORT COMMANDS
# ===========================================

@import_app.command("moseq2-workspace")
def import_moseq2_workspace(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    workspace_root: Path = typer.Option(..., help="MoSeq2 workspace root"),
    index_csv: Path = typer.Option(
        None,
        help="Compiled session index CSV (defaults to apps/mus1/workspace/contracts/ml_tracking_metadata_model/index/session_index_filtered.csv)",
    ),
    check_paths_exist: bool = typer.Option(True, help="Record QC events for missing paths"),
):
    """Import MoSeq2 workspace session index into a MUS1 project DB (path-only; non-fatal QC)."""
    from .schema import Database
    from .repository import get_repository_factory
    from .importers.moseq2_workspace import import_session_index

    if not project_path.exists():
        rich_print(f"[red]✗[/red] Project path does not exist: {project_path}")
        raise typer.Exit(1)

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    if index_csv is None:
        repo_root = Path(__file__).resolve().parents[3]
        contracts_root = repo_root / "workspace" / "contracts" / "ml_tracking_metadata_model"
        index_csv = contracts_root / "index" / "session_index_filtered.csv"

    if not index_csv.exists():
        rich_print(f"[red]✗[/red] Index CSV not found: {index_csv}")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)

    stats = import_session_index(
        repos,
        workspace_root=workspace_root,
        session_index_csv=index_csv,
        check_paths_exist=check_paths_exist,
    )

    rich_print("[green]✓[/green] Import complete")
    rich_print(f"[blue]ℹ[/blue] Rows: {stats.rows_total}")
    rich_print(f"[blue]ℹ[/blue] Subjects upserted: {stats.subjects_upserted}")
    rich_print(f"[blue]ℹ[/blue] Experiments upserted: {stats.experiments_upserted}")
    rich_print(f"[blue]ℹ[/blue] Videos upserted: {stats.videos_upserted}")
    rich_print(f"[blue]ℹ[/blue] Artifacts added: {stats.artifacts_added}")
    rich_print(f"[blue]ℹ[/blue] QC events added: {stats.qc_events_added}")


@import_app.command("arena-zones")
def import_arena_zones(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    workspace_root: Path = typer.Option(..., help="MoSeq2 workspace root"),
    session_index_csv: Path = typer.Option(
        None,
        help="Session index CSV (defaults to apps/mus1/workspace/contracts/ml_tracking_metadata_model/index/session_index_filtered.csv)",
    ),
    ezm_dir: Path = typer.Option(
        None,
        help="Directory of EZM per-video zone JSONs (defaults to apps/mus1/workspace/arena_zones/ezm_per_video_v2)",
    ),
    nor_nof_dir: Path = typer.Option(
        None,
        help="Directory of NOR/NOF per-video ROI JSONs (defaults to apps/mus1/workspace/arena_zones/nor_nof_per_video_v2)",
    ),
):
    """Index arena annotation JSON outputs into MUS1 DB as external artifacts."""
    from .repository import get_repository_factory
    from .importers.arena_zones import index_arena_zone_jsons

    if session_index_csv is None:
        repo_root = Path(__file__).resolve().parents[3]
        contracts_root = repo_root / "workspace" / "contracts" / "ml_tracking_metadata_model"
        session_index_csv = contracts_root / "index" / "session_index_filtered.csv"
    if ezm_dir is None:
        repo_root = Path(__file__).resolve().parents[3]
        arena_zones_root = repo_root / "workspace" / "arena_zones"
        ezm_dir = arena_zones_root / "ezm_per_video_v2"
    if nor_nof_dir is None:
        repo_root = Path(__file__).resolve().parents[3]
        arena_zones_root = repo_root / "workspace" / "arena_zones"
        nor_nof_dir = arena_zones_root / "nor_nof_per_video_v2"

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    if not session_index_csv.exists():
        rich_print(f"[red]✗[/red] Session index CSV not found: {session_index_csv}")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)

    stats = index_arena_zone_jsons(
        repos,
        workspace_root=workspace_root,
        session_index_csv=session_index_csv,
        ezm_dir=ezm_dir,
        nor_nof_dir=nor_nof_dir,
    )

    rich_print("[green]✓[/green] Arena zones indexed")
    rich_print(f"[blue]ℹ[/blue] Total JSONs scanned: {stats.total_jsons}")
    rich_print(f"[blue]ℹ[/blue] Artifacts added: {stats.artifacts_added}")
    rich_print(f"[blue]ℹ[/blue] Artifacts skipped (existing): {stats.artifacts_skipped_existing}")
    rich_print(f"[blue]ℹ[/blue] Artifacts updated (linkage): {stats.artifacts_updated_linkage}")
    rich_print(f"[blue]ℹ[/blue] Linked to experiments: {stats.linked_to_experiment}")
    rich_print(f"[blue]ℹ[/blue] Unlinked: {stats.unlinked}")
    rich_print(f"[blue]ℹ[/blue] QC events added: {stats.qc_events_added}")


@import_app.command("ezm-unet-runs")
def import_ezm_unet_runs(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    workspace_root: Path = typer.Option(..., help="MoSeq2 workspace root (contains statistics_summaries/...)"),
    runs_root: Optional[Path] = typer.Option(
        None,
        help="Optional runs root dir (defaults to <project_path>/runs/ezm_unet)",
    ),
    only_latest: bool = typer.Option(False, help="Only index the latest train_* run directory"),
):
    """Index EZM open/closed U-Net run outputs into MUS1 DB (run provenance + worst_frames pointers)."""
    from .repository import get_repository_factory
    from .importers.ezm_unet_runs import index_ezm_unet_runs

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)

    # Canonical: project-scoped runs folder (Option A). No fallback scanning of the MoSeq2 workspace.
    if runs_root is None:
        runs_root = project_path / "runs" / "ezm_unet"

    stats = index_ezm_unet_runs(
        repos,
        workspace_root=workspace_root,
        runs_root=runs_root,
        only_latest=only_latest,
    )

    rich_print("[green]✓[/green] EZM U-Net runs indexed")
    rich_print(f"[blue]ℹ[/blue] Runs seen: {stats.runs_seen}")
    rich_print(f"[blue]ℹ[/blue] Runs indexed: {stats.runs_indexed}")
    rich_print(f"[blue]ℹ[/blue] Artifacts added: {stats.artifacts_added}")
    rich_print(f"[blue]ℹ[/blue] Artifacts skipped (existing): {stats.artifacts_skipped_existing}")
    rich_print(f"[blue]ℹ[/blue] QC events added: {stats.qc_events_added}")


@import_app.command("ml-tracking-runs")
def import_ml_tracking_runs(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    only_latest: bool = typer.Option(False, help="Only index the latest run directory"),
):
    """Index ML tracking run output directories into MUS1 DB (project-scoped runs)."""
    from .repository import get_repository_factory
    from .importers.ml_tracking_runs import index_ml_tracking_runs

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)

    runs_root = project_path / "runs" / "ml_tracking"
    stats = index_ml_tracking_runs(repos, runs_root=runs_root, only_latest=only_latest)

    rich_print("[green]✓[/green] ML tracking runs indexed")
    rich_print(f"[blue]ℹ[/blue] Runs seen: {stats.runs_seen}")
    rich_print(f"[blue]ℹ[/blue] Runs indexed: {stats.runs_indexed}")
    rich_print(f"[blue]ℹ[/blue] Artifacts added: {stats.artifacts_added}")
    rich_print(f"[blue]ℹ[/blue] Artifacts skipped (existing): {stats.artifacts_skipped_existing}")
    rich_print(f"[blue]ℹ[/blue] QC events added: {stats.qc_events_added}")


@web_app.command("experiment-browser")
def web_experiment_browser(
    project_path: Path = typer.Option(Path.cwd(), help="MUS1 project directory (contains mus1.db)"),
    port: int = typer.Option(8502, help="Streamlit server port"),
    address: str = typer.Option("127.0.0.1", help="Bind address (use 127.0.0.1 for SSH port-forwarding)"),
    workspace_root: Optional[Path] = typer.Option(None, help="Optional MoSeq2 workspace root (enables matching/suggestions)"),
):
    """Launch the MUS1 experiment browser (Streamlit)."""
    script_path = (Path(__file__).resolve().parents[1] / "web" / "experiment_browser.py").resolve()
    if not script_path.exists():
        raise typer.Exit(1)

    cmd = [
        "streamlit",
        "run",
        str(script_path),
        "--server.port",
        str(port),
        "--server.address",
        str(address),
        "--",
        "--project-path",
        str(project_path),
    ]
    if workspace_root is not None:
        cmd.extend(["--workspace-root", str(workspace_root)])

    rich_print("[blue]ℹ[/blue] Starting Streamlit experiment browser")
    rich_print(f"[blue]ℹ[/blue] DB project path: {project_path}")
    rich_print(f"[blue]ℹ[/blue] Port-forward example:")
    rich_print(f"  ssh -L {port}:localhost:{port} $USER@chinook04.alaska.edu")
    rich_print("")
    rich_print(f"[blue]ℹ[/blue] Running: {' '.join(cmd)}")

    # Streamlit parses its own args; app args after `--` are forwarded to the script.
    subprocess.run(cmd, check=True)

# ===========================================
# DATA MANAGEMENT
# ===========================================

@app.command("add-subject")
def add_subject(
    subject_id: str = typer.Argument(..., help="Subject ID"),
    sex: str = typer.Option("Unknown", help="Subject sex (M/F/Unknown)"),
    designation: str = typer.Option("experimental", help="Subject designation (experimental/breeding/culled)"),
    genotype: Optional[str] = typer.Option(None, help="Subject genotype"),
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Add a subject to the project."""
    # Validate input
    if sex not in ["M", "F", "Unknown"]:
        rich_print("[red]✗[/red] Sex must be M, F, or Unknown")
        return

    if designation not in ["experimental", "breeding", "culled"]:
        rich_print("[red]✗[/red] Designation must be experimental, breeding, or culled")
        return

    # Create DTO
    from .metadata import Sex, SubjectDesignation
    sex_enum = {"M": Sex.MALE, "F": Sex.FEMALE, "Unknown": Sex.UNKNOWN}[sex]
    designation_enum = {
        "experimental": SubjectDesignation.EXPERIMENTAL,
        "breeding": SubjectDesignation.BREEDING,
        "culled": SubjectDesignation.CULLED
    }[designation]

    subject_dto = SubjectDTO(
        id=subject_id,
        sex=sex_enum,
        designation=designation_enum,
        genotype=genotype
    )

    # Initialize database and repositories
    db_path = project_path / "mus1.db"
    db = Database(str(db_path))
    db.create_tables()

    # Get repositories
    from .repository import get_repository_factory
    repos = get_repository_factory(db)

    # Create domain subject (CLI subjects can exist without colonies)
    from .metadata import Subject
    subject_domain = Subject(
        id=subject_dto.id,
        colony_id=None,  # CLI subjects don't require colonies
        sex=subject_dto.sex,
        designation=subject_dto.designation,
        individual_genotype=subject_dto.individual_genotype
    )

    # Save subject using repository
    subject = repos.subjects.save(subject_domain)

    rich_print(f"[green]✓[/green] Added subject {subject.id}")
    if subject.genotype:
        rich_print(f"[blue]ℹ[/blue] Genotype: {subject.genotype}")

@app.command("import-rotarod")
def import_rotarod(
    project_path: Path = typer.Option(..., help="Target MUS1 project directory (contains mus1.db)"),
    csv_path: Path = typer.Option(..., help="Path to rotarod CSV file"),
    assay_type: str = typer.Option("rotarod", help="Assay type identifier"),
):
    """Import rotarod assay data from CSV into a MUS1 project DB."""
    from .schema import Database
    from .repository import get_repository_factory
    from .importers.rotarod import import_rotarod_csv

    if not project_path.exists():
        rich_print(f"[red]✗[/red] Project path does not exist: {project_path}")
        raise typer.Exit(1)

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No mus1.db found at: {db_path}")
        rich_print("[blue]ℹ[/blue] Create one with: mus1 project init \"<name>\" --path <project_path>")
        raise typer.Exit(1)

    if not csv_path.exists():
        rich_print(f"[red]✗[/red] CSV file not found: {csv_path}")
        raise typer.Exit(1)

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)

    stats = import_rotarod_csv(
        repos,
        csv_path=csv_path,
        assay_type=assay_type,
    )

    rich_print("[green]✓[/green] Import complete")
    rich_print(f"[blue]ℹ[/blue] Rows processed: {stats.rows_total}")
    rich_print(f"[blue]ℹ[/blue] Assay sessions created: {stats.assay_sessions_created}")
    rich_print(f"[blue]ℹ[/blue] Assay measurements created: {stats.assay_measurements_created}")
    rich_print(f"[blue]ℹ[/blue] Subjects created: {stats.subjects_created}")
    if stats.subjects_skipped > 0:
        rich_print(f"[yellow]⚠[/yellow] Subjects skipped: {stats.subjects_skipped}")
    if stats.errors > 0:
        rich_print(f"[yellow]⚠[/yellow] Errors encountered: {stats.errors}")

@app.command("add-experiment")
def add_experiment(
    experiment_id: str = typer.Argument(..., help="Experiment ID"),
    subject_id: str = typer.Argument(..., help="Subject ID"),
    experiment_type: str = typer.Argument(..., help="Experiment type"),
    date_recorded: str = typer.Option(..., help="Recording date (YYYY-MM-DD)"),
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Add an experiment to the project."""
    from datetime import datetime

    # Parse date
    try:
        recorded_date = datetime.fromisoformat(date_recorded)
    except ValueError:
        rich_print("[red]✗[/red] Invalid date format. Use YYYY-MM-DD")
        return

    # Create DTO
    experiment_dto = ExperimentDTO(
        id=experiment_id,
        subject_id=subject_id,
        experiment_type=experiment_type,
        date_recorded=recorded_date
    )

    # Initialize database and repositories
    db_path = project_path / "mus1.db"
    db = Database(str(db_path))
    db.create_tables()

    # Get repositories
    from .repository import get_repository_factory
    repos = get_repository_factory(db)

    # Convert DTO to domain object
    from .metadata import Experiment
    experiment_domain = Experiment(
        id=experiment_dto.id,
        subject_id=experiment_dto.subject_id,
        experiment_type=experiment_dto.experiment_type,
        date_recorded=experiment_dto.date_recorded,
        processing_stage=experiment_dto.processing_stage
    )

    # Save experiment using repository
    experiment = repos.experiments.save(experiment_domain)

    rich_print(f"[green]✓[/green] Added experiment {experiment.id}")
    rich_print(f"[blue]ℹ[/blue] Type: {experiment.experiment_type}")
    rich_print(f"[blue]ℹ[/blue] Subject: {experiment.subject_id}")

@app.command("list-subjects")
def list_subjects(
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """List all subjects in the project."""
    # Initialize database
    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print("[red]✗[/red] No database found. Run 'mus1 init' first.")
        return

    db = Database(str(db_path))
    from .repository import get_repository_factory
    repos = get_repository_factory(db)

    subjects = repos.subjects.find_all()
    if not subjects:
        rich_print("[yellow]⚠[/yellow] No subjects found")
        return

    rich_print(f"[bold]Subjects ({len(subjects)}):[/bold]")
    for subject in subjects:
        age_str = f", {subject.age_days}d old" if subject.age_days else ""
        genotype_str = f" - {subject.genotype}" if subject.genotype else ""
        designation_str = f" ({subject.designation.value})"
        rich_print(f"  {subject.id} ({subject.sex.value}){age_str}{genotype_str}{designation_str}")

@app.command("list-experiments")
def list_experiments(
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """List all experiments in the project."""
    # Initialize database
    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print("[red]✗[/red] No database found. Run 'mus1 init' first.")
        return

    db = Database(str(db_path))
    from .repository import get_repository_factory
    repos = get_repository_factory(db)

    experiments = repos.experiments.find_all()
    if not experiments:
        rich_print("[yellow]⚠[/yellow] No experiments found")
        return

    rich_print(f"[bold]Experiments ({len(experiments)}):[/bold]")
    for exp in experiments:
        status = "✓ Ready" if exp.is_ready_for_analysis else "⏳ Planned"
        rich_print(f"  {exp.id} - {exp.experiment_type} ({exp.subject_id}) [{status}]")

# ===========================================
# UTILITY COMMANDS
# ===========================================

@app.command("scan")
def scan_videos(
    path: Path = typer.Argument(..., help="Directory to scan"),
    output: Optional[Path] = typer.Option(None, help="Output JSON file"),
):
    """Scan directory for video files."""
    if not path.exists():
        rich_print(f"[red]✗[/red] Path {path} does not exist")
        return

    import json
    videos = []

    # Simple scan for common video extensions
    exts = {'.mp4', '.avi', '.mov', '.mkv', '.mpg'}
    for file_path in path.rglob('*'):
        if file_path.suffix.lower() in exts:
            videos.append({
                "path": str(file_path),
                "size": file_path.stat().st_size,
                "modified": file_path.stat().st_mtime
            })

    if output:
        with open(output, 'w') as f:
            json.dump(videos, f, indent=2)
        rich_print(f"[green]✓[/green] Found {len(videos)} videos, saved to {output}")
    else:
        rich_print(f"[green]✓[/green] Found {len(videos)} videos:")
        for video in videos[:5]:  # Show first 5
            rich_print(f"  {video['path']}")
        if len(videos) > 5:
            rich_print(f"  ... and {len(videos) - 5} more")

@app.command("test-kpms-import")
def test_kpms_import(
    csv_path: Path = typer.Argument(..., help="Path to a recordings CSV file"),
    workspace_root: Path = typer.Option(..., "--workspace-root", help="Workspace root directory"),
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Smoke test for KPMS recordings import (dry-run, shows what would be imported)."""
    from .importers.kpms_recordings import import_kpms_recordings_csv
    from .repository import get_repository_factory
    
    db_path = project_path / "mus1.db"
    if not db_path.exists():
        rich_print(f"[red]✗[/red] No database found at {db_path}")
        rich_print("[blue]ℹ[/blue] Run 'mus1 project init' first")
        raise typer.Exit(1)
    
    if not csv_path.exists():
        rich_print(f"[red]✗[/red] CSV file not found: {csv_path}")
        raise typer.Exit(1)
    
    if not workspace_root.exists():
        rich_print(f"[red]✗[/red] Workspace root not found: {workspace_root}")
        raise typer.Exit(1)
    
    rich_print("[blue]ℹ[/blue] Running smoke test (dry-run)...")
    rich_print(f"[blue]ℹ[/blue] CSV: {csv_path}")
    rich_print(f"[blue]ℹ[/blue] Workspace root: {workspace_root}")
    
    # Extract source name
    source_name = csv_path.parent.parent.name if csv_path.name == "recordings.csv" else csv_path.stem
    
    try:
        from .schema import Database
        db = Database(str(db_path))
        db.create_tables()
        repos = get_repository_factory(db)
        
        # Count before
        from .schema import ExternalArtifactModel
        with db.get_session() as session:
            before_count = session.query(ExternalArtifactModel).count()
        
        # Run import
        stats = import_kpms_recordings_csv(repos, csv_path, workspace_root, source_name)
        
        # Count after
        with db.get_session() as session:
            after_count = session.query(ExternalArtifactModel).count()
        
        rich_print("\n[bold green]✓ Smoke test passed![/bold green]")
        rich_print(f"\n[bold]Results:[/bold]")
        rich_print(f"  Artifacts added: {stats['artifacts_added']}")
        rich_print(f"  Linked to experiments: {stats['linked_to_experiment']}")
        rich_print(f"  Linked to subjects: {stats['linked_to_subject']}")
        rich_print(f"  Unlinked: {stats['unlinked']}")
        rich_print(f"  Total artifacts in DB: {before_count} -> {after_count}")
        
    except Exception as e:
        rich_print(f"[red]✗[/red] Smoke test failed: {e}")
        import traceback
        rich_print(traceback.format_exc())
        raise typer.Exit(1)

# ===========================================
# SETUP COMMANDS
# ===========================================

@setup_app.command("root")
def setup_mus1_root(
    path: Path = typer.Argument(..., help="Path to MUS1 root directory"),
    create: bool = typer.Option(True, help="Create directory if it doesn't exist"),
    copy_config: bool = typer.Option(True, help="Copy existing configuration to new location"),
):
    """Set up MUS1 root location for configuration and data storage."""
    setup_service = get_setup_service()

    # Check if already configured
    if setup_service.is_mus1_root_configured():
        existing_path = setup_service.get_mus1_root_path()
        rich_print(f"[yellow]⚠[/yellow] MUS1 root location already configured at: {existing_path}")
        if not Confirm.ask("Reconfigure MUS1 root location?"):
            rich_print("[blue]ℹ[/blue] Setup cancelled")
            return

    # Create DTO and run setup
    root_dto = MUS1RootLocationDTO(
        path=path,
        create_if_missing=create,
        copy_existing_config=copy_config
    )

    try:
        result = setup_service.setup_mus1_root_location(root_dto)

        if result["success"]:
            rich_print("[green]✓[/green] MUS1 root location configured successfully!")
            rich_print(f"[blue]ℹ[/blue] Root path: {result['path']}")
            rich_print(f"[blue]ℹ[/blue] Configuration saved to: {result['config_path']}")

            # Show created subdirectories
            subdirs = ["config", "logs", "cache", "temp"]
            rich_print("\n[blue]ℹ[/blue] Created subdirectories:")
            for subdir in subdirs:
                subdir_path = path / subdir
                if subdir_path.exists():
                    rich_print(f"  ✓ {subdir_path}")

            # Next steps
            rich_print("\n[bold]Next steps:[/bold]")
            rich_print("1. Run 'mus1 setup user' to configure your user profile")
            rich_print("2. Run 'mus1 setup shared' to configure shared storage")
            rich_print("3. Run 'mus1 lab create' to set up your first lab")
        else:
            rich_print(f"[red]✗[/red] {result['message']}")
            raise typer.Exit(1)

    except Exception as e:
        rich_print(f"[red]✗[/red] Setup failed: {e}")
        raise typer.Exit(1)


@setup_app.command("user")
def setup_user(
    name: Optional[str] = typer.Option(None, help="User's full name"),
    email: Optional[str] = typer.Option(None, help="User's email address"),
    organization: Optional[str] = typer.Option(None, help="Organization/Lab name"),
    default_projects_dir: Optional[Path] = typer.Option(None, help="Default projects directory"),
    default_shared_dir: Optional[Path] = typer.Option(None, help="Default shared storage directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing configuration"),
):
    """Set up user profile and default configuration."""
    setup_service = get_setup_service()

    # Check if user config already exists
    if setup_service.is_user_configured() and not force:
        existing_profile = setup_service.get_user_profile()
        user_name_display = existing_profile.name if existing_profile else "Unknown"
        rich_print(f"[yellow]⚠[/yellow] User configuration already exists for: {user_name_display}")
        if not Confirm.ask("Overwrite existing configuration?"):
            rich_print("[blue]ℹ[/blue] Setup cancelled")
            return

    # Interactive prompts if values not provided
    if not name:
        name = Prompt.ask("Enter your full name")
    if not email:
        email = Prompt.ask("Enter your email address")
    if not organization:
        organization = Prompt.ask("Enter your organization/lab name")

    # Set platform-specific defaults
    if platform.system() == "Darwin":  # macOS
        if not default_projects_dir:
            default_projects_dir = Path.home() / "Documents" / "MUS1" / "Projects"
        if not default_shared_dir:
            default_shared_dir = Path("/Volumes")  # Will be configured per-project
    else:
        if not default_projects_dir:
            default_projects_dir = Path.home() / "mus1-projects"
        if not default_shared_dir:
            default_shared_dir = Path.home() / "mus1-shared"

    # Create DTO and run setup
    user_dto = UserProfileDTO(
        name=name,
        email=email,
        organization=organization,
        default_projects_dir=default_projects_dir,
        default_shared_dir=default_shared_dir
    )

    try:
        result = setup_service.setup_user_profile(user_dto, force=force)

        rich_print("[green]✓[/green] User profile configured successfully!")
        rich_print(f"[blue]ℹ[/blue] Name: {user_dto.name}")
        rich_print(f"[blue]ℹ[/blue] Email: {user_dto.email}")
        rich_print(f"[blue]ℹ[/blue] Organization: {user_dto.organization}")
        rich_print(f"[blue]ℹ[/blue] Default projects directory: {user_dto.default_projects_dir}")
        rich_print(f"[blue]ℹ[/blue] Configuration saved to: {result['config_path']}")

        # Next steps
        rich_print("\n[bold]Next steps:[/bold]")
        rich_print("1. Run 'mus1 setup shared --path /Volumes/CuSSD3' to configure your shared storage")
        rich_print("2. Run 'mus1 lab create' to set up your first lab")
        rich_print("3. Run 'mus1 project init \"My Project\"' to create your first project")

    except Exception as e:
        rich_print(f"[red]✗[/red] Setup failed: {e}")
        raise typer.Exit(1)


@setup_app.command("shared")
def setup_shared_storage(
    path: Path = typer.Argument(..., help="Path to shared storage directory"),
    create: bool = typer.Option(True, help="Create directory if it doesn't exist"),
    verify_permissions: bool = typer.Option(True, help="Verify write permissions"),
):
    """Configure shared storage directory for MUS1 projects."""
    setup_service = get_setup_service()

    # Create DTO and run setup
    storage_dto = SharedStorageDTO(
        path=path,
        create_if_missing=create,
        verify_permissions=verify_permissions
    )

    try:
        result = setup_service.setup_shared_storage(storage_dto)

        if result["success"]:
            if create and not path.exists():
                rich_print(f"[green]✓[/green] Created shared directory: {path}")
            if verify_permissions:
                rich_print("[green]✓[/green] Write permissions verified")

            rich_print("[green]✓[/green] Shared storage configured successfully!")
            rich_print(f"[blue]ℹ[/blue] Shared root: {result['path']}")
            rich_print(f"[blue]ℹ[/blue] Configuration saved to: {result['config_path']}")

            # Suggest next steps
            rich_print("\n[bold]Next steps:[/bold]")
            rich_print("1. Run 'mus1 lab create' to set up your first lab")
            rich_print("2. Run 'mus1 project init \"My Project\" --use-shared' to create a project using this shared storage")
        else:
            rich_print(f"[red]✗[/red] {result['message']}")
            raise typer.Exit(1)

    except Exception as e:
        rich_print(f"[red]✗[/red] Setup failed: {e}")
        raise typer.Exit(1)


@setup_app.command("status")
def setup_status():
    """Show current MUS1 configuration status."""
    setup_service = get_setup_service()
    status = setup_service.get_setup_status()

    table = Table(title="MUS1 Configuration Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    # MUS1 Root Location
    if status.mus1_root_configured:
        path = Path(status.mus1_root_path)
        if path.exists():
            table.add_row("MUS1 Root", "✓ Configured", f"Path: {status.mus1_root_path}")
        else:
            table.add_row("MUS1 Root", "⚠ Path missing", f"Configured but doesn't exist: {status.mus1_root_path}")
    else:
        table.add_row("MUS1 Root", "⚠ Not configured", "Run 'mus1 setup root'")

    # User configuration
    if status.user_configured:
        table.add_row("User Profile", "✓ Configured", f"Name: {status.user_name}")
    else:
        table.add_row("User Profile", "⚠ Not configured", "Run 'mus1 setup user'")

    # Shared storage
    if status.shared_storage_configured:
        path = Path(status.shared_storage_path)
        if path.exists():
            table.add_row("Shared Storage", "✓ Configured", f"Path: {status.shared_storage_path}")
        else:
            table.add_row("Shared Storage", "⚠ Path missing", f"Configured but doesn't exist: {status.shared_storage_path}")
    else:
        table.add_row("Shared Storage", "⚠ Not configured", "Run 'mus1 setup shared'")

    # Labs
    if status.labs_count > 0:
        table.add_row("Labs", "✓ Configured", f"{status.labs_count} labs configured")
    else:
        table.add_row("Labs", "⚠ Not configured", "Run 'mus1 lab create' to set up labs")

    # Projects
    if status.projects_count > 0:
        table.add_row("Projects", "✓ Configured", f"{status.projects_count} projects found")
    else:
        table.add_row("Projects", "⚠ Not configured", "Run 'mus1 project init' to create projects")

    rich_print(table)

    # Show config location
    rich_print(f"\n[blue]ℹ[/blue] Configuration database: {status.config_database_path}")


@setup_app.command("wizard")
def setup_wizard():
    """Interactive first-time setup wizard for MUS1."""
    rich_print(Panel.fit(
        "[bold blue]Welcome to MUS1 Setup Wizard![/bold blue]\n\n"
        "This wizard will help you configure MUS1 for your research workflow.\n"
        "We'll set up your MUS1 root location, user profile, shared storage, labs, and projects.",
        title="🎯 MUS1 First-Time Setup"
    ))

    # Check if already configured
    setup_service = get_setup_service()
    if setup_service.is_user_configured():
        user_name = get_config("user.name")
        rich_print(f"[yellow]⚠[/yellow] MUS1 is already configured for user: {user_name}")

        # Also check for existing root pointer that might be affected
        from mus1.core.config_manager import get_root_pointer_info
        root_pointer_info = get_root_pointer_info()
        if root_pointer_info["exists"]:
            if root_pointer_info["valid"]:
                rich_print(f"[yellow]⚠[/yellow] Existing root pointer will be overwritten: {root_pointer_info['target']}")
            else:
                rich_print(f"[yellow]⚠[/yellow] Invalid root pointer will be cleaned up: {root_pointer_info['target']}")

        if not Confirm.ask("Run setup wizard anyway?"):
            rich_print("[blue]ℹ[/blue] Setup cancelled")
            return

    rich_print("\n[bold]Step 1: MUS1 Root Location Setup[/bold]")
    rich_print("MUS1 needs a directory to store its configuration and data.")
    rich_print(f"Current repository location: {Path.cwd()}")

    # MUS1 Root Location setup
    use_current = Confirm.ask("Use current repository location as MUS1 root?", default=True)
    mus1_root_path = None

    if use_current:
        mus1_root_path = Path.cwd()
        rich_print(f"[blue]ℹ[/blue] Using current location: {mus1_root_path}")
    else:
        # Ask for custom location
        if platform.system() == "Darwin":  # macOS
            suggested_root = str(Path.home() / "Documents" / "MUS1-Data")
        else:
            suggested_root = str(Path.home() / "mus1-data")

        root_input = Prompt.ask("Enter MUS1 root directory path", default=suggested_root)
        mus1_root_path = Path(root_input)

        # Validate and create if needed
        if not mus1_root_path.exists():
            if Confirm.ask(f"Path {mus1_root_path} doesn't exist. Create it?", default=True):
                try:
                    mus1_root_path.mkdir(parents=True, exist_ok=True)
                    rich_print("[green]✓[/green] Created MUS1 root directory")
                except Exception as e:
                    rich_print(f"[red]✗[/red] Failed to create directory: {e}")
                    mus1_root_path = Path.cwd()  # Fall back to current directory
                    rich_print(f"[blue]ℹ[/blue] Falling back to current location: {mus1_root_path}")
            else:
                mus1_root_path = Path.cwd()  # Fall back to current directory
                rich_print(f"[blue]ℹ[/blue] Using current location: {mus1_root_path}")

        if mus1_root_path.exists():
            # Test permissions
            test_file = mus1_root_path / ".mus1_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                rich_print("[green]✓[/green] Write permissions verified")
            except Exception as e:
                rich_print(f"[yellow]⚠[/yellow] Permission issue: {e}")
                rich_print("[blue]ℹ[/blue] You can fix permissions later")

    # Setup MUS1 root location
    root_dto = MUS1RootLocationDTO(
        path=mus1_root_path,
        create_if_missing=True,
        copy_existing_config=not use_current  # Only copy if using custom location
    )

    try:
        root_result = setup_service.setup_mus1_root_location(root_dto)
        if root_result["success"]:
            rich_print("[green]✓[/green] MUS1 root location configured")
            # Show any warnings about root pointer changes
            if "warnings" in root_result:
                for warning in root_result["warnings"]:
                    rich_print(f"[yellow]⚠[/yellow] {warning}")
        else:
            rich_print(f"[yellow]⚠[/yellow] MUS1 root setup issue: {root_result['message']}")
    except Exception as e:
        rich_print(f"[yellow]⚠[/yellow] Could not setup MUS1 root: {e}")

    rich_print("\n[bold]Step 2: User Profile Setup[/bold]")
    rich_print("Let's set up your user profile...")

    # User profile setup
    name = Prompt.ask("Enter your full name")
    email = Prompt.ask("Enter your email address")
    organization = Prompt.ask("Enter your organization/lab name")

    # Set platform-specific defaults
    if platform.system() == "Darwin":  # macOS
        default_projects_dir = Path.home() / "Documents" / "MUS1" / "Projects"
        suggested_shared = "/Volumes/CuSSD3"
    else:
        default_projects_dir = Path.home() / "mus1-projects"
        suggested_shared = str(Path.home() / "mus1-shared")

    # Ask about shared storage
    rich_print("\n[bold]Step 3: Shared Storage Setup[/bold]")
    rich_print("MUS1 can use shared storage for collaborative projects.")
    rich_print(f"Suggested path for macOS: {suggested_shared}")

    use_shared = Confirm.ask("Do you want to configure shared storage now?", default=True)
    shared_path = None

    if use_shared:
        shared_input = Prompt.ask("Enter shared storage path", default=suggested_shared)
        shared_path = Path(shared_input)

        # Validate and create if needed
        if not shared_path.exists():
            if Confirm.ask(f"Path {shared_path} doesn't exist. Create it?", default=True):
                try:
                    shared_path.mkdir(parents=True, exist_ok=True)
                    rich_print("[green]✓[/green] Created shared directory")
                except Exception as e:
                    rich_print(f"[red]✗[/red] Failed to create directory: {e}")
                    shared_path = None
            else:
                shared_path = None

        if shared_path and shared_path.exists():
            # Test permissions
            test_file = shared_path / ".mus1_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                rich_print("[green]✓[/green] Write permissions verified")
            except Exception as e:
                rich_print(f"[yellow]⚠[/yellow] Permission issue: {e}")
                rich_print("[blue]ℹ[/blue] You can fix permissions later with 'mus1 setup shared'")

    # Persist via SetupService (SQL authoritative; ConfigManager stores only active user id)
    try:
        from .setup_service import UserProfileDTO, SharedStorageDTO
        svc = get_setup_service()
        user_result = svc.setup_user_profile(UserProfileDTO(
            name=name,
            email=email,
            organization=organization,
            default_projects_dir=default_projects_dir,
            default_shared_dir=shared_path
        ))
        if not user_result.get("success"):
            rich_print(f"[red]✗[/red] Failed to save user profile: {user_result.get('message','unknown error')}")
            raise typer.Exit(1)
        if shared_path:
            storage_result = svc.setup_shared_storage(SharedStorageDTO(path=shared_path, create_if_missing=True, verify_permissions=True))
            if not storage_result.get("success"):
                rich_print(f"[yellow]⚠[/yellow] Shared storage setup warning: {storage_result.get('message','unknown error')}")
    except Exception as e:
        rich_print(f"[red]✗[/red] Error applying configuration: {e}")
        raise typer.Exit(1)

    rich_print("\n[bold]Step 4: Lab Setup[/bold]")
    create_lab_now = Confirm.ask("Do you want to create your first lab now?", default=True)

    lab_created = False
    if create_lab_now:
        from .metadata import LabDTO

        lab_id = Prompt.ask("Enter lab identifier (e.g., 'copperlab')", default="mylab")
        lab_name = Prompt.ask("Enter full lab name", default=f"{organization} Lab")
        lab_institution = Prompt.ask("Enter institution name", default=organization)
        lab_pi = Prompt.ask("Enter PI name", default=name)

        # Get current user ID for lab creator
        user_id = get_config("user.id", scope="user")
        if not user_id:
            rich_print("[red]✗[/red] No user configured - cannot create lab")
        else:
            lab_dto = LabDTO(
                id=lab_id,
                name=lab_name,
                institution=lab_institution,
                pi_name=lab_pi,
                creator_id=user_id
            )

            try:
                lab_result = setup_service.create_lab(lab_dto)
                if lab_result["success"]:
                    lab_created = True
                    rich_print("[green]✓[/green] Lab created successfully!")
                    rich_print(f"[blue]ℹ[/blue] Lab ID: {lab_id}")
                else:
                    rich_print(f"[yellow]⚠[/yellow] Could not create lab: {lab_result['message']}")
                    # Check if lab already exists and offer to update
                    if "already exists" in lab_result["message"]:
                        if Confirm.ask(f"Lab '{lab_id}' already exists. Update it instead?", default=True):
                            update_result = setup_service.update_lab(
                                lab_id=lab_id,
                                name=lab_name,
                                institution=lab_institution,
                                pi_name=lab_pi
                            )
                            if update_result["success"]:
                                lab_created = True
                                rich_print("[green]✓[/green] Lab updated successfully!")
                            else:
                                rich_print(f"[yellow]⚠[/yellow] Could not update lab: {update_result['message']}")
            except Exception as e:
                rich_print(f"[red]✗[/red] Error creating lab: {e}")

    # Summary
    rich_print("\n[bold green]🎉 MUS1 Setup Complete![/bold green]")

    table = Table(title="Setup Summary")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    table.add_row("MUS1 Root", "✓ Configured", str(mus1_root_path))
    table.add_row("User Profile", "✓ Configured", f"Name: {name}")
    table.add_row("Email", "✓ Configured", email)
    table.add_row("Organization", "✓ Configured", organization)

    if shared_path:
        table.add_row("Shared Storage", "✓ Configured", str(shared_path))
    else:
        table.add_row("Shared Storage", "⚠ Not configured", "Run 'mus1 setup shared' later")

    if lab_created:
        table.add_row("Lab", "✓ Created", lab_id)
    else:
        table.add_row("Lab", "⚠ Not created", "Run 'mus1 lab create' later")

    table.add_row("Projects", "ℹ Ready", "Run 'mus1 project init' to create projects")

    rich_print(table)

    # Next steps
    rich_print("\n[bold]Next Steps:[/bold]")
    if not lab_created:
        rich_print("1. Create a lab: 'mus1 lab create'")
    if not shared_path:
        rich_print("2. Set up shared storage: 'mus1 setup shared /Volumes/CuSSD3'")
    rich_print("3. Create your first project: 'mus1 project init \"My Project\"'")
    if lab_created:
        rich_print(f"4. Add colonies to your lab: 'mus1 lab add-colony {lab_id}'")
    rich_print("5. Check your setup anytime: 'mus1 setup status'")

    rich_print("\n[blue]ℹ[/blue] Configuration saved to: ~/Library/Application Support/mus1/config.db")
    rich_print("[blue]ℹ[/blue] You can always reconfigure with 'mus1 setup wizard --force'")


@setup_app.command("migrate")
def setup_migrate():
    """Migrate legacy configurations to simplified architecture."""
    setup_service = get_setup_service()

    rich_print("[blue]ℹ[/blue] Checking for legacy configurations to migrate...")
    results = setup_service.migrate_legacy_configurations()

    if results.get("success"):
        rich_print("[green]✓[/green] Migration completed successfully!")

        if results.get("migrated"):
            rich_print("\n[blue]Migrated configurations:[/blue]")
            for item in results["migrated"]:
                rich_print(f"  • {item}")

        if results.get("warnings"):
            rich_print("\n[yellow]⚠ Warnings:[/yellow]")
            for warning in results["warnings"]:
                rich_print(f"  • {warning}")

        if results.get("removed_features"):
            rich_print("\n[orange]Removed features (expected):[/orange]")
            for feature in results["removed_features"]:
                rich_print(f"  • {feature}")

    else:
        rich_print("[red]✗[/red] Migration failed!")
        for error in results.get("errors", []):
            rich_print(f"  • {error}")
        sys.exit(1)


# ===========================================
# LAB MANAGEMENT COMMANDS
# ===========================================

@lab_app.command("create")
def create_lab(
    lab_id: str = typer.Argument(..., help="Unique lab identifier"),
    name: str = typer.Argument(..., help="Full lab name"),
    institution: Optional[str] = typer.Option(None, help="Institution name"),
    pi_name: Optional[str] = typer.Option(None, help="Principal Investigator name"),
):
    """Create a new lab using the setup service."""
    setup_service = get_setup_service()

    # Get current user ID for lab creator
    user_id = get_config("user.id", scope="user")
    if not user_id:
        rich_print("[red]✗[/red] No user configured. Run 'mus1 setup user' first.")
        raise typer.Exit(1)

    # Interactive prompts for missing info
    if not institution:
        institution = Prompt.ask("Enter institution name", default="")
    if not pi_name:
        pi_name = Prompt.ask("Enter PI name", default="")

    # Create lab DTO
    lab_dto = LabDTO(
        id=lab_id,
        name=name,
        institution=institution,
        pi_name=pi_name,
        creator_id=user_id
    )

    # Create lab using setup service
    try:
        result = setup_service.create_lab(lab_dto)
        if result["success"]:
            rich_print("[green]✓[/green] Lab created successfully!")
            rich_print(f"[blue]ℹ[/blue] Lab ID: {lab_id}")
            rich_print(f"[blue]ℹ[/blue] Name: {name}")
            if institution:
                rich_print(f"[blue]ℹ[/blue] Institution: {institution}")
            if pi_name:
                rich_print(f"[blue]ℹ[/blue] PI: {pi_name}")

            rich_print("\n[bold]Next steps:[/bold]")
            rich_print(f"1. Add colonies: 'mus1 lab add-colony {lab_id}'")
            rich_print(f"2. Create projects: 'mus1 project init \"Project Name\" --lab {lab_id}'")
        else:
            rich_print(f"[red]✗[/red] Failed to create lab: {result['message']}")
            raise typer.Exit(1)
    except Exception as e:
        rich_print(f"[red]✗[/red] Error creating lab: {e}")
        raise typer.Exit(1)


@lab_app.command("list")
def list_labs():
    """List all configured labs."""
    setup_service = get_setup_service()
    labs = setup_service.get_labs()

    if not labs:
        rich_print("[yellow]⚠[/yellow] No labs configured yet")
        rich_print("[blue]ℹ[/blue] Run 'mus1 lab create' to set up your first lab")
        return

    table = Table(title="Configured Labs")
    table.add_column("Lab ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Institution", style="white")
    table.add_column("PI", style="white")
    table.add_column("Created", style="white")

    for lab in labs.values():
        table.add_row(
            lab.get("id", "Unknown"),
            lab.get("name", "Unknown"),
            lab.get("institution", "Unknown"),
            lab.get("pi_name", "Unknown"),
            lab.get("created_at", "Unknown")[:10] if lab.get("created_at") else "Unknown"
        )

    rich_print(table)


@lab_app.command("add-colony")
def add_colony_to_lab(
    lab_id: str = typer.Argument(..., help="Lab ID to add colony to"),
    colony_id: str = typer.Argument(..., help="Unique colony identifier"),
    name: str = typer.Argument(..., help="Colony name"),
    genotype: Optional[str] = typer.Option(None, help="Genotype of interest"),
    background: Optional[str] = typer.Option(None, help="Background strain"),
):
    """Add a colony to an existing lab."""
    setup_service = get_setup_service()

    # Interactive prompts for missing info
    if not genotype:
        genotype = Prompt.ask("Enter genotype of interest", default="")
    if not background:
        background = Prompt.ask("Enter background strain", default="")

    # Create colony DTO
    colony_dto = ColonyDTO(
        id=colony_id,
        name=name,
        genotype_of_interest=genotype,
        background_strain=background,
        lab_id=lab_id
    )

    # Create colony using setup service
    try:
        result = setup_service.create_colony(lab_id, colony_dto)
        if result["success"]:
            rich_print("[green]✓[/green] Colony added to lab successfully!")
            rich_print(f"[blue]ℹ[/blue] Lab: {lab_id}")
            rich_print(f"[blue]ℹ[/blue] Colony ID: {colony_id}")
            rich_print(f"[blue]ℹ[/blue] Name: {name}")
            if genotype:
                rich_print(f"[blue]ℹ[/blue] Genotype: {genotype}")
            if background:
                rich_print(f"[blue]ℹ[/blue] Background: {background}")
        else:
            rich_print(f"[red]✗[/red] Failed to add colony: {result['message']}")
            raise typer.Exit(1)
    except Exception as e:
        rich_print(f"[red]✗[/red] Error adding colony: {e}")
        raise typer.Exit(1)


# ===========================================
# DEMO COMMANDS
# ===========================================

@app.command("demo")
def run_demo(
    demo_type: str = typer.Argument(..., help="Demo type: clean-architecture, plugin-architecture"),
):
    """Run architecture demonstration."""
    if demo_type == "clean-architecture":
        from functional_tests.demo_clean_architecture import demo_clean_architecture
        demo_clean_architecture()
    elif demo_type == "plugin-architecture":
        from functional_tests.demo_plugin_architecture import demo_plugin_architecture
        demo_plugin_architecture()
    else:
        rich_print(f"[red]Unknown demo type: {demo_type}[/red]")
        rich_print("Available demos: clean-architecture, plugin-architecture")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
