# MUS1 Architecture Update

## Key Implementations (v0.2) *(Revised on 2/8/2025)*

1. **Unify Data Processing Pipeline (JSON + Pydantic)**  #Not done
   - Single `process_dlc_file()` method in `DataManager`  
   - **Pydantic**-based data models for core validations instead of external YAML schemas for main data.  
   - Uses `Enum` for experiment types (e.g., `"NOR"`, `"OpenField"`), allowing us to cleanly dispatch to the appropriate plugin or submodel.  
   - use enum for sex of mouse
   - Frame rate hierarchy: (1) Experiment-specific > (2) Global default (60).  
   - Centralized duration calculation in `DataManager`.

2. **State Management Improvements**  *(Revised on 2/5/2025-2/9/2025)*
   ```mermaid
   graph TD
       GUI-->StateManager
       StateManager-->ProjectState
       ProjectState-->IndexedQueries
       IndexedQueries-->GUI
   ```
   - `StateManager` coordinates validation and data flow.  
   - `ProjectState` organizes in-memory data (subjects, experiments, batches).  
   - Queries (e.g., listing experiments by mouse) are not moved out of metadata classes and into `StateManager`.  

3. **Validation Strategy**  
   - **Field-Level Validation**: Pydantic ensures required vs. optional fields (e.g. submodels for each experiment type).  
   - **Plugin-Specific or "Submodel" Validation**: For each experiment type, a dedicated Pydantic submodel captures the required parameters (like `object_roles`, `arena_markings`). Cross-field or advanced checks happen in the plugin code or `StateManager`.  
   - **UI Guidance**: Validation results are relayed to the UI so the user can correct issues before data is saved.  

4. **Core Component Responsibilities**  
   | Component          | Responsibilities                                                                                          |
   |--------------------|----------------------------------------------------------------------------------------------------------|
   | **StateManager**   | State mutation, orchestrates validations & updates (plugin submodel checks or advanced checks)           |
   | **DataManager**    | Data processing (e.g. DLC file parsing, basic validation steps), frames/time calculations                |
   | **ProjectState**   | In-memory data store (subjects, experiments, batches), plus indexing                                    |
   | **Plugins**        | Experiment-type-specific checks & calculations (e.g. requiring objects, certain arena markings, etc.)   |

## Lessons Learned

1. **Single Source of Truth**  
   Moving all DLC processing to `DataManager` reduced plugin complexity by ~40%.

2. **Move From YAML to JSON + Pydantic**  
   - Eliminates overhead of maintaining separate schema files  
   - Validation is now consistent and purely in Python (Enum-based type checks, submodels, and advanced validations)  
   - Easier maintenance and debugging

3. **Query Optimization**  
   Indexes in `ProjectState` improved common query performance:
   - e.g., quickly listing all experiments for a given mouse or experiment type

## Next Steps

1. **Plugin Development**  
   - Standardize NOR analysis interface (via dedicated submodel)  
   - Implement Open Field plugin skeleton  
   - Add plugin dependency checks as needed  

**MUS1 in one sentence**:  
*Take a mouse movement file from a third-party app, display it over an arena image, let the user specify analysis options, and then scale that analysis to multiple experiments/subjects.*

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
  - Other optional fields like project name or date created  

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
- **Required**: `id`  
- **Optional**: `sex`, `birth_date`, `genotype`, `treatment`, `notes`

### Experiment Data
- **Required**:  
  - `id`  
  - `type` → an `ExperimentType` enum (e.g., `NOR`, `OpenField`)  
  - `mouse_id` (existing mouse)  
  - `date`  
  - A submodel (e.g. `NORPluginParams`) if the experiment's type demands it  
- **Optional**:  
  - Fields like `notes`, `time_of_recording`, `length_of_interest`, or `arena_image_path`  
  - Additional plugin submodel fields (like `object_roles`) if marked optional  

### Project Metadata
- **Required**:  
  - A structure for global settings (e.g. `dlc_configs`, `bodyparts`, `active_bodyparts`, `tracked_objects`, `global_frame_rate`)  
- **Optional**:  
  - `project_name`, version info, date created  

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
- **Remove advanced query logic** from metadata classes, shifting it to `ProjectState` or `StateManager`.  
- **Continue** removing or consolidating the old `ProjectManager` if desired, possibly letting `StateManager` handle loading/saving.  
- **Validate** advanced, plugin-specific fields in plugin code or the appropriate submodel, rather than in the base metadata classes.
- implement lists of mice, experiments, batches, and batches in the gui and in the state manager with clean up of old code


