"""Importer for rotarod assay CSV data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..metadata import AssaySession, AssayMeasurement, Subject, Sex, SubjectDesignation
from ..repository import RepositoryFactory


@dataclass(frozen=True)
class RotarodImportStats:
    """Statistics from rotarod import."""
    rows_total: int
    assay_sessions_created: int
    assay_measurements_created: int
    subjects_created: int
    subjects_skipped: int
    errors: int


def _parse_date(value: str) -> Optional[datetime]:
    """Parse date string to datetime."""
    if not value or not value.strip():
        return None
    try:
        # Try YYYY-MM-DD format
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _normalize_tag_number(tag: str) -> str:
    """Normalize tag number (remove leading zeros)."""
    try:
        return str(int(tag.strip()))
    except (ValueError, AttributeError):
        return str(tag).strip()


def _ensure_subject_exists(
    repos: RepositoryFactory,
    tag_number: str,
    sex: Optional[str] = None,
    genotype: Optional[str] = None,
) -> Tuple[Optional[Subject], bool]:
    """
    Ensure subject exists, creating if necessary.
    
    Returns:
        Tuple of (subject, was_created) where was_created is True if subject was just created
    """
    tag_normalized = _normalize_tag_number(tag_number)
    
    # Try to find existing subject
    subject = repos.subjects.find_by_id(tag_normalized)
    if subject:
        return subject, False
    
    # Create new subject if not found
    # Map sex string to enum
    sex_enum = Sex.UNKNOWN
    if sex:
        sex_upper = sex.strip().upper()
        if sex_upper == "M":
            sex_enum = Sex.MALE
        elif sex_upper == "F":
            sex_enum = Sex.FEMALE
    
    subject = Subject(
        id=tag_normalized,
        colony_id=None,
        sex=sex_enum,
        designation=SubjectDesignation.EXPERIMENTAL,
        individual_genotype=genotype.strip() if genotype else None,
    )
    
    try:
        created_subject = repos.subjects.save(subject)
        return created_subject, True
    except Exception:
        # Subject creation failed (e.g., constraint violation)
        return None, False


def import_rotarod_csv(
    repos: RepositoryFactory,
    csv_path: Path,
    assay_type: str = "rotarod",
) -> RotarodImportStats:
    """
    Import rotarod assay data from CSV.
    
    Creates assay_sessions per (tag_number, session_id) and assay_measurements
    for each row with metrics like time_sec, speed_rpm, attempt.
    
    Args:
        repos: Repository factory for database operations
        csv_path: Path to rotarod CSV file
        assay_type: Type identifier for assay sessions (default: "rotarod")
    
    Returns:
        Import statistics
    """
    rows_total = 0
    assay_sessions_created = 0
    assay_measurements_created = 0
    subjects_created = 0
    subjects_skipped = 0
    errors = 0
    
    # Track created sessions by (tag_number, session_id) to avoid duplicates
    session_cache: Dict[Tuple[str, str], int] = {}
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            rows_total += 1
            
            try:
                tag_number = row.get("tag_number", "").strip()
                session_id = row.get("session_id", "").strip()
                
                if not tag_number or not session_id:
                    errors += 1
                    continue
                
                # Ensure subject exists
                sex = row.get("sex_final", "").strip()
                genotype = row.get("genotype_final", "").strip()
                subject, was_created = _ensure_subject_exists(repos, tag_number, sex, genotype)
                
                if not subject:
                    subjects_skipped += 1
                    errors += 1
                    continue
                
                if was_created:
                    subjects_created += 1
                
                # Check if we already created this session
                # Use normalized tag_number for consistency
                tag_normalized = _normalize_tag_number(tag_number)
                session_key = (tag_normalized, session_id)
                assay_session_id = session_cache.get(session_key)
                
                if assay_session_id is None:
                    # Create new assay session
                    test_date_str = row.get("test_date", "").strip()
                    occurred_at = _parse_date(test_date_str)
                    
                    # Collect metadata for session
                    session_meta: Dict[str, Any] = {
                        "source_file": row.get("source_file", "").strip(),
                        "session_index": row.get("session_index", "").strip(),
                        "genotype_final": genotype,
                        "sex_final": sex,
                        "birthdate_final": row.get("birthdate_final", "").strip(),
                        "treatment_roster": row.get("treatment_roster", "").strip(),
                        "age_days": row.get("age_days", "").strip(),
                    }
                    
                    assay_session = AssaySession(
                        assay_type=assay_type,
                        subject_id=subject.id,
                        occurred_at=occurred_at,
                        experiment_id=None,  # No experiment linkage for rotarod
                        source_path=csv_path,
                        meta=session_meta,
                    )
                    
                    assay_session_id = repos.assay_sessions.create(assay_session)
                    session_cache[session_key] = assay_session_id
                    assay_sessions_created += 1
                
                # Create measurements for this row
                # Measurement 1: time_sec
                time_sec_str = row.get("time_sec", "").strip()
                if time_sec_str:
                    try:
                        time_value = float(time_sec_str)
                        exclude_reason = row.get("exclude_reason", "").strip()
                        qc_flags = [exclude_reason] if exclude_reason else []
                        
                        measurement = AssayMeasurement(
                            assay_session_id=assay_session_id,
                            metric="time_sec",
                            value=time_value,
                            units="seconds",
                            qc_flags=qc_flags,
                            details={
                                "attempt": row.get("attempt", "").strip(),
                                "speed_rpm": row.get("speed_rpm", "").strip(),
                            },
                        )
                        repos.assay_measurements.add(measurement)
                        assay_measurements_created += 1
                    except (ValueError, TypeError):
                        pass  # Skip invalid time_sec
                
                # Measurement 2: speed_rpm
                speed_rpm_str = row.get("speed_rpm", "").strip()
                if speed_rpm_str:
                    try:
                        speed_value = float(speed_rpm_str)
                        exclude_reason = row.get("exclude_reason", "").strip()
                        qc_flags = [exclude_reason] if exclude_reason else []
                        
                        measurement = AssayMeasurement(
                            assay_session_id=assay_session_id,
                            metric="speed_rpm",
                            value=speed_value,
                            units="rpm",
                            qc_flags=qc_flags,
                            details={
                                "attempt": row.get("attempt", "").strip(),
                                "time_sec": row.get("time_sec", "").strip(),
                            },
                        )
                        repos.assay_measurements.add(measurement)
                        assay_measurements_created += 1
                    except (ValueError, TypeError):
                        pass  # Skip invalid speed_rpm
                
                # Measurement 3: attempt (as a metric)
                attempt_str = row.get("attempt", "").strip()
                if attempt_str:
                    try:
                        attempt_value = float(attempt_str)
                        exclude_reason = row.get("exclude_reason", "").strip()
                        qc_flags = [exclude_reason] if exclude_reason else []
                        
                        measurement = AssayMeasurement(
                            assay_session_id=assay_session_id,
                            metric="attempt",
                            value=attempt_value,
                            units=None,
                            qc_flags=qc_flags,
                            details={
                                "time_sec": row.get("time_sec", "").strip(),
                                "speed_rpm": row.get("speed_rpm", "").strip(),
                            },
                        )
                        repos.assay_measurements.add(measurement)
                        assay_measurements_created += 1
                    except (ValueError, TypeError):
                        pass  # Skip invalid attempt
                
            except Exception as e:
                errors += 1
                # Continue processing other rows
                continue
    
    return RotarodImportStats(
        rows_total=rows_total,
        assay_sessions_created=assay_sessions_created,
        assay_measurements_created=assay_measurements_created,
        subjects_created=subjects_created,
        subjects_skipped=subjects_skipped,
        errors=errors,
    )
