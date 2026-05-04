"""Shared experiment discovery across the canonical mus1 data roots.

mus1 scans exactly two directories under the project path for
per-experiment JSONs:

  • ``experiment_data/``  — publication-grade experiments
  • ``validation_data/``  — held-out validation experiments

This pair is hard-coded by design (see :data:`DATA_ROOTS`). Adding a third
root is a code-level decision, not a config tweak — the goal is that
"where do experiments live?" has the same answer in every environment.
If you genuinely need a third root, edit :data:`DATA_ROOTS` and update
the runbook; usually though the right answer is a new cohort manifest,
not a new directory.

Each root has the same internal layout::

    {ROOT}/{TASK}/{EXP_ID}/{EXP_ID}.json
    {ROOT}/{TASK}/{EXP_ID}/recording/{video}

where ``TASK`` ∈ :data:`SUPPORTED_TASKS`.

This module is the single source of truth for discovery and is used by
every marking pane, the cohort manager, and the CLI. Standard cache TTL
for filesystem scans is :data:`CACHE_TTL_SECONDS` (5 minutes); panes that
mutate JSONs on disk should call ``st.cache_data.clear()`` after the write
rather than lowering the TTL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

#: Canonical data roots, in scan order. The first root that contains an
#: experiment with a given ID wins (publication > validation). Hard-coded
#: by design — see module docstring.
DATA_ROOTS: Tuple[str, ...] = ("experiment_data", "validation_data")

#: Backwards-compatible alias for ``DATA_ROOTS``. Prefer the new name.
DEFAULT_DATA_ROOTS: Tuple[str, ...] = DATA_ROOTS

#: Supported task type folder names. Adding a new task requires updating
#: this tuple plus a per-task pane in ``web/views/``.
SUPPORTED_TASKS: Tuple[str, ...] = ("OF", "EZM", "NOR", "NOF", "RR")

#: Streamlit cache TTL for filesystem-scan loaders (seconds). 5 minutes
#: balances read-after-write freshness against repeated-nav cost on
#: cohorts approaching n≈900 experiments. Panes that mutate JSONs on
#: disk should call ``st.cache_data.clear()`` after the write.
CACHE_TTL_SECONDS: int = 300


def get_data_roots(project_path: Path) -> List[Path]:
    """Return the canonical data-root directories that exist for *project_path*.

    Always returns a subset of :data:`DATA_ROOTS` (in declaration order),
    keeping only roots that exist on disk. Roots that don't exist are
    dropped silently so the call site never sees a missing path.
    """
    project_path = Path(project_path).resolve()
    out: List[Path] = []
    seen: set = set()
    for name in DATA_ROOTS:
        p = (project_path / name).resolve()
        if p.is_dir() and p not in seen:
            out.append(p)
            seen.add(p)
    return out


def iter_experiment_dirs(
    project_path: Path,
    task: Optional[str] = None,
    *,
    data_roots: Optional[Sequence[Path]] = None,
) -> Iterator[Tuple[Path, str, Path]]:
    """Yield ``(root, task, exp_dir)`` triples for every experiment on disk.

    - *root* is the absolute data root that contains *exp_dir*.
    - *task* is the task-type folder name (e.g. ``"EZM"``).
    - *exp_dir* is the experiment folder. Its name is the experiment_id.
    - When *task* is given, only that task is yielded.
    """
    roots = list(data_roots) if data_roots is not None else get_data_roots(project_path)
    tasks = [task.upper()] if task else list(SUPPORTED_TASKS)
    for root in roots:
        for t in tasks:
            task_dir = root / t
            if not task_dir.is_dir():
                continue
            for entry in sorted(task_dir.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    yield root, t, entry


def find_experiment_json(exp_dir: Path) -> Optional[Path]:
    """Return the canonical per-experiment JSON inside *exp_dir*, if any.

    Project convention: each experiment folder contains exactly one
    ``{EXP_ID}.json``. We glob for the first ``*.json`` to be tolerant of
    minor naming drift.
    """
    candidate = exp_dir / f"{exp_dir.name}.json"
    if candidate.is_file():
        return candidate
    for jp in sorted(exp_dir.glob("*.json")):
        return jp
    return None


def _read_json(path: Path) -> Optional[Dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def discover_experiments(
    project_path: Path,
    task: Optional[str] = None,
    *,
    data_roots: Optional[Sequence[Path]] = None,
) -> List[Dict]:
    """Return a list of experiment summary dicts across all data roots.

    Each dict has at least::

        {
            "experiment_id": str,
            "task_type": str,         # OF/EZM/NOR/NOF/RR
            "data_root": str,         # absolute path of the data root
            "exp_dir": str,           # absolute path of the experiment folder
            "json_path": str,         # absolute path of the canonical JSON
            "subject_id": str,        # from metadata
            "genotype": str,
            "sex": str,
            "date_recorded": str,
            "cohort": str,            # metadata.experiment_level.cohort, "" if absent
        }

    Sorted by (task_type, experiment_id) for stable UI ordering.
    Experiments without a JSON are skipped silently.
    """
    rows: List[Dict] = []
    for root, t, exp_dir in iter_experiment_dirs(project_path, task, data_roots=data_roots):
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        d = _read_json(jp) or {}
        md = d.get("metadata", {}) if isinstance(d, dict) else {}
        exp_lvl = md.get("experiment_level", {}) if isinstance(md, dict) else {}
        rows.append(
            {
                "experiment_id": exp_dir.name,
                "task_type": t,
                "data_root": str(root),
                "exp_dir": str(exp_dir),
                "json_path": str(jp),
                "subject_id": str(md.get("subject_id", "")),
                "genotype": str(md.get("genotype", "")),
                "sex": str(md.get("sex", "")),
                "date_recorded": str(md.get("date_recorded", "")),
                "cohort": str(exp_lvl.get("cohort", "") if isinstance(exp_lvl, dict) else ""),
            }
        )
    rows.sort(key=lambda r: (r["task_type"], r["experiment_id"]))
    return rows


def find_experiment_dir(
    project_path: Path,
    experiment_id: str,
    *,
    data_roots: Optional[Sequence[Path]] = None,
) -> Optional[Path]:
    """Locate the folder for *experiment_id* across all data roots."""
    task = experiment_id.split("_", 1)[0]
    roots = list(data_roots) if data_roots is not None else get_data_roots(project_path)
    for root in roots:
        candidate = root / task / experiment_id
        if candidate.is_dir():
            return candidate
    return None


def task_dirs_for_root(root: Path, task: str) -> List[Path]:
    """Return the per-task experiment folders under *root* for *task*."""
    task_dir = root / task.upper()
    if not task_dir.is_dir():
        return []
    return sorted(p for p in task_dir.iterdir() if p.is_dir())


def task_dirs_across_roots(
    project_path: Path,
    task: str,
    *,
    data_roots: Optional[Sequence[Path]] = None,
) -> List[Path]:
    """Return per-task experiment folders across all configured data roots."""
    roots = list(data_roots) if data_roots is not None else get_data_roots(project_path)
    out: List[Path] = []
    for root in roots:
        out.extend(task_dirs_for_root(root, task))
    return out


def resolve_dlc_csv_path(extraction: Optional[Dict]) -> str:
    """Return the DLC tracking CSV path from either supported JSON schema.

    Two schemas exist in the canonical data roots:
      • Legacy (publication batches): ``extraction.tracking_file_path``
      • New (validation_2026 batches): ``extraction.dlc_runs[-1].output.csv``

    The newer pipeline records every DLC run as an append-only entry under
    ``dlc_runs[]`` and never writes the legacy flat field, so loaders that
    only read ``tracking_file_path`` silently miss tracking for those
    experiments. Use this resolver instead.
    """
    if not isinstance(extraction, dict):
        return ""
    legacy = extraction.get("tracking_file_path") or ""
    if legacy:
        return legacy
    runs = extraction.get("dlc_runs") or []
    if runs:
        last = runs[-1] if isinstance(runs[-1], dict) else {}
        out = last.get("output") or {}
        return out.get("csv") or ""
    return ""
