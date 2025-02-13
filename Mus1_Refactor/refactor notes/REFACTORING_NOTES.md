# MUS1 Refactoring / Rewrite Notes



## Objectives
- Utilize the python library effectively: use pydantic for metadata, loguru for logging, and the built in libraries for the gui.
- Unify the GUI approach: set up a single `main_window.py` that works with main and core to handle the different windows and views
- Consitenta tab implement: seperate and coordinate tabs within main window.
- splaash screen and project selection on start up sequence alligned with core
- Restructure the `core` folder to ensure a cleaner architecture
- Support addition of image(s) and or video(s) to the project and to a specific experiment
- Future image extraction from video support
- support on image markings with mouse movment plots, be able to save these plots. User should be able to save markings indipendent of plot. 
- support for batch processing of experiments
- support for user defined settings
- support for user extracted bodyparts either from csv or dlc config file. make sure its filterable and sortable. 


## Proposed Steps
1. **Set up new repo structure**: 
   - Create a single `mus1` folder with subfolders `core`, `gui`, `utils`, `docs`.
   - Move or rename any duplicates carefully and test imports.
   - set up the logic to connect to plugins at core level

2. **Decide on logging**:
   - Direct usage of Python's logging library in each module, launched by main.py

3. **GUI merging**:
   - Evaluate whether a single `MainWindow` with each tab being its own script that sits in Main Window 
   - decide if main window logic is sufficient or if an additional support class is needed like `base_widget.py` 
   - Move "splash screen" to 'main.py' decide who coordinates initial project view (project selection: new or open) in project tab 
4. 
**Metadata**:
   - Keep the current pydantic-based `metadata.py` from your latest version.  
   - import metadata with pathlib
   - maintain data relationship logic in metadata as its the easiest way to ensure consistency

5. **Plugins**:
   - Confirm the plugin approach: each experiment type (NOR, OpenField, etc.) will remain as submodels (Pydantic), calculations for plugins coordinated between data manager and plugin classes, consitently coordinated through state

## Notes
- For older code references, look at the copy of the old mus1 folder in the refactor branch
- GitHub connect should go to `refactor-core` on mus-1 repo @llplatil 


## ProjectManager  
- We updated `add_experiment()` to ensure that multiple validations occur:
  1. The referenced mouse exists in `ProjectState.subjects`.
  2. The mouse is allowed to do the requested `experiment_type` (if non-empty set).
  3. The user can optionally assign a session_stage or link a video/image. #TODO: implement the plugin specified object selection specification, and phase specification as plugin dependent reqs as part of process experiment implementation
  4. initial additions can then just raise warnings rather then errors, the goal is ease of use

- Linking arena images or videos updates both directions:
  - The experiment gets its `arena_image_path` or `video` reference.
  - The metadata for that image or video now includes the experiment's ID, so browsing the media can tell which experiments it's associated with.
  - the image and video support is half cooked at the moment 

## Additional Validations
- We introduced `allowed_experiment_types` in `MouseMetadata` to handle future logic about which experiments a mouse can perform. You can keep the set empty to allow all experiments by default, will decide if we need this or if we just want to allow all by default.

## Next Steps

Step 1: Revisit and Clarify the “Plugin” Approach
-By design, the advanced validations are supposed to live in separate plugin logic or submodel root validators—some is done, but more thorough checks can be extracted out of the main metadata classes (like ExperimentMetadata) and placed into plugin code or submodels.

To do this: 
1. Create a dedicated plugins folder under core/ or at the same level, e.g. mus1/plugins/.
2. Provide a standard interface (e.g., BasePlugin) that each experiment plugin (NOR, OpenField, etc.) implements:
   - A reference to its Pydantic submodel (e.g. NORPluginParams)
   - Optional methods like validate_experiment(), analyze_experiment(), etc.
3. Register plugins in a PluginManager that maps ExperimentType → plugin class. Then, whenever you add an experiment of type NOR, you can fetch the corresponding plugin and run advanced validations or analysis.
Example Flow
When calling add_experiment(), your ProjectManager or your new PluginManager can:
   - Check experiment_type in the PluginManager.
   - Instantiate or retrieve a submodel for that type (e.g., NORPluginParams) if needed.
   - Execute specialized checks or transformations (like ensuring object roles are consistent for NORSessions.FAMILIARIZATION).
4. Additional considerations
   - We get more synergy if the DataManager focuses on raw data tasks, while the PluginManager (or plugin classes) handles experiment-specific logic
   - In your submodels (e.g. NORPluginParams), continue adding root validators for complex conditions (e.g., multiple objects must be identical for FAMILIARIZATION).
   - If you have cross-experiment logic that needs knowledge about the project or multiple experiments, place it in DataManager or a plugin’s utility function, not in the Pydantic model.
   - For each experiment type, have a plugin method validate_experiment_before_save(experiment, project_state). This can be called inside ProjectManager.add_experiment() if experiment.type matches a plugin.
   - If advanced session-stage logic or types exist, consider this in how we write a good complementary analyze_experiment() function that utilizes metadata and plugins

Step 2: Allign image and video support with the plugin approach

Step 3: Sharpen the Logging Strategy
Define a single logging configuration in main.py
- Use loguru for logging
- expose that logger globally
- use logger = logging.getLogger(__name__) in each file with consistent naming
- make sure logging writes to a local file that is created if it doesn't exist by default but is appended to if it does
- implement means of tracking logging leevel and clarify app session in log output

Step 4: Refine the GUI Structure
- create the gui classes and connect them to the core classes so we stay on track with connections through the whole stack
- flow at start up sequence:
  1. splash screen
  2. project selection
  3. load project
  4. change project view to standard view with tabs displayed and project view as default
- Create main_window.py, with a QMainWindow or QTabWidget approach.
  -use connect core
  - Keep the GUI as “dumb” as possible: it interacts with managers, receives data, and updates the UI. Manager classes remain the single source-of-truth.

