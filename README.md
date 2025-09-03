# MUS1: An Open Source Workflow Integration Platform for Animal Behavior Analysis 

Mus-1 is a Python-based tool with an intuitive UI layer designed to streamline the analysis of subject behavior data allowing multidisciplinary workflows through a plugin based infrastructure. Mus-1 users can integrate multiple 3rd party open source tools within their respective pipline while maintaining data integrity without the hassle of managing import and export workflows from one analysis tool to the next. At its core, Mus-1 is built to accommodate each lab's unique research through its ability to support a variety of workflows and data types either through existing plugins or by developing a plugin that meets one's exact needs as outlined by the documentation provided within the Mus-1 install.

## Overview

MUS1 facilitates a workflow starting from recordings, csv files and some proccessed tracking data, enabling users to:
1. **Import and Organize:** Manage tracking files, associated videos, and metadata within structured MUS1 projects. Import body part definitions directly from DLC `config.yaml` files with the DeepLabCutHandlerPlugin.
2. **Analyze Kinematics:** Perform foundational analyses like distance, speed, and zone occupancy using built-in analysis plugins.
3. **Manage Experiments:** Organize experiments by subject, type, and batch, tracking processing stages.
4. **Standardize:** Apply consistent analysis parameters and project settings.

The project uses a modular architecture with plugins for data handling (e.g., DeepLabCut outputs) and analysis (e.g., kinematics).

## Features

- **Material Design UI**: Clean, modern interface built with PySide6-Qt.
- **Project Management**: Centralized handling of subjects, experiments, metadata, and analysis results.
- **DeepLabCut Integration**: Imports body parts from DLC configs and utilizes DLC tracking data (CSV/HDF5).
- **Plugin Architecture**: Supports data handlers (DLC), importers, and analysis modules (e.g., kinematics). Plugins are discovered via Python entry points (`mus1.plugins`).
- **Hierarchical Experiment Setup**: Step-by-step workflow linking data files and analysis parameters.
- **Batch Processing**: Group experiments for efficient management (analysis planned).
- **Observer Pattern**: UI components update automatically based on project state changes.
- **Theme System**: Light/dark themes with OS detection.
- **Per-recording Media Folders (New)**: Each recording lives in its own folder under `project/media/subject-YYYYMMDD-hash8/` with a `metadata.json` tracking `subject_id`, `experiment_type`, hashes, times, provenance, and processing history.

## Intended Workflow

1.  **Tracking (External)**: Use **DeepLabCut** (installed separately) to track keypoints from your experimental videos. Generate tracking CSV/HDF5 files.
2.  **MUS1 Project Setup**: Create a new project in MUS1.
3.  **Import DLC Config (Optional)**: Use the `DlcProjectImporter` plugin within MUS1 to populate the project's master body part list from your DLC project's `config.yaml`.
4.  **Define Experiments in MUS1**: Add subjects and experiments. Use the `DeepLabCutHandler` plugin parameters to link each experiment to its corresponding DLC tracking file (CSV/HDF5).
5.  **Run Kinematic Analysis (MUS1)**: Use the `Mus1TrackingAnalysis` plugin via the MUS1 interface to calculate metrics like distance, speed, zone time, etc. Results are stored within the experiment's metadata.
6.  **Future**: MoSeq2/Keypoint-MoSeq orchestration and feature extraction are planned via a dedicated plugin (see Roadmap). The current GCP orchestrator is deprecated in favor of a future server-backed integration.

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

# Assembly (generic, plugin-discovered)
```bash
# List assembly-capable plugins and their actions, lab specific
mus1 project assembly list
mus1 project assembly list-actions CopperlabAssembly

# Run an action with YAML params or KEY=VALUE pairs
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
mus1 project -h         # project sub-commands
mus1 scan -h            # scanner sub-commands
mus1 project-help       # show full help for project group
mus1 scan-help          # show full help for scan group
```

Projects & shared storage
```bash
# List local or shared projects
mus1 project list                    
mus1 project list --shared

# Create a project (local or shared)
mus1 project create my_proj                          
mus1 project create my_shared --location shared      

# Configure per-user shared root (no secrets)
mus1 setup shared --path /mnt/mus1 --create

# Configure per-user local projects root (non-shared)
mus1 setup projects --path ~/MUS1/projects --create

# Bind a project to the shared root and/or move it under that root
mus1 project set-shared-root /path/to/project /mnt/mus1
mus1 project move-to-shared /path/to/project
```

Targets and workers
```bash
# Targets represent scan roots per-machine (local/ssh/wsl)
mus1 targets list   /path/to/project
mus1 targets add    /path/to/project --name this-machine --kind local --root ~/Videos --root /media/T7
mus1 targets remove /path/to/project <name>

# Workers represent remote execution endpoints (optional)
mus1 workers list   /path/to/project
mus1 workers add    /path/to/project --name ubuntu --ssh-alias lab-ubuntu --test
mus1 workers run    /path/to/project --name ubuntu -- echo hello
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
# 1) Extract subjects from a folder of CSVs (lab plugin), get YAML with subjects and conflicts, LAB SPECIFIC
mus1 project assembly run /path/to/project \
  -p CopperlabAssembly -a subjects_from_csv_folder \
  --param csv_dir=/path/to/csvs

# 2) (Legacy) assembly-scan-by-experiments remains for now but is deprecated in favor of assembly run
mus1 project assembly-scan-by-experiments /path/to/project CSV1 [CSV2 ...] \
  --roots /Volumes/Data ~/Videos \
  --verify-time \
  --provenance assembly_guided_import

# Import third-party processed folder (copy by default or move) into media with provenance
mus1 project import-third-party-folder /path/to/project /path/to/source \
  --copy \
  --verify-time \
  --provenance third_party_import
```

# Master media list (New)
```bash
# Accept current project's media as the lab master list (stored at the configured projects root under master_media_index.json)
mus1 master-accept-current /path/to/project

# Add unique items from another project's media to the master list
mus1 master-add-unique /path/to/other_project
```

# Credentials (New)
```bash
mus1 credentials-set <ssh_alias> --user myuser --identity-file ~/.ssh/id_ed25519
mus1 credentials-list
mus1 credentials-remove <ssh_alias>
```

```bash
# Scan arbitrary roots and get JSONL (stdout), then dedup
mus1 scan videos <roots...> | mus1 scan dedup

# Aggregate scans from configured targets, dedup, and register items under shared
# (preview only; do not register; write JSONL lists for review)
mus1 project scan-from-targets /path/to/project \
  --dry-run \
  --emit-in-shared ~/in.jsonl \
  --emit-off-shared ~/off.jsonl

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

## Shared Projects (Networked storage)

MUS1 supports keeping projects on a shared network location so multiple machines can access the same project state.

Setup
- Choose a local mount path on your machine, mount your network share there, and set the environment variable `MUS1_SHARED_DIR` to that mount path. The directory should contain your MUS1 project folders.
- The core saves `project_state.json` using a lightweight advisory lock (`.mus1-lock`) to reduce conflicting writes across machines.

CLI
```bash
# List projects from shared storage
mus1 project list --shared

# Create a project on shared storage
mus1 project create my_proj --location shared

# Configure per-user shared root (no secrets)
mus1 setup shared --path /mnt/mus1 --create

# Set project shared root and move an existing project under it
mus1 project set-shared-root /path/to/project /mnt/mus1
mus1 project move-to-shared /path/to/project

# Define scan targets and aggregate scans
mus1 targets add /path/to/project --name lab-mac --kind local --root ~/Videos --root /Volumes
mus1 targets add /path/to/project --name copper --kind ssh --ssh-alias copperlab-server --root /data/recordings
mus1 project scan-from-targets /path/to/project --target lab-mac --target copper

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
  mus1 workers add /path/to/project --name copper --ssh-alias copperlab-server --test
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

## New Media Organization and Metadata (Dev)

- Each recording is placed under `project/media/subject-YYYYMMDD-hash8/` and retains the original filename.
- A `metadata.json` is created per recording with fields:
  - `subject_id`, `experiment_type`
  - `file`: `path`, `filename`, `size_bytes`, `last_modified`, `sample_hash` (fast) and optional `full_hash` (on-demand)
  - `times`: `recorded_time` and `recorded_time_source` (csv|mtime|container|manual)
  - `provenance`: `source` label and freeform `notes`
  - `processing_history`: array of stage events
  - `experiment_links`, `derived_files`, `is_master_member`
- `--verify-time` performs a container probe and prefers it only when it differs from mtime.
- Pattern-based master naming is deprecated; folder-based layout is enforced.

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
