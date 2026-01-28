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
from ..metadata import Subject, Experiment, VideoFile, Sex, ProcessingStage, SubjectDesignation


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
    """Resolve a path to absolute, preferring absolute paths when possible."""
    if path.is_absolute():
        return path
    # Try relative to workspace_root
    resolved = workspace_root / path
    if resolved.exists():
        return resolved.resolve()
    # Return as-is if it doesn't exist (will be caught by QC check)
    return path


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

    workspace_root = Path(workspace_root).resolve()

    for _, row in df.iterrows():
        # Extract subject information
        subject_id = str(row.get("subject_id", "")).strip()
        if not subject_id:
            continue  # Skip rows without subject_id

        # Parse subject fields
        sex = _parse_sex(row.get("sex"))
        genotype = str(row.get("genotype", "")).strip() or None
        birthdate = _parse_date(row.get("birthdate"))

        # Create/upsert subject
        subject = Subject(
            id=subject_id,
            colony_id=None,  # No colony association from CSV
            sex=sex,
            designation=SubjectDesignation.EXPERIMENTAL,
            birth_date=birthdate,
            individual_genotype=genotype,
            individual_treatment=str(row.get("treatment", "")).strip() or None,
        )
        repos.subjects.save(subject)
        stats.subjects_upserted += 1

        # Extract experiment information
        session_id = str(row.get("session_id", "")).strip()
        if not session_id:
            session_id = f"{subject_id}_{row.get('recording_date', 'unknown')}"

        task = str(row.get("task", "")).strip() or "unknown"
        recording_date = _parse_date(row.get("recording_date"))
        if not recording_date:
            recording_date = datetime.now()  # Fallback

        # Create/upsert experiment
        experiment = Experiment(
            id=session_id,
            subject_id=subject_id,
            experiment_type=task,
            date_recorded=recording_date,
            processing_stage=ProcessingStage.RECORDED,  # Assume recorded since we have data
        )
        repos.experiments.save(experiment)
        stats.experiments_upserted += 1

        # Handle video path
        video_path = _as_path(row.get("video_path"))
        if video_path:
            video_path = _resolve_path(video_path, workspace_root)
            # Save video (path-only, no hash)
            repos.videos.save(VideoFile(path=video_path, hash=None))
            stats.videos_upserted += 1
            # Link video to experiment
            repos.experiments.add_video_to_experiment_by_path(experiment.id, video_path)

            # Store as external artifact
            repos.external_artifacts.add(
                kind="video_path",
                experiment_id=experiment.id,
                subject_id=subject_id,
                path=str(video_path),
                meta={"source": "session_index_filtered.csv"},
            )
            stats.artifacts_added += 1

            # Check if video exists
            if check_paths_exist and not video_path.exists():
                repos.qc_events.add(
                    scope="artifact",
                    code="MISSING_PATH",
                    subject_id=subject_id,
                    experiment_id=experiment.id,
                    details={"kind": "video_path", "path": str(video_path)},
                )
                stats.qc_events_added += 1

        # Artifact columns to index directly
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

            # Store as external artifact
            repos.external_artifacts.add(
                kind=col,
                experiment_id=experiment.id,
                subject_id=subject_id,
                path=str(p),
                meta={"source": "session_index_filtered.csv"},
            )
            stats.artifacts_added += 1

            # Check if path exists
            if check_paths_exist and not p.exists():
                repos.qc_events.add(
                    scope="artifact",
                    code="MISSING_PATH",
                    subject_id=subject_id,
                    experiment_id=experiment.id,
                    details={"kind": col, "path": str(p)},
                )
                stats.qc_events_added += 1

        # Store scalar identifiers as meta on an artifact record
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
            repos.external_artifacts.add(
                kind="identifiers",
                experiment_id=experiment.id,
                subject_id=subject_id,
                path="",  # No file path for identifiers
                payload_json=json.dumps(identifiers),  # Store as JSON string
                meta={"source": "session_index_filtered.csv"},
            )
            stats.artifacts_added += 1

    return stats
