# MUS1 Architecture Overview

## Core Components

### ProjectManager
- Manages project-level operations (adding subjects/experiments, renaming projects, and handling file operations).
- Handles theme detection, application, and dynamic QSS integration for consistent UI styling.
- Delegates validation and analysis to plugins.
- Coordinates project data persistence using JSON serialization with `pydantic_encoder`.
- Consistently converts and updates metadata objects (for subjects, body parts, and tracked objects) to maintain type integrity.

### StateManager
- Maintains the in-memory `ProjectState` and implements the observer pattern for responsive UI updates.
- Coordinates the hierarchical experiment creation workflow.
- Provides unified sorting logic that outputs sorted lists for both master and active entities (body parts and objects) based on a global sort setting.
- Notifies observers (UI components) whenever the state changes.

### PluginManager
- Registers and manages experiment-specific plugins.
- Provides methods to retrieve plugins based on experiment type, processing stage, and data source.
- Facilitates dynamic plugin discovery and registration.
- Aggregates plugin metadata and CSS to ensure unified styling throughout the application.

### DataManager
- Handles data validation, transformation, and import/export operations (Excel, CSV, YAML).
- Supports extraction of body parts from DLC config files and CSV files.
- Coordinates data transformations—such as frame rate and threshold resolution—to integrate seamlessly with project metadata updates.

## Component Architecture

```

```

## UI Integration

### Observer Pattern
- UI components subscribe to `StateManager` to receive updates.
- Updates propagate automatically to ensure synchronized, reactive interfaces.
- Components register callbacks on initialization and unsubscribe on destruction to avoid memory leaks.

### Theme Handling Architecture
- Themes are managed via a centralized QSS system that enforces consistent widget sizing, padding, and spacing.
- **MainWindow** is the central handler for theme changes.
- **ProjectManager** applies themes by updating QPalette and injecting CSS.
- **BaseView** propagates theme settings and all centralized layout helpers (e.g., `create_form_section`, `create_form_row`, `create_form_label`) to its child components.
- **ProjectView** offers UI for theme selection and delegates logic to MainWindow.

## Best Practices for Uniform UI Styling Using QSS and Centralized Layout Helpers

### 1. Use QSS for Sizing, Padding, and Spacing
- **Remove Explicit Sizing in Code**  
  Avoid hard-coded widget dimensions (e.g., `setFixedHeight`, `setMinimumHeight`). Instead, define these in QSS.
- **Define Consistent Dimensions in QSS**  
  Specify widget dimensions (e.g., 24px height) and line-heights in QSS for key classes:
  - `.mus1-primary-button`
  - `.mus1-secondary-button`
  - `.mus1-text-input`
  - `.mus1-combo-box`
  - `QLabel[formLabel="true"]`

### 2. Rely on Centralized Layout Helpers from BaseView
- **Use BaseView Methods for Layout**  
  Utilize helper methods such as `create_form_section`, `create_form_row`, and `create_form_label` to standardize layouts.
- **Ensure Consistency in Margins and Spacing**  
  These helper methods use layout constants (e.g., `SECTION_SPACING`, `CONTROL_SPACING`, `FORM_MARGIN`) to ensure uniform appearance.

### 3. Standardize QSS Rules for Widgets
- **Label Styling**  
  For `QLabel[formLabel="true"]`, define consistent `min-height`, `height`, and `line-height` (e.g., 24px).
- **Input and ComboBox Consistency**  
  Ensure inputs and combo boxes share matching padding and dimensions.
- **Form Row Sizing**  
  Use QSS to enforce uniform minimum heights for form rows.
- **Button Uniformity**  
  Primary and secondary buttons should use consistent padding, border-radius, and alignment to align with accompanying inputs and labels.

### 4. Remove Redundant or Conflicting Code
- **Avoid Duplicate Styling in Code**  
  Remove hard-coded styling (e.g., `setFixedHeight`, `setAlignment`) in favor of centralized QSS definitions.
- **Maintain a Single Source of Truth**  
  Rely exclusively on the stylesheet for size, padding, and margin definitions to prevent conflicts.

### 5. Load Your Stylesheet Last
- **Apply QSS After Widget Creation**  
  Ensure the stylesheet is applied after all UI components are created so every element fully picks up the standardized styles.

## Benefits of Adopting These Best Practices
- **Centralized Adjustments**  
  Central control over sizing and spacing simplifies design updates and ensures consistency.
- **Uniform Appearance Across Components**  
  Standardized helper functions and QSS guarantees that even complex layouts maintain uniform margins and padding.
- **Elimination of Conflicting Code**  
  Removing redundant hard-coded styles eliminates conflicts and ensures reliable, predictable UI rendering.
- **Maintainability and Predictability**  
  A centralized styling approach allows for single-point updates, easing future maintenance efforts.

### Dynamic Form Generation
- ExperimentView dynamically generates forms based on plugin metadata.
- Supports hierarchical selection (experiment type, processing stage, data source, and plugins).

## Plugin Architecture

### Hierarchical Experiment Creation Workflow
1. Core experiment metadata (ID, Subject, Date, Type)
2. Processing stage selection
3. Data source selection (dependent on stage)
4. Plugin selection based on earlier choices
5. Collection of required fields (as specified by the plugins)
6. Optional field collection and final validation
7. Experiment creation and data persistence

### Plugin UI Styling System
- Utilizes QSS variables and property-based styling for a consistent design.
- Supports theme switching with unified styling across all plugin interfaces.
- Each plugin can define custom styling preferences that are aggregated by the PluginManager.

## Data Management

### Metadata Models
- Defined using Pydantic for robust, consistent validation.
- Models include MouseMetadata, ExperimentMetadata, PluginMetadata, BodyPartMetadata, ObjectMetadata, etc.

### Sorting and Validation
- Centralized sorting logic in StateManager now returns sorted dictionaries for both master and active lists.
- Sorting is based on the global sort mode and applies consistently to both body parts and objects.
- DataManager integrates file validation and data extraction (e.g., extracting body parts from DLC configs and CSVs) with these uniform update methods.

## Batch Management System

### Experiment Grid Selection
- Provides a UI for batch creation with selectable experiment grids.
- Updated dynamically via the observer pattern in StateManager.

### Status Tracking
- Batch operations, including creation, deletion, and updates, are uniformly managed by ProjectManager and StateManager.
- The observer pattern ensures that any state change automatically triggers UI refreshes.

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

### Recent Updates from last Composer Session

- **Persistent UI-to-State Synchronization:**
  - Updated the handling of project notes in the UI (NotesBox) so that changes are explicitly committed to the project state (`state.settings["project_notes"]`) and persisted via a call to `save_project()`. This ensures that notes persist across project switches and application reloads.

- **State Serialization Enhancements:**
  - Modified `ProjectManager.save_project` to use `pydantic_encoder` for JSON serialization, preserving non-native types (e.g., sets) and ensuring the state is correctly reconstructed on reload.

- **Type Consistency for Object Metadata:**
  - Identified that objects added via `add_tracked_object` were stored as plain strings, causing a type mismatch in the UI (which expects objects with a `.name` attribute). Future improvements should either store objects as proper metadata objects or adjust the key function to handle strings appropriately.

- **Decoupling Business Logic and UI:**
  - Reinforced the design where UI components focus solely on data presentation and user input, while business logic such as duplicate checking, file validations, and state updates is delegated to core modules like `ProjectManager`, `StateManager`, and `DataManager`.

- **Enhanced Observer Pattern Usage:**
  - Ensured that state updates via the observer pattern trigger consistent UI refreshes. This reinforces that any changes to the underlying state are properly reflected across all subscribed UI components.

**Next Steps:**
  - Verify that objects added to the tracked objects list are correctly converted to or stored as full metadata objects.
  - Review and ensure consistent UI-to-state synchronization for other components (e.g., subject list updates), and refine conversion routines as needed.

End of file