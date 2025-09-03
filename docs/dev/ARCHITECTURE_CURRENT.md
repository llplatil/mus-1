### MUS1 Architecture — Current State (authoritative)

This document describes how MUS1 works today based on the code, including gaps and quirks.

## Core modules

 - ProjectManager (`src/mus1/core/project_manager.py`)
  - Creates/loads/saves projects (`project_state.json`) under a local projects root resolved by precedence: (1) explicit argument (where supported), (2) env `MUS1_PROJECTS_DIR`, (3) per-user config `config.yaml` key `projects_root`, (4) default `~/MUS1/projects`.
  - Supports a shared projects root via `get_shared_directory()` resolved by precedence: (1) explicit argument, (2) env `MUS1_SHARED_DIR`, (3) per-user config `config.yaml` key `shared_root`. The shared path must be a locally mounted path. Both CLI and GUI can create/list projects under this shared root.
  - Saves use a lightweight advisory lock file `.mus1-lock` and atomic temp-file rename to reduce concurrent write conflicts on shared storage.
  - Discovers plugins via Python entry points using `PluginManager.discover_entry_points()` (group `mus1.plugins`). Discovery is entry-point only; in-tree scanning has been removed from defaults.
  - Orchestrates analysis via `run_analysis(experiment_id, capability)`:
    - Looks up the experiment and a plugin whose `analysis_capabilities()` includes the capability.
    - Calls `plugin.validate_experiment(experiment, project_state)`.
    - Calls `plugin.analyze_experiment(experiment, data_manager, capability)`.
    - On success: stores results under `experiment.analysis_results[capability]` and advances `processing_stage` to `tracked` for data-load capabilities or `interpreted` for analyses.
  - Video workflow:
    - `register_unlinked_videos(paths_with_hashes)` populates `ProjectState.unassigned_videos` keyed by `sample_hash`.
    - `link_unassigned_video(hash, experiment_id)` moves a video to `experiment_videos` and updates `ExperimentMetadata.file_ids`.
    - `link_video_to_experiment(experiment_id, video_path, notes)` adds metadata about a file directly to an experiment using `DataManager.compute_sample_hash`.
    - `move_project_to_directory(new_parent_dir)` relocates an entire project folder (e.g., local → shared).

- PluginManager (`src/mus1/core/plugin_manager.py`)
  - Holds registered plugin instances.
  - Discovers external plugins via Python entry points (`discover_entry_points`), avoiding in-tree coupling by default.
  - Indexes plugins by `readable_data_formats()` and `analysis_capabilities()` for quick lookup.
  - Provides UI-oriented helpers for importer/analysis/exporter lists. Legacy “supported_*” shims remain but return canonical or empty lists; prefer enums/constants and capability/format indices.

 - DataManager (`src/mus1/core/data_manager.py`)
  - Generic IO: `read_yaml`, `read_csv`, `read_hdf` (DLC-friendly checks/warnings).
  - Settings helpers: `resolve_likelihood_threshold`, `resolve_frame_rate`.
  - Handler invocation: `call_handler_method(handler_name, method_name, **kwargs)` and automatic `data_manager` injection when required.
  - Experiment output paths: `get_experiment_data_path(experiment)` for plugins to persist outputs under `<project>/data/<subject>/<experiment>/`. DataManager is made project-aware via `set_project_root` called by `ProjectManager` on create/load.
  - Video discovery: delegates to scanners via `get_scanner().iter_videos(...)`.
  - Staging: `stage_files_to_shared(src_with_hashes, ...)` now creates per-recording folders under `project/media/subject-YYYYMMDD-hash8/`, writes `metadata.json` (hashes, recorded_time with source, provenance, history), and yields tuples for registration. `--verify-time` prefers container metadata only when it differs from mtime.
  - Cross-target scanning: `project scan-from-targets` aggregates local/SSH/WSL targets, deduplicates, and can preview/emit JSONL.

- Metadata models (`src/mus1/core/metadata.py`)
  - Pydantic models for Subjects, Experiments, Batches, Videos, ProjectState.
  - Central stage enum exists; `ExperimentMetadata.processing_stage` is stored as a string with default "planned".
  - `ProjectState` holds videos under both `unassigned_videos` and `experiment_videos`, keyed by `sample_hash`.
  - Typed fields for multi-machine workflows: `shared_root: Optional[Path]`, `workers: List[WorkerEntry]`, `scan_targets: List[ScanTarget]`.

## Plugins (external packages)

- Handler: `mus1-plugin-deeplabcut-handler` (public)
- Importer: `mus1-plugin-dlc-importer` (public)
- Analysis: `mus1-plugin-tracking-analysis` (public)
- Importer: `mus1-plugin-moseq2-importer` (public)
- Assembly (lab-specific): `mus1-assembly-plugin-copperlab` (private, editable for dev)
- Skeleton: `mus1-assembly-skeleton` (public template)

Notes: In-tree plugin implementations were removed. Only the interface remains under `src/mus1/plugins/base_plugin.py`. Real plugins are external packages discovered via entry points.

## UI touchpoints

- `ExperimentView` dynamically builds forms from plugins’ `required_fields`/`optional_fields` using `get_field_types()` and `get_field_descriptions()`.
- File dialogs use generic filters; allowing plugin-provided filters is a useful enhancement.
- Metadata display grids implement sort-key aware sorting for experiments; subject grid can adopt the same pattern.
- `ProjectView` includes:
  - Project Settings: set `shared_root` and "Move Project to Shared" (uses `ProjectManager.move_project_to_directory`).
  - Scan & Ingest: select targets, scan, view totals/unique/off-shared, add unique under shared, or stage off-shared into a subdirectory under `shared_root`.
  - Workers tab: CRUD for `ProjectState.workers`.
  - Targets tab: CRUD for `ProjectState.scan_targets`.

## Scanners

- macOS scanner: filters out iCloud placeholders and zero-sized files; uses `compute_sample_hash` per file.
- Windows/Linux: specialized scanners are present with conservative exclusions; parity improvements remain planned.
- Remote scanning aggregator (`src/mus1/core/remote_scanner.py`):
  - Local: calls `DataManager.discover_video_files`.
  - SSH: runs remote `mus1 scan videos` via `ssh` and parses JSONL.
  - WSL: runs `wsl.exe -e mus1 scan videos` on Windows hosts over SSH.

## Known gaps/bugs (truthful)

- Prefer canonical stage list from metadata and capability/format indices; avoid legacy `PluginManager` shims. Entry-point discovery is the single discovery path. The CLI exposes `plugins list|install|uninstall` to manage external plugin packages registered via `mus1.plugins`.
- DeepLabCut handler likelihood filtering depends on `numpy`; ensure import stays present to prevent runtime errors.
- Server-backed MoSeq2 orchestration is planned; current GCP-based orchestrator is deprecated.
- `Mus1TrackingAnalysisPlugin` has duplicated private helpers; consolidate to reduce confusion.
- Remote scans require MUS1 installed on remote PATH (or inside WSL); document and validate during setup.
- GUI scan summary is basic; per-target progress and error surfacing are planned.
 - Project-aware CLI commands initialize project logging early; remaining legacy commands may still print a missing FileHandler warning until consolidated.

## Recent CLI additions (0.1.1)
- Root: `mus1 --version` prints the installed MUS1 version.
- Targets: `targets list` uses plain printing to avoid markup issues with paths.
- Project scanning from targets: `--dry-run`, `--emit-in-shared FILE`, and `--emit-off-shared FILE` enable safe preview and export of lists for later staging.
- New: `project ingest` for single-command scan→dedup→split→preview or stage+register.
- Group helps: `mus1 project-help`, `mus1 scan-help`.
 - Parallel scanning: `scan-from-targets` and `ingest` support `--parallel --max-workers`.
 - Auto-host ingest: if `shared_root` isn’t writable on this machine, ingest emits off-shared list for host staging.
 - Setup helpers: `mus1 setup shared` writes `shared_root` to per-user config; `mus1 setup projects` writes `projects_root` to per-user config (used when `MUS1_PROJECTS_DIR` is not set).
 - Plugin helpers: `mus1 plugins list`, `mus1 plugins install`, and `mus1 plugins uninstall` manage external plugins discoverable via entry points (`mus1.plugins`).
 - New: `project assembly` group for plugin-driven project actions:
   - `project assembly list` – list assembly-capable plugins
   - `project assembly list-actions --plugin <name>` – list actions for a plugin
   - `project assembly run --plugin <name> --action <name> [--params-file|-f] [--param KEY=VALUE]` – run an action
   - Example (Copperlab): `subjects_from_csv_folder` returns `{subjects, conflicts}` with 3-digit ID normalization and reconciliation of sex, birth/death dates, genotype, treatment
 - GUI launch is via `mus1-gui` only; the CLI no longer exposes a `gui` subcommand.
