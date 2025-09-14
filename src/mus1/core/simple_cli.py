"""
Simplified MUS1 CLI - Core operations only.

This replaces the 2910-line grab-bag CLI with focused commands.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import typer
from rich import print as rich_print

from .metadata import ProjectConfig, SubjectDTO, ExperimentDTO
from .data_service import SubjectService, ExperimentService
from .schema import Database

app = typer.Typer(
    help="MUS1 - Simple video analysis system",
    add_completion=False,
)

# ===========================================
# CORE COMMANDS
# ===========================================

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """MUS1 - Clean and simple."""
    if ctx.invoked_subcommand is None:
        rich_print("[bold blue]MUS1[/bold blue] - Video analysis system")
        rich_print("Use 'mus1 --help' for available commands")

# ===========================================
# PROJECT MANAGEMENT
# ===========================================

@app.command("init")
def init_project(
    name: str = typer.Argument(..., help="Project name"),
    path: Optional[Path] = typer.Option(None, help="Project directory (default: ~/mus1-projects/{name})"),
):
    """Initialize a new MUS1 project."""
    project_path = path or Path.home() / "mus1-projects" / name
    project_path.mkdir(parents=True, exist_ok=True)

    # Create simple project config
    config = ProjectConfig(name=name)
    config_path = project_path / "project.json"

    import json
    with open(config_path, 'w') as f:
        json.dump({
            "name": config.name,
            "shared_root": str(config.shared_root) if config.shared_root else None,
            "lab_id": config.lab_id,
            "date_created": config.date_created.isoformat()
        }, f, indent=2)

    rich_print(f"[green]✓[/green] Created project '{name}' at {project_path}")
    rich_print(f"[blue]ℹ[/blue] Project config: {config_path}")

@app.command("status")
def project_status(
    path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Show project status."""
    config_path = path / "project.json"
    if not config_path.exists():
        rich_print(f"[red]✗[/red] No MUS1 project found at {path}")
        return

    import json
    with open(config_path) as f:
        config = json.load(f)

    rich_print(f"[bold]Project:[/bold] {config['name']}")
    rich_print(f"[bold]Path:[/bold] {path}")
    rich_print(f"[bold]Created:[/bold] {config['date_created']}")
    if config.get('shared_root'):
        rich_print(f"[bold]Shared root:[/bold] {config['shared_root']}")

# ===========================================
# DATA MANAGEMENT
# ===========================================

@app.command("add-subject")
def add_subject(
    subject_id: str = typer.Argument(..., help="Subject ID"),
    sex: str = typer.Option("Unknown", help="Subject sex (M/F/Unknown)"),
    genotype: Optional[str] = typer.Option(None, help="Subject genotype"),
    project_path: Path = typer.Option(Path.cwd(), help="Project directory"),
):
    """Add a subject to the project."""
    # Validate input
    if sex not in ["M", "F", "Unknown"]:
        rich_print("[red]✗[/red] Sex must be M, F, or Unknown")
        return

    # Create DTO
    from .metadata import Sex
    sex_enum = {"M": Sex.MALE, "F": Sex.FEMALE, "Unknown": Sex.UNKNOWN}[sex]

    subject_dto = SubjectDTO(
        id=subject_id,
        sex=sex_enum,
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
        rich_print(f"  {subject.id} ({subject.sex.value}){age_str}{genotype_str}")

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

if __name__ == "__main__":
    app()
