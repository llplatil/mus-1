# MUS1: Mouse Behavior Analysis Tool

A Python-based tool designed to streamline the analysis of mouse behavior data.

## Overview

MUS1 takes the CSV tracking files and arena images from your DeepLabCut projects and makes it easy to:
1. Visualize mouse movement patterns
2. Organize experiments and subjects with metadata
3. Batch process multiple experiments using optimized settings
4. Apply consistent analysis across various experiment types

The project uses a modular architecture with plugin support for different experiment types and analysis methods.

## Features

- **Material Design UI**: Clean, modern interface built with PySide6-Qt
- **Responsive Layout**: BaseView implementation with QSplitter for consistent UI
- **Theme System**: Light/dark themes with OS detection and CSS variables
- **Flexible Project Structure**: Organize subjects, experiments, and batches
- **Plugin Architecture**: Support for multiple experiment types (NOR, OpenField, etc.)
- **Hierarchical Experiment Creation**: Step-by-step workflow for experiment setup
- **Batch Processing**: Group and analyze experiments together
- **Phase-Based Workflow**: Track experiments from planning through analysis
- **Observer Pattern**: UI components subscribe to state changes for automatic updates
- **Standardized Metadata Display**: Visualize complex relationships consistently
- **Reusable Components**: NotesBox and other UI patterns for consistent interfaces

## Architecture

MUS1 follows a modular architecture with clear separation of concerns:

### Core Components
- **ProjectManager**: Handles project-level operations, theme management, and plugin coordination
- **StateManager**: Maintains in-memory state and implements observer pattern
- **PluginManager**: Registers and manages experiment-specific plugins
- **DataManager**: Handles data validation and transformation

### UI Components
- **MainWindow**: Main application window with central theme management
- **BaseView**: Abstract base class for all views with standardized layout
- **NavigationPane**: Left-side navigation with consistent sizing and log display
- **Specialized Views**: ProjectView, SubjectView, ExperimentView for specific functions

## Current Status (v0.1.0)

MUS1 is under active development with the following functionality implemented:
- ✅ Core application structure with theming
- ✅ Project, subject, and experiment management
- ✅ Plugin architecture foundation
- ✅ Batch experiment system
- ✅ Experiment phase tracking
- ✅ Unified CSS variable system
- ✅ Proper theme handling architecture
- ✅ Consistent component styling

We're currently working on enhanced visualization and analysis capabilities. See our [Development Roadmap](Mus1_Refactor/refactor%20notes/ROADMAP.md) for details.

## Requirements
- Python 3.10+
- Processed DeepLabCut project files (tracking CSVs)
- Arena images from your experiments
- Dependencies (see requirements.txt):
  - PySide6
  - pydantic
  - pandas/numpy/matplotlib

## Documentation
- [Development Roadmap](Mus1_Refactor/refactor%20notes/ROADMAP.md)
- [Architecture Documentation](Mus1_Refactor/refactor%20notes/Architecture.md)

## Getting Started

1. Clone the repository into venv
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python -m Mus1_Refactor.main`

## Future Goals
- Advanced analysis visualizations
- Automated arena detection
- Statistical analysis tools
- Cross-experiment correlation
- Custom analysis pipeline creation



