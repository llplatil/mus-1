# MUS1: An Open Source Workflow Integration Platform for Animal Behavior Analysis

Mus-1 is a Python-based tool with an intuitive UI layer designed to streamline the analysis of subject behavior data allowing multidisciplinary workflows through a plugin based infrastructure. Mus-1 users can integrate multiple 3rd party open source tools within their respective pipline while maintaining data integrity without the hassle of managing import and export workflows from one analysis tool to the next. At its core, Mus-1 is built to accommodate each lab's unique research through its ability to support a variety of workflows and data types either through existing plugins or by developing a plugin that meets one's exact needs as outlined by the documentation provided within the Mus-1 install.

## Overview

MUS1 facilitates a lab-centric workflow starting from recordings, CSV files and processed tracking data, enabling users to:
1. **Lab Setup:** Create lab configurations with shared compute resources (workers, credentials, scan targets), **shared storage configuration**, and **genotype management**
2. **Project Association:** Link projects to labs for automatic resource inheritance and **shared storage usage**
3. **Import and Organize:** Manage tracking files, associated videos, and metadata within structured MUS1 projects. Import body part definitions directly from DLC `config.yaml` files with the DeepLabCutHandlerPlugin.
4. **Subject Management:** Extract subjects from CSV files with confidence scoring, manage subject lifecycles with CLI commands, and validate against lab genotype configurations
5. **Analyze Kinematics:** Perform foundational analyses like distance, speed, and zone occupancy using built-in analysis plugins.
6. **Manage Experiments:** Organize experiments by subject, type, and batch, tracking processing stages with support for RR (Rota Rod), OF (Open Field), and NOV (Novel Object) experiment types
7. **Standardize:** Apply consistent analysis parameters and lab-wide settings.

The project uses a modular architecture with plugins for data handling (e.g., DeepLabCut outputs), analysis (e.g., kinematics), and assembly (e.g., Copperlab CSV processing), all managed at the lab level. **New:** MUS1 now supports shared storage configuration, lab-level genotype tracking, and iterative subject extraction workflows.

## Features

- **Lab-Centric Architecture**: Centralized lab configuration with shared compute resources (workers, credentials, scan targets)
- **Shared Storage Configuration**: Automatic detection and usage of external drives (like CuSSD3) for project storage when labs are active
- **Lab-Level Genotype Management**: Configure and validate gene loci (e.g., ATP7B with WT/Het/KO alleles) at lab level with mutual exclusivity
- **Iterative Subject Extraction**: Extract subjects from CSV files with confidence scoring (high/medium/low/uncertain) and interactive approval workflows
- **Subject Lifecycle Management**: CLI commands for removing subjects from projects with optional bulk operations
- **Enhanced Experiment Types**: Support for RR (Rota Rod), OF (Open Field), and NOV (Novel Object) with specific subtypes and validation
- **Material Design UI**: Clean, modern interface built with PySide6-Qt.
- **Project Management**: Centralized handling of subjects, experiments, metadata, and analysis results with lab association.
- **DeepLabCut Integration**: Imports body parts from DLC configs and utilizes DLC tracking data (CSV/HDF5).
- **Plugin Architecture**: Supports data handlers (DLC), importers, assembly plugins, and analysis modules. Plugins are discovered via Python entry points (`mus1.plugins`).
- **Hierarchical Experiment Setup**: Step-by-step workflow linking data files and analysis parameters.
- **Batch Processing**: Group experiments for efficient management (analysis planned).
- **Observer Pattern**: UI components update automatically based on project state changes.
- **Theme System**: Light/dark themes with OS detection.
- **Per-recording Media Folders**: Each recording lives in its own folder under `project/media/subject-YYYYMMDD-hash8/` with a `metadata.json` tracking `subject_id`, `experiment_type`, hashes, times, provenance, and processing history.
- **Lab-Level Resource Management**: Workers, credentials, and scan targets managed at lab level and inherited by associated projects.

## Intended Workflow

1.  **Lab Setup**: Create a lab configuration with shared resources, storage, and genotype management
   ```bash
   mus1 lab create --name "My Lab"
   mus1 lab add-worker --name compute-01 --ssh-alias server1
   mus1 lab add-credential --alias server1 --user researcher
   # Configure genotype system (e.g., ATP7B for Copperlab)
   mus1 lab add-genotype --gene-name ATP7B --locus default --alleles WT,Het,KO
   ```

2.  **Configure Shared Storage** (Optional): Set up shared storage for the lab
   ```bash
   # Configure CuSSD3 as shared storage
   mus1 lab configure-storage --mount-point /Volumes/CuSSD3 --volume-name CuSSD3 --enabled --auto-detect
   ```

3.  **Activate Lab**: Activate the lab to use its configured resources and storage
   ```bash
   mus1 lab activate my_lab
   ```

4.  **Project Association**: Create or associate projects with the lab (projects will use shared storage if configured)
   ```bash
   mus1 project create my_project  # Automatically uses shared storage if lab is active
   mus1 project associate-lab my_project --lab-id my_lab
   ```

5.  **Subject Extraction**: Extract subjects from CSV files with confidence scoring and approval workflow
   ```bash
   # Initialize iterative subject extraction
   mus1 project assembly run my_project --plugin CopperlabAssembly \
     --action extract_subjects_iterative --param "csv_dir=/path/to/csvs"

   # Get batches for review by confidence level
   mus1 project assembly run my_project --plugin CopperlabAssembly \
     --action get_subject_batch --param "csv_dir=/path/to/csvs" \
     --param "confidence_level=high" --param "batch_size=10"

   # Approve subjects to add to lab
   mus1 project assembly run my_project --plugin CopperlabAssembly \
     --action approve_subject_batch --param "csv_dir=/path/to/csvs" \
     --param "subject_ids=169,175,180" --param "confidence_level=high"
   ```

6.  **Subject Management**: Manage subject lifecycles throughout the project
   ```bash
   # Remove specific subjects
   mus1 project remove-subjects my_project --subject-id 169 --subject-id 175

   # Remove all subjects (with confirmation)
   mus1 project remove-subjects my_project --all
   ```

7.  **Tracking (External)**: Use **DeepLabCut** (installed separately) to track keypoints from your experimental videos. Generate tracking CSV/HDF5 files.

8.  **Import DLC Config (Optional)**: Use the `DlcProjectImporter` plugin within MUS1 to populate the project's master body part list from your DLC project's `config.yaml`.

9.  **Define Experiments in MUS1**: Add subjects and experiments with enhanced experiment types (RR, OF, NOV). Use the `DeepLabCutHandler` plugin parameters to link each experiment to its corresponding DLC tracking file (CSV/HDF5).

10. **Run Kinematic Analysis (MUS1)**: Use the `Mus1TrackingAnalysis` plugin via the MUS1 interface to calculate metrics like distance, speed, zone time, etc. Results are stored within the experiment's metadata.

11. **Future**: MoSeq2/Keypoint-MoSeq orchestration and feature extraction are planned via a dedicated plugin (see Roadmap). The current GCP orchestrator is deprecated in favor of a future server-backed integration.

## Requirements

### System Dependencies
- **ffmpeg/ffprobe** (video metadata & hashing). Install via Homebrew `brew install ffmpeg` or apt `sudo apt install ffmpeg`.

- Python 3.10+
- **DeepLabCut**: Must be installed separately. Used externally for keypoint tracking before using MUS1. See DeepLabCut Installation docs.

## Documentation
- Development Roadmap: `docs/dev/ROADMAP.md`
- Architecture Documentation: `docs/dev/ARCHITECTURE_CURRENT.md`
- Architecture Summary: `docs/dev/Architecture.md`

## CLI Quick Reference

# Lab Management
```bash
# Create and configure labs
mus1 lab create --name "My Lab"
mus1 lab list
mus1 lab activate my_lab
mus1 lab status

# Configure shared storage
mus1 lab configure-storage --mount-point /Volumes/CuSSD3 --volume-name CuSSD3 --enabled --auto-detect

# Add lab resources
mus1 lab add-worker --name compute-01 --ssh-alias server1
mus1 lab add-credential --alias server1 --user researcher
mus1 lab add-target --name local-media --kind local --root ~/Videos

# Add genotype configurations
mus1 genotype add-to-lab --gene ATP7B --allele WT --allele Het --allele KO --inheritance recessive --mendelian

# Associate projects with labs
mus1 project associate-lab /path/to/project --lab-id my_lab
mus1 project lab-status /path/to/project
```

# Subject Management
```bash
# Remove subjects from projects
mus1 project remove-subjects /path/to/project --subject-id 169 --subject-id 175
mus1 project remove-subjects /path/to/project --all
```

# Assembly (generic, plugin-discovered)
```bash
# List assembly-capable plugins and their actions, lab specific
mus1 project assembly list
mus1 project assembly list-actions CopperlabAssembly

# Iterative subject extraction workflow
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action extract_subjects_iterative \
  --param csv_dir=/path/to/csvs

mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action get_subject_batch \
  --param csv_dir=/path/to/csvs \
  --param confidence_level=high \
  --param batch_size=10

mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action approve_subject_batch \
  --param csv_dir=/path/to/csvs \
  --param subject_ids=169,175,180 \
  --param confidence_level=high

# Legacy CSV processing
mus1 project assembly run /path/to/project \
  --plugin CopperlabAssembly \
  --action subjects_from_csv_folder \
  --param csv_dir=/path/to/csvs
```

# Third-party/importer (generic)
```bash
# List available importer plugins and run one with parameters
mus1 project import-supported-3rdparty /path/to/project --list
mus1 project import-supported-3rdparty /path/to/project \
  --plugin "MoSeq2 Importer" \
  --params-file params.yaml \
  --param key=value --param another=val
```

Basics
```bash
mus1 --version          # print version
mus1 -h                 # top-level help
mus1 lab -h             # lab sub-commands
mus1 project -h         # project sub-commands
mus1 scan -h            # scanner sub-commands
```

Projects & shared storage
```bash
# List local or shared projects
mus1 project list
mus1 project list --shared

# Create a project (automatically uses shared storage if lab is active)
mus1 project create my_proj

# Lab-based shared storage configuration
mus1 lab configure-storage --mount-point /Volumes/CuSSD3 --volume-name CuSSD3 --enabled --auto-detect
mus1 lab activate my_lab  # Projects created after this will use shared storage

# Configure per-user shared root (no secrets)
mus1 setup shared --path /mnt/mus1 --create

# Configure per-user local projects root (non-shared)
mus1 setup projects --path ~/MUS1/projects --create

# Bind a project to the shared root and/or move it under that root
mus1 project set-shared-root /path/to/project /mnt/mus1
mus1 project move-to-shared /path/to/project
```

# Lab-based resource management (recommended)
```bash
# All resource management is now done at the lab level
mus1 lab add-worker --name compute-01 --ssh-alias server1
mus1 lab add-target --name local-media --kind local --root ~/Videos
mus1 lab status  # View all lab resources
```

Scanning and ingest
# Media indexing and assignment (New)
```bash
# Scan roots → move files into project/media/subject-YYYYMMDD-hash8/ and register unassigned
mus1 project scan-and-move /path/to/project [roots...] --verify-time

# Index loose files already dropped into project/media (create folders + metadata; register)
mus1 project media-index /path/to/project --provenance scan_and_move

# Iterate unassigned media → set subject and experiment type; optional create+link experiment
mus1 project media-assign /path/to/project \
  --prompt-on-time-mismatch \
  --set-provenance manual_assignment

# CSV-guided assembly examples
# Extract subjects from a folder of CSVs (lab plugin), get YAML with subjects and conflicts, LAB SPECIFIC
mus1 project assembly run /path/to/project \
  -p CopperlabAssembly -a subjects_from_csv_folder \
  --param csv_dir=/path/to/csvs

# Import third-party processed folder (copy by default or move) into media with provenance
mus1 project import-third-party-folder /path/to/project /path/to/source \
  --copy \
  --verify-time \
  --provenance third_party_import
```

# Genotype management
```bash
# Configure genotype systems at lab level
mus1 genotype add-to-lab --gene ATP7B --allele WT --allele Het --allele KO --inheritance recessive --mendelian

# Track genes and experiment types at lab level
mus1 genotype track ATP7B --lab my_lab
mus1 genotype track-exp-type RR --lab my_lab

# List genotype configurations and tracked items
mus1 genotype list --lab my_lab
mus1 genotype list-exp-types --lab my_lab

# Accept lab-tracked genotypes for project use
mus1 genotype accept-lab-tracked ATP7B --project /path/to/project
```

# Lab Resources (use lab commands instead of deprecated credentials commands)
```bash
# All resource management is now done at the lab level
mus1 lab add-credential --alias <ssh_alias> --user myuser
mus1 lab status  # View all lab resources
```

```bash
# Scan arbitrary roots and get JSONL (stdout), then dedup
mus1 scan videos <roots...> | mus1 scan dedup

# Scan and ingest from multiple roots with parallel processing
mus1 project ingest /path/to/project [roots...] \
  --preview \
  --emit-in-shared ~/in.jsonl \
  --emit-off-shared ~/off.jsonl \
  --parallel --max-workers 4

# Stage off-shared files (from JSONL) into shared_root/<subdir> and register
mus1 project stage-to-shared /path/to/project /tmp/all.unique.jsonl recordings/raw

# One-shot ingest: scan → dedup → split by shared → preview or stage+register
# Preview: prints counts and optionally writes JSONL files
mus1 project ingest /path/to/project [roots...] \
  --preview \
  --emit-in-shared ~/in.jsonl \
  --emit-off-shared ~/off.jsonl \
  --parallel --max-workers 4

# Apply: registers in-shared, stages off-shared to dest-subdir, and registers
mus1 project ingest /path/to/project [roots...] \
  --dest-subdir recordings/raw \
  --parallel --max-workers 4
```

Cleanup redundant copies
```bash
# Preview redundant off-shared copies and planned actions
mus1 project cleanup-copies /path/to/project --policy delete --scope non-shared --dry-run

# Archive copies to a specified directory
mus1 project cleanup-copies /path/to/project --policy archive --scope all --archive-dir /data/archive --dry-run false
```

## Shared Projects & Lab-Based Storage

MUS1 supports two approaches for shared storage: lab-based configuration (recommended) and traditional networked storage.

### **Lab-Based Shared Storage (Recommended)**
Configure shared storage at the lab level for automatic project storage management:

```bash
# Configure shared storage for your lab
mus1 lab configure-storage --mount-point /Volumes/CuSSD3 --volume-name CuSSD3 --enabled --auto-detect

# Activate the lab (automatically detects and uses shared storage)
mus1 lab activate copperlab

# Create projects (automatically uses shared storage)
mus1 project create my-experiment  # Stored in /Volumes/CuSSD3/mus1_projects/my-experiment/
```

**Benefits:**
- Automatic detection of mounted drives
- Projects automatically use shared storage when lab is active
- No manual configuration per project
- Works across multiple machines in the same lab

### **Traditional Shared Storage**
For legacy setups or specific requirements:

Setup
- Choose a local mount path on your machine, mount your network share there, and set the environment variable `MUS1_SHARED_DIR` to that mount path. The directory should contain your MUS1 project folders.
- The core saves `project_state.json` using a lightweight advisory lock (`.mus1-lock`) to reduce conflicting writes across machines.

CLI
```bash
# List projects from shared storage
mus1 project list --shared

# Create a project (will automatically use shared storage if lab is active)
mus1 project create my_proj

# Configure per-user shared root (no secrets)
mus1 setup shared --path /mnt/mus1 --create

# Set project shared root and move an existing project under it
mus1 project set-shared-root /path/to/project /mnt/mus1
mus1 project move-to-shared /path/to/project

# Use lab-based scan targets and ingest
mus1 lab add-target --name lab-mac --kind local --root ~/Videos --root /Volumes
mus1 lab add-target --name copper --kind ssh --ssh-alias copperlab-server --root /data/recordings
mus1 project ingest /path/to/project --target lab-mac --target copper --dest-subdir recordings/raw

# Stage off-shared files into shared_root/subdir with hash verification and register
mus1 project stage-to-shared /path/to/project /tmp/all.unique.jsonl recordings/raw
```

GUI
- Project Selection dialog: choose “Shared” to list or create projects on the shared location.
- Project View → Project Settings: use the “Shared” option in the project switcher to switch to projects on shared storage.

Notes
- `MUS1_SHARED_DIR` must be a locally mounted path; MUS1 does not perform mounting. Use your OS’s mount tools (e.g., SMB/NFS/sshfs) prior to launching MUS1.
- On save, `.mus1-lock` is created and removed automatically. If you see a stale lock after a crash, it can be deleted safely once no MUS1 instance is writing.
- Remote scans require MUS1 to be installed on the remote host's PATH (or inside WSL for Windows). Test SSH connectivity via:
  ```bash
  mus1 lab add-worker --name copper --ssh-alias copperlab-server
  ```

### Project folders default (local and shared)

- Local projects directory precedence:
  - `--base-dir` (where supported)
  - `MUS1_PROJECTS_DIR`
  - Per-user config file `config.yaml` under the OS config dir containing `projects_root`
  - Default `~/MUS1/projects`

- Shared projects directory precedence:
  - Explicit argument to APIs/CLI
  - `MUS1_SHARED_DIR`
  - Per-user config file `config.yaml` under the OS config dir containing `shared_root` (set via `mus1 setup shared`)

OS config directory locations:
- macOS: `~/Library/Application Support/mus1/config.yaml`
- Windows: `%APPDATA%/mus1/config.yaml`
- Linux: `$XDG_CONFIG_HOME/mus1/config.yaml` or `~/.config/mus1/config.yaml`

Use:
```bash
# Set shared root
mus1 setup shared --path /Volumes/CuSSD3/mus1-shared --create

# Set default local projects root
mus1 setup projects --path /Volumes/CuSSD3/mus1-projects --create
```

## Lab-Centric Media Organization and Metadata

- Each recording is placed under `project/media/subject-YYYYMMDD-hash8/` and retains the original filename.
- A `metadata.json` is created per recording with fields:
  - `subject_id`, `experiment_type`
  - `file`: `path`, `filename`, `size_bytes`, `last_modified`, `sample_hash` (fast) and optional `full_hash` (on-demand)
  - `times`: `recorded_time` and `recorded_time_source` (csv|mtime|container|manual)
  - `provenance`: `source` label and freeform `notes`
  - `processing_history`: array of stage events
  - `experiment_links`, `derived_files`, `is_master_member`
- `--verify-time` performs a container probe and prefers it only when it differs from mtime.
- All media operations work within the lab context, using lab-level scan targets and workers for distributed processing.

## Getting Started

We recommend using UV for faster, isolated environments. MUS1 is packaged via `pyproject.toml`.

### UV Setup (recommended)
1. Install UV: `pipx install uv` (or `pip install uv`).
2. Clone MUS1:
   ```bash
   git clone <your-mus1-repo-url>
   cd mus-1
   ```
3. Create and activate a virtual environment:
   ```bash
   uv venv .venv
   # Windows:  . .venv/Scripts/activate
   # Unix/Mac: source .venv/bin/activate
   ```
4. Install MUS1 (editable for development):
   ```bash
   uv pip install -e .
   ```
5. Run MUS1:
   ```bash
   mus1 --help
   ```

### Fast dev launcher
Use `dev-launch.sh` to create/update a venv only when `pyproject.toml` changes and run MUS1 immediately:
```bash
./dev-launch.sh --help
./dev-launch.sh gui
```
It ensures an editable install from this checkout and forwards all args to `mus1`.

## Plugin packages (dev installs)

MUS1 discovers plugins via Python entry points (`mus1.plugins`) only. In-tree scanning has been removed from defaults.

- Public (skeleton): install via VCS pin
```bash
pip install -r requirements-plugins.public.txt
```

- Private (Copperlab): clone alongside and install editable via requirements
```bash
# one-time clone of the private repo
gh repo clone llplatil/mus1-assembly-plugin-copperlab .plugins/mus1-assembly-plugin-copperlab

# install the private plugin in editable mode
pip install -r requirements-plugins.private.txt
```

Manage plugins via CLI:
```bash
mus1 plugins list
mus1 plugins install mus1-assembly-skeleton
mus1 plugins uninstall mus1-assembly-skeleton -y
```

Notes:
- Keep plugin source repos outside `src/mus1/plugins/`; install them into the venv so MUS1 can discover them via entry points.
