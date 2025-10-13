# MUS1 Roadmap

This roadmap shows current status and planned development priorities. Items are prioritized by impact and risk.


## Known Issues
- Legacy GUI components need migration to clean architecture
- Windows/Linux video scanners lack OS-specific optimizations
- Some plugins need migration to new service pattern
- User profile fields duplicated between ConfigManager and SQL `users` table (via legacy CLI); risk of drift
- Wizard lacks explicit default projects directory chooser and app preferences page
- Modal popups used during setup; prefer in-app log/status per development guidelines

## Development Priorities

### High Priority
1. **GUI Migration**: Update remaining GUI components to use clean architecture (Subject View ✅, Video Linking ✅)
2. **Plugin Migration**: Migrate existing plugins to new service pattern
3. **Code Cleanup**: Remove redundant DTOs and unused code

4. **🔄 PARTIAL: Setup & Project Flow**
   - **❌ MUS1 root selection and ConfigManager re-initialization**: JSON serialization bugs break project loading
   - **❌ Setup workflow async execution**: Works but error handling incomplete, conclusion page doesn't show per-step status
   - **✅ ProjectView wiring**: Subject View and experiment management now use clean architecture
   - **❌ Lab-project registration**: GUI integration broken despite database schema existing
   - **❌ Modal popup replacement**: Still uses QMessageBox in development builds

5. **❌ NOT IMPLEMENTED: Workgroup Model**
   - **✅ Database schema exists**: Models created but no functional UI or CLI implementation

   - **❌ No key generation/verification**: Utilities not implemented

6. **❌ BROKEN: Lab Management**
   - **✅ Database schema exists**: LabModel and LabProjectModel tables created
   - **❌ Migration incomplete**: One-time migration not properly implemented
   - **❌ GUI integration broken**: Lab-project association doesn't work in practice

7. **❌ BROKEN: GUI Tab Reorganization**
   - **❌ Settings tab exists**: Basic tab structure created but functionality broken
   - **❌ User Settings**: Profile management has bugs due to state_manager references
   - **❌ Lab Settings**: Lab creation/management broken
   - **❌ Workers**: SSH worker configuration moved but may not work due to missing methods

8. **❌ NOT IMPLEMENTED: Wizard UX & Preferences**

   - **❌ No App Preferences page**: Theme/sort preferences not in wizard
   - **❌ QMessageBox still used**: Modal popups not replaced with navigation log

9. **❌ BROKEN: Config Root Usage Consistency**

   - **❌ ConfigManager rebinding**: Works but project corruption makes it irrelevant
   - **❌ Startup resolution**: Fails when projects are corrupted
   - In `src/mus1/main.py`, prefer configured `get_config("mus1.root_path")` for logs when present; fall back to `resolve_mus1_root()` only if unset — 🔄 pending
   - Implement optional "Copy existing configuration to new location" when creating a new root — 🔄 pending (wizard collects flag; service does not copy)
11. **Lab-Centric Sharing (Planned)**
   - Normalize shared resources under the lab and expose retrieval by lab membership
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
     - Project selection: separate Shared (by labs) vs Local sections
     - Settings → Lab Settings: members/workers/scan targets management
     - CLI parity: `mus1 lab members|workers|targets ...`
   - Migration:
     - Backfill membership for lab creators as `admin`
     - Attach existing workers/scan targets to selected lab without data duplication

  - In `src/mus1/main.py`, when configuring logs, prefer configured `get_config("mus1.root_path")` when present; fall back to `resolve_mus1_root()` only if unset — 🔄 pending
  - Audit imports using `resolve_mus1_root()` and switch to configuration value post-setup where appropriate — 🔄 pending

### Medium Priority
1. **Scanner Improvements**: OS-specific video scanners for Windows/Linux
2. **Remote Processing**: SSH-based worker execution and scanning
3. **Advanced Features**: Distributed processing and job orchestration

10. **Persistent User Profile — Single Source of Truth**
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
- Labs config → `user.default_projects_dir` → `<storage.shared_root>/Projects`

7) View Wiring
- `MainWindow` owns `ProjectManagerClean`
- Views (e.g., `ProjectView`) use the active `project_manager` from `MainWindow`

## Implementation Notes (File-Level Targets)
- `src/mus1/gui/setup_wizard.py`: **✅ COMPLETED** - reordered workflow with proper ConfigManager re-initialization, async execution, error handling
- `src/mus1/core/setup_service.py`: **✅ COMPLETED** - removed cached config reference, migrated lab CRUD to SQL repository with User/Lab entities
- `src/mus1/core/config_manager.py`: **✅ COMPLETED** - `init_config_manager(path)` exposed and used for immediate rebind after root setup; root pointer implemented
- `src/mus1/core/schema.py`: **✅ COMPLETED** - added UserModel, LabModel, LabProjectModel, WorkgroupModel, WorkgroupMemberModel, experiment_videos tables
- `src/mus1/core/repository.py`: **✅ COMPLETED** - added UserRepository, LabRepository, VideoRepository with proper CRUD operations including find_by_path and merge handling
- `src/mus1/core/metadata.py`: **✅ COMPLETED** - added User, Lab, Workgroup domain models and DTOs; fixed Subject dataclass conflicts and genotype aliasing
- `src/mus1/core/project_manager_clean.py`: **✅ COMPLETED** - added batch creation, video linking with proper SQL text() usage
- `src/mus1/gui/settings_view.py`: **✅ COMPLETED** - new SettingsView with User Settings, Lab Settings, Workers pages
- `src/mus1/gui/main_window.py`: **✅ COMPLETED** - added Settings tab, updated tab management and theme propagation
- `src/mus1/gui/project_view.py`: **✅ COMPLETED** - removed Workers functionality, focused on project operations
- `src/mus1/gui/subject_view.py`: **✅ COMPLETED** - migrated to clean architecture, removed state_manager dependencies, fixed metadata display data format
- `src/mus1/gui/metadata_display.py`: **✅ COMPLETED** - added dict support for clean architecture data flow, disabled dangerous editing
- `src/mus1/gui/experiment_view.py`: **✅ COMPLETED** - added batch creation functionality with experiment selection grid
- `src/mus1/main.py`: prefer configured root for logs; avoid unconditional `resolve_mus1_root()` after setup — 🔄 pending
- `src/mus1/core/setup_service.py`: implement optional copy of existing config on root creation — 🔄 pending
- `src/mus1/core/simple_cli.py`: stop writing duplicate user profile keys; rely on SQL-backed services — 🔄 pending
- `src/mus1/gui/setup_wizard.py`: show per-step statuses/errors on conclusion page; replace modal popups in dev builds — 🔄 pending

## Future Features

### Remote Processing & Scanning
- SSH-based worker execution
- Remote video scanning across networks
- Shared storage integration
- Cross-platform deployment automation



