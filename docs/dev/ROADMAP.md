# MUS1 Development Roadmap

This document outlines the planned development roadmap for MUS1, defining milestones and feature targets for upcoming versions.

## Current Phase (v0.1.x -> v0.2.x) - Plugin & Experiment Refactor + Initial kp-MoSeq Integration

### Recently Completed Tasks (2025-08)
* Implemented threaded video-discovery pipeline in DataManager (`discover_video_files`, `deduplicate_video_list`).
* Added `ProjectState.unassigned_videos` plus migration logic.
* Added `ProjectManager.register_unlinked_videos` and `link_unassigned_video` (GUI + CLI now share ingestion path).
* Replaced legacy argparse CLI with Typer‐based app (`mus1`).
* New commands: `mus1 scan videos`, `mus1 scan dedup`, `mus1 project add-videos`.
* Rotating log handler per-project (`LoggingEventBus.configure_default_file_handler`).
* GUI `Add Experiment` page now registers/links videos via the unassigned workflow.
* Deleted deprecated scripts (`cli.py`, `scripts/scan_videos.py`, `process_video_list.py`, `index_videos.py`).

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
1. **DataManager.discover_video_files** – move scanning logic from `scripts/scan_videos.py` (✅ code draft exists).  Add progress‐callback support.
2. **DataManager.deduplicate_video_list** – hash-based deduplication; yields JSON Lines.
3. **ProjectState.unassigned_videos** – schema update + migration on load.
4. **ProjectManager.register_unlinked_videos / link_unassigned_video** – core ingestion.
5. **CLI**
   * `mus1 scan videos`, `mus1 scan dedup` (Typer sub-app).
   * `mus1 project add-videos` (progress bar, stdin friendly).
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

