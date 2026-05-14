"""``mus1 arena-inference`` CLI subcommand group (T14).

Generic arena-U-Net inference driver. Given a registered arena profile
id and a cohort, locate matching experiments, sample N frames per
video, run the active U-Net (per ``data/arena_models.yaml``), dispatch
the configured post-processor, aggregate across sampled frames, and
write the result into ``arena_markings.predicted.<mask_to_marking>``
in each experiment's JSON.

Successor to the EZM-only ``mus1 ezm-arena-infer`` command. The legacy
command is preserved as a thin back-compat wrapper that calls
:func:`_run_arena_inference` here with the EZM profile pinned.

Activation discipline (per user 2026-05-07 confirmation): every
predicted block records the *active* ``run_id`` from the loaded model
so historical reviews stay anchored to the model they were performed
against.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from rich import print as rich_print


# Exit codes — must match the legacy ``ezm-arena-infer`` for back-compat.
EXIT_OK = 0
EXIT_MODEL_FAIL = 2
EXIT_NO_COHORT = 3
EXIT_PARTIAL = 4


def _resolve_project_path(project_path: Optional[Path]) -> Path:
    """Mirror arena_cli's resolver: prefer cwd if it has cohorts/ or
    project.json, else fall back to ``cwd/data`` when that looks like
    the project root. Returns an absolute path either way."""
    if project_path is not None:
        return Path(project_path).resolve()
    cwd = Path.cwd()
    if (cwd / "project.json").is_file() or (cwd / "cohorts").is_dir():
        return cwd.resolve()
    if (cwd / "data" / "project.json").is_file() or (cwd / "data" / "cohorts").is_dir():
        return (cwd / "data").resolve()
    return cwd.resolve()


def _resolve_cohort_path(project_path: Path, cohort: str) -> Path:
    """Map a cohort name like 'ezm_publication' to its JSON file.

    Accepts an already-suffixed ``.json``, a plain name, or an absolute
    path to a JSON file.
    """
    p = Path(cohort)
    if p.is_absolute() and p.is_file():
        return p.resolve()
    cohorts_dir = project_path / "cohorts"
    if cohort.endswith(".json"):
        cand = (cohorts_dir / cohort).resolve()
        if cand.is_file():
            return cand
    return (cohorts_dir / f"{cohort}.json").resolve()


def _load_cohort_eids(cohort_path: Path) -> List[str]:
    """Return cohort experiment_ids in declaration order. Empty list on
    any parse / shape problem so callers can treat 'no eids' as 'cohort
    is unusable for this run' uniformly."""
    if not cohort_path.is_file():
        return []
    try:
        data = json.loads(cohort_path.read_text())
    except Exception:
        return []
    members = data.get("members", []) or []
    eids: List[str] = []
    for m in members:
        if isinstance(m, dict):
            eid = m.get("experiment_id")
        else:
            eid = m
        if eid:
            eids.append(str(eid))
    return eids


def _experiment_matches_profile(
    data: Dict[str, Any], task_type: str, profile_id: str,
    task_default_lookup: Dict[str, Optional[str]],
) -> bool:
    """Return True if the experiment is bound to *profile_id*.

    Matching rule:
      1. If the JSON's ``arena_markings.arena_profile.profile_id`` is
         set, use it (most specific).
      2. Otherwise fall back to the task's default ``arena_profile_id``.
    """
    am = data.get("arena_markings") or {}
    ap = am.get("arena_profile") or {}
    explicit = (ap.get("profile_id") or "").strip() if isinstance(ap, dict) else ""
    if explicit:
        return explicit == profile_id
    return task_default_lookup.get(task_type) == profile_id


def _build_task_default_lookup() -> Dict[str, Optional[str]]:
    """Return ``{task_id -> arena_profile_id_or_None}`` from the task registry."""
    from mus1.tasks.registry import TaskRegistry
    reg = TaskRegistry()
    out: Dict[str, Optional[str]] = {}
    for tid in reg.list_ids():
        try:
            out[tid] = reg.get(tid).arena_profile_id
        except Exception:
            out[tid] = None
    return out


def _aggregate_ezm_wedge_points(
    per_frame: List[Tuple[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Median of 4 wedge points across sampled frames (legacy behaviour)."""
    import numpy as np
    all_pts = np.array([r["points"] for _, r in per_frame])  # (N, 4, 2)
    median_pts = np.median(all_pts, axis=0).tolist()
    mid_i = len(per_frame) // 2
    rep_fi, rep_r = per_frame[mid_i]
    return {
        "points": median_pts,
        "source_frame_idx": int(rep_fi),
        "ellipse_orig": rep_r.get("ellipse_orig"),
        "quality": rep_r.get("quality", {}),
    }


def _aggregate_circular_arena_boundary(
    per_frame: List[Tuple[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Aggregate fitted ellipses across sampled frames.

    Median of center_xy and axes_xy; circular mean of angle_deg (since
    ellipse orientation wraps modulo 180°, but cv2 reports it in
    [0, 180), we lift to [0, 2π) by doubling, take the circular mean,
    then halve. This matches the convention in
    :func:`mus1.compute.arena_unet._circular_mean`.
    """
    import numpy as np
    centers = np.array([r["ellipse"]["center_xy"] for _, r in per_frame], dtype=float)
    axes = np.array([r["ellipse"]["axes_xy"] for _, r in per_frame], dtype=float)
    angles_deg = np.array([r["ellipse"]["angle_deg"] for _, r in per_frame], dtype=float)
    # cv2 ellipse orientation is mod-180; double the angle to lift to mod-360 for safe averaging.
    rad = np.radians(2.0 * angles_deg)
    s = float(np.sin(rad).mean())
    c = float(np.cos(rad).mean())
    avg_rad = math.atan2(s, c)
    avg_deg = (math.degrees(avg_rad) / 2.0) % 180.0
    med_center = np.median(centers, axis=0).tolist()
    med_axes = np.median(axes, axis=0).tolist()
    mid_i = len(per_frame) // 2
    rep_fi, rep_r = per_frame[mid_i]
    return {
        "ellipse": {
            "center_xy": [float(med_center[0]), float(med_center[1])],
            "axes_xy": [float(med_axes[0]), float(med_axes[1])],
            "angle_deg": float(avg_deg),
        },
        "source_frame_idx": int(rep_fi),
        "quality": rep_r.get("quality", {}),
    }


def _aggregate(per_frame: List[Tuple[int, Dict[str, Any]]],
                mask_to_marking: str) -> Optional[Dict[str, Any]]:
    """Dispatch the per-marking aggregator. Returns ``None`` if no
    aggregator is registered for *mask_to_marking*."""
    if not per_frame:
        return None
    if mask_to_marking == "ezm_wedge_points":
        return _aggregate_ezm_wedge_points(per_frame)
    if mask_to_marking == "circular_arena_boundary":
        return _aggregate_circular_arena_boundary(per_frame)
    return None


def _video_path_from_json(data: Dict[str, Any]) -> str:
    """Resolve the experiment's recorded video path; normalises the
    ``/center1/`` legacy mount to the current ``/import/c1/`` path."""
    vp = (data.get("video") or {}).get("path", "")
    if not vp:
        return ""
    return vp.replace("/center1/", "/import/c1/")


def _run_arena_inference(
    *,
    profile_id: str,
    cohort: str,
    project_path: Optional[Path] = None,
    frames_per_video: int = 5,
    overwrite: bool = False,
    dry_run: bool = False,
    json_out: bool = False,
    limit: Optional[int] = None,
    # Legacy back-compat hook: the old ``ezm-arena-infer`` lets users
    # pass an explicit checkpoint path that overrides arena_models.yaml.
    model_path_override: Optional[Path] = None,
) -> int:
    """Shared driver used by both ``arena-inference run`` and the
    legacy ``ezm-arena-infer`` command. Returns the exit code; callers
    should ``sys.exit(rc)`` so typer surfaces the correct status.
    """
    proj = _resolve_project_path(project_path)
    cohort_path = _resolve_cohort_path(proj, cohort)

    # ── Cohort presence + content checks (exit 3) ────────────────────
    if not cohort_path.is_file():
        rich_print(f"[red]Cohort file not found: {cohort_path}[/red]")
        return EXIT_NO_COHORT
    eids = _load_cohort_eids(cohort_path)
    if not eids:
        rich_print(f"[red]No experiments in cohort {cohort!r}[/red]")
        return EXIT_NO_COHORT
    if limit is not None:
        eids = eids[: int(limit)]

    # ── Profile validation ───────────────────────────────────────────
    from mus1.arena_profiles import ArenaProfileRegistry
    profiles = ArenaProfileRegistry.from_config(proj)
    if profile_id not in profiles.list_ids():
        rich_print(f"[red]Unknown arena profile: {profile_id!r}[/red]")
        rich_print(f"[dim]Available: {profiles.list_ids()}[/dim]")
        return EXIT_MODEL_FAIL

    # ── Resolve the active registry entry so we know mask_to_marking ─
    from mus1.compute.arena_models import ArenaModelRegistry
    registry = ArenaModelRegistry.load(proj)
    entry = registry.get(profile_id)
    if entry is None and model_path_override is None:
        rich_print(
            f"[red]No active arena U-Net for profile {profile_id!r}.[/red]\n"
            f"[dim]Register one with `mus1 arena-models activate {profile_id} "
            f"<run_id> --checkpoint <path>`[/dim]"
        )
        return EXIT_MODEL_FAIL

    mask_to_marking = (entry.mask_to_marking if entry else "ezm_wedge_points") or ""
    if not mask_to_marking:
        rich_print(
            f"[red]Active model for {profile_id!r} has no mask_to_marking "
            f"post-processor configured.[/red]"
        )
        return EXIT_MODEL_FAIL

    # ── Load model (legacy override path supports raw checkpoint) ────
    from mus1.compute.arena_unet import (
        load_arena_unet, load_ezm_unet, sample_video_frame,
        infer_arena_mask, run_post_processor, model_run_id,
        model_version_string,
    )
    rich_print(f"[cyan]Arena inference[/cyan]")
    rich_print(f"  Profile: {profile_id}")
    rich_print(f"  Cohort:  {cohort} ({len(eids)} candidate experiments)")
    rich_print(f"  Mask -> marking: {mask_to_marking}")
    rich_print(f"  Frames per video: {frames_per_video}")
    rich_print(f"  Dry-run: {dry_run}, overwrite: {overwrite}")

    try:
        if model_path_override is not None:
            # Legacy path: caller forced a specific checkpoint. We still
            # honour any registered run_id by trying the profile-aware
            # loader first; on miss, fall back to load_ezm_unet.
            ckpt = Path(model_path_override)
            if not ckpt.is_file():
                rich_print(f"[red]Checkpoint not found: {ckpt}[/red]")
                return EXIT_MODEL_FAIL
            model = load_ezm_unet(str(ckpt), device="cpu")
            model_ver = model_version_string(str(ckpt))
            run_id = entry.run_id if entry else ""
            # Tag so model_run_id() returns the registered run_id.
            setattr(model, "_mus1_run_id", run_id)
            setattr(model, "_mus1_profile_id", profile_id)
            setattr(model, "_mus1_mask_to_marking", mask_to_marking)
        else:
            model = load_arena_unet(profile_id, proj)
            ckpt_path = entry.checkpoint if entry else None
            model_ver = model_version_string(str(ckpt_path)) if ckpt_path else ""
    except LookupError as e:
        rich_print(f"[red]Model load failed: {e}[/red]")
        return EXIT_MODEL_FAIL
    except FileNotFoundError as e:
        rich_print(f"[red]Model load failed: {e}[/red]")
        return EXIT_MODEL_FAIL
    except Exception as e:
        rich_print(f"[red]Model load failed: {e}[/red]")
        return EXIT_MODEL_FAIL

    run_id = model_run_id(model)
    rich_print(f"  Loaded run_id={run_id or '(none)'} version={model_ver or '(none)'}")

    # ── Discover experiments + filter by profile binding ─────────────
    from mus1.web.discovery import find_experiment_dir, find_experiment_json
    task_default_lookup = _build_task_default_lookup()

    n_ok = 0
    n_skipped_existing = 0
    n_skipped_profile = 0
    n_failed = 0
    successes: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    import numpy as np
    import cv2

    for i, eid in enumerate(eids):
        exp_dir = find_experiment_dir(proj, eid)
        if exp_dir is None or not exp_dir.is_dir():
            failures.append({"experiment_id": eid, "reason": "experiment_dir_missing"})
            n_failed += 1
            continue
        jp = find_experiment_json(exp_dir)
        if jp is None:
            failures.append({"experiment_id": eid, "reason": "json_missing"})
            n_failed += 1
            continue
        try:
            data = json.loads(jp.read_text())
        except Exception as e:
            failures.append({"experiment_id": eid, "reason": f"json_parse_error: {e}"})
            n_failed += 1
            continue

        # Profile-binding filter
        task_type = exp_dir.parent.name  # parent of exp_dir is the task folder
        if not _experiment_matches_profile(
            data, task_type, profile_id, task_default_lookup,
        ):
            n_skipped_profile += 1
            continue

        am = data.get("arena_markings") or {}
        predicted = am.get("predicted") or {}
        if predicted.get(mask_to_marking) and not overwrite:
            n_skipped_existing += 1
            continue

        vpath = _video_path_from_json(data)
        if not vpath:
            failures.append({"experiment_id": eid, "reason": "video_path_missing"})
            n_failed += 1
            continue
        if not Path(vpath).exists():
            failures.append({"experiment_id": eid, "reason": "video_file_missing",
                              "path": vpath})
            n_failed += 1
            continue

        cap = cv2.VideoCapture(vpath)
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        if n_frames < 30:
            failures.append({"experiment_id": eid, "reason": f"too_few_frames: {n_frames}"})
            n_failed += 1
            continue

        # Sample evenly from the 10–90% range to skip intro/outro frames.
        sample_idx = np.linspace(int(n_frames * 0.1), int(n_frames * 0.9),
                                  frames_per_video, dtype=int)
        per_frame: List[Tuple[int, Dict[str, Any]]] = []
        for fi in sample_idx:
            frame = sample_video_frame(vpath, int(fi))
            if frame is None:
                continue
            mask, meta = infer_arena_mask(model, frame)
            try:
                r = run_post_processor(mask_to_marking, mask, meta)
            except KeyError as e:
                failures.append({"experiment_id": eid, "reason": f"unknown_post_processor: {e}"})
                n_failed += 1
                per_frame = []  # abort this experiment
                break
            if r is not None:
                per_frame.append((int(fi), r))

        if not per_frame:
            # If we already counted a failure above (post-processor error),
            # don't double-count.
            if not failures or failures[-1].get("experiment_id") != eid:
                failures.append({"experiment_id": eid, "reason": "no_valid_predictions"})
                n_failed += 1
            continue

        agg = _aggregate(per_frame, mask_to_marking)
        if agg is None:
            failures.append({"experiment_id": eid,
                              "reason": f"no_aggregator_for_marking: {mask_to_marking}"})
            n_failed += 1
            continue

        # Capture source frame shape from the first sampled frame.
        f0 = sample_video_frame(vpath, int(sample_idx[0]))
        src_h, src_w = ((int(f0.shape[0]), int(f0.shape[1]))
                         if f0 is not None else (1080, 1080))

        predicted_block: Dict[str, Any] = dict(agg)
        predicted_block["frame_shape"] = [src_h, src_w]
        predicted_block["qc_status"] = "predicted_unreviewed"
        predicted_block["predicted_at"] = datetime.now(tz=timezone.utc).isoformat()
        predicted_block["model_run_id"] = run_id
        predicted_block["model_version"] = model_ver  # back-compat tag
        predicted_block["n_frames_sampled"] = len(per_frame)

        if not dry_run:
            am.setdefault("predicted", {})
            am["predicted"][mask_to_marking] = predicted_block
            data["arena_markings"] = am
            jp.write_text(json.dumps(data, indent=2, default=str) + "\n")

        success_row: Dict[str, Any] = {
            "experiment_id": eid,
            "n_frames_used": len(per_frame),
            "marking": mask_to_marking,
        }
        # Provide a marking-specific summary stat for the report.
        q = predicted_block.get("quality") or {}
        if "open_pixel_fraction" in q:
            success_row["open_pixel_fraction"] = q["open_pixel_fraction"]
        if "arena_pixel_fraction" in q:
            success_row["arena_pixel_fraction"] = q["arena_pixel_fraction"]
        successes.append(success_row)
        n_ok += 1
        if (i + 1) % 25 == 0 or (i + 1) == len(eids):
            rich_print(
                f"  [{i+1}/{len(eids)}] ok={n_ok} "
                f"skipped_existing={n_skipped_existing} "
                f"skipped_profile={n_skipped_profile} "
                f"failed={n_failed}"
            )

    summary: Dict[str, Any] = {
        "profile_id": profile_id,
        "cohort": cohort,
        "mask_to_marking": mask_to_marking,
        "model_run_id": run_id,
        "model_version": model_ver,
        "dry_run": dry_run,
        "n_total": len(eids),
        "n_predicted": n_ok,
        "n_skipped_existing": n_skipped_existing,
        "n_skipped_profile_mismatch": n_skipped_profile,
        "n_failed": n_failed,
        "frames_per_video": frames_per_video,
        "successes": successes,
        "failures": failures,
    }
    if json_out:
        rich_print(json.dumps(summary, indent=2, default=str))
    else:
        rich_print(f"[green]Arena inference complete[/green]")
        rich_print(
            f"  Predicted: {n_ok}/{len(eids)}, "
            f"skipped_existing: {n_skipped_existing}, "
            f"skipped_profile: {n_skipped_profile}, "
            f"failed: {n_failed}"
        )
        if failures:
            rich_print(f"  [yellow]Failures:[/yellow]")
            for f in failures[:5]:
                rich_print(f"    {f}")
            if len(failures) > 5:
                rich_print(f"    ... and {len(failures) - 5} more")

    if n_failed > 0:
        return EXIT_PARTIAL
    return EXIT_OK


def register_commands(parent_app: typer.Typer) -> None:
    """Register the ``mus1 arena-inference`` subcommand group."""
    arena_inf_app = typer.Typer(
        help="Profile-aware arena U-Net inference (writes arena_markings.predicted).",
    )
    parent_app.add_typer(arena_inf_app, name="arena-inference")

    @arena_inf_app.command("run")
    def arena_inference_run(
        profile_id: str = typer.Argument(
            ..., help="Arena profile id (e.g. ezm_460mm, tamco_black_bucket).",
        ),
        cohort: str = typer.Option(
            ..., "--cohort", "-c",
            help="Cohort name (matches <project_path>/cohorts/<name>.json).",
        ),
        project_path: Optional[Path] = typer.Option(
            None, "--project-path", "-p",
            help="Project root. Default: cwd or cwd/data, whichever looks right.",
        ),
        frames_per_video: int = typer.Option(
            5, "--frames-per-video",
            help="Frames to sample per video; aggregator combines them.",
        ),
        overwrite: bool = typer.Option(
            False, "--overwrite",
            help="Re-infer even if a predicted block already exists.",
        ),
        dry_run: bool = typer.Option(
            False, "--dry-run",
            help="Don't write JSONs; just report what would be done.",
        ),
        json_out: bool = typer.Option(
            False, "--json-out",
            help="Emit machine-readable JSON summary on stdout.",
        ),
        limit: Optional[int] = typer.Option(
            None, "--limit",
            help="Process only the first N cohort members (for test runs).",
        ),
    ):
        """Run the active arena U-Net for *profile_id* on every cohort
        experiment bound to that profile. Writes predictions under
        ``arena_markings.predicted.<mask_to_marking>`` in each JSON.

        Exit codes:

          0 = all matching experiments inferred successfully
          2 = profile unknown / no active model / checkpoint missing
          3 = cohort file missing or empty
          4 = some experiments failed (successes still written)
        """
        rc = _run_arena_inference(
            profile_id=profile_id,
            cohort=cohort,
            project_path=project_path,
            frames_per_video=frames_per_video,
            overwrite=overwrite,
            dry_run=dry_run,
            json_out=json_out,
            limit=limit,
        )
        if rc != 0:
            raise typer.Exit(rc)
