"""
Index ML tracking run outputs into MUS1 DB.

Canonical location (project-scoped; DB-first):
  <project_path>/runs/ml_tracking/<run_id>/

The web Training Monitor view lists runs from the DB (external_artifacts),
but still reads metrics/log files from disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..repository import RepositoryFactory


@dataclass(frozen=True)
class MLTrackingRunsIndexStats:
    runs_seen: int
    runs_indexed: int
    artifacts_added: int
    artifacts_skipped_existing: int
    qc_events_added: int


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
    existing = repos.external_artifacts.find_one(kind=kind, path=str(path))
    if existing is not None:
        return False
    repos.external_artifacts.add(kind=kind, path=str(path), meta=meta)
    return True


def index_ml_tracking_runs(
    repos: RepositoryFactory,
    *,
    runs_root: Path,
    only_latest: bool = False,
) -> MLTrackingRunsIndexStats:
    """
    Index ML tracking run outputs under `<project_path>/runs/ml_tracking/`.
    """
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
        _qc("MISSING_INPUT", {"kind": "ml_tracking_runs_root", "path": str(base)})
        return MLTrackingRunsIndexStats(
            runs_seen=0,
            runs_indexed=0,
            artifacts_added=0,
            artifacts_skipped_existing=0,
            qc_events_added=qc_added,
        )

    run_dirs = [p for p in base.iterdir() if p.is_dir()]

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
        runs_seen += 1

        run_meta = {
            "runs_root": str(base),
            "run_name": run_dir.name,
            "run_dir": str(run_dir),
        }
        if _artifact_upsert(repos, kind="ml_tracking_run_dir", path=run_dir, meta=run_meta):
            added += 1
            runs_indexed += 1
        else:
            skipped += 1

        rs = run_dir / "run_status.json"
        if not rs.exists():
            _qc("MISSING_EXPECTED_FILE", {"kind": "ml_tracking_run_status", "path": str(rs), "run_dir": str(run_dir)})
        else:
            st = _safe_read_json(rs) or {}
            if isinstance(st, dict) and st.get("state") in {"failed", "error"}:
                _qc("RUN_FAILED", {"kind": "ml_tracking", "run_dir": str(run_dir), "run_status": st})

        # Optional artifacts (don’t QC as missing; they may be written during/after training)
        for pth, ak in [
            (run_dir / "metrics.csv", "ml_tracking_metrics_csv"),
            (run_dir / "metrics_by_exposure.csv", "ml_tracking_metrics_by_exposure_csv"),
        ]:
            if pth.exists():
                if _artifact_upsert(repos, kind=ak, path=pth, meta={"run_dir": str(run_dir)}):
                    added += 1
                else:
                    skipped += 1

    return MLTrackingRunsIndexStats(
        runs_seen=runs_seen,
        runs_indexed=runs_indexed,
        artifacts_added=added,
        artifacts_skipped_existing=skipped,
        qc_events_added=qc_added,
    )

