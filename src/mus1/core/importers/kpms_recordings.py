"""
Importer for KPMS recordings metadata CSV files.

Indexes recordings metadata from KPMS rerun CSV files and stores them as
external artifacts linked to experiments/subjects when possible.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ..repository import RepositoryFactory
from ..schema import Database


def resolve_absolute_path(workspace_root: Path, path_str: str) -> Optional[Path]:
    """Resolve a relative path to absolute using workspace root."""
    if not path_str or not path_str.strip():
        return None
    
    path = Path(path_str.strip())
    
    # If already absolute, return as-is
    if path.is_absolute():
        return path
    
    # Otherwise resolve relative to workspace root
    resolved = workspace_root / path
    return resolved if resolved.exists() else None


def parse_recording_date(recording_id: str) -> Optional[datetime]:
    """Extract date from recording_id if possible.
    
    Examples:
    - EZM__159_20202312__12.20.2023_EZM_159 -> 2023-12-20
    - NOF__02.15.2024_159F_FAM -> 2024-02-15
    """
    import re
    
    # Try MM.DD.YYYY pattern
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', recording_id)
    if match:
        month, day, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass
    
    # Try YYYY-MM-DD pattern
    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', recording_id)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass
    
    return None


def find_experiment_by_heuristics(
    repos: RepositoryFactory,
    recording_id: str,
    subject_tag: Optional[str],
    condition: str,
    recording_date: Optional[datetime],
) -> Optional[str]:
    """Try to find an experiment ID using heuristics.
    
    Heuristics:
    1. Try recording_id as experiment_id directly
    2. If subject_tag exists, find experiments for that subject matching condition and date
    3. Return None if no match found
    """
    # Try recording_id as experiment ID directly
    exp = repos.experiments.find_by_id(recording_id)
    if exp:
        return exp.id
    
    # If we have subject_tag, try to find matching experiments
    if subject_tag:
        subject_experiments = repos.experiments.find_by_subject(subject_tag)
        
        # Filter by condition (experiment_type)
        matching = [e for e in subject_experiments if e.experiment_type == condition]
        
        # If we have a date, try to match by date (within 1 day tolerance)
        if recording_date and matching:
            best_match = None
            min_diff = None
            for exp in matching:
                if exp.date_recorded:
                    diff = abs((exp.date_recorded - recording_date).days)
                    if min_diff is None or diff < min_diff:
                        min_diff = diff
                        best_match = exp
            
            # Accept match if within 1 day
            if best_match and min_diff is not None and min_diff <= 1:
                return best_match.id
        
        # Otherwise return first matching experiment if any
        if matching:
            return matching[0].id
    
    return None


def find_subject_by_tag(repos: RepositoryFactory, tag: Optional[str]) -> Optional[str]:
    """Find subject ID by tag."""
    if not tag:
        return None
    
    # Try tag as subject ID directly
    subject = repos.subjects.find_by_id(tag)
    if subject:
        return subject.id
    
    return None


def import_kpms_recordings_csv(
    repos: RepositoryFactory,
    csv_path: Path,
    workspace_root: Path,
    source_name: str,
) -> Dict[str, int]:
    """Import recordings from a KPMS recordings CSV file.
    
    Args:
        repos: Repository factory
        csv_path: Path to the CSV file
        workspace_root: Root of the workspace (for resolving relative paths)
        source_name: Name of the source (e.g., "20260122_trim30s_ezm")
    
    Returns:
        Dictionary with counts: artifacts_added, linked_to_experiment, linked_to_subject, unlinked
    """
    stats = {
        "artifacts_added": 0,
        "linked_to_experiment": 0,
        "linked_to_subject": 0,
        "unlinked": 0,
    }
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            recording_id = row.get('recording_id', '').strip()
            if not recording_id:
                continue
            
            # Extract metadata
            condition = row.get('condition', '').strip()
            tag = row.get('tag', '').strip()  # Subject tag
            video_path = row.get('video_path', '').strip()
            source_video_path = row.get('source_video_path', '').strip()
            dlc_csv = row.get('dlc_csv', '').strip()
            trimmed_dlc_csv = row.get('trimmed_dlc_csv', '').strip()
            
            # Parse recording date
            recording_date = parse_recording_date(recording_id)
            
            # Try to find linked entities
            experiment_id = find_experiment_by_heuristics(
                repos, recording_id, tag, condition, recording_date
            )
            subject_id = find_subject_by_tag(repos, tag)
            
            # Track linkage status
            linked_to_exp = experiment_id is not None
            linked_to_subj = subject_id is not None
            
            if linked_to_exp:
                stats["linked_to_experiment"] += 1
            if linked_to_subj:
                stats["linked_to_subject"] += 1
            if not linked_to_exp and not linked_to_subj:
                stats["unlinked"] += 1
            
            # Store recording metadata as artifact
            recording_meta = {
                "source": source_name,
                "recording_id": recording_id,
                "condition": condition,
                "tag": tag,
                "recording_date": recording_date.isoformat() if recording_date else None,
                "genotype": row.get('genotype', '').strip(),
                "sex": row.get('sex', '').strip(),
                "treatment": row.get('treatment', '').strip(),
                "birthdate": row.get('birthdate', '').strip(),
            }
            
            # Store recording metadata artifact
            repos.external_artifacts.add(
                kind="kpms_recording_metadata",
                path=str(csv_path),
                subject_id=subject_id,
                experiment_id=experiment_id,
                payload_json=json.dumps(recording_meta),
                meta={
                    "source_file": str(csv_path),
                    "source_name": source_name,
                    "row_index": reader.line_num - 1,  # Approximate
                },
            )
            stats["artifacts_added"] += 1
            
            # Store video paths as artifacts
            paths_to_store = [
                ("kpms_video_path", video_path),
                ("kpms_source_video_path", source_video_path),
                ("kpms_dlc_csv", dlc_csv),
                ("kpms_trimmed_dlc_csv", trimmed_dlc_csv),
            ]
            
            for kind, path_str in paths_to_store:
                if not path_str:
                    continue
                
                abs_path = resolve_absolute_path(workspace_root, path_str)
                if abs_path:
                    repos.external_artifacts.add(
                        kind=kind,
                        path=str(abs_path),
                        subject_id=subject_id,
                        experiment_id=experiment_id,
                        meta={
                            "source": source_name,
                            "recording_id": recording_id,
                            "original_path": path_str,
                        },
                    )
                    stats["artifacts_added"] += 1
    
    return stats


def import_kpms_recordings(
    db_path: Path,
    csv_paths: List[Path],
    workspace_root: Path,
) -> Dict[str, any]:
    """Import recordings from multiple CSV files.
    
    Args:
        db_path: Path to the MUS1 database
        csv_paths: List of CSV file paths to import
        workspace_root: Root of the workspace
    
    Returns:
        Dictionary with import statistics
    """
    db = Database(str(db_path))
    db.create_tables()
    repos = RepositoryFactory(db)
    
    all_stats = {
        "total_artifacts": 0,
        "total_linked_to_experiment": 0,
        "total_linked_to_subject": 0,
        "total_unlinked": 0,
        "sources": {},
    }
    
    for csv_path in csv_paths:
        # Extract source name from path
        # e.g., .../20260122_trim30s_ezm/metadata/recordings.csv -> 20260122_trim30s_ezm
        source_name = csv_path.parent.parent.name if csv_path.name == "recordings.csv" else csv_path.stem
        
        try:
            stats = import_kpms_recordings_csv(repos, csv_path, workspace_root, source_name)
            all_stats["total_artifacts"] += stats["artifacts_added"]
            all_stats["total_linked_to_experiment"] += stats["linked_to_experiment"]
            all_stats["total_linked_to_subject"] += stats["linked_to_subject"]
            all_stats["total_unlinked"] += stats["unlinked"]
            all_stats["sources"][source_name] = stats
        except Exception as e:
            all_stats["sources"][source_name] = {"error": str(e)}
    
    return all_stats
