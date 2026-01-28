"""
Arena annotation zone JSON indexing.

Purpose:
- Keep zone JSONs written into the MoSeq2 workspace (for arena inference workflows).
- Make them DB-queryable by indexing them into MUS1 as external artifacts linked to
  experiments/subjects via the compiled session index contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from ..repository import RepositoryFactory


@dataclass(frozen=True)
class ArenaZonesIndexStats:
    total_jsons: int
    artifacts_added: int
    artifacts_skipped_existing: int
    qc_events_added: int
    linked_to_experiment: int
    unlinked: int


def _path_aliases(p: Path) -> list[str]:
    """
    Return a small set of canonical/aliased path strings for matching.

    This workspace commonly references the same files via both:
    - /center1/... (canonical)
    - /import/c1/... (alternate mount path)
    """
    out: list[str] = []
    s = str(p)
    out.append(s)

    try:
        out.append(str(p.resolve()))
    except Exception:
        pass

    if s.startswith("/import/c1/"):
        out.append("/center1/" + s[len("/import/c1/"):])
    elif s.startswith("/center1/"):
        out.append("/import/c1/" + s[len("/center1/"):])

    # unique, preserve order
    uniq: list[str] = []
    seen: set[str] = set()
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _read_session_index_by_video_path(session_index_csv: Path) -> Dict[str, Dict[str, str]]:
    """
    Build a lookup of absolute video path -> row dict from session_index_filtered.csv.
    Uses the 'video_path' column.
    """
    by_path: Dict[str, Dict[str, str]] = {}
    df = pd.read_csv(session_index_csv)
    if "video_path" not in df.columns:
        return {}

    # Keep only rows with a non-empty video_path
    vps = df["video_path"].fillna("").astype(str).str.strip()
    df = df.loc[vps.ne("")].copy()

    for _, r in df.iterrows():
        vp = str(r.get("video_path", "")).strip()
        if not vp:
            continue
        row = {k: ("" if pd.isna(v) else str(v)) for k, v in r.to_dict().items()}
        for alias in _path_aliases(Path(vp)):
            by_path[alias] = row
    return by_path


def _resolve_video_path(workspace_root: Path, zone_payload: dict) -> Optional[Path]:
    """
    Extract the `video_path` saved by the annotator and resolve it to an absolute path.
    """
    ann = zone_payload.get("annotations") or {}
    # Current schemas store this under annotations.calibration.video_path.
    calib = ann.get("calibration") or {}
    meta = ann.get("meta") or {}
    vp = (calib.get("video_path") or meta.get("video_path") or "").strip()
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
                row = None
                for alias in _path_aliases(video_abs):
                    row = by_video_path.get(alias)
                    if row:
                        break
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

