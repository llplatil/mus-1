### MUS1 Roadmap — Authoritative

This roadmap reflects how the code works today and what is planned next. It avoids dates and versions; items are prioritized by impact and risk.

## What works today (observed in code)
- Project lifecycle and persistence via `ProjectManager`; default projects live under `~/MUS1/projects` (env override `MUS1_PROJECTS_DIR`).
- Dynamic plugin discovery and registration from `src/mus1/plugins/*` with `PluginManager` indices by readable formats and capabilities.
- Analysis orchestration: `ProjectManager.run_analysis(experiment_id, capability)` validates via plugin, calls `analyze_experiment`, stores results, and advances `processing_stage` when appropriate.
- Data IO helpers in `DataManager`: `read_yaml`, `read_csv`, `read_hdf`; handler invocation through `call_handler_method`.
- Video discovery and ingestion: pluggable scanners (`macOS` specialized, base for others), `discover_video_files`, `deduplicate_video_list`, and unassigned→assigned workflow using `sample_hash` keys.
- Typer CLI (`mus1`) with commands: `scan videos`, `scan dedup`, `project add-videos`, `project list`, `project create`, `project scan-and-add`.
- UI: `ExperimentView` builds parameter forms from plugin metadata, separates Importer/Analysis/Exporter lists, supports bulk add, and links videos through the unassigned workflow.
- Plugins:
  - `DeepLabCutHandlerPlugin` (handler): extract body parts, validate/ack tracking sources, load DataFrame via helper with optional likelihood thresholding.
  - `Mus1TrackingAnalysisPlugin` (analysis): kinematics, heatmap, zones/objects, NOR index, partial OF metrics; loads tracking data via handler/DataManager.
  - `SubjectImporterPlugin` (project-level import).
  - `GcpMoSeq2OrchestratorPlugin` marked deprecated (kept for reference only).

## Known gaps and quirks (truthful)
- Handler uses likelihood filtering but relies on `numpy`; this is imported in the handler, but ensure it remains imported to avoid runtime NameError in future edits.
- `PluginManager` still exposes legacy “supported_*” shims; keep canonical stage list from metadata and avoid introducing new legacy surfaces.
- `DataManager.get_experiment_data_path` is present; call sites should rely on it (or a central helper) rather than recomputing output paths.
- Windows/Linux scanners currently use the base scanner; OS-specific exclusions and removable drive handling are not implemented.
- `Mus1TrackingAnalysisPlugin` contains duplicated internal method names in places and mixes frame/series APIs; safe but should be tidied for clarity.

## Highest-priority next steps
1) Tighten correctness and remove misleading surfaces
- Remove/retire broken or misleading `PluginManager` aggregators. Keep: canonical stages via metadata and capability/format indices.
- Ensure all docs and UI refer to realistic capabilities; keep MoSeq2 as future server-backed plan, not current capability.

2) Strengthen IO and handler ergonomics
- Keep `DataManager.read_hdf` as the single path for HDF5 DLC reads; plumb structured warnings when non-standard column indexes are detected.
- Add `DataManager.get_experiment_data_path` usage wherever plugins persist outputs.

3) Scanner parity and progress UX
- Implement `WindowsVideoScanner` and `LinuxVideoScanner` with hidden/system file handling and removable drive traversal options.
- File dialog filters provided by plugins (e.g., `*.csv;*.h5`) through field metadata in the UI.

4) Analysis depth and tests
- Extend OF metrics (entries to center, thigmotaxis/perimeter time) with small synthetic tests.
- Add light-weight tests for NOR DI and zone-time on toy trajectories.

5) Code hygiene
- Remove duplicated private helpers in `Mus1TrackingAnalysisPlugin`; consolidate on the series-based implementations.

## Medium-term (architectural enablement)
- Storage/compute providers (mount-first design): local/shared/server storage providers plus local/SSH worker providers; wire into CLI and GUI creation/listing. Persist provider info in project metadata. Advisory lock file and atomic writes on save.
- Project-level data aggregation script (external) to export features and labels for ML training; keep training/inference outside MUS1, but define a minimal “prediction plugin” interface for optional future inference.
- GUI: subject grid gains sort-key aware sorting; basic Analysis tab for capability selection and status.

## Long-term direction
- Robust multimodal workflows (video, MoSeq2 syllables, Rotarod, biochemical CSVs) via dedicated handler/analysis/viewer plugins.
- Optional remote orchestration plugin (SSH/Slurm) for MoSeq2 and heavy jobs; job status and minimal log tailing in CLI/GUI.
- Better distribution: portable builds and UV-based reproducible environments.

## Deprecations and realities
- GCP MoSeq2 orchestrator is deprecated. Treat as reference only; replacement is a server-backed orchestration plugin when provider abstractions land.
- No Keypoint-MoSeq analysis plugin exists today; it is a planned analysis plugin that will consume tracking data via the handler/DataManager path.

## Acceptance snapshots (what “done” means soon)
- CLI and GUI share a single ingestion path; scan→dedup→register unassigned works end-to-end across macOS; parity on Win/Linux scanners.
- Plugins load DLC data through `DataManager.call_handler_method` and return results stored in `ExperimentMetadata.analysis_results` keyed by capability.
- Docs (this file + Architecture) truthfully describe implemented behavior and list gaps explicitly so users aren’t misled.


