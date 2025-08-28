CustomProjectAssembly_Skeleton

This package is a starting point for lab-specific project assembly:

- Parse your lab's experiment CSVs and normalize to subject_id, experiment_type, date.
- Suggest matches between subjects and existing media in the project's media/ folder.
- Provide helpers for QA (ground-truth date tokens) and CSV-driven scans.

Files:
- project_assembly.py: plugin class and CSV parsing entrypoints
- utils.py: reusable CSV parsing and QA helpers
- subject_importer.py: optional bulk subject importer

Customize:
- Copy/rename this package (e.g., CustomProjectAssembly_MyLab)
- Adjust utils.py mappings to your CSV headers/sections
- Add config support if needed (e.g., subject ID patterns, preferred scan roots)

