#!/usr/bin/env python3
import pandas as pd
import argparse

def main():
    parser = argparse.ArgumentParser(description="Merge multiple subject CSVs into a consolidated file")
    parser.add_argument('inputs', nargs='+', help="Input subject CSV files")
    parser.add_argument('-o', '--output', help="Output merged CSV path", default=None)
    args = parser.parse_args()

    # Read and concatenate input CSVs
    dfs = [pd.read_csv(csv_path, dtype={'subject_id': str}) for csv_path in args.inputs]
    combined = pd.concat(dfs, ignore_index=True)

    # Merge subjects by subject_id, taking first metadata values and concatenating notes
    def merge_notes(series):
        notes = series.dropna().astype(str)
        unique_notes = [n for n in notes.unique() if n]
        return '; '.join(unique_notes)
    agg_dict = {
        'sex': 'first',
        'birth_date': 'first',
        'genotype': 'first',
        'treatment': 'first',
        'death_date': 'first',
        'notes': merge_notes
    }
    merged = combined.groupby('subject_id', as_index=False).agg(agg_dict)

    # Determine output path
    output_csv = args.output if args.output else 'test_data/subjects_copperlab.csv'
    merged.to_csv(output_csv, index=False)
    print(f"Merged {len(merged)} unique subjects to {output_csv}")

if __name__ == '__main__':
    main() 