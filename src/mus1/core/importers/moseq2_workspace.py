"""
MoSeq2 workspace importer.

Reads session_index_filtered.csv and imports subjects, experiments, external artifacts,
and QC events into the MUS1 repository.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import pandas as pd

from ..repository import RepositoryFactory
from ..metadata import Sex, ProcessingStage, SubjectDesignation
from ..schema import SubjectModel, ExperimentModel, ExternalArtifactModel, QCEventModel


@dataclass
class ImportStats:
    """Statistics from an import operation."""
    rows_total: int = 0
    subjects_upserted: int = 0
    experiments_upserted: int = 0
    videos_upserted: int = 0
    artifacts_added: int = 0
    qc_events_added: int = 0


def _as_path(value: Any) -> Optional[Path]:
    """Convert a value to a Path if it's a non-empty string, otherwise None."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return Path(value)


def _resolve_path(path: Path, workspace_root: Path) -> Path:
    """Make a path absolute. Relative paths are resolved against workspace_root without stat calls."""
    if path.is_absolute():
        return path
    return workspace_root / path


def _parse_date(date_str: Any) -> Optional[datetime]:
    """Parse a date string to datetime."""
    if not date_str or pd.isna(date_str):
        return None
    if isinstance(date_str, datetime):
        return date_str
    if isinstance(date_str, str):
        date_str = date_str.strip()
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return None
    return None


def _parse_sex(sex_str: Any) -> Sex:
    """Parse sex string to Sex enum."""
    if not sex_str or pd.isna(sex_str):
        return Sex.UNKNOWN
    sex_str = str(sex_str).strip().upper()
    if sex_str == "M":
        return Sex.MALE
    elif sex_str == "F":
        return Sex.FEMALE
    else:
        return Sex.UNKNOWN


def import_session_index(
    repos: RepositoryFactory,
    *,
    workspace_root: Path,
    session_index_csv: Path,
    check_paths_exist: bool = True,
) -> ImportStats:
    """
    Import MoSeq2 workspace session index CSV into MUS1 repository.

    Args:
        repos: Repository factory for database operations
        workspace_root: Root directory of the MoSeq2 workspace
        session_index_csv: Path to session_index_filtered.csv
        check_paths_exist: If True, create QC events for missing file paths

    Returns:
        ImportStats with counts of imported entities
    """
    stats = ImportStats()

    # Read CSV
    df = pd.read_csv(session_index_csv)
    stats.rows_total = len(df)

    workspace_root = Path(workspace_root)
    # Performance note: use a single SQLAlchemy session and commit once.
    # This avoids thousands of per-row commits during large workspace imports.
    now = datetime.utcnow()
    session = repos.db.get_session()
    try:
        seen_subjects: set[str] = set()
        seen_experiments: set[str] = set()
        for _, row in df.iterrows():
            subject_id = str(row.get("subject_id", "")).strip()
            if not subject_id:
                continue

            sex = _parse_sex(row.get("sex"))
            genotype = str(row.get("genotype", "")).strip() or None
            birthdate = _parse_date(row.get("birthdate"))
            treatment = str(row.get("treatment", "")).strip() or None

            if subject_id not in seen_subjects:
                seen_subjects.add(subject_id)
                session.merge(
                    SubjectModel(
                        id=subject_id,
                        colony_id=None,
                        sex=sex,
                        designation=SubjectDesignation.EXPERIMENTAL,
                        birth_date=birthdate,
                        death_date=None,
                        individual_genotype=genotype,
                        individual_treatment=treatment,
                        notes="",
                        date_added=now,
                    )
                )
                stats.subjects_upserted += 1

            session_id = str(row.get("session_id", "")).strip()
            if not session_id:
                session_id = f"{subject_id}_{row.get('recording_date', 'unknown')}"

            task = str(row.get("task", "")).strip() or "unknown"
            recording_date = _parse_date(row.get("recording_date")) or datetime.utcnow()

            if session_id not in seen_experiments:
                seen_experiments.add(session_id)
                session.merge(
                    ExperimentModel(
                        id=session_id,
                        subject_id=subject_id,
                        experiment_type=task,
                        date_recorded=recording_date,
                        processing_stage=ProcessingStage.RECORDED,
                        experiment_subtype=None,
                        notes="",
                        date_added=now,
                    )
                )
                stats.experiments_upserted += 1

            # Record video path as an external artifact (path-only).
            video_path = _as_path(row.get("video_path"))
            if video_path:
                video_path = _resolve_path(video_path, workspace_root)
                session.add(
                    ExternalArtifactModel(
                        kind="video_path",
                        experiment_id=session_id,
                        subject_id=subject_id,
                        assay_session_id=None,
                        path=str(video_path),
                        content_sha256=None,
                        payload_json=None,
                        meta_json=json.dumps({"source": "session_index_filtered.csv"}),
                        created_at=now,
                    )
                )
                stats.artifacts_added += 1
                if check_paths_exist and not video_path.exists():
                    session.add(
                        QCEventModel(
                            scope="artifact",
                            code="MISSING_PATH",
                            subject_id=subject_id,
                            experiment_id=session_id,
                            assay_session_id=None,
                            details_json=json.dumps({"kind": "video_path", "path": str(video_path)}),
                            created_at=now,
                        )
                    )
                    stats.qc_events_added += 1

            artifact_cols = [
                "dlc_csv_path",
                "moseq2_results_h5_path",
                "moseq2_results_yaml_path",
                "moseq2_metadata_path",
                "moseq2_identifier_path",
                "syllable_stats_path",
                "syllable_h5_path",
                "kpms_syllable_stats_path",
            ]

            for col in artifact_cols:
                p = _as_path(row.get(col))
                if not p:
                    continue
                p = _resolve_path(p, workspace_root)
                session.add(
                    ExternalArtifactModel(
                        kind=col,
                        experiment_id=session_id,
                        subject_id=subject_id,
                        assay_session_id=None,
                        path=str(p),
                        content_sha256=None,
                        payload_json=None,
                        meta_json=json.dumps({"source": "session_index_filtered.csv"}),
                        created_at=now,
                    )
                )
                stats.artifacts_added += 1
                if check_paths_exist and not p.exists():
                    session.add(
                        QCEventModel(
                            scope="artifact",
                            code="MISSING_PATH",
                            subject_id=subject_id,
                            experiment_id=session_id,
                            assay_session_id=None,
                            details_json=json.dumps({"kind": col, "path": str(p)}),
                            created_at=now,
                        )
                    )
                    stats.qc_events_added += 1

            identifiers: Dict[str, Any] = {}
            for k in (
                "syllable_uuid",
                "kpms_recording_id",
                "moseq2_session_name",
                "arena_bucket",
                "moseq2_source_filename",
            ):
                v = str(row.get(k, "")).strip()
                if v:
                    identifiers[k] = v
            if identifiers:
                session.add(
                    ExternalArtifactModel(
                        kind="identifiers",
                        experiment_id=session_id,
                        subject_id=subject_id,
                        assay_session_id=None,
                        path="",
                        content_sha256=None,
                        payload_json=json.dumps(identifiers),
                        meta_json=json.dumps({"source": "session_index_filtered.csv"}),
                        created_at=now,
                    )
                )
                stats.artifacts_added += 1

        session.commit()
    finally:
        session.close()

    return stats
