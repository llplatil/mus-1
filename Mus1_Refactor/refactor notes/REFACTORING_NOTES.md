# MUS1 Refactoring / Rewrite Summary

## Objectives
- Modernize the codebase using modern Python libraries (Pydantic for metadata, built-in logging) and a GUI framework (PySide6/PyQt).
- Clearly separate core business logic (in managers) from UI logic.
- Maintain a consistent data model (ProjectState) and implement global sorting for lists.
- Support advanced features incrementally through a flexible plugin architecture.

## Current Architecture & Key Components
- **Folder Structure:**
  - `core/`: Business logic and state management.
  - `gui/`: User interface components (to be refactored to dynamically generate forms and subscribe to state changes).
  - `plugins/`: Experiment-specific validations and logic.
  - `docs/`: Documentation.

- **StateManager:**
  - Manages the in-memory ProjectState.
  - Implements an observer pattern to notify UI components of state changes.

- **ProjectManager:**
  - Handles project-level operations such as adding subjects/experiments, renaming projects, and updating tracked objects.
  - No longer directly triggers UI refreshes; it relies on StateManager's notifications.

- **PluginManager:**
  - Supports registering experiment-specific plugins that define required fields and perform validations. Impment means of plugin telling what ui a tab should display. 

- **Metadata Models:**
  - Defined using Pydantic to ensure consistent validation (e.g., MouseMetadata, ExperimentMetadata, PluginMetadata).

- **Global Sorting:**
  - Centralized in sort_manager.py to sort lists by date, name, or custom keys consistently across different data types.

## Recent Improvements
- UI decoupling: Removed direct UI update calls from ProjectManager. UI components now subscribe to state changes via StateManager's observer pattern.
- Simplified metadata and plugin field handling to better support dynamic form generation in the GUI.


List data relationships

# Current Overview of Data Classes For Sorting as currently possible by global sort using current version of sort_manager.py. Core still needs to be updated to use this new sorting approach and we need consider special cases and what patterns we want to follow.

Below is a concise list of the primary data classes in **MUS1** that appear in lists and benefit from sorting by name or date. In each case, note any special considerations (e.g., fallback fields, unique ID fields).

---

## 1. `MouseMetadata`
- **Possible Sort Fields**:
  - `date_added` (Date-based sorting)
  - `id` (Unique mouse ID; can also serve as a fallback).
- **Additional Considerations:**  
  - Some pipelines sort by birth date or genotype. Generally, though, "date_added" is used for chronological listing and "id" for name-like listing.

---

## 2. `ExperimentMetadata`
- **Possible Sort Fields**:
  - `date_added` (Date the experiment was recorded/created in the system)
  - `id` (Experiment ID, often includes numbers that might need natural sorting)
- **Additional Considerations:**  
  - Some "grouping" or specialized sorts happen by `subject_id` or `type` (plugin type).  
  - A fallback is "Lexicographical / Natural Order" of the `id`.

---

## 3. `PluginMetadata`
- **Possible Sort Fields**:
  - `date_created` (When the plugin was registered or created)
  - `name` (Plugin's display name)
- **Additional Considerations:**  
  - Typically sorted lexicographically by name for UI displays.  
  - "Date Added" might help if you want to show the newest plugins first.

---

## 4. `BodyPartMetadata`
- **Possible Sort Fields**:
  - `date_added` (When the body part was added)
  - `name` (e.g., "nose," "tail_base")
- **Additional Considerations:**  
  - Often displayed in forms or lists (like "master body parts").  

---

## 5. `ObjectMetadata`
- **Possible Sort Fields**:
  - `date_added`
  - `name` (the object's label, e.g. "Cube1")
- **Additional Considerations:**  
  - Some projects might rely more on lexicographical ordering for object names.

---

## 6. `BatchMetadata`
- **Possible Sort Fields**:
  - `date_added`
  - Possibly `analysis_type` if you need specialized grouping.
- **Additional Considerations:**  
  - Often used in an "analysis queue" or "batch processing" UI, so chronological order by `date_added` is typical.

---

## 7. `ArenaImageMetadata`
- **Possible Sort Fields**:
  - `date` (When the image was created/recorded)
  - `path` (Lexicographical if you want to sort by file name)
- **Additional Considerations:**  
  - This might not always appear in user-facing lists, but if so, date or file name is typical.
  - most useful may be by subject ID or experiment and if labled or not
  - we need to consider future CV implementation and how to sort these images and videos and how we relate them to the experiments and subjects
---

## 8. `VideoMetadata`
- **Possible Sort Fields**:
  - `date` (When the video was recorded)
  - `path`
- **Additional Considerations:**  
  - Similar to `ArenaImageMetadata`: might be sorted by file path or date for quick chronological listing, most useful may be by subject ID or experiment and if labled or not
  - we need to consider future CV implementation and how to sort these images and videos and how we relate them to the experiments and subjects
---

## 9. `ExternalConfigMetadata`
- **Possible Sort Fields**:
  - `date` (When the config was created/last updated)
  - `path`
- **Additional Considerations:**  
  - Typically minimal usage but might be displayed if you let users manage external config files.
  _ we are not saving them atm but might need to consider this for the future

---

## Overall Strategy
- **Date-based sorting** often references fields like `date_added`, `date_created`, or `date_recorded`.  
- **Name-based sorting** typically references a `name` or `id` property, which may need natural order parsing if it mixes letters and numbers.  
- **Fallback Fields** might include `id` or `path` when no `date` or `name` is available.  
- **Consistency** is key: by applying the same protocol or mixin approach (HasDateAdded, HasName) and a unified `sort_manager.py`, each list can be sorted reliably using a single interface.


Overview of the New Flow:
1. Core Reorganization:
 • The PluginManager now lives in core/plugin_manager.py. It registers all available plugins (e.g., BasicCSVPlotPlugin, NORPlugin, OFPlugin) and provides methods to retrieve a plugin based on the experiment type.
 • The BasePlugin only declares the common interface and shared utilities (like CSV body part extraction), so individual plugins can focus on their validation and analysis logic.
 • The ProjectManager (in core/project_manager.py) now holds a reference to PluginManager. When adding an experiment, it delegates validation and analysis to the registered plugin for that experiment type.
 This frees up data_manager. #see thoughts on what data manager will do below
 • The StateManager holds the current ProjectState (which contains, for instance, experiments and plugin metadata) and can be synced with the PluginManager info (like supported types or entire plugin metadata lists).
2. UI Integration:
 • At the main window level (main_window.py), when a project is selected the StateManager syncs supported experiment types and plugin metadata.
 • In the Experiments view (experiment_view.py), the experiment type drop-down is populated based on the supported experiment types (from PluginManager via StateManager).
 • When a user selects an experiment type (for example, "BasicCSVPlot"), the update_plugin_fields_display() method in ExperimentView retrieves the plugin via the PluginManager. It then calls plugin.required_fields() and plugin.optional_fields() to dynamically build the input form for plugin-specific parameters. For BasicCSVPlotPlugin these are "csv_path" (required) plus "body_part", "extracted_image", and "video" (optional).
Adding an Experiment:
 • When the user fills out the form and clicks "Add Experiment," ExperimentView gathers both the core experiment fields (ID, subject, date) and the filled plugin-specific fields.
 • ExperimentView calls project_manager.add_experiment(), which creates an ExperimentMetadata instance. Before saving, it hands off validation to PluginManager.validate_experiment() (which in turn calls the selected plugin's validate_experiment method). This step verifies that, for example, the CSV file exists and its header contains at least one tracked body part that matches the master body parts.
 • If validation passes, the new experiment is added to the project state (and associated with the subject), the project state is saved to disk, and UI lists are refreshed (showing the new experiment sorted appropriately).


Next steps:
1. General Goals & Considerations
Continue decoupling UI code from the business logic in manager classes.
Use the observer pattern already implemented in StateManager for automatic UI updates.
Rely on PluginManager for experiment-specific fields and validations.
Ensure consistency in sorting throughout (using sort_manager).
---
2. ExperimentView Enhancements
These tasks focus on making ExperimentView fully dynamic and properly integrated with PluginManager.
Dynamically Generate Plugin Fields
In the method update_plugin_fields_display(), retrieve the plugin for the currently selected experiment type (via self.project_manager.plugin_manager).
Call plugin.required_fields() and plugin.optional_fields() to build dynamic widgets.
Required fields: Create labeled input widgets (e.g., QLineEdit, QComboBox, etc.).
Optional fields: Group them separately (e.g., in a collapsible section or a separate QGroupBox).
Make sure you clear out old plugin fields whenever the experiment type changes and re-generate new ones.
Handle Experiment Addition & Validation
In handle_add_experiment(), gather both:
a) Core experiment fields (ID, subject, date).
b) Dynamically created plugin-specific fields.
Pass them to project_manager.add_experiment() for creation.
Inside add_experiment(), call PluginManager.validate_experiment() to run the selected plugin's validation logic.
If validation fails, show a QMessageBox with the error.
If it succeeds, finalize the addition (ProjectManager will save to disk, then rely on StateManager to notify observers).
Refresh the Experiment List Display
After adding a new experiment, automatically refresh the experiment list.
You might use the existing refresh_data() or create a new method that queries self.state_manager.get_experiments_list() and then sorts them via the global sort setting in the ProjectState.
Populate the experimentListWidget with the updated, sorted experiment list.
---
3. ProjectManager Updates
You already have ProjectManager coordinating creation and saving of data, but here are some refinements:
add_experiment Method
Implement (or refine) add_experiment() to:
Create an ExperimentMetadata object.
Assign it a date_added if not already provided (for uniform date-based sorting).
Associate the new experiment with the correct subject if subject_id is provided.
Call PluginManager.validate_experiment() before adding the experiment to the ProjectState.
If validation passes, add the experiment to the state, save the project, and call StateManager.notify_observers().
Sorting Integration
Ensure that, whenever new items are added (subjects, experiments, body parts, etc.), the relevant UI lists can be re-sorted by the global sort mode in the state.
You may already have a sort_manager. Double-check that ProjectManager (or StateManager) uses it consistently when returning data for the UI.
Potential Subject/Experiment Linking
Confirm that when adding a new experiment, it can be linked to a Subject's experiments list or remain in a global experiment dictionary.
If bridging or referencing is needed, ensure that the UI can still fetch experiments by subject_id.
---
4. StateManager / Observer Pattern
Confirm Subscriptions
Review all GUI classes (ProjectView, SubjectView, ExperimentView) and confirm each one subscribes to the StateManager (if relevant).
Each view's refresh method should be triggered when StateManager.notify_observers() is called.
sort_manager.py Usage
Verify that StateManager or the manager classes use sort_manager.py for sorting objects consistently.
For each data list (subjects, experiments, body parts, objects), confirm that calls to sort_items(...) are made with the currently stored global_sort_mode.
PluginManager Sync
If the UI or ProjectManager needs a list of plugin metadata (e.g., for display, user selection), confirm that you are calling StateManager.sync_plugin_metadatas(...) or your own method to keep plugin data updated in the ProjectState.
Ensure the experiment types are being fetched from PluginManager's get_supported_experiment_types() and stored in project_state.supported_experiment_types.
---
5. Plugin Integration
Validate Experiment-Specific Logic
Each plugin should define its required_fields, optional_fields, and validate_experiment methods.
Ensure the new dynamic form creation in the ExperimentView matches these definitions.
Confirm that, when you call validate_experiment, it raises an exception or returns a specific result on failure, which the UI will then display in a QMessageBox.
DataManager vs. Plugins
Your notes mention refactoring data_manager. Keep in mind which tasks you want inside a plugin's logic (e.g., CSV reading, custom validations) vs. what belongs in data_manager.
DataManager might hold common analysis routines (speed calculation, heat map generation, etc.) that multiple plugins can call.
---
6. UI Cleanup (Optional / Aesthetic)
Project Selection Dialog
Update the layout/style to look more polished: bigger title, consistent color scheme, padding, etc.
You can set a QWidget stylesheet in the dialog's constructor.
Main Window & Other Views
Review each view (ProjectView, SubjectView, ExperimentView) for any leftover direct calls to ProjectManager that should go through StateManager or an observer pattern.
Consider minor UI design tweaks for clarity (labels, spacing, grouping).
---
7. Testing & Verification
Basic Workflow Testing
Create a new project, add several subjects, add experiments with different plugins, ensure they sort by ID or date as intended.
Switch between projects to confirm data loads and all UI lists refresh properly.
Edge Case Testing
Duplicate subject IDs, empty experiment IDs, missing CSV files for plugin-based validations.
Confirm each case results in correct error messages or user feedback.
Plugin Development & Testing
If you plan to add more plugins (e.g., NORPlugin, OFPlugin), verify that they follow the same pattern: define required/optional fields, implement validation, and appear in the experiment type dropdown.
---
8. Summary of Concrete "To Do" Items
In ExperimentView:
Implement update_plugin_fields_display() to fetch required/optional fields from the selected plugin and build the form.
In handle_add_experiment(), gather user input (core + plugin fields), call add_experiment in ProjectManager, handle validation errors, and refresh the experiment list.
In ProjectManager:
Implement or refine add_experiment() with plugin validation.
Ensure date_added is set on new experiments.
After acceptance, save the project and notify observers.
In StateManager:
Verify observer subscriptions are correct in every view.
Make sure get_experiments_list() (and similar) use the global sort mode (via sort_manager).
In sort_manager.py (if not done):
Confirm all data classes (MouseMetadata, ExperimentMetadata, etc.) can be sorted by their relevant fields.
Handle fallback sorting (e.g., if date is missing, fall back to ID).
UI Aesthetics:
(Optional) Improve ProjectSelectionDialog styling.
Review other minor layout or visual improvements in main_window.py and the views.
Thorough Testing
Perform "create → add subjects → add experiments → switch project" cycle.
Test plugin field validation with real data.
Confirm sorted lists appear consistently with chosen sorting modes.
---
These steps should cover the main features you need to shore up before you move on to more advanced functionality like custom analysis, advanced plugin logic, or extended UI features. By following this list, you'll ensure your codebase remains modular, the UI is kept separate from core logic, and future plugins or features can be added without major rewrites.

## Update: Current Status and Next Steps

### Current Status Feb 21 2025
- **UI Decoupling:** ExperimentView now dynamically generates plugin-specific fields based on the selected experiment type. The view registers with StateManager to automatically refresh when the project state changes.
- **ProjectManager Updates:** The add_experiment method now validates experiments using PluginManager, attaches the corresponding plugin metadata (e.g., from BasicCSVPlot, NOR, and OF plugins), and stores the experiments in the project state. Redundant sorting methods have been removed in favor of StateManager's unified sorting via get_sorted_list.
- **Plugin Integration:** PluginManager and individual plugins (BasicCSVPlot, NOR, and OF) have been updated. Each plugin now defines its required and optional fields and performs basic validation. Plugin-specific parameter classes have been moved out of metadata.py and should be implemented within each plugin as needed.
- **Metadata Cleanup:** metadata.py now focuses on generic metadata definitions. Unused plugin-specific parameter models have been removed (though some unused imports may still need cleanup).

### Next Steps
- **UI Enhancements:** Refine the dynamic form components in ExperimentView by matching widget types to data types (e.g., date pickers for dates, combo boxes for enums).
- **Validation & Testing:** Extend and further refine validation rules for plugins using real CSV data, and implement thorough tests for each plugin's validation logic.
- **Data Analysis Integration:** Integrate a DataManager to support complete analysis workflows for BasicCSVPlot and other plugins.
- **Code Cleanup:** Remove unused imports and warnings in metadata.py and other modules to improve code clarity and quality.
- **Unit Testing:** Develop unit tests covering PluginManager behavior, plugin validation, experiment addition, and state management.
- **Plugin Expansion:** Continue developing new plugins and enhance existing ones, maintaining clear separation between UI, business logic, and plugin-specific behavior.
