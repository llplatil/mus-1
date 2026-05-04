"""
Index EZM open/closed U-Net training run outputs into MUS1 DB.

Purpose:
- Make prior training runs discoverable from the DB (not by manual path pasting).
- Preserve provenance of the most recent downstream-used run artifacts:
  - run directory
  - train_config.json
  - training_index_from_zones.csv
  - model checkpoints (e.g. model_best.pt)
  - labeled_eval/worst_frames.csv (+ overlay directory pointers)

We store run artifacts as ExternalArtifact rows with experiment_id/subject_id NULL.
This keeps the DB-first workflow consistent while avoiding premature schema expansion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ..repository import RepositoryFactory


@dataclass(frozen=True)
class EZMUnetRunsIndexStats:
    runs_seen: int
    runs_indexed: int
    artifacts_added: int
    artifacts_skipped_existing: int
    qc_events_added: int


def _path_aliases(p: Path) -> list[str]:
    """
    Return canonical/aliased path strings for matching existing artifacts.

    Wraps :func:`mus1.paths.mount_alias_variants` and adds the
    resolved-symlink form for callers that need to dedupe artifacts
    across mounts AND symlink targets.
    """
    from mus1.paths import mount_alias_variants
    out: list[str] = list(mount_alias_variants(p))
    try:
        resolved = str(p.resolve())
    except Exception:
        resolved = ""
    if resolved and resolved not in out:
        out.append(resolved)
    return out


def _canonical_store_path(p: Path) -> str:
    """Choose a stable stored path to reduce mount-alias duplicates.

    Resolves through symlinks first, then normalizes the
    ``/import/c1/`` form to the canonical ``/center1/`` mount.
    """
    try:
        s = str(p.resolve())
    except Exception:
        s = str(p)
    from mus1.paths import mount_alias_variants
    for v in mount_alias_variants(s):
        if v.startswith("/center1/"):
            return v
    return s


def _safe_read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _artifact_upsert(
    repos: RepositoryFactory,
    *,
    kind: str,
    path: Path,
    meta: Dict[str, Any],
) -> bool:
    canonical = _canonical_store_path(path)
    aliases = _path_aliases(Path(canonical))
    # Check existing rows across common mount aliases.
    for alias in aliases:
        existing = repos.external_artifacts.find_one(kind=kind, path=alias)
        if existing is not None:
            return False
    repos.external_artifacts.add(kind=kind, path=canonical, meta=meta)
    return True


def index_ezm_unet_runs(
    repos: RepositoryFactory,
    *,
    workspace_root: Path,
    runs_root: Optional[Path] = None,
    only_latest: bool = False,
) -> EZMUnetRunsIndexStats:
    """
    Index EZM U-Net run outputs under a project-scoped runs root.

    Canonical location (DB-first):
      <project_path>/runs/ezm_unet/<run_id>/

    A run directory is considered valid if it contains at least one of:
      - training_index_from_zones.csv
      - run_status.json
      - model_best.pt
      - train_config.json

    Writes ExternalArtifact rows for key run artifacts and QC events for missing expected files.
    """
    ws = Path(workspace_root).resolve()
    if runs_root is None:
        raise ValueError("runs_root is required (project-scoped runs; no workspace scanning).")
    base = Path(runs_root).resolve()

    qc_added = 0
    added = 0
    skipped = 0
    runs_seen = 0
    runs_indexed = 0

    def _qc(code: str, details: dict) -> None:
        nonlocal qc_added
        repos.qc_events.add(scope="ml", code=code, details=details)
        qc_added += 1

    if not base.exists():
        _qc("MISSING_INPUT", {"kind": "ezm_unet_runs_root", "path": str(base)})
        return EZMUnetRunsIndexStats(runs_seen=0, runs_indexed=0, artifacts_added=0, artifacts_skipped_existing=0, qc_events_added=qc_added)

    run_dirs = [p for p in base.iterdir() if p.is_dir()]
    # Sort newest-first by directory mtime (more reliable than lexicographic run names).
    def _mtime(p: Path) -> float:
        try:
            rs = p / "run_status.json"
            if rs.exists():
                return float(rs.stat().st_mtime)
            return float(p.stat().st_mtime)
        except Exception:
            return 0.0

    run_dirs.sort(key=_mtime, reverse=True)
    if only_latest and run_dirs:
        run_dirs = [run_dirs[0]]

    for run_dir in run_dirs:
        # Skip directories that don't look like run outputs.
        has_any = any(
            (run_dir / fn).exists()
            for fn in ("training_index_from_zones.csv", "run_status.json", "model_best.pt", "train_config.json")
        )
        if not has_any:
            continue
        runs_seen += 1
        run_name = run_dir.name

        # "Run record" pointer
        run_meta = {
            "workspace_root": str(ws),
            "runs_root": str(base),
            "run_name": run_name,
            "run_dir": str(run_dir),
            "indexed_at": datetime.utcnow().isoformat(),
        }
        if _artifact_upsert(repos, kind="ezm_unet_run_dir", path=run_dir, meta=run_meta):
            added += 1
        else:
            skipped += 1

        # Config
        cfg_path = run_dir / "train_config.json"
        cfg = _safe_read_json(cfg_path) if cfg_path.exists() else None
        cfg_meta = {**run_meta, "kind": "train_config", "config": (cfg or {})}
        if cfg_path.exists():
            if _artifact_upsert(repos, kind="ezm_unet_train_config_json", path=cfg_path, meta=cfg_meta):
                added += 1
            else:
                skipped += 1
        else:
            _qc("MISSING_INPUT", {"kind": "ezm_unet_train_config_json", "path": str(cfg_path), **run_meta})

        # Training index generated from zone JSONs (lists training videos/frames)
        idx_path = run_dir / "training_index_from_zones.csv"
        if idx_path.exists():
            if _artifact_upsert(repos, kind="ezm_unet_training_index_csv", path=idx_path, meta={**run_meta, "kind": "training_index"}):
                added += 1
            else:
                skipped += 1
        else:
            _qc("MISSING_INPUT", {"kind": "ezm_unet_training_index_csv", "path": str(idx_path), **run_meta})

        # Primary model checkpoint(s)
        model_best = run_dir / "model_best.pt"
        if model_best.exists():
            if _artifact_upsert(repos, kind="ezm_unet_model_best_pt", path=model_best, meta={**run_meta, "kind": "model_best"}):
                added += 1
            else:
                skipped += 1
        else:
            _qc("MISSING_INPUT", {"kind": "ezm_unet_model_best_pt", "path": str(model_best), **run_meta})

        # Labeled eval worst-frames manifest + overlay pointers (store as artifacts; do not ingest PNGs)
        worst_csv = run_dir / "labeled_eval" / "worst_frames.csv"
        if worst_csv.exists():
            if _artifact_upsert(repos, kind="ezm_unet_labeled_eval_worst_frames_csv", path=worst_csv, meta={**run_meta, "kind": "worst_frames"}):
                added += 1
            else:
                skipped += 1
        else:
            _qc("MISSING_INPUT", {"kind": "ezm_unet_labeled_eval_worst_frames_csv", "path": str(worst_csv), **run_meta})

        overlays_dir = run_dir / "labeled_eval" / "best_worst_overlays"
        if overlays_dir.exists():
            if _artifact_upsert(repos, kind="ezm_unet_labeled_eval_overlays_dir", path=overlays_dir, meta={**run_meta, "kind": "best_worst_overlays_dir"}):
                added += 1
            else:
                skipped += 1
        else:
            # not always present (depends on pipeline stage), so QC but non-fatal
            _qc("MISSING_INPUT", {"kind": "ezm_unet_labeled_eval_overlays_dir", "path": str(overlays_dir), **run_meta})

        # QC overlays from training (if enabled)
        qc_overlays = run_dir / "qc_overlays"
        if qc_overlays.exists():
            if _artifact_upsert(repos, kind="ezm_unet_training_qc_overlays_dir", path=qc_overlays, meta={**run_meta, "kind": "qc_overlays_dir"}):
                added += 1
            else:
                skipped += 1

        runs_indexed += 1

    return EZMUnetRunsIndexStats(
        runs_seen=runs_seen,
        runs_indexed=runs_indexed,
        artifacts_added=added,
        artifacts_skipped_existing=skipped,
        qc_events_added=qc_added,
    )

