"""Cohort management — named, versioned subsets of experiments.

Cohort manifests live in ``data/cohorts/`` as JSON files.
Experiment JSONs hold per-experiment data (QC, metrics); manifests hold membership.

Every save recomputes a ``summary`` block with unique subject counts, group
breakdowns, and validation warnings so the cohort JSON is self-documenting.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from .discovery import find_experiment_dir, find_experiment_json, get_data_roots


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Experiment metadata resolution (for summary computation)
# ---------------------------------------------------------------------------

def _resolve_experiment_metadata(
    experiment_id: str,
    data_roots: Sequence[Path],
) -> Optional[Dict[str, str]]:
    """Read subject/genotype/sex/date from an experiment JSON on disk.

    Searches *data_roots* in order; returns the first match. *data_roots*
    is the list returned by :func:`mus1.web.discovery.get_data_roots`.
    """
    parts = experiment_id.split("_", 1)
    task = parts[0] if parts else ""
    exp_dir: Optional[Path] = None
    for root in data_roots:
        candidate = root / task / experiment_id
        if candidate.is_dir():
            exp_dir = candidate
            break
    if exp_dir is None:
        return None
    jp = find_experiment_json(exp_dir)
    if jp is None:
        return None
    try:
        data = json.loads(jp.read_text())
    except Exception:
        return None
    md = data.get("metadata", {})
    return {
        "experiment_id": experiment_id,
        "task_type": task,
        "subject_id": str(md.get("subject_id", "")),
        "genotype": str(md.get("genotype", "")),
        "sex": str(md.get("sex", "")),
        "date_recorded": str(md.get("date_recorded", "")),
    }


def compute_cohort_summary(
    cohort: Dict[str, Any],
    *,
    experiment_lookup: Optional[Dict[str, Dict[str, str]]] = None,
    data_roots: Optional[Sequence[Path]] = None,
    experiment_data_root: Optional[Path] = None,  # back-compat
) -> Dict[str, Any]:
    """Compute integrity summary from cohort members.

    Args:
        cohort: Cohort dict with ``members`` list.
        experiment_lookup: Optional pre-built mapping of experiment_id to
            metadata dicts (keys: subject_id, genotype, sex, task_type,
            date_recorded).  When provided, avoids disk I/O.
        data_roots: List of root directories to search for experiment
            folders (e.g. ``[data/experiment_data, data/validation_data]``).
            Used as fallback when *experiment_lookup* is None.
        experiment_data_root: Deprecated single-root fallback. If given and
            *data_roots* is None, treated as ``[experiment_data_root]``.

    Returns:
        Summary dict suitable for embedding as ``cohort["summary"]``.
    """
    if data_roots is None and experiment_data_root is not None:
        data_roots = [Path(experiment_data_root)]
    member_ids = cohort_member_ids(cohort)
    n_experiments = len(member_ids)

    warnings: List[str] = []
    unresolved: List[str] = []
    coh_tasks: Set[str] = set(cohort.get("task_types") or [])

    subject_ids: Set[str] = set()
    groups: Dict[str, int] = defaultdict(int)
    subjects_by_group: Dict[str, Set[str]] = defaultdict(set)
    task_type_counts: Dict[str, int] = defaultdict(int)
    seen_subject_date: Dict[str, List[str]] = defaultdict(list)

    for eid in sorted(member_ids):
        # Resolve metadata
        meta: Optional[Dict[str, str]] = None
        if experiment_lookup is not None:
            meta = experiment_lookup.get(eid)
        if meta is None and data_roots:
            meta = _resolve_experiment_metadata(eid, data_roots)

        if meta is None:
            unresolved.append(eid)
            continue

        sid = meta.get("subject_id", "")
        genotype = meta.get("genotype", "")
        sex = meta.get("sex", "")
        task = meta.get("task_type", "")
        date_rec = meta.get("date_recorded", "")

        if sid:
            subject_ids.add(sid)
        group_key = f"{genotype}_{sex}" if genotype and sex else "UNKNOWN"
        groups[group_key] += 1
        if sid:
            subjects_by_group[group_key].add(sid)
        if task:
            task_type_counts[task] += 1
            if coh_tasks and task not in coh_tasks:
                warnings.append(
                    f"{eid}: task_type '{task}' not in cohort task_types {sorted(coh_tasks)}"
                )
        # Track duplicate subject+date within same task
        sd_key = f"{task}_{sid}_{date_rec}"
        seen_subject_date[sd_key].append(eid)

    # Flag duplicates
    for key, eids in seen_subject_date.items():
        if len(eids) > 1:
            warnings.append(f"duplicate subject+date: {eids}")

    if unresolved:
        warnings.append(f"unresolved_members ({len(unresolved)}): {unresolved}")

    return {
        "n_experiments": n_experiments,
        "n_subjects": len(subject_ids),
        "groups": dict(sorted(groups.items())),
        "subjects_by_group": {
            k: sorted(v) for k, v in sorted(subjects_by_group.items())
        },
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "warnings": warnings,
        "computed_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_cohort(
    name: str,
    *,
    task_types: Optional[List[str]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """Return a new cohort dict (not yet saved to disk)."""
    return {
        "name": name,
        "version": 1,
        "description": description,
        "task_types": task_types or [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "criteria": {"type": "manual", "description": ""},
        "members": [],
    }


def load_cohort(cohort_path: Path) -> Dict[str, Any]:
    """Load a cohort manifest from disk."""
    return json.loads(cohort_path.read_text())


def save_cohort(
    cohort_path: Path,
    cohort: Dict[str, Any],
    *,
    experiment_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
    """Write cohort manifest to disk, recomputing the summary block.

    Args:
        cohort_path: Destination JSON file.
        cohort: Cohort dict to save.
        experiment_lookup: Optional pre-built mapping of experiment_id to
            metadata dicts.  When *None*, metadata is resolved from disk
            using the sibling ``experiment_data/`` directory.
    """
    # Resolve data_roots from project_path (cohort_path.parent.parent is data/)
    project_path = cohort_path.parent.parent
    roots = get_data_roots(project_path) if experiment_lookup is None else None

    cohort["summary"] = compute_cohort_summary(
        cohort,
        experiment_lookup=experiment_lookup,
        data_roots=roots,
    )
    cohort["updated_at"] = _now_iso()
    cohort_path.parent.mkdir(parents=True, exist_ok=True)
    cohort_path.write_text(json.dumps(cohort, indent=2) + "\n", encoding="utf-8")


def list_cohorts(
    cohorts_dir: Path,
    *,
    task_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return lightweight summaries for all cohorts on disk."""
    if not cohorts_dir.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(cohorts_dir.glob("*.json")):
        try:
            c = json.loads(p.read_text())
        except Exception:
            continue
        if task_type and task_type not in (c.get("task_types") or []):
            continue
        summary = c.get("summary") or {}
        out.append({
            "name": c.get("name", p.stem),
            "path": str(p),
            "version": c.get("version", 1),
            "n_members": len(c.get("members") or []),
            "n_subjects": summary.get("n_subjects"),
            "task_types": c.get("task_types", []),
            "updated_at": c.get("updated_at", ""),
        })
    return out


def cohort_member_ids(cohort: Dict[str, Any]) -> set:
    """Return the set of experiment_ids in a cohort."""
    return {m["experiment_id"] for m in (cohort.get("members") or []) if "experiment_id" in m}


# ---------------------------------------------------------------------------
# Membership operations
# ---------------------------------------------------------------------------

def add_member(
    cohort: Dict[str, Any],
    experiment_id: str,
    *,
    notes: str = "",
) -> Dict[str, Any]:
    """Add an experiment to the cohort (idempotent)."""
    existing = cohort_member_ids(cohort)
    if experiment_id in existing:
        return cohort
    cohort.setdefault("members", []).append({
        "experiment_id": experiment_id,
        "added_at": _now_iso(),
        "notes": notes,
    })
    return cohort


def remove_member(cohort: Dict[str, Any], experiment_id: str) -> Dict[str, Any]:
    """Remove an experiment from the cohort."""
    cohort["members"] = [
        m for m in (cohort.get("members") or [])
        if m.get("experiment_id") != experiment_id
    ]
    return cohort


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_training_csv(
    cohort: Dict[str, Any],
    experiment_data_root: Path,
    out_path: Path,
    *,
    label_source: str = "auto",
) -> int:
    """Write a training CSV from cohort members.

    Scans experiment JSONs for zone_json_path and video_path. Searches
    every configured data root (so validation cohorts also export).
    Returns the number of rows written.

    *experiment_data_root* is retained as the project-path anchor for
    back-compat: its parent is treated as the project_path used to resolve
    additional data roots (e.g. validation_data).
    """
    import csv

    project_root = Path(experiment_data_root).parent
    data_roots = get_data_roots(project_root)
    # Always include the explicitly supplied root as a fallback, in case
    # config-driven discovery hasn't picked it up.
    if Path(experiment_data_root) not in data_roots:
        data_roots = [Path(experiment_data_root)] + data_roots

    rows: List[Dict[str, str]] = []
    for member in cohort.get("members") or []:
        eid = member.get("experiment_id", "")
        if not eid:
            continue
        exp_dir = find_experiment_dir(project_root, eid, data_roots=data_roots)
        if exp_dir is None:
            continue
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue
        az = (data.get("derived_data") or {}).get("arena_zones") or {}
        zone_json_path = az.get("zone_json_path", "")
        video_path = (data.get("video") or {}).get("path", "")
        if not zone_json_path:
            continue
        # Resolve zone_json_path to absolute
        zj_abs = project_root / zone_json_path
        rows.append({
            "video_path": video_path,
            "zone_json": str(zj_abs),
            "label_source": label_source,
            "frame_idx": "0",
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["video_path", "zone_json", "label_source", "frame_idx"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)
