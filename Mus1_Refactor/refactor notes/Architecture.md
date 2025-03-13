# MUS1 Architecture Overview

## Core Components

### ProjectManager
- Manages project-level operations (adding subjects/experiments, renaming projects)
- Handles theme detection and application
- Applies proper theme to QPalette and CSS
- Delegates validation and analysis to plugins
- Coordinates theme changes throughout the application

### StateManager
- Maintains in-memory `ProjectState`
- Implements observer pattern for UI updates
- Coordinates hierarchical experiment creation workflow
- Outputs sorted lists
- Notifies observers (UI components) when state changes

### PluginManager
- Registers and manages experiment-specific plugins
- Provides methods to retrieve plugins based on experiment type, processing stage, and data source
- Enables plugin discovery and registration
- Manages plugin metadata
- Aggregates plugin CSS for unified styling

### DataManager
- Handles data validation and transformation
- Manages metadata import/export (Excel, CSV)
- Coordinates data transformation between formats

## Component Architecture

```

```

## UI Integration

### Observer Pattern
- UI components subscribe to `StateManager`
- UI updates triggered by state changes
- Classes register update callbacks on initialization
- Components unsubscribe when destroyed

### Theme Handling Architecture
- Theme manager for QSS theme 
- **MainWindow**: Central handler for theme changes
- **ProjectManager**: Applies theme to application through QPalette and CSS
- **BaseView**: Propagates theme to its components
- **ProjectView**: Contains UI for theme selection, delegates logic to MainWindow

### Dynamic Form Generation
- ExperimentView dynamically generates forms based on plugin metadata
- Supports hierarchical selection (experiment type, processing stage, data source, plugins)

## Plugin Architecture

### Hierarchical Experiment Creation Workflow
1. Core experiment metadata (ID, Subject, Date, Type)
2. Processing stage selection
3. Data source selection (dependent on stage)
4. Plugin selection (based on previous choices)
5. Required fields collection (based on plugins)
6. Optional fields collection
7. Final validation and save

### Plugin UI Styling System
- Uses QSS variables and property-based styling
- Consistent design across plugins with theme support
- Each plugin can define custom styling preferences

## Data Management

### Metadata Models
- Defined using Pydantic for consistent validation
- Includes models for MouseMetadata, ExperimentMetadata, PluginMetadata, etc.

### Sorting and Validation
- Centralized sorting logic coordinated with state manager

## Batch Management System

### Experiment Grid Selection
- UI for batch creation with selectable experiment grid
- Tracks batch status and metadata

### Status Tracking
- Batch operations managed by ProjectManager and StateManager

## UI Component Patterns

### Widget Box Pattern
- Uses QGroupBox with standard styling
- Contains related UI elements

### Multi-Column Widget Pattern
- Side-by-side column layout within a widget box
- Used for comparison or selection interfaces

### Notes Widget Pattern
- Expandable text field for user notes
- Connects to state management system
- Expands vertically when focused this is still a to do 

## CSS System

### Variable Structure
- **Base variables**: Font, colors, spacing
- **Component variables**: Derived from base variables
- **Theme-specific variables**: Defined with variable substitution

### Theme Switching
- Uses CSS variables for theme definition in theme manager with qss stylesheet
- BaseView propagates theme to all children
- MainWindow is the central point for theme changes

## Current Status

### Completed
- ✅ Core application architecture implemented
- ✅ Observer pattern for UI updates
- ✅ Unified QSS variable system
- ✅ Proper theme handling architecture
- ✅ Navigation pane with fixed width


### Outstanding Tasks
- [ ] Complete component validation system
- [ ] Implement QPalette colors derived from CSS variables
- [ ] Complete plugin UI styling system implementation

This document serves as a comprehensive reference for developers to understand the architecture and implementation details of MUS1.