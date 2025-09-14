### MUS1 Architecture — Current State (authoritative)

This document describes how MUS1 works today based on the code, including gaps and quirks.

## Core modules

 - **ConfigManager** (`src/mus1/core/config_manager.py`) **[NEW]**
  - Unified configuration system with SQLite-based persistence
  - Hierarchical configuration with precedence: Runtime > Project > Lab > User > Install
  - Handles migration from old scattered YAML/JSON configurations
  - Provides atomic operations and proper error handling
  - Manages all MUS1 settings in a single, centralized database

 - **ConfigMigrationManager** (`src/mus1/core/config_migration.py`) **[NEW]**
  - Migrates from old scattered configuration files to new unified system
  - Automatic detection and migration of existing YAML/JSON configs
  - Environment variable migration support
  - Backward compatibility maintained during transition
  - deletes old configuration files after migration and only retains the new unified system
  - get rid of migration manager after we use it for testing and validation by trying to use during migration
  

 - LabManager (`src/mus1/core/lab_manager.py`)
  - **REFACTORED:** Now uses ConfigManager instead of YAML/JSON files
  - Stores shared resources: workers (compute), credentials (SSH), scan targets (local/ssh/wsl), master subjects, software installs
  - Manages shared storage configuration with automatic drive detection
  - Manages genotype configurations with validation (e.g., ATP7B: WT/Het/KO with mutual exclusivity)
  - Provides methods to associate/disassociate projects with labs
  - Handles lab metadata, creation, loading, and persistence
  - Auto-loads last activated lab and sets shared storage environment variables

 - ProjectManager (`src/mus1/core/project_manager.py`)
  - **REFACTORED:** Uses ConfigManager for path resolution and settings
  - Creates/loads/saves projects (`project_state.json`) under a projects root resolved via ConfigManager
  - Supports lab-based shared storage - when a lab is activated with shared storage configured, projects automatically use the shared storage location
  - Saves use a lightweight advisory lock file `.mus1-lock` and atomic temp-file rename to reduce concurrent write conflicts on shared storage
  - Lab Integration: Projects can associate with labs via `associate_with_lab()` method. Once associated, projects inherit lab-level resources (workers, credentials, scan targets) directly without fallbacks
  - Simplified Resource Access: Removed fallback methods; projects now use `get_workers()`, `get_credentials()`, `get_scan_targets()` which require lab association and return lab resources directly
  - Discovers plugins via Python entry points using `PluginManager.discover_entry_points()` (group `mus1.plugins`). Discovery is entry-point only; in-tree scanning has been removed from defaults
  - Orchestrates analysis via `run_analysis(experiment_id, capability)`:
    - Looks up the experiment and a plugin whose `analysis_capabilities()` includes the capability
    - Calls `plugin.validate_experiment(experiment, project_state)`
    - Calls `plugin.analyze_experiment(experiment, data_manager, capability)`
    - On success: stores results under `experiment.analysis_results[capability]` and advances `processing_stage` to `tracked` for data-load capabilities or `interpreted` for analyses
  - Video workflow:
    - `register_unlinked_videos(paths_with_hashes)` populates `ProjectState.unassigned_videos` keyed by `sample_hash`
    - `link_unassigned_video(hash, experiment_id)` moves a video to `experiment_videos` and updates `ExperimentMetadata.file_ids`
    - `link_video_to_experiment(experiment_id, video_path, notes)` adds metadata about a file directly to an experiment using `DataManager.compute_sample_hash`
    - `move_project_to_directory(new_parent_dir)` relocates an entire project folder (e.g., local → shared)

- PluginManager (`src/mus1/core/plugin_manager.py`)
  - Holds registered plugin instances
  - Discovers external plugins via Python entry points (`discover_entry_points`), avoiding in-tree coupling by default
  - Indexes plugins by `readable_data_formats()` and `analysis_capabilities()` for quick lookup
  - Provides UI-oriented helpers for importer/analysis/exporter lists

 - DataManager (`src/mus1/core/data_manager.py`)
  - Generic IO: `read_yaml`, `read_csv`, `read_hdf` (DLC-friendly checks/warnings)
  - Settings helpers: `resolve_likelihood_threshold`, `resolve_frame_rate`
  - Handler invocation: `call_handler_method(handler_name, method_name, **kwargs)` and automatic `data_manager` injection when required
  - Experiment output paths: `get_experiment_data_path(experiment)` for plugins to persist outputs under `<project>/data/<subject>/<experiment>/`. DataManager is made project-aware via `set_project_root` called by `ProjectManager` on create/load
  - Video discovery: delegates to scanners via `get_scanner().iter_videos(...)`
  - Staging: `stage_files_to_shared(src_with_hashes, ...)` now creates per-recording folders under `project/media/subject-YYYYMMDD-hash8/`, writes `metadata.json` (hashes, recorded_time with source, provenance, history), and yields tuples for registration. `--verify-time` prefers container metadata only when it differs from mtime
  - Cross-target scanning: `project scan-from-targets` aggregates local/SSH/WSL targets, deduplicates, and can preview/emit JSONL

 - StateManager (`src/mus1/core/state_manager.py`)
  - **REFACTORED:** Uses ConfigManager for global settings and theme preferences
  - Maintains the in-memory `ProjectState` (single source of truth for project data, including metadata for subjects, experiments, etc.)
  - Implements the observer pattern to notify subscribed UI components of state changes
  - Provides access to global settings stored in ConfigManager with fallbacks to project state
  - Manages theme preferences using ConfigManager with automatic persistence

- Metadata models (`src/mus1/core/metadata.py`)
  - Pydantic models for Subjects, Experiments, Batches, Videos, ProjectState
  - Central stage enum exists; `ExperimentMetadata.processing_stage` is stored as a string with default "planned"
  - `ProjectState` holds videos under both `unassigned_videos` and `experiment_videos`, keyed by `sample_hash`
  - Typed fields for multi-machine workflows: `shared_root: Optional[Path]`, `workers: List[WorkerEntry]`, `scan_targets: List[ScanTarget]`

## Plugins (external packages)

- Handler: `mus1-plugin-deeplabcut-handler` (public)
- Importer: `mus1-plugin-dlc-importer` (public)
- Analysis: `mus1-plugin-tracking-analysis` (public)
- Importer: `mus1-plugin-moseq2-importer` (public)
- **Enhanced Assembly (lab-specific)**: `mus1-assembly-plugin-copperlab` (private, editable for dev) - Now supports iterative subject extraction with confidence scoring, genotype normalization (ATP7B: WT/Het/KO), and experiment type validation (RR/OF/NOV with subtypes)
- Skeleton: `mus1-assembly-skeleton` (public template)

Notes: In-tree plugin implementations were removed. Only the interface remains under `src/mus1/plugins/base_plugin.py`. Real plugins are external packages discovered via entry points.

## UI touchpoints

- `ExperimentView` dynamically builds forms from plugins’ `required_fields`/`optional_fields` using `get_field_types()` and `get_field_descriptions()`.
- File dialogs use generic filters; allowing plugin-provided filters is a useful enhancement.
- Metadata display grids implement sort-key aware sorting for experiments; subject grid can adopt the same pattern.
- `ProjectView` includes:
  - Project Settings: set `shared_root` and "Move Project to Shared" (uses `ProjectManager.move_project_to_directory`).
  - Scan & Ingest: select targets, scan, view totals/unique/off-shared, add unique under shared, or stage off-shared into a subdirectory under `shared_root`.
  - Workers tab: CRUD for `ProjectState.workers`.
  - Targets tab: CRUD for `ProjectState.scan_targets`.

## Scanners

- macOS scanner: filters out iCloud placeholders and zero-sized files; uses `compute_sample_hash` per file.
- Windows/Linux: specialized scanners are present with conservative exclusions; parity improvements remain planned.
- Remote scanning aggregator (`src/mus1/core/remote_scanner.py`):
  - Local: calls `DataManager.discover_video_files`.
  - SSH: runs remote `mus1 scan videos` via `ssh` and parses JSONL.
  - WSL: runs `wsl.exe -e mus1 scan videos` on Windows hosts over SSH.

## Known gaps/bugs (truthful)

- Prefer canonical stage list from metadata and capability/format indices; avoid legacy `PluginManager` shims. Entry-point discovery is the single discovery path. The CLI exposes `plugins list|install|uninstall` to manage external plugin packages registered via `mus1.plugins`.
- DeepLabCut handler likelihood filtering depends on `numpy`; ensure import stays present to prevent runtime errors.
- Server-backed MoSeq2 orchestration is planned; current GCP-based orchestrator is deprecated.
- `Mus1TrackingAnalysisPlugin` has duplicated private helpers; consolidate to reduce confusion.
- Remote scans require MUS1 installed on remote PATH (or inside WSL); document and validate during setup.
- GUI scan summary is basic; per-target progress and error surfacing are planned.
 - Project-aware CLI commands initialize project logging early; remaining legacy commands may still print a missing FileHandler warning until consolidated.

## Recent CLI additions (Lab-focused Architecture)
- **Lab Management**: New `mus1 lab` command group for lab-level configuration
  - `lab create --name <name>` – Create a new lab configuration
  - `lab list` – List available lab configurations
  - `lab activate <lab_id>` – Activate a lab with automatic shared storage detection
  - `lab configure-storage` – Configure shared storage for the current lab
  - `lab load <lab_id>` – Load a lab for current session
  - `lab associate <project>` – Associate a project with the current lab
  - `lab status` – Show current lab configuration and resources
  - `lab add-worker --name <name> --ssh-alias <alias>` – Add compute worker to lab
  - `lab add-credential --alias <alias> --user <user>` – Add SSH credentials to lab
  - `lab add-target --name <name> --kind <local|ssh|wsl>` – Add scan target to lab
  - `genotype add-to-lab --gene <name> --allele <allele> --inheritance <pattern>` – Configure genotype systems (e.g., ATP7B: WT,Het,KO)
  - `genotype track <gene_name> --lab <lab_id>` – Track genes at lab level
  - `genotype list --lab <lab_id>` – List genotype configurations and tracked genes
  - `lab projects` – List projects associated with the lab

- **Project Lab Integration**:
  - `project associate-lab <project> --lab-id <lab>` – Associate project with lab
  - `project lab-status <project>` – Show lab association and inherited resources

- **Subject Management**: New commands for subject lifecycle management
  - `project remove-subjects --subject-id <id> [--all]` – Remove subjects from projects with optional bulk operations

- **Genotype Management**: Comprehensive genotype system management
  - `genotype add-to-lab --gene <name> --allele <allele> --inheritance <pattern>` – Add genotype to lab
  - `genotype add-to-project --gene <name> --allele <allele> --inheritance <pattern> --project <path>` – Add genotype to project
  - `genotype accept-lab-tracked <gene_names> --project <path>` – Accept lab-tracked genotypes for project use
  - `genotype track <gene_name> --lab <lab_id>` – Track genes at lab level
  - `genotype list --lab <lab_id>` – List genotype configurations and tracked genes
  - `genotype track-exp-type <exp_type> --lab <lab_id>` – Track experiment types at lab level
  - `genotype list-exp-types --lab <lab_id>` – List tracked experiment types

- **Deprecated Commands Removed**: All project-level worker/credential/target management commands have been deprecated and removed to enforce lab-centric architecture:
  - ❌ `workers list|add|remove|detect-os` (use `lab` commands instead)
  - ❌ `targets list|add|remove` (use `lab` commands instead)
  - ❌ `credentials-set|credentials-list|credentials-remove` (use `lab` commands instead)

- **Root**: `mus1 --version` prints the installed MUS1 version.
- **Setup helpers**: `mus1 setup shared`, `mus1 setup labs`, `mus1 setup projects` now use the unified ConfigManager instead of YAML files for persistent configuration storage.
- **Plugin helpers**: `mus1 plugins list`, `mus1 plugins install`, and `mus1 plugins uninstall` manage external plugin packages registered via `mus1.plugins`.
- **Project assembly**: `project assembly` group for plugin-driven project actions:
  - `project assembly list` – list assembly-capable plugins
  - `project assembly list-actions --plugin <name>` – list actions for a plugin
  - `project assembly run --plugin <name> --action <name> [--params-file|-f] [--param KEY=VALUE]` – run an action
  - **Enhanced Copperlab Plugin**: Now supports iterative subject extraction with confidence scoring
    - `extract_subjects_iterative` – Initialize extraction process with confidence scoring (high/medium/low/uncertain)
    - `get_subject_batch` – Get batches of subjects for review by confidence level
    - `approve_subject_batch` – Approve subjects to add to lab master registry
    - `finalize_subject_import` – Complete the import process and clean up
    - Legacy: `subjects_from_csv_folder` returns `{subjects, conflicts}` with 3-digit ID normalization and reconciliation of sex, birth/death dates, genotype, treatment
 - GUI launch is via `mus1-gui` only; the CLI no longer exposes a `gui` subcommand.

## Recent Architectural Changes

### Configuration System Refactoring **[COMPLETED]**

**What was changed:**
- **Unified ConfigManager**: Replaced scattered YAML/JSON configuration files with a single SQLite-based configuration system
- **Hierarchical Configuration**: Implemented proper precedence (Runtime > Project > Lab > User > Install)
- **Migration System**: Added automatic migration from old configuration files to new system
- **Atomic Operations**: Configuration changes now use proper transactions and error handling

**Benefits:**
- **Reduced Complexity**: Eliminated 7+ scattered config locations in favor of single centralized database
- **Better Reliability**: Atomic operations prevent partial configuration updates
- **Improved Performance**: Faster configuration lookups and changes
- **Cleaner Code**: Removed complex path resolution logic and fallback mechanisms

**Impact on Data Import:**
- **Streamlined Setup**: Data import plugins can now rely on consistent configuration access
- **Better Validation**: Configuration values are properly validated and typed
- **Simplified Integration**: New data sources can be configured through the unified system

**Code Changes:**
- ✅ Created `ConfigManager` (`src/mus1/core/config_manager.py`)
- ✅ Created `ConfigMigrationManager` (`src/mus1/core/config_migration.py`)
- ✅ Refactored `LabManager` to use ConfigManager instead of YAML files
- ✅ Refactored `ProjectManager` to use ConfigManager for path resolution
- ✅ Refactored `StateManager` to use ConfigManager for global settings
- ✅ Updated CLI setup commands (`mus1 setup shared/labs/projects`) to use ConfigManager
- ✅ Removed deprecated methods from `master_media.py`
- ✅ Updated `AppInitializer` to initialize configuration system

**Outstanding Tasks:**
- Complete full migration testing across different operating systems
- Update GUI components to use new configuration system
- Add configuration backup/restore functionality
- Document configuration schema for plugin developers
