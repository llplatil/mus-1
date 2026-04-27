"""CLI subcommands for experiment + cohort management.

Registers two Typer subcommand groups on the main mus1 ``app``:

  mus1 experiment list             → discover experiments across data roots
  mus1 experiment show <id>        → print one experiment's metadata
  mus1 experiment add-validation   → ingest a freshly-created validation JSON
                                     (alias for "make sure it's discoverable")

  mus1 cohort list                 → list cohorts in data/cohorts/
  mus1 cohort show <name>          → print cohort summary + members
  mus1 cohort create <name>        → create a new cohort JSON
  mus1 cohort add-member <name> <experiment_id>
  mus1 cohort remove-member <name> <experiment_id>
  mus1 cohort add-where <name>     → bulk-add by filter (--task, --cohort,
                                     --root, --unassigned)

All commands use the multi-root discovery layer in ``mus1.web.discovery``,
so validation_data and any other configured roots are picked up automatically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from rich import print as rich_print
from rich.table import Table


def _resolve_project_path(project_path: Optional[Path]) -> Path:
    if project_path is not None:
        p = Path(project_path).resolve()
    else:
        # Default to ./data if it looks like a project, else cwd
        p = Path.cwd().resolve()
        if (p / "data").is_dir() and (p / "data" / "cohorts").is_dir():
            p = p / "data"
        elif (p / "cohorts").is_dir():
            pass
        else:
            # Last-ditch default
            pass
    return p


def _cohorts_dir_for(project_path: Path) -> Path:
    return project_path / "cohorts"


def _resolve_cohort_path(cohorts_dir: Path, name: str) -> Path:
    """Map a cohort name like 'validation_2026' to its JSON file."""
    if name.endswith(".json"):
        candidate = (cohorts_dir / name).resolve()
        if candidate.is_file():
            return candidate
    candidate = (cohorts_dir / f"{name}.json").resolve()
    return candidate


def register_commands(app: typer.Typer) -> None:
    """Register `experiment` and `cohort` subcommands on the main app."""
    experiment_app = typer.Typer(help="Experiment discovery + ingestion")
    app.add_typer(experiment_app, name="experiment")

    cohort_app = typer.Typer(help="Cohort manifest management")
    app.add_typer(cohort_app, name="cohort")

    # --------------------------------------------------------------- experiment

    @experiment_app.command("list")
    def experiment_list(
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p", help="Project root (parent of cohorts/, experiment_data/, validation_data/). Default: ./data."),
        task: Optional[str] = typer.Option(None, "--task", "-t", help="Restrict to one task type (OF/EZM/NOR/NOF/RR)."),
        cohort: Optional[str] = typer.Option(None, "--cohort", "-c", help="Filter by metadata.experiment_level.cohort. Use 'none' for unassigned."),
        root_name: Optional[str] = typer.Option(None, "--root", "-r", help="Filter by data_root basename (e.g. validation_data)."),
        json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
    ):
        """List experiments discovered across all configured data roots."""
        from mus1.web.discovery import discover_experiments

        proj = _resolve_project_path(project_path)
        rows = discover_experiments(proj, task=task)

        if cohort is not None:
            target = "" if cohort.lower() == "none" else cohort
            rows = [r for r in rows if r.get("cohort", "") == target]
        if root_name:
            rows = [r for r in rows if Path(r.get("data_root", "")).name == root_name]

        if json_out:
            rich_print(json.dumps(rows, indent=2))
            return

        if not rows:
            rich_print("[yellow]No experiments found matching filters.[/yellow]")
            return

        t = Table(title=f"{len(rows)} experiments")
        for col in ("experiment_id", "task", "subject", "geno", "sex", "date", "cohort", "root"):
            t.add_column(col)
        for r in rows:
            t.add_row(
                r["experiment_id"],
                r["task_type"],
                r["subject_id"],
                r["genotype"],
                r["sex"],
                r["date_recorded"],
                r["cohort"] or "-",
                Path(r["data_root"]).name,
            )
        rich_print(t)

    @experiment_app.command("show")
    def experiment_show(
        experiment_id: str = typer.Argument(..., help="Experiment ID, e.g. EZM_VAL_1017_2026-04-08."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Print full metadata for one experiment."""
        from mus1.web.discovery import find_experiment_dir, find_experiment_json

        proj = _resolve_project_path(project_path)
        exp_dir = find_experiment_dir(proj, experiment_id)
        if exp_dir is None:
            rich_print(f"[red]Not found: {experiment_id}[/red]")
            raise typer.Exit(1)
        jp = find_experiment_json(exp_dir)
        if jp is None:
            rich_print(f"[red]No JSON in {exp_dir}[/red]")
            raise typer.Exit(1)
        rich_print(f"[bold]{experiment_id}[/bold]  ({exp_dir})")
        rich_print(json.loads(jp.read_text()))

    @experiment_app.command("data-roots")
    def experiment_data_roots(
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Print the canonical data roots that exist for this project."""
        from mus1.web.discovery import DATA_ROOTS, get_data_roots

        proj = _resolve_project_path(project_path)
        roots = get_data_roots(proj)
        rich_print(f"[bold]Project path:[/bold] {proj}")
        rich_print(f"[bold]Canonical data roots:[/bold] {list(DATA_ROOTS)}")
        rich_print(f"[bold]Present on disk ({len(roots)}):[/bold]")
        for r in roots:
            rich_print(f"  • {r}")
        missing = [n for n in DATA_ROOTS if not (proj / n).is_dir()]
        if missing:
            rich_print(f"[dim]Not on disk: {missing} (will appear here once created).[/dim]")

    # ------------------------------------------------------------------- cohort

    @cohort_app.command("list")
    def cohort_list(
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """List cohort manifests in data/cohorts/."""
        from mus1.web.cohorts import list_cohorts

        proj = _resolve_project_path(project_path)
        cohorts = list_cohorts(_cohorts_dir_for(proj))
        if not cohorts:
            rich_print("[yellow]No cohorts.[/yellow]")
            return
        t = Table(title=f"{len(cohorts)} cohorts in {_cohorts_dir_for(proj)}")
        for col in ("name", "members", "subjects", "task_types", "updated_at"):
            t.add_column(col)
        for c in cohorts:
            t.add_row(
                c["name"],
                str(c["n_members"]),
                str(c.get("n_subjects") or "-"),
                ", ".join(c.get("task_types") or []) or "any",
                c.get("updated_at", ""),
            )
        rich_print(t)

    @cohort_app.command("show")
    def cohort_show(
        name: str = typer.Argument(..., help="Cohort name (e.g. validation_2026) or path to JSON."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        members: bool = typer.Option(False, "--members", "-m", help="Print full members list."),
    ):
        """Print one cohort's summary block, and optionally its member list."""
        from mus1.web.cohorts import load_cohort

        proj = _resolve_project_path(project_path)
        path = _resolve_cohort_path(_cohorts_dir_for(proj), name)
        if not path.is_file():
            rich_print(f"[red]Not found: {path}[/red]")
            raise typer.Exit(1)
        c = load_cohort(path)
        rich_print(f"[bold]{c.get('name', path.stem)}[/bold]  ({path})")
        rich_print(f"  description: {c.get('description', '')}")
        rich_print(f"  task_types:  {c.get('task_types', [])}")
        s = c.get("summary") or {}
        if s:
            rich_print(f"  experiments: {s.get('n_experiments')}")
            rich_print(f"  subjects:    {s.get('n_subjects')}")
            rich_print(f"  groups:      {s.get('groups')}")
            if s.get("warnings"):
                rich_print(f"  [yellow]warnings:[/yellow]")
                for w in s["warnings"]:
                    rich_print(f"    - {w}")
        if members:
            rich_print(f"  members ({len(c.get('members') or [])}):")
            for m in c.get("members") or []:
                rich_print(f"    - {m.get('experiment_id')}  added={m.get('added_at','')[:10]}")

    @cohort_app.command("create")
    def cohort_create(
        name: str = typer.Argument(..., help="Cohort name (also the JSON filename without .json)."),
        description: str = typer.Option("", "--description", "-d"),
        task_types: Optional[List[str]] = typer.Option(None, "--task", "-t", help="Restrict cohort to these task types (repeatable)."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite if a cohort with this name exists."),
    ):
        """Create an empty cohort JSON in data/cohorts/."""
        from mus1.web.cohorts import create_cohort, save_cohort

        proj = _resolve_project_path(project_path)
        cohorts_dir = _cohorts_dir_for(proj)
        path = _resolve_cohort_path(cohorts_dir, name)
        if path.is_file() and not force:
            rich_print(f"[red]Already exists: {path}. Use --force to overwrite.[/red]")
            raise typer.Exit(1)
        cohorts_dir.mkdir(parents=True, exist_ok=True)
        coh = create_cohort(name, task_types=list(task_types or []), description=description)
        save_cohort(path, coh)
        rich_print(f"[green]✓[/green] Created {path}")

    @cohort_app.command("add-member")
    def cohort_add_member(
        name: str = typer.Argument(..., help="Cohort name."),
        experiment_id: str = typer.Argument(..., help="Experiment ID to add."),
        notes: str = typer.Option("", "--notes"),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Add an experiment to an existing cohort (idempotent)."""
        from mus1.web.cohorts import add_member as add_, load_cohort, save_cohort
        from mus1.web.discovery import find_experiment_dir

        proj = _resolve_project_path(project_path)
        exp_dir = find_experiment_dir(proj, experiment_id)
        if exp_dir is None:
            rich_print(f"[yellow]Warning: experiment {experiment_id} not found on disk.[/yellow]")
            rich_print("[yellow]Adding to cohort anyway (members are tracked by ID).[/yellow]")

        path = _resolve_cohort_path(_cohorts_dir_for(proj), name)
        if not path.is_file():
            rich_print(f"[red]Cohort not found: {path}[/red]")
            raise typer.Exit(1)
        coh = load_cohort(path)
        before = len(coh.get("members") or [])
        add_(coh, experiment_id, notes=notes)
        save_cohort(path, coh)
        after = len(coh.get("members") or [])
        if after > before:
            rich_print(f"[green]✓[/green] Added {experiment_id} to {name} ({after} members)")
        else:
            rich_print(f"[yellow]·[/yellow] {experiment_id} was already in {name} ({after} members)")

    @cohort_app.command("remove-member")
    def cohort_remove_member(
        name: str = typer.Argument(...),
        experiment_id: str = typer.Argument(...),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Remove an experiment from a cohort."""
        from mus1.web.cohorts import remove_member as rem_, load_cohort, save_cohort

        proj = _resolve_project_path(project_path)
        path = _resolve_cohort_path(_cohorts_dir_for(proj), name)
        if not path.is_file():
            rich_print(f"[red]Cohort not found: {path}[/red]")
            raise typer.Exit(1)
        coh = load_cohort(path)
        before = len(coh.get("members") or [])
        rem_(coh, experiment_id)
        save_cohort(path, coh)
        after = len(coh.get("members") or [])
        if after < before:
            rich_print(f"[green]✓[/green] Removed {experiment_id} from {name} ({after} members)")
        else:
            rich_print(f"[yellow]·[/yellow] {experiment_id} was not in {name}")

    @cohort_app.command("add-where")
    def cohort_add_where(
        name: str = typer.Argument(..., help="Cohort name."),
        task: Optional[str] = typer.Option(None, "--task", "-t", help="Restrict to one task type."),
        cohort_filter: Optional[str] = typer.Option(None, "--cohort", "-c", help="Filter source experiments by their declared cohort. Use 'none' for unassigned."),
        root_name: Optional[str] = typer.Option(None, "--root", "-r", help="Filter by data_root basename."),
        unassigned: bool = typer.Option(False, "--unassigned", help="Equivalent to --cohort none."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be added without writing."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Bulk-add experiments to a cohort by filter."""
        from mus1.web.cohorts import add_member as add_, load_cohort, save_cohort, cohort_member_ids
        from mus1.web.discovery import discover_experiments

        proj = _resolve_project_path(project_path)
        path = _resolve_cohort_path(_cohorts_dir_for(proj), name)
        if not path.is_file():
            rich_print(f"[red]Cohort not found: {path}[/red]")
            raise typer.Exit(1)
        coh = load_cohort(path)

        rows = discover_experiments(proj, task=task)
        if unassigned or (cohort_filter and cohort_filter.lower() == "none"):
            rows = [r for r in rows if not r.get("cohort")]
        elif cohort_filter:
            rows = [r for r in rows if r.get("cohort") == cohort_filter]
        if root_name:
            rows = [r for r in rows if Path(r.get("data_root", "")).name == root_name]

        existing = cohort_member_ids(coh)
        new_rows = [r for r in rows if r["experiment_id"] not in existing]

        rich_print(f"Matched: {len(rows)}  ·  Already in cohort: {len(rows) - len(new_rows)}  ·  Will add: {len(new_rows)}")
        for r in new_rows:
            rich_print(f"  + {r['experiment_id']}  ({r['task_type']}, {r['genotype']}/{r['sex']}, {Path(r['data_root']).name})")
        if dry_run:
            rich_print("[dim](dry-run; no write)[/dim]")
            return
        if not new_rows:
            rich_print("[yellow]Nothing to add.[/yellow]")
            return
        for r in new_rows:
            add_(coh, r["experiment_id"])
        save_cohort(path, coh)
        rich_print(f"[green]✓[/green] Added {len(new_rows)} to {name}")
