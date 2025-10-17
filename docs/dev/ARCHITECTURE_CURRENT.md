# MUS1 Simplified Architecture — Current State (authoritative)

This document describes the current MUS1 simplified architecture implementation with clean lab-based collaboration.

## Architecture Overview

MUS1 uses a simplified architecture focused on two primary user workflows:
1. **Local Projects**: Individual researchers working with projects on their local machine
2. **Lab Collaboration**: Teams collaborating through shared lab storage and member management

The architecture eliminates complex precedence chains, peer-hosted modes, and workgroup concepts in favor of simple, predictable behavior.
  
## 🎯 HOW IT WORKS

### Simplified Architecture Data Flow
```
User Input → Presentation Layer → Service Layer → Domain Layer → Repository Layer → Infrastructure Layer → Output

Presentation: main_window.py, simple_cli.py, setup_wizard.py (3-page setup wizard)
Service: project_discovery_service.py, setup_service.py, project_manager_clean.py
Domain: metadata.py entities + repository.py patterns
Infrastructure: schema.py models + config_manager.py settings
```

### Core Design Principles

1. **Two User Paths**: Local-only or Lab collaboration (no complex hybrid modes)
2. **Simple Storage**: Lab storage root or local user directory (no precedence chains)
3. **Clean Sharing**: Enable/disable lab sharing with online status checks
4. **Plugin-Based Extension**: Cross-lab project movement via importer plugins

### Definitions (Authoritative)

- **Lab**: Named collaborative scope that owns projects and a single optional Lab Shared Root. Represented by `LabDTO`.
- **Local mode**: No lab selected; projects live under the user’s `user.default_projects_dir`.
- **Project**: A directory containing `mus1.db`. A project is either lab-registered or local; there is no storage precedence computation.
- **Lab Shared Root**: One folder per lab for collaborative storage. No global precedence with user directories.
- **Worker**: Compute agent (SSH/WSL) registered under a lab and used only within that lab.
- **Project discovery**: Lab-registered projects (authoritative) + filesystem scan of the user default projects directory for local projects.
- **Configuration**: Single SQLite-backed `ConfigManager`; use `get_config("user.default_projects_dir")` and `get_lab_storage_root(lab_id)`.

### Standardized Code-Use Patterns

- **Discovery**: Use `ProjectDiscoveryService.discover_existing_projects()` and `find_project_path(name)`. Do not scan global/shared roots or compute precedence.
- **DTOs/validation**: Use Pydantic DTOs from `metadata.py` across services/GUI; avoid duplicate dataclass DTOs.
- **Configuration access**: Read local dir via `get_config("user.default_projects_dir")`; read/set lab storage via `get_lab_storage_root`/`set_lab_storage_root`. New code should not rely on a global `storage.shared_root`.
- **Project validity**: A project is valid if it contains `mus1.db`.
- **GUI layering**: GUI calls services (e.g., `SetupService`, `ProjectDiscoveryService`) instead of reading/writing config directly when a service exists.

### Example: Simplified Project Discovery Workflow
```python
# 1. User requests project list in GUI
# main_window.py (Presentation Layer)
def show_project_selection_dialog(self):
    discovery_service = get_project_discovery_service()
    # Simple: lab projects + local projects
    projects = discovery_service.discover_existing_projects()

# 2. Service finds projects from two locations only
# project_discovery_service.py (Service Layer)
def discover_existing_projects(self) -> List[Path]:
    projects = []

    # Lab-registered projects (if user has labs)
    for lab_config in self._get_user_labs():
        lab_projects = lab_config.get("projects", [])
        projects.extend(lab_projects)

    # Local user projects (always available)
    user_dir = get_config("user.default_projects_dir")
    if user_dir:
        projects.extend(self._discover_in_directory(user_dir))

    return projects

# 3. Clean lab-based data access
# repository.py (Domain Layer)
class LabRepository:
    def find_user_labs(self, user_id: str) -> List[Lab]:
        # Simple query for user's labs
        return self.db.query(LabModel).filter_by(creator_id=user_id).all()
```

### Example: Adding Subjects with Optional Colony Relationships
```python
# 1. User can create subjects with or without colony context
breeding_subject = SubjectDTO(
    id="SUB001",
    colony_id="COL001",  # Links to lab colony (breeding population)
    sex=Sex.MALE,
    genotype="GENE:WT"
)

experiment_subject = SubjectDTO(
    id="SUB002",
    colony_id=None,  # No colony - experimental subject only
    sex=Sex.FEMALE,
    genotype="GENE:KO"
)

# 2. Service validates colony exists (if specified) and handles business logic
# project_manager_clean.py
def add_subject_to_project(self, subject_dto: SubjectDTO):
    if subject_dto.colony_id:
        # Verify colony exists in project's lab
        colony = self.get_colony(subject_dto.colony_id)
        # Business logic: ensure genotype consistency, etc.
    # colony_id is optional - subjects can exist without colonies

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
# Configure application-level logging (always under OS app root)
from .core.logging_bus import LoggingEventBus
log_bus = LoggingEventBus.get_instance()
log_bus.configure_app_file_handler(max_size=5 * 1024 * 1024, backups=3)

# Qt platform detection and setup
app = QApplication(sys.argv)
```

Note: Application logs are now always written under the OS app root (`<app_root>/logs/mus1.log`) via `LoggingEventBus.configure_app_file_handler()`. This is decoupled from lab/project storage and respects the root pointer resolution.

#### **Phase 5: User Environment (SetupService)**
```python
# First-time detection and setup wizard (or via --setup flag)
run_setup_wizard = "--setup" in sys.argv or "-s" in sys.argv or os.environ.get('MUS1_SETUP_REQUESTED') == '1'

if run_setup_wizard or not setup_service.is_user_configured():
    setup_wizard = show_setup_wizard()
    # Setup wizard can be run anytime, not just first launch

# User/Lab Selection Dialog
dialog = UserLabSelectionDialog(parent=self)
if dialog.exec() == QDialog.DialogCode.Accepted:
    # Store selected user and lab
    self.selected_user_id = dialog.selected_user_id
    self.selected_lab_id = dialog.selected_lab_id
    # Switch to project management tab
    self.tab_widget.setCurrentWidget(self.project_view)
```

### **Platform-Specific Environment Handling**
- **macOS**: `~/Library/Application Support/mus1/`, native Qt plugins
- **Linux**: `~/.config/mus1/` or `$XDG_CONFIG_HOME/mus1/`, xcb Qt platform
- **Windows**: `%APPDATA%/mus1/`, Windows-specific Qt setup
- All GUI Qt imports must go through the `mus1/gui/qt.py` facade. Direct `PyQt6`/`PySide6` imports are forbidden and enforced via import-linter.

### Simplified Lab Storage
- **Lab Storage Root**: Each lab can optionally configure one shared storage directory
- **Simple Sharing**: Boolean enable/disable with online status checks
- **No Precedence**: Projects are either under lab storage OR local user directory
- **Discovery**: Lab-registered projects + local user projects (no complex scanning)
 - **Global shared storage (`storage.shared_root`)**: Deprecated; prefer per-lab storage roots. Existing keys may be read only for migration warnings.

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

### Data Relationship Validation

The MUS1 data model relationships are thoroughly validated by dedicated functional tests in `test_data_relationships.py`:

- **User → Lab Relationships**: Users can create multiple labs (one-to-many)
- **Lab → Multiple Entity Relationships**: Labs contain colonies, projects, members, workers, and scan targets
- **Colony → Subject Relationships**: Colonies can have multiple subjects (one-to-many)
- **Subject → Experiment Relationships**: Subjects can have multiple experiments (one-to-many)
- **Experiment ↔ Video Relationships**: Experiments can be linked to multiple videos (many-to-many)
- **Optional Relationships**: Subjects can exist with or without colony relationships
- **Complete Hierarchy Chain**: Full validation of User → Lab → Colony → Subject → Experiment chain
- **Relationship Integrity**: All foreign key constraints and relationship traversals work correctly

#### Identified Relationship Gaps

The following relationships exist conceptually but are not fully implemented or tested:

- **User → Local Project**: Users can create projects without lab setup (standalone projects)
- **Recording ↔ Experiment ↔ Subject**: Complete chain validation for single-animal recordings
- **Metadata ↔ Project/Lab Relationships**: Objects, bodyparts, treatments managed at project level but could be associated with labs
- **Breeding vs Experimental Contexts**: Treatments don't distinguish between breeding and experimental animal contexts

These gaps are documented and tested in `TestMissingRelationships` to highlight areas for future enhancement.

### Database Architecture
```sql
-- Complete relational schema with user-lab-project-colony-subject hierarchy
-- Key relationships:
--   Users belong to Labs (many-to-many via lab_members)
--   Colonies belong to Labs (one-to-many)
--   Projects are assigned to Labs (many-to-many via lab_projects)
--   Subjects can exist with or without Colonies (optional relationship)
--   Subjects can exist in both Colonies (breeding) AND Projects (experiments)
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
    genotype of interest TEXT,
    background_strain TEXT,
    common_traits TEXT DEFAULT '{}',
    date_added DATETIME NOT NULL
);

CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    colony_id TEXT REFERENCES colonies(id),  -- Optional: subjects can exist without colonies
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

### Recent Enhancements (2025-01)

#### **✅ Enhanced User/Lab Selection Dialog**
- **Optional Project Pre-selection**: Users can now optionally select a specific project immediately after choosing user and lab
- **Quality of Life Improvement**: Eliminates need to browse project list when you know which project you want to work with
- **Smart Integration**: If project selected, loads directly; otherwise proceeds to project management tab
- **Lab-Filtered Projects**: Project dropdown shows only projects registered with the selected lab

#### **✅ Complete Lab Management System**
- **Lab Creation & Settings**: Full CRUD operations for labs with institution, PI, and member management
- **Colony Management**: Create, update colonies with genotype tracking and optional subject assignment
- **Flexible Subject Assignment**: Subjects can be created with or without colony relationships; manual colony assignment/removal available
- **Project Registration**: Register projects with labs for better organization and discovery
- **Member Management**: Add/remove lab members with role-based permissions

#### **✅ Enhanced Subject & Metadata Display**
- **Colony Membership Display**: Subject overview shows which colony each subject belongs to
- **Manual Colony Assignment**: Direct UI for assigning subjects to colonies without complex workflows
- **Improved Metadata Tree**: Enhanced tree view with colony information and better sorting
- **Reusable Metadata Grid**: New `MetadataGridDisplay` replaces ad-hoc lists/dropdowns for subjects and experiments. It provides sortable columns, optional checkbox selection, and double-click activation via `row_activated(id)`. we still use normal dropdowns where apropriate though. this method is for use cases where a dropdown would be a UI pain point

Usage snippet (from `SubjectView`):

```335:370:src/mus1/gui/subject_view.py
# Grid creation and hookup
from .metadata_display import MetadataGridDisplay
self.subjects_grid = MetadataGridDisplay()
subjects_layout.addWidget(self.subjects_grid)
self.subjects_grid.row_activated.connect(self.handle_edit_subject_by_id)

# Populate grid
items = []
columns = ["ID", "Sex", "Genotype", "birth_date", "Colony"]
for subj_dto in subjects_display_dto:
    birth_dt = getattr(subj_dto, 'birth_date', None)
    items.append({
        "ID": subj_dto.id,
        "Sex": subj_dto.sex_display,
        "Genotype": getattr(subj_dto, 'genotype', None) or 'N/A',
        "birth_date": birth_dt.strftime('%Y-%m-%d') if birth_dt else 'N/A',
        "raw_birth_date": birth_dt,
        "Colony": getattr(subj_dto, 'colony_name', None) or 'None',
    })
self.subjects_grid.populate_data(items, columns)

# Read selected
subject_id = self.subjects_grid.get_current_item_id()
```
- **Validation & Error Handling**: Proper error messages and confirmation dialogs

#### **✅ Service Layer Extensions**
- **SetupService**: Added comprehensive lab management methods (create_lab, add_lab_member, create_colony, etc.)
- **LabService**: GUI service layer for lab operations with proper error handling
- **SubjectService**: Enhanced with colony information and manual assignment capabilities

### Wizard Behavior and Reinstall Experience
- The setup wizard can be run anytime via `--setup` flag (CLI/GUI) or File → Setup Wizard... menu option
- Clean separation of concerns: Setup Wizard → User/Lab Selection Dialog → Project Management in Project tab
- The setup wizard no longer exposes MUS1 application root selection in the default flow; it focuses on user profile, global shared storage, and lab creation (with optional per-lab storage root).
- If a previously configured root pointer is invalid or unavailable at startup, the application (outside the wizard) prompts to locate an existing configuration and updates the root pointer accordingly.
- After startup root selection (when needed), the ConfigManager binds to `<root>/config/config.db`. The wizard does not move or configure the app root.
- Current limitation: The wizard is creation-focused and does not provide pickers for existing users/labs. Use the User/Lab Selection dialog after startup to select existing entities.

#### Wizard Modes (New)
- Start Fresh vs Edit Existing: the wizard now offers a mode selector.
- Start Fresh can optionally wipe existing MUS1 configuration (config.db, root pointer, logs) before re-initializing.
- Edit Existing allows choosing an existing root (`config/config.db`) and editing settings in place.

## Current Status

### Actually Working Components
- **CLI Interface**: Basic command-line operations work reliably
- **Setup Wizard**: Can be launched via `--setup` flag, basic user profile creation works
- **Video Linking System**: Videos can be linked to experiments with proper association tables
- **Subject Management**: Flexible subject creation with optional colony relationships and proper genotype handling
- **Colony Management**: Flexible colony relationships with optional subject assignment/removal
- **Lab Management**: Lab creation, member management, colony management, and project registration
- **User Experience**: Enhanced user/lab selection dialog with optional project pre-selection
- **Batch Creation**: Experiments can be grouped into batches for analysis
- **SQL Schema**: Database tables exist for users, labs, colonies, subjects, experiments, videos
- **Repository Pattern**: Data access layer implemented with proper update/merge handling
- **Project Discovery**: Can find projects in configured locations
- **Configuration System**: Hierarchical config with JSON serialization and Path object handling
- **Standardized Service Patterns**: Consistent instantiation patterns (singletons, factories, direct) across the application
- **Functional Tests**: All 62 functional tests pass, including 14 relationship validation tests (9 core + 5 gap documentation tests)

### Known Issues & Remaining Components
- **GUI State Manager References**: Some legacy references remain (commented out) but don't break functionality
- **Plugin System GUI Integration**: ✅ **RESOLVED** - GUIPluginService now properly integrated through GUIServiceFactory
- **Clean Architecture Migration**: Most GUI views properly use service layer, no direct database access found
- **Service Pattern Standardization**: Some services still use inconsistent patterns (tracked in migration plan)
- **Repository Layer Gaps**: Missing experiment-video repository methods prevent PluginService from accessing video relationships — ✅ Implemented: repository APIs for experiment↔video associations are available and used via `ProjectManagerClean`.
- **Workgroup Features**: Models exist but no functional UI implementation
- **Modal Popups**: Still used in development builds instead of navigation log as per guidelines
- **User Profile Persistence**: CLI and GUI store user data in conflicting ways
- **Setup Workflow**: Async execution implemented but error handling incomplete
- **Lab-Project Association**: Database schema exists and GUI integration completed (registration from Project Settings/ProjectView).
 - **GUISubjectService repos usage**: Runtime error "GUISubjectService object has no attribute 'repos'" indicates an inconsistent repository access path; services must route via `ProjectManagerClean`.
 - **Shared folder designation for workers/compute**: No explicit configuration to designate/validate a lab-shared folder for lab workers or lab compute; needs path selection, validation, and exposure to worker configs.

## Findings from Initial Setup and Project Creation Audit (2025-09)

This section documents concrete gaps discovered during the "user → lab setup → drive selection → project creation" flow and the corrections applied.

### **Incomplete/Incorrect Claims - Current Status**

Many of the claimed fixes are not actually working due to critical bugs:

#### **✅ WORKING: JSON Serialization**
- **Status**: **Fixed**. Path objects are properly serialized/deserialized with custom handlers.
- **Validation**: All functional tests pass, including project creation/loading scenarios.

#### **✅ WORKING: GUI State Manager References**
- **Status**: **Resolved**. Remaining references are commented out and don't affect functionality.
- **Impact**: No AttributeError exceptions from state_manager references.

#### **✅ WORKING: Clean Architecture Migration**
- **Status**: **Mostly Complete**. GUI views use service layer, no direct database access found.
- **Validation**: All functional tests pass, indicating proper separation of concerns.

#### **✅ WORKING: Plugin System GUI Integration**
- **Status**: **Fully Working**. GUIPluginService properly integrated through GUIServiceFactory.
- **Implementation**: Plugin discovery, selection, and execution available through clean service interfaces.
- **Validation**: Plugin lists populate correctly in Experiment View.

#### **❓ UNKNOWN: Lab-Project Association**
- **Status**: **Needs Verification**. Database schema exists but GUI integration status unclear.
- **Action Needed**: Verify if lab-project registration works in practice.

#### **❌ MISSING: Experiment-Video Repository Methods**
- **Problem**: Repository layer lacks experiment-video relationship methods.
- **Impact**: GUIPluginService cannot access video data for experiments through clean repository pattern.
- **Workaround**: ProjectManagerClean handles experiment-video associations directly.
- **Status**: **Missing Implementation**. Violates repository pattern completeness for experiment-video associations.

### ✅/🔄 **User Profile Single Source of Truth**
- Implemented: Only `user.id` is persisted in ConfigManager; user fields live in SQL. A one-time migration from legacy keys to SQL is invoked at startup.
- Outstanding: If any legacy CLI path persists duplicate user fields, it should be updated to stop writing them.

### ✅ **WORKING: Plugin Discovery surfaced in GUI**
- Intended: GUI should list discovered plugins via the clean plugin manager.
- Current: GUIPluginService properly integrated through GUIServiceFactory provides plugin discovery and selection.
- Implementation: Experiment View plugin lists populate correctly through GUIServiceFactory.
- Status: **Fully Working**. Plugin discovery, registration, selection, and execution all work through clean GUI service interfaces.

### Reinforced Design Principles
- Deterministic root resolution is the baseline; GUI no longer selects the app root. A startup prompt handles relocating to an existing config when needed.
- **Simple Discovery**: Lab-registered projects + local user projects (no complex priority chains)
- **Simple Storage Model**: Projects are stored in either lab shared storage OR local user directory
- **No Complex Precedence**: Clear separation between lab projects and local projects

### Data Storage Roots
- **Lab Projects**: Stored under `lab.storage_root` (when lab sharing is enabled)
- **Local Projects**: Stored under `user.default_projects_dir` (always available)
- **Online Checks**: Lab storage accessibility is checked and displayed in UI

### Cross-Lab Project Movement
- **Default Importer Plugin**: `project_importer` is the default MUS1 plugin for importing existing MUS1 projects to labs they were not previously associated with, enabling cross-lab project movement
- **Clean Separation**: Projects maintain their original lab association until explicitly imported
- **Flexible Migration**: Users can import project data, subjects, or experiments as needed

### GUI Identity
- The main window title surfaces the active user (name and email) derived from the SQL profile.

## Service Instantiation Patterns

### **Standardized Service Patterns**

MUS1 uses consistent service instantiation patterns to ensure clean architecture, testability, and maintainability.

#### **1. Singletons (Global Services)**
**When to Use**: Truly global, stateless services accessed application-wide.

**Pattern**:
```python
class LoggingEventBus:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = LoggingEventBus()
        return cls._instance

# Usage
log_bus = LoggingEventBus.get_instance()
```

**MUS1 Singletons**:
- `LoggingEventBus` - Application-wide logging coordination
- `ConfigManager` - Global configuration state (when singleton)

#### **2. Factories (Scoped Services)**
**When to Use**: Services with dependencies, lifecycle management, or scoped context.

**Pattern**:
```python
class GUIServiceFactory:
    def __init__(self, project_manager):
        self.project_manager = project_manager

    def create_subject_service(self) -> GUISubjectService:
        return GUISubjectService(self.project_manager)

# Usage
factory = GUIServiceFactory(project_manager)
subject_service = factory.create_subject_service()
```

**MUS1 Factories**:
- `GUIServiceFactory` - Creates GUI services for a project context
- `RepositoryFactory` - Creates repository instances for database access
- `ProjectServiceFactory` - Creates project-scoped core services (planned)

#### **3. Direct Instantiation (Stateless Services)**
**When to Use**: Pure utility services with no dependencies or state.

**Pattern**:
```python
# Simple instantiation for stateless services
data_transformer = DataTransformer()
```

**MUS1 Direct Instantiation**:
- Pure data transformation services
- Value objects and DTOs

#### **4. Service Locator (Limited Use)**
**When to Use**: Only for services requiring dynamic resolution at runtime.

**Pattern**:
```python
class SetupService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SetupService()
        return cls._instance

def get_setup_service() -> SetupService:
    return SetupService.get_instance()

# Usage (limited to necessary cases)
setup_service = get_setup_service()
```

**MUS1 Service Locators**:
- `get_setup_service()` - For setup operations (converted to singleton)
- `get_project_discovery_service()` - For project discovery (converted to singleton)

### **Current MUS1 Service Classification**

| Service | Pattern | Status | Notes |
|---------|---------|--------|-------|
| `LoggingEventBus` | Singleton | ✅ Implemented | Global logging coordination |
| `GUIServiceFactory` | Factory | ✅ Implemented | GUI service creation |
| `RepositoryFactory` | Factory | ✅ Implemented | Database access layer |
| `ProjectManagerClean` | Factory | ✅ Implemented | Via ProjectServiceFactory |
| `PluginManagerClean` | Factory | ✅ Implemented | Via ProjectServiceFactory |
| `SetupService` | Singleton | ✅ Implemented | Global setup coordination |
| `LabService` | Factory | ✅ Implemented | Via GUIServiceFactory |

### **Current Factory Implementations**

#### **GUIServiceFactory (Current)**
```python
# Factory Creation (in MainWindow)
self.gui_services = GUIServiceFactory(self.project_manager)
self.gui_services.set_plugin_manager(self.plugin_manager)

# Service Creation (in Views)
subject_service = services.create_subject_service()      # GUISubjectService
experiment_service = services.create_experiment_service() # GUIExperimentService
project_service = services.create_project_service()      # GUIProjectService
lab_service = services.create_lab_service()              # LabService
plugin_service = services.create_plugin_service()        # GUIPluginService
```

#### **RepositoryFactory (Current)**
```python
# Factory Creation (in ProjectManagerClean)
self.repos = RepositoryFactory(self.db)

# Lazy Service Creation
subjects_repo = repos.subjects    # SubjectRepository
experiments_repo = repos.experiments  # ExperimentRepository
```

#### **ProjectServiceFactory (Planned)**
```python
# Central factory for project-scoped services
class ProjectServiceFactory:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._project_manager = None
        self._plugin_manager = None

    @property
    def project_manager(self):
        if self._project_manager is None:
            self._project_manager = ProjectManagerClean(self.project_path)
        return self._project_manager

    @property
    def plugin_manager(self):
        if self._plugin_manager is None:
            self._plugin_manager = PluginManagerClean(self.project_manager.db)
        return self._plugin_manager

    @property
    def gui_services(self):
        return GUIServiceFactory(self.project_manager, self.plugin_manager)
```

### **Migration Plan**

1. **Phase 1**: ✅ Implement `ProjectServiceFactory` to standardize core service creation
2. **Phase 2**: ✅ Convert `SetupService` to singleton pattern
3. **Phase 3**: ✅ Update `MainWindow` to use `ProjectServiceFactory` (remove backward compatibility)
4. **Phase 4**: ✅ Convert remaining service locators to singletons where appropriate

## Key Features

- **Deterministic Configuration**: Clean priority chain for MUS1 root resolution
- **Single Source of Truth**: All configuration in one SQLite database
- **Clean Architecture**: Proper layer separation with repository pattern and standardized service instantiation
- **Lab-Colony-Subject Hierarchy**: Flexible subject management with optional colony relationships
- **Standardized Service Patterns**: Singletons, factories, and direct instantiation based on service scope and requirements
- **Plugin System**: Full automatic discovery, selection, and execution through GUIPluginService
- **Test Coverage**: 62 functional tests all passing, validating business logic integrity
- **Metadata Management**: Project-scoped objects, bodyparts, treatments, genotypes (stored in project config JSON)


## 🔎 Duplication Hotspots and Consistent Approach (Updated)

- **Resolved DTO duplication (Lab/Colony)**: `LabDTO` and `ColonyDTO` are defined in `metadata.py` as Pydantic models and imported by services; duplicated dataclass variants have been removed from `setup_service.py`.
- **Remaining form DTOs**: `UserProfileDTO` and related setup-wizard dataclasses still perform validation in `__post_init__`. Consider converting them to Pydantic or clearly marking them as view-only form models.
- **Scattered Validators**: Prefer Pydantic validators for ID/name/date rules; avoid repeating equivalent checks in services.
- **ProjectConfig vs ProjectModel**: Treat `ProjectConfig` as a thin read/view model; keep persistence validation and transformations in repositories.

### Recommended Consistent Approach

- **Single DTO Source**: Keep all DTOs as Pydantic models in `metadata.py`. Remove dataclass DTO definitions from `setup_service.py` and import the Pydantic DTOs instead.
- **Centralize Validation**: Encode ID/name/date rules in Pydantic validators and delete equivalent `__post_init__` checks in services.
- **Repository-Centric Transformations**: Do conversions (DTO ↔ domain ↔ SQLAlchemy) in repositories; services orchestrate flows without redefining field sets.
- **Thin View Models**: Use `ProjectConfig` only as a thin read model constructed by repositories on top of `ProjectModel` when needed; avoid duplicating validation rules.

### Concrete Fix Steps

1) **Consolidate DTOs**
   - Keep `LabDTO` and `ColonyDTO` only in `metadata.py`; ensure services import these exclusively.
   - Migrate remaining setup-wizard dataclass DTOs to Pydantic (or document them as view-only form models).

2) **Unify Validators**
   - Keep ID/name checks in Pydantic validators (`metadata.py`).
   - Remove duplicated `__post_init__` checks in `setup_service.py`.
   - Replace ad-hoc helper functions with shared validators or model mixins when applicable.

3) **Align with Repository Layer**
   - Ensure repositories perform the entity-model mapping; avoid re-specifying field sets in services.
   - Keep `ProjectConfig` as a read/view model only; move its validation to DTOs or repo save path.

4) **Audit and Remove Dead Code**
   - Follow `.audit/pylint_duplicates.txt` and `.audit/vulture.txt` to delete unused/duplicate code and imports.

5) **Tests & CI**
   - Run functional tests and add CI checks for import-linter and ruff to prevent regressions.

### Ambiguities and Unnecessary Separation to Address

- **Global shared storage surfaces**: CLI flags (`--use-shared`, `--shared-root`), Settings UI group, and `ProjectModel.shared_root` field remain. These should be removed in favor of per-lab roots.
- **Project selection dialog root helper**: `ProjectDiscoveryService.get_project_root_for_dialog(...)` has an incomplete `default_dir` branch; ensure it returns the user default dir when no lab root is present and that it’s a proper method on the service.
- **GUI vs Service layering**: Some GUI code still reads/writes config directly for storage roots; route these through `SetupService` to keep the presentation layer thin.
- **Worker registration visibility**: Worker registration/management is not clearly surfaced in lab settings; align UI and services to treat workers as lab-scoped resources.

## GUI Architecture Addendum (2025-10)

### Qt Binding Facade
- All GUI modules must import Qt types from `mus1/gui/qt.py`. This facade detects PySide6/PyQt6 and exposes unified enums (`QPalette.ColorRole`, `Qt.AspectRatioMode`, etc.).
- Direct imports from `PySide6`/`PyQt6` are not allowed in GUI code.

### Theming
- Single source: `mus1/gui/theme_manager.py`. The previous duplicate in `mus1/core/theme_manager.py` was removed.
- App creates one `ThemeManager` in `mus1/main.py` and passes it to `MainWindow(theme_manager=...)`.
- `ThemeManager.apply_theme(app)` sets the application palette and processes `themes/mus1.qss` by substituting `$VARIABLES` based on Light/Dark.
- `MainWindow.apply_theme()` propagates the effective theme to views via `update_theme(theme)`.

Usage example:
```python
# main.py
config_manager = ConfigManager()
app = QApplication(sys.argv)
theme_manager = ThemeManager(config_manager)
theme_manager.apply_theme(app)
main_window = MainWindow(theme_manager=theme_manager)
main_window.apply_theme()
```

### Shared Background Watermark
- Common helper `mus1/gui/background.py` provides `apply_watermark_background(widget)`.
- Dialogs call this from `setup_background()` and `resizeEvent` to keep visuals consistent.


### Risks and Mitigations
- Mixing DTO types during refactor → Mitigate by changing imports in one PR and running all functional tests.
- Service call sites expecting dataclass instances → Update service parameters to accept Pydantic DTOs and adjust call sites.

