"""CLI subcommands for multi-DLC-tracking management.

Registers the ``tracking`` subcommand group on the main mus1 ``app``::

    mus1 tracking register-run --cohort C --dlc-project P --snapshot S --csv-dir D --write
    mus1 tracking list-runs <experiment_id> [--json]
    mus1 tracking compare --cohort C --run-a ID --run-b ID [--out FILE]
    mus1 tracking set-cohort-model --cohort C --run-id ID [--basis "..."]
    mus1 tracking set-primary <experiment_id> --run-id ID
    mus1 tracking set-primary <experiment_id> --clear

These are the building blocks for: registering several trackings against a
single experiment (so a v1 production model and a v2 candidate coexist),
comparing them, and declaring a cohort-level winner that downstream compute
picks up via :func:`mus1.compute.tracking.resolve_dlc_csv_path`.

Writes are append-only to ``extraction.dlc_runs[]`` (register-run) or set a
single flag (set-primary); they use an atomic temp-file replace so a
concurrent reader never sees a half-written JSON. ``--dry-run`` reports
without writing. Agent-friendly: every command takes ``--json``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from .experiment_cli import _resolve_project_path


def register_commands(app: typer.Typer) -> None:
    """Register the `tracking` subcommand group on the main app."""
    tracking_app = typer.Typer(help="Manage multiple DLC trackings per experiment")
    app.add_typer(tracking_app, name="tracking")

    # -- register-run -------------------------------------------------------
    @tracking_app.command("register-run")
    def cmd_register_run(
        experiment_id: Optional[str] = typer.Argument(
            None, help="Single experiment. Omit when using --cohort."),
        cohort: Optional[str] = typer.Option(
            None, "--cohort", "-c", help="Register across every cohort member."),
        dlc_project: str = typer.Option(
            ..., "--dlc-project", help="DLC project dir name (stored as-is)."),
        snapshot: str = typer.Option(
            ..., "--snapshot", help="Snapshot label, e.g. snapshot-best-160."),
        csv_dir: Optional[Path] = typer.Option(
            None, "--csv-dir",
            help="Directory holding inference CSVs named {video_stem}{scorer}.csv. "
                 "Default: <project>/inference-results-pytorch (searched recursively)."),
        dlc_project_root: Optional[Path] = typer.Option(
            None, "--dlc-project-root",
            help="DLC projects root, used to default --csv-dir. "
                 "Default: <project>/../dlc_workspace/projects."),
        scorer: Optional[str] = typer.Option(
            None, "--scorer", help="DLC scorer. Inferred from CSV filename if omitted."),
        shuffle: int = typer.Option(1, "--shuffle"),
        config: str = typer.Option("", "--config", help="Path to the DLC config.yaml."),
        primary: bool = typer.Option(
            False, "--primary",
            help="Mark this run as the per-experiment primary (clears others)."),
        supersede: bool = typer.Option(
            False, "--supersede",
            help="Mark prior dlc_runs entries as superseded by this one."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        write: bool = typer.Option(False, "--write", help="Persist to experiment JSONs."),
        dry_run: bool = typer.Option(False, "--dry-run"),
        json_out: bool = typer.Option(False, "--json"),
    ):
        """Register a DLC model's CSV output against one experiment or a cohort.

        For each experiment, finds the inference CSV by video stem, infers
        the scorer (and thus the stable run_id), and appends a
        ``dlc_runs[]`` entry. Idempotent: an identical (run_id, csv) entry is
        skipped. Does not run inference — point ``--csv-dir`` at completed
        output.
        """
        proj = _resolve_project_path(project_path)
        targets = _resolve_targets(proj, experiment_id=experiment_id, cohort=cohort)
        if not targets:
            typer.echo("error: no experiments matched.", err=True)
            raise typer.Exit(code=1)

        search_dir = _resolve_csv_dir(proj, csv_dir, dlc_project_root, dlc_project)

        results: List[Dict[str, Any]] = []
        for exp_id, jp in targets:
            results.append(_register_one(
                jp, exp_id,
                dlc_project=dlc_project, snapshot=snapshot, search_dir=search_dir,
                scorer=scorer, shuffle=shuffle, config=config,
                primary=primary, supersede=supersede,
                write=write and not dry_run,
            ))

        _emit(results, json_out=json_out, dry_run=dry_run, write=write,
              human=_print_register_summary)

    # -- list-runs ----------------------------------------------------------
    @tracking_app.command("list-runs")
    def cmd_list_runs(
        experiment_id: str = typer.Argument(...),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        json_out: bool = typer.Option(False, "--json"),
    ):
        """List every DLC tracking registered against an experiment."""
        from ..compute.tracking import list_dlc_runs

        proj = _resolve_project_path(project_path)
        jp = _json_for_experiment(proj, experiment_id)
        if jp is None:
            typer.echo(f"error: experiment {experiment_id} not found.", err=True)
            raise typer.Exit(code=1)
        data = json.loads(jp.read_text())
        runs = list_dlc_runs(data.get("extraction"))
        rows = [{
            "run_id": r.run_id, "model_label": r.model_label, "snapshot": r.snapshot,
            "primary": r.primary, "source": r.source, "csv_path": r.csv_path,
            "csv_exists": bool(r.csv_path) and Path(r.csv_path).is_file(),
        } for r in runs]
        if json_out:
            typer.echo(json.dumps({"experiment_id": experiment_id, "runs": rows}, indent=2))
            return
        if not rows:
            typer.echo(f"{experiment_id}: no DLC runs registered.")
            return
        typer.echo(f"=== {experiment_id}: {len(rows)} run(s) ===")
        for r in rows:
            mark = " *PRIMARY*" if r["primary"] else ""
            exists = "" if r["csv_exists"] else "  [CSV MISSING]"
            typer.echo(f"  [{r['source']}] {r['run_id']}{mark}{exists}")

    # -- compare ------------------------------------------------------------
    @tracking_app.command("compare")
    def cmd_compare(
        run_a: str = typer.Option(..., "--run-a", help="run_id of model A."),
        run_b: str = typer.Option(..., "--run-b", help="run_id of model B."),
        cohort: Optional[str] = typer.Option(None, "--cohort", "-c"),
        experiment_id: Optional[str] = typer.Option(None, "--experiment-id"),
        pcutoff: float = typer.Option(0.6, "--pcutoff"),
        top_n: int = typer.Option(20, "--top-n"),
        out: Optional[Path] = typer.Option(None, "--out", help="Write rollup JSON here."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        json_out: bool = typer.Option(False, "--json"),
    ):
        """Compare two registered models (A vs B) across a cohort/experiment."""
        from ..compute.tracking import get_dlc_run
        from ..compute.tracking_comparison import compare_tracks, comparison_to_jsonable
        from ..paths import resolve_with_mount_aliases

        proj = _resolve_project_path(project_path)
        targets = _resolve_targets(proj, experiment_id=experiment_id, cohort=cohort)
        if not targets:
            typer.echo("error: no experiments matched.", err=True)
            raise typer.Exit(code=1)

        per_exp: List[Dict[str, Any]] = []
        for exp_id, jp in targets:
            data = json.loads(jp.read_text())
            ext = data.get("extraction")
            ra, rb = get_dlc_run(ext, run_a), get_dlc_run(ext, run_b)
            if ra is None or rb is None:
                missing = run_a if ra is None else run_b
                per_exp.append({"experiment_id": exp_id, "status": "missing_run",
                                "detail": f"run not registered: {missing}"})
                continue
            ca = resolve_with_mount_aliases(ra.csv_path) or Path(ra.csv_path)
            cb = resolve_with_mount_aliases(rb.csv_path) or Path(rb.csv_path)
            if not Path(ca).is_file() or not Path(cb).is_file():
                per_exp.append({"experiment_id": exp_id, "status": "csv_missing"})
                continue
            comp = compare_tracks(Path(ca), Path(cb), run_a_id=run_a, run_b_id=run_b,
                                  pcutoff=pcutoff, top_n=top_n)
            if comp is None:
                per_exp.append({"experiment_id": exp_id, "status": "unreadable"})
                continue
            row = comparison_to_jsonable(comp, top_n=top_n)
            row["experiment_id"] = exp_id
            row["status"] = "ok"
            per_exp.append(row)

        rollup = _build_compare_rollup(run_a, run_b, pcutoff, per_exp)
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rollup, indent=2) + "\n")
            typer.echo(f"wrote rollup -> {out}")
        if json_out:
            typer.echo(json.dumps(rollup, indent=2))
        else:
            _print_compare_rollup(rollup)

    # -- set-cohort-model ---------------------------------------------------
    @tracking_app.command("set-cohort-model")
    def cmd_set_cohort_model(
        cohort: str = typer.Option(..., "--cohort", "-c"),
        run_id: str = typer.Option(..., "--run-id", help="Model run_id to select."),
        basis: str = typer.Option("", "--basis", help="Why this model was chosen."),
        selected_by: str = typer.Option("cli", "--selected-by"),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        dry_run: bool = typer.Option(False, "--dry-run"),
        json_out: bool = typer.Option(False, "--json"),
    ):
        """Declare the DLC model a cohort's analyses should use.

        The run_id must be registered on at least one cohort member (run
        ``register-run`` first); its full model metadata is copied into the
        cohort's ``analysis_config.dlc_model`` block.
        """
        from datetime import datetime, timezone
        from ..web.cohorts import load_cohort, save_cohort, set_cohort_dlc_model

        proj = _resolve_project_path(project_path)
        cohort_path = proj / "cohorts" / f"{cohort}.json"
        if not cohort_path.is_file():
            typer.echo(f"error: cohort {cohort} not found at {cohort_path}", err=True)
            raise typer.Exit(code=1)
        cohort_data = load_cohort(cohort_path)

        run = _lookup_run_on_members(proj, cohort_data, run_id)
        if run is None:
            typer.echo(
                f"error: run_id '{run_id}' is not registered on any member of "
                f"'{cohort}'. Run `mus1 tracking register-run` first.", err=True)
            raise typer.Exit(code=1)

        model = {
            "run_id": run.run_id,
            "dlc_project": run.dlc_project,
            "scorer": run.scorer,
            "shuffle": run.shuffle,
            "snapshot": run.snapshot,
            "selected_at": datetime.now(timezone.utc).isoformat(),
            "selected_by": selected_by,
        }
        if basis:
            model["basis"] = basis
        set_cohort_dlc_model(cohort_data, model)

        if not dry_run:
            save_cohort(cohort_path, cohort_data)
        if json_out:
            typer.echo(json.dumps({"cohort": cohort, "dlc_model": model,
                                   "dry_run": dry_run}, indent=2))
        else:
            verb = "would set" if dry_run else "set"
            typer.echo(f"{verb} {cohort}.analysis_config.dlc_model = {run.run_id}")

    # -- set-primary --------------------------------------------------------
    @tracking_app.command("set-primary")
    def cmd_set_primary(
        experiment_id: str = typer.Argument(...),
        run_id: Optional[str] = typer.Option(
            None, "--run-id", help="Run to flag primary (clears others)."),
        clear: bool = typer.Option(False, "--clear", help="Remove all primary flags."),
        project_path: Optional[Path] = typer.Option(None, "--project-path", "-p"),
        dry_run: bool = typer.Option(False, "--dry-run"),
        json_out: bool = typer.Option(False, "--json"),
    ):
        """Set (or clear) the per-experiment primary-model override.

        The primary override wins over any cohort-level selection for this
        one experiment.
        """
        if (run_id is None) == (not clear):
            typer.echo("error: provide exactly one of --run-id or --clear.", err=True)
            raise typer.Exit(code=2)

        proj = _resolve_project_path(project_path)
        jp = _json_for_experiment(proj, experiment_id)
        if jp is None:
            typer.echo(f"error: experiment {experiment_id} not found.", err=True)
            raise typer.Exit(code=1)
        data = json.loads(jp.read_text())
        runs = (data.get("extraction") or {}).get("dlc_runs") or []

        matched = False
        from ..compute.tracking import derive_run_id
        for entry in runs:
            if not isinstance(entry, dict):
                continue
            entry.pop("primary", None)
            if run_id and not clear:
                eid = derive_run_id(
                    str(entry.get("scorer") or ""),
                    str(entry.get("dlc_project") or ""),
                    str(entry.get("snapshot") or ""))
                if eid == run_id:
                    entry["primary"] = True
                    matched = True
        if run_id and not clear and not matched:
            typer.echo(f"error: run_id '{run_id}' not registered on {experiment_id}.",
                       err=True)
            raise typer.Exit(code=1)

        if not dry_run:
            _atomic_write_json(jp, data)
        action = "cleared all primary flags" if clear else f"set primary = {run_id}"
        if json_out:
            typer.echo(json.dumps({"experiment_id": experiment_id, "action": action,
                                   "dry_run": dry_run}, indent=2))
        else:
            verb = "would " if dry_run else ""
            typer.echo(f"{experiment_id}: {verb}{action}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_targets(
    project_path: Path, *, experiment_id: Optional[str], cohort: Optional[str],
) -> List[Tuple[str, Path]]:
    """Return ``[(experiment_id, json_path), ...]``. Reuses compute_cli logic."""
    from .compute_cli import _resolve_targets as _impl
    if (experiment_id is None) == (cohort is None):
        # Neither or both -> invalid; surface as empty so callers error out.
        return [] if experiment_id is None else _impl(
            project_path, experiment_id=experiment_id, cohort=None)
    return _impl(project_path, experiment_id=experiment_id, cohort=cohort)


def _json_for_experiment(project_path: Path, experiment_id: str) -> Optional[Path]:
    from ..web.discovery import find_experiment_dir, find_experiment_json
    exp_dir = find_experiment_dir(project_path, experiment_id)
    if exp_dir is None:
        return None
    return find_experiment_json(exp_dir)


def _resolve_csv_dir(
    project_path: Path,
    csv_dir: Optional[Path],
    dlc_project_root: Optional[Path],
    dlc_project: str,
) -> Path:
    """Resolve the directory to search for inference CSVs."""
    if csv_dir is not None:
        return Path(csv_dir)
    root = dlc_project_root or (project_path.parent / "dlc_workspace" / "projects")
    return Path(root) / dlc_project / "inference-results-pytorch"


def _find_csv_for_video(search_dir: Path, video_stem: str, snapshot: str) -> Optional[Path]:
    """Find a DLC CSV ``{video_stem}{scorer}.csv`` under search_dir (recursive)."""
    if not search_dir.is_dir():
        return None
    matches = sorted(search_dir.rglob(f"{video_stem}*.csv"))
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    norm_snap = snapshot.lower().replace("_", "").replace("-", "")
    snap_hits = [m for m in matches
                 if norm_snap and norm_snap in m.name.lower().replace("_", "").replace("-", "")]
    if len(snap_hits) == 1:
        return snap_hits[0]
    return (snap_hits or matches)[0]  # deterministic fallback


def _infer_scorer(csv_name: str, video_stem: str) -> str:
    base = csv_name[:-4] if csv_name.endswith(".csv") else csv_name
    return base[len(video_stem):] if base.startswith(video_stem) else ""


def _register_one(
    jp: Path, exp_id: str, *,
    dlc_project: str, snapshot: str, search_dir: Path,
    scorer: Optional[str], shuffle: int, config: str,
    primary: bool, supersede: bool, write: bool,
) -> Dict[str, Any]:
    from ..compute.tracking import derive_run_id, make_dlc_run_entry

    data = json.loads(jp.read_text())
    video = (data.get("video") or {})
    video_path = video.get("path") or video.get("filename") or ""
    video_stem = Path(video_path).stem
    if not video_stem:
        return {"experiment_id": exp_id, "status": "no_video"}

    csv_path = _find_csv_for_video(search_dir, video_stem, snapshot)
    if csv_path is None:
        return {"experiment_id": exp_id, "status": "pending",
                "detail": f"no CSV for stem {video_stem} under {search_dir}"}

    eff_scorer = scorer or _infer_scorer(csv_path.name, video_stem)
    h5 = csv_path.with_suffix(".h5")
    run_id = derive_run_id(eff_scorer, dlc_project, snapshot)

    ext = data.setdefault("extraction", {})
    runs = ext.setdefault("dlc_runs", [])

    # Idempotency: skip if an entry already has this run_id AND csv.
    for entry in runs:
        if not isinstance(entry, dict):
            continue
        existing_id = derive_run_id(str(entry.get("scorer") or ""),
                                    str(entry.get("dlc_project") or ""),
                                    str(entry.get("snapshot") or ""))
        existing_csv = str((entry.get("output") or {}).get("csv") or "")
        if existing_id == run_id and existing_csv == str(csv_path):
            return {"experiment_id": exp_id, "status": "already_registered",
                    "run_id": run_id}

    if supersede and runs:
        for entry in runs:
            if isinstance(entry, dict) and "superseded_by" not in entry:
                entry["superseded_by"] = "next_entry"

    if primary:
        for entry in runs:
            if isinstance(entry, dict):
                entry.pop("primary", None)

    entry = make_dlc_run_entry(
        dlc_project=dlc_project, snapshot=snapshot, csv=str(csv_path),
        scorer=eff_scorer, shuffle=shuffle, config=config,
        h5=str(h5) if h5.is_file() else "",
        note="Registered by `mus1 tracking register-run`.",
        primary=primary,
    )
    runs.append(entry)

    if write:
        _atomic_write_json(jp, data)
    return {"experiment_id": exp_id, "status": "registered", "run_id": run_id,
            "csv": str(csv_path), "primary": primary}


def _lookup_run_on_members(project_path: Path, cohort_data: Dict[str, Any], run_id: str):
    """Return the first DlcRun matching run_id across cohort members, or None."""
    from ..compute.tracking import get_dlc_run
    from ..web.discovery import find_experiment_dir, find_experiment_json
    for m in cohort_data.get("members") or []:
        eid = m.get("experiment_id") if isinstance(m, dict) else None
        if not eid:
            continue
        exp_dir = find_experiment_dir(project_path, eid)
        if exp_dir is None:
            continue
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue
        run = get_dlc_run(data.get("extraction"), run_id)
        if run is not None:
            return run
    return None


def _build_compare_rollup(
    run_a: str, run_b: str, pcutoff: float, per_exp: List[Dict[str, Any]],
) -> Dict[str, Any]:
    import numpy as np

    ok = [r for r in per_exp if r.get("status") == "ok"]
    status_counts: Dict[str, int] = {}
    for r in per_exp:
        s = r.get("status", "?")
        status_counts[s] = status_counts.get(s, 0) + 1

    # Per-bodypart median coverage_delta across experiments (B - A).
    cov_by_bp: Dict[str, List[float]] = {}
    b_better: Dict[str, int] = {}
    for r in ok:
        for bp, pbc in (r.get("per_bodypart") or {}).items():
            delta = pbc.get("coverage_delta")
            if delta is None:
                continue
            cov_by_bp.setdefault(bp, []).append(float(delta))
            if delta > 0:
                b_better[bp] = b_better.get(bp, 0) + 1
    median_cov_delta = {
        bp: float(np.median(vals)) for bp, vals in cov_by_bp.items() if vals
    }
    return {
        "run_a_id": run_a,
        "run_b_id": run_b,
        "pcutoff": pcutoff,
        "n_experiments": len(per_exp),
        "n_compared": len(ok),
        "status_counts": status_counts,
        "median_coverage_delta_by_bodypart": median_cov_delta,
        "n_experiments_b_better_coverage_by_bodypart": b_better,
        "per_experiment": per_exp,
    }


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON via a temp file + atomic replace (crash- and reader-safe)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _emit(results, *, json_out, dry_run, write, human) -> None:
    if json_out:
        typer.echo(json.dumps(results, indent=2))
    else:
        human(results, dry_run=dry_run, write=write)


def _print_register_summary(results: List[Dict[str, Any]], *, dry_run: bool, write: bool) -> None:
    counts: Dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for r in results:
        typer.echo(f"  {r['experiment_id']}: {r['status']}"
                   + (f"  ({r.get('detail')})" if r.get("detail") else ""))
    typer.echo("")
    typer.echo("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if not write and not dry_run:
        typer.echo("(no --write given; nothing persisted)")
    elif dry_run:
        typer.echo("(--dry-run; nothing persisted)")


def _print_compare_rollup(rollup: Dict[str, Any]) -> None:
    typer.echo(f"=== compare {rollup['run_a_id']}  vs  {rollup['run_b_id']} ===")
    typer.echo(f"compared {rollup['n_compared']}/{rollup['n_experiments']} experiments "
               f"(pcutoff={rollup['pcutoff']})")
    typer.echo("status: " + ", ".join(f"{k}={v}" for k, v in sorted(rollup['status_counts'].items())))
    typer.echo("")
    typer.echo("median coverage Δ (B − A) by bodypart  [+ = B better]:")
    deltas = rollup["median_coverage_delta_by_bodypart"]
    b_better = rollup["n_experiments_b_better_coverage_by_bodypart"]
    for bp in sorted(deltas):
        typer.echo(f"  {bp:14s} {deltas[bp]:+.3f}   (B better on {b_better.get(bp, 0)} exp)")
