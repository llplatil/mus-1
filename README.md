# MUS1: An Open Source Workflow Integration Platform for Animal Behavior Analysis 

Mus-1 is a Python-based tool with an intuitive UI layer designed to streamline the analysis of subject behavior data allowing multidisciplinary workflows through a plugin based infrastructure. Mus-1 users can integrate multiple 3rd party open source tools within their respective pipline while maintaining data integrity without the hassle of managing import and export workflows from one analysis tool to the next. At its core, Mus-1 is built to accommodate each lab's unique research through its ability to support a variety of workflows and data types either through existing plugins or by developing a plugin that meets one's exact needs as outlined by the documentation provided within the Mus-1 install.

## Overview

MUS1 facilitates a workflow starting from DeepLabCut-generated tracking data, enabling users to:
1. **Import and Organize:** Manage DeepLabCut tracking files, associated videos, and metadata within structured MUS1 projects. Import body part definitions directly from DLC `config.yaml` files.
2. **Analyze Kinematics:** Perform foundational analyses like distance, speed, and zone occupancy using built-in analysis plugins.
3. **Manage Experiments:** Organize experiments by subject, type, and batch, tracking processing stages.
4. **Standardize:** Apply consistent analysis parameters and project settings.

The project uses a modular architecture with plugins for data handling (e.g., DeepLabCut outputs) and analysis (e.g., kinematics).

## Features

- **Material Design UI**: Clean, modern interface built with PySide6-Qt.
- **Project Management**: Centralized handling of subjects, experiments, metadata, and analysis results.
- **DeepLabCut Integration**: Imports body parts from DLC configs and utilizes DLC tracking data (CSV/HDF5).
- **Plugin Architecture**: Supports data handlers (DLC) and various analysis modules (e.g., kinematics).
- **Hierarchical Experiment Setup**: Step-by-step workflow linking data files and analysis parameters.
- **Batch Processing**: Group experiments for efficient management (analysis planned).
- **Observer Pattern**: UI components update automatically based on project state changes.
- **Theme System**: Light/dark themes with OS detection.

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
```

GUI
- Project Selection dialog: choose “Shared” to list or create projects on the shared location.
- Project View → Project Settings: use the “Shared” option in the project switcher to switch to projects on shared storage.

Notes
- `MUS1_SHARED_DIR` must be a locally mounted path; MUS1 does not perform mounting. Use your OS’s mount tools (e.g., SMB/NFS/sshfs) prior to launching MUS1.
- On save, `.mus1-lock` is created and removed automatically. If you see a stale lock after a crash, it can be deleted safely once no MUS1 instance is writing.

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
   # or
   python -m mus1.main
   ```

### Alternative: pip/Conda
```bash
pip install -e .
```

## Future Goals
- Enhanced visualization for kinematic and Keypoint-MoSeq results within MUS1.
- Batch analysis execution for both kinematics and Keypoint-MoSeq syllables.
- Statistical comparison tools for syllable usage across groups.
- Streamlined export of MUS1/kp-MoSeq results.
- Potential integration with labeling workflows (Long-term).
- Enhanced visualization for kinematic results within MUS1.
- Batch analysis execution.
- Statistical comparison tools.
- Streamlined export of results.
- Server-backed MoSeq2 orchestration plugin (planned).



