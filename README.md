# MUS1: Video Analysis and Behavior Tracking System

MUS1 is a Python-based tool for organizing and analyzing animal behavior videos and tracking data. It provides a lab-centric workflow with persistent state management between CLI commands.

## Quick Start

### 1. Initial Setup

Configure your directories using the unified configuration system:
```bash
# Set up shared storage paths (now stored in SQLite database)
mus1 setup shared --path /Volumes/CuSSD3/mus1_media
mus1 setup labs --path /Volumes/CuSSD3/mus1_labs
mus1 setup projects --path /Volumes/CuSSD3/mus1_projects
```

The configuration is now stored in a centralized SQLite database with automatic migration from old YAML files.

### 2. Create Lab Configuration

```bash
# Create a lab configuration
mus1 lab create copperlab /Volumes/CuSSD3/mus1_labs

# Load the lab (this will persist for future commands)
mus1 lab load copperlab
```

### 3. Add Lab Resources

```bash
# Add compute workers
mus1 lab add-worker --name worker1 --ssh-alias server1

# Add credentials for remote access
mus1 lab add-credential --alias server1 --user researcher

# Check lab status
mus1 lab status
```

### 4. Create and Configure Project

```bash
# Create a project
mus1 project create myproject

# Associate project with lab
mus1 project associate-lab myproject copperlab
```

### 5. Discover and Import Videos

```bash
# Scan for video files
mus1 scan videos /path/to/videos > videos.jsonl

# Remove duplicates
mus1 scan dedup videos.jsonl > deduped.jsonl

# Import videos into project
mus1 project ingest myproject deduped.jsonl
```

### 6. Assign Videos to Subjects/Experiments

```bash
# Interactively assign unassigned videos
mus1 project media-assign myproject
```

## Core Features

### Lab Management
- Create lab configurations with shared resources
- Add workers, credentials, and scan targets
- Persistent state across CLI sessions

### Project Management
- Create projects for organizing experiments
- Associate projects with labs for resource inheritance
- Import videos and tracking data

### Video Discovery
- Scan directories for video files
- Deduplicate based on file hashes
- Stream JSON lines for processing

### Media Organization
- Automatic per-recording folder structure
- Metadata tracking for each video
- Subject and experiment assignment

## CLI Commands Reference

### Core Commands
```bash
mus1 status                    # Show system status and loaded lab/project
mus1 --version                 # Show version
mus1 clear-state               # Clear persistent CLI state
```

### Lab Management
```bash
mus1 lab create NAME PATH      # Create lab configuration
mus1 lab load NAME             # Load lab (persists between commands)
mus1 lab status                # Show lab details and resources
mus1 lab list                  # List available labs
mus1 lab add-worker --name NAME --ssh-alias ALIAS  # Add compute worker
```

### Project Management
```bash
mus1 project create NAME       # Create new project
mus1 project list              # List available projects
mus1 project associate-lab PROJ LAB  # Link project to lab
mus1 project ingest PROJ FILE  # Import videos from JSONL
mus1 project media-assign PROJ # Assign videos to subjects/experiments
```

### Video Discovery
```bash
mus1 scan videos [PATHS...]    # Discover videos, output JSONL
mus1 scan dedup FILE           # Remove duplicates, add metadata
```

## Architecture

MUS1 uses a modular architecture with:

- **ConfigManager**: Unified SQLite-based configuration system with hierarchical precedence
- **ConfigMigrationManager**: Automatic migration from old YAML/JSON configurations
- **StateManager**: Manages project state and metadata using ConfigManager for settings
- **PluginManager**: Handles plugin discovery and loading
- **ProjectManager**: Coordinates project operations with ConfigManager integration
- **LabManager**: Manages lab configurations and resources using ConfigManager
- **DataManager**: Handles file operations and hashing

### Key Improvements (2025)

- **Unified Configuration**: Single SQLite database replaces scattered YAML/JSON files
- **Hierarchical Settings**: Runtime > Project > Lab > User > Install precedence
- **Atomic Operations**: Configuration changes use proper transactions
- **Automatic Migration**: Seamless upgrade from old configuration system
- **Cleaner Code**: Reduced complexity by ~40% through elimination of fallback logic

## Persistent State

MUS1 maintains state between CLI commands through:
1. **In-memory cache** during a session
2. **Unified SQLite configuration database** for all settings
3. **Automatic migration** from old YAML/JSON configurations

Load a lab once with `mus1 lab load` and it stays active for subsequent commands. All configuration is now stored in a centralized, reliable SQLite database with proper atomic operations.

## Requirements

- Python 3.8+
- PySide6 (for GUI)
- typer, rich, tqdm (for CLI)
- pandas, numpy (for data processing)
- pyyaml (for configuration)

## Installation

```bash
pip install -e .
```

## Development

This is a development branch with active CLI improvements. Core functionality includes:
- **Unified Configuration System**: SQLite-based ConfigManager with hierarchical settings
- **Automatic Migration**: Seamless upgrade from old YAML/JSON configurations
- Lab and project management using ConfigManager
- Video discovery and deduplication
- Media organization and assignment
- Persistent state management with atomic operations

### Recent Major Refactoring (2025)

- **Configuration System Overhaul**: Replaced scattered YAML/JSON files with unified SQLite database
- **Hierarchical Configuration**: Runtime > Project > Lab > User > Install precedence
- **Atomic Operations**: All configuration changes use proper transactions
- **Code Simplification**: Reduced complexity by ~40% through elimination of fallback logic
- **Future-Ready Architecture**: Clean foundation for LLM-powered data import features
