### MUS1 Roadmap — Clean Draft

No dates, versions, or estimates. Concrete, code-aligned.

## Completed (observed in code)

- Core orchestration
  - `ProjectManager.run_analysis` implemented; validates via plugin, executes, stores results, advances stage.
  - Dynamic plugin discovery and registration from `src/mus1/plugins`.
- Data IO & scanners
  - `DataManager.read_yaml`, `read_csv`, settings resolution helpers.
  - macOS video scanner (skips iCloud placeholders); base scanner for other OSes.
  - Video ingestion workflow: `register_unlinked_videos`, `link_unassigned_video`, and direct `link_video_to_experiment` using `compute_sample_hash`.
- Plugins
  - `DeepLabCutHandlerPlugin`: `extract_bodyparts`, `load_tracking_data`, and `get_tracking_dataframe` helper with likelihood filtering.
  - `Mus1TrackingAnalysisPlugin`: implemented capabilities for kinematic and zone/object analyses; NOR index; partial OF metrics.
  - `SubjectImporterPlugin`: project-level CSV import.
- UI
  - Experiment form auto-builds plugin parameter widgets from `get_field_types`/`get_field_descriptions`.
  - Grid sorting for experiments with raw sort keys.

## Carried-over ideas (pruned & de-duplicated)

- Scanner coverage for Windows/Linux (parity features; hidden/system file handling; removable drives).
- DataManager `read_hdf` helper to centralize HDF5 IO.
- Experiment UI: plugin-provided file filters for file dialogs.
- Metadata grids: adopt sort-key aware sorting for subjects.
- PluginManager cleanup: remove stage/source aggregation methods that assume non-existent plugin APIs.
- Path helpers: add `DataManager` or `ProjectManager` helper for experiment data output paths used by plugins.
- Clean duplicated private methods in `Mus1TrackingAnalysisPlugin`.

## Ranked next actions (highest impact/least risk first)

1) Fix real runtime errors
- Add `import numpy as np` in `DeepLabCutHandlerPlugin` (likelihood filtering).
- Provide `DataManager.get_experiment_data_path(experiment)` or equivalent; update GCP plugin to use it.

2) Remove misleading/unused APIs
- Delete or refactor `PluginManager.get_supported_processing_stages/get_supported_data_sources/get_supported_arena_sources` to rely on centralized enums/constants.

3) HDF5 IO consistency
- Implement `DataManager.read_hdf(path, key='df_with_missing')` with robust error handling and column structure checks; update handler to use it.

4) Scanner parity
- Implement `WindowsVideoScanner` and `LinuxVideoScanner` with OS-specific exclusions and device handling; keep interface parity with macOS.

5) UI fidelity & ergonomics
- Let plugins supply file filters (e.g., `*.csv;*.h5`) via `get_field_types`/metadata and pass them to `QFileDialog`.
- Add sort-key aware subject grid to match experiments.

6) Analysis depth
- Extend OF metrics (entries, thigmotaxis, perimeter time); add tests with simple synthetic trajectories.

7) Code hygiene
- Remove duplicate private methods in `Mus1TrackingAnalysisPlugin`; keep the series-based set.

## Notes
- Keypoint-MoSeq: No analysis plugin exists in repo; a GCP MoSeq2 orchestrator is present but needs a data-path helper. Treat kp-MoSeq analysis as a future plugin task, separate from orchestrator.

## Direction on MoSeq2 orchestration
- Deprecate the GCP-based orchestrator (kept for reference).
- Design a server-backed (e.g., Slurm) MoSeq2 orchestration plugin that:
  - Prepares uniquely identified MKV inputs for MoSeq2 extraction.
  - Uses canonical experiment output paths (`DataManager.get_experiment_data_path`).
  - Integrates with future server provider abstractions (local process, SSH, Slurm).