#!/usr/bin/env python3
"""
Copperlab Data Cleaning and Transformation Script

This script processes raw CSV files from the Copperlab mouse zinc study and transforms
them into clean, structured data suitable for import into MUS1 via the copperlab plugin.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import json
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CopperlabDataCleaner:
    """Class for cleaning and transforming Copperlab CSV data."""

    def __init__(self, csv_dir: Path):
        self.csv_dir = csv_dir
        self.subjects = {}
        self.experiments = []

        # Experiment type mappings
        self.experiment_mappings = {
            'open field/arean habitation': 'OF',
            'novel object | familiarization session': 'FAM',
            'novel object | recognition session': 'NOV',
            'elevated zero maze': 'EZM',
            'rota rod': 'RR'
        }

        # Genotype normalization
        self.genotype_mapping = {
            'wt': 'WT',
            'het': 'HET',
            'ko': 'KO',
            'wild type': 'WT',
            'heterozygous': 'HET',
            'knockout': 'KO'
        }

    def clean_four_week_treatment_csv(self) -> Dict[str, Any]:
        """Clean the four week treatment CSV file."""
        file_path = self.csv_dir / "Mouse Zn MASTER - FOUR WEEK TREATMENT.csv"

        if not file_path.exists():
            logger.warning(f"Four week treatment file not found: {file_path}")
            return {}

        logger.info("Processing four week treatment data...")

        # Read the CSV with careful handling
        try:
            df = pd.read_csv(file_path, header=None, encoding='utf-8')
        except Exception as e:
            logger.warning(f"Error reading CSV with utf-8, trying latin1: {e}")
            df = pd.read_csv(file_path, header=None, encoding='latin1')

        subjects_data = {}

        # Process male section (rows 2-8)
        male_section_start = 2
        male_animals = []
        for row_idx in range(male_section_start, male_section_start + 6):
            if row_idx < len(df):
                row = df.iloc[row_idx]
                if len(row) > 1 and pd.notna(row[1]):
                    animal_id = str(row[1]).strip()
                    if animal_id and animal_id.isdigit():
                        genotype = str(row[2]).strip().lower() if len(row) > 2 else ""
                        genotype = self.genotype_mapping.get(genotype, genotype.upper())
                        male_animals.append({
                            'id': f"{int(animal_id):03d}",
                            'sex': 'M',
                            'genotype': genotype,
                            'treatment': 'CNTRL' if 'CNTRL' in str(row[0]).upper() else 'WT/Het'
                        })

        # Process female section (rows 9-15)
        female_section_start = 9
        female_animals = []
        for row_idx in range(female_section_start, female_section_start + 6):
            if row_idx < len(df):
                row = df.iloc[row_idx]
                if len(row) > 3 and pd.notna(row[3]):
                    animal_id = str(row[3]).strip()
                    if animal_id and animal_id.isdigit():
                        genotype = str(row[4]).strip().lower() if len(row) > 4 else ""
                        genotype = self.genotype_mapping.get(genotype, genotype.upper())
                        female_animals.append({
                            'id': f"{int(animal_id):03d}",
                            'sex': 'F',
                            'genotype': genotype,
                            'treatment': 'CNTRL' if 'CNTRL' in str(row[2]).upper() else 'WT/Het'
                        })

        # Process later sections (TTM, ZN treatments)
        for row_idx in range(17, len(df)):
            if row_idx < len(df):
                row = df.iloc[row_idx]
                if len(row) > 1:
                    # Check for animal IDs in various positions
                    for col_idx in range(len(row)):
                        if pd.notna(row[col_idx]):
                            animal_id = str(row[col_idx]).strip()
                            if animal_id and animal_id.isdigit() and len(animal_id) <= 3:
                                genotype = ""
                                treatment = ""

                                # Determine treatment based on section
                                if "TTM" in str(row[0]).upper() or "TTM" in str(df.iloc[max(0, row_idx-2), 0]).upper():
                                    treatment = "TTM"
                                elif "ZN" in str(row[0]).upper() or "ZN" in str(df.iloc[max(0, row_idx-2), 0]).upper():
                                    treatment = "ZN"

                                # Try to get genotype from adjacent columns
                                if col_idx + 1 < len(row) and pd.notna(row[col_idx + 1]):
                                    genotype_raw = str(row[col_idx + 1]).strip().lower()
                                    genotype = self.genotype_mapping.get(genotype_raw, genotype_raw.upper())

                                subjects_data[f"{int(animal_id):03d}"] = {
                                    'id': f"{int(animal_id):03d}",
                                    'sex': 'M' if 'MALES' in str(df.iloc[max(0, row_idx-3), 0]).upper() else 'F',
                                    'genotype': genotype,
                                    'treatment': treatment,
                                    'source': 'four_week_treatment'
                                }

        # Add male and female animals
        for animal in male_animals + female_animals:
            subjects_data[animal['id']] = animal

        logger.info(f"Extracted {len(subjects_data)} subjects from four week treatment data")
        return subjects_data

    def clean_colony_csv(self) -> Dict[str, Any]:
        """Clean the colony CSV file."""
        file_path = self.csv_dir / "Mouse Zn MASTER - COLONY.csv"

        if not file_path.exists():
            logger.warning(f"Colony file not found: {file_path}")
            return {}

        logger.info("Processing colony data...")

        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except Exception as e:
            logger.warning(f"Error reading CSV with utf-8, trying latin1: {e}")
            df = pd.read_csv(file_path, encoding='latin1')

        subjects_data = {}

        for _, row in df.iterrows():
            # Extract animal ID (first column)
            animal_id_raw = str(row.iloc[0]).strip()
            if not animal_id_raw or not animal_id_raw[0].isdigit():
                continue

            # Parse animal ID and sex
            animal_id = re.match(r'(\d+)', animal_id_raw)
            if not animal_id:
                continue

            animal_id = animal_id.group(1)
            sex = 'M' if 'm' in animal_id_raw.lower() else 'F'

            # Extract other data
            dob = str(row.get('DOB', '')).strip()
            genotype = str(row.get('GENOTYPE', '')).strip().lower()
            genotype = self.genotype_mapping.get(genotype, genotype.upper())

            treatment_status = str(row.get('TREATMENT, STATUS', '')).strip()
            notes = str(row.get('NOTES', '')).strip()

            # Parse birth date
            birth_date = None
            if dob:
                try:
                    birth_date = datetime.strptime(dob, '%m/%d/%Y').strftime('%Y-%m-%d')
                except ValueError:
                    try:
                        birth_date = datetime.strptime(dob, '%m/%d/%y').strftime('%Y-%m-%d')
                    except ValueError:
                        pass

            subjects_data[f"{int(animal_id):03d}"] = {
                'id': f"{int(animal_id):03d}",
                'sex': sex,
                'birth_date': birth_date,
                'genotype': genotype,
                'treatment': treatment_status,
                'notes': notes,
                'source': 'colony'
            }

        logger.info(f"Extracted {len(subjects_data)} subjects from colony data")
        return subjects_data

    def clean_behavior_csv(self, csv_file: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """Clean behavior CSV files and extract experiments and subjects."""
        logger.info(f"Processing behavior data from {csv_file.name}...")

        try:
            df = pd.read_csv(csv_file, encoding='utf-8')
        except Exception as e:
            logger.warning(f"Error reading CSV with utf-8, trying latin1: {e}")
            df = pd.read_csv(csv_file, encoding='latin1')

        experiments = []
        subjects = {}
        current_section = None

        for _, row in df.iterrows():
            # Check for section headers
            first_col = str(row.iloc[0]).strip().lower() if len(row) > 0 else ""

            if first_col in self.experiment_mappings:
                current_section = self.experiment_mappings[first_col]
                continue

            # Skip if no current section or insufficient data
            if not current_section or len(row) < 5:
                continue

            # Extract experiment data
            subject_id = None
            date = None
            time_in = None
            treatment = None
            notes = []

            # Find subject ID (usually first column with digits)
            for col in row:
                col_str = str(col).strip()
                if col_str and col_str.isdigit() and len(col_str) <= 3:
                    subject_id = f"{int(col_str):03d}"
                    break

            if not subject_id:
                continue

            # Extract date (usually in MM/DD/YYYY format)
            for col in row:
                col_str = str(col).strip()
                if col_str and '/' in col_str:
                    try:
                        date = datetime.strptime(col_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        try:
                            date = datetime.strptime(col_str, '%m/%d/%y').strftime('%Y-%m-%d')
                            break
                        except ValueError:
                            continue

            # Extract time and treatment
            for col in row:
                col_str = str(col).strip()
                if not time_in and ':' in col_str and ('AM' in col_str.upper() or 'PM' in col_str.upper()):
                    time_in = col_str
                elif not treatment and col_str.upper() in ['CONTROL', 'ZN', 'D-PEN']:
                    treatment = col_str.upper()

            # Collect notes
            for col in row:
                col_str = str(col).strip()
                if col_str and len(col_str) > 3 and not any(char.isdigit() for char in col_str[:10]):
                    notes.append(col_str)

            if subject_id and date:
                experiments.append({
                    'subject_id': subject_id,
                    'experiment_type': current_section,
                    'date': date,
                    'time_in': time_in,
                    'treatment': treatment,
                    'notes': '; '.join(notes),
                    'source_file': csv_file.name
                })

                # Also create a minimal subject entry if we don't have one
                if subject_id not in subjects:
                    subjects[subject_id] = {
                        'id': subject_id,
                        'sex': None,  # We don't know the sex from behavior data
                        'genotype': None,  # We don't know the genotype from behavior data
                        'treatment': treatment or 'CONTROL',  # Default to CONTROL if not specified
                        'source': f'behavior_{csv_file.name}'
                    }

        logger.info(f"Extracted {len(experiments)} experiments and {len(subjects)} subjects from {csv_file.name}")
        return experiments, subjects

    def merge_subjects_data(self, *subjects_dicts: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Merge subject data from multiple sources."""
        merged = {}

        for subjects_dict in subjects_dicts:
            for subject_id, subject_data in subjects_dict.items():
                if subject_id not in merged:
                    merged[subject_id] = subject_data.copy()
                else:
                    # Merge data, preferring non-empty values
                    existing = merged[subject_id]
                    for key, value in subject_data.items():
                        if key != 'id' and value and not existing.get(key):
                            existing[key] = value
                        elif key == 'source':
                            existing[key] = f"{existing.get('source', '')}; {value}".strip('; ')

        return merged

    def process_all_data(self) -> Dict[str, Any]:
        """Process all CSV files and generate clean dataset."""
        logger.info("Starting data processing...")

        # Process subjects from different sources
        four_week_subjects = self.clean_four_week_treatment_csv()
        colony_subjects = self.clean_colony_csv()

        # Merge subject data
        all_subjects = self.merge_subjects_data(four_week_subjects, colony_subjects)

        # Process behavior data
        behavior_files = [
            self.csv_dir / "Mouse Zn MASTER - BEHAVIOR RECORDS [6-14 weeks] (4).csv",
            self.csv_dir / "Mouse Zn MASTER - BEHAVIOR RECORDS [12-20 WEEKS] (4).csv"
        ]

        all_experiments = []
        behavior_subjects = {}

        for behavior_file in behavior_files:
            if behavior_file.exists():
                experiments, subjects = self.clean_behavior_csv(behavior_file)
                all_experiments.extend(experiments)
                # Merge behavior subjects
                for subject_id, subject_data in subjects.items():
                    if subject_id not in behavior_subjects:
                        behavior_subjects[subject_id] = subject_data

        # Merge behavior subjects into main subjects
        all_subjects = self.merge_subjects_data(all_subjects, behavior_subjects)

        # Convert subjects dict to list
        subjects_list = list(all_subjects.values())

        # Sort subjects by ID
        subjects_list.sort(key=lambda x: int(x['id']) if x['id'].isdigit() else 0)

        # Sort experiments by subject ID, date, experiment type
        all_experiments.sort(key=lambda x: (
            int(x['subject_id']) if x['subject_id'].isdigit() else 0,
            x['date'],
            x['experiment_type']
        ))

        result = {
            'subjects': subjects_list,
            'experiments': all_experiments,
            'metadata': {
                'total_subjects': len(subjects_list),
                'total_experiments': len(all_experiments),
                'processed_files': [
                    "Mouse Zn MASTER - FOUR WEEK TREATMENT.csv",
                    "Mouse Zn MASTER - COLONY.csv",
                    "Mouse Zn MASTER - BEHAVIOR RECORDS [6-14 weeks] (4).csv",
                    "Mouse Zn MASTER - BEHAVIOR RECORDS [12-20 WEEKS] (4).csv"
                ],
                'generated_at': datetime.now().isoformat()
            }
        }

        logger.info(f"Processing complete: {len(subjects_list)} subjects, {len(all_experiments)} experiments")
        return result

    def save_clean_data(self, output_path: Path, data: Dict[str, Any]) -> None:
        """Save the cleaned data to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Clean data saved to {output_path}")

def main():
    """Main function to run the data cleaning process."""
    import argparse

    parser = argparse.ArgumentParser(description="Clean Copperlab CSV data")
    parser.add_argument("--csv-dir", type=str,
                       help="Directory containing CSV files (defaults to plugin data dir)")
    parser.add_argument("--output", type=str, default="clean_copperlab_data.json",
                       help="Output JSON file path")

    args = parser.parse_args()

    # Get CSV directory - default to plugin data directory
    if args.csv_dir:
        csv_dir = Path(args.csv_dir).resolve()
    else:
        # Default to plugin's data directory
        plugin_root = Path(__file__).parent.parent
        csv_dir = plugin_root / "data"

    if not csv_dir.exists():
        logger.error(f"CSV directory does not exist: {csv_dir}")
        return 1

    output_file = Path(args.output).resolve()
    if not output_file.is_absolute():
        # If relative, put it in the plugin's processing directory
        output_file = Path(__file__).parent / args.output

    cleaner = CopperlabDataCleaner(csv_dir)
    clean_data = cleaner.process_all_data()
    cleaner.save_clean_data(output_file, clean_data)

    print(f"Data cleaning complete!")
    print(f"Subjects: {clean_data['metadata']['total_subjects']}")
    print(f"Experiments: {clean_data['metadata']['total_experiments']}")
    print(f"Output: {output_file}")

if __name__ == "__main__":
    main()
