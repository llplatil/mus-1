# MUS1: Video Analysis System

A SQLite-based system for organizing and analyzing animal behavior videos with clean architecture, application-level user management, and complete lab-colony-project hierarchy.

## Installation

### Production Users
```bash
pip install mus1
```

### Developers
```bash
git clone <repository-url>
cd mus1
./setup.sh
```

## Quick Start

### GUI Mode (Recommended)
```bash
# Production
mus1-gui                    # Normal GUI launch
mus1-gui --setup           # GUI with setup wizard (can rerun anytime)

# Development
./dev-launch.sh gui        # Normal GUI launch
./dev-launch.sh gui --setup # GUI with setup wizard (can rerun anytime)
```

### CLI Mode
```bash
# Production
mus1 --help                # CLI help
mus1 --setup               # CLI mode with setup wizard

# Development
./dev-launch.sh --help     # CLI help
./dev-launch.sh --setup    # CLI mode with setup wizard
```

## Current Status

### ⚠️ **Remaining Issues**
- **GUI has some remaining bugs** - subject management, video linking, and lab management now work, but other components may have issues
- **JSON serialization issues** cause project files to become corrupted
- **Incomplete clean architecture migration** - subject view, video linking, and lab management migrated, other components still need work
- **Project loading fails** due to corruption and missing methods in some areas

### ✅ **What Works**
- **CLI Interface**: Basic command-line operations work reliably
- **Setup Wizard**: Can be launched via `--setup` flag, basic user profile creation works
- **Video Linking System**: Videos can be linked to experiments with proper association tables
- **Subject Management**: Subject creation and genotype handling works with proper data relationships
- **Lab Management**: Complete lab creation, member management, colony management, and project registration
- **Colony Management**: Manual subject-to-colony assignment/removal with proper validation
- **User Experience**: Enhanced user/lab selection dialog with optional project pre-selection
- **Batch Creation**: Experiments can be grouped into batches for analysis
- **Database Schema**: SQL tables exist for users, labs, colonies, subjects, experiments, videos
- **Repository Pattern**: Data access layer implemented with proper update/merge handling

### ❌ **What's Broken**
- **GUI**: Some remaining AttributeError and signal disconnection issues (subject view and video linking fixed)

- **State Management**: References resolved in subject view, video linking, and lab management
- **Lab-Project Association**: Complete GUI integration with project registration and management
- **Plugin System**: Entry-point discovery exists but GUI integration broken

## Features (Planned/Partial)

### 🎯 **Application-Level User & Lab Management (Complete)**
- Complete user profile management with SQL-backed persistence
- Full lab creation and management with institution/PI tracking
- Member management with role-based permissions (admin/member)
- Colony management with genotype tracking and subject assignment
- Project registration and association with labs
- Enhanced user/lab selection dialog with optional project pre-selection

### 🔄 **Setup Wizard (Partial)**
- Can be launched via `--setup` flag
- Basic user profile setup works
- Advanced configuration options missing

### 🎬 **Video Analysis System (Working)**
- Video linking to experiments with proper database associations
- Batch creation for grouping experiments for analysis
- File hash computation for video deduplication

### 🏗️ **Clean Architecture (Partial)**
- Repository pattern implemented with proper update/merge handling
- Service layer implemented for subject and experiment management
- GUI migration completed for subject view and video linking

### 🎨 **GUI (Partial)**
- Subject management and video linking work properly
- Basic tab structure exists with some functionality working
- Some remaining bugs and signal handling issues in other components

### 🔧 **Configuration System (Partial)**
- Basic hierarchical config exists
- JSON serialization works but has Path object corruption bugs
- Project discovery works for finding existing projects

## Usage Examples (CLI Only - GUI Broken)

### Basic CLI Operations (Working)
```bash
# Setup wizard
mus1 --setup

# List projects (may work)
mus1 project list

# Check status
mus1 setup status
```

### Data Management (May Not Work)
```bash
# These commands exist but may have issues
mus1 add-subject SUB001 --sex M --designation experimental
mus1 add-experiment EXP001 SUB001 "Open Field Test" --date 2024-01-15
mus1 list-subjects
```

### Lab Management (Broken)
```bash
# Lab commands exist but GUI integration broken
mus1 lab create mylab "My Laboratory"
mus1 lab list
```

## Requirements

- Python 3.10+
- macOS, Linux, or Windows
- Qt usage must go through the GUI Qt facade (`src/mus1/gui/qt.py`). Do not import `PyQt6` or `PySide6` directly in GUI views.

## Troubleshooting

### Fresh Start
```bash
# Remove configuration to start over
rm -rf ~/Library/Application\ Support/MUS1/  # macOS
rm -rf ~/.config/mus1/                       # Linux
rm -rf "$APPDATA/MUS1/"                      # Windows
```

### Check Status
```bash
mus1 setup status
```

### Override Configuration Location
### Known Behavior / Limitations
- Setup Wizard is creation-focused and does not offer picking existing users/labs. Use the User/Lab Selection dialog at startup for existing selections.
- Storage precedence at runtime is: project `shared_root` → lab storage root → global shared storage. The wizard configures only the global shared storage. Set per-project in Project Settings.
- Project dropdown is filtered by Local/Shared; ensure the filter matches where the project resides.
```bash
export MUS1_ROOT="/custom/path"
mus1-gui
```

## Documentation

- [docs/dev/ARCHITECTURE_CURRENT.md](docs/dev/ARCHITECTURE_CURRENT.md) - Architecture details
- [docs/dev/ROADMAP.md](docs/dev/ROADMAP.md) - Development roadmap
