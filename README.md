# MUS1: Video Analysis System

A SQLite-based system for organizing and analyzing animal behavior videos with a clean architecture and lab-colony hierarchy.

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
mus1-gui

# Development
./dev-launch.sh gui
```

### CLI Mode
```bash
# Production
mus1 --help

# Development
./dev-launch.sh --help
```

## Usage Examples

### Project Management
```bash
# List projects
mus1 project list

# Create project
mus1 project init "My Project" --lab mylab

# Check status
mus1 project status
```

### Data Management
```bash
# Add subject
mus1 add-subject SUB001 --sex M --designation experimental

# Add experiment
mus1 add-experiment EXP001 SUB001 "Open Field Test" --date 2024-01-15

# List data
mus1 list-subjects
mus1 list-experiments
```

### Lab and Colony Management
```bash
# Create lab
mus1 lab create mylab "My Laboratory"

# Add colony
mus1 lab add-colony mylab colony1 "Treatment Group" --genotype "GENE:WT"

# List labs
mus1 lab list
```

## Requirements

- Python 3.10+
- macOS, Linux, or Windows
- PySide6 (installed automatically)

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
```bash
export MUS1_ROOT="/custom/path"
mus1-gui
```

## Documentation

- [docs/dev/ARCHITECTURE_CURRENT.md](docs/dev/ARCHITECTURE_CURRENT.md) - Architecture details
- [docs/dev/ROADMAP.md](docs/dev/ROADMAP.md) - Development roadmap
