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
pre fix: 
MainWindow 
    └── Contains tab instances of concrete views 
            (ProjectView, SubjectView, ExperimentView)
                └── Each inherits from BaseView (template pattern)
                        └── Each contains a NavigationPane instance 

┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│                             USER INTERFACE                                │
│                                                                           │
│   ┌───────────────┐                                     ┌───────────────┐ │
│   │               │                                     │               │ │
│   │  MainWindow   │◄────────────────────────────────►   │   Concrete    │ │
│   │               │     contains tabs of views          │    Views      │ │
│   └───────┬───────┘                                     └───────┬───────┘ │
│           │                                                     │         │
│           │                                                     │         │
│           │                                                     │ inherits│
│           ▼                                                     ▼         │
│  ┌─────────────────┐ Interacts with   ┌────────────────────────┐          │
│  │                 │                  │                        │          │
│  │ Project Manager ◄─────────────────►│ BaseView               │          │
│  │                 │                  │ (Template for views)   │          │
│  └────────┬────────┘                  └──────────┬────────────┘           │
│           │ Manages                              │ contains              │
│           │                                      │                       │
│           ▼                                      ▼                       │
│  ┌─────────────────┐                    ┌─────────────────────┐          │
│  │                 │                    │                     │          │
│  │  StateManager   │                    │ NavigationPane      │          │
│  │                 │                    │                     │          │
│  └─────────────────┘                    └─────────────────────┘          │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
so we need to fix this to something that alligns with: 

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  PluginManager  │───►│  StateManager   │◄───│   MainWindow    │
│                 │    │                 │    │                 │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         │                      │                      │
         ▼                      ▼                      ▼
    Collects plugin      Stores preferences     Coordinates theme
     preferences          & classes list          application
                                                      │
                                                      │
                                                      ▼
                                                ┌─────────────────┐
                                                │  Concrete Views │
                                                │  (e.g., ExpView)│
                                                └────────┬────────┘
                                                         │
                                                         │
                                                         ▼
                                                  Queries StateManager
                                                  for plugin styling
                                                  & applies to widgets

ie main window as coordinator of theme and specific styling mods when plugins say to do so

MainWindow
   │
   ├── ProjectView (inherits from BaseView)
   │        │
   │        └── NavigationPane
   │
   ├── SubjectView (inherits from BaseView)
   │        │
   │        └── NavigationPane
   │
   └── ExperimentView (inherits from BaseView)
            │
            └── NavigationPane
```

## UI Integration

### Observer Pattern
- UI components subscribe to `StateManager`
- UI updates triggered by state changes
- Classes register update callbacks on initialization
- Components unsubscribe when destroyed


### Theme Handling Architecture
- **MainWindow**: Central handler for theme changes
- **ProjectManager**: Applies theme to application through QPalette and CSS
- **BaseView**: Propagates theme to its components
- **ProjectView**: Contains only UI for theme selection, delegates logic to MainWindow


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

The plugin UI styling system leverages the existing architecture to provide consistent yet customizable styling:

see refactur UI for uptodate sketch

## Data Management

### Metadata Models
- Defined using Pydantic for consistent validation
- Includes models for MouseMetadata, ExperimentMetadata, PluginMetadata, etc.

### Sorting and Validation
- Centralized sorting logic in `sort_manager.py`
- coordinates with state manager

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
- Expands vertically when focused

## CSS System

### Variable Structure
- **Base variables**: Font, colors, spacing
- **Component variables**: Derived from base variables
- **Theme-specific variables**: Defined in :root and .dark-theme:root

### Theme Switching
- Uses CSS classes instead of separate files
- BaseView propagates theme to all children
- MainWindow is the central point for theme changes

## Current Status and Next Steps

### Completed
- ✅ Core application architecture implemented
- ✅ Observer pattern for UI updates
- ✅ Unified CSS variable system
- ✅ Proper theme handling architecture
- ✅ Navigation pane with fixed width

### Outstanding Tasks
- [ ] Delete legacy CSS files (dark.css, light.css)
- [ ] Fix text highlighting in input elements
- [ ] Implement consistent widget styling
- [ ] Complete component validation system
- [ ] Implement QPalette colors derived from CSS variables
- [ ] Implement plugin UI styling system

This document serves as a comprehensive reference for developers to understand the architecture and implementation details of MUS1.