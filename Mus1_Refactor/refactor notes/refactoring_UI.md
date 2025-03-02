# Mus1 UI Refactoring Plan

## Goals
- Implement a minimalist and reusable UI system using qt-material
- Ensure consistent theming across the entire application
- Standardize how metadata is displayed
- Create a system for plugin UI integration
- Reduce maintenance overhead through CSS class-based styling

### Base Theme Configuration
Create a file named `custom_dark_teal.xml` in your project root:

```xml
<!--?xml version="1.0" encoding="UTF-8"?-->
<resources>
  <color name="primaryColor">#009688</color>
  <color name="primaryLightColor">#52c7b8</color>
  <color name="secondaryColor">#232629</color>
  <color name="secondaryLightColor">#4f5b62</color>
  <color name="secondaryDarkColor">#31363b</color>
  <color name="primaryTextColor">#ffffff</color>
  <color name="secondaryTextColor">#ffffff</color>
</resources>
```

### Class-based CSS System
Create a file named `custom.css` with reusable CSS classes:

```css
/* Base styling */
QWidget {
  font-size: 12px;
  font-family: "Roboto";
}

/* Reusable class-based styling */
.mus1-nav-pane {
  background-color: {QTMATERIAL_SECONDARYDARKCOLOR};
  min-width: 180px;
  max-width: 180px;
}

.mus1-nav-list {
  background-color: {QTMATERIAL_SECONDARYDARKCOLOR};
  border: none;
}

.mus1-nav-list::item {
  padding: 8px;
  border-bottom: 1px solid {QTMATERIAL_SECONDARYLIGHTCOLOR};
  color: {QTMATERIAL_SECONDARYTEXTCOLOR};
}

.mus1-log-display {
  border: none;
  background-color: transparent;
  color: #cccccc;
  font-size: 11px;
  padding: 4px;
  max-height: 120px;
  min-height: 80px;
}

.mus1-primary-button {
  border-radius: 4px;
  padding: 8px 12px;
  background-color: {QTMATERIAL_PRIMARYCOLOR};
  color: {QTMATERIAL_PRIMARYTEXTCOLOR};
}

.mus1-secondary-button {
  border-radius: 4px;
  padding: 8px 12px;
  background-color: {QTMATERIAL_SECONDARYCOLOR};
  color: {QTMATERIAL_SECONDARYTEXTCOLOR};
}

.mus1-tab-pane {
  background-color: {QTMATERIAL_SECONDARYCOLOR};
}

.mus1-panel {
  background-color: {QTMATERIAL_SECONDARYCOLOR};
  border-radius: 4px;
  padding: 8px;
}

.mus1-data-view {
  background-color: {QTMATERIAL_SECONDARYDARKCOLOR};
  border: none;
}

.mus1-dialog {
  background-color: {QTMATERIAL_SECONDARYCOLOR};
  border-radius: 6px;
}

.mus1-text-input {
  border-radius: 4px;
  padding: 6px;
  background-color: {QTMATERIAL_SECONDARYDARKCOLOR};
}

.mus1-tree-view {
  background-color: {QTMATERIAL_SECONDARYCOLOR};
  alternate-background-color: {QTMATERIAL_SECONDARYDARKCOLOR};
  border: none;
}

.mus1-list-view {
  background-color: {QTMATERIAL_SECONDARYCOLOR};
  alternate-background-color: {QTMATERIAL_SECONDARYDARKCOLOR};
  border: none;
}

/* Plugin-specific styling */
.plugin-panel {
  border: 1px solid {QTMATERIAL_PRIMARYLIGHTCOLOR};
  background-color: {QTMATERIAL_SECONDARYCOLOR};
  border-radius: 4px;
  padding: 12px;
}
```

## 2. Theme Manager Implementation

Create a file named `theme_manager.py` in your project:

```python
import os
from PySide6 import QtWidgets
from qt_material import apply_stylesheet

class ThemeManager:
    """Manages application themes using qt-material with a minimalist approach."""
    
    @staticmethod
    def apply_theme(app, config=None):
        """Apply theme to application with custom configuration."""
        # Default theme and customizations
        theme_name = "dark_teal.xml"
        custom_css = "custom.css"
        
        # Theme variables
        extra = {
            # Font configuration
            'font_family': 'Roboto',
            'font_size': '12px',
            'line_height': '20px',
            
            # Density for compact UI
            'density_scale': '-1',
            
            # Button colors
            'danger': '#dc3545',
            'warning': '#ffc107',
            'success': '#17a2b8',
        }
        
        # Override with config if provided
        if config:
            if 'theme_name' in config:
                theme_name = config['theme_name']
            if 'extra' in config:
                extra.update(config['extra'])
        
        # Path to custom theme XML and CSS
        theme_path = os.path.join(os.path.dirname(__file__), theme_name)
        css_path = os.path.join(os.path.dirname(__file__), custom_css)
        
        # If custom theme doesn't exist, use the default dark_teal
        if not os.path.exists(theme_path):
            theme_path = theme_name
        
        # Apply the theme
        return apply_stylesheet(app, theme=theme_path, css_file=css_path, extra=extra)
```

## 3. UI Components Refactoring

### NavigationPane Refactoring - remove old style sheet then: 
Update `navigation_pane.py` to use class-based styling:

```python
# navigation_pane.py (refactored)
class NavigationPane(QWidget):
    """A consistent navigation pane using classes for styling."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Apply class-based styling
        self.setObjectName("navigationPane")
        self.setProperty("class", "mus1-nav-pane")
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Navigation list with class-based styling
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("navList")
        self.list_widget.setProperty("class", "mus1-nav-list")
        self.list_widget.setMaximumWidth(180)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.layout.addWidget(self.list_widget)
        self.list_widget.currentRowChanged.connect(self.button_clicked)
        
        # Spacer for consistent layout
        self.layout.addStretch()
        
        # Log display with class-based styling
        self.log_display = QTextEdit(self)
        self.log_display.setObjectName("logDisplay")
        self.log_display.setProperty("class", "mus1-log-display")
        self.log_display.setReadOnly(True)
        
        self.layout.addWidget(self.log_display)
        
        # Rest of implementation remains the same...

### ProjectSelectionDialog Refactoring
Update `project_selection_dialog.py` to use class-based styling:

```python
# Key changes in ProjectSelectionDialog.__init__:
self.setObjectName("projectSelectionDialog")
self.setProperty("class", "mus1-dialog")

left_frame = QFrame(self)
left_frame.setObjectName("newProjectPanel")
left_frame.setProperty("class", "mus1-panel")

self.new_project_line = QLineEdit(left_frame)
self.new_project_line.setObjectName("newProjectInput")
self.new_project_line.setProperty("class", "mus1-text-input")

self.new_button = QPushButton("Create New Project", left_frame)
self.new_button.setObjectName("createButton")
self.new_button.setProperty("class", "mus1-primary-button")
```

## 4. Standardized Metadata Display

Create a new file named `metadata_display.py` with reusable components:

```python
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

class MetadataTreeView(QTreeWidget):
    """Standardized tree view for hierarchical metadata display."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("metadataTree")
        self.setProperty("class", "mus1-tree-view")
        self.setHeaderHidden(False)
        self.setAlternatingRowColors(True)
        
    def populate_subjects_with_experiments(self, subjects_dict, experiments_dict):
        """Populate tree with subjects as parents and experiments as children."""
        self.clear()
        self.setHeaderLabels(["Subject ID", "Sex", "Experiments"])
        
        for subject_id, subject in subjects_dict.items():
            item = QTreeWidgetItem(self)
            item.setText(0, subject_id)
            item.setText(1, subject.sex.value if hasattr(subject.sex, 'value') else str(subject.sex))
            
            # Count experiments
            subject_experiments = [exp for exp_id, exp in experiments_dict.items() 
                                 if exp.subject_id == subject_id]
            item.setText(2, str(len(subject_experiments)))
            
            # Add experiment children
            for experiment in subject_experiments:
                exp_item = QTreeWidgetItem(item)
                exp_item.setText(0, experiment.id)
                exp_item.setText(1, "")
                exp_item.setText(2, experiment.type)
                
        self.expandAll()
        
    # Add more specialized display methods as needed
```

## 5. Plugin UI Integration

Create a new file named `plugin_ui_manager.py` to standardize plugin UI generation:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox, QLineEdit
from PySide6.QtCore import Qt

class PluginUIManager:
    """Manages UI components for plugins."""
    
    @staticmethod
    def create_plugin_form(plugin, parent=None):
        """Create a form widget based on plugin's field definitions."""
        form_widget = QWidget(parent)
        form_widget.setObjectName(f"{plugin.plugin_self_metadata().name}Form")
        form_widget.setProperty("class", "plugin-panel")
        
        layout = QFormLayout(form_widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Add plugin metadata and fields
        metadata = plugin.plugin_self_metadata()
        name_label = QLabel(f"<b>{metadata.name}</b> v{metadata.version}")
        layout.addRow("", name_label)
        
        # Add the rest of the form based on plugin requirements
        
        return form_widget
```

## 6. Main UI Layout Rules

### General Layout Principles
- **Consistent Structure**: Every view should maintain a three-panel layout structure
- **Left Panel**: Navigation and filtering (always present)
- **Central Panel**: List or tree view of data
- **Right Panel**: Details or editing form for selected item
- **Log Display**: Always at the bottom of the left panel

### Diagram of Standard UI Layout
Main widnow sets tabs: project, subjects, experiments, analysis
``` Individal tab: (controls its own pane) 
+---------------------+---------------------------+---------------------------+
|                     |                           |                           |
|  Navigation Panel   |    Data List/Tree View    |     Details/Edit Panel    |
|  (Fixed width)      |    (Flexible width)       |     (Fixed/Flex width)    |
|                     |                           |                           |
|                     |                           |                           |
|                     |                           |                           |
|                     |                           |                           |
|                     |                           |                           |
|                     |                           |                           |
|---------------------|                           |                           |
|                     |                           |                           |
|   Log Display       |                           |                           |
|                     |                           |                           |
+---------------------+---------------------------+---------------------------+
```

### Tab-Specific Layout
Each tab in the main window should follow this layout, but may have specialized content:
- **Project Tab**: Project metadata and summary statistics
- **Subject Tab**: List of subjects with experiment counts
- **Experiment Tab**: List or tree of experiments
- **Analysis Tab**: Analysis results and visualizations

## 7. Implementation Strategy

1. Create base files (`theme_manager.py`, `custom.css`, `custom_dark_teal.xml`)
2. Create reusable components (`metadata_display.py`, `plugin_ui_manager.py`)
3. Refactor existing components to use the class-based styling
4. Update main window to use the new components and layout rules
5. Test and refine the system

## 8. Plugin UI Considerations

Plugins will interface with the UI system through the `PluginUIManager`:

1. Plugins define required and optional fields through the BasePlugin interface
2. PluginUIManager creates appropriate input widgets based on field type
3. Plugins can provide custom visualization components if needed
4. All plugin UI elements will use consistent styling through CSS classes

<!-- Additional Considerations for Minimalistic and Scalable UI Components -->

## 9. Enhanced Reusable UI Components & Grid Displays

In addition to the reusable components defined in `metadata_display.py` and `plugin_ui_manager.py`, we plan to implement a minimalistic grid display for subjects and experiments. This grid display will:

- Use a minimal grid widget (e.g., QTableView or QTableWidget) to display metadata relationships for subjects and experiments.
- Feature a sorting function tab (or header controls) above the grid display to allow users to sort by various metadata fields (e.g., subject ID, date added, experiment type).
- Be designed to scale as the number of subjects or experiments grows, with lazy loading or pagination if necessary.

### Proposed Code Sketch for Grid Display:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

class MetadataGridDisplay(QWidget):
    """A minimalistic grid display for subjects/experiments with sorting capability."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Table to display metadata
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)  # Example: ID, Type/Extra, Date
        self.table.setHorizontalHeaderLabels(['ID', 'Type', 'Date'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.table)

    def populate_data(self, items, columns):
        """Populate table using a list of dicts where keys match the columns names."""
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, key in enumerate(columns):
                value = str(item.get(key, ''))
                self.table.setItem(row, col, QTableWidgetItem(value))
        # Enable sorting
        self.table.setSortingEnabled(True)
```

### Incorporating Batch UI in Experiment View

In `experiment_view.py`, we will also add a newly designed pane to handle batches. This pane will:

- Allow users to create, view, and manage batches.
- Be connected to the StateManager and ProjectManager, so that adding a new batch updates the underlying project state.

#### Code Adjustment Sketch in experiment_view.py:

```python
# ... existing imports ...
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLineEdit, QLabel

class BatchPane(QWidget):
    """UI pane for managing experiment batches."""
    def __init__(self, state_manager, project_manager, parent=None):
        super().__init__(parent)
        self.state_manager = state_manager
        self.project_manager = project_manager
        layout = QVBoxLayout(self)
        self.batch_input = QLineEdit(self)
        self.batch_input.setPlaceholderText('Enter batch name')
        self.add_button = QPushButton('Add Batch', self)
        self.add_button.clicked.connect(self.add_batch)
        self.status_label = QLabel('', self)
        layout.addWidget(self.batch_input)
        layout.addWidget(self.add_button)
        layout.addWidget(self.status_label)

    def add_batch(self):
        batch_name = self.batch_input.text().strip()
        if not batch_name:
            self.status_label.setText('Batch name cannot be empty.')
            return
        # Update state via ProjectManager (assume a method add_batch exists)
        try:
            self.project_manager.add_batch(batch_name)
            self.status_label.setText(f'Batch {batch_name} added successfully.')
            # Notify state manager to refresh observers
            self.state_manager.notify_observers()
        except Exception as e:
            self.status_label.setText(f'Error: {e}')
```

### Adjusting Reusable UI Element Definitions

Given the current definitions in core (subjects, experiments, plugins), we propose that reusable UI elements (such as input forms, editable grids, and list views) should derive their structure from these core metadata definitions. For example:

- A subject entry form should automatically generate input fields based on the `MouseMetadata` fields.
- An experiment grid should use the keys from `ExperimentMetadata` and Plugin input to define sortable columns.
- Plugin UI elements should be generated in a way that reflects the patern we have worked to develop for add experiment. we will need to add aditional experiment stages to @metadata.py and plugin definitions 

### Adjustments to Requirements

Update `requirements.txt` to include any additional packages needed for enhanced grid display and potential pagination/lazy loading (if, for instance, using additional modules):

```
PySide6>=6.2.0
pydantic>=1.9.0
pandas
numpy
matplotlib
PyYAML
# Optionally, a package for enhanced table features if needed, e.g.: 
# qtmodern
```

---

These adjustments aim to provide a more realistic and scalable approach to UI design while leveraging the existing core definitions. Future iterations may further refine these components to optimize performance and usability.