"""
Migration script to convert existing MUS1 JSON project data to SQLite.

This script reads the existing project_state.json file and migrates all
subjects, experiments, and metadata to the new SQLite-based system.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import hashlib
import logging

from .metadata import (
    Subject, Experiment, VideoFile, Sex, ProcessingStage,
    SubjectDTO, ExperimentDTO
)
from .project_manager_clean import ProjectManagerClean
from .schema import Database

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MUS1Migrator:
    """Handles migration from JSON-based MUS1 projects to SQLite."""

    def __init__(self, source_project_path: Path, target_project_path: Path):
        self.source_project_path = source_project_path
        self.target_project_path = target_project_path
        self.source_state_file = source_project_path / "project_state.json"

        # Initialize target project
        self.pm = ProjectManagerClean(target_project_path)

        # Track migration stats
        self.stats = {
            "subjects_migrated": 0,
            "experiments_migrated": 0,
            "videos_found": 0,
            "errors": []
        }

    def load_source_data(self) -> Dict[str, Any]:
        """Load the source project state JSON file."""
        if not self.source_state_file.exists():
            raise FileNotFoundError(f"Source project state not found: {self.source_state_file}")

        logger.info(f"Loading source data from {self.source_state_file}")
        with open(self.source_state_file, 'r') as f:
            return json.load(f)

    def map_sex(self, sex_str: str) -> Sex:
        """Map string sex representation to enum."""
        mapping = {
            "M": Sex.MALE,
            "F": Sex.FEMALE,
            "Male": Sex.MALE,
            "Female": Sex.FEMALE,
            "Unknown": Sex.UNKNOWN
        }
        return mapping.get(sex_str.upper() if sex_str else "UNKNOWN", Sex.UNKNOWN)

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse date: {date_str}")
            return None

    def migrate_subjects(self, subjects_data: Dict[str, Any]):
        """Migrate subjects from JSON to SQLite."""
        logger.info(f"Migrating {len(subjects_data)} subjects...")

        for subject_id, subject_data in subjects_data.items():
            try:
                # Map sex
                sex = self.map_sex(subject_data.get("sex", "Unknown"))

                # Parse dates
                birth_date = self.parse_date(subject_data.get("birth_date"))
                death_date = self.parse_date(subject_data.get("death_date"))

                # Create subject
                subject = Subject(
                    id=subject_id,
                    sex=sex,
                    birth_date=birth_date,
                    death_date=death_date,
                    genotype=subject_data.get("genotype", "UNKNOWN"),
                    treatment=subject_data.get("treatment"),
                    notes=subject_data.get("notes", ""),
                    date_added=self.parse_date(subject_data.get("date_added")) or datetime.now()
                )

                # Save to database
                saved_subject = self.pm.add_subject(subject)
                logger.info(f"Migrated subject: {saved_subject.id} ({saved_subject.genotype})")
                self.stats["subjects_migrated"] += 1

            except Exception as e:
                error_msg = f"Failed to migrate subject {subject_id}: {str(e)}"
                logger.error(error_msg)
                self.stats["errors"].append(error_msg)

    def extract_experiment_info(self, experiment_id: str) -> Dict[str, Any]:
        """Extract experiment type and metadata from experiment ID."""
        # Parse experiment ID format: SUBJECT_TYPE_DATE_SESSION
        # Example: "056_EZM_20230528_1" -> EZM experiment
        parts = experiment_id.split('_')
        if len(parts) >= 3:
            experiment_type = parts[1]
            # Map common abbreviations to full names
            type_mapping = {
                "EZM": "ElevatedZeroMaze",
                "OF": "OpenField",
                "NOV": "NovelObjectRecognition",
                "FAM": "Familiarization",
                "RR": "Rotarod"
            }
            experiment_type = type_mapping.get(experiment_type, experiment_type)
            return {
                "experiment_type": experiment_type,
                "subtype": parts[3] if len(parts) > 3 else None
            }
        return {"experiment_type": "Unknown", "subtype": None}

    def migrate_experiments(self, subjects_data: Dict[str, Any]):
        """Migrate experiments from JSON to SQLite."""
        logger.info("Migrating experiments...")

        for subject_id, subject_data in subjects_data.items():
            experiment_ids = subject_data.get("experiment_ids", [])

            for experiment_id in experiment_ids:
                try:
                    # Extract experiment info from ID
                    exp_info = self.extract_experiment_info(experiment_id)

                    # Create experiment
                    experiment = Experiment(
                        id=experiment_id,
                        subject_id=subject_id,
                        experiment_type=exp_info["experiment_type"],
                        experiment_subtype=exp_info["subtype"],
                        processing_stage=ProcessingStage.RECORDED,  # Assume recorded if in project
                        date_recorded=self.extract_date_from_id(experiment_id),
                        notes=f"Migrated from legacy system",
                        date_added=datetime.now()
                    )

                    # Save to database
                    saved_experiment = self.pm.add_experiment(experiment)
                    logger.info(f"Migrated experiment: {saved_experiment.id} ({saved_experiment.experiment_type})")
                    self.stats["experiments_migrated"] += 1

                except Exception as e:
                    error_msg = f"Failed to migrate experiment {experiment_id}: {str(e)}"
                    logger.error(error_msg)
                    self.stats["errors"].append(error_msg)

    def extract_date_from_id(self, experiment_id: str) -> datetime:
        """Extract date from experiment ID."""
        # Look for date pattern YYYYMMDD in the ID
        import re
        date_match = re.search(r'(\d{8})', experiment_id)
        if date_match:
            date_str = date_match.group(1)
            try:
                return datetime.strptime(date_str, '%Y%m%d')
            except ValueError:
                pass
        return datetime.now()

    def scan_and_add_videos(self):
        """Scan for video files and add them to the database."""
        logger.info("Scanning for video files...")

        # Define search paths (adjust as needed)
        search_paths = [
            self.source_project_path / "media",
            Path("/Volumes/CuSSD3/open_field_structured"),
            Path("/Volumes/CuSSD3/moseq_media"),
            Path("/Volumes/CuSSD3/open field")
        ]

        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.mpg'}

        for search_path in search_paths:
            if not search_path.exists():
                continue

            logger.info(f"Scanning {search_path} for videos...")
            for file_path in search_path.rglob('*'):
                if file_path.suffix.lower() in video_extensions:
                    try:
                        # Calculate file hash
                        hash_value = self.calculate_file_hash(file_path)

                        # Get file stats
                        stat = file_path.stat()

                        # Create video record
                        video = VideoFile(
                            path=file_path,
                            hash=hash_value,
                            recorded_time=None,  # We'll set this later if we can parse from filename
                            size_bytes=stat.st_size,
                            last_modified=stat.st_mtime,
                            date_added=datetime.now()
                        )

                        # Add to database
                        saved_video = self.pm.add_video(video)
                        logger.info(f"Added video: {saved_video.path.name}")
                        self.stats["videos_found"] += 1

                    except Exception as e:
                        error_msg = f"Failed to add video {file_path}: {str(e)}"
                        logger.warning(error_msg)
                        self.stats["errors"].append(error_msg)

    def calculate_file_hash(self, file_path: Path, chunk_size: int = 8192) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()

    def run_migration(self):
        """Run the complete migration process."""
        logger.info("Starting MUS1 SQLite migration...")
        logger.info(f"Source: {self.source_project_path}")
        logger.info(f"Target: {self.target_project_path}")

        try:
            # Load source data
            source_data = self.load_source_data()

            # Migrate subjects
            subjects_data = source_data.get("subjects", {})
            self.migrate_subjects(subjects_data)

            # Migrate experiments
            self.migrate_experiments(subjects_data)

            # Scan and add videos
            self.scan_and_add_videos()

            # Print migration summary
            self.print_summary()

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            raise

    def print_summary(self):
        """Print migration summary."""
        logger.info("=" * 50)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 50)
        logger.info(f"Subjects migrated: {self.stats['subjects_migrated']}")
        logger.info(f"Experiments migrated: {self.stats['experiments_migrated']}")
        logger.info(f"Videos found: {self.stats['videos_found']}")
        logger.info(f"Errors: {len(self.stats['errors'])}")

        if self.stats['errors']:
            logger.info("\nErrors encountered:")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                logger.info(f"  - {error}")
            if len(self.stats['errors']) > 5:
                logger.info(f"  ... and {len(self.stats['errors']) - 5} more")

def main():
    """CLI entry point for migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate MUS1 project to SQLite")
    parser.add_argument("source", help="Path to source MUS1 project directory")
    parser.add_argument("target", help="Path to target SQLite project directory")

    args = parser.parse_args()

    source_path = Path(args.source)
    target_path = Path(args.target)

    migrator = MUS1Migrator(source_path, target_path)
    migrator.run_migration()

if __name__ == "__main__":
    main()
