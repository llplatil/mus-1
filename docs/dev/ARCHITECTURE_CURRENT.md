### MUS1 Architecture — Current State (authoritative)

This document describes how MUS1 works today based on the code, including gaps and quirks.

## Core modules

- ProjectManager (`src/mus1/core/project_manager.py`)
  - Creates/loads/saves projects (`project_state.json`) under `~/MUS1/projects` by default (overridable via `MUS1_PROJECTS_DIR`).
  - Supports a shared projects root via `get_shared_directory()` resolved from `MUS1_SHARED_DIR` (must be a locally mounted path). Both CLI and GUI can create/list projects under this shared root.
  - Saves use a lightweight advisory lock file `.mus1-lock` to reduce concurrent write conflicts on shared storage.
  - Discovers plugins by importing classes in `src/mus1/plugins/*.py` that subclass `BasePlugin` and are concrete; registers them with `PluginManager`.
  - Orchestrates analysis via `run_analysis(experiment_id, capability)`:
    - Looks up the experiment and a plugin whose `analysis_capabilities()` includes the capability.
    - Calls `plugin.validate_experiment(experiment, project_state)`.
    - Calls `plugin.analyze_experiment(experiment, data_manager, capability)`.
    - On success: stores results under `experiment.analysis_results[capability]` and advances `processing_stage` to `tracked` for data-load capabilities or `interpreted` for analyses.
  - Video workflow:
    - `register_unlinked_videos(paths_with_hashes)` populates `ProjectState.unassigned_videos` keyed by `sample_hash`.
    - `link_unassigned_video(hash, experiment_id)` moves a video to `experiment_videos` and updates `ExperimentMetadata.file_ids`.
    - `link_video_to_experiment(experiment_id, video_path, notes)` adds metadata about a file directly to an experiment using `DataManager.compute_sample_hash`.

- PluginManager (`src/mus1/core/plugin_manager.py`)
  - Holds registered plugin instances.
  - Indexes plugins by `readable_data_formats()` and `analysis_capabilities()` for quick lookup.
  - Provides UI-oriented helpers for importer/analysis/exporter lists. Legacy “supported_*” shims remain but return canonical or empty lists; prefer enums/constants and capability/format indices.

- DataManager (`src/mus1/core/data_manager.py`)
  - Generic IO: `read_yaml`, `read_csv`, `read_hdf` (DLC-friendly checks/warnings).
  - Settings helpers: `resolve_likelihood_threshold`, `resolve_frame_rate`.
  - Handler invocation: `call_handler_method(handler_name, method_name, **kwargs)` and automatic `data_manager` injection when required.
  - Experiment output paths: `get_experiment_data_path(experiment)` for plugins to persist outputs under `<project>/data/<subject>/<experiment>/`.
  - Video discovery: delegates to scanners via `get_scanner().iter_videos(...)`. macOS has a specialized scanner that skips iCloud placeholders; other OSes use the base scanner for now.

- Metadata models (`src/mus1/core/metadata.py`)
  - Pydantic models for Subjects, Experiments, Batches, Videos, ProjectState.
  - Central stage enum exists; `ExperimentMetadata.processing_stage` is stored as a string with default "planned".
  - `ProjectState` holds videos under both `unassigned_videos` and `experiment_videos`, keyed by `sample_hash`.

## Plugins in repo

- DeepLabCutHandlerPlugin (handler)
  - Capabilities: `extract_bodyparts`, `load_tracking_data`.
  - Public helper `get_tracking_dataframe(file_path, data_manager, likelihood_threshold)` returns DLC DataFrame from CSV/HDF5 with optional likelihood filtering.

- Mus1TrackingAnalysisPlugin (analysis)
  - Capabilities: distance/speed, heatmap, movement plot, time in zones, time near objects, hemisphere analysis, NOR index, OF metrics (partial).
  - Loads tracking data via `DataManager.call_handler_method('DeepLabCutHandler', 'get_tracking_dataframe', ...)` and resolves frame rate/likelihood from `DataManager`.

- SubjectImporterPlugin (project-level)
  - Imports subject CSV and creates `SubjectMetadata` entries via `ProjectManager`.

- GcpMoSeq2OrchestratorPlugin (deprecated)
  - Retained for reference; slated to be replaced by a server-backed orchestration approach.

## UI touchpoints

- `ExperimentView` dynamically builds forms from plugins’ `required_fields`/`optional_fields` using `get_field_types()` and `get_field_descriptions()`.
- File dialogs use generic filters; allowing plugin-provided filters is a useful enhancement.
- Metadata display grids implement sort-key aware sorting for experiments; subject grid can adopt the same pattern.

## Scanners

- macOS scanner: filters out iCloud placeholders and zero-sized files; uses `compute_sample_hash` per file.
- Windows/Linux: use the base scanner; OS-specific improvements are planned.

## Known gaps/bugs (truthful)

- Prefer canonical stage list from metadata and capability/format indices; phase out legacy `PluginManager` shims.
- DeepLabCut handler likelihood filtering depends on `numpy`; ensure import stays present to prevent runtime errors.
- Server-backed MoSeq2 orchestration is planned; current GCP-based orchestrator is deprecated.
- `Mus1TrackingAnalysisPlugin` has duplicated private helpers; consolidate to reduce confusion.
