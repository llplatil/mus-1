# Mus1 UI Refactoring Plan - Implementation Status

# MUS1 Outstanding Tasks

This document provides a consolidated list of all outstanding tasks for the MUS1 project. It is organized by category and prioritized based on importance.

## UI Layout Responsibility Chain

The MUS1 UI layout system now follows a clear responsibility hierarchy:

1. **NavigationPane**: Single source of truth for navigation width
   - Defines `FIXED_WIDTH = 180` and other sizing constants
   - Responsible for its own internal layout only
   - Manages button stack sizing and log space allocation

2. **BaseView**: Manages overall layout structure
   - Coordinates the splitter with navigation pane and content area
   - Ensures proper splitter proportions during resize
   - Centralized place for layout updates via `resizeEvent`
   - All views (ProjectView, SubjectView, ExperimentView) inherit these behaviors

3. **MainWindow**: Handles high-level coordination
   - Manages tab switching without worrying about layout details
   - Focuses on application-level concerns
   - Delegates layout management to individual views

This hierarchy ensures consistent sizing across the application and prevents redundant layout recalculations.

## Priority 1: CSS and Theme System

- [ ] **Delete old CSS files**
  ```bash
  rm Mus1_Refactor/themes/dark.css
  rm Mus1_Refactor/themes/light.css
  ```

- [ ] **Check mus1.css filename**
  - If the file is still named unified_css_approach.css, rename it to mus1.css:
  ```bash
  mv Mus1_Refactor/themes/unified_css_approach.css Mus1_Refactor/themes/mus1.css
  ```

- [ ] **Fix text highlighting in input elements**
  ```css
  /* Fix text selection highlighting */
  QLineEdit::selection, QTextEdit::selection, QPlainTextEdit::selection {
    background-color: var(--selection-background);
    color: var(--selection-text-color);
  }

  /* Input label styling */
  .mus1-input-label {
    color: var(--text-color);
    font-weight: normal;
    background-color: transparent; /* No background highlight */
    padding: 2px 0;
  }
  ```

- [ ] **Implement QPalette color derivation from CSS variables**
  ```python
  def get_theme_colors(self):
      """Extract color values from CSS variables"""
      return {
          "--background-color": "#121212" if self.get_effective_theme() == "dark" else "#f0f0f0",
          "--text-color": "#ffffff" if self.get_effective_theme() == "dark" else "#000000",
          # ... other variables
      }
  
  def apply_theme(self, app):
      colors = self.get_theme_colors()
      palette = QPalette()
      palette.setColor(QPalette.Window, QColor(colors["--background-color"]))
      palette.setColor(QPalette.WindowText, QColor(colors["--text-color"]))
      # ... other palette colors
      app.setPalette(palette)
  ```

- [ ] **Thorough theme testing**
  - Test application startup
  - Test theme switching between light/dark
  - Test OS theme detection
  - Verify all components display correctly in both themes
  - Check theme propagation to all views and components

## Priority 2: UI Component Improvements

- [ ] **Implement component validation system**
  - Create a validation method in BaseView that checks for required components
  - Implement fallback behaviors for missing components
  - Add visual indicators for missing components in debug mode
  - Validation method skeleton:
  ```python
  def validate_components(self):
      """Validate that all required components exist and are properly configured."""
      missing_components = []
      
      # Check core components
      if not hasattr(self, 'navigation_pane'):
          missing_components.append('navigation_pane')
      
      # Check page-specific components based on view type
      if isinstance(self, ProjectView):
          if not hasattr(self, 'project_notes_edit'):
              missing_components.append('project_notes_edit')
              
      # Handle missing components
      if missing_components:
          self.log_bus.log(f"Missing components: {', '.join(missing_components)}", "warning", self.__class__.__name__)
          return False
      return True
  ```

- [ ] **Finalize body parts list functionality**
  - Implement save/cancel functionality for body parts changes
  - Add error handling for body parts operations
  - Complete integration with state management

- [ ] **Implement consistent widget styling**
  - Review all widgets for consistent class property application
  - Ensure all widgets use the appropriate mus1-* CSS classes
  - Add focus and hover styles for all interactive elements

## Priority 3: Plugin UI Integration

- [x] **Implement Plugin CSS Framework**
  - The original approach using `plugin_custom_style()` has been replaced with a more robust and standardized approach
  - Implemented a declarative styling system using the `get_styling_preferences()` method in BasePlugin
  - Added CSS classes in mus1.css that correspond to these standardized preferences
  - This approach ensures consistent styling across plugins while still allowing customization
  
  #### New Standardized Styling System:
  1. Plugins specify styling preferences through a structured dictionary:
  ```python
  def get_styling_preferences(self) -> dict:
      return {
          "colors": {
              "primary": "accent",  # Use the accent color
              "backgrounds": {
                  "analysis": "prominent",  # Make analysis sections stand out
              }
          },
          "borders": {
              "style": "rounded",  # Use rounded borders
          },
          "spacing": {
              "internal": "spacious",  # Use more padding
          }
      }
  ```
  
  2. The PluginManager collects these preferences and converts them to CSS classes
  3. The StateManager stores these preferences in the project state
  4. UI components can query the StateManager for styling information
  5. The CSS stylesheet includes standardized classes that implement these preferences

  This approach provides the following benefits:
  - Maintains UI consistency across the application
  - Gives plugins controlled customization options
  - Uses the same state flow pattern as other UI specifications
  - Prevents arbitrary CSS that could break the UI

- [x] **Extend PluginManager to Handle Styling**
  - Added methods to collect styling preferences from plugins
  - Implemented conversion of preferences to CSS classes
  - Added support for both direct CSS styles (legacy) and new preference-based styling

- [x] **Update ExperimentView Implementation**
  - Modified `update_plugin_fields()` to use the new styling system
  - Added code to query the StateManager for plugin-specific styling classes
  - Applied classes dynamically to plugin form elements
  - Created responsive input elements based on plugin field definitions

- [ ] **Complete experiment view workflow**
  - Implement remaining steps in hierarchical experiment creation
  - Add validation for experiment parameters
  - Complete plugin integration in experiment view

### Architectural Considerations

#### Handling Plugin Requirements vs. Styling

The current architecture has two parallel flows for plugin customization:

1. **Requirements & Validation Flow:**
   - Plugins define field requirements (`required_fields()`, `optional_fields()`)
   - Validation logic sits directly in plugins (`validate_experiment()`)
   - UI components query plugins directly for field requirements

2. **Styling Flow:**
   - Plugins define styling preferences (`get_styling_preferences()`)
   - PluginManager processes these preferences into CSS classes
   - StateManager stores processed styling info
   - UI components query StateManager for styling

**Analysis:**
- This separation allows requirements to be enforced directly (critical path) while styling passes through state (presentation layer)
- It reflects the different nature of these concerns: validation is essential functionality, styling is presentation

**Potential Solutions:**
1. **Keep As Is:**
   - The separation maintains proper concerns - validation logic should live with plugins, while styling can be managed via state
   - Benefit: Clean separation of concerns between functional requirements and presentation

2. **Unified Plugin Interface:**
   - Add a single `get_ui_configuration()` method to BasePlugin that returns both requirements and styling
   - StateManager could process and store this unified configuration
   - UI components would only need to query StateManager
   - Benefit: Single source of truth for all plugin UI information

3. **Mediator Pattern:**
   - Create a PluginUIMediator that handles coordination between plugins and UI components
   - This mediator would fetch both validation and styling information
   - Benefit: Encapsulated coordination logic, simplified UI code

**Recommendation:**
The current approach (option 1) is architecturally sound. While there are two parallel flows, they serve different purposes. Validation requirements are part of the core functionality and should remain directly accessible, while styling is a presentation concern that benefits from the coordination through StateManager.

## Priority 4: Documentation

- [ ] **Complete UI component guidelines**
  - Document all components and their usage patterns
  - Add guidelines for when to use each pattern
  - Include diagrams illustrating the component hierarchy
  - Add sizing and spacing guidelines

- [ ] **Document CSS variable system**
  - Create a comprehensive guide to the CSS variable hierarchy
  - Document the process for adding new CSS variables
  - Add examples of proper component styling

- [x] **Add plugin styling documentation**
  - Created a standardized plugin styling system based on preference dictionaries
  - Documented the transition from arbitrary CSS to controlled styling options
  - Added CSS classes in mus1.css that implement the standardized options
  - Created architecture documentation explaining the flow of styling information
  - Provided example implementation showing how to use the new system in ExperimentView

## Priority 5: Functional Improvements

- [ ] **Complete experiment view workflow**
  - Implement remaining steps in hierarchical experiment creation
  - Add validation for experiment parameters
  - Complete plugin integration in experiment view

- [ ] **Improve log file management**
  - Implement log rotation
  - Add log level filtering
  - Improve log message formatting

## Testing Tasks

- [ ] **Test theme switching thoroughly**
  - Test startup with each theme
  - Test switching between themes
  - Test OS theme detection
  - Verify appearance of all components

- [ ] **Test component validation**
  - Verify error handling for missing components
  - Test fallback behaviors
  - Check visual indicators in debug mode

- [ ] **Test UI component patterns**
  - Verify Widget Box pattern implementation
  - Test Multi-Column Widget pattern
  - Test Notes Widget expand/collapse behavior

- [ ] **Test plugin UI styling**
  - Verify field status indicators work correctly
  - Test plugin-specific CSS application
  - Check for styling conflicts between plugins

## Implementation Checklist

1. Delete old CSS files and verify mus1.css is correctly named
2. Implement text highlighting fix in CSS
3. Create QPalette color derivation method
4. Implement component validation system
5. Complete remaining UI component improvements
6. Create documentation for developers
7. Test thoroughly across all views and components

## ✅ Completed Tasks

### 1. Theme System Implementation

- ✅ Created unified CSS approach with variables in `mus1.css`
- ✅ Implemented proper CSS organization with section comments
- ✅ Enhanced `ProjectManager.detect_os_theme()` with robust platform-specific detection
  - macOS: Uses `defaults read` via subprocess
  - Windows: Registry query via winreg
  - Linux: GTK/GNOME theme detection
  - Fallback: Qt palette-based detection
- ✅ Improved `ProjectManager.apply_theme()` to use unified CSS file
- ✅ Added detailed docstrings to all theme-related methods
- ✅ Refactored theme handling architecture with MainWindow as central handler

### 2. Standardized Component Architecture

- ✅ Implemented `BaseView` class that standardizes the UI layout structure
  - Manages the QSplitter with proper configuration
  - Handles navigation pane and content area setup
  - Provides consistent page management methods
- ✅ Refactored `NavigationPane` with a fixed width of 180px
  - Added scrollable button container for better space management
  - Implemented consistent log display at the bottom
  - Added theme update capability
- ✅ Converted all main views to inherit from `BaseView`:
  - `ProjectView`
  - `SubjectView`
  - `ExperimentView`

### 3. UI Component Implementation

- ✅ Implemented project notes widget with expand/collapse behavior
  ```python
  # In ProjectView.setup_current_project_page:
  
  # Create notes box
  self.project_notes_group = QGroupBox("Project Notes")
  self.project_notes_group.setObjectName("projectNotesGroup")
  self.project_notes_group.setProperty("class", "mus1-input-group")
  
  notes_layout = QVBoxLayout(self.project_notes_group)
  
  # Create the notes edit widget with expanding behavior
  self.project_notes_edit = QTextEdit()
  self.project_notes_edit.setObjectName("projectNotesEdit")
  self.project_notes_edit.setProperty("class", "mus1-notes-edit")
  self.project_notes_edit.setPlaceholderText("Enter project notes here...")
  
  # Define minimum heights and focus events for expand/contract behavior
  self.project_notes_edit.setMinimumHeight(80)
  
  # Store original focus event handlers
  original_focus_in = self.project_notes_edit.focusInEvent
  original_focus_out = self.project_notes_edit.focusOutEvent
  
  # Override focus events to handle height changes
  def expand_on_focus(event):
      self.project_notes_edit.setMinimumHeight(150)
      if original_focus_in:
          original_focus_in(event)
  
  def contract_on_focus_lost(event):
      self.project_notes_edit.setMinimumHeight(80)
      if original_focus_out:
          original_focus_out(event)
  
  self.project_notes_edit.focusInEvent = expand_on_focus
  self.project_notes_edit.focusOutEvent = contract_on_focus_lost
  
  notes_layout.addWidget(self.project_notes_edit)
  
  # Add to current project layout after the frame rate group
  current_project_layout.addWidget(self.project_notes_group)
  ```

- ✅ Refactored Body Parts page to use Multi-Column Widget Pattern
  ```python
  # In ProjectView.setup_body_parts_page:
  
  # Create a "Manage Body Parts" widget using the Multi-Column Widget Pattern
  self.manage_body_parts_group = QGroupBox("Manage Body Parts")
  self.manage_body_parts_group.setProperty("class", "mus1-input-group")
  manage_body_parts_layout = QVBoxLayout(self.manage_body_parts_group)
  
  # Create horizontal layout for two columns
  body_parts_columns_layout = QHBoxLayout()
  
  # First column: All body parts
  all_body_parts_group = QGroupBox("All Body Parts")
  all_body_parts_layout = QVBoxLayout(all_body_parts_group)
  self.all_body_parts_list = QListWidget()
  self.all_body_parts_list.setSelectionMode(QAbstractItemView.MultiSelection)
  self.all_body_parts_list.setProperty("class", "mus1-list-widget")
  all_body_parts_layout.addWidget(self.all_body_parts_list)
  
  # Add to active button
  add_to_active_button = QPushButton("Add to Active →")
  add_to_active_button.setProperty("class", "mus1-secondary-button")
  add_to_active_button.clicked.connect(self.handle_add_to_active_body_parts)
  all_body_parts_layout.addWidget(add_to_active_button)
  
  # Second column: Active body parts
  active_body_parts_group = QGroupBox("Active Body Parts")
  active_body_parts_layout = QVBoxLayout(active_body_parts_group)
  self.current_body_parts_list = QListWidget()
  self.current_body_parts_list.setSelectionMode(QAbstractItemView.MultiSelection)
  self.current_body_parts_list.setProperty("class", "mus1-list-widget")
  active_body_parts_layout.addWidget(self.current_body_parts_list)
  
  # Remove button
  remove_button = QPushButton("← Remove from Active")
  remove_button.setProperty("class", "mus1-secondary-button")
  remove_button.clicked.connect(self.handle_remove_body_part)
  active_body_parts_layout.addWidget(remove_button)
  
  # Add columns to layout
  body_parts_columns_layout.addWidget(all_body_parts_group)
  body_parts_columns_layout.addWidget(active_body_parts_group)
  
  # Add columns layout to the manage body parts group
  manage_body_parts_layout.addLayout(body_parts_columns_layout)
  
  # Add manage body parts group to page ABOVE the bodypart_io_group
  body_parts_layout.insertWidget(0, self.manage_body_parts_group)
  ```

- ✅ Fixed "Current Project" display positioning
  - Moved to the Current Project page (under the "Current Project" navigation button)
  - Added proper styling with `.mus1-project-selector` class
  - Created `.mus1-section-label` class for better visibility

### 4. Navigation Pane Layout Improvements

- ✅ Fixed button spacing issues with single source of truth for sizing
  - Added dedicated constants for all sizing parameters (BUTTON_HEIGHT, SPACING, etc.)
  - Removed conflicting CSS sizing properties
  - Implemented precise button stack height calculation
- ✅ Simplified widget hierarchy for better performance and reliability
  - Removed unnecessary QScrollArea for buttons (which caused scrolling issues)
  - Used direct QWidget → QVBoxLayout → buttons structure
- ✅ Improved log display area with better space allocation
  - Added a dedicated log container with label and display
  - Implemented precise calculations for available log space
  - Enhanced resize handling for proper space distribution
- ✅ Created consistent CSS styling for log components
  - Added .mus1-log-container, .mus1-log-label, .mus1-log-display classes
  - Reduced padding and margins for better spacing
  - Applied consistent styling across themes

### 5. Theme Handling Architecture

- ✅ Refactored theme handling with proper architecture:
  - **MainWindow**: Contains central theme change logic
  - **ProjectManager**: Applies theme to application
  - **BaseView**: Propagates theme to components
  - **ProjectView**: Maintains UI for theme selection only
- ✅ Added MainWindow.change_theme() as central theme handler:
  ```python
  def change_theme(self, theme_choice):
      """
      Central handler for theme changes throughout the application.
      Called when user selects a theme from the menu or the ProjectView settings.
      
      Args:
          theme_choice: 'light', 'dark', or 'os'
      """
      # If 'os' is selected, detect the OS theme
      if theme_choice == "os":
          theme_choice = self.project_manager.detect_os_theme()
          
      # Update theme in settings
      self.project_manager.update_theme(theme_choice)
      
      # Apply theme to application
      app = QApplication.instance()
      self.project_manager.apply_theme(app)
      
      # Notify all views to update their theme
      self.propagate_theme_to_views(theme_choice)
  ```
- ✅ Updated ProjectView.handle_change_theme() to delegate to MainWindow:
  ```python
  def handle_change_theme(self, theme_choice: str):
      """
      UI handler for theme change requests, delegates actual change to MainWindow.
      Keeps the UI in ProjectView but moves the logic to MainWindow.
      
      Args:
          theme_choice: 'dark', 'light', or 'os'
      """
      # Log the requested change
      self.navigation_pane.add_log_message(f"Changing theme to {theme_choice}...", 'info')
      
      # Delegate the actual theme change to the MainWindow
      main_window = self.window()
      if main_window:
          # The MainWindow will handle all aspects of theme changing
          main_window.change_theme(theme_choice)
  ```

## UI Component Pattern Guide

The MUS1 UI follows these standard component patterns:

### Widget Box Pattern
- Uses QGroupBox with standard styling
- Contains related UI elements
- Example: Input groups, settings panels

### Multi-Column Widget Pattern
- Side-by-side column layout within a widget box
- Used for comparison or selection interfaces
- Example: Manage Objects panel, Body Parts list

### Notes Widget Pattern
- Expandable text field for user notes
- Connects to state management system
- Expands vertically when focused

## Navigation Pane Design - Key Principles

The NavigationPane component follows these key design principles:

1. **Simplified Widget Hierarchy**
   ```
   NavigationPane → QVBoxLayout → button_container → button_container_layout → buttons
   ```

2. **Single Source of Truth for Sizing**
   All size parameters are defined as class constants:
   ```python
   BUTTON_HEIGHT = 32          # Core button height without padding/margin
   BUTTON_SPACING = 2          # Space between buttons
   FIXED_WIDTH = 180           # Fixed width per UI guidelines
   MIN_LOG_HEIGHT = 100        # Minimum height for log display
   LOG_LABEL_HEIGHT = 20       # Height for log label
   LAYOUT_MARGINS = 10         # Layout margin size
   LAYOUT_SPACING = 6          # Spacing between widgets
   ```

3. **Dynamic Log Space Allocation**
   Log display gets all remaining space after button stack:
   ```python
   available_for_log = nav_height - button_stack_height - self.LOG_LABEL_HEIGHT - 
                      (self.LAYOUT_MARGINS * 2) - (self.LAYOUT_SPACING * 2)
   ```

4. **Tab-Specific Button Configuration**
   Each tab configures its own navigation buttons:
   ```python
   self.setup_navigation([
       "Current Project", 
       "General Settings", 
       "Body Parts", 
       "Objects"
   ])
   ```

   # MUS1 UI Refactoring - Consolidated Notes

## Completed Tasks

✅ **Theme System Implementation**
- Created CSS variables system in a unified CSS file
- Updated theme switching to use class-based approach
- Properly organized CSS with section comments
- Created a comprehensive CSS variable mapping

✅ **Standardized Component Architecture**
- Implemented BaseView for consistent layout structure
- Refactored NavigationPane with proper sizing
- Converted all views to inherit from BaseView

✅ **Fixed UI Components**
- Added project notes widget with expand/collapse behavior
- Implemented body parts display using multi-column pattern
- Fixed layout issues in various components

✅ **Architecture Improvements**
- Fixed theme handling architecture
  - MainWindow - Central theme change logic
  - ProjectView - Theme selection UI only
  - BaseView - Theme propagation to components
- Implemented proper observer pattern for state changes

## Remaining Tasks

### Priority 1: Core UI Functionality
- [ ] Implement the component validation system
- [ ] Complete body parts list functionality
- [ ] Fix text highlighting in input elements
- [ ] Implement consistent widget styling across views

### Priority 2: CSS Cleanup
- [ ] Delete old CSS files (dark.css, light.css)
- [ ] Rename unified CSS file to mus1.css
- [ ] Test thoroughly across the application

### Priority 3: Documentation
- [ ] Create developer guide for UI patterns
- [ ] Add diagrams and decision trees for component selection
- [ ] Document the CSS variable system

## UI Component Patterns

The MUS1 UI follows these standard component patterns:

  MainWindow.change_theme()
     │
     ▼
   ProjectManager.update_theme() → Updates in-memory preference
     │
     ▼
   ProjectManager.apply_theme() → Loads CSS file and applies to QApplication
     │
     ▼
   QApplication.setStyleSheet() → Applies the unified CSS file
     │
     ▼
   MainWindow.propagate_theme_to_views() → Sets theme property on views

### Widget Box Pattern
- Uses QGroupBox with standard styling
- Contains related UI elements
- Example: Input groups, settings panels

### Multi-Column Widget Pattern
- Side-by-side column layout within a widget box
- Used for comparison or selection interfaces
- Example: Manage Objects panel, Body Parts list

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

### Benefits
- Single source of truth for all styles
- Easier maintenance and consistency
- More efficient theme switching

## Architecture Updates

### Theme Handling Architecture
- **MainWindow**: Central handler for theme changes
- **ProjectManager**: Applies theme to application
- **BaseView**: Propagates theme to its components
- **ProjectView**: Contains only UI for theme selection

### Observer Pattern
- StateManager is observed by views
- Views subscribe to state changes
- Changes to state trigger UI updates

### QPalette Coloring in ProjectManager
ProjectManager.py sets QPalette colors explicitly for a specific reason:

1. **Native Qt Widget Compatibility**
   - Some native Qt widgets don't fully respect CSS styling
   - The QPalette provides a fallback styling mechanism for these widgets
   - This ensures a consistent base level of theming regardless of CSS support

2. **Current Implementation**
   - Currently, these colors are hardcoded in ProjectManager.apply_theme()
   - This creates duplicate color definitions (in both QPalette and CSS)
   - There's no single source of truth for these colors

3. **Future Improvement**
   - Ideally, QPalette colors should be derived from the same CSS variables
   - This would maintain a single source of truth for all colors
   - Implementation would require a mapping system between CSS variables and QPalette roles

```python
# Example of future implementation using shared colors
def apply_theme(self, app):
    # Get the same colors used in CSS
    colors = self.get_theme_colors()
    
    # Apply to QPalette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors["--background-color"]))
    palette.setColor(QPalette.WindowText, QColor(colors["--text-color"]))
    # ...etc
    
    app.setPalette(palette)
```

## Files That Can Be Deleted

The following files can now be safely deleted:

1. **CSS Files**:
   - `dark.css` - Replaced by unified CSS approach
   - `light.css` - Replaced by unified CSS approach

2. **Refactor Notes**:
   - `css_migration_plan.md` - Content merged into refactoring_UI.md
   - `delete_css_files.md` - Steps merged into refactoring_UI.md

# Updated Implementation Status

## Recent Changes (March 2025)

### 1. Theme System Implementation Improvements
- ✅ Streamlined the theme handling architecture 
- ✅ Created a centralized `apply_theme_to_application()` method in ProjectManager
- ✅ Fixed theme application timing to ensure components are fully initialized
- ✅ Improved theme propagation to views

### 2. Plugin Styling System Enhancements
- ✅ Implemented enhanced plugin field creation in ExperimentView
- ✅ Added support for dynamic widget types based on field requirements
- ✅ Integrated styling preferences with field widgets
- ✅ Created visual indicators for required/optional fields

### 3. Component Validation System
- ✅ Implemented component validation system in BaseView
- ✅ Added validation for required components and methods
- ✅ Improved error handling and logging for missing components
- ✅ Applied validation in ProjectView as proof of concept

### 4. Bug Fixes
- ✅ Fixed method name mismatch in ProjectView initialization
- ✅ Added missing `current_project_label` component
- ✅ Implemented missing update methods in ProjectView
- ✅ Fixed theme application timing issues
- ✅ Added error handling for initialization issues

## Remaining Tasks

### Priority 1: CSS and Theme System
- [ ] **Delete old CSS files**
  - Old CSS files have been moved to the outdated folder
  - Verify no remaining references to these files in the codebase

- [ ] **Implement QPalette color derivation from CSS variables**
  ```python
  def get_theme_colors(self):
      """Extract color values from CSS variables"""
      return {
          "--background-color": "#121212" if self.get_effective_theme() == "dark" else "#f0f0f0",
          "--text-color": "#ffffff" if self.get_effective_theme() == "dark" else "#000000",
          # ... other variables
      }
  
  def apply_theme(self, app):
      colors = self.get_theme_colors()
      palette = QPalette()
      palette.setColor(QPalette.Window, QColor(colors["--background-color"]))
      palette.setColor(QPalette.WindowText, QColor(colors["--text-color"]))
      # ... other palette colors
      app.setPalette(palette)
  ```

### Priority 2: UI Component Improvements
- [x] **Implement component validation system**
  - ✅ Created a validation method in BaseView that checks for required components
  - ✅ Added error handling for missing components and methods
  - ✅ Implemented informative logging for missing components

### Priority 3: Documentation
- [ ] **Complete UI component guidelines**
  - Update with the new plugin styling examples
  - Add documentation on component validation system
  - Add documentation on the update methods pattern

## Component Validation System

The newly implemented Component Validation System provides several benefits:

1. **Early Detection**: Missing components and methods are detected at initialization time
2. **Better Debugging**: Clear logs indicate what's missing and where
3. **Graceful Degradation**: The application can continue running with appropriate error handling
4. **Self-Documenting Code**: Required components and methods are explicitly listed

Example usage:

```python
# Define required components and methods
required_components = ['navigation_pane', 'project_notes_edit', 'current_project_label']
required_methods = ['refresh_lists', 'update_ui_from_state']

# Validate components and methods
self.validate_components(required_components, required_methods)

# Use try-except for graceful degradation
try:
    self.update_ui_from_state()
except Exception as e:
    self.navigation_pane.add_log_message(f"Error updating UI: {str(e)}", "error")
```

This system helps prevent cryptic errors and provides better feedback during development.
