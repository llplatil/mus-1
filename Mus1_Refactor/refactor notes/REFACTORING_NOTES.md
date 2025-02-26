# Refactoring Notes

## Objectives
1. **Modernize the codebase** using modern Python libraries (e.g., Pydantic for metadata, built-in logging) and a GUI framework (either PySide6 or PyQt).  
2. **Separate core business logic from UI logic** to keep the application maintainable and extendable.  
3. Maintain a **consistent data model** via a central `ProjectState`, with easy global sorting.  
4. **Incrementally support advanced features** using a flexible plugin architecture.

## Current Architecture & Key Components

- **Folder Structure**  
  - `core/`: Business logic and state management.  
  - `gui/`: User interface components (to be refactored to dynamically generate forms and subscribe to state changes).  
  - `plugins/`: Experiment-specific validations and logic.  
  - `docs/`: Documentation.

- **StateManager**  
  - Manages the in-memory `ProjectState`.  
  - Implements an observer pattern to notify UI components of state changes.

- **ProjectManager**  
  - Handles project-level operations, such as adding subjects/experiments, renaming projects, and updating tracked items.  
  - Relies on `StateManager` notifications for UI refresh instead of calling UI methods directly.

- **PluginManager**  
  - Registers experiment-specific plugins (e.g., BasicCSVPlot, NOR, OF).  
  - Exposes required fields, optional fields, and validation routines for each plugin.  
  - Provides a way to retrieve a plugin based on the experiment type.

- **Metadata Models**  
  - Defined with Pydantic (e.g., `MouseMetadata`, `ExperimentMetadata`, `PluginMetadata`).  
  - Provide consistent validation and typing.

- **Global Sorting**  
  - Centralized in `sort_manager.py`.  
  - Ensures consistent ordering across different data lists (subjects, experiments, objects, etc.).

## Recent Improvements

- **UI Decoupling**: Removed direct UI update calls from `ProjectManager`. UI now subscribes to `StateManager` changes.  
- **Metadata Simplification**: Simplified metadata and plugin-specific fields so the GUI can generate forms dynamically.

## Primary Data Classes and Sorting

Below is a quick look at data classes that appear in lists and typically benefit from sorting:

1. **MouseMetadata**  
   - Fields for sorting: `date_added`, `id`.  
   - Also possible to sort by birth date or genotype.

2. **ExperimentMetadata**  
   - Fields for sorting: `date_added`, `id`.  
   - Might also be grouped or sorted by `subject_id` or `type`.

3. **PluginMetadata**  
   - Fields for sorting: `date_created`, `name`.  
   - Often sorted lexicographically by name in the UI.

4. **BodyPartMetadata**  
   - Fields for sorting: `date_added`, `name`.

5. **ObjectMetadata**  
   - Fields for sorting: `date_added`, `name`.

6. **BatchMetadata**  
   - Fields for sorting: `date_added`, or specialized groupings like `analysis_type`.

7. **ArenaImageMetadata**  
   - Fields for sorting: `date`, `path` (lexicographical).

8. **VideoMetadata**  
   - Fields for sorting: `date`, `path`.

9. **ExternalConfigMetadata**  
   - Fields for sorting: `date`, `path`.


## New Flow Overview

1. **Core Reorganization**  
   - `PluginManager` lives in `core/plugin_manager.py`.  
   - `BasePlugin` declares a common plugin interface and utility methods.  
   - `ProjectManager` delegates validation and analysis to the correct plugin when creating new experiments.  
   - `StateManager` holds the `ProjectState` and can sync with `PluginManager` to update metadata.

2. **UI Integration**  
   - The main window triggers `StateManager` to sync with `PluginManager` on project selection.  
   - `ExperimentView` populates an experiment-type drop-down from `PluginManager`.  
   - When a user selects a plugin type, the view dynamically builds input fields (required/optional) from that plugin.  
   - When a user adds an experiment, validation is performed by the chosen plugin, and the experiment is saved to the state on success.

3. **ProjectManager Updates**  
   - `add_experiment()` creates an `ExperimentMetadata` object.  
   - Calls `PluginManager.validate_experiment()` before finalizing.  
   - If validation passes, saves to disk and notifies observers.

4. **StateManager / Observer Pattern**  
   - Each UI component subscribes to `StateManager`.  
   - On changes, `notify_observers()` triggers UI refresh.

5. **Plugin Integration**  
   - Each plugin defines `required_fields()`, `optional_fields()`, and `validate_experiment()`.  
   - Future expansions can implement custom data analysis or workflows in `DataManager` or within each plugin.

6. **UI Cleanup (Optional)**  
   - Improve the look and feel of the project selection dialog and main window.  
   - Consider small layout or style improvements in each view for clarity.

7. **Testing & Verification**  
   - Test basic workflows: create project, add subjects, add experiments, confirm sorting, etc.  
   - Handle edge cases: duplicate IDs, missing data, invalid plugin paths, etc.

8. **Summary of "To Do" Items**  
   1. **ExperimentView**: Implement dynamic plugin field creation and handle experiment addition (including validation).  
   2. **ProjectManager**: Finalize or refine `add_experiment()` logic, set `date_added`, notify observers.  
   3. **StateManager**: Ensure sorting uses `sort_manager` and that observers are correctly registered.  
   4. **sort_manager.py**: Confirm support for all relevant data fields (e.g., `date_added`, `id`).  
   5. **UI Aesthetics**: Optional improvements to dialogs and layout.  
   6. **Testing**: Validate the core workflow and plugin-specific logic.

## Current Status and Next Steps (Feb 21, 2025)

- We need to:
  - Resolve how `ExperimentMetadata` is defined to align with plugin metadata and the experiment flow.  
  - Verify the application runs locally with the updated observer pattern, sorting, and plugin-based forms.  
  - Support batch creation in the UI (connect the new batch metadata to the core logic).  
  - Improve the `SubjectView` so users can clearly see project status for each subject.  
  - Potentially show a mini log or message feed in the UI for user actions feedback.  
  - Integrate the NOR plugin with an analysis view to test plugin functionality in a real scenario.

---

# Detailed "To Do" for Steps 1 Through 6

Below are the concrete tasks for each step. These items can go into your "notepad" or task tracker:


## 2. Ensure the App Runs Locally with Correct Connections
- 

## 3. Support Batch Creation at the UI Level
- [ ] Add a "Batch" or "Queue" page or section in the GUI.  
- [ ] Create or update a method `add_batch()` in `ProjectManager` that creates a `BatchMetadata` entry in `ProjectState`.  
  - Ensure `date_added` is set.  
- [ ] Provide a UI form to fill out batch info (e.g., name, analysis type).  
- [ ] Validate inputs before creating the batch (optionally using a plugin approach if you expect specialized batch logic).  
- [ ] Save the new batch to the project state, and confirm that the UI refreshes to show the updated list of batches.

## 4. Improve Subject View
- [ ] Display a concise list of subjects, including relevant metadata (birth dates, genotype, training status).  
- [ ] Optionally add filtering or searching by subject ID or genotype.  
- [ ] Provide a more detailed subject "info" panel (e.g., show experiments related to this subject, or notes).  
- [ ] (Optional) Enable editing existing subject metadata (like genotype or notes) and saving it back to the state.

## 5. Implement UI Feature for Last N Log Messages
- [ ] In each tab I want it to be possible to see last actions by utilizing the space in left lower pane thats empty, my idea is to use 'navigation_pane.py' to display a log pane that dynimcally shows last n actions that fit in the space.
  
## 6. Connect the Basic CSV Plot Plugin to an Analysis View
- [ ] Create an `AnalyzeView` or expand an existing GUI component for advanced analysis.  
- [ ] Provide a way to select an experiment of type "CSV Plot" from the UI.  
- [ ] Invoke the `CSV Plot Plugin`'s analysis or validation methods (or any other relevant methods you’ve defined).  
- [ ] Display the results (it could be a metrics summary, generated plots, or images) in the UI.  
- [ ] Handle any plugin exceptions with a user-friendly error message.

## 7. Implement extract metadata from csv file that is compatible with Mus1 by transforming the csv file from a variety of sources
