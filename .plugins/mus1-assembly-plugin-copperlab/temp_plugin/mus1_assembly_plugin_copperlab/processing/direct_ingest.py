#!/usr/bin/env python3
"""
Direct Copperlab Data Ingest Script for MUS1

This script directly loads cleaned copperlab data into MUS1 without relying on plugins.
It creates subjects and experiments directly using MUS1's core functionality.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
import sys
from datetime import datetime

# Add the src directory to the path so we can import MUS1 modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from mus1.core.app_initializer import initialize_mus1_app
    from mus1.core.metadata import Sex
except ImportError as e:
    print(f"Error importing MUS1 modules: {e}")
    print("Make sure you're running this from the correct directory and MUS1 is properly installed.")
    sys.exit(1)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DirectCopperlabIngester:
    """Class for directly ingesting cleaned copperlab data into MUS1."""

    def __init__(self, clean_data_path: Path):
        self.clean_data_path = clean_data_path
        self.clean_data = None
        self.state = None
        self.plugin_manager = None
        self.dm = None
        self.project_manager = None
        self.theme_manager = None
        self.log_bus = None

    def load_clean_data(self) -> Dict[str, Any]:
        """Load the cleaned data from JSON file."""
        logger.info(f"Loading clean data from {self.clean_data_path}")

        if not self.clean_data_path.exists():
            raise FileNotFoundError(f"Clean data file not found: {self.clean_data_path}")

        with open(self.clean_data_path, 'r', encoding='utf-8') as f:
            self.clean_data = json.load(f)

        logger.info(f"Loaded {len(self.clean_data['subjects'])} subjects and {len(self.clean_data['experiments'])} experiments")
        return self.clean_data

    def initialize_mus1(self) -> None:
        """Initialize MUS1 application and get managers."""
        logger.info("Initializing MUS1 application...")

        try:
            self.state, self.plugin_manager, self.dm, self.project_manager, self.theme_manager, self.log_bus = initialize_mus1_app()

            if not self.project_manager:
                raise RuntimeError("Failed to initialize MUS1 project manager")

            logger.info("MUS1 application initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MUS1: {e}")
            raise

    def create_or_load_project(self, project_path: Path) -> bool:
        """Create or load a MUS1 project."""
        project_path = project_path.expanduser().resolve()

        try:
            if not project_path.exists():
                logger.info(f"Creating new project: {project_path}")
                self.project_manager.create_project(project_path, project_path.name)
                logger.info("Project created successfully")
            else:
                logger.info(f"Loading existing project: {project_path}")
                self.project_manager.load_project(project_path)
                logger.info("Project loaded successfully")

            return True
        except Exception as e:
            logger.error(f"Failed to create/load project: {e}")
            return False

    def create_subjects(self, subjects_data: List[Dict[str, Any]]) -> int:
        """Create subjects directly in MUS1."""
        logger.info(f"Creating {len(subjects_data)} subjects...")

        created_count = 0
        skipped_count = 0

        for subject_data in subjects_data:
            try:
                subject_id = subject_data['id']

                # Determine sex
                sex = None
                if subject_data.get('sex') == 'M':
                    sex = Sex.M
                elif subject_data.get('sex') == 'F':
                    sex = Sex.F
                else:
                    # Try to infer sex from ID if it ends with 'm' or 'f'
                    id_lower = str(subject_id).lower()
                    if id_lower.endswith('m'):
                        sex = Sex.M
                    elif id_lower.endswith('f'):
                        sex = Sex.F

                # Use genotype or default to 'UNKNOWN'
                genotype = subject_data.get('genotype') or 'UNKNOWN'

                # Use defaults for missing fields
                if not sex:
                    sex = Sex.M  # Default to Male
                    logger.info(f"Using default sex=M for subject {subject_id}")

                if not genotype:
                    genotype = 'UNKNOWN'  # Default genotype
                    logger.info(f"Using default genotype=UNKNOWN for subject {subject_id}")

                birth_date = subject_data.get('birth_date')
                treatment = subject_data.get('treatment')

                self.project_manager.add_subject(
                    subject_id=subject_id,
                    sex=sex,
                    birth_date=birth_date,
                    genotype=genotype,
                    treatment=treatment
                )

                created_count += 1
                if created_count % 10 == 0:
                    logger.info(f"Created {created_count} subjects...")

            except Exception as e:
                logger.warning(f"Failed to create subject {subject_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue

        logger.info(f"Successfully created {created_count} subjects, skipped {skipped_count}")
        return created_count

    def create_experiments(self, experiments_data: List[Dict[str, Any]]) -> int:
        """Create experiments directly in MUS1."""
        logger.info(f"Creating {len(experiments_data)} experiments...")

        created_count = 0
        skipped_count = 0
        experiment_counters = {}  # Track duplicates

        for exp_data in experiments_data:
            try:
                subject_id = exp_data['subject_id']
                exp_type = exp_data['experiment_type']
                date_str = exp_data['date']
                time_in = exp_data.get('time_in', '')
                treatment = exp_data.get('treatment', '')

                # Parse date
                try:
                    date_recorded = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid date format for experiment: {date_str}")
                    skipped_count += 1
                    continue

                # Create unique experiment ID with additional info
                base_id = f"{subject_id}_{exp_type}_{date_str.replace('-', '')}"

                # Add counter for duplicates
                if base_id in experiment_counters:
                    experiment_counters[base_id] += 1
                    experiment_id = f"{base_id}_{experiment_counters[base_id]}"
                else:
                    experiment_counters[base_id] = 1
                    experiment_id = f"{base_id}_1"

                # Add more uniqueness with time/treatment if available
                if time_in:
                    # Clean time string and add to ID
                    time_clean = time_in.replace(':', '').replace(' ', '').replace('AM', 'A').replace('PM', 'P')
                    experiment_id = f"{experiment_id}_{time_clean}"

                if treatment and treatment != 'CONTROL':
                    experiment_id = f"{experiment_id}_{treatment.replace(' ', '_')}"

                # Ensure ID is not too long (MUS1 might have limits)
                if len(experiment_id) > 100:
                    experiment_id = experiment_id[:95] + "_etc"

                # Add experiment
                self.project_manager.add_experiment(
                    experiment_id=experiment_id,
                    subject_id=subject_id,
                    date_recorded=date_recorded,
                    exp_type=exp_type,
                    exp_subtype=None,
                    processing_stage="planned",
                    associated_plugins=[],
                    plugin_params={}
                )

                created_count += 1
                if created_count % 50 == 0:
                    logger.info(f"Created {created_count} experiments...")

            except Exception as e:
                logger.warning(f"Failed to create experiment for subject {exp_data.get('subject_id', 'unknown')}: {e}")
                skipped_count += 1
                continue

        logger.info(f"Successfully created {created_count} experiments, skipped {skipped_count}")
        return created_count

    def ingest_data(self, project_path: Path) -> Dict[str, Any]:
        """Main method to ingest all data into MUS1."""
        try:
            # Load clean data
            data = self.load_clean_data()

            # Initialize MUS1
            self.initialize_mus1()

            # Create or load project
            if not self.create_or_load_project(project_path):
                return {
                    "status": "failed",
                    "error": "Failed to create/load project"
                }

            # Create subjects
            subjects_created = self.create_subjects(data['subjects'])

            # Create experiments
            experiments_created = self.create_experiments(data['experiments'])

            result = {
                "status": "success",
                "project_path": str(project_path),
                "subjects_created": subjects_created,
                "experiments_created": experiments_created,
                "total_subjects": len(data['subjects']),
                "total_experiments": len(data['experiments']),
                "message": "Data ingestion completed successfully"
            }

            logger.info("Data ingestion completed successfully!")
            return result

        except Exception as e:
            logger.error(f"Error during data ingestion: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

def main():
    """Main function to run the data ingestion process."""
    parser = argparse.ArgumentParser(description="Direct ingest of cleaned copperlab data into MUS1")
    parser.add_argument(
        "clean_data_file",
        type=Path,
        help="Path to the cleaned data JSON file"
    )
    parser.add_argument(
        "project_path",
        type=Path,
        help="Path to the MUS1 project (will be created if it doesn't exist)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level"
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Validate input file
    if not args.clean_data_file.exists():
        print(f"Error: Clean data file not found: {args.clean_data_file}")
        sys.exit(1)

    print("🚀 Starting direct data ingestion into MUS1...")
    print(f"   Data file: {args.clean_data_file}")
    print(f"   Project: {args.project_path}")

    # Run ingestion
    ingester = DirectCopperlabIngester(args.clean_data_file)
    result = ingester.ingest_data(args.project_path)

    # Print result
    if result["status"] == "success":
        print("\n✅ Data ingestion completed successfully!")
        print(f"   Project: {result['project_path']}")
        print(f"   Subjects created: {result['subjects_created']}/{result['total_subjects']}")
        print(f"   Experiments created: {result['experiments_created']}/{result['total_experiments']}")
    else:
        print("\n❌ Data ingestion failed!")
        print(f"   Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
