# MUS1 Launch Guide

## 📋 **Launch Architecture**

MUS1 has a **platform-aware launch architecture** with different behaviors for development and production environments. The system automatically detects the platform and available Qt backends, with fallback handling for GUI compatibility issues.

### **Entry Points (Defined in pyproject.toml)**
```toml
[project.scripts]
mus1 = "mus1.core.simple_cli:app"        # CLI entry point
mus1-gui = "mus1.main:main"              # GUI entry point
```

### **Launch Methods**

#### **Production Users (After `pip install mus1`)**
```bash
mus1-gui                    # GUI mode (may fail on macOS due to Qt issues)
mus1-gui --setup            # GUI mode with setup wizard (can rerun anytime)
mus1 --help                 # CLI help (always works)
mus1 --setup                # CLI mode with setup wizard
mus1 project list           # CLI commands (always works)
```

#### **Development Users**
```bash
./setup.sh                  # Environment setup with Qt diagnostics
./dev-launch.sh gui         # GUI mode with platform-specific Qt setup
./dev-launch.sh gui --setup # GUI mode with setup wizard (can rerun anytime)
./dev-launch.sh --help      # CLI help
./dev-launch.sh --setup     # CLI mode with setup wizard
./dev-launch.sh project list # CLI commands
```

**Important Notes:**
- **GUI may not work** on macOS due to Qt platform plugin issues
- **CLI always works** regardless of Qt/GUI status
- **Platform detection** automatically handles Qt backend selection
- **Wizard limitations**: The Setup Wizard focuses on creating configuration. To use an existing user/lab, complete or cancel the wizard and select via the User/Lab Selection dialog at startup.
- **Qt facade required**: All GUI code must import Qt via `mus1/gui/qt.py`. Direct `PyQt6`/`PySide6` imports can cause platform crashes.

---

## 🔄 **Complete Launch Flow**

### **First-Time User Experience**
```bash
# Production: Install and launch
pip install mus1
mus1-gui

# Development: Setup and launch
./setup.sh
./dev-launch.sh gui
```

**What happens automatically in phases:**

#### **Phase 1: Environment Setup**
- **Dependencies**: System-wide installation (production) or virtual environment (dev)
- **Config Directory**: Platform-specific directory creation
  - macOS: `~/Library/Application Support/mus1/`
  - Linux: `~/.config/mus1/` or `$XDG_CONFIG_HOME/mus1/`
  - Windows: `%APPDATA%/mus1/`
- **SQLite Database**: Configuration database initialization

#### **Phase 2: Application Environment**
- **Qt Platform**: GUI environment detection and setup
- **Theme System**: Platform-appropriate theming application
- **Logging**: File and console logging configuration

#### **Phase 3: User Environment**
1. **Setup Detection**: MUS1 detects it's the first launch or setup was requested via `--setup` flag
2. **Setup Wizard**: Guided configuration wizard appears (can be rerun anytime)
   - User profile (name, email, organization)
   - Shared storage configuration (optional)
   - First lab creation (optional)
3. **Configuration Persistence**: All preferences saved to SQLite
4. **User/Lab Selection**: Enhanced dialog with user profile, lab selection, and optional project pre-selection
5. **Project Management**: Project creation and selection handled in Project tab

#### **External Configuration Roots (Best Practices)**
- You can choose any location for the MUS1 root in the Setup Wizard (including external drives like `/Volumes/CuSSD3`).
- MUS1 writes a small locator at the platform default path to rediscover your chosen root across reinstalls/shells:
  - macOS: `~/Library/Application Support/MUS1/config/root_pointer.json`
  - Contents: `{ "root": "/absolute/path", "updated_at": "ISO8601" }`
- On startup, MUS1 resolves the configuration root in this order: `MUS1_ROOT` env → locator file → platform default → create default.
- If the external drive is temporarily unavailable, MUS1 will prompt you to:
  - Retry later
  - Locate an existing configuration (browse to the root that contains `config/config.db`)
  - Create a new configuration (optionally copy later)
- This pattern avoids dev-only helpers and ensures production launches remain consistent.
- **Storage precedence**: At runtime, storage resolves as project `shared_root` → lab storage root → global shared storage. The wizard configures only the global shared storage. Set per-project in Project Settings.

### **Subsequent Launches**
```bash
# GUI mode (remembers last project)
mus1-gui                    # Production
./dev-launch.sh gui         # Development

# CLI mode (same commands work everywhere)
mus1 project list          # Production
./dev-launch.sh project list # Development
```

**Smart workflow:**
1. **Preference Loading**: User settings automatically restored
2. **Project Discovery**: Projects found from configured locations
3. **State Restoration**: Last used project reopened
4. **Seamless Experience**: No manual configuration needed
5. **List Filters**: Project dropdown is filtered by Local/Shared; ensure it matches where the project resides.

---

## 🏗️ **Clean Architecture Overview**

### **Layered Architecture**
```
┌─────────────────────────────────────┐
│        Presentation Layer           │
│  • main_window.py (GUI coordination)│
│  • simple_cli.py (CLI commands)     │
│  • setup_wizard.py (setup UI)       │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│      Application/Service Layer      │
│  • setup_service.py (setup logic)   │
│  • project_discovery_service.py     │
│  • project_manager_clean.py         │
│  • plugin_manager_clean.py          │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│          Domain Layer               │
│  • metadata.py (business entities)  │
│  • repository.py (data access)      │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│      Infrastructure Layer           │
│  • schema.py (SQLite models)        │
│  • config_manager.py (settings)     │
└─────────────────────────────────────┘
```

### **Service Responsibilities**
- **SetupService**: User configuration, shared storage, labs, colonies
- **ProjectDiscoveryService**: Intelligent project path resolution
- **ProjectManagerClean**: Project operations with lab-colony hierarchy
- **PluginManagerClean**: Plugin discovery and analysis execution

### **Architecture Status (Partial)**
- **✅ Repository Pattern**: Implemented with proper update/merge handling and video associations
- **✅ Domain Models**: Entities exist in metadata.py with proper genotype aliasing
- **✅ Service Layer**: Implemented for subject and experiment management with video linking
- **🔄 Clean Separation**: Achieved for subject view and video linking - GUI uses services properly
- **🔄 UI Independence**: Business logic separated for core functionality, some components still need migration


---

## 📁 **File Responsibilities**

### **Entry Points & Launch**
| File | Responsibility | Entry Point? |
|------|----------------|--------------|
| `setup.sh` | Development environment setup | No |
| `dev-launch.sh` | Development launcher with venv management | No |
| `pyproject.toml` | Defines entry points and dependencies | No |
| `main.py` | GUI application entry point | `mus1-gui` |
| `__main__.py` | Module execution delegation | `python -m mus1` |
| `simple_cli.py` | CLI commands and routing | `mus1`, `mus1-cli` |

### **Clean Architecture Implementation**
| File | Layer | Responsibility |
|------|-------|----------------|
| `metadata.py` | Domain | Business entities and validation |
| `repository.py` | Domain | Data access patterns |
| `schema.py` | Infrastructure | SQLite database models |
| `config_manager.py` | Infrastructure | Hierarchical configuration |
| `setup_service.py` | Application | Setup and configuration logic |
| `project_discovery_service.py` | Application | Project path resolution |
| `project_manager_clean.py` | Application | Project operations |
| `plugin_manager_clean.py` | Application | Plugin management |
| `main_window.py` | Presentation | GUI coordination |
| `setup_wizard.py` | Presentation | Setup UI flow |

---

##  **User Experience**

### **Actual Launch Behavior**

#### **GUI Launch (Partial)**
```bash
# Subject management and video linking now work
mus1-gui                    # Production - subject/experiment features work
./dev-launch.sh gui         # Development - subject/experiment features work
```

#### **CLI Launch (Always Works)**
```bash
# CLI works regardless of GUI/Qt status
mus1 --help                 # Production CLI
./dev-launch.sh project list # Development CLI
```

### **Known Issues**

#### **macOS Qt Platform Plugin Problem**
- **Symptom**: `Could not find Qt platform plugin "cocoa"`
- **Cause**: PySide6/PyQt6 platform plugins not compatible with macOS security restrictions
- **Workaround**: Use CLI-only features, or try alternative Qt installations
- **Status**: Known issue affecting Qt Python bindings on macOS

#### **Platform-Specific Behavior**
- **macOS**: GUI may fail, CLI works
- **Linux**: GUI and CLI both work (with X11/Wayland)
- **Windows**: GUI and CLI both work

### **Preferences & Recents**
- MUS1 persists user profile and lab information in the configuration database (SQL) at the chosen root.
- The last opened project is stored in SQL under the user scope and used to streamline subsequent launches.

### **Error Recovery**
- **Setup cancelled**: Retry dialog with clear options
- **Configuration corrupted**: `mus1 setup user --force` to reset
- **Project not found**: Automatic path resolution from configured locations
- **Permission issues**: Clear error messages with suggested fixes

### **Cross-Platform Consistency**
- **macOS**: Native paths (`~/Documents/MUS1/Projects`)
- **Linux/Windows**: Standard user directories
- **Shared Storage**: Automatic detection and permission checking
- **Virtual Environment**: Seamless dev/prod environment management

### **Environment Troubleshooting**

#### **Development Environment Issues**
```bash
# Check if virtual environment is working
source .venv/bin/activate && python -c "import mus1"

# Rebuild virtual environment with Qt diagnostics
rm -rf .venv && ./setup.sh

# Setup includes Qt platform checks now
# Look for Qt diagnostic messages during setup

# Check Python version in venv
./dev-launch.sh --version
```

#### **Production Environment Issues**
```bash
# Check MUS1 installation
python -c "import mus1; print('MUS1 installed')"

# Check PySide6 installation
python -c "import PySide6.QtWidgets; print('Qt available')"

# Check config directory permissions
ls -la ~/Library/Application\ Support/mus1/  # macOS
ls -la ~/.config/mus1/                        # Linux
```

#### **Qt/GUI Environment Issues**
```bash
# Check Qt availability
python -c "try:
    import PyQt6
    print('PyQt6 available')
except ImportError:
    try:
        import PySide6
        print('PySide6 available')
    except ImportError:
        print('No Qt backend available')

# Test Qt GUI capability
python -c "try:
    import PyQt6.QtWidgets as QtW
    import sys
    app = QtW.QApplication(sys.argv)
    print('Qt GUI works')
except Exception as e:
    print(f'Qt GUI failed: {e}')

# macOS specific (may not work due to platform plugin issues)
export QT_QPA_PLATFORM=cocoa

# Linux Qt setup
export QT_QPA_PLATFORM=xcb
export DISPLAY=:0
```

#### **Configuration Database Issues**
```bash
# Check config database location
mus1 setup status | grep "Config database"

# Reset configuration (nuclear option)
rm ~/Library/Application\ Support/mus1/config.db
# Then restart MUS1 to recreate
```

#### **Environment Variables**
```bash
# Override MUS1 root (useful for testing)
export MUS1_ROOT="/tmp/mus1-test"

# Force Qt platform
export QT_QPA_PLATFORM_PLUGIN_PATH="/usr/lib/qt6/plugins"
export QT_QPA_PLATFORM="xcb"
```

---



### **Clean Architecture Development**

#### **Working Features**
- **Video Linking**: Videos properly associated with experiments via database relationships
- **Subject Management**: Subject creation with genotype handling and manual colony assignment
- **Lab Management**: Complete lab creation, member management, colony management, and project registration
- **User Experience**: Enhanced user/lab selection with optional project pre-selection
- **Colony Management**: Manual subject-to-colony assignment/removal with validation
- **Batch Creation**: Experiments can be grouped for analysis workflows

#### **Recent Enhancements (2025-01)**
- **Enhanced User/Lab Selection Dialog**: Added optional project pre-selection for faster workflow
- **Complete Lab Management System**: Full CRUD operations for labs, members, colonies, and projects
- **Manual Colony Assignment**: Direct UI for adding/removing subjects from colonies
- **Improved Metadata Display**: Colony membership shown in subject overview tree
- **Service Layer Extensions**: Comprehensive lab management methods in SetupService and LabService

#### **Adding New Features**
- **Domain Entities**: Add to `metadata.py` with validation
- **Business Logic**: Create service in Application layer
- **Data Operations**: Add repository methods to `repository.py`
- **CLI Commands**: Extend `simple_cli.py` with typer decorators
- **GUI Features**: Update views to use services, not direct database access

#### **Service Layer Pattern**
```python
# Example: Adding a new service
class MyNewService:
    def __init__(self, repository: MyRepository):
        self.repository = repository

    def business_operation(self, dto: MyDTO) -> Result:
        # Business logic here
        entity = MyEntity(**dto.dict())
        return self.repository.save(entity)

# Usage in CLI/GUI
service = MyNewService(repository)
result = service.business_operation(dto)
```

### **Development Workflow**
```bash
# Setup development environment
./setup.sh

# Launch with hot-reload capabilities
./dev-launch.sh gui

# Test CLI commands
./dev-launch.sh --help
./dev-launch.sh setup status

# Run workflow tests
python test_workflow.py

# Check architecture documentation
cat docs/dev/ARCHITECTURE_CURRENT.md
```

### **Testing Strategy**
- **Unit Tests**: Test services and repositories independently
- **Integration Tests**: Test CLI commands with real database
- **Workflow Tests**: End-to-end user experience testing
- **Architecture Tests**: Verify clean separation of concerns

### **Key Development Principles**
- **Single Responsibility**: Each class/function has one clear job
- **Dependency Injection**: Pass repositories to services, not create them
- **Clean Interfaces**: Use DTOs for data transfer between layers
- **Configuration Hierarchy**: Respect the Install → User → Lab → Project cascade
- **Error Handling**: Clear error messages and recovery options
