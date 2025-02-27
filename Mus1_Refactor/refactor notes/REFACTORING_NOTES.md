# Refactoring Notes
Mus1 is a tool for managing and analyzing behavioral data from mice experiments, it aims to be a one stop shop for all data associated with a projects, and allow for the use of the best tools from other open source projects. Imagine an ML driven anymaze, but it supports plugins (how we add new best practices and tools) and custom scripts.
the core should be set up to best track all the various data one will need for lab animal experiments and allow for the use of the best tools from other open source projects.

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


App runs locally after we did the following, did not test further:
we keep for saving editing and validation of experiments using plugin reqs im thinking: after user sets type of experiment (behavioral science level), user then selects stage of data procesing they are on (right now we just offer post processing). the next option the user is shown is the file source they are using (for now just DLC). then they are offered plugins that support that type of experiment, at that stage, with files from that source. user then selects 1 or more plugin they plan to use, back end compiles list of all unique reqs for display in the experiment view ui(box that clearly shows all unique requirnmnets that must be met to use the selections up to this point). below it we list all unique optional associated with those chosen plugins (this is a seperate optional box). once user meets all of these reqs and clciks save new experiment, validation at plugin level was succsesful, project metadata saves, pushes refresh all lists and state manager emits new current lists. Id have state manager be the master coordinator between intermedate steps selections of add experiment and project manager just does the final saving and makes sure it saved the various data apropriately. 

thus we are comminting to String-Based Approach. 

Core Concept
Implement a hierarchical experiment creation workflow where users select:
1. Experiment type (behavioral science level)
Processing stage
Data source
Compatible plugins
Required and optional fields

User Workflow for Adding an Experiment
Type Selection: User selects the scientific experiment type (e.g., NOR, OpenField)
Processing Stage: User selects data processing stage (currently only post-processing)
Data Source: User selects the source of tracking data (currently only DLC)
Plugin Selection: Based on the above selections, system shows compatible plugins
Required Fields: System compiles and displays all unique required fields from selected plugins
Optional Fields: System shows all optional fields from selected plugins
Validation: On save, system validates all requirements are met before saving the experiment

## Implementation Phases

1. **Core Model Updates**
   - Update metadata classes
   - Update BasePlugin with string methods
   - Remove enum definitions

2. **Manager Classes**
   - Enhance PluginManager with new methods
   - Update StateManager for hierarchical compatibility
   - Add validation methods to DataManager

3. **UI Implementation**
   - Add hierarchical selection components
   - Connect change events
   - Update plugin selection display

4. **Testing**
   - we test by getting the app to launch and I test new features 

Metadata: 
we should remove these: 
class NORSessions(Enum):
    FAMILIARIZATION = "familiarization"
    RECOGNITION = "recognition"


class OFSessions(str, Enum):
    HABITUATION = "habituation"
    REEXPOSURE = "re-exposure"

# REMOVE this enum definition
# class ArenaImageSource(str, Enum):
#     DLC_EXPORT = "DLC_Export"
#     MANUAL = "Manual"
#     UNKNOWN = "Unknown"

# INSTEAD, add these constants if you want standard string references
ARENA_SOURCE_DLC_EXPORT = "DLC_Export"
ARENA_SOURCE_MANUAL = "Manual" 
ARENA_SOURCE_UNKNOWN = "Unknown"

then: 

- Update `ExperimentMetadata` in core/metadata.py:
  - Add fields for processing_stage and data_source (both as strings)
  - Add associated_plugins: List[str] field to track selected plugins
  - Remove any legacy enum references for experiment types

- Update `PluginMetadata` in core/metadata.py:
  - Add supported_processing_stages: List[str]
  - Add supported_data_sources: List[str] 
  - Keep supported_experiment_types: List[str]
class ArenaImageMetadata(BaseModel):
    path: Path
    name: str = ""
    date_added: datetime = Field(default_factory=datetime.now)
    source: str = "Unknown"  # String instead of enum
    # ... other fields

Base Plugin: 

- Update `BasePlugin` in plugins/base_plugin.py:
  - Add simple methods that return lists of strings:
    ```python
    def get_supported_experiment_types(self) -> List[str]:
        """Return experiment types this plugin supports."""
        meta = self.plugin_self_metadata()
        return meta.supported_experiment_types or []
    
    def get_supported_processing_stages(self) -> List[str]:
        """Return processing stages this plugin supports."""
        # Default to post-processing
        return ["post-processing"]
    
    def get_supported_data_sources(self) -> List[str]:
        """Return data sources this plugin supports."""
        # Default to DLC
        return ["DLC"]
    ```

class BasePlugin(ABC):
    # Other methods...

    metods related to images
```python
    def get_supported_arena_sources(self) -> List[str]:
        """Return arena image sources this plugin supports."""
        # Default implementation
        return ["DLC_Export", "Manual"]
        def validate_experiment(self, experiment: ExperimentMetadata, project_state: ProjectState) -> None:
    # Existing validation code...
    
    # If this plugin requires arena images
    if "arena_image" in self.required_fields():
        # Get arena image path from plugin params
        arena_path = experiment.plugin_params.get(self.plugin_self_metadata().name, {}).get("arena_image_path")
        if not arena_path:
            raise ValueError("Arena image path is required")
            
        # Use DataManager to validate arena image
        from core.data_manager import DataManager  # Avoid circular imports
        data_manager = DataManager()
        data_manager.validate_arena_image(
            Path(arena_path), 
            self.get_supported_arena_sources(),
            project_state
        )
        ```
Individual Plugins: 

- Update individual plugins:
  - Remove the NORSessions and OFSessions enums
  - Update plugin_self_metadata in each plugin to declare:
    - supported_experiment_types
    - supported_processing_stages
    - supported_data_sources

PluginManager Enhancements:

- Add methods to get unique lists from all plugins:
  ```python
  def get_supported_processing_stages(self) -> List[str]:
      """Return unique processing stages from all plugins."""
      stages = set()
      for plugin in self._plugins:
          stages.update(plugin.get_supported_processing_stages())
      return sorted(list(stages))
  
  def get_supported_data_sources(self) -> List[str]:
      """Return unique data sources from all plugins."""
      sources = set()
      for plugin in self._plugins:
          sources.update(plugin.get_supported_data_sources())
      return sorted(list(sources))
  ```

- Add method to get compatible plugins:
  ```python
  def get_plugins_by_criteria(self, exp_type: str, stage: str, source: str) -> List[BasePlugin]:
      """Return plugins supporting the given criteria combination."""
      return [
          plugin for plugin in self._plugins
          if (exp_type in plugin.get_supported_experiment_types() and
              stage in plugin.get_supported_processing_stages() and
              source in plugin.get_supported_data_sources())
      ]
-image

  ```python
def get_supported_arena_sources(self) -> List[str]:
    """Return unique arena image sources supported by all plugins."""
    sources = set()
    for plugin in self._plugins:
        if hasattr(plugin, "get_supported_arena_sources"):
            sources.update(plugin.get_supported_arena_sources())
    return sorted(list(sources))

State Manager: 

- Add methods to bridge between UI and plugin manager:
  ```python
  def get_compatible_processing_stages(self, exp_type: str) -> List[str]:
      """Get processing stages compatible with selected experiment type."""
      stages = set()
      for plugin in self._plugin_manager.get_all_plugins():
          if exp_type in plugin.get_supported_experiment_types():
              stages.update(plugin.get_supported_processing_stages())
      return sorted(list(stages))
  
  def get_compatible_data_sources(self, exp_type: str, stage: str) -> List[str]:
      """Get data sources compatible with selected experiment type and stage."""
      sources = set()
      for plugin in self._plugin_manager.get_all_plugins():
          if (exp_type in plugin.get_supported_experiment_types() and
              stage in plugin.get_supported_processing_stages()):
              sources.update(plugin.get_supported_data_sources())
      return sorted(list(sources))
  ```

- Add intermediate experiment creation methods:
  ```python
  def compile_required_fields(self, plugins: List[BasePlugin]) -> List[str]:
      """Get unique required fields from selected plugins."""
      fields = set()
      for plugin in plugins:
          fields.update(plugin.required_fields())
      return sorted(list(fields))
  ```

DataManager Improvement

- Add validation methods for files against plugin requirements:
  ```python
  def validate_file_for_plugins(self, file_path: Path, plugins: List[BasePlugin]) -> Dict[str, Any]:
      """Validate a file against plugin requirements."""
      results = {}
      for plugin in plugins:
          plugin_name = plugin.plugin_self_metadata().name
          try:
              # Plugin-specific validation
              # ...
              results[plugin_name] = {"valid": True}
          except Exception as e:
              results[plugin_name] = {"valid": False, "error": str(e)}
      return results
  ```
Project Manager Updates

- Update add_experiment to use the new method signature:
  ```python
  def add_experiment(self, experiment_id, subject_id, date_recorded, 
                    exp_type, processing_stage, data_source,
                    plugin_selections, plugin_params):
      # ...
      def validate_arena_image(self, image_path: Path, allowed_sources: List[str], 
                        project_state: ProjectState) -> Dict[str, Any]:
    """
    Validate an arena image against requirements.
    
    Args:
        image_path: Path to the arena image
        allowed_sources: List of allowed sources for this image
        project_state: Current project state
        
    Returns:
        Dictionary with validation results
        
    Raises:
        ValueError: If validation fails
    """
    # Check if file exists
    if not image_path.exists():
        raise ValueError(f"Arena image not found: {image_path}")
        
    # Get image source from project state
    arena_source = project_state.get_arena_image_source(image_path)
    
    # Check if source is allowed
    if arena_source not in allowed_sources:
        supported = ", ".join(allowed_sources)
        raise ValueError(f"Arena image source '{arena_source}' not supported. Must be one of: {supported}")
        
    # Any other validations (format, size, etc.)
    # ...
    
    return {
        "valid": True,
        "source": arena_source,
        "path": str(image_path)
    }
  ```
Experiment View UI Changes

- Implement hierarchical selection:
  1. Add experiment type dropdown (expTypeCombo)
  2. Add processing stage dropdown (stageCombo)
  3. Add data source dropdown (sourceCombo)
  4. Add plugin selection area with checkboxes
  5. Add required fields area (groupbox)
  6. Add optional fields area (groupbox)

- Connect change events:
  ```python
  def on_experiment_type_changed(self):
      """When experiment type changes, update available processing stages."""
      exp_type = self.expTypeCombo.currentText()
      self.stageCombo.clear()
      stages = self.state_manager.get_compatible_processing_stages(exp_type)
      for stage in stages:
          self.stageCombo.addItem(stage)
  ```

- Use tuples as dictionary keys:
  ```python
  # Instead of:
  self.widgets[f"{plugin_name}:{field}"] = widget
  
  # Use:
  self.widgets[(plugin_name, field)] = widget
  ```

- Add explicit error handling for selection stages:
     ```python
     def on_experiment_type_changed(self):
         """When experiment type changes, update available processing stages."""
         exp_type = self.expTypeCombo.currentText()
         self.stageCombo.clear()
         stages = self.state_manager.get_compatible_processing_stages(exp_type)
         
         if not stages:
             self.navigation_pane.add_log_message(f"Warning: No processing stages found for {exp_type}")
             self.stageCombo.setEnabled(False)
         else:
             self.stageCombo.setEnabled(True)
             for stage in stages:
        
        
                 self.stageCombo.addItem(stage)
     ```

   - Add clear logic for dependent selections:
     ```python
     def on_experiment_type_changed(self):
         """When experiment type changes, reset all dependent selections."""
         # Clear dependent dropdowns
         self.stageCombo.clear()
         self.sourceCombo.clear()
         self.plugin_selection_area.clear()
         self.required_fields_area.clear()
         self.optional_fields_area.clear()
         
         # Update processing stages
         exp_type = self.expTypeCombo.currentText()
         stages = self.state_manager.get_compatible_processing_stages(exp_type)
         for stage in stages:
             self.stageCombo.addItem(stage)
     ```
     
Navigation Pane Improvement


- Add logger message display area at bottom:
  ```python
  class NavigationPane(QWidget):
      def __init__(self, parent=None):
          # ...
          self.log_display = QTextEdit(self)
          self.log_display.setReadOnly(True)
          self.log_display.setMaximumHeight(100)
          self.layout.addWidget(self.log_display)
          
      def add_log_message(self, message):
          """Add a new log message, keep only last 3."""
          current_text = self.log_display.toPlainText()
          lines = current_text.split("\n")
          if len(lines) > 2:  # Keep only last 2 lines + new message
              lines = lines[-2:]
          lines.append(message)
          self.log_display.setPlainText("\n".join(lines))
  ```

Potential sources of error to avoid:
       general: 
adopt legacy naming as much as possible. remove old code as you add new replacments. grep often. get rid of outdataed notes in codebase that would cause confusion. 

       Scattered Enum References:
Removing the enum definitions for NOR or OF sessions will mean systematically removing or updating any code that still references those sessions. Watch out for any leftover references in UI code, validations, or leftover docstrings.
Similarly, if you remove “ArenaImageSource” enum, ensure that all plugin or data manager references have been changed to the new string constants. Doing a full code search for the old enums is often safer than relying on memory so you don’t leave any unconverted references.

       Consistency & Validation:
Switching to a string-based approach can increase the risk of typos or slight variations (e.g., "post-processing" vs "PostProcessing"). Consider establishing a set of constants to avoid “string drift.”
can store these valid strings in plugin metadata and reference them across the code if it makes sense

       UI Dependency and Error Handling:
As you implement the hierarchical selection (type → stage → data source → plugin), ensure that your UI gracefully handles situations where no plugins are found for a particular combination.

       State Manager & Plugin Manager Coordination:
You plan to have the StateManager coordinate the experiment creation steps while the ProjectManager just finalizes and saves the experiment. This separation is good, but verify that the flow of data is crystal clear—especially if user preference changes mid-way (e.g., user picks a plugin, then changes the data source). You’ll want to store partial state in memory or reset things carefully.
Double-check that the new methods (like get_compatible_processing_stages and get_compatible_data_sources) properly reflect the plugin manager’s actual plugin list. If the plugin manager references an uninitialized plugin set, you might end up with empty lists.

       Arena Image Validation:
Your plan to add an arena image validator in the DataManager is good, but watch out for potential circular imports if you do something like from core.data_manager import DataManager inside plugin code. You can fix that with local imports or by passing a data manager instance around where needed.
Confirm that the logic to determine the arena image “source” from the path is well-defined. If “source” is now a free-form string, be sure you have a consistent way of assigning that string (e.g., "DLC_Export") and storing it in project state.
