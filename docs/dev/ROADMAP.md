# MUS1 Simplified Architecture Roadmap

This roadmap shows current status and planned development priorities for the simplified MUS1 architecture.

## ✅ COMPLETED: Major Architecture Simplification (2025-01)

### **Simplified User Workflows**
- **✅ 3-Page Setup Wizard**: User Profile → Lab Choice → Lab Config
- **✅ Dual-Mode Support**: Local projects OR lab collaboration (no hybrid complexity)
- **✅ Simple Storage**: Lab storage root OR local user directory (no precedence chains)
- **✅ Clean Sharing**: Boolean enable/disable with online status checks
- **✅ Default Project Importer Plugin**: Core MUS1 plugin for importing existing MUS1 projects to labs they were not previously associated with, enabling cross-lab project movement

### **Removed Complexity**
- **✅ Workgroups & Complex Collaboration**: Eliminated separate workgroup concept
- **✅ Peer-Hosted Sharing Modes**: Removed always_on/peer_hosted complexity
- **✅ Storage Precedence Chains**: No more project→lab→global precedence logic
- **✅ Multi-Root Scanning**: Simple lab + local discovery only
- **✅ Dead Code Cleanup**: Removed unused DTOs, functions, database tables

## Known Issues (Updated)
- Windows/Linux video scanners lack OS-specific optimizations
- Service instantiation patterns need standardization (singletons, factories, direct instantiation)
- Modal popups used during setup; prefer in-app log/status per development guidelines

## Development Priorities (Updated)

### High Priority
1. **Service Pattern Standardization**: Implement ProjectServiceFactory and standardize all service instantiation ✅ **IN PROGRESS**
2. **Plugin GUI Integration**: Connect PluginManagerClean to ExperimentView.set_plugin_manager() ✅ **DONE**
3. **Metadata Database Persistence**: Move objects/bodyparts/treatments/genotypes from JSON config to database tables ✅ **DONE**
4. **Modal Popup Replacement**: Replace QMessageBox with navigation log/status messages 🔄 **IN PROGRESS**
5. **Data Migration**: Implement migration path for existing users to simplified model

### Medium Priority
1. **Windows/Linux Video Scanners**: OS-specific optimizations for video discovery
2. **Advanced Lab Features**: Lab member permissions, worker management UI

4. **✅ COMPLETED: Clean Architecture Foundation**
   - **✅ GUI Views**: All views use service layer, no direct database access found
   - **✅ Repository Pattern**: Fully implemented with proper separation of concerns
   - **✅ Service Layer**: Bridges domain models to GUI with clean DTOs
   - **✅ Test Coverage**: 62 functional tests validate all relationships
   - **🔄 Service Patterns**: Standardizing instantiation patterns (singletons, factories, direct)

5. **🔄 PARTIAL: Setup & Project Flow**
   - **✅ MUS1 root selection and ConfigManager re-initialization**: JSON serialization works correctly with Path object handling
   - **❌ Setup workflow async execution**: Works but error handling incomplete, conclusion page doesn't show per-step status
   - **✅ ProjectView wiring**: Subject View and experiment management now use clean architecture
   - **✅ Lab-project registration**: Complete GUI integration with project discovery and registration
   - **❌ Modal popup replacement**: Still uses QMessageBox in development builds
   - **✅ ProjectView registration option**: Local project creation can optionally register with selected lab.
   - **✅ Qt facade enforcement**: Import-linter contract forbids direct `PyQt6`/`PySide6` imports in GUI.

6. **❌ NOT IMPLEMENTED: Workgroup Model (unused)**
   - **✅ Database schema exists**: Tables present but unused; slated for removal or feature-flag
   - **❌ No key generation/verification**: Utilities not implemented

7. **✅ IMPLEMENTED: Lab Management**
   - **✅ Database schema exists**: LabModel and LabProjectModel tables created
   - **✅ Migration implemented**: One-time migration properly wired into startup
   - **✅ GUI integration complete**: Full lab creation, member management, colony management, project registration

8. **✅ IMPLEMENTED: GUI Tab Reorganization**
   - **✅ Settings tab exists**: Complete tab structure with User, Lab, Workers pages
   - **✅ User Settings**: Profile management working correctly with clean architecture
   - **✅ Lab Settings**: Complete lab management system with creation, member management, colony management
   - **❌ Workers**: SSH worker configuration moved but may not work due to missing methods

9. **❌ NOT IMPLEMENTED: Wizard UX & Preferences**
   - **❌ No App Preferences page**: Theme/sort preferences not in wizard
   - **❌ QMessageBox still used**: Modal popups not replaced with navigation log

10. **✅ WORKING: Config Root Usage Consistency**
    - **✅ ConfigManager rebinding**: Works correctly with JSON serialization and Path handling
    - **✅ Startup resolution**: Functions properly with corrupted project detection
    - **✅ main.py logging**: Prefer configured `mus1.root_path` for logs when present
    - Implement optional "Copy existing configuration to new location" when creating a new root — 🔄 pending (wizard collects flag; service best-effort copy for DB already present)
11. **Lab-Centric Sharing (Planned)**
   - Normalize shared resources under the lab and expose retrieval by lab membership with a single per-lab Shared Root
   - Schema additions:
     - `lab_members(lab_id, user_id, role, joined_at, PRIMARY KEY(lab_id,user_id))`
     - `lab_workers(lab_id, worker_id, permissions, tags, PRIMARY KEY(lab_id,worker_id))`
     - `lab_scan_targets(lab_id, scan_target_id, PRIMARY KEY(lab_id,scan_target_id))`
   - Repository APIs:
     - `LabRepository.find_for_user(user_id)`
     - `LabRepository.get_workers(lab_id)`, `get_scan_targets(lab_id)`
     - Membership CRUD: `add_member`, `remove_member`, `list_members`
     - Association CRUD: `attach_worker`, `detach_worker`, `attach_scan_target`, `detach_scan_target`
   - GUI/CLI:
     - Project selection: separate Lab (registered projects) vs Local sections
     - Settings → Lab Settings: members/workers/scan targets management
     - CLI parity: `mus1 lab members|workers|targets ...`
   - Migration:
     - Backfill membership for lab creators as `admin`
     - Attach existing workers/scan targets to selected lab without data duplication

  - In `src/mus1/main.py`, when configuring logs, prefer configured `get_config("mus1.root_path")` when present; fall back to `resolve_mus1_root()` only if unset — 🔄 pending
  - Audit imports using `resolve_mus1_root()` and switch to configuration value post-setup where appropriate — 🔄 pending

### High Priority (New): Storage Model Cleanup, DTO Consolidation, and Context Sync

- **Problem A (Storage Model)**: Global `storage.shared_root` is deprecated in GUI; CLI still exposes shared-root flags for worker/SSH workflows.
- **Problem B (Discovery/Dialog)**: (Resolved) `ProjectDiscoveryService.get_project_root_for_dialog(...)` returns lab root when present, else user default dir.
- **Problem C (DTOs/Validators)**: Duplicate DTOs/validators across layers cause drift and maintenance overhead.
- **Problem D (Context Sync)**: Views do not consistently refresh when user/lab/project changes.

- **Decision/Approach**:
  - Storage: GUI uses per-lab storage roots (`get_lab_storage_root(lab_id)`) and local user directory (`get_config("user.default_projects_dir")`); CLI retains `--use-shared/--shared-root` to support SSH/worker tasks.
  - Discovery/Dialog: Dialog helper complete; GUI relies on it and does not reference a global shared root.
  - DTOs/Validators: Single DTO source in `metadata.py` (Pydantic); centralize validation; repositories own persistence transformations. Treat `ProjectConfig` as read/view model only.
  - Context Sync: Add `MainWindow.contextChanged` signal; have `ProjectView`, `SubjectView`, `ExperimentView`, and `SettingsView` (workers) refresh on signal.

- **Tasks**:
  1. GUI storage surfaces
     - Delete Settings UI "Shared Storage" group; surface only per-lab root in GUI
     - Keep CLI flags `--use-shared/--shared-root` and clarify help text as worker/SSH-oriented
     - Keep `ProjectModel.shared_root` for CLI/dev compatibility; mark as deprecated in GUI context
  2. Discovery/dialog helper
     - (Done) `ProjectDiscoveryService.get_project_root_for_dialog(...)` returns lab root or user default dir
  3. Consolidate DTOs/validators
     - Ensure services import `LabDTO`/`ColonyDTO` from `metadata.py` exclusively
     - Convert setup-wizard dataclass DTOs to Pydantic or document as view-only
     - Remove duplicated `__post_init__` validations where Pydantic covers rules
  4. Context Sync
     - Define `MainWindow.contextChanged` as a real `Signal(object)` (missing)
     - Views (`ProjectView`, `SubjectView`, `ExperimentView`, `SettingsView`) already subscribe; confirm after signal is declared
  5. CI & audits
     - Add lints for banned `storage.shared_root` usage in new code
     - Run `.audit` checks and remove dead code

- **Expected Outcome**: Per-lab storage as the only shared model; discovery strictly lab+local; single DTO source; consistent view refresh on context changes; fewer user-facing ambiguities and cleaner layering.

### Medium Priority
1. **Scanner Improvements**: OS-specific video scanners for Windows/Linux
2. **Remote Processing**: SSH-based worker execution and scanning
3. **Advanced Features**: Distributed processing and job orchestration
4. **Lab-scoped Workers**: Model and manage workers under labs; bind SSH aliases and permissions to lab storage.


## 10. **Persistent User Profile — Single Source of Truth**
- Make the SQL `users` table authoritative for user profile persistence
- Store only `user.id` in `ConfigManager` as the active-user pointer — ✅ in services; 🔄 legacy CLI writes duplicate user fields
- Update `SetupService.is_user_configured()` and `get_user_profile()` to query repositories — ✅ implemented
- Add `UserService` with `get_current_user()`, `set_current_user_by_email()`, `update_profile()`, `delete_profile()`
- One-time migration: if legacy config keys `user.name/email/organization` exist and SQL has no user, seed `users` and remove those keys — 🔄 migration module present; not wired at startup
- Decide on stable `User.id` (UUID recommended) and handle email change/migration if using email-derived IDs


## Intended Setup/Project Logic (Authoritative)

1) Environment Root
- Default: `resolve_mus1_root()` determines a valid root
- Wizard: If user selects a different root, that selection overrides defaults
- After choosing root, the config DB is `<root>/config/config.db` and must be re-initialized immediately before subsequent steps
 - Optional: If the wizard's copy flag is enabled, copy an existing configuration into the new root — 🔄 pending in service layer

2) User Profile
- Persist user fields in SQL `users` table (authoritative)
- In config, store only `user.id` (active user)
- `user.default_projects_dir` set per-platform in SQL profile; ensure directory exists
 - Avoid persisting duplicate user fields in ConfigManager (cleanup legacy CLI path) — 🔄 pending

3) Shared Storage (Optional)
- `storage.shared_root` stored and validated; verify write permissions if requested
- Standard shared projects directory is `<shared_root>/Projects`

4) Labs
- Stored under `labs` (user scope), each lab: `id`, `name`, `institution`, `pi_name`, `projects`, `colonies`

5) Project Creation (GUI/CLI)
- Create dir and initialize `mus1.db` + `project.json`
- If a lab is selected/known:
  - Set `lab_id` via `ProjectManagerClean.set_lab_id()`
  - Append `{ name, path, created_date }` to `labs[lab_id].projects`
 - If a workgroup is active, associate project/lab with `workgroup_id`

6) Project Discovery Priority
- Labs (registered projects) → `user.default_projects_dir`

7) View Wiring
- `MainWindow` owns `ProjectManagerClean`
- Views (e.g., `ProjectView`) use the active `project_manager` from `MainWindow`


## Implementation Notes (File-Level Targets)

### ✅ **COMPLETED - Clean Architecture Migration**
- `src/mus1/gui/subject_view.py`: **✅ COMPLETED** - Full clean architecture migration with service layer integration
- `src/mus1/gui/experiment_view.py`: **✅ COMPLETED** - Service layer integration with plugin UI (needs plugin manager connection)
- `src/mus1/gui/project_view.py`: **✅ COMPLETED** - Clean architecture with proper service usage
- `src/mus1/gui/settings_view.py`: **✅ COMPLETED** - Complete SettingsView with User, Lab, Workers pages
- `src/mus1/gui/main_window.py`: **✅ COMPLETED** - Settings tab integration, theme propagation
- `src/mus1/gui/metadata_display.py`: **✅ COMPLETED** - Dict support for clean architecture data flow

### ✅ **COMPLETED - Core Architecture**
- `src/mus1/core/metadata.py`: **✅ COMPLETED** - Domain models, DTOs, enums properly implemented
- `src/mus1/core/repository.py`: **✅ COMPLETED** - Full repository pattern with proper CRUD operations
- `src/mus1/core/schema.py`: **✅ COMPLETED** - Complete database schema with relationships
- `src/mus1/core/project_manager_clean.py`: **✅ COMPLETED** - Clean project management with config handling
- `src/mus1/gui/gui_services.py`: **✅ COMPLETED** - Service layer bridging GUI to domain

### ✅ **COMPLETED - Configuration & Setup**
- `src/mus1/core/config_manager.py`: **✅ COMPLETED** - Root pointer, config management working correctly
- `src/mus1/core/setup_service.py`: **✅ COMPLETED** - Lab CRUD, user profile migration implemented
- `src/mus1/gui/setup_wizard.py`: **✅ COMPLETED** - Workflow with ConfigManager re-initialization

### 🔄 **PENDING - High Priority**
- `src/mus1/core/`: Implement ProjectServiceFactory for standardized service instantiation — **ARCHITECTURAL** (factory exists; continue adoption)
- `src/mus1/gui/main_window.py`: Ensure PluginManagerClean is wired (already done via `ProjectServiceFactory`)
- `src/mus1/core/repository.py`: Experiment-video relationship repository methods — **DONE** (update docs; keep improving callers)
- `src/mus1/core/schema.py`: Add metadata tables (objects, bodyparts, treatments, genotypes) for database persistence — **DESIGN DECISION**

### 🔄 **PENDING - Medium Priority**
- `src/mus1/main.py`: Prefer configured root for logs; avoid unconditional `resolve_mus1_root()` after setup — **MINOR**
- `src/mus1/core/setup_service.py`: Implement optional copy of existing config on root creation — **ENHANCEMENT**
- `src/mus1/core/simple_cli.py`: Stop writing duplicate user profile keys — **CLEANUP**
- `src/mus1/gui/setup_wizard.py`: Show per-step statuses/errors on conclusion page — **UX IMPROVEMENT**


## Recent Enhancements (2025-01)

### ✅ **Enhanced User Experience**
- **Optional Project Pre-selection**: User/lab selection dialog now allows optional project selection for faster workflow
- **Lab-Filtered Projects**: Project dropdown shows only projects registered with selected lab
- **Direct Project Loading**: Selected projects load immediately instead of browsing

### ✅ **Complete Lab Management System**
- **Lab CRUD Operations**: Full create/read/update/delete for labs with institution and PI tracking
- **Member Management**: Add/remove lab members with role-based permissions (admin/member)
- **Colony Management**: Create/update colonies with genotype tracking and subject assignment
- **Project Registration**: Register/unregister projects with labs for better organization
- **Manual Subject Assignment**: Direct UI for assigning subjects to colonies with validation

### ✅ **Enhanced Subject & Metadata Features**
- **Colony Membership Display**: Subject overview shows colony assignment for each subject
- **Manual Colony Operations**: Add/remove subjects from colonies through dedicated UI
- **Improved Metadata Tree**: Enhanced tree view with colony information and better column sorting
- **Validation & Error Handling**: Comprehensive error messages and confirmation dialogs


## Code Review Findings (2025-01)

### ✅ **Clean Architecture - FULLY IMPLEMENTED**
- **Repository Pattern**: Complete with proper domain model separation
- **Service Layer**: Clean bridging between GUI and domain logic
- **GUI Views**: All views use services, no direct database access
- **Test Coverage**: 62 functional tests validate all relationships
- **Domain Models**: Proper DTOs and enums throughout

### 🚨 **Critical Gaps Identified**
1. **Modal Dialogs**: Replace remaining QMessageBox usages with navigation log/status in development flows
2. **Context Sync**: Define `MainWindow.contextChanged` signal (views already subscribe)
3. **Scan Targets**: Reintroduce `ScanTargetRepository` surface in `RepositoryFactory` and wire GUI under Lab manager for scan/import with optional move
4. **Video Listing**: Add `VideoRepository.find_all()` or update `ProjectManagerClean.list_videos()` to not call a missing method

### 📊 **Architecture Health Assessment**
- **Overall Status**: **EXCELLENT** - Core architecture solid and working
- **Test Quality**: **COMPREHENSIVE** - 62 tests covering all relationships
- **GUI State**: **CLEAN** - No direct database access, proper service usage
- **Configuration**: **ROBUST** - JSON serialization with Path handling works correctly
- **Service Patterns**: **STANDARDIZING** - Clear patterns defined, implementation in progress


## Future Features

### Remote Processing & Scanning
- SSH-based worker execution
- Remote video scanning across networks
- Shared storage integration
- Cross-platform deployment automation



