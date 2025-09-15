# MUS1 Roadmap

This roadmap shows current status and planned development priorities. Items are prioritized by impact and risk.


## Known Issues
- Legacy GUI components need migration to clean architecture
- Windows/Linux video scanners lack OS-specific optimizations
- Some plugins need migration to new service pattern
- Setup Wizard writes user/lab/storage to the wrong config DB until after completion
- No first-class workgroup model or shareable key in SQL backend
- Labs stored as JSON in config entries (not normalized SQL); no membership
- Wizard lacks explicit default projects directory chooser and app preferences page
- Modal popups used during setup; prefer in-app log/status per development guidelines

## Development Priorities

### High Priority
1. **GUI Migration**: Update GUI components to use clean architecture
2. **Plugin Migration**: Migrate existing plugins to new service pattern
3. **Code Cleanup**: Remove redundant DTOs and unused code

4. **✅ COMPLETED: Authoritative Setup & Project Flow**
   - **✅ Make MUS1 root selection in GUI wizard authoritative**:
     - Use page-selected root to construct `MUS1RootLocationDTO`
     - Immediately re-initialize `ConfigManager` to `<root>/config/config.db` after MUS1 root step succeeds (before saving user/storage/lab)
       - **✅ In `src/mus1/gui/setup_wizard.py`**: after calling `setup_service.setup_mus1_root_location`, call `init_config_manager(<root>/config/config.db)` and re-create the `SetupService` so subsequent `set_config` writes target the new DB
       - **✅ In `src/mus1/core/setup_service.py`**: stop caching `config_manager` at construction; fetch via `get_config_manager()` inside each operation or provide a `rebind_config_manager()` used right after root commit
       - **✅ Ensure `run_setup_workflow` executes MUS1 root first, checks success, then proceeds; short-circuit and surface error state if root fails
   - **✅ Ensure setup workflow runs async and conclusion page reflects errors**
     - In `ConclusionPage`, render per-step statuses from `result["steps_completed"]` and `result["errors"]`; remove generic success text when errors exist
   - **✅ Wire `ProjectView` to active `ProjectManagerClean` from `MainWindow`**
   - **✅ Register newly created projects under labs**:
     - Set `lab_id` in project config when lab is known/selected
     - Append to `labs[lab_id].projects` with name/path/created_date
   - Replace modal popups during setup with navigation/status log output for development builds (follow project logging bus guidelines)

5. **🔄 PARTIALLY COMPLETED: Workgroup Model with Shareable Key (SQL, not JSON)**
   - **✅ Add normalized tables in the configuration database for collaborative grouping**:
     - **✅ In `src/mus1/core/schema.py` (config DB context), create `WorkgroupModel(id, name, share_key_hash, created_at)` and `WorkgroupMemberModel(workgroup_id, member_email, role, added_at)`**
     - Store only a salted hash of the shareable key; never persist the raw key
     - Provide key generation/rotation and join-by-key verification utilities in `src/mus1/core/setup_service.py`
   - Wizard integration:
     - Add a `Workgroup` page to create a workgroup (name) and generate a one-time display shareable key; allow joining an existing workgroup via key
     - Persist membership using the current `user.email`; link selected `lab` records to `workgroup_id` when applicable
   - CLI parity:
     - Expose `mus1 setup workgroup create`, `mus1 setup workgroup rotate-key`, and `mus1 setup workgroup join --key` with clear `--help` entries

6. **✅ COMPLETED: Normalize Labs to SQL (avoid JSON in config entries)**
   - **✅ Replace `labs` JSON blob in user scope with relational tables in the configuration database**:
     - **✅ Create `LabModel(id, name, institution, pi_name, creator_id, created_at)` and `LabProjectModel(lab_id, name, path, created_date)`**
     - **✅ Migrate reads/writes in `src/mus1/core/setup_service.py` from `set_config("labs", ...)` to SQL CRUD via a lightweight repository**
   - **✅ Provide a one-time migration that reads existing `labs` config entry and populates the new tables** (via backward-compatible get_labs() method)

7. **✅ COMPLETED: GUI Tab Reorganization**
   - **✅ Add Settings tab with User Settings, Lab Settings, and Workers**:
     - Create `SettingsView` with navigation for "User Settings", "Lab Settings", "Workers"
     - Move Workers functionality from `ProjectView` to `SettingsView`
     - Keep Project tab focused on project-specific operations
   - **✅ User Settings**: Profile management (name, email, organization, default directories)
   - **✅ Lab Settings**: Lab creation, management, and project association viewing
   - **✅ Workers**: SSH worker configuration moved from Project tab

8. **Wizard UX & Preferences**
   - Add a `Project Storage` page to choose `user.default_projects_dir` explicitly; create directory if missing
   - Add an `App Preferences` page (theme, global sort mode, optional telemetry) and persist via `ConfigManager` under `user.*`
   - Update `src/mus1/gui/setup_wizard.py` to remove `QMessageBox` info/critical usage in dev; surface messages via the navigation/status pane

9. **Config Root Usage Consistency**
   - In `src/mus1/main.py`, when configuring logs, prefer configured `get_config("mus1.root_path")` when present; fall back to `resolve_mus1_root()` only if unset
   - Audit imports using `resolve_mus1_root()` and switch to configuration value post-setup where appropriate

### Medium Priority
1. **Scanner Improvements**: OS-specific video scanners for Windows/Linux
2. **Remote Processing**: SSH-based worker execution and scanning
3. **Advanced Features**: Distributed processing and job orchestration

## Intended Setup/Project Logic (Authoritative)

1) Environment Root
- Default: `resolve_mus1_root()` determines a valid root
- Wizard: If user selects a different root, that selection overrides defaults
- After choosing root, the config DB is `<root>/config/config.db` and must be re-initialized immediately before subsequent steps

2) User Profile
- Store `user.name`, `user.email`, `user.organization`
- `user.default_projects_dir` set per-platform; ensure directory exists

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
- Labs config → `user.default_projects_dir` → `<storage.shared_root>/Projects`

7) View Wiring
- `MainWindow` owns `ProjectManagerClean`
- Views (e.g., `ProjectView`) use the active `project_manager` from `MainWindow`

## Implementation Notes (File-Level Targets)
- `src/mus1/gui/setup_wizard.py`: **✅ COMPLETED** - reordered workflow with proper ConfigManager re-initialization, async execution, error handling
- `src/mus1/core/setup_service.py`: **✅ COMPLETED** - removed cached config reference, migrated lab CRUD to SQL repository with User/Lab entities
- `src/mus1/core/config_manager.py`: **✅ COMPLETED** - `init_config_manager(path)` exposed and used for immediate rebind after root setup
- `src/mus1/core/schema.py`: **✅ COMPLETED** - added UserModel, LabModel, LabProjectModel, WorkgroupModel, WorkgroupMemberModel tables
- `src/mus1/core/repository.py`: **✅ COMPLETED** - added UserRepository, LabRepository with proper CRUD operations
- `src/mus1/core/metadata.py`: **✅ COMPLETED** - added User, Lab, Workgroup domain models and DTOs
- `src/mus1/gui/settings_view.py`: **✅ COMPLETED** - new SettingsView with User Settings, Lab Settings, Workers pages
- `src/mus1/gui/main_window.py`: **✅ COMPLETED** - added Settings tab, updated tab management and theme propagation
- `src/mus1/gui/project_view.py`: **✅ COMPLETED** - removed Workers functionality, focused on project operations
- `src/mus1/main.py`: prefer configured root for logs; avoid unconditional `resolve_mus1_root()` after setup

## Future Features

### Remote Processing & Scanning
- SSH-based worker execution
- Remote video scanning across networks
- Shared storage integration
- Cross-platform deployment automation



