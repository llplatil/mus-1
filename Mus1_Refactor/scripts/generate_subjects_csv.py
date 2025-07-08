#!/usr/bin/env python3
import pandas as pd
import os
import argparse

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate unique subjects CSV from behavior records CSV")
    parser.add_argument('-i', '--input', help="Path to input behavior CSV file", default=None)
    parser.add_argument('-o', '--output', help="Path to output subjects CSV file", default=None)
    args = parser.parse_args()

    # Determine default paths based on script location
    root = os.path.dirname(os.path.dirname(__file__))
    default_input = os.path.join(root, 'test_data', 'Mouse Zn MASTER - BEHAVIOR RECORDS [6-14 weeks] (1).csv')
    default_output = os.path.join(root, 'test_data', 'subjects_template.csv')
    raw_csv = args.input if args.input else default_input
    output_csv = args.output if args.output else default_output

    # Read raw CSV, skipping the first three lines so header row is used as column names
    df = pd.read_csv(raw_csv, skiprows=3)
    # Strip whitespace around column names and drop any unnamed columns
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.startswith('Unnamed')]

    # Rename relevant columns
    df = df.rename(columns={
        'Tag Number': 'subject_id',
        'Sex': 'sex',
        'Birthdate': 'birth_date',
        'Genotype': 'genotype',
        'Treatment type': 'treatment',
        'Notes': 'notes'
    })

    # Drop rows with missing or non-numeric subject_id (skip section headers)
    df = df[df['subject_id'].notna()]
    df = df[df['subject_id'].apply(lambda x: str(x).strip().isdigit())]
    # Normalize subject_id to string
    df['subject_id'] = df['subject_id'].astype(int).astype(str)

    # Parse and format birth_date
    df['birth_date'] = pd.to_datetime(df['birth_date'], errors='coerce').dt.date.astype(str)

    # Normalize sex values
    def normalize_sex(x):
        x = str(x).upper()
        if x.startswith('M'):
            return 'M'
        if x.startswith('F'):
            return 'F'
        return 'Unknown'
    df['sex'] = df['sex'].apply(normalize_sex)

    # Fill missing fields
    df['genotype'] = df.get('genotype', pd.Series()).fillna('')
    df['treatment'] = df.get('treatment', pd.Series()).fillna('')
    df['notes'] = df.get('notes', pd.Series()).fillna('')

    # Select unique subjects
    df_unique = df[['subject_id', 'sex', 'birth_date', 'genotype', 'treatment', 'notes']].drop_duplicates(subset=['subject_id'])

    # Add death_date column
    df_unique['death_date'] = ''

    # Write to CSV
    df_unique.to_csv(output_csv, index=False)
    print(f"Generated {len(df_unique)} unique subjects to {output_csv}")

if __name__ == '__main__':
    main() 