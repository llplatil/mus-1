# MUS1 Development Roadmap

This document outlines the planned development roadmap for MUS1, defining milestones and feature targets for upcoming versions.

## Current Phase (v0.1.x -> v0.2.x) - Plugin & Experiment Refactor + Initial kp-MoSeq Integration

### Recently Completed Tasks (2025-08)
* Implemented threaded video-discovery pipeline in DataManager (`discover_video_files`, `deduplicate_video_list`).
* Added `ProjectState.unassigned_videos` plus migration logic.
* Added `ProjectManager.register_unlinked_videos` and `link_unassigned_video` (GUI + CLI share one code path).
* Replaced legacy argparse CLI with Typer‐based app (`mus1`).
* New commands: `mus1 scan videos`, `mus1 scan dedup`, `mus1 project add-videos`, `mus1 project scan-and-add`.
* Rotating log handler per-project (`LoggingEventBus.configure_default_file_handler`).
* GUI `Add Experiment` page now registers/links videos via the unassigned workflow.
* Deleted deprecated scripts (`cli.py`, `scripts/scan_videos.py`, `process_video_list.py`, `index_videos.py`).
* Cleaned up cli_ty.py: integrated notebook code blocks for scan_videos, scan_dedup, and project_scan_and_add; removed unused parameters; used generators for efficiency; eliminated duplicates.
* Added run() function in cli_ty.py to connect with __main__.py.
* Added progress bar to dedup step in project scan-and-add command.
* Cleaned up create_project command to use actual environment variables and remove placeholders.
* Default projects directory standardized to `~/MUS1/projects` (unless overridden by `--base-dir` or `MUS1_PROJECTS_DIR`).
* macOS scanning now uses sensible default roots (`~/Movies`, `~/Videos`, `/Volumes`) when roots are omitted.
* Unified `experiment_videos` keying to `sample_hash` across all code paths (prevents duplicates; consistent lookups).
* Factored file hashing into shared utility `mus1/core/utils/file_hash.py` and updated scanners/DataManager to use it.
* Removed UI widget access from core (`handle_apply_general_settings` → `apply_general_settings(sort_mode,…)`).
* Fixed mutable defaults in metadata models with `Field(default_factory=...)`.
* CLI help text clarified for scan defaults and project creation.
* Added `openpyxl` dependency for Excel import.
* `project add-videos` and `scan-and-add` now report exact number added; `add-videos` honors `start_time` in input.

### Recently Completed Tasks (2025-07)
* ExperimentView plugin-selection split into Importer / Analysis / Exporter lists with collapsible parameter boxes.
* Added "Add Multiple Experiments" page with bulk table entry and save.
* Added support for `text` and `dict` parameter field types.
* DeepLabCut tracking file requirement shifted to stage-aware core validation; UI no longer blocks early stages.
* `ProjectManager.add_experiment` now persists immediately after creation.

### New High-Priority Tasks (Next Sprint)

#### CLI Modernization (Typer Migration ✅ planned)

*Enhancements added after disk-space & editable-install success*

| Milestone | Description |
|-----------|-------------|
| `0.2.0`   | Migrate to Typer, console-script `mus1`, keep legacy stub |
| `0.2.1`   | Add progress bar (`tqdm`) to `scan videos` and hashing steps |
| `0.2.2`   | `mus1 project add-videos` – link videos into **existing** project from a prepared `video_list.txt` (uses ProjectManager) |
| `0.2.3`   | Config file (`mus1.toml`) – default scan roots, exclude patterns, preferred progress settings |
| `0.3.0`   | Remove `scripts/` duplicates; all new CLI functionality lives either in core Typer app or as Typer sub-apps in `plugins/` |

Upcoming tasks:
1. **DataManager.discover_video_files** – adopt new cross-platform scanner architecture:  
   • Extract core traversal logic into `mus1/core/scanners/` with `BaseScanner` plus OS-specific subclasses (`MacOSVideoScanner`, `LinuxVideoScanner`, `WindowsVideoScanner`).  
   • Implement macOS/iCloud placeholder detection to skip `.icloud` stubs and zero-byte files.  
   • `discover_video_files` delegates to `video_discovery.get_scanner()` so GUI, CLI and unit tests share one path.  
   • Provide progress-callback support (`tqdm`).  
   • Add unit tests (macOS stub, Windows hidden files).  
 2. **DataManager.deduplicate_video_list** – hash-based deduplication; yields JSON Lines.
3. **ProjectState.unassigned_videos** – schema update + migration on load.
4. **ProjectManager.register_unlinked_videos / link_unassigned_video** – core ingestion.
5. **CLI**
   * `mus1 scan videos`, `mus1 scan dedup` (Typer sub-app).
   * `mus1 project add-videos` (progress bar, stdin friendly).
   * `mus1 project scan-and-add` (one-shot scan/dedup/add with defaults where appropriate). 
   * Add `--no-progress` and richer `--help` examples where useful. (Planned)
6. **GUI stub** – show count of unassigned videos; simple assignment dialog.
7. Deprecate `scripts/*.py` once Typer commands are stable.
8. CI tests for scanner/dedup and add-videos on Windows & Linux.

1. **Create `mus1/__main__.py` Typer app** exposing the existing sub-commands.
2. **Command grouping**
   * `mus1 scan-videos` → becomes `mus1 scan videos …`
   * `mus1 process-video-list` → `mus1 scan dedup …`
   * `mus1 create-project` & `index-videos` move under `mus1 project …`
3. **Context object** initialises shared managers once and injects into
   sub-commands to avoid slow re-initialisation.
4. **Add console-script entrypoint** in `pyproject.toml` so users type `mus1`
   instead of `python -m Mus1_Refactor.cli`.
5. **Progressive transition** – `cli.py` remains for one minor version; a stub
   will forward to `mus1.__main__` and show a deprecation warning.
6. **Update docs & CI tests** to use the new interface.

1. **Responsibility Separation Refactor**
   * Move video-related helpers (sample-hash, video path suggestion) from `ExperimentView` to `ProjectManager`/`DataManager`.
   * Expose canonical `PROCESSING_STAGES` list from core (StateManager or separate constants module) and have UIs query it.
   * Provide core wrapper for browsing/selecting files so multiple views can reuse.
2. **Plugin Parameter UI Enhancements**
   * Allow collapsible plugin boxes to remember open/closed state per session.
   * Syntax-check `dict` (`JSON`) text fields and highlight errors in red.
3. **Batch & View Pages Update**
   * Migrate View Experiments & Create Batch pages to `MetadataGridDisplay`, showing stage badges.
4. **Documentation & Tests**
   * Update developer docs for new plugin categories and UI flow.
   * Add unit tests for stage-aware validation and bulk experiment creation.
5. **Future Large-Scale Refactor**
   * Ensure UI layers contain *no* business logic – only delegate to core managers.
   * Evaluate signals/slots vs observer pattern consistency across all views.

**Current High-Priority Tasks:**

1.  **`ExperimentView` Refactor**
    *   [x] Implement parameter-driven file handling UI (`'file'`/`'directory'` type widgets). *(Done)*
    *   [x] Update `handle_add_experiment` to collect nested `plugin_params` and infer initial stage. *(Done)*
    *   [x] Update UI layout for Subject -> Type -> Handler/Analysis Plugin lists -> Dynamic Parameters workflow. *(Done for Add Experiment page)*
    *   [x] Implement dynamic plugin list population (`_discover_plugins`) based on capabilities/formats. Filter Handler plugins (`load_tracking_data`) and Analysis plugins separately. *(Done)*
    *   [x] Ensure dynamic parameter form updates correctly based on *all* selected plugins (`update_plugin_fields`). *(Done)*
    *   [ ] Update experiment lists/grids (`View Experiments` page, `Create Batch` page) to use `MetadataGridDisplay` and display `processing_stage` visually. Ensure subject filtering is robust. *(Pending)*
    *   [x] Implement UI-level validation: Disable 'Add' button until all plugin-required fields have values. *(Done)*

2.  **Plugin Implementation & Orchestration**
    *   [x] Implement `ProjectManager.run_analysis` orchestration. *(Done)*
    *   [x] Implement `DeepLabCutHandlerPlugin` fully. *(Done)*
    *   [ ] **Implement `KeypointMoSeqAnalysisPlugin`:** Core logic for kp-MoSeq fitting. *(New High Priority Task)*
    *   [ ] Implement `DlcProjectImporterPlugin`: Finalize DLC project import. *(High Priority Task)*
    *   [x] Refactor `Mus1TrackingAnalysisPlugin` data loading. *(Done)*
    *   [ ] Refine/test analysis algorithms within `Mus1TrackingAnalysisPlugin` (NOR, OF metrics). *(Pending)*
    *   [ ] **Implement `MoSeq2ResultsViewerPlugin`:** Load and extract features from external MoSeq2 `results.h5` files. *(New Medium Priority Task)*
    *   [ ] **Implement Handler Plugins for Tabular Data:** Create/refine handlers for common formats like Rotarod CSVs (`RotarodDataHandlerPlugin`), Biochemical data (`BiochemDataHandlerPlugin`), potentially generalizing to a `CsvDataHandlerPlugin`. *(New Medium Priority Task)*

3.  **Core Support & Cleanup**
    *   [ ] Implement plugin `validate_experiment` methods. *(Refined Scope, Pending)*
    *   [x] Ensure `DataManager` provides necessary helpers. *(Done)*
    *   [ ] **Implement Data Aggregation Script for ML:** Develop an external script to export features and target variables from `ProjectState` into a format suitable for ML model training. *(New Medium Priority Task)*
    *   [ ] Refine QSS rules. *(Pending)*
    *   [ ] Remove remaining legacy methods/fields. *(Refined, Pending)*
    *   [ ] Add migration shim to convert legacy path-keyed `experiment_videos` to `sample_hash` keys on load. *(New)*
    *   [ ] Configure `LoggingEventBus` automatically in CLI flows to avoid "Could not find a FileHandler…" warning. *(New)*
    *   [ ] Implement default scan roots for Windows/Linux (hidden files, removable drives) mirroring macOS defaults. *(New)*
    *   [ ] Add CLI to link unassigned videos to an experiment (`mus1 project link-unassigned <project> --hash <h> --exp <id>`). *(New)*

**Future Tasks (Post-Refactor / v0.3.x +):**

*   [ ] **Analysis & Visualization:**
    *   [ ] Create dedicated "Analysis" tab/view in the UI.
    *   [ ] Implement UI for selecting analysis capabilities.
    *   [ ] **Develop visualization methods for Keypoint-MoSeq results (syllable sequences, probabilities, transitions).** *(Refined)*
    *   [ ] Develop visualization methods for kinematic analysis results (plots, heatmaps).
    *   [ ] Implement batch analysis execution (kinematics & kp-MoSeq) and result aggregation.
*   [ ] **Interoperability & Data Handling:**
    *   [ ] **Enhance Keypoint-MoSeq Integration (e.g., parameter tuning UI, advanced result handling).** *(Refined - was 'Add support')*
    *   [ ] Design and implement data export functionality.
    *   [ ] Add support for SLEAP (new `SleapHandlerPlugin`).
    *   [ ] Develop CSV templates for data import/structuring.
*   [ ] **UI/UX Enhancements:**
    *   [ ] Enhance metadata display components (`View Experiments`, `MetadataGridDisplay`).
    *   [ ] Improve `SubjectView` organization (if needed).
    *   [x] **Finalize body parts/tracked objects list management UI (Simplified in SubjectView, extraction removed).** *(Marked as done/simplified)*
    *   [ ] User preferences/settings panel.
    *   [ ] Implement Labeling Interface/Plugins (e.g., `BaseLabelerPlugin`, `Mus1LabelerPlugin`, `NapariLabelerPlugin`).
*   [ ] **Deployment & Advanced Features:**
    *   [ ] Optional Ubuntu server integration.
    *   [ ] Local inference support (potentially via model files).
    *   [ ] Shared project folder sync on `copperlab-server` (SSH). First target: when a shared project is selected in MUS1, auto-sync metadata/results.
    *   [ ] Multi-machine dev workflow (Mac + `copperlab-server` + `lab-windows`) with consistent project paths.
    *   [ ] Migrate shared storage to NAS with configurable mount path per machine.
    *   [ ] Job orchestration: submit long-running analyses to a cluster/queue from MUS1 (CLI + future GUI button).
*   [ ] **Implement `PredictionPlugin` Framework:** Allow loading pre-trained ML models and running inference within MUS1, storing predictions. *(New Future Task)*

## Shared Projects and Remote Workers (Storage vs Compute)

The goal is to decouple where projects live (storage) from where analyses run (compute). These may be the same machine but are modeled independently for flexibility and reliability.

### Scope and principles
- Single code path for project creation and state: always use `ProjectManager.create_project(project_root, project_name)`.
- No legacy fallbacks or duplicated logic; providers only resolve/validate paths and delegate to core.
- Prefer mounted shares (SMB/NFS) as the single source of truth for shared projects. Avoid implicit copy/sync flows.
- Keep credentials/machine specifics out of the repo; use per-user config under `~/.config/mus1/` and existing `~/.ssh/config`.

### Storage Providers (Shared Projects)
- Introduce a provider interface to support multiple storage backends.
- Base interface (abstract): `StorageProvider`
  - Methods: `resolve_project_path(name) -> Path`, `exists(path) -> bool`, `create_project_dir(path) -> None`, `list_projects() -> list[Path]`, `health_check() -> dict`.
  - Optional: `acquire_lock(path)`, `release_lock(path)` for advisory file locking.
- Initial implementations:
  - `LocalStorageProvider` – current default using `MUS1_PROJECTS_DIR` or `./projects`.
  - `SharedMountStorageProvider` – uses `MUS1_SHARED_DIR` or configured mount path; assumes mount is accessible.
  - `UbuntuServerStorageProvider` – prefers mounted path for reads/writes; may optionally perform remote directory bootstrap via SSH if explicitly enabled in per-user config.
- Project metadata: store provider details for reproducibility, e.g. `project_metadata.storage = {"provider": "shared_mount", "root": "/mnt/mus1/projects", "server": "copperlab-server"}`.

### Worker Providers (Remote Workers)
- Introduce a provider interface for where jobs run.
- Base interface (abstract): `WorkerProvider`
  - Methods: `submit_job(job_spec) -> job_id`, `job_status(job_id) -> dict`, `cancel_job(job_id) -> None`, `health_check() -> dict`.
  - Optional: log streaming support.
- Initial implementations:
  - `LocalProcessWorker` – executes analyses as local subprocesses.
  - `SSHWorker` – executes on a remote host via SSH, leveraging `~/.ssh/config` (e.g., `copperlab-server`).
- Project metadata: default worker, e.g. `project_metadata.default_worker = "ssh:copperlab_ssh"`.

### Configuration
- Per-user, not in repo:
  - `~/.config/mus1/storage.toml`
    - Example:
      - `[storage.shared_mount] type = "shared_mount" root = "/mnt/mus1/projects"`
      - `[storage.copperlab_server] type = "ubuntu_server" mount = "/mnt/mus1" projects_root = "/mnt/mus1/projects" ssh_host = "copperlab-server" allow_ssh_create = true`
  - `~/.config/mus1/workers.toml`
    - Example:
      - `[worker.local] type = "local_process"`
      - `[worker.copperlab_ssh] type = "ssh" host = "copperlab-server" python = "/opt/mus1-env/bin/python"`
- Environment overrides: `MUS1_PROJECTS_DIR`, `MUS1_SHARED_DIR`, `MUS1_SERVER`, `MUS1_SERVER_ROOT`, `MUS1_DEFAULT_WORKER`.

### Specific code edits (next)
- Add provider bases and first implementations:
  - `src/mus1/plugins/storage_base.py`: define `class StorageProvider(Protocol)` with methods above.
  - `src/mus1/plugins/storage_local.py`: `LocalStorageProvider`.
  - `src/mus1/plugins/storage_shared_mount.py`: `SharedMountStorageProvider`.
  - `src/mus1/plugins/storage_ubuntu_server.py`: `UbuntuServerStorageProvider` (mount-first; optional SSH mkdir if enabled in config).
  - `src/mus1/plugins/worker_base.py`: define `class WorkerProvider(Protocol)`.
  - `src/mus1/plugins/worker_local.py`: `LocalProcessWorker`.
  - `src/mus1/plugins/worker_ssh.py`: `SSHWorker`.
- Extend metadata to persist storage/worker selections:
  - `src/mus1/core/metadata.py` (Pydantic models):
    - In `ProjectMetadata`: add `storage: dict | None = None` and `default_worker: str | None = None`.
- Update CLI:
  - `src/mus1/cli_ty.py`:
    - In `project create`: replace `--location` with `--storage <local|shared_mount|ubuntu_server|NAME>` and add `--storage-config` (key=value pairs, repeatable) and `--server` alias for ubuntu server.
    - Resolve provider from config, validate via `health_check()`, call `provider.resolve_project_path(name)`, ensure directory via `provider.create_project_dir(path)`, then `ProjectManager.create_project(path, name)`.
    - Add `job` command group: `submit`, `status`, `cancel`, `tail` using `WorkerProvider`.
- Update GUI:
  - `src/mus1/gui/project_selection_dialog.py`:
    - Add Location dropdown: `Local | Shared (Mounted) | Server`.
    - When creating, resolve path via selected `StorageProvider`; list projects by provider for tabs/sections (Local, Shared). Server listing shown only if mount path available.
- Hardening in core persistence:
  - `src/mus1/core/project_manager.py`:
    - In `save_project()`: implement advisory lock `.mus1-lock` (hostname, PID, timestamp) and atomic write (temp file + fsync + rename). Expose lock state to UIs.

### CLI examples
- Local: `mus1 project create MyLab1 --storage local`
- Shared (mounted): `MUS1_SHARED_DIR=/mnt/mus1/projects mus1 project create MyShared --storage shared_mount`
- Server (mounted): `mus1 project create ColonyA --storage ubuntu_server --server copperlab-server`
- Jobs: `mus1 job submit --project /mnt/mus1/projects/ColonyA --experiment E1 --plugin KeypointMoSeq --capability fit --worker ssh:copperlab_ssh`

### Phased delivery
- Phase 1: Storage providers + CLI integration; metadata fields; mounted-share creation and listing.
- Phase 2: Worker providers + CLI `job` commands; default worker in project metadata.
- Phase 3: GUI location selector, provider-based listing, default worker selector, minimal job status panel.
- Phase 4: Locking + atomic persistence + provider health checks surfaced in GUI.

### Acceptance criteria
- Can create/list projects on a shared mounted path via storage provider and the CLI.
- Project state records storage provider info; no duplicated creation logic.
- Can submit an analysis job to an SSH worker via CLI; status polling works.
- GUI can create/open from Local and Shared (mounted); server-only listing remains disabled unless mount is present.

**Long-term Vision:**
*   Integration with other behavioral analysis platforms.
*   Real-time data input capabilities.
*   Cloud synchronization / enhanced server interaction.
*   Advanced automation and customizable analysis pipelines.
*   Statistical analysis tools.
*   **Robust support for multimodal ML workflows (training data prep and inference integration).** *(Added emphasis)*
*   Comprehensive documentation.

## Current Version (v0.1.0) - Foundation

**Completed Tasks:**

1. **QSS and Theme System**
   - [x] Delete old CSS files (dark.css, light.css)
   - [x] Create unified CSS approach with variable substitution
   - [x] Implement theme switching (dark, light, OS detection)
   - [x] Fix CSS variable consistency 
   - [x] Ensure proper QLabel background styling

2. **UI Component Implementation** 
   - [x] Implement reusable NotesBox component
   - [x] Create consistent layout patterns
   - [x] Standardize margins and spacing
   - [x] Improve ProjectView organization
   - [X] Imrove SubjectView org
   - [ ] finish exeriment view and do a code review w debug
   - add image extraction from video via Deeplavcut plugin and add page to do this under Experiment view 
   - add an analysis tab 
   - attach batching to core
   - think about visulization methods for figures and data 
   

**Current Tasks:**
1. **UI Component Refinement** 
   - [ ] Complete component validation system
   - [ ] Finalize body parts list functionality
   - [ ] Implement plugin-specific styling

2. **Data Processing**
   - [ ] Implement likelihood filter functionality
   - [ ] Add frame rate limiting options
   - [ ] Complete data validation pipeline



**Planned Features:**
- [ ] Comprehensive analysis views for all plugin types
- [ ] Batch analysis execution - labeling by batch would be great too 
- [ ] Enhanced metadata display components
- [ ] Data export functionality
- [ ] User-configurable analysis parameters
- [ ] Optional Ubuntu server integration -set up as plugin module and displayed under project settings


**Planned Features:**
- [ ] Experiment workflow pipeline
- [ ] Enhanced subject tracking
- [ ] Extended plugin system
- [ ] User preferences and settings
- [ ] Google Sheets integration - or just have csv template(s) for mus1 project that projects and data can fit to, i wonder if there is a 3rd party tool we could use, not neccessary to directly integrate into mus 1 we could just have button link or something for now. need to know more about how all this works - ideally how we set up @metadata_view.py would essentially reflect the mus 1 project(s) sheet in compatability and styling where apropriate 


**Planned Features:**
- [ ] Statistical analysis tools
- [ ] Results dashboard
- [ ] Machine learning integration
- [ ] Video analysis enhancements


**Planned Features:**
- [ ] Comprehensive documentation
- [ ] Integration with common lab workflows
- [ ] Performance optimization
- [ ] Multi-experiment correlation tools
- [ ] Batch export and reporting

## Long-term Vision

**Future Enhancements (Post merge to main):**
- Integration with other behavioral analysis platforms
- Real-time data input capabilities
- Cloud synchronization options - really connection to the ubuntu server for training and recordings retrieval
- Advanced automation for data processing
- Customizable analysis pipelines
- Local inference (for labeling would be really nice but idk how managable that is, for tracking for sure, then be able to label extracted frames with all related metadata and other analyis outcomes, including other experiments to work towards a model that can deduce end points from watching mouse experiemnts), server training

