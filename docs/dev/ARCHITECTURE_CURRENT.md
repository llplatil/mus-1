### MUS1 Architecture — Current State (authoritative)

This document describes how MUS1 works today based on the code, including gaps and quirks.

## Core modules

- ProjectManager (`src/mus1/core/project_manager.py`)
  - Creates/loads/saves projects (`project_state.json`) under `~/MUS1/projects` by default.
  - Discovers plugins by importing every class in `src/mus1/plugins/*.py` that subclasses `BasePlugin` and is concrete; registers them with `PluginManager`.
  - Orchestrates analysis via `run_analysis(experiment_id, capability)`:
    - Looks up the experiment and finds a registered plugin whose `analysis_capabilities()` includes the capability.
    - Calls `plugin.validate_experiment(experiment, project_state)`.
    - Calls `plugin.analyze_experiment(experiment, data_manager, capability)`.
    - On success: stores results under `experiment.analysis_results[capability]` and may advance `processing_stage` to `interpreted` unless capability considered a data-load.
  - Video workflow:
    - `register_unlinked_videos(paths_with_hashes)` populates `ProjectState.unassigned_videos` keyed by `sample_hash`.
    - `link_unassigned_video(hash, experiment_id)` moves a video to `experiment_videos` and updates `ExperimentMetadata.file_ids`.
    - `link_video_to_experiment(experiment_id, video_path, notes)` adds metadata about a file directly to an experiment using `DataManager.compute_sample_hash`.

- PluginManager (`src/mus1/core/plugin_manager.py`)
  - Holds registered plugin instances.
  - Indexes plugins by `readable_data_formats()` and `analysis_capabilities()` for quick lookup.
  - Legacy methods around stages/data sources exist with TODOs; they assume `plugin.get_supported_*()` methods that are not in `BasePlugin` and not implemented by plugins.

- DataManager (`src/mus1/core/data_manager.py`)
  - Generic IO: `read_yaml`, `read_csv`; no `read_hdf` wrapper yet.
  - Settings helpers: `resolve_likelihood_threshold`, `resolve_frame_rate` (reads project/batch/experiment fields).
  - Handler invocation: `call_handler_method(handler_name, method_name, **kwargs)` routes to a registered handler plugin and injects `data_manager` arg if requested by signature.
  - Video discovery: delegates to scanners via `get_scanner().iter_videos(...)`. macOS has a specialized scanner that skips iCloud placeholders; other OSes use `BaseScanner`.

- Metadata models (`src/mus1/core/metadata.py`)
  - Pydantic models for Subjects, Experiments, Batches, Videos, ProjectState.
  - Central stage enum exists, but `ExperimentMetadata.processing_stage` is a free string with default "planned". UI and `run_analysis` advance stages heuristically.
  - `ProjectState` holds videos under both `unassigned_videos` and `experiment_videos`, keyed by `sample_hash`.

## Plugins in repo

- DeepLabCutHandlerPlugin
  - Capabilities: `extract_bodyparts`, `load_tracking_data` (validates source). Public helper `get_tracking_dataframe(file_path, data_manager, likelihood_threshold)` returns a DLC-format DataFrame from CSV/HDF5, optionally applying likelihood filtering.
  - Note: HDF5 path uses `pd.read_hdf`. TODO suggests moving to a DataManager helper. `_apply_likelihood_filter` references `np` but the module does not import numpy; will fail at runtime when thresholding is used.

- Mus1TrackingAnalysisPlugin
  - Capabilities: distance/speed, heatmap, movement plot, time in zones, time near objects, hemisphere analysis, NOR index, OF metrics (partial).
  - Loads tracking data by calling `DataManager.call_handler_method('DeepLabCutHandler', 'get_tracking_dataframe', ...)` and resolves frame rate / likelihood from `DataManager`.
  - OF metrics currently include center time; entries/thigmotaxis are noted as TODO. Contains duplicated internal method names (earlier utility variants and later series-based variants) — later ones override earlier, but duplicates should be removed for clarity.

- SubjectImporterPlugin
  - Project-level importer with `run_import(params, project_manager)`, not `analyze_experiment`. Imports a CSV of subjects, normalizes fields, and calls `ProjectManager.add_subject` per row.

- GcpMoSeq2OrchestratorPlugin
  - A separate orchestrator for uploading videos to GCP, triggering a Cloud Run MoSeq2 job, and downloading results. It references a `DataManager.get_experiment_data_path(...)` helper that does not exist today; needs a DataManager/ProjectManager path helper.

## UI touchpoints (observed)

- ExperimentView dynamically builds forms from plugin `required_fields`/`optional_fields` via `get_field_types()` and `get_field_descriptions()`.
- File dialogs currently use a generic "All Files" filter; a TODO suggests allowing plugins to provide specific filters.
- Metadata display grids implement sort-key aware sorting for experiments; subject grid has a TODO to adopt similar sorting.

## Scanners

- macOS scanner: filters out iCloud placeholders and zero-sized files; uses `compute_sample_hash` per file.
- Windows/Linux: fall back to the base scanner; OS-specific improvements are TODO.

## Known gaps/bugs (current behavior)

- PluginManager stage/source aggregation methods assume plugin methods that do not exist; should be removed or refactored to rely on centralized enums/config.
- DeepLabCutHandler `_apply_likelihood_filter` will raise `NameError` (missing `import numpy as np`).
- GCP MoSeq2 orchestrator uses `DataManager.get_experiment_data_path`, which is not implemented.
- Mus1TrackingAnalysisPlugin contains duplicated private methods; while harmless due to name override rules, they add confusion and risk divergence.
- README doc links point to old paths (`Mus1_Refactor/...`) and claim a Keypoint-MoSeq plugin that’s not present.