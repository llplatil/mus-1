# MUS1 Clean Architecture — Current State (authoritative)

This document describes the current MUS1 clean architecture implementation.

## Architecture Overview

MUS1 uses clean architecture principles with clear separation of concerns and layered design.
  
## 🎯 HOW IT WORKS

### Clean Architecture Data Flow
```
User Input → Presentation Layer → Service Layer → Domain Layer → Repository Layer → Infrastructure Layer → Output

Presentation: main_window.py, simple_cli.py
Service: project_discovery_service.py, setup_service.py, project_manager_clean.py
Domain: metadata.py entities + repository.py patterns
Infrastructure: schema.py models + config_manager.py settings
```

### Example: Complete Project Discovery Workflow
```python
# 1. User requests project list in GUI
# main_window.py (Presentation Layer)
def show_project_selection_dialog(self):
    discovery_service = get_project_discovery_service()
    project_root = discovery_service.get_project_root_for_dialog()

# 2. Service finds projects from configured locations
# project_discovery_service.py (Service Layer)
def discover_existing_projects(self) -> List[Path]:
    projects = []
    for base_path in self._get_search_paths():
        # Search logic with proper validation
    return projects

# 3. Repository pattern for data access
# repository.py (Domain Layer)
class ColonyRepository:
    def find_by_lab(self, lab_id: str) -> List[Colony]:
        # Clean SQLAlchemy queries
        return self.db.query(ColonyModel).filter_by(lab_id=lab_id).all()
```

### Example: Adding a Subject with Colony Relationship
```python
# 1. User provides data with colony context
subject_dto = SubjectDTO(
    id="SUB001",
    colony_id="COL001",  # Links to lab colony
    sex=Sex.MALE,
    genotype="GENE:WT"
)

# 2. Service validates colony exists and handles business logic
# project_manager_clean.py
def add_subject_to_project(self, subject_dto: SubjectDTO):
    # Verify colony exists in project's lab
    colony = self.get_colony(subject_dto.colony_id)
    # Business logic: ensure genotype consistency, etc.

# 3. Repository saves with proper relationships
# repository.py
def save(self, subject: Subject) -> Subject:
    model = SubjectModel(**subject.dict())
    self.db.add(model)
    self.db.commit()
    return Subject.from_model(model)
```

## 🔧 **ENVIRONMENT SETUP ARCHITECTURE**

### **5-Phase Environment Initialization (Updated)**

The MUS1 environment setup now uses **deterministic MUS1 root resolution**:

#### **Phase 1: MUS1 Root Resolution (New Deterministic Approach)**
```python
def resolve_mus1_root() -> Path:
    """
    Deterministically resolve MUS1 root directory.

    Priority (highest to lowest):
    1. MUS1_ROOT environment variable (if valid)
    2. Existing MUS1 root in platform default location
    3. Create/use platform default location
    """
    # Priority 1: Environment variable
    env_root = os.environ.get("MUS1_ROOT")
    if env_root:
        root_path = Path(env_root).expanduser().resolve()
        if _is_valid_mus1_root(root_path):
            return root_path

    # Priority 2: Platform default with existing config
    default_root = _get_platform_default_mus1_root()
    if _is_valid_mus1_root(default_root):
        return default_root

    # Priority 3: Create platform default
    return _create_mus1_root(default_root)

def _get_platform_default_mus1_root() -> Path:
    """Get platform-specific default MUS1 root location."""
    if platform.system() == "Darwin":  # macOS
        return Path.home() / "Library/Application Support/MUS1"
    elif platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
        return Path(appdata) / "MUS1"
    else:  # Linux/Unix
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(xdg_config) / "mus1"
```

#### **Phase 2: System Environment Setup**
```bash
# Production: Global installation
pip install mus1

# Development: Isolated environment
./setup.sh  # Creates .venv, installs dependencies
```

#### **Phase 3: Runtime Environment (ConfigManager)**
```python
class ConfigManager:
    def __init__(self, db_path: Optional[Path] = None):
        # Use deterministic MUS1 root resolution if no explicit path provided
        if db_path is None:
            mus1_root = resolve_mus1_root()
            config_dir = mus1_root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / "config.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
```

#### **Phase 4: Application Environment (main.py)**
```python
# First, resolve MUS1 root deterministically
from .core.config_manager import resolve_mus1_root
mus1_root = resolve_mus1_root()
logs_dir = mus1_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Configure logging to use MUS1 logs directory
log_file = logs_dir / "mus1.log"

# Qt platform detection and setup
app = QApplication(sys.argv)
```

Note: In the current implementation, the logs root is resolved via `resolve_mus1_root()` on startup. The intended behavior post-setup is to prefer a configured `get_config("mus1.root_path")` when present, falling back to `resolve_mus1_root()` only if unset. See Roadmap for the outstanding task.

#### **Phase 5: User Environment (SetupService)**
```python
# First-time detection and setup wizard
if not setup_service.is_user_configured():
    setup_wizard = show_setup_wizard()
    # Clean startup sequence prevents wizard loops
```

### **Platform-Specific Environment Handling**
- **macOS**: `~/Library/Application Support/mus1/`, native Qt plugins
- **Linux**: `~/.config/mus1/` or `$XDG_CONFIG_HOME/mus1/`, xcb Qt platform
- **Windows**: `%APPDATA%/mus1/`, Windows-specific Qt setup

### **Environment Variables**
```bash
# Optional overrides
MUS1_ROOT="/custom/mus1/location"    # Override config location
QT_QPA_PLATFORM="xcb"                 # Force Qt platform
QT_QPA_PLATFORM_PLUGIN_PATH="..."     # Custom Qt plugins
DISPLAY=":0"                          # Linux display
```

### Root Pointer Locator (persistent discovery)
- MUS1 uses a small locator file at the platform default path to rediscover the chosen configuration root across reinstalls, different shells, and environments.
- File: `~/Library/Application Support/MUS1/config/root_pointer.json` on macOS (platform-appropriate on Linux/Windows)
- Contents: `{ "root": "/absolute/path/to/MUS1_ROOT", "updated_at": "ISO8601" }`
- Startup resolution order:
  1. `MUS1_ROOT` environment variable (if set and valid)
  2. Root pointer file (if present and valid) → becomes the canonical MUS1 root
  3. Platform default if it already contains a valid MUS1 config
  4. Create platform default if nothing else exists
- The locator stores no user data; it only points to the authoritative root.

Status: Implemented. `ConfigManager` reads and writes the root pointer at the platform default location and validates the target before use.

### Database Architecture
```sql
-- Complete relational schema with user-lab-project hierarchy
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    organization TEXT,
    default_projects_dir TEXT,
    default_shared_dir TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE labs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    institution TEXT,
    pi_name TEXT,
    creator_id TEXT NOT NULL REFERENCES users(id),
    created_at DATETIME NOT NULL
);

CREATE TABLE lab_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_id TEXT NOT NULL REFERENCES labs(id),
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    created_date DATETIME NOT NULL
);

CREATE TABLE workgroups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    share_key_hash TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE workgroup_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workgroup_id TEXT NOT NULL REFERENCES workgroups(id),
    member_email TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    added_at DATETIME NOT NULL
);

CREATE TABLE colonies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lab_id TEXT NOT NULL,
    genotype_of_interest TEXT,
    background_strain TEXT,
    common_traits TEXT DEFAULT '{}',
    date_added DATETIME NOT NULL
);

CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    colony_id TEXT NOT NULL REFERENCES colonies(id),
    sex TEXT NOT NULL,
    designation TEXT,
    birth_date DATETIME,
    individual_genotype TEXT,
    individual_treatment TEXT,
    date_added DATETIME NOT NULL
);

CREATE TABLE experiments (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    experiment_type TEXT NOT NULL,
    date_recorded DATETIME NOT NULL,
    processing_stage TEXT NOT NULL,
    date_added DATETIME NOT NULL
);
```

### User Profile Persistence — Single Source of Truth
- Intended design: The SQL `users` table is authoritative for all user profile fields (name, email, organization, default directories). `ConfigManager` stores only `user.id` (active user). Services fetch user details via repositories using the active `user.id`. A one-time migration should seed SQL from legacy config keys and remove those keys.
- Current status: Service/repository layer uses SQL for user data as intended. However, the legacy CLI path still writes `user.name/email/organization` to ConfigManager, and the one-time migration is not wired into startup. See Outstanding Items below.

### Wizard Behavior and Reinstall Experience
- Wizard offers three options when a config is detected:
  - Use existing configuration at the discovered root (default)
  - Locate existing configuration... (browse to a `config.db` to switch roots)
  - Set up new configuration (with optional “copy existing config to new location”)
- After choosing a root, the wizard writes/updates the root pointer and rebinds the ConfigManager to `<root>/config/config.db`.
- If the root (e.g., external drive) is temporarily unavailable, startup prompts to retry/locate/create, without losing the pointer.

## Current Status

### Working Components
- **Application-level user and lab management**: SQL-based user/lab entities with proper relationships
- **Complete user-lab-project-workgroup hierarchy**: Full relational schema with foreign keys
- **Clean setup workflow**: Proper ConfigManager re-initialization after MUS1 root selection
- **Organized GUI architecture**: Settings tab with User Settings, Lab Settings, and Workers
- SQLite-based domain models with lab-colony hierarchy
- Repository pattern for data access
- Clean project management with colony relationships
- Core plugin system with entry-point discovery (GUI integration pending)
- Hierarchical configuration system
- Simple CLI interface

### Known Limitations
- Some plugins require updates for new service pattern
- Windows/Linux video scanners lack OS-specific optimizations
- Workgroup features partially implemented (models exist, UI integration pending)
- Setup wizard still uses modal popups (`QMessageBox`) for some flows; per dev guidelines, these should be replaced by the navigation/status log in development builds
- Conclusion page does not render per-step statuses from `steps_completed`/`errors`; it shows generic success/failure
- `main.py` currently resolves logs root via `resolve_mus1_root()`; should prefer configured `mus1.root_path` when present
- CLI `simple_cli.py` persists user profile fields in ConfigManager; conflicts with the “SQL authoritative” model until migration is wired
- "Copy existing configuration to new location" flag is collected by the wizard but not acted on in `SetupService`
- GUI does not yet surface discovered plugins; Experiment view lists use placeholders

## Findings from Initial Setup and Project Creation Audit (2025-09)

This section documents concrete gaps discovered during the "user → lab setup → drive selection → project creation" flow and the corrections applied.

### ✅ **FIXED: MUS1 Root Selection Ignored in GUI Wizard**
- Problem: `MUS1SetupWizard.collect_setup_data()` previously ignored the MUS1 Root page and always used `resolve_mus1_root()`.
- Impact: User drive/root selection in the wizard had no effect.
- Status: **Fixed**. The wizard now reads the selected path and initializes `MUS1RootLocationDTO` accordingly. On success, `ConfigManager` is re-initialized to `<selected_root>/config/config.db`.

### ✅/🔄 **SETUP WORKFLOW: Async Execution Implemented; Per-Step UI Pending**
- Problem: `SetupWorker.run()` was invoked on the GUI thread; failure paths didn't update the conclusion page.
- Impact: Potential UI freezes; conclusion page stuck on "in progress" after errors.
- Status: **Fixed (Async)**. Worker runs in a `QThread`, and both success and error paths emit through `setup_completed`.
- Status: **Outstanding (Per-Step UI)**. Conclusion page does not yet render per-step statuses/errors from the workflow result; it shows generic success/failure.

### ✅ **FIXED: ProjectView Not Wired to Active ProjectManagerClean**
- Problem: Methods referenced `self.project_manager` which wasn't set; some other places used `self.window().project_manager`.
- Impact: Rename/settings/admin actions failed silently.
- Status: **Fixed**. `set_gui_services` now also wires `self.project_manager = self.window().project_manager` when available.

### ✅ **FIXED: New Projects Not Registered Under Labs**
- Problem: Project creation didn't append to `labs[lab_id].projects` and didn't set `lab_id` in project config.
- Impact: Discovery (which prioritizes labs) missed new projects; lab linkage broken.
- Status: **Fixed**. When exactly one lab exists, the dialog associates the project via `ProjectManagerClean.set_lab_id()` and appends to the lab's `projects` list.

### ✅ **FIXED: ConfigManager Instancing**
- Problem: `SetupService` cached ConfigManager instance, preventing proper re-initialization after MUS1 root changes.
- Impact: Setup writes went to wrong database when custom root was selected.
- Status: **Fixed**. `SetupService` now fetches fresh ConfigManager instances for each operation, allowing proper re-initialization.

### ✅ **IMPLEMENTED: Application-Level User and Lab Management**
- Problem: Labs stored as JSON blobs in config; no proper user management or relational structure.
- Impact: Difficult to manage users across projects, no proper lab relationships.
- Status: **Implemented**. Added SQL schema with `UserModel`, `LabModel`, `LabProjectModel` tables. Created repositories and updated setup to store users/labs in SQL database with proper relationships.

### ✅ **IMPLEMENTED: GUI Tab Reorganization**
### 🔄 **PARTIAL: Configuration Root Usage Consistency**
- Intended: After setup, the app should prefer the configured MUS1 root (`mus1.root_path`) for logs and other paths, falling back to deterministic resolution only if unset.
- Current: `main.py` always uses `resolve_mus1_root()` when configuring logs; imports across the app sometimes call `resolve_mus1_root()` directly.
- Action: Prefer `get_config("mus1.root_path")` when present; audit imports and replace direct calls where appropriate.

### 🔄 **PARTIAL: Copy Existing Configuration**
- Intended: Wizard option "Copy existing configuration to new location" should copy an existing config (e.g., `config.db`) when creating a new root.
- Current: Wizard collects the flag, but `SetupService.setup_mus1_root_location` does not implement copy logic.
- Action: Implement guarded copy of legacy config into the new root when flagged.

### 🔄 **PARTIAL: User Profile Single Source of Truth**
- Intended: Only `user.id` lives in ConfigManager; all user fields live in SQL.
- Current: Service/repository use SQL; legacy CLI still persists user fields in ConfigManager; one-time migration not wired.
- Action: Update CLI to stop writing duplicate keys; wire `ConfigMigrationManager` (or a simpler seeding step) to migrate and remove legacy keys.

### 🔄 **PARTIAL: Plugin Discovery surfaced in GUI**
- Intended: GUI should list discovered plugins via the clean plugin manager.
- Current: Core discovery exists; Experiment view uses placeholder text and does not display discovered plugins.
- Action: Connect GUI lists to `PluginManagerClean` and populate dynamically.
- Problem: Workers mixed with project settings; unclear separation of concerns.
- Impact: Confusing user experience with settings scattered across different views.
- Status: **Implemented**. Created `SettingsView` with User Settings, Lab Settings, and Workers pages. Moved Workers functionality from `ProjectView` to `SettingsView`. Project tab now focused on project-specific operations.

### Reinforced Design Principles
- Deterministic root resolution is the baseline; explicit GUI selection must override it and re-bind the config database path.
- Project discovery priority: lab config → user default projects dir → shared storage `Projects/`. New projects should be registered into lab config when lab is known.
- Views should act through services and the `ProjectManagerClean` held by `MainWindow` to avoid split state.

## Key Features

- **Deterministic Configuration**: Clean priority chain for MUS1 root resolution
- **Single Source of Truth**: All configuration in one SQLite database
- **Clean Architecture**: Proper layer separation with repository pattern
- **Lab-Colony Hierarchy**: Colony-based subject management with genotype tracking
- **Plugin System**: Core automatic discovery and clean service integration (GUI surfacing pending)

