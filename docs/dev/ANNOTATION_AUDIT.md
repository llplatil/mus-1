### MUS1 Annotation & TODO Audit

This audit classifies annotations across the codebase into:
- Deletable annotations (stale or redundant)
- Incorrect/out-of-date annotations (disagree with current code behavior or interfaces)
- Relevant TODOs (actionable items worth keeping)

Each item includes brief reasoning and an exact file reference.

---

## Deletable annotations

- src/mus1/core/project_manager.py:354-360
  - Text: "# TODO: Consider adding plugin-specific validation call here later" (with example loop)
  - Reason: Plugin validation is already performed centrally in `run_analysis()` before execution. Duplicating validation at `add_experiment` time would add latency and partial-context checks. Remove to avoid confusion and double work.

- src/mus1/core/plugin_manager.py:157-164
  - Text: Docstring/inline message “DEPRECATED?” in `get_plugins_by_criteria`
  - Reason: The function warns it “may be deprecated” and the codebase already prefers format/capability filtering. Either remove the method or keep but mark clearly as deprecated in docstrings; the inline question can be deleted.

---

## Incorrect or out-of-date annotations

- src/mus1/core/plugin_manager.py:85-113, 117-131
  - Text: "# TODO: Review relevance" on methods `get_supported_processing_stages`, `get_supported_data_sources`, `get_supported_arena_sources`; callers iterate `plugin.get_supported_*()`
  - Reason: `BasePlugin` does not define these methods and no plugin implements them. These utilities are currently broken if called. Replace with a centralized stage list (already exists in `metadata.py`) and remove the others, or extend the plugin interface—current TODO minimizes the real issue.

- docs/dev/Architecture.md:349-356 (and similar “Outstanding Tasks” bullets)
  - Text: “Implement ProjectManager.run_analysis …” and “Implement DeepLabCutHandlerPlugin …” as high-priority outstanding tasks
  - Reason: Both are already implemented in code (`ProjectManager.run_analysis`, `DeepLabCutHandlerPlugin` with working capabilities and helpers). The doc is out-of-date; move these to “done” in the doc or remove from “outstanding”.

- README.md:49-52 (Documentation links)
  - Text: Links to `Mus1_Refactor/refactor notes/ROADMAP.md` and `Architecture.md`
  - Reason: Actual docs live under `docs/dev/`. These links are wrong; update to `docs/dev/ROADMAP.md` and `docs/dev/Architecture.md`.

- README.md:21-23 (Feature claims)
  - Text: “Includes a plugin to run Keypoint-MoSeq analysis directly within the MUS1 environment.”
  - Reason: There is no `KeypointMoSeqAnalysisPlugin` in the repo. A GCP MoSeq2 orchestrator exists, but it’s not the same. The claim should be revised to “planned” or point to the orchestrator.

---

## Relevant TODOs to keep (actionable)

- src/mus1/plugins/Mus1TrackingAnalysisPlugin.py:393
  - Text: “TODO: Implement other OF metrics like entries, thigmotaxis”
  - Reason: OF metrics are partially implemented (center time). Extending metrics is a clear next step.

- src/mus1/core/scanners/video_discovery.py:12-16
  - Text: “TODO: Implement WindowsVideoScanner / LinuxVideoScanner”
  - Reason: Only macOS has a specialized scanner; Windows/Linux fall back to the base scanner. Implementing OS-specific behavior is valuable.

- src/mus1/plugins/DeepLabCutHandlerPlugin.py:155-156
  - Text: “TODO: Consider adding a DataManager.read_hdf helper”
  - Reason: DataManager currently offers `read_yaml`/`read_csv`. A `read_hdf` wrapper would align IO patterns and centralize error handling.

- src/mus1/plugins/base_plugin.py:118-121
  - Text: “TODO: Review if this is still the primary way to filter…” for `get_supported_experiment_types`
  - Reason: Still used by UI for discovery alongside capabilities. Keep until type/capability filtering is fully unified.

- src/mus1/gui/experiment_view.py:1296-1299
  - Text: “TODO: Could potentially get specific file filters from plugin?”
  - Reason: File dialogs could use plugin-provided filters (e.g., *.csv, *.h5). Good, bounded UX improvement.

- src/mus1/gui/metadata_display.py:403-405
  - Text: “TODO: Update this method if enhanced sorting is needed for subjects”
  - Reason: The grid has advanced sorting for experiments; subjects view could adopt the same pattern.

---

## Extra: Suspicious code hotspots found during audit (worth promoting to TODOs)

- src/mus1/plugins/DeepLabCutHandlerPlugin.py:_apply_likelihood_filter
  - Issue: Uses `np` but file does not import numpy. This will raise `NameError` on thresholding HDF. Add `import numpy as np` or avoid direct use.

- src/mus1/plugins/GcpMoSeq2OrchestratorPlugin.py:226
  - Issue: Calls `data_manager.get_experiment_data_path(...)`, which does not exist in `DataManager`. Add a helper in `DataManager` (e.g., `get_experiment_data_path(experiment) -> Path`) or change the plugin to derive paths via `ProjectManager`.

- src/mus1/plugins/Mus1TrackingAnalysisPlugin.py
  - Issue: Duplicate method names (`_get_bodypart_columns`, `_calculate_nor_di`) are defined twice; later definitions override earlier ones. Clean up duplicates to avoid confusion.