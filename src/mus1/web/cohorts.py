"""Cohort management — named, versioned subsets of experiments.

Cohort manifests live in ``data/cohorts/`` as JSON files.
Experiment JSONs hold per-experiment data (QC, metrics); manifests hold membership.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def save_cohort(cohort_path: Path, cohort: Dict[str, Any]) -> None:
    """Write cohort manifest to disk."""
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
        out.append({
            "name": c.get("name", p.stem),
            "path": str(p),
            "version": c.get("version", 1),
            "n_members": len(c.get("members") or []),
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

    Scans experiment JSONs for zone_json_path and video_path.
    Returns the number of rows written.
    """
    import csv

    rows: List[Dict[str, str]] = []
    for member in cohort.get("members") or []:
        eid = member.get("experiment_id", "")
        if not eid:
            continue
        parts = eid.split("_", 1)
        task = parts[0] if parts else "EZM"
        exp_dir = experiment_data_root / task / eid
        if not exp_dir.is_dir():
            continue
        jsons = [f for f in exp_dir.iterdir() if f.suffix == ".json"]
        if not jsons:
            continue
        try:
            data = json.loads(jsons[0].read_text())
        except Exception:
            continue
        az = (data.get("derived_data") or {}).get("arena_zones") or {}
        zone_json_path = az.get("zone_json_path", "")
        video_path = (data.get("video") or {}).get("path", "")
        if not zone_json_path:
            continue
        # Resolve zone_json_path to absolute
        project_root = experiment_data_root.parent
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
