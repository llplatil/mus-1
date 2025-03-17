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

# Best Practices for Uniform UI Styling Using QSS and Centralized Layout Helpers

## 1. Use QSS for Sizing, Padding, and Spacing
- **Remove Explicit Sizing in Code**  
  Avoid using methods such as `setFixedHeight` or `setMinimumHeight` in your Python code (for buttons, labels, inputs, etc.). Let the QSS control sizes so that all styling comes from a single source.

- **Define Consistent Dimensions in QSS**  
  Specify widget dimensions (e.g., 24px height) and line-heights in your QSS for key classes:
  - `.mus1-primary-button`
  - `.mus1-secondary-button`
  - `.mus1-text-input`
  - `.mus1-combo-box`
  - `QLabel[formLabel="true"]`

## 2. Rely on Centralized Layout Helpers from BaseView
- **Use BaseView Methods for Layout**  
  Always create form sections, rows, and labels using BaseView’s helper methods:  
  - `create_form_section`
  - `create_form_row`
  - `create_form_label`
  
- **Ensure Consistency in Margins and Spacing**  
  These helper methods reference layout constants (such as `SECTION_SPACING`, `CONTROL_SPACING`, and `FORM_MARGIN`) so that all elements are uniformly spaced and aligned.
for LLMs: 
## 3. Standardize QSS Rules for Widgets
- **Label Styling**  
  For labels defined as `QLabel[formLabel="true"]`, explicitly set:
  - `min-height`, `height`, and `line-height` (e.g., all 24px)  
  This ensures consistency with buttons and input sizes.

- **Input and ComboBox Consistency**  
  Ensure that input fields and combo boxes have matching styling:
  - Padding: e.g., `padding: 4px 6px;`
  - Dimensions: e.g., `min-height: 24px;` and `height: 24px;`

- **Form Row Sizing**  
  Set `QHBoxLayout.form-row` to have a `min-height` (e.g., 24px) to correspond with widget sizes, preventing rows from expanding unexpectedly.

- **Button Uniformity**  
  Ensure that primary and secondary buttons use consistent padding, border-radius, and text alignment so they visually align with adjacent inputs and labels.

## 4. Remove Redundant or Conflicting Code
- **Avoid Duplicate Styling in Code**  
  Strip out any hard-coded alignment or sizing (like `setAlignment`, `setFixedHeight`, etc.) from your view code. Let the QSS and layout constants be the sole source for these properties.

- **Maintain a Single Source of Truth**  
  Rely solely on the stylesheet for properties like size, padding, and margins to avoid conflicts and ensure predictable rendering.

## 5. Load Your Stylesheet Last
- **Apply QSS After Widget Creation**  
  Ensure that the stylesheet is applied after all widgets are created so every element consistently picks up the standardized styles without being overridden by earlier settings.

## Benefits of Adopting These Best Practices
- **Centralized Adjustments**  
  Sizing and spacing are controlled centrally via QSS and BaseView’s layout constants, allowing for easy updates and consistent design changes.
  
- **Uniform Appearance Across Components**  
  Uniform helper functions and centralized styling guarantee that even complex layouts (with nested sections) maintain consistent margins and padding.
  
- **Elimination of Conflicting Code**  
  Removing redundant hard-coded styles avoids conflicts and ensures a predictable, uniform UI across the application.
  
- **Maintainability and Predictability**  
  By using these best practices, your UI remains uniform and maintainable, making future updates a single-point change rather than a large-scale refactor.

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