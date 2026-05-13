"""``mus1 arena-models`` CLI subcommand group.

Manage the project's active arena U-Net registry
(``<project_path>/arena_models.yaml``). The registry tells the app
which trained checkpoint to use for each :class:`mus1.arena_profiles.
ArenaProfile`. Activation discipline: every QC / inference write
records the active ``run_id`` so historical reviews stay anchored to
the model they were performed against (per user 2026-05-07
confirmation).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print as rich_print
from rich.table import Table

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


def _resolve_project_path(project_path: Optional[Path]) -> Path:
    """Mirror experiment_cli's path resolver."""
    if project_path is not None:
        return Path(project_path).resolve()
    cwd = Path.cwd()
    if (cwd / "project.json").is_file() or (cwd / "cohorts").is_dir():
        return cwd
    if (cwd / "data" / "project.json").is_file() or (cwd / "data" / "cohorts").is_dir():
        return (cwd / "data").resolve()
    return cwd.resolve()


def _models_yaml_path(project_path: Path) -> Path:
    from mus1.compute.arena_models import PROJECT_MODELS_FILENAME
    return project_path / PROJECT_MODELS_FILENAME


def register_commands(parent_app: typer.Typer) -> None:
    arena_app = typer.Typer(help="Arena model registry (data/arena_models.yaml).")
    parent_app.add_typer(arena_app, name="arena-models")

    @arena_app.command("list")
    def arena_models_list(
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Show the active U-Net registry for every arena profile."""
        from mus1.arena_profiles import ArenaProfileRegistry
        from mus1.compute.arena_models import ArenaModelRegistry

        proj = _resolve_project_path(project_path)
        models = ArenaModelRegistry.load(proj)
        profiles = ArenaProfileRegistry.from_config(proj)

        rich_print(f"[bold]Project path:[/bold] {proj}")
        if models.source_path:
            rich_print(f"[dim]Registry: {models.source_path}[/dim]")
        else:
            rich_print(f"[dim]Registry: (no arena_models.yaml — none active)[/dim]")

        table = Table(title="Arena models", show_lines=False)
        table.add_column("profile_id")
        table.add_column("active?")
        table.add_column("run_id")
        table.add_column("checkpoint")
        table.add_column("on_disk?")
        table.add_column("post-proc")

        for profile_id in profiles.list_ids():
            entry = models.get(profile_id)
            if entry is None:
                table.add_row(profile_id, "[dim]no[/dim]", "—", "—", "—", "—")
                continue
            on_disk = "[green]yes[/green]" if entry.checkpoint.is_file() else "[red]no[/red]"
            table.add_row(
                profile_id,
                "[green]yes[/green]",
                entry.run_id,
                str(entry.checkpoint),
                on_disk,
                entry.mask_to_marking or "—",
            )
        rich_print(table)

    @arena_app.command("activate")
    def arena_models_activate(
        profile_id: str = typer.Argument(..., help="Arena profile id."),
        run_id: str = typer.Argument(..., help="Run identifier (free-form, e.g. '20260120_lr01_bs8')."),
        checkpoint: Path = typer.Option(..., "--checkpoint", help="Path to model_best.pt."),
        n_classes: int = typer.Option(3, "--n-classes"),
        mask_to_marking: str = typer.Option(
            "", "--mask-to-marking",
            help="Post-processor key (e.g. ezm_wedge_points, circular_arena_boundary).",
        ),
        notes: str = typer.Option("", "--notes"),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Set / replace the active model for a profile.

        Validates that the profile is registered and the checkpoint
        exists before writing. Preserves any other entries already in
        ``arena_models.yaml``.
        """
        from datetime import datetime, timezone
        from mus1.arena_profiles import ArenaProfileRegistry
        from mus1.compute.arena_post_processors import get as _get_post_processor

        proj = _resolve_project_path(project_path)
        profiles = ArenaProfileRegistry.from_config(proj)
        if profile_id not in profiles.list_ids():
            rich_print(f"[red]Unknown arena profile: {profile_id!r}[/red]")
            rich_print(f"[dim]Available: {profiles.list_ids()}[/dim]")
            raise typer.Exit(1)

        ckpt = Path(checkpoint)
        if not ckpt.is_file():
            rich_print(f"[red]Checkpoint not found: {ckpt}[/red]")
            raise typer.Exit(1)

        if mask_to_marking and _get_post_processor(mask_to_marking) is None:
            rich_print(
                f"[yellow]Warning: mask_to_marking={mask_to_marking!r} is not "
                f"in the registered post-processor set yet.[/yellow]"
            )

        if yaml is None:
            rich_print("[red]PyYAML required to write arena_models.yaml[/red]")
            raise typer.Exit(1)

        yaml_path = _models_yaml_path(proj)
        # Read existing YAML (preserve other profile entries)
        if yaml_path.is_file():
            with yaml_path.open("r") as f:
                doc = yaml.safe_load(f) or {}
        else:
            doc = {}
        models = doc.setdefault("arena_models", {})
        if not isinstance(models, dict):
            rich_print(f"[red]{yaml_path}: arena_models must be a mapping[/red]")
            raise typer.Exit(1)
        models[profile_id] = {
            "active": {
                "run_id": run_id,
                "checkpoint": str(ckpt),
                "n_classes": n_classes,
                "mask_to_marking": mask_to_marking,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "notes": notes,
            }
        }
        with yaml_path.open("w") as f:
            yaml.safe_dump(doc, f, sort_keys=False)
        rich_print(f"[green]Activated[/green] {profile_id} -> {run_id}")
        rich_print(f"[dim]Wrote {yaml_path}[/dim]")

    @arena_app.command("deactivate")
    def arena_models_deactivate(
        profile_id: str = typer.Argument(...),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
    ):
        """Clear the active model for a profile (sets ``active: null``)."""
        if yaml is None:
            rich_print("[red]PyYAML required[/red]")
            raise typer.Exit(1)
        proj = _resolve_project_path(project_path)
        yaml_path = _models_yaml_path(proj)
        if not yaml_path.is_file():
            rich_print(f"[dim]No registry to update at {yaml_path}.[/dim]")
            return
        with yaml_path.open("r") as f:
            doc = yaml.safe_load(f) or {}
        models = doc.get("arena_models") or {}
        if profile_id in models:
            models[profile_id] = {"active": None}
            with yaml_path.open("w") as f:
                yaml.safe_dump(doc, f, sort_keys=False)
            rich_print(f"[green]Deactivated[/green] {profile_id}")
        else:
            rich_print(f"[dim]No entry for {profile_id!r} — nothing to do.[/dim]")
