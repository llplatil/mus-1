# mus1-assembly-plugin-copperlab

Copperlab assembly plugin for MUS1. Provides CSV-driven assembly and metadata resolver utilities.

## Install (dev)

From the MUS1 repo root (using the project venv):

```bash
python -m pip install -e .plugins/mus1-assembly-plugin-copperlab
```

Or for regular install:

```bash
python -m pip install .plugins/mus1-assembly-plugin-copperlab
```

## Package Structure

```
mus1-assembly-plugin-copperlab/
├── mus1_assembly_plugin_copperlab/
│   ├── __init__.py
│   └── assembly.py
├── pyproject.toml
└── README.md
```

## Entry point

```toml
[project.entry-points."mus1.plugins"]
CopperlabAssembly = "mus1_assembly_plugin_copperlab:CopperlabAssembly"
```

## Capabilities

- CSV parsing and project assembly
  - parse_experiments_csv
  - add_experiments_from_csv
  - link_media_by_csv
- Metadata resolver actions (migrated from in-tree resolver)
  - suggest_subjects
  - assign_subject_to_recording
  - assign_subject_sex
  - propose_subject_assignments_from_master
  - propose_subject_sex_from_master

## Lab Setup and Usage

### Initial Lab Setup (Run these commands in order)

Before using this plugin, set up your lab and genotypes:

```bash
# 1. Create the lab
mus1 lab create --name "Copperlab" --id copperlab --description 
#removed commands that actually dont work in cli 



# 4. Create and associate a project with the lab
mus1 project create /path/to/your/project --name "My Copperlab Project"
mus1 project associate-lab /path/to/your/project --lab copperlab

# 5. Accept lab genotypes for the project
mus1 genotype accept-lab-tracked --all --project /path/to/your/project
```

### Subject Extraction Workflow

After setup, use the CLI commands for subject extraction:

```bash
# Extract subjects from CSV folder
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action subjects_from_csv_folder \
  --param csv_dir=/path/to/csvs

# Get a batch of subjects for review
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action get_subject_batch \
  --param csv_dir=/path/to/csvs \
  --param confidence_level=high \
  --param batch_size=10

# Approve subjects
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action approve_subject_batch \
  --param csv_dir=/path/to/csvs \
  --param subject_ids="001,002,003" \
  --param confidence_level=high
```

### Manual CLI Usage

For direct CLI usage:

```bash
# List available assembly plugins and actions
mus1 project assembly list
mus1 project assembly list-actions CopperlabAssembly

# Extract subjects from CSV folder
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action subjects_from_csv_folder \
  --param csv_dir=/path/to/csvs

# Get a batch of subjects for review
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action get_subject_batch \
  --param csv_dir=/path/to/csvs \
  --param confidence_level=high \
  --param batch_size=10
```

### Experiment Types

The plugin recognizes these CSV sections as experiment types:
- "Open field/Arena Habitation" → OF
- "Novel object | Familiarization Session" → FAM
- "Novel object | Recognition Session" → NOV
- "Elevated zero maze" → EZM
- "Rota Rod" → RR
# will need to add elevated zero maze as EZM

### Notes

- Subject IDs are automatically normalized to 3 digits when purely numeric
- On plugin reinstall, clean old egg-info/build artifacts to avoid duplicates
- The workflow script handles interactive approval of subject extraction batches