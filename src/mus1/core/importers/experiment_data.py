"""
Experiment data importer.

Scans data/experiment_data/{OF,EZM,NOR,NOF,RR} and imports subjects, experiments,
assay_sessions (for RR), and video_path artifacts into the MUS1 repository.
experiment_data is the canonical source; no session_index or rotarod CSV.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
from dataclasses import dataclass
from datetime import datetime
import json

from ..repository import RepositoryFactory
from ..metadata import Sex, ProcessingStage, SubjectDesignation
from ..schema import (
    SubjectModel,
    ExperimentModel,
    ExternalArtifactModel,
    AssaySessionModel,
    AssayMeasurementModel,
)


@dataclass
class ExperimentDataImportStats:
    """Statistics from experiment_data import."""
    jsons_scanned: int = 0
    subjects_upserted: int = 0
    experiments_upserted: int = 0
    artifacts_added: int = 0
    assay_sessions_created: int = 0
    assay_measurements_created: int = 0
    skipped: int = 0


def _parse_date(date_str: Any) -> datetime | None:
    """Parse date string to datetime."""
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str
    s = str(date_str).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _parse_sex(sex_str: Any) -> Sex:
    """Parse sex string to Sex enum."""
    if not sex_str:
        return Sex.UNKNOWN
    s = str(sex_str).strip().upper()
    if s == "M":
        return Sex.MALE
    if s == "F":
        return Sex.FEMALE
    return Sex.UNKNOWN


# Map experiment_type from JSON to DB (Rotarod -> RR for TASK_ORDER)
EXPERIMENT_TYPE_MAP = {"Rotarod": "RR", "ROTAROD": "RR"}


def import_experiment_data(
    repos: RepositoryFactory,
    *,
    experiment_data_root: Path,
    tasks: tuple[str, ...] = ("OF", "EZM", "NOR", "NOF", "RR"),
) -> ExperimentDataImportStats:
    """
    Import experiment_data JSONs into MUS1 repository.

    Scans experiment_data_root/{task}/ for folders, reads first JSON per folder,
    upserts subjects and experiments, adds video_path artifact.
    For RR: also creates assay_sessions and assay_measurements from attempts.
    """
    stats = ExperimentDataImportStats()
    root = Path(experiment_data_root)
    if not root.is_dir():
        return stats

    now = datetime.utcnow()
    session = repos.db.get_session()
    seen_subjects: set[str] = set()
    seen_experiments: set[str] = set()
    seen_rr_sessions: set[tuple[str, str]] = set()  # (subject_id, date)

    try:
        for task in tasks:
            task_dir = root / task
            if not task_dir.is_dir():
                continue
            for exp_dir in task_dir.iterdir():
                if not exp_dir.is_dir():
                    continue
                jsons = list(exp_dir.glob("*.json"))
                if not jsons:
                    continue
                stats.jsons_scanned += 1
                try:
                    data = json.loads(jsons[0].read_text())
                except Exception:
                    stats.skipped += 1
                    continue

                eid = data.get("experiment_id") or exp_dir.name
                raw_etype = data.get("experiment_type") or task
                etype = EXPERIMENT_TYPE_MAP.get(raw_etype, raw_etype)
                if etype == "Rotarod":
                    etype = "RR"
                md = data.get("metadata") or {}
                subject_id = str(md.get("subject_id", "")).strip()
                if not subject_id:
                    stats.skipped += 1
                    continue

                date_recorded = _parse_date(md.get("date_recorded"))
                if not date_recorded:
                    stats.skipped += 1
                    continue

                sex = _parse_sex(md.get("sex"))
                genotype = str(md.get("genotype", "")).strip() or None
                treatment = str(md.get("treatment", "")).strip() or None
                birthdate = _parse_date(md.get("birthdate"))

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

                if eid not in seen_experiments:
                    seen_experiments.add(eid)
                    session.merge(
                        ExperimentModel(
                            id=eid,
                            subject_id=subject_id,
                            experiment_type=etype,
                            date_recorded=date_recorded,
                            processing_stage=ProcessingStage.RECORDED,
                            experiment_subtype=None,
                            notes="",
                            date_added=now,
                        )
                    )
                    stats.experiments_upserted += 1

                vid = data.get("video") or {}
                video_path = vid.get("path")
                if video_path:
                    session.add(
                        ExternalArtifactModel(
                            kind="video_path",
                            experiment_id=eid,
                            subject_id=subject_id,
                            assay_session_id=None,
                            path=str(video_path),
                            content_sha256=None,
                            payload_json=None,
                            meta_json=json.dumps({"source": "experiment_data"}),
                            created_at=now,
                        )
                    )
                    stats.artifacts_added += 1

                # RR: create assay_sessions and assay_measurements for Subject Explorer RR count
                if etype == "RR":
                    rr_key = (subject_id, str(date_recorded.date()) if date_recorded else "")
                    if rr_key not in seen_rr_sessions:
                        seen_rr_sessions.add(rr_key)
                        existing_session = session.query(AssaySessionModel).filter_by(
                            experiment_id=eid, assay_type="rotarod",
                        ).first()
                        if existing_session is not None:
                            continue
                        exp_level = md.get("experiment_level") or {}
                        attempts = exp_level.get("attempts") or {}
                        assay_row = AssaySessionModel(
                            assay_type="rotarod",
                            subject_id=subject_id,
                            occurred_at=date_recorded,
                            experiment_id=eid,
                            source_path=str(jsons[0]),
                            meta_json=json.dumps(exp_level),
                            created_at=now,
                        )
                        session.add(assay_row)
                        session.flush()
                        stats.assay_sessions_created += 1
                        for _attempt_name, attempt_data in attempts.items():
                            if isinstance(attempt_data, dict):
                                t_sec = attempt_data.get("time_seconds")
                                speed = attempt_data.get("speed")
                                if t_sec is not None:
                                    session.add(
                                        AssayMeasurementModel(
                                            assay_session_id=assay_row.id,
                                            metric="time_sec",
                                            value=float(t_sec),
                                            units="seconds",
                                            qc_flags_json="[]",
                                            details_json=json.dumps(attempt_data),
                                            created_at=now,
                                        )
                                    )
                                    stats.assay_measurements_created += 1
                                if speed is not None:
                                    session.add(
                                        AssayMeasurementModel(
                                            assay_session_id=assay_row.id,
                                            metric="speed_rpm",
                                            value=float(speed),
                                            units="rpm",
                                            qc_flags_json="[]",
                                            details_json=json.dumps(attempt_data),
                                            created_at=now,
                                        )
                                    )
                                    stats.assay_measurements_created += 1

        session.commit()
    finally:
        session.close()

    return stats
