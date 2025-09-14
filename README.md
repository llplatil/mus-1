# MUS1: Clean Video Analysis System

A clean, SQLite-based system for organizing and analyzing animal behavior videos with a simple, focused architecture.

## 🚀 **Quick Start**

### **First Time Setup**
```bash
# 1. Clone and setup environment
git clone <repository-url>
cd mus1
./setup.sh

# 2. Launch MUS1 (setup wizard appears automatically)
./dev-launch.sh gui
```

That's it! The setup wizard will guide you through configuration.

## 📋 **Usage**

### **Launch MUS1**
```bash
# GUI mode (recommended)
./dev-launch.sh gui

# CLI mode
./dev-launch.sh [command]
```

### **Common Commands**
```bash
# Projects
./dev-launch.sh project list
./dev-launch.sh project init "My Project"

# Data management
./dev-launch.sh add-subject <id>
./dev-launch.sh add-experiment <id> <subject_id>

# Configuration
./dev-launch.sh setup status
```

## 🏗️ **Architecture**

MUS1 uses clean architecture principles with clear separation of concerns:
- **Domain Models**: Pure business logic entities
- **Service Layer**: Business logic and validation
- **Repository Pattern**: Clean data access
- **SQLite Backend**: Relational database with constraints

## 🎯 **Core Features**

- **Project Management**: SQLite-backed projects with automatic setup
- **Subject & Experiment Tracking**: Full lifecycle management
- **Video Organization**: Hash-based integrity checking
- **Plugin System**: Extensible analysis capabilities
- **Lab Management**: Multi-lab research organization
- **Shared Storage**: Collaborative project support
- **Clean CLI**: Focused command-line interface
- **Setup Wizard**: Guided first-time configuration

## 📋 **Requirements**

- **Python**: 3.10 or higher
- **Operating System**: macOS, Linux, or Windows
- **Storage**: SQLite (built-in), optional shared storage
- **GUI**: PySide6 (automatically installed)

## 🔧 **Troubleshooting**

### **Common Issues**
- **GUI won't start**: Ensure you're in a graphical environment
- **Permission errors**: Check shared storage permissions
- **Setup issues**: Run `./dev-launch.sh setup user --force`

### **Getting Help**
```bash
./dev-launch.sh --help          # See all commands
./dev-launch.sh setup status    # Check configuration
```

## 📚 **Documentation**

- **[LAUNCH.md](LAUNCH.md)**: Detailed launch architecture and development guide
- **Setup Scripts**: `./setup.sh --help` for environment setup
- **CLI Commands**: `./dev-launch.sh --help` for available commands

## 📄 **License**

MUS1 is open source software for research purposes.
