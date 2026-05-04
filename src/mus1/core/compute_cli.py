"""CLI subcommands for compute operations.

Registers the ``compute`` subcommand group on the main mus1 ``app``::

    mus1 compute tracking-confidence <experiment_id>
    mus1 compute tracking-confidence --cohort <name>
    mus1 compute tracking-confidence <experiment_id> --json
    mus1 compute tracking-confidence <experiment_id> --write
    mus1 compute tracking-confidence <experiment_id> --pcutoff 0.7

Output target depends on flags:

  default            → human-readable summary on stdout
  --json             → JSON document on stdout
  --write            → also persist into the experiment JSON at
                       ``extraction.tracking_confidence`` (idempotent;
                       overwrites the prior block per SCHEMA_VARIANTS.md §6)

Cohort mode (``--cohort``) iterates members. ``--write --cohort`` is the
canonical "compute baseline confidence over a whole cohort" command.

Thresholds default to documented DLC conventions
(``mus1.compute.tracking_confidence.DEFAULT_*``) but are overridable via
flags or via ``compute.tracking_confidence`` in the user/project
preferences file (``mus1.preferences``).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from .experiment_cli import _resolve_project_path


def register_commands(app: typer.Typer) -> None:
    """Register the `compute` subcommand group on the main app."""
    compute_app = typer.Typer(help="Deterministic compute operations")
    app.add_typer(compute_app, name="compute")

    @compute_app.command("tracking-confidence")
    def cmd_tracking_confidence(
        experiment_id: Optional[str] = typer.Argument(
            None,
            help="Single experiment to compute. Omit when using --cohort.",
        ),
        cohort: Optional[str] = typer.Option(
            None, "--cohort", "-c",
            help="Compute over every member of the named cohort.",
        ),
        project_path: Optional[Path] = typer.Option(
            None, "--project-path", "-p",
            help="Project root (parent of cohorts/, experiment_data/, "
                 "validation_data/). Default: ./data.",
        ),
        write: bool = typer.Option(
            False, "--write",
            help="Persist results into experiment JSON "
                 "(extraction.tracking_confidence). Idempotent; overwrites.",
        ),
        json_out: bool = typer.Option(
            False, "--json",
            help="Emit JSON to stdout (single dict, or list for cohort).",
        ),
        pcutoff: Optional[float] = typer.Option(
            None, "--pcutoff",
            help="Override pcutoff. Default from preferences or DLC docs (0.6).",
        ),
        overall_frac: Optional[float] = typer.Option(
            None, "--overall-frac-threshold",
            help="Override LOW_LIKELIHOOD_OVERALL threshold.",
        ),
        bp_frac: Optional[float] = typer.Option(
            None, "--bodypart-frac-threshold",
            help="Override BODYPART_FAILURE threshold.",
        ),
        dropout_min: Optional[int] = typer.Option(
            None, "--dropout-min-frames",
            help="Override LIKELIHOOD_DROPOUT_RUN minimum-run length.",
        ),
    ):
        """Compute baseline DLC tracking confidence for one experiment or a cohort.

        Pure function of the DLC CSV — does not require any task-specific
        state (markings, metrics). Run this first when intaking new
        experiments to filter unusable tracking before deeper QC.
        """
        if (experiment_id is None) == (cohort is None):
            typer.echo(
                "error: provide exactly one of <experiment_id> or --cohort.",
                err=True,
            )
            raise typer.Exit(code=2)

        proj = _resolve_project_path(project_path)
        thresholds = _resolve_thresholds(proj, pcutoff, overall_frac,
                                         bp_frac, dropout_min)

        targets: List[Tuple[str, Path]] = _resolve_targets(
            proj, experiment_id=experiment_id, cohort=cohort)

        if not targets:
            typer.echo("error: no experiments matched.", err=True)
            raise typer.Exit(code=1)

        results: List[Dict[str, Any]] = []
        for exp_id, json_path in targets:
            res = _compute_one(json_path, thresholds)
            res["experiment_id"] = exp_id
            results.append(res)
            if write:
                _persist_to_json(json_path, res)

        if json_out:
            payload: Any = results if cohort else results[0]
            typer.echo(json.dumps(payload, indent=2))
        else:
            _print_summary(results, write=write)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_thresholds(
    project_path: Path,
    pcutoff: Optional[float],
    overall_frac: Optional[float],
    bp_frac: Optional[float],
    dropout_min: Optional[int],
) -> Dict[str, Any]:
    """Resolve threshold overrides: CLI > preferences > module defaults."""
    from ..preferences import load_preferences
    prefs = load_preferences(project_path=project_path)
    tc = prefs.compute.tracking_confidence
    return {
        "pcutoff": pcutoff if pcutoff is not None else tc.pcutoff,
        "overall_frac_threshold": (
            overall_frac if overall_frac is not None else tc.overall_frac_threshold),
        "bodypart_frac_threshold": (
            bp_frac if bp_frac is not None else tc.bodypart_frac_threshold),
        "dropout_min_frames": (
            dropout_min if dropout_min is not None else tc.dropout_min_frames),
    }


def _resolve_targets(
    project_path: Path,
    *,
    experiment_id: Optional[str],
    cohort: Optional[str],
) -> List[Tuple[str, Path]]:
    """Return ``[(experiment_id, json_path), ...]`` to compute on."""
    from ..web.discovery import find_experiment_dir, find_experiment_json
    out: List[Tuple[str, Path]] = []

    if experiment_id is not None:
        exp_dir = find_experiment_dir(project_path, experiment_id)
        if exp_dir is None:
            return []
        jp = find_experiment_json(exp_dir)
        if jp is None:
            return []
        return [(experiment_id, jp)]

    # Cohort mode
    cohort_path = project_path / "cohorts" / f"{cohort}.json"
    if not cohort_path.is_file():
        return []
    try:
        cohort_data = json.loads(cohort_path.read_text())
    except Exception:
        return []
    members = cohort_data.get("members") or []
    for m in members:
        if not isinstance(m, dict):
            continue
        eid = m.get("experiment_id")
        if not eid:
            continue
        exp_dir = find_experiment_dir(project_path, eid)
        if exp_dir is None:
            continue
        jp = find_experiment_json(exp_dir)
        if jp is not None:
            out.append((eid, jp))
    return out


def _compute_one(json_path: Path, thresholds: Dict[str, Any]) -> Dict[str, Any]:
    """Read DLC csv path from JSON, run compute, return the result dict."""
    from ..compute.tracking_confidence import compute_tracking_confidence
    from ..compute.tracking import resolve_dlc_csv_path

    try:
        data = json.loads(json_path.read_text())
    except Exception as e:
        return {"error": f"could not read JSON {json_path}: {e}"}

    csv_path_str = resolve_dlc_csv_path(data.get("extraction"))
    if not csv_path_str:
        return {"error": "no DLC CSV path found in extraction.* (legacy or dlc_runs)"}

    from ..paths import resolve_with_mount_aliases
    csv_path = resolve_with_mount_aliases(csv_path_str) or Path(csv_path_str)

    return compute_tracking_confidence(csv_path, **thresholds)


def _persist_to_json(json_path: Path, result: Dict[str, Any]) -> None:
    """Write ``result`` into ``extraction.tracking_confidence`` AND merge
    its flags into ``qc_flags.auto_flags`` via the shared merger.

    The two-target write is the same operation the QC pane's Compute
    button does — see ``mus1.compute.tracking_flags.merge_into_qc_flags``.
    Single helper, two call sites, guaranteed not to drift.
    """
    from ..compute.tracking_flags import merge_into_qc_flags

    data = json.loads(json_path.read_text())
    ext = data.setdefault("extraction", {})
    # Strip the synthesized experiment_id key; it lives at top level of JSON.
    payload = {k: v for k, v in result.items() if k != "experiment_id"}
    ext["tracking_confidence"] = payload

    # Merge universal-layer flags into qc_flags.auto_flags (additive,
    # preserves task-specific flags already present).
    data["qc_flags"] = merge_into_qc_flags(data.get("qc_flags"), payload)

    json_path.write_text(json.dumps(data, indent=2) + "\n")


def _print_summary(results: List[Dict[str, Any]], *, write: bool) -> None:
    """Print a one-screen-per-experiment summary."""
    from ..compute.tracking_confidence import render_summary_text

    for i, res in enumerate(results):
        exp_id = res.get("experiment_id", "?")
        if i > 0:
            typer.echo("")
        typer.echo(f"=== {exp_id} ===")
        typer.echo(render_summary_text(res))
    if write:
        typer.echo("")
        typer.echo(f"persisted {len(results)} result(s) to extraction.tracking_confidence")
