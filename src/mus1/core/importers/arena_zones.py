"""
Arena annotation zone JSON indexing.

Purpose:
- Keep zone JSONs written into the MoSeq2 workspace (for arena inference workflows).
- Make them DB-queryable by indexing them into MUS1 as external artifacts linked to
  experiments/subjects via the compiled session index contract.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from ..repository import RepositoryFactory


@dataclass(frozen=True)
class ArenaZonesIndexStats:
    total_jsons: int
    artifacts_added: int
    artifacts_skipped_existing: int
    qc_events_added: int
    linked_to_experiment: int
    unlinked: int


def _read_session_index_by_video_path(session_index_csv: Path) -> Dict[str, Dict[str, str]]:
    """
    Build a lookup of absolute video path -> row dict from session_index_filtered.csv.
    Uses the 'video_path' column.
    """
    by_path: Dict[str, Dict[str, str]] = {}
    with session_index_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}
        if "video_path" not in reader.fieldnames:
            return {}
        for row in reader:
            vp = (row.get("video_path") or "").strip()
            if not vp:
                continue
            by_path[str(Path(vp))] = row
    return by_path


def _resolve_video_path(workspace_root: Path, zone_payload: dict) -> Optional[Path]:
    """
    Extract the `video_path` saved by the annotator and resolve it to an absolute path.
    """
    # Both schemas store this under annotations.meta.video_path (currently).
    meta = (zone_payload.get("annotations") or {}).get("meta") or {}
    vp = (meta.get("video_path") or "").strip()
    if not vp:
        return None
    p = Path(vp)
    if p.is_absolute():
        return p
    # Often relative like "data/behavior_videos/...". Resolve relative to workspace root.
    return (workspace_root / p).resolve()


def index_arena_zone_jsons(
    repos: RepositoryFactory,
    *,
    workspace_root: Path,
    session_index_csv: Path,
    ezm_dir: Path,
    nor_nof_dir: Path,
) -> ArenaZonesIndexStats:
    """
    Index arena annotation outputs into MUS1 DB as external artifacts.

    Links are determined by joining each zone JSON's embedded `video_path` to the
    `video_path` column in session_index_filtered.csv (compiled contract).
    """
    by_video_path = _read_session_index_by_video_path(session_index_csv)

    total = 0
    added = 0
    skipped = 0
    qc_added = 0
    linked = 0
    unlinked = 0

    def _qc(code: str, details: dict, subject_id: Optional[str] = None, experiment_id: Optional[str] = None):
        nonlocal qc_added
        repos.qc_events.add(scope="annotation", code=code, details=details, subject_id=subject_id, experiment_id=experiment_id)
        qc_added += 1

    def _index_dir(kind: str, d: Path):
        nonlocal total, added, skipped, linked, unlinked
        if not d.exists():
            _qc("MISSING_INPUT", {"kind": kind, "path": str(d)})
            return

        for p in sorted(d.glob("*.json")):
            total += 1
            try:
                payload = json.loads(p.read_text())
            except Exception as e:
                _qc("ANNOTATION_JSON_READ_ERROR", {"path": str(p), "error": str(e)})
                continue

            video_abs = _resolve_video_path(workspace_root, payload)
            if video_abs is None:
                _qc("ANNOTATION_MISSING_VIDEO_PATH", {"path": str(p)})
                # Still index as unlinked artifact (provenance is the JSON itself)
                exp_id = None
                subj_id = None
                unlinked += 1
                meta = {"workspace_root": str(workspace_root), "zone_json": str(p)}
            else:
                row = by_video_path.get(str(video_abs)) or by_video_path.get(str(video_abs.resolve()))
                if row:
                    exp_id = (row.get("session_id") or "").strip() or None
                    subj_id = (row.get("subject_id") or "").strip() or None
                    linked += 1
                    meta = {
                        "workspace_root": str(workspace_root),
                        "session_id": exp_id,
                        "task": (row.get("task") or "").strip(),
                        "subject_id": subj_id,
                        "recording_date": (row.get("recording_date") or "").strip(),
                        "video_path": str(video_abs),
                    }
                else:
                    exp_id = None
                    subj_id = None
                    unlinked += 1
                    meta = {
                        "workspace_root": str(workspace_root),
                        "video_path": str(video_abs),
                    }
                    _qc("ANNOTATION_UNLINKED", {"zone_json": str(p), "video_path": str(video_abs), "kind": kind})

            if repos.external_artifacts.exists(kind=kind, path=str(p), subject_id=subj_id, experiment_id=exp_id):
                skipped += 1
                continue

            repos.external_artifacts.add(
                kind=kind,
                path=str(p),
                subject_id=subj_id,
                experiment_id=exp_id,
                meta=meta,
            )
            added += 1

    _index_dir("ezm_zone_json_v2", ezm_dir)
    _index_dir("nor_nof_objects_json_v1", nor_nof_dir)

    return ArenaZonesIndexStats(
        total_jsons=total,
        artifacts_added=added,
        artifacts_skipped_existing=skipped,
        qc_events_added=qc_added,
        linked_to_experiment=linked,
        unlinked=unlinked,
    )

