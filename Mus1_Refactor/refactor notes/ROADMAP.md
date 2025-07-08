# MUS1 Development Roadmap

This document outlines the planned development roadmap for MUS1, defining milestones and feature targets for upcoming versions.

## Current Phase (v0.1.x -> v0.2.x) - Plugin & Experiment Refactor + Initial kp-MoSeq Integration

**Recently Completed Tasks:**

1.  **Plugin Architecture Overhaul**
    *   [x] Shifted from experiment-type plugins to tool-based plugins.
    *   [x] Created `Mus1TrackingAnalysisPlugin` consolidating NOR/OF/basic analysis logic.
    *   [x] Renamed DLC plugin to `DeepLabCutHandlerPlugin` focusing on format handling.
    *   [x] Added `readable_data_formats` and `analysis_capabilities` concepts to plugins.
    *   [x] Refactored `BasePlugin` (updated signatures, added abstract methods).
    *   [x] Refactored `PluginManager` (new filtering, removed analysis/validation/styling methods).
    *   [x] Added interpolation (`handle_gaps`) to `Mus1TrackingAnalysisPlugin`.
    *   [x] Added `run_project_level_plugin_action` and refined `update_master_body_parts` in `ProjectManager`.
    *   [x] Drafted `DlcProjectImporterPlugin` structure.
    *   [x] Outlined plan for integrating Keypoint-MoSeq as a MUS1 plugin.
    *   [x] Drafted `KeypointMoSeqAnalysisPlugin` skeleton structure.
    *   [x] Updated `README.md` and `requirements.txt` for kp-MoSeq integration.
    *   [x] Implemented `ProjectManager.run_analysis` orchestration logic.
    *   [x] **Implemented Data Loading via DataManager/Handler Helpers:** Refactored data loading so analysis plugins call `DataManager.call_handler_method`, which finds the correct Handler plugin (e.g., `DeepLabCutHandler`) and executes its public helper method (e.g., `get_tracking_dataframe`) to load and process data (including likelihood filtering).

2.  **Styling Unification & Experiment Stages**
    *   [x] Centralized styling in `mus1.qss` and `ThemeManager`.
    *   [x] Removed complex plugin-specific styling methods (`get_styling_preferences`, etc.).
    *   [x] Implemented consistent styling for experiment `processing_stage` via QSS property.
    *   [x] Implemented unified styling for required plugin parameters via QSS property.
    *   [x] Cleaned up `ThemeManager` logic related to plugin styles.

3.  **Metadata & Core Logic**
    *   [x] Updated `ExperimentMetadata` (removed `data_files`, added `analysis_results`, `associated_plugins`, `plugin_params`).
    *   [x] Updated `ProjectManager.add_experiment` signature.
    *   [x] Clarified roles: `DataManager` (generic I/O, handler coordination), `Handler Plugins` (format expertise, loading helpers), `Analysis Plugins` (calculations), `ProjectManager` (orchestration).
    *   [x] Applied likelihood thresholding within `DeepLabCutHandlerPlugin` loading helper method.

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

