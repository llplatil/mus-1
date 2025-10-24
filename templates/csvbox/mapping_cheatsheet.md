# MUS1 CSVBox Mapping Cheatsheet

This maps columns from your current sheets to the MUS1 templates.

## Subjects (template: subjects_template.csv)
- **id**: tag number (normalize to digits only, e.g., 056 -> 56)
- **colony_id**: lab-defined colony code (e.g., ZN-1). If not tracked in sheet, set once in UI.
- **sex**: M/F/Unknown (map from Sex or tag suffix like 169f -> F)
- **birth_date**: ISO YYYY-MM-DD (parse from DOB/Birthdate)
- **individual_genotype**: from GENOTYPE/Genotype (normalize to WT/HET/KO)
- **individual_treatment**: from Treatment/TREATMENT,