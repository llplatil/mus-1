# MUS1 Refactoring / Rewrite Notes

## Objectives
1. Employ modern Python libraries (Pydantic for metadata, built-in logging, PySide6/PyQt for GUI).  
2. Modernize the GUI approach:  
   - Use a single MainWindow with multiple functional tabs (Project, Subjects, Experiments, Markup, etc.).  
   - Integrate splash screen + project selection dialog seamlessly.  
3. Maintain consistency in the data model via **ProjectState** (with Pydantic) and a coherent folder structure (`mus1/core`, `mus1/gui`, `mus1/plugins`, `mus1/docs`).  
4. Support advanced features incrementally:  
   - Image/video integration and extraction.  
   - Interactive “markup” of images (draw objects / arena zones).  
   - Flexible plugin architecture for experiment types (NOR, OpenField, BasicCSVPlot, etc.).  

## Current Repo Restructure
1. A single "mus1/" folder, with subfolders:
   - `core/`  
   - `gui/`  
   - `plugins/`  
   - `docs/`  
   In the base of the mus1 folder:
   - `projects/` (houses mus1 projects for testing)  
   - `mus1.log` (log file)  
   - `gitignore` (configured to ignore log file and projects folder)  
   - `README.md`  
   - `requirements.txt`  
   - `project.toml`  
   - `pytest.ini`  
2. Logging with a unified strategy in `main.py` (using Python's built-in logging or loguru):
   - Logs appended to `mus1.log` by default.
   - Each module can use `logging.getLogger(__name__)`.
3. Metadata:
   - Uses Pydantic-based classes (e.g., `MouseMetadata`, `ExperimentMetadata`, etc.).  
   - Advanced validations move into plugins coded as submodels (e.g., `NORPluginParams`, `OFPluginParams`).
4. Plugin Approach:
   - Each experiment type is a plugin with logic for validation / analysis.
   - A `PluginManager` maps from experiment type → plugin class.

## Metadata & Experiment Minimalism

- **Required**: `Experiment ID`, `Subject (Mouse) ID`, `Date`, `Type` (one of the registered plugins).  
- **Optional**: Additional fields (e.g., tracking data, arena image) that plugins can validate.  
- If `MouseMetadata.allowed_experiment_types` is empty, any experiment type is possible; plugin logic enforces specialized constraints.

## Step 0: Clean Up Metadata (if Needed)
- Confirm that `metadata.py` is organized for easy reuse by plugins:
  - Keep plugin-specific fields out of the base models (use `plugin_params` to store them).  
  - Ensure the base enumerations (`ExperimentType`, `SessionStage`, etc.) are up to date and consistent with the new plugin approach.
  - Remove any redundant or conflicting logic now that we rely on plugin validations.

## Step 1: Implement “Add Experiment” With Plugin-Specified Fields
In line with the notes from `current_notes.txt`, the main tasks are:

1. **Extend/Create BasicCSVPlotPlugin**  
   - Add a `required_fields()` method that at least returns `["csv_path"]`.  
   - In `validate_experiment`, check:  
     - The CSV file path exists.  
     - At least one overlapping body part with `ProjectState`.  
   - Ensure the `ProjectManager` (or a helper method) can fetch these required fields for the GUI.

2. **Update ProjectManager.add_experiment(...)**  
   - Gather minimal required experiment data (ID, Subject ID, Date, Type).  
   - Attach plugin-specific fields under `experiment.plugin_params["csv_path"]`, etc.  
   - Call `plugin_manager.validate_experiment(experiment, project_state)`.  
   - If valid, insert into `project_state.experiments`.

3. **GUI Integration**  
   - In the Experiments tab (`ExperimentView`), dynamically show/hide the CSV path widget upon experiment type selection.  
   - On “Save,” collect the CSV path and other user input, call `add_experiment(...)`.  
   - Handle validation errors gracefully, showing them to the user if any arise.

By completing these tasks, you'll have a functioning BasicCSVPlot experiment flow:
- User chooses experiment type → plugin states required fields → user provides them → plugin validation → saved experiment → optional analysis available.

## “No Save Until Valid” Approach
- Recommended but optional: the GUI tracks the required fields from the plugin in real time.  
- Disable “Save” if mandatory fields aren’t provided or if local checks fail.

## Next Steps
1. **Markup Tab**: Create or refine a `gui/tabs/markup_tab.py` for image extraction/video snapshots, allowing object placement, arena boundaries, etc. Store markup in `ArenaImageMetadata`.
2. **Analysis**: Provide UI to trigger `plugin_manager.analyze_experiment(...)`. For BasicCSVPlot, generate a quick chart from the CSV.
3. **Documentation**: Update `README.md` to explain the new plugin system and mention the dynamic forms in the GUI.

---