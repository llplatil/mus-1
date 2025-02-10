# MUS1 Architecture (Updated)

## Key Implementations (Using Pydantic for Metadata)

1. **Unified Data Processing and Metadata**  
   - JSON-based data storage for mouse, experiment, and project-level metadata, validated by Pydantic models.  
   - Enums capture discrete fields (e.g., `ExperimentType`, `Sex`, `NORSessions`, `OFSessions`).
   - Frame rate logic uses either experiment-specific or a global default (60).

2. **Plugin Submodels**  
   - Each plugin defines a Pydantic submodel with fields and minimal logic.  
   - **NORPluginParams**: includes `NORSessions` (FAMILIARIZATION, RECOGNITION) and object roles.  
   - **OFPluginParams**: includes `OFSessions` (HABITUATION, RE-EXPOSURE) and optional arena markings.

3. **State Management**  
   - A `StateManager` orchestrates core validations and merges advanced logic.  
   - A `ProjectState` holds in-memory data: mice, experiments, submodels, and more.  
   - `ProjectManager` saves/loads JSON files and updates the filesystem accordingly.

4. **Validation Strategy**  
   - **Field-Level Validation**: Pydantic checks for basic constraints (e.g., future birth_date disallowed).  
   - **Plugin-Specific Validations**: Enforced through submodels (e.g., for NOR familiarization) or plugin business logic.  
   - **Cross-Field or Complex Checks**: Handled by code in `StateManager` or each plugin's analysis functions.

5. **Why Pydantic Over YAML**  
   - **Consistency**: Single Pythonic approach for defining/enforcing schemas.  
   - **Less Redundancy**: No extra YAML schema files to maintain.  
   - **Enum Integration**: Clear definition of valid experiment types and stages.

## Data Flow

1. **Add Mouse**  
   - Minimal fields: `id` required; `birth_date` is optional.  
   - Stored in `ProjectState.subjects[mouse_id]`.

2. **Add Experiment**  
   - You specify `ExperimentType` (e.g., `NOR` or `OpenField`).  
   - A session stage enum (`NORSessions` or `OFSessions`) is stored in the plugin submodel.  
   - `DataManager` processes the tracking file if needed.

3. **Analyze Experiment**  
   - Plugin logic checks required fields or advanced rules (e.g., two objects for NOR recognition).  
   - Results are stored in plugin data or separate result objects.

4. **Project Saving**  
   - `ProjectManager` or `StateManager` serializes `ProjectState` and writes JSON.  
   - Re-loaded on next session.

## Conclusion

MUS1 organizes metadata via Pydantic-based models (for mice, experiments, plugin params, and project settings), combining them into a single in-memory state managed by `StateManager`. Each **plugin** (e.g., NOR, OF) interacts with these models for advanced validations or analysis steps.

---

## Core Components

### State Management
- **`StateManager`**  
  - Central object that holds application state in memory (via `ProjectState`)  
  - Carries out advanced or conditional validations using plugin submodels or specialized checks  
  - Emits signals/events to update GUI widgets  

### Data Management
- **`DataManager`**  
  - Primary handler for technical data operations (e.g., parsing DLC CSVs, computing durations, verifying frame rates)  
  - References `ProjectState` for experiment context (e.g., "Which mouse?").
  - Delegates advanced or experiment-type-specific logic (e.g., needed arenas) to **plugins**.  

### Project Management
- **`ProjectManager`**  
  - Coordinates filesystem operations (create/open/save project folders)  
  - Persists JSON files for each mouse/experiment **or** a single project-wide JSON  
  - Orchestrates commands like "add new mouse" with `StateManager` + `DataManager`.

### Metadata System
- **`MetadataSystem`** (Provided via Pydantic Models)  
  - **Single point** for field definitions (mouse ID, experiment date, plugin submodels, etc.), including required vs. optional.  
  - Field-level validation is handled via Pydantic. More complex plugin-based checks (e.g., "object roles must match the plugin's requirements") happen in plugin or manager code.

#### Project-Level Metadata
- A `ProjectMetadata` model that defines:  
  - A list of DLC configs referenced by the project (local paths, optional version info, etc.)  
  - A "master list" of possible body parts, discovered from all DLC configs  
  - A user-defined subset of **active** body parts for analysis  
  - A user-defined list of tracked objects  
  - A global frame rate (60 by default) used unless an experiment specifies otherwise  
  - Unique Project name 
  - date created  

**Why Project-Level?**  
- These settings apply across all experiments and mice—reloaded when the user re-opens the project.  
- We avoid duplicating global data in each experiment or pushing it into `MouseMetadata`.

#### Experiment-Level Metadata
- **Uses an Enum** to identify experiment type. For example, `ExperimentType.NOR` or `ExperimentType.OpenField`.  
- **Has a submodel** (e.g. `NORPluginParams`, `OpenFieldPluginParams`) to store required fields (like "object_roles," "arena_markings," or "time_of_recording").  
- Each experiment references a `mouse_id`, and can be added individually to that mouse in `ProjectState`.

#### Data Relationships
- **Subjects (mice) can exist alone.**  
- **Experiments** must reference an existing subject (`mouse_id`). Each experiment has:  
  - A unique `id`  
  - Required `type` (Enum-based: `"NOR"`, `"OpenField"`, etc.)  
  - A date/time of the experiment  
  - Potentially optional fields like "notes," "time_of_recording," or "length_of_interest"  
- **Batches** group experiments by chosen criteria (date range, experiment type, mouse, etc.).  

### Data Flow

1. **Add subject (mouse)**  
   - Minimal fields: `id` is required (validated by Pydantic).  
   - Optional fields: `sex`, `birth_date`, etc.  

2. **Add experiment**  
   - Must specify `mouse_id` and an **Enum-based** `type` to select the plugin or submodel.  
   - If `type=ExperimentType.NOR`, submodel fields (e.g., `object_roles`) are required.  
   - `DataManager` processes the tracking file, if needed (e.g., `tracking_file_path`).

3. **Create batch**  
   - A set of experiment IDs.  

4. **Run plugin analysis**  
   - The plugin ensures advanced or conditional requirements (e.g., at least two objects for NOR).  
   - May query `MouseMetadata` or `ProjectMetadata` if needed (e.g., genotype, global frame rate).  

---

## Using Pathlib for File Operations

1. **Pathlib in Models**  
   - Where relevant (e.g., DLC config paths in `ProjectMetadata`), store file locations as `Path`.  
   - This makes file operations (`path.exists()`, `path.read_text()`, etc.) more concise and consistent.

2. **Storage & Staging**  
   - A known `project_root: Path` when a user opens/creates a project.  
   - The `ProjectState` or a "ProjectManager" can do `project_root / "experiments"` or `project_root / "subjects"` for JSON files.  
   - All file references (like `tracking_file_path`) can be typed as `Path` in the experiment submodel.

3. **Example**  
   ```python
   from pathlib import Path
   from pydantic import BaseModel

   class DLCConfig(BaseModel):
       path: Path
       version: str = ""

   class ProjectMetadata(BaseModel):
       dlc_configs: list[DLCConfig] = []
       # ... other fields
   ```
   When stored in JSON, Pydantic will handle paths as strings internally, but your code can still use `Path` objects.

---

## Testing Strategy

- **GUI-Level Integration Tests**: Validate typical user workflows (e.g., add experiment with plugin submodel, run analysis).  
- **Core Unit Testing**: Test each plugin and submodel with Pydantic's field-level validation.  
- **Cross-Validation**: In advanced or plugin scenarios, verify that mandatory fields (like "object_roles") are provided before saving.

### Logging Strategy

- Single global log file with session markers  
- Detailed context for debugging test failures, plugin submodel validation issues  

---

## File Organization

- **MUS1's data** (mice, experiments, batches, project-level settings) is saved in **JSON**.  
- **Pydantic** definitions for each core model:  
  - `MouseMetadata` (per mouse)  
  - `ExperimentMetadata` (referencing an `ExperimentType` enum and a submodel)  
  - `BatchMetadata`  
  - `ProjectMetadata` (e.g., DLC config paths, body parts, etc.)  
- **Pathlib** usage**:  
  - In `ProjectMetadata` or submodels referencing file paths (like `tracking_file_path`).  
- **Minimize logic** in metadata classes: they handle only basic field-level validation.  
- **Advanced validation** (like checking whether an NOR experiment has at least two objects) is done in plugin code or in `StateManager`.

---

## Required Data Elements (Summary)

### Mouse Data
- **Required**: `id`, `experiment.type` <- user specifies what type of experiments the mouse underwent (poluated by plugin submodels)
- **Optional**: `sex`, `birth_date`, `genotype`, `treatment`, `notes`, `in_training_set`

### Experiment Data
- **Required**:  
  - `id`  
  - `type` → an `ExperimentType` enum (e.g., `NOR`, `OpenField`)  
  - `mouse_id` (existing mouse)  
  - `date`  
  - A submodel (e.g. `NORPluginParams`) if the experiment's type demands it  
- **Optional**:  
  - Fields like `notes`, `video_file_path`, `length_of_interest`, `arena_image_path`
  - Additional plugin submodel fields (like `object_roles`, phases) if marked optional  

### Project Metadata
- **Required**:  
  - A structure for global settings (e.g. `dlc_configs`, `bodyparts`, `active_bodyparts`, `tracked_objects`, `global_frame_rate`)  
  - see above

### Batches
- **Required**: `id`, plus a list of `experiment_ids`  
- **Optional**: Additional parameters (like name or user-specified grouping criteria)

### Plugins / Submodels
- **Referenced** by `experiment.type` (Enum-based)  
- Each type has a submodel capturing plugin-specific fields (e.g. "object_roles" for NOR).  

---

## Frame Rate Management

1. **Experiment-specific rate** if set in `ExperimentMetadata`.  
2. **Global default** from project settings (60 FPS).  

---

## Application Startup Architecture

1. **Main**: Launches GUI  
2. **StateManager**: Creates or loads `ProjectState` and `ProjectMetadata` (JSON)  
3. **DataManager**: Prepares data processing (e.g., parses DLC CSV, merges body parts)  
4. **GUI**: Binds event handlers to `StateManager`, plugin menu, etc.  

---

## Current Dev Focus

- **Use Enum** to enforce valid experiment types (e.g., "NOR," "OpenField").  
- **Introduce Submodels** for each experiment type to capture specialized fields.  
- **Implement Pathlib** for metadata paths (e.g. DLC config files, tracking file paths).  
- **Moved advanced query logic** from metadata classes, shifting it to  `StateManager` but need to properly implement. 
- **Continue** consolidating `ProjectManager` as point of defining project operations, and `DataManager` as point of technical operations, integration with plugins, and data processing.
- **Validate** advanced, plugin-specific fields in plugin code or the appropriate submodel, rather than in the base metadata classes.
- implement lists of mice, experiments, batches, and batches in the gui and in the state manager with clean up of old code


## current thoughts
- use age calc to figure out n of times mouse went through same experiment and temoral relationship between experiments
- metadata needs to support lists of experiments, experiment types, mice, batches, images and projects
- Use the Native QMainWindow Directly in Your “BaseWidget” and get rid of 'main window'
      example of how to do this:
      from PySide6.QtWidgets import QMainWindow, QTabWidget, QApplication
      from PySide6.QtCore import Qt

         class BaseWidget(QMainWindow):
            def __init__(self):
                  super().__init__()
                  self.setWindowTitle("MUS1")
                  self.resize(1200, 800)
                  self.tab_widget = QTabWidget(self)
                  self.tab_widget.setTabPosition(QTabWidget.West)
                  self.setCentralWidget(self.tab_widget)
                  
                  # Initialize other components, core references, etc.

            def connect_core(self, state_manager, data_manager, project_manager):
                  # Setup references and signals here
                  pass

            # Additional methods for adding tabs, hooking up signals, etc.

            def main() -> int:
         app = QApplication(sys.argv)

         # Initialize your systems (init_core, init_plugins, init_gui, etc.)
         # Create the managers: state_manager, data_manager, project_manager

         # Create the main window directly from BaseWidget
         window = BaseWidget()
         window.connect_core(state_manager, data_manager, project_manager)
         window.show()

         return app.exec()