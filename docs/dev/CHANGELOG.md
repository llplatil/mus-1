### Changelog

This changelog summarizes edits in response to the annotation audit and roadmap alignment.

## Removed/deprecated annotations and code
- ProjectManager.add_experiment: deleted outdated TODO about plugin-specific validation at add-time (validation runs in `run_analysis`).
- PluginManager:
  - Replaced broken stage aggregation with canonical list from `metadata.DEFAULT_PROCESSING_STAGES`.
  - Marked data source and arena source aggregators as deprecated shims returning empty lists.
  - Simplified compatibility helpers to use canonical stages and return empty data sources.
- Docs: marked `docs/dev/Architecture.md` and `docs/dev/ROADMAP.md` as superseded; pointed to new authoritative documents.

Reason: Remove misleading/stale hooks and align with current design (capabilities-based filtering, central stage list).

## Bug fixes and helpers
- DataManager:
  - Added `read_hdf(path, key='df_with_missing')` with structure warnings.
  - Added `get_experiment_data_path(experiment)` to standardize plugin output locations.
- DeepLabCutHandlerPlugin:
  - Added `import numpy as np` for likelihood filtering helper.
  - Switched HDF5 reading to `data_manager.read_hdf`.

Reason: Prevent runtime errors (NameError on np), centralize IO, and support plugins needing canonical paths.

## Documentation updates
- Added `docs/dev/ARCHITECTURE_CURRENT.md`: authoritative, current architecture reflecting actual code.
- Added `docs/dev/ROADMAP_DRAFT.md`: cleaned, de-dated roadmap with ranked next actions and MoSeq2 orchestration direction.
- Added `docs/dev/ANNOTATION_AUDIT.md`: lists deletable vs. incorrect annotations and relevant TODOs.
- README updates:
  - Removed unimplemented Keypoint-MoSeq plugin claims.
  - Updated doc links to `docs/dev/ARCHITECTURE_CURRENT.md` and `docs/dev/ROADMAP_DRAFT.md`.
  - Noted that GCP MoSeq2 orchestrator is deprecated in favor of future server-backed integration.
- GCP MoSeq2 orchestrator plugin: added module-level deprecation note.

Reason: Ensure docs are truthful, point to the correct sources, and reflect future direction.

## Impact
- Plugins/UI relying on PluginManager stage/source aggregators should migrate to the canonical stage list and capability/format indices; no such usages were found in repo.
- DLC handler uses centralized HDF5 IO; behavior unchanged except better errors/warnings.
- Orchestrator plugin remains but is deprecated; roadmap defines the replacement approach (server-backed orchestration).