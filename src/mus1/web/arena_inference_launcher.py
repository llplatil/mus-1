"""Launch background ``mus1 arena-inference run`` jobs from the UI (T17).

Splits out the subprocess + run-dir bookkeeping so the Arena Training
pane can stay thin and the launcher can be unit-tested without
Streamlit. Pattern follows ``mus1 runs create`` / the existing
``runs/<kind_slug>/<run_id>/`` convention in :mod:`mus1.core.simple_cli`.

Each launch creates::

    <project_path>/runs/arena_inference/<run_id>/
        run_status.json          # written here; the running process appends
        stdout.log               # subprocess stdout
        stderr.log               # subprocess stderr

And registers the run dir as an ``arena_inference_run_dir`` artifact in
``mus1.db`` so the Training Monitor pane (and any future Job Monitor)
can discover it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RUN_KIND_SLUG = "arena_inference"
RUN_ARTIFACT_KIND = "arena_inference_run_dir"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(*, profile_id: str, cohort: str, now: Optional[datetime] = None) -> str:
    """Build a stable run_id from profile + cohort + UTC timestamp."""
    t = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    # Sanitize cohort so the run_id is filesystem-friendly
    cohort_clean = "".join(c if c.isalnum() or c in "_-" else "_" for c in cohort)
    return f"{t}__{profile_id}__{cohort_clean}"


@dataclass
class LaunchedRun:
    run_id: str
    run_dir: Path
    stdout_log: Path
    stderr_log: Path
    status_path: Path
    pid: Optional[int]
    command: List[str]


def build_command(
    *,
    profile_id: str,
    cohort: str,
    project_path: Path,
    frames_per_video: int = 5,
    overwrite: bool = False,
    limit: Optional[int] = None,
    python_executable: Optional[str] = None,
) -> List[str]:
    """Build the argv for ``mus1 arena-inference run ...``.

    *python_executable* lets tests substitute ``sys.executable`` /
    ``mus1-dev`` python explicitly; defaults to the current interpreter.
    """
    py = python_executable or sys.executable
    argv: List[str] = [
        py, "-m", "mus1", "arena-inference", "run", profile_id,
        "--cohort", cohort,
        "--project-path", str(project_path),
        "--frames-per-video", str(int(frames_per_video)),
    ]
    if overwrite:
        argv.append("--overwrite")
    if limit is not None:
        argv.extend(["--limit", str(int(limit))])
    return argv


def prepare_run_dir(
    *,
    project_path: Path,
    profile_id: str,
    cohort: str,
    command: List[str],
    now: Optional[datetime] = None,
) -> Tuple[Path, str]:
    """Create ``runs/arena_inference/<run_id>/`` and seed ``run_status.json``.

    Returns ``(run_dir, run_id)``. Idempotent only at the level of run_id
    uniqueness (the timestamp varies). Raises ``FileExistsError`` if the
    caller passes a pre-computed run_id that already exists on disk.
    """
    run_id = make_run_id(profile_id=profile_id, cohort=cohort, now=now)
    run_dir = Path(project_path) / "runs" / RUN_KIND_SLUG / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    status = {
        "kind": RUN_KIND_SLUG,
        "run_id": run_id,
        "state": "queued",
        "profile_id": profile_id,
        "cohort": cohort,
        "command": list(command),
        "created_at": _utc_now_iso(),
    }
    (run_dir / "run_status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return run_dir, run_id


def register_run_artifact(
    *,
    db_path: Path,
    run_dir: Path,
    run_id: str,
    profile_id: str,
    cohort: str,
) -> bool:
    """Insert an ``arena_inference_run_dir`` artifact row.

    Returns ``True`` if inserted, ``False`` if the row already exists or
    the DB file is missing. Failures inside the DB layer propagate.
    """
    db_path = Path(db_path)
    if not db_path.is_file():
        return False
    from ..core.schema import Database
    from ..core.repository import get_repository_factory

    db = Database(str(db_path))
    db.create_tables()
    repos = get_repository_factory(db)
    # Don't duplicate
    existing = repos.external_artifacts.find_one(
        kind=RUN_ARTIFACT_KIND, path=str(run_dir),
    )
    if existing is not None:
        return False
    repos.external_artifacts.add(
        kind=RUN_ARTIFACT_KIND,
        path=str(run_dir),
        meta={
            "kind": RUN_KIND_SLUG,
            "run_id": run_id,
            "profile_id": profile_id,
            "cohort": cohort,
            "run_dir": str(run_dir),
            "created_at": _utc_now_iso(),
        },
    )
    return True


def launch(
    *,
    project_path: Path,
    db_path: Optional[Path],
    profile_id: str,
    cohort: str,
    frames_per_video: int = 5,
    overwrite: bool = False,
    limit: Optional[int] = None,
    python_executable: Optional[str] = None,
    dry_run: bool = False,
    now: Optional[datetime] = None,
) -> LaunchedRun:
    """End-to-end: prepare run dir → register artifact → spawn subprocess.

    When *dry_run* is True, the run dir + status JSON are created and the
    artifact is registered, but the subprocess is NOT started (``pid`` in
    the return value will be ``None``). Useful for tests + for letting
    the operator preview the planned command.
    """
    command = build_command(
        profile_id=profile_id, cohort=cohort, project_path=project_path,
        frames_per_video=frames_per_video, overwrite=overwrite, limit=limit,
        python_executable=python_executable,
    )
    run_dir, run_id = prepare_run_dir(
        project_path=project_path, profile_id=profile_id, cohort=cohort,
        command=command, now=now,
    )
    if db_path is not None:
        try:
            register_run_artifact(
                db_path=db_path, run_dir=run_dir, run_id=run_id,
                profile_id=profile_id, cohort=cohort,
            )
        except Exception:
            # Don't block the launch on DB issues — the run_dir + status
            # file are sufficient state to find the run later.
            pass

    stdout_log = run_dir / "stdout.log"
    stderr_log = run_dir / "stderr.log"
    pid: Optional[int] = None
    if not dry_run:
        # Detach: write logs to files; close stdin; let the process outlive
        # the Streamlit re-render.
        with stdout_log.open("w") as so, stderr_log.open("w") as se:
            proc = subprocess.Popen(
                command,
                stdout=so, stderr=se, stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ},
            )
            pid = proc.pid
        # Update status to "running" with pid
        status_path = run_dir / "run_status.json"
        status = json.loads(status_path.read_text())
        status["state"] = "running"
        status["pid"] = pid
        status["started_at"] = _utc_now_iso()
        status_path.write_text(
            json.dumps(status, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return LaunchedRun(
        run_id=run_id,
        run_dir=run_dir,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        status_path=run_dir / "run_status.json",
        pid=pid,
        command=command,
    )


def relevant_cohorts_for_profile(
    *,
    project_path: Path,
    profile_id: str,
) -> List[str]:
    """Return cohort names whose ``task_types`` overlap with the tasks
    that default to *profile_id*.

    Sorted; empty list when the cohorts dir is missing or no match.
    """
    from mus1.tasks.registry import TaskRegistry
    cohorts_dir = Path(project_path) / "cohorts"
    if not cohorts_dir.is_dir():
        return []

    registry = TaskRegistry()
    relevant_tasks: set = set()
    for task_name in registry.list_ids():
        td = registry.get(task_name)
        if getattr(td, "arena_profile_id", None) == profile_id:
            relevant_tasks.add(task_name)
    if not relevant_tasks:
        return []

    out: List[str] = []
    for p in sorted(cohorts_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        task_types = set(data.get("task_types") or [])
        if task_types & relevant_tasks:
            out.append(data.get("name") or p.stem)
    return out
