# MUS1 Architecture Overview (summary)

Note: See `docs/dev/ARCHITECTURE_CURRENT.md` for the current, authoritative architecture description. This file summarizes intended design and recent changes.

# MUS1 Architecture Overview

## Core Components

### LabManager
- **(New)** Manages lab-level configuration stored in `~/.mus1/labs/` (YAML/JSON format).
- **Lab Resources**: Centralized storage for:
  - Workers (compute nodes with SSH/local/WSL support)
  - Credentials (SSH authentication)
  - Scan targets (local/ssh/wsl scan locations)
  - Master subjects registry
  - **Genotype Configurations**: Gene loci with allele definitions and validation (e.g., ATP7B: WT/Het/KO)
  - Software installations
  - Associated projects
- **(New)** Shared Storage Configuration: Automatic detection and configuration of external drives (like CuSSD3)
- **Project Association**: Links projects to labs for resource inheritance.
- **Persistence**: Atomic YAML/JSON file operations with metadata tracking.
- **(New)** Auto-activation: Automatically loads last activated lab and sets shared storage environment variables
- **(New)** Genotype Validation: Validates subject genotypes against lab genotype configurations with mutual exclusivity

### ProjectManager
- **(Revised)** Orchestrates project-level operations (adding subjects/experiments, running analyses, renaming projects).
- **Lab Integration**: Projects associate with labs via `associate_with_lab()` method.
- **Resource Inheritance**: Projects access lab resources directly via `get_workers()`, `get_credentials()`, `get_scan_targets()`.
- **Simplified Methods**: Removed fallback logic; requires lab association for resource access.
- **(New)** Shared Storage Integration: Automatically uses lab's shared storage when creating projects if a lab is activated with shared storage configured.
- Manages project data persistence by saving/loading the `ProjectState` using JSON serialization (`pydantic_encoder`).
- Coordinates with `PluginManager` to find appropriate tools (plugins) and `DataManager` to facilitate data loading.
- Updates application state via `StateManager` after operations.
- Collaborates with `MainWindow` and `ThemeManager` to apply theme changes.
- **(Revised)** Includes `run_analysis` method to execute specific plugin capabilities on experiments. This method:
    - Finds the relevant analysis plugin based on the requested capability.
    *   Calls the analysis plugin's `analyze_experiment` method, passing it the `ExperimentMetadata` and the `DataManager` instance. **It does NOT pre-load primary data.** The analysis plugin is responsible for requesting data loading via the `DataManager` when needed.
    *   Receives results from the analysis plugin.
    *   Updates `ExperimentMetadata.analysis_results` and `processing_stage`.
    *   Saves the project state and notifies observers.
- **(New)** Includes `run_project_level_plugin_action` to execute plugin capabilities operating at the project level (e.g., importers), often coordinating with handler plugins via the `DataManager`.
- **(Updated)** Local projects root resolves by precedence: explicit arg (where supported) → env `MUS1_PROJECTS_DIR` → per-user config `projects_root` → default `~/MUS1/projects`. Shared projects root resolves by precedence: lab shared storage (if active) → explicit arg → env `MUS1_SHARED_DIR` → per-user config `shared_root`.
- **(Updated)** Video ingestion: `register_unlinked_videos` populates `unassigned_videos` keyed by `sample_hash`; `link_unassigned_video` moves entries into `experiment_videos` using the same key.
- **(Updated)** Core no longer references UI widgets directly; UI passes settings via `apply_general_settings(sort_mode, frame_rate_enabled, frame_rate)`.

### StateManager
- Maintains the in-memory `ProjectState` (single source of truth for project data, including metadata for subjects, experiments, etc.).
- Implements the observer pattern to notify subscribed UI components of state changes.
- Provides access to global settings (e.g., theme preference, sort mode, frame rate) stored within `ProjectState`.
- **(Revised)** Provides unified sorting logic for various metadata lists with the help of Sort Manager . py 

### PluginManager
- **(Revised)** Discovers, registers, and manages tool-based plugins.
- **(New)** Discovery is via Python entry points (group `mus1.plugins`) to allow external plugin packages (e.g., lab-specific assemblies) without in-tree coupling. Discovery is entry-point only.
- **(Revised)** Provides methods to retrieve plugins based on `readable_data_formats`, `analysis_capabilities`, and name. Used by `ProjectManager` for orchestration and by `DataManager` to find appropriate handlers.
- **(Revised)** Registers simplified plugin style manifests (`get_style_manifest`) with `ThemeManager` to allow plugins to define custom CSS variables.

### DataManager
- **(Revised)** Handles generic data I/O operations (reading/writing common formats like CSV, YAML).
- **(Revised)** Resolves global settings (e.g., frame rate, likelihood threshold) from `StateManager` when requested by plugins or handlers.
- **(New)** Provides a `call_handler_method` function. Analysis plugins use this method to request specific data formats (e.g., DLC tracking data). `DataManager` uses `PluginManager` to find the appropriate Handler plugin (e.g., `DeepLabCutHandler`) and invokes a dedicated public helper method on that handler (e.g., `get_tracking_dataframe`) to perform the actual loading, parsing, and pre-processing (like filtering).
- **(Updated)** File hashing is centralized in `mus1/core/utils/file_hash.py` and used by scanners and core logic.
- **(Updated)** Likelihood defaults are resolved from `ProjectState` fields (`likelihood_filter_enabled`, `default_likelihood_threshold`).
- Returns data in standardized formats (e.g., Pandas DataFrame) for plugins to consume, usually via the handler's helper method.
- **(New)** Is project-aware for output paths via `set_project_root` (called by `ProjectManager` on create/load) and `get_experiment_data_path`.
- Does not contain logic specific to third-party formats (delegated to Handler Plugins via `call_handler_method`).

## Component Architecture

```

```

## Command-Line Interface Modernization

MUS1 provides a modern CLI built with Typer, accessible via the `mus1` command (defined as a console-script in pyproject.toml). The CLI is structured in mus1/cli_ty.py and connected via mus1/__main__.py calling the run() function.

Key design decisions:

1. **Single top-level command** – installed as the console-script `mus1` via `pyproject.toml` (GUI launched via `mus1-gui`).
2. **Command groups mirror core managers** – e.g. `mus1 project …`, `mus1 scan …`, so that the CLI surface tracks the responsibility boundaries defined in this document.
3. **Automatic help, prompts & colors** – Typer provides rich `--help`, prompt questions (for missing parameters), validation and error colours out of the box, improving lab usability.
4. **Context injection of core managers** – an app-wide Typer `Context.obj` will hold a singleton `StateManager` / `PluginManager` / `DataManager` bundle so sub-commands can reuse them without global imports. (Planned)
5. **Re-use in scripts** – because Typer is function-oriented (`@app.command`), each CLI entry point doubles as an importable Python function, enabling notebooks and automation pipelines.
6. **Future plug-ins** – plugin modules will be able to register CLI commands by calling `mus1_cli_app.add_typer(plugin_app, name="my-plugin")`, keeping extensibility aligned with the plugin architecture. (Planned)

### Extended Requirements (Lab-Focused)

1. **Lab Management**
   • `mus1 lab create --name <lab_name>` – Create new lab configuration
   • `mus1 lab activate <lab_id>` – Activate lab with automatic shared storage detection
   • `mus1 lab configure-storage` – Configure shared storage for the current lab
   • `mus1 lab load <lab_id>` – Load lab for current session
   • `mus1 lab associate <project_path>` – Associate project with current lab
   • `mus1 lab add-worker --name <name> --ssh-alias <alias>` – Add compute worker to lab
   • `mus1 lab add-credential --alias <alias> --user <user>` – Add SSH credentials to lab
   • `mus1 lab add-target --name <name> --kind <local|ssh|wsl>` – Add scan target to lab

2. **Project Lab Integration**
   • `mus1 project associate-lab <project_path> --lab-id <lab>` – Associate project with specific lab
   • `mus1 project lab-status <project_path>` – Show lab association and inherited resources
   • `mus1 project ingest <project_path> [roots...] [--target ...]` – one-shot scan→dedup→split by shared→preview or stage+register off-shared; uses lab scan targets when available
   • Parallelism: `--parallel --max-workers` supported
   • Auto-host staging in `ingest`: when `shared_root` isn't writable on current host, emit off-shared JSONL for host staging

2. **Scanner progress bar**  
   • `--progress` flag streams a `tqdm` bar to stderr; enabled by default when interactive.
   • **(Updated)** On macOS, if no roots are provided, default scan roots are used (`~/Movies`, `~/Videos`, `/Volumes`).

3. **CLI conveniences and scanners**  
   • Root app supports `--version` to print the installed MUS1 version.  
   • Additional scanning methods are implemented by entry-point plugins (not in-tree modules).
   • Top-level helpers: `mus1 project-help`, `mus1 scan-help` print group help.

4. **Environment & Distribution**  
   • Official install will move to **UV** (`pipx install uv; uv venv; uv pip install mus1`) generating an isolated environment per application.  
   • A *portable* build (`mus1-win64.zip`, `mus1-mac.dmg`) will be produced via PyInstaller for machines without Python.

5. **Compute-backend plugins**  
   • Cluster / NAS integration appears as `ClusterBackendPlugin` inside `plugins/compute/`.  Capabilities: submit job, monitor, sync results via Qsync.


MUS1 ships with an *argparse*-based CLI (`Mus1_Refactor/cli.py`).  To scale
with the growing number of commands and to offer a richer UX the CLI will be
migrated to **Typer** (built on Click).

Key design decisions:

1. **Single top-level command**  – installed as the console-script `mus1` via
   `pyproject.toml`.
2. **Command groups mirror core managers**  – e.g. `mus1 project …`,
   `mus1 scan …`, `mus1 video …`, so that the CLI surface tracks the
   responsibility boundaries defined in this document.
3. **Automatic help, prompts & colors**  – Typer provides rich `--help`, prompt
   questions (for missing parameters), validation and error colours out of the
   box, improving lab usability.
4. **Context injection of core managers**  – an app-wide Typer `Context.obj`
   will hold a singleton `StateManager` / `PluginManager` / `DataManager`
   bundle so sub-commands can reuse them without global imports.
5. **Re-use in scripts**  – because Typer is function-oriented (`@app.command`),
   each CLI entry point doubles as an importable Python function, enabling
   notebooks and automation pipelines.
6. **Future plug-ins**  – plugin modules will be able to register CLI commands
   by calling `mus1_cli_app.add_typer(plugin_app, name="my-plugin")`, keeping
   extensibility aligned with the plugin architecture.

Implementation steps are tracked in *ROADMAP.md*.

### Assembly commands (new)
MUS1 exposes a generic, plugin-driven assembly group:
- `mus1 project assembly list` – list assembly-capable plugins
- `mus1 project assembly list-actions --plugin <name>` – list plugin actions
- `mus1 project assembly run --plugin <name> --action <name> [--params-file|-f] [--param KEY=VALUE]`

Example (Copperlab): `subjects_from_csv_folder` parses a folder of CSV files, normalizes 3-digit subject IDs, reconciles sex, birth/death dates, genotype, and treatment, and returns a structured YAML with `subjects` and `conflicts` for review.

## CLI Design Rules (Lab-Centric Architecture)

1. **Lab-First Workflow**
   - CLI enforces lab-centric workflow: `mus1 lab create` → `mus1 lab add-*` → `mus1 project associate-lab` → project operations
   - Projects require lab association for resource access (workers, credentials, scan targets)
   - No fallback to project-level resources; lab association is mandatory

2. **Single entrypoints**
   - CLI is invoked via `mus1`; GUI is invoked via `mus1-gui`. The CLI does not expose a `gui` subcommand.

3. **Thin CLI, heavy core**
   - CLI commands perform argument parsing, minimal validation, and output. All business logic is owned by core managers (`LabManager`, `ProjectManager`, `DataManager`, `StateManager`) or external plugins discovered through entry points.
   - **Updated**: `LabManager` added as core manager for lab-level operations

4. **Plugin discovery and usage**
   - Plugins are discovered exclusively via Python entry points under the group `mus1.plugins`. No in-tree plugin scanning is used.
   - The CLI never hard-codes plugin details. Plugin-driven operations use generic surfaces, e.g., `mus1 project assembly run --plugin <name> --action <name>`.

5. **Manager lifecycle**
   - Managers are created once per CLI process and cached in Typer's `ctx.obj` (see `_get_managers`). Subcommands reuse them to prevent repeated initialization and to keep behavior uniform.
   - **Updated**: `LabManager` included in manager lifecycle

6. **Output modes and progress**
   - Root flags: `--json`, `--quiet`, `--verbose` apply to all subcommands via `ctx.obj['output']`.
   - Use `typer.echo`/`typer.secho` for text. Use JSON (machine-readable) only when `--json` is set.
   - Progress bars (`tqdm`) are disabled when `--quiet` is set or when stdout is non-interactive.

7. **Errors and exit codes**
   - Use `typer.BadParameter` for invalid user input (exit code 2 by Typer convention).
   - Use `typer.secho(..., err=True)` with red color for error messages.
   - Return exit code 1 for operational failures (e.g., plugin/core error), 2 for configuration/environment issues (e.g., missing lab association), 0 for success.
   - **New**: Exit code 3 for missing lab association errors

8. **Consistent parameter naming and help**
   - Prefer kebab-case options and clear nouns (e.g., `--dest-subdir`, `--library-path`).
   - Each command includes concise examples aligned with README and actual behavior.

9. **Assembly and import flows**
   - The generic assembly group is the single path for project-level plugin actions. Avoid bespoke CLI commands for a specific lab plugin.
   - For third-party importers, use `mus1 project import-supported-3rdparty` instead of ad-hoc commands.

10. **Idempotence and safe preview**
   - Commands that mutate state support preview or no-op paths where practical (e.g., `--dry-run`, JSON output for review) and are safe to re-run.

11. **No GUI coupling**
   - The CLI must not import or initialize GUI components; only import core and plugin APIs.

12. **Truthfulness and single source of truth**
   - Documentation reflects current implemented behavior, not intentions. Version numbers are sourced from `pyproject.toml`.
   - **Updated**: Documentation emphasizes lab-centric workflow and mandatory lab association
---

## Video Discovery & Media Workflow (Updated)

The ingestion path separates discovery from assignment and standardizes media organization under per-recording folders.

Core changes
-------------
DataManager
• **discover_video_files(...)** – generator yielding `(path, hash)` with optional progress callback. 
• **deduplicate_video_list(...)** – removes duplicate hashes, yielding `(path, hash, start_time)`; supports progress callback.
• **scanners package** – `mus1/core/scanners/` houses `BaseScanner` plus OS-specific subclasses (macOS, Linux, Windows) and remote helpers for SSH/WSL.
• **Staging to per-recording folders** – `stage_files_to_shared` creates `project/media/subject-YYYYMMDD-hash8/`, retains original filename, and writes `metadata.json`:
  - `file`: `path`, `filename`, `size_bytes`, `last_modified`, `sample_hash`, optional `full_hash`
  - `times`: `recorded_time`, `recorded_time_source` (csv|mtime|container|manual)
  - `provenance`: `source`, `notes`
  - `processing_history`, `experiment_links`, `derived_files`, `is_master_member`
• **Recorded time policy** – prefer CSV; else mtime; use container only with `--verify-time` when differing.

ProjectState (metadata.py)
```
unassigned_videos: Dict[str, VideoMetadata] = {}
```
Key = `sample_hash` – value is existing `VideoMetadata`.

ProjectManager
• **register_unlinked_videos(iterable)** – populates `unassigned_videos` and persists.  
• **link_unassigned_video(hash, experiment_id)** – moves entry into `experiment_videos` and updates corresponding `ExperimentMetadata.file_ids`.
• **create_experiment_from_recording(...)** – auto-names from recording folder and links media.

CLI mapping (Updated)
```
mus1 scan videos …                        -> DataManager.discover_video_files
mus1 scan dedup                           -> DataManager.deduplicate_video_list
mus1 project scan-and-move …              -> scan, dedup, stage into media per-recording folders, register
mus1 project media-index …                -> index loose files under media and register
mus1 project media-assign …               -> interactive assignment + optional create+link experiment
mus1 project assembly-scan-by-experiments -> CSV-guided subject scan via assembly plugin, stage into media
mus1 project import-third-party-folder    -> copy/move third-party media into project/media with provenance
```

Shared Logging
--------------
`LoggingEventBus.configure_default_file_handler(project_root)` ensures both GUI and CLI write to the same rotating log inside each project directory. Project-aware CLI commands initialize this handler early so logs are captured from the start.

Targets Scanning – via ingest
-----------------------------
`mus1 project ingest --target` supports:
- `--dry-run`: do not register; report counts under shared vs off-shared
- `--emit-in-shared FILE`, `--emit-off-shared FILE`: write JSONL lists for review or later staging

---

## UI Integration

### Observer Pattern
- UI components register observer callbacks with `StateManager` during initialization and unsubscribe on teardown.
- Ensures UI automatically reflects changes in the `ProjectState`.

### Theme Handling Architecture
- Themes are managed via a centralized QSS system (`mus1.qss`).
- **MainWindow** detects theme changes and triggers updates.
- **ThemeManager**:
    - Defines theme color variables (dark/light).
    - Processes `mus1.qss`, substituting theme variables and incorporating minimal variables from plugin manifests (`get_style_manifest`).
    - Applies the final stylesheet to the application.
- **BaseView** propagates theme changes to child components.
- **ProjectView** offers UI for theme selection.

UI components—including `ProjectView`, `SubjectView`, and `ExperimentView`—fetch core managers (e.g., `ProjectManager` and `StateManager`) from MainWindow to access data and operations.
Business logic remains encapsulated in core modules while UI components focus on data presentation and user interactions.
Notably, the project switching widget in `ProjectView` has been refactored:
  - The current project is now displayed above the switch dropdown.
  - The label preceding the dropdown has been changed to "Switch to:" for clarity.

## Best Practices for Uniform UI Styling Using QSS and Centralized Layout Helpers

### 1. Use QSS for Sizing, Padding, and Spacing
- **Remove Explicit Sizing in Code**  
  Avoid hard-coded widget dimensions (e.g., `setFixedHeight`, `setMinimumHeight`). Instead, define these in QSS.
- **Define Consistent Dimensions in QSS**  
  Specify widget dimensions (e.g., 24px height) and line-heights in QSS for key classes:
  - `.mus1-primary-button`
  - `.mus1-secondary-button`
  - `.mus1-text-input`
  - `.mus1-combo-box`
  - `QLabel[formLabel="true"]`

### 2. Rely on Centralized Layout Helpers from BaseView
- **Use BaseView Methods for Layout**  
  Utilize helper methods such as `create_form_section`, `create_form_row`, and `create_form_label` to standardize layouts.
- **Ensure Consistency in Margins and Spacing**  
  These helper methods use layout constants (e.g., `SECTION_SPACING`, `CONTROL_SPACING`, `FORM_MARGIN`) to ensure uniform appearance.

### 3. Standardize QSS Rules for Widgets
- **Label Styling**  
  For `QLabel[formLabel="true"]`, define consistent `min-height`, `height`, and `line-height` (e.g., 24px).
- **Input and ComboBox Consistency**  
  Ensure inputs and combo boxes share matching padding and dimensions.
- **Form Row Sizing**  
  Use QSS to enforce uniform minimum heights for form rows.
- **Button Uniformity**  
  Primary and secondary buttons should use consistent padding, border-radius, and alignment to align with accompanying inputs and labels.

### 4. Remove Redundant or Conflicting Code
- **Avoid Duplicate Styling in Code**  
  Remove hard-coded styling (e.g., `setFixedHeight`, `setAlignment`) in favor of centralized QSS definitions.
- **Maintain a Single Source of Truth**  
  Rely exclusively on the stylesheet for size, padding, and margin definitions to prevent conflicts.

### 5. Load Your Stylesheet Last
- **Apply QSS After Widget Creation**  
  Ensure the stylesheet is applied after all UI components are created so every element fully picks up the standardized styles.

## Benefits of Adopting These Best Practices
- **Centralized Adjustments**  
  Central control over sizing and spacing simplifies design updates and ensures consistency.
- **Uniform Appearance Across Components**  
  Standardized helper functions and QSS guarantees that even complex layouts maintain uniform margins and padding.
- **Elimination of Conflicting Code**  
  Removing redundant hard-coded styles eliminates conflicts and ensures reliable, predictable UI rendering.
- **Maintainability and Predictability**  
  A centralized styling approach allows for single-point updates, easing future maintenance efforts.

## Dynamic Form Generation
- **(Revised & Implemented)** ExperimentView dynamically generates parameter forms based on selected plugins' fields.
- **(Revised & Implemented)** Handles file paths required by plugins primarily through parameters of type `'file'` or `'directory'` within the plugin's `required_fields` or `optional_fields`. This uses UI widgets like file browsers linked to the parameter input. `ExperimentMetadata.plugin_params` stores these paths.
- **(Revised & Implemented Workflow):**
    1.  **Core Details:** User selects `Subject ID`, `Experiment Type`, and enters `Experiment ID`, `Date Recorded`.
    2.  **Plugin Selection:** UI dynamically displays available Data Handler plugins (capability: `load_tracking_data`) and Analysis plugins (other capabilities, filtered by selected `Experiment Type`). User selects one Handler (optional) and one or more Analysis plugins.
    3.  **Parameter Entry:** As the user selects/deselects plugins, the required/optional parameters for *each* selected plugin are dynamically displayed in the "Plugin Parameters" section using appropriate widgets (LineEdit, ComboBox, File/Directory browsers, etc.). Required fields are marked.
    4.  **Saving:** `handle_add_experiment` collects core details, associated plugin names, and the structured `plugin_params` (including file paths). It infers an initial `processing_stage` and calls `ProjectManager.add_experiment`. The 'Add' button is only enabled when core details and all required plugin parameters are filled.
- **(Revised & Implemented)** `ExperimentView._discover_plugins` finds data handlers via `load_tracking_data` capability and analysis plugins by listing those with capabilities beyond just data loading *and* matching the selected `Experiment Type`.

## Plugin Architecture

### Tool-Based Plugins & Specialization
- **(Revised)** Plugins represent data processing/analysis tools or specialized interfaces. They adhere to the `BasePlugin` interface.
- **Handler Plugins:** Specialized plugins (e.g., `DeepLabCutHandlerPlugin`, future `SleapHandlerPlugin`, `RotarodDataHandlerPlugin`, `BiochemDataHandlerPlugin`) encapsulate all knowledge required to read, parse, validate, pre-process, and potentially write specific complex data formats or simple tabular data (like CSVs). They declare `'file'` type parameters for necessary input files. They typically provide `load_data` or similar capabilities and often include public helper methods (e.g., `get_tracking_dataframe`) that `DataManager` calls to perform the actual data loading and processing.
- **Analysis Plugins:** Plugins (e.g., `Mus1TrackingAnalysisPlugin`, `KeypointMoSeqAnalysisPlugin`) implement specific analysis algorithms. They declare their data dependencies via `plugin_params`. Inside their `analyze_experiment` method, they load required data *on demand* (using `DataManager` generic methods or `call_handler_method`) and perform computations, storing results in `ExperimentMetadata.analysis_results`.
- **(Revised) Importer Plugins:** Specialized plugins (e.g., `DlcProjectImporterPlugin`) focused on importing entire project structures or specific configurations.
- **(New) Results Viewer Plugins:** Specialized plugins (e.g., `MoSeq2ResultsViewerPlugin`) designed *not* to run an external process, but to load, parse, and extract key features or results from files generated by external tools (like MoSeq2). They store extracted data in `ExperimentMetadata.analysis_results`.
- **(Future) Inference Plugins:** Plugins (e.g., `DiseasePredictionPlugin`) designed to load a pre-trained machine learning model, gather the necessary input features (from `analysis_results` of various associated experiments for a subject), run inference, and store the prediction back into `ExperimentMetadata.analysis_results` or `SubjectMetadata`.
- **(Future) Interface Plugins:** Plugins providing specific UI or functionalities (e.g., `NapariLabelerPlugin`).
- Plugins declare `readable_data_formats` and `analysis_capabilities`. `PluginManager` uses this information for filtering and discovery.

### Plugin Parameter Conventions (New Section)
To promote consistency and interoperability between plugins, especially Handlers and Analyzers:
*   **File Paths:** Use descriptive names ending in `_file_path` for required input files (e.g., `tracking_file_path`, `config_file_path`, `video_file_path`). Define these with type `'file'`. Handler plugins typically define these.
*   **Directories:** Use names ending in `_directory` for output locations (e.g., `output_directory`, `frames_directory`). Define with type `'directory'` (or `'file'` if a specific output file is needed).
*   **Common Analysis Params:** Strive for common names for similar concepts where applicable (e.g., `likelihood_threshold`, `arena_dimensions`, `frame_rate`).
*   **Naming:** Use `snake_case` for all parameter names.

### Experiment Processing Stage
- **(Revised)** `ExperimentMetadata` includes a `processing_stage` field (e.g., "planned", "recorded", "tracked", "interpreted") defaulting to "planned".
- **(Revised Logic):**
    *   Serves primarily as a visual indicator and filtering aid in the UI.
    *   Can be set manually by the user during experiment creation/editing to reflect the known state of externally processed data.
    *   Can be inferred by `ProjectManager.add_experiment` based on the types of files provided via Handler plugin parameters (e.g., video file -> "recorded", tracking file -> "tracked"), if not set manually.
    *   Is automatically updated by MUS1 (`ProjectManager.run_analysis`) to reflect the stage *completed* by the last successful analysis run within the application.
    *   Core application logic (e.g., enabling analysis buttons) should validate based on the actual presence and format of required data files and parameters for the *specific capability*, not solely rely on the `processing_stage`.
- Stage is visually indicated in the UI using QSS properties (e.g., `QWidget[processingStage="tracked"]`) and colors defined in `ThemeManager`.

### Plugin UI Styling System
- **(Revised)** Relies on the central `mus1.qss` stylesheet and `ThemeManager`.
- Plugins have minimal direct styling influence, primarily via `get_style_manifest` defining CSS variables if needed.
- Complex methods (`get_styling_preferences`, `get_field_styling`) have been removed from `BasePlugin`.
- Required fields in plugin parameter forms are indicated using a standard QSS property (`QWidget[fieldRequired="true"]`) set by `ExperimentView` and styled globally via `$PLUGIN_REQUIRED_COLOR` in `ThemeManager`.

## Data Management

### Metadata Models
- Defined using Pydantic for validation.
- **(Updated)** `ExperimentMetadata` now includes `associated_plugins` (list of names) and `plugin_params` (nested dict) for parameters and file paths. `data_files` field removed for primary file handling. `analysis_results` stores outputs keyed by capability. `processing_stage` tracks status.

### Validation
- **(Updated & Refined)** Multi-level validation approach:
    *   **UI (`ExperimentView` - Add Time):** Performs immediate feedback. Checks that core details (`Experiment ID`, `Subject ID`, `Experiment Type`) are selected/entered. Checks that at least one plugin is selected. Checks that all fields defined as `required_fields()` by the *currently selected plugins* have non-empty values before enabling the "Add Experiment" button (`_update_add_button_state`). May perform basic format checks (e.g., numbers). *(Implementation complete)*
    *   **Pydantic Models (`metadata.py` - Add/Load Time):** Enforces data types, required model fields, and basic value constraints automatically on object creation/parsing.
    *   **Core Logic (`ProjectManager` - Add Time):** Enforces business rules like unique IDs (experiments, subjects), existence of related entities (e.g., `subject_id` must exist when adding an experiment).
    *   **Plugin (`validate_experiment` - Pre-Analysis):** Called by `ProjectManager` immediately *before* invoking a specific `analyze_experiment` capability. Performs deep, context-aware validation of the specific parameters stored in `plugin_params` required for *that capability*. Checks if prerequisites (e.g., arena data for zone analysis, valid kp-MoSeq config file) are available and valid. Raises `ValueError` on failure, preventing the analysis from running. *(Implementation pending for most plugins)*

### Data Loading (New/Revised Section)
- **Orchestration:** The `DataManager` orchestrates loading of complex, format-specific data, often via Handler plugins.
- **Request:** Analysis, Viewer, or Inference plugins request data. For complex formats, they typically call `DataManager.call_handler_method`, specifying the Handler plugin name and desired helper method. For simpler formats (like CSV via a Handler or directly), they might use generic `DataManager.read_csv`.
- **Execution:** `DataManager` finds the Handler instance (via `PluginManager`) and calls the requested method, or performs the generic read directly.
- **Handler Responsibility:** The Handler plugin's method reads, parses, preprocesses (if needed), and returns data in a standardized format.
- **Benefits:** Encapsulates format logic, simplifies other plugins, promotes modularity.

## Batch Management System

### Experiment Grid Selection
- Provides a UI for batch creation with selectable experiment grids.
- Updated dynamically via the observer pattern in StateManager.

### Status Tracking
- Batch operations, including creation, deletion, and updates, are uniformly managed by ProjectManager and StateManager.
- The observer pattern ensures that any state change automatically triggers UI refreshes.

## UI Component Patterns

### Widget Box Pattern
- Uses QGroupBox with standard styling
- Contains related UI elements

### Multi-Column Widget Pattern
- Side-by-side column layout within a widget box
- Used for comparison or selection interfaces

### Notes Widget Pattern
- Expandable text field for user notes
- Connects to state management system
- Expands vertically when focused this is still a to do 

## CSS System

### Variable Structure
- **Base variables**: Font, colors, spacing
- **Component variables**: Derived from base variables
- **Theme-specific variables**: Defined with variable substitution

### Theme Switching
- Uses CSS variables for theme definition in theme manager with qss stylesheet
- BaseView propagates theme to all children
- MainWindow is the central point for theme changes

## Current Status

### Recently Completed (Refactoring)
- ✅ Shifted to tool-based plugin architecture (`Mus1TrackingAnalysisPlugin`).
- ✅ Added `readable_data_formats` and `analysis_capabilities` to plugin definition.
- ✅ Refactored `BasePlugin` and `PluginManager` (updated signatures, new filtering, removed obsolete methods).
- ✅ Centralized and simplified UI styling:
    - Removed complex plugin styling methods.
    - Unified stage styling using `processingStage` property and `ThemeManager` colors.
    - Unified required field styling using `fieldRequired` property and `ThemeManager` color.
    - Cleaned up `ThemeManager` logic.
- ✅ Updated `ExperimentMetadata` (`data_files` removed, `plugin_params` added, `analysis_results`, `processing_stage` default).
- ✅ Added interpolation logic (`handle_gaps`) to `Mus1TrackingAnalysisPlugin`.
- ✅ Strengthened validation in Pydantic models and `ProjectManager`.
- ✅ Fixed core manager initialization errors preventing application startup.
- ✅ **Refactored `ExperimentView` (Add Experiment Page):**
    - ✅ Implemented new workflow (Subject -> Type -> Plugin Lists -> Params).
    - ✅ Implemented dynamic plugin discovery (`_discover_plugins`) based on capabilities and type.
    - ✅ Implemented dynamic parameter form generation (`update_plugin_fields`) with file/dir browsers.
    - ✅ Implemented UI validation (`_update_add_button_state`) checking core details and required plugin params.
    - ✅ Updated `handle_add_experiment` to collect nested `plugin_params` and infer initial stage.
- ✅ Added `run_project_level_plugin_action` and refined `update_master_body_parts` in `ProjectManager`.
- ✅ Standardized default projects directory; macOS default scan roots; unified hash-keying of videos; improved CLI help; added `scan-and-add` command.
- ✅ Drafted `DlcProjectImporterPlugin` structure using new `ProjectManager` methods.
- ✅ Outlined plan for integrating Keypoint-MoSeq as a MUS1 plugin.
- ✅ Drafted `KeypointMoSeqAnalysisPlugin` skeleton structure.
- ✅ Updated `README.md` and `requirements.txt` for kp-MoSeq integration.

### Outstanding Tasks (High Priority)
- **Implement `ProjectManager.run_analysis`:** Add the orchestration logic to find plugins by capability, load data via `DataManager` (or Handler helpers using file paths from `plugin_params`), call `validate_experiment`, execute `analyze_experiment`, and update state (`analysis_results`, `processing_stage`).
- **Implement `DeepLabCutHandlerPlugin`:** Ensure it can correctly read DLC formats based on provided file path parameters (`tracking_file_path`, `config_file_path`) via its helper functions or `analyze_experiment` for loading. Ensure its `extract_bodyparts` capability works correctly for use by importer plugins.
- **Implement `KeypointMoSeqAnalysisPlugin`:** Implement the core logic to load data, configure, fit, and extract results from the Keypoint-MoSeq library based on plugin parameters. *(New High Priority Task)*
- **Implement `DlcProjectImporterPlugin`:** Finalize and test the plugin to import DLC body parts via the Handler and update `ProjectMetadata.master_body_parts`.
- **Implement Plugin Validation:** Implement `validate_experiment` methods in `Mus1TrackingAnalysisPlugin`, `DeepLabCutHandlerPlugin`, `KeypointMoSeqAnalysisPlugin`, and `DlcProjectImporterPlugin`. *(Updated scope)*
- **Refine Analysis Capabilities:** Implement/test specific analysis logic within `Mus1TrackingAnalysisPlugin` (e.g., NOR, OF metrics).
- **Finalize DataManager Helpers:** Ensure `DataManager` provides necessary generic file reading methods (CSV, YAML, HDF5) and potentially path management helpers for analysis outputs.
- **Refactor `ExperimentView` (Remaining Pages):** Update "View Experiments" and "Create Batch" pages to use `MetadataGridDisplay`, display `processing_stage`, and ensure filtering works.
- **QSS Rule Refinement:** Ensure `mus1.qss` correctly targets `processingStage` and `fieldRequired` properties.
- **Cleanup Legacy Code:** Remove deprecated/unused methods and fields.

## Recent Updates
- **(Updated)** Major refactoring of the plugin system to a tool-based architecture (`Mus1TrackingAnalysisPlugin`, `DeepLabCutHandlerPlugin`).
- **(Updated)** Simplified and centralized the UI styling system.
- **(Updated)** Refined manager roles (`ProjectManager`, `PluginManager`, `DataManager`).
- **(Updated)** Updated `ExperimentMetadata`.
- **(Updated)** Improved validation framework (UI + Pydantic).
- **(New)** Decided Handler Plugins define file path parameters; Analysis plugins use helpers or `DataManager`.
- **(New & Implemented)** Refined ExperimentView workflow: Subject/Type -> Handler/Analysis Plugin Selection -> Dynamic Parameter Forms.
- **(New)** Defined conventions for plugin parameter names.
- **(New)** Clarified logic for `processing_stage` updates and usage.
- **(New)** Refined conceptual plugin structure (Handler, Analyzer, Importer, Interface types).
- **(New)** Resolved core manager initialization errors.
- **(New & Implemented)** Implemented dynamic plugin discovery and parameter form generation in `ExperimentView`.
- **(New & Implemented)** Implemented UI validation for required fields in `ExperimentView`.
- **(New)** Integrated Keypoint-MoSeq as a planned core analysis plugin (`KeypointMoSeqAnalysisPlugin`).
- **(New)** Updated `README.md` and `requirements.txt` to reflect kp-MoSeq integration plan.
- **(New)** Added project-level plugin execution capability to `ProjectManager`.

## Open Questions & Next Steps

This section outlines current points needing decisions or further work and suggests areas for future development focus.

**Open Questions & Considerations:**

*   **Analysis Capability Selection UI (Future):** How should users select *which* capability of an analysis plugin to run if it offers multiple? *(Plan: Future Analysis tab/view will likely offer dropdowns/buttons.)*
*   **Processing Stage Inference:** Should the initial `processing_stage` inference logic be more robust? *(Decision: Current basic inference is acceptable for now.)*
*   **Legacy Metadata Fields:** Review and remove `ExperimentMetadata.data_source` and `ExperimentMetadata.file_ids`. *(Decision: Mark for removal)*.
*   **Keypoint-MoSeq Results Handling:** How should detailed kp-MoSeq results (e.g., model checkpoints, parameters beyond syllable sequence) be stored and accessed within MUS1? How best to visualize syllable sequences and related kp-MoSeq outputs in the UI? *(New - Future Consideration)*
*   **kp-MoSeq Output Paths:** Ensure `KeypointMoSeqAnalysisPlugin` correctly uses project/experiment-specific paths provided by `DataManager`/`ProjectManager` for saving its internal files (`results.h5`, `checkpoint.h5`). *(New - Implementation Detail)*

**Relationships to Consider:**

*   **Experiment Configuration:** `ExperimentMetadata` links `associated_plugins` (names) to parameters (`plugin_params`).
*   **Plugin Interface:** `BasePlugin` defines contract; `PluginManager` manages plugins.
*   **Analysis Orchestration (`run_analysis`):** Finds plugin, validates, calls `analyze_experiment`, updates state.
*   **Data Loading:** Analysis Plugins request complex data via `DataManager.call_handler_method`. `DataManager` uses `PluginManager` to find the Handler and calls its public helper method (e.g., `DeepLabCutHandler.get_tracking_dataframe`) to load and process the data.
*   **Keypoint-MoSeq Integration:** `KeypointMoSeqAnalysisPlugin` acts as an Analysis Plugin, consuming tracking data (via Handler/DataManager) and producing syllable sequence results.
*   **UI-Core Interaction:** UI uses Managers for discovery/actions, `StateManager` for updates.

**Potential Next Areas for Codebase Focus (Revised Priority):**

1.  **Implement `ProjectManager.run_analysis`:** Essential for executing *any* analysis plugin. *(High Priority)*
2.  **Implement `DeepLabCutHandlerPlugin` & `DataManager` Helpers:** Needed to provide data access for downstream analysis plugins. *(High Priority)*
3.  **Implement `KeypointMoSeqAnalysisPlugin`:** Core implementation of the kp-MoSeq fitting workflow within the plugin structure. *(High Priority)*
4.  **Implement Plugin Validation Methods:** Crucial for robust analysis execution (`validate_experiment` for DLC Handler, kp-MoSeq, Kinematics plugins). *(High Priority)*
5.  **Implement `DlcProjectImporterPlugin`:** Enable project setup from existing DLC projects. *(Medium-High Priority)*
6.  **Implement `Mus1TrackingAnalysisPlugin` Capabilities:** Flesh out standard kinematic analyses. *(Medium Priority)*
7.  **Refactor `ExperimentView` (Other Pages):** Update remaining UI sections. *(Medium Priority)*
8.  **Cleanup Legacy Code:** Remove deprecated code/fields. *(Low Priority)*

## Multimodal Machine Learning Support (New Section)

MUS1 is designed to serve as a central hub for organizing and preprocessing diverse data types required for training and running multimodal machine learning models aimed at prediction tasks (e.g., genotype, survival time, disease status).

- **Role of MUS1:** Data management, standardized preprocessing, and feature extraction via plugins. It aggregates data but does not perform the ML model training itself.
- **Feature Extraction:** Plugins (Handlers, Analyzers, Viewers) are responsible for processing their respective data sources (video tracking, MoSeq2 results, Rotarod CSVs, biochemical data) and extracting relevant features.
- **Centralized Feature Storage:** Extracted features from all sources associated with an experiment are stored in the `ExperimentMetadata.analysis_results` dictionary, keyed by the generating plugin/capability.
- **Target Variable Storage:** Prediction targets (ground truth labels like genotype, survival days) are typically stored in `SubjectMetadata`.
- **Data Aggregation for Training:** A separate, external script is used to:
    - Load the `ProjectState` using MUS1's core modules.
    - Iterate through subjects and their experiments.
    - Select and pull the specific required features from various `analysis_results` dictionaries and target variables from `SubjectMetadata`.
    - Align and structure these features into a format suitable for ML frameworks (e.g., Pandas DataFrame).
    - Export this aggregated dataset (e.g., to CSV).
- **ML Model Training:** Training is performed externally using standard ML libraries (PyTorch, TensorFlow, scikit-learn) on the dataset exported from MUS1.
- **Inference Workflow:**
    1.  **Process New Data:** New subject/experiment data is added to MUS1 and processed using the *same* set of feature-extraction plugins used for the training data.
    2.  **Extract Features:** An external script (or potentially an Inference Plugin) gathers the required features for the new subject from their `analysis_results`.
    3.  **Run Inference:** The pre-trained model is loaded (externally or by an Inference Plugin) and generates predictions based on the extracted features.
    4.  **Store Predictions:** Predictions are stored back into MUS1, typically in the `analysis_results` of a relevant experiment or potentially updating `SubjectMetadata`, allowing them to be viewed and managed within the MUS1 context.
- **Consistency:** Using the same MUS1 plugins for feature extraction for both training and inference ensures consistency and reproducibility.

This document serves as a comprehensive reference for developers to understand the architecture and implementation details of MUS1.

## Multi-Machine Collaboration & Remote Compute Plan (NEW)

1. **Shared Network Project Directory** – store the MUS1 project folder on an SMB or NFS share that every workstation can mount (e.g., `/mnt/mus1`, `Z:\MyProj`). `ProjectManager.save_project` will implement a small `.mus1-lock` advisory file so concurrent writes are safe.
2. **Reproducible Environments with UV** – on macOS, Ubuntu, and WSL run:
   ```bash
   pipx install uv
   git clone <your-repo>
   cd mus1 && uv venv .venv && source .venv/bin/activate
   uv pip install -r requirements.txt
   uv pip install -e .
   ```
   This guarantees the same Python (≥3.10) and exposes the `mus1` CLI everywhere.
3. **Cross-Platform Typer CLI** – existing commands in `cli_ty.py` (`mus1 scan …`, `mus1 project …`, `mus1 gui`) already work on all OSes.
4. **SSH Backend Plugin (Phase-1)** – add `ClusterBackendPlugin` inside `plugins/compute/` with capabilities:
   * `submit_job(cmd, project_path)` – `ssh user@host 'python -m mus1 …'`
   * `monitor_job(job_id)`
   * `sync_results(job_id)` – `rsync` back result folders.
   Heavy kp-MoSeq fits can thus be off-loaded to the Ubuntu workstation while metadata stays consistent.
5. **Optional SQLite → Postgres Migration (Phase-2/3)** – if file-locking proves limiting, swap JSON persistence for SQLite in the share, and later move to Postgres hosted on the workstation with DSN configured in `mus1.toml`.
6. **Daily Lab Workflow** –
   1. Mount the share on each machine.
   2. Pull latest code from GitHub on whichever box will run the job.
   3. Activate the UV environment.
   4. Run the GUI (`mus1 gui`) or CLI locally, or `mus1 remote submit … --host ubuntu-server` to off-load compute.

_This phased roadmap enables immediate cross-machine collaboration, leverages the existing CLI, and scales toward a database-backed multi-user setup without blocking current work._

End of file

## 2025-07 Refactor Snapshot (UI & Core)

### ExperimentView Updates
* Navigation now offers **Add Experiment**, **Add Multiple Experiments**, **View Experiments**, **Create Batch**.
* Plugin selection area is split into three group-boxes:
  * **Importer Plugins** (data handlers such as `DeepLabCutHandler`).
  * **Analysis Plugins**.
  * **Exporter Plugins**.
* Parameter widgets for each plugin are wrapped in a collapsible `QGroupBox`, eliminating field overlap and improving readability.
* New field-types supported by dynamic form generator:
  * `text` → multiline `QTextEdit`.
  * `dict` → JSON-oriented `QTextEdit`.
* "Add Multiple Experiments" page provides a table where users can batch-enter core metadata and optional video path; rows are persisted via `ProjectManager.add_experiment` and `link_video_to_experiment`.
* Date-time conversion is now version-safe (`QDateTime.toPython()` fallback).

### Core Contract Changes
* `ProjectManager.add_experiment` immediately calls `save_project()` after inserting the new metadata, ensuring persistence without UI involvement.
* DeepLabCutHandler’s `validate_experiment` enforces the presence of `tracking_file_path` **only** once an experiment’s `processing_stage` ≥ `tracked`.  UI therefore accepts “planned/recorded” experiments without the DLC file.
* Experiment stages remain a string enum (`planned`, `recorded`, `tracked`, `interpreted`) stored solely in `ExperimentMetadata`.  A future task (see Roadmap) will expose a canonical stage list from the core layer so UIs no longer hard-code it.

### Upcoming Responsibility Separation (agreed)
* Move reusable helpers currently in `ExperimentView` (sample-hash computation, video path browse helpers, etc.) into `DataManager` / `ProjectManager`.
* UI will request the canonical stage list from `StateManager` instead of defining `PROCESSING_STAGES` locally.
* Video-related convenience utilities (e.g., suggested experiment ID from video filename, automatic stage inference) will be centralised in `ProjectManager`.