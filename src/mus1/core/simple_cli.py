"""
Simplified MUS1 CLI - Core operations only.

This replaces the 2910-line grab-bag CLI with focused commands.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, List
import typer
from rich import print as rich_print
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
import json
import platform
from datetime import datetime

from .metadata import ProjectConfig, SubjectDTO, ExperimentDTO, ColonyDTO, Colony, Worker, ScanTarget, WorkerProvider, ScanTargetKind
from .data_service import SubjectService, ExperimentService
from .config_manager import get_config_manager, set_config, get_config
from .repository import ColonyRepository, SubjectRepository, ExperimentRepository
from .schema import Database
from .setup_service import (
    SetupService, SetupStatusDTO, get_setup_service, MUS1RootLocationDTO
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

# ===========================================
# CORE COMMANDS
# ===========================================

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    setup: bool = typer.Option(False, "--setup", "-s", help="Run setup wizard after starting GUI"),
):
    """MUS1 - Clean and simple."""
    if ctx.invoked_subcommand is None:
        rich_print("[bold blue]MUS1[/bold blue] - Video analysis system")
        rich_print("Use 'mus1 --help' for available commands")

        # Launch GUI with setup flag if requested
        if setup:
            import sys
            import os
            # Set environment variable or modify sys.argv to pass setup flag to GUI
            os.environ['MUS1_SETUP_REQUESTED'] = '1'

        # Import and run GUI
        try:
            from ..main import main as gui_main
            gui_main()
        except KeyboardInterrupt:
            rich_print("\n[yellow]GUI interrupted by user[/yellow]")
        except Exception as e:
            rich_print(f"[red]Error launching GUI: {e}[/red]")
            raise typer.Exit(1)

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
    config_manager = get_config_manager()

    # Determine project path
    if not path:
        if use_shared or shared_root:
            # Use shared storage
            shared_path = shared_root or Path(get_config("storage.shared_root", "/Volumes"))
            if not shared_path:
                rich_print("[red]✗[/red] No shared storage configured. Run 'mus1 setup shared' first or specify --shared-root")
                raise typer.Exit(1)
            project_path = shared_path / "Projects" / name
        else:
            # Use default user projects directory
            default_dir = get_config("user.default_projects_dir", str(Path.home() / "Documents" / "MUS1" / "Projects"))
            project_path = Path(default_dir) / name
    else:
        project_path = path

    # Check if project already exists
    if (project_path / "mus1.db").exists() or (project_path / "project.json").exists():
        rich_print(f"[red]✗[/red] Project already exists at {project_path}")
        raise typer.Exit(1)

    # Validate lab association
    if lab_id:
        labs = get_config("labs", scope="user") or {}
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
        shared_root=shared_root or (Path(get_config("storage.shared_root")) if use_shared else None),
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
        labs = get_config("labs", scope="user") or {}
        if lab_id in labs:
            lab_config = labs[lab_id]
            projects = lab_config.get("projects", [])
            projects.append({
                "name": name,
                "path": str(project_path),
                "created_date": config.date_created.isoformat()
            })
            lab_config["projects"] = projects
            labs[lab_id] = lab_config
            set_config("labs", labs, scope="user")

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
    config_manager = get_config_manager()

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

    # Also scan for projects in default locations
    default_dirs = [
        get_config("user.default_projects_dir", str(Path.home() / "Documents" / "MUS1" / "Projects")),
        get_config("storage.shared_root", None)
    ]

    for dir_path in default_dirs:
        if dir_path:
            dir_path = Path(dir_path)
            if dir_path.exists():
                projects_dir = dir_path / "Projects" if "shared_root" in str(dir_path) else dir_path
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

    # Initialize database
    db_path = project_path / "mus1.db"
    db = Database(str(db_path))
    db.create_tables()

    # Save subject
    service = SubjectService(db)
    subject = service.create_subject(subject_dto)

    rich_print(f"[green]✓[/green] Added subject {subject.id}")
    if subject.genotype:
        rich_print(f"[blue]ℹ[/blue] Genotype: {subject.genotype}")

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

    # Initialize database
    db_path = project_path / "mus1.db"
    db = Database(str(db_path))
    db.create_tables()

    # Save experiment
    service = ExperimentService(db)
    experiment = service.create_experiment(experiment_dto)

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
    service = SubjectService(db)

    subjects = service.list_subjects()
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
    service = ExperimentService(db)

    experiments = service.list_experiments()
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
        rich_print(f"[yellow]⚠[/yellow] User configuration already exists for: {existing_profile.name}")
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
        from .setup_service import LabDTO
        from .metadata import User

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


# ===========================================
# LAB MANAGEMENT COMMANDS
# ===========================================

@lab_app.command("create")
def create_lab(
    lab_id: str = typer.Argument(..., help="Unique lab identifier"),
    name: str = typer.Argument(..., help="Full lab name"),
    description: Optional[str] = typer.Option(None, help="Lab description"),
    institution: Optional[str] = typer.Option(None, help="Institution name"),
    pi_name: Optional[str] = typer.Option(None, help="Principal Investigator name"),
):
    """Create a new lab configuration."""
    config_manager = get_config_manager()

    # Check if lab already exists
    existing_labs = get_config("labs", scope="user") or {}
    if lab_id in existing_labs:
        rich_print(f"[red]✗[/red] Lab '{lab_id}' already exists")
        raise typer.Exit(1)

    # Interactive prompts for missing info
    if not description:
        description = Prompt.ask("Enter lab description", default="")
    if not institution:
        institution = Prompt.ask("Enter institution name", default="")
    if not pi_name:
        pi_name = Prompt.ask("Enter PI name", default="")

    # Create lab configuration
    lab_config = {
        "id": lab_id,
        "name": name,
        "description": description,
        "institution": institution,
        "pi_name": pi_name,
        "created_date": datetime.now().isoformat(),
        "colonies": [],
        "projects": []
    }

    # Save to user config
    if not existing_labs:
        existing_labs = {}
    existing_labs[lab_id] = lab_config
    set_config("labs", existing_labs, scope="user")

    rich_print("[green]✓[/green] Lab created successfully!")
    rich_print(f"[blue]ℹ[/blue] Lab ID: {lab_id}")
    rich_print(f"[blue]ℹ[/blue] Name: {name}")
    rich_print(f"[blue]ℹ[/blue] Institution: {institution}")
    rich_print(f"[blue]ℹ[/blue] PI: {pi_name}")

    rich_print("\n[bold]Next steps:[/bold]")
    rich_print(f"1. Create colonies: 'mus1 lab add-colony {lab_id}'")
    rich_print(f"2. Create projects: 'mus1 project init \"Project Name\" --lab {lab_id}'")


@lab_app.command("list")
def list_labs():
    """List all configured labs."""
    config_manager = get_config_manager()
    labs = get_config("labs", scope="user") or {}

    if not labs:
        rich_print("[yellow]⚠[/yellow] No labs configured yet")
        rich_print("[blue]ℹ[/blue] Run 'mus1 lab create' to set up your first lab")
        return

    table = Table(title="Configured Labs")
    table.add_column("Lab ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Institution", style="white")
    table.add_column("PI", style="white")
    table.add_column("Colonies", style="green", justify="right")
    table.add_column("Projects", style="blue", justify="right")

    for lab_id, lab_config in labs.items():
        colonies_count = len(lab_config.get("colonies", []))
        projects_count = len(lab_config.get("projects", []))
        table.add_row(
            lab_id,
            lab_config.get("name", "Unknown"),
            lab_config.get("institution", "Unknown"),
            lab_config.get("pi_name", "Unknown"),
            str(colonies_count),
            str(projects_count)
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
    config_manager = get_config_manager()

    # Get existing labs
    labs = get_config("labs", scope="user") or {}
    if lab_id not in labs:
        rich_print(f"[red]✗[/red] Lab '{lab_id}' not found")
        rich_print("[blue]ℹ[/blue] Run 'mus1 lab list' to see available labs")
        raise typer.Exit(1)

    # Check if colony already exists in this lab
    lab_config = labs[lab_id]
    colonies = lab_config.get("colonies", [])
    existing_colony_ids = [c.get("id") for c in colonies]

    if colony_id in existing_colony_ids:
        rich_print(f"[red]✗[/red] Colony '{colony_id}' already exists in lab '{lab_id}'")
        raise typer.Exit(1)

    # Interactive prompts for missing info
    if not genotype:
        genotype = Prompt.ask("Enter genotype of interest", default="")
    if not background:
        background = Prompt.ask("Enter background strain", default="")

    # Create colony configuration
    colony_config = {
        "id": colony_id,
        "name": name,
        "genotype_of_interest": genotype,
        "background_strain": background,
        "created_date": datetime.now().isoformat(),
        "subjects": []
    }

    # Add to lab
    colonies.append(colony_config)
    lab_config["colonies"] = colonies
    labs[lab_id] = lab_config
    set_config("labs", labs, scope="user")

    rich_print("[green]✓[/green] Colony added to lab successfully!")
    rich_print(f"[blue]ℹ[/blue] Lab: {lab_id}")
    rich_print(f"[blue]ℹ[/blue] Colony ID: {colony_id}")
    rich_print(f"[blue]ℹ[/blue] Name: {name}")
    if genotype:
        rich_print(f"[blue]ℹ[/blue] Genotype: {genotype}")
    if background:
        rich_print(f"[blue]ℹ[/blue] Background: {background}")


# ===========================================
# DEMO COMMANDS
# ===========================================

@app.command("demo")
def run_demo(
    demo_type: str = typer.Argument(..., help="Demo type: clean-architecture, plugin-architecture"),
):
    """Run architecture demonstration."""
    if demo_type == "clean-architecture":
        from .demo_clean_architecture import demo_clean_architecture
        demo_clean_architecture()
    elif demo_type == "plugin-architecture":
        from .demo_plugin_architecture import demo_plugin_architecture
        demo_plugin_architecture()
    else:
        rich_print(f"[red]Unknown demo type: {demo_type}[/red]")
        rich_print("Available demos: clean-architecture, plugin-architecture")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
