# MUS1 Launch Guide

## 📋 **Unified Launch Architecture**

MUS1 has a **clean, streamlined launch architecture** that works identically for both development and production users, with automatic setup detection and user preference persistence.

### **Entry Points (Defined in pyproject.toml)**
```toml
[project.scripts]
mus1 = "mus1.core.simple_cli:app"        # CLI entry point
mus1-cli = "mus1.core.simple_cli:app"    # CLI alias
mus1-gui = "mus1.main:main"              # GUI entry point
```

### **Launch Methods**

#### **Production Users (After `pip install mus1`)**
```bash
mus1-gui                    # GUI mode (recommended)
mus1 --help                 # CLI help
mus1 project list           # CLI commands
```

#### **Development Users**
```bash
./setup.sh                  # One-time environment setup
./dev-launch.sh gui         # GUI mode (recommended)
./dev-launch.sh --help      # CLI help
./dev-launch.sh project list # CLI commands
```

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
1. **Setup Detection**: MUS1 detects it's the first launch
2. **Setup Wizard**: Guided configuration wizard appears
   - User profile (name, email, organization)
   - MUS1 root location preference
   - Shared storage configuration (optional)
   - First lab creation (optional)
3. **Configuration Persistence**: All preferences saved to SQLite
4. **Project Selection**: Welcome dialog guides first project creation

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

### **Clean Separation Achieved**
- ✅ **Single Source of Truth**: Each service has one clear responsibility
- ✅ **Dependency Injection**: Services use repositories, not direct database access
- ✅ **UI Independence**: Business logic separated from presentation
- ✅ **Testability**: Each layer independently testable
- ✅ **Configuration Hierarchy**: Install → User → Lab → Project settings

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

### **Seamless Workflow**
```bash
# First time (automatic setup wizard appears)
mus1-gui                    # Production
./dev-launch.sh gui         # Development

# Subsequent launches (remembers your preferences)
mus1-gui                    # Loads last project automatically
./dev-launch.sh project list # Same CLI commands work everywhere
```

### **Smart Features**
- ✅ **Automatic Setup Detection**: First-time users get guided wizard
- ✅ **Preference Persistence**: User choices maintained across restarts
- ✅ **Intelligent Discovery**: Projects found from configured locations
- ✅ **Unified Commands**: Same CLI works in dev and production
- ✅ **Configuration Hierarchy**: Settings cascade properly (Install → User → Lab → Project)

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

# Rebuild virtual environment
rm -rf .venv && ./setup.sh

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
# macOS Qt setup
export QT_QPA_PLATFORM=cocoa

# Linux Qt setup
export QT_QPA_PLATFORM=xcb
export DISPLAY=:0

# Check Qt plugins
python -c "import PySide6; print(PySide6.__file__)"
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
