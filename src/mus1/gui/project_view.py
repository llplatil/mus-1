from .qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QFileDialog, QMessageBox, Qt, QProgressBar, QTextEdit, QSlider, QCheckBox
)
from .qt import Signal
from pathlib import Path
from .base_view import BaseView
from typing import Dict, Any
from ..core.scanners.remote import collect_from_targets
from .gui_services import GUIProjectService


class NotesBox(QGroupBox):
    """A reusable notes component that can be added to any view."""
    def __init__(self, parent=None, title="Notes", placeholder_text="Enter notes here..."):
        super().__init__(title, parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 15, 10, 10)
        self.layout.setSpacing(8)
        
        # Set up the QTextEdit for notes
        self.notes_edit = QTextEdit(self)
        self.notes_edit.setPlaceholderText(placeholder_text)
        self.notes_edit.setProperty("class", "mus1-notes-edit")
        self.layout.addWidget(self.notes_edit)
        
        # Add a save button
        self.save_button = QPushButton("Save", self)
        self.save_button.setProperty("class", "mus1-primary-button")
        
        # Button row layout - no specific margins set here
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.save_button)
        
        self.layout.addLayout(button_layout)
        
        # Find base_view for accessing log functionality
        self.base_view = self.find_base_view_parent(parent)
    
    def find_base_view_parent(self, parent):
        """Find the closest BaseView parent to access layout constants."""
        current = parent
        while current:
            if hasattr(current, 'FORM_MARGIN') and hasattr(current, 'CONTROL_SPACING'):
                return current
            if hasattr(current, 'parent'):
                current = current.parent()
            else:
                break
        return None
    
    def set_text(self, text):
        """Set the content of the notes editor."""
        self.notes_edit.setPlainText(text)
    
    def get_text(self):
        """Get the content of the notes editor."""
        return self.notes_edit.toPlainText()
    
    def connect_save_button(self, callback):
        """Connect the save button to a callback function."""
        self.save_button.clicked.connect(callback)


class ProjectView(BaseView):
    project_renamed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, view_name="project")
        # Initialize GUI services
        self.gui_services = None  # Will be set when project is loaded
        self.project_service = None  # Will be set when project is loaded
        self.importer_param_widgets: Dict[str, QWidget] = {} # Initialize the dictionary here
        self.setup_navigation(["Import Project", "Project Settings", "General Settings"])
        self.setup_import_project_page()
        self.setup_project_settings_page()
        self.setup_general_settings_page()
        self.setup_scan_ingest_page()
        self.setup_targets_page()
        # Add navigation buttons for newly added pages to keep nav and pages aligned
        self.add_navigation_button("Scan & Ingest")
        self.add_navigation_button("Targets")
        self.change_page(0)

    # --- Lifecycle hooks ---
    def on_services_ready(self, services):
        super().on_services_ready(services)
        self.gui_services = services
        self.project_service = services

    def format_item(self, item):
        """Utility to return the proper display string for an item."""
        return item.name if hasattr(item, "name") else str(item)

    def setup_import_project_page(self):
        """Setup the page for importing data from external projects."""
        self.import_project_page = QWidget()
        layout = QVBoxLayout(self.import_project_page)
        layout.setSpacing(self.SECTION_SPACING)

        # 1. Importer Plugin Selection Group
        importer_group, importer_layout = self.create_form_section("Select Importer", layout)
        importer_row = self.create_form_row(importer_layout)
        importer_label = self.create_form_label("Importer Type:")
        self.importer_plugin_combo = QComboBox()
        self.importer_plugin_combo.setProperty("class", "mus1-combo-box")
        self.importer_plugin_combo.currentIndexChanged.connect(self.on_importer_plugin_selected)
        importer_row.addWidget(importer_label)
        importer_row.addWidget(self.importer_plugin_combo, 1)

        # 2. Dynamic Parameter Fields Group
        # Use a group box to visually contain the dynamic fields
        self.importer_params_group, self.importer_params_layout = self.create_form_section("Importer Parameters", layout)
        # Initially hide the group until a plugin is selected? Optional.
        # self.importer_params_group.setVisible(False)

        # Add stretch before the button
        layout.addStretch(1)

        # 3. Action Button
        button_row = self.create_button_row(layout)
        self.import_project_button = QPushButton("Import Project Settings")
        self.import_project_button.setProperty("class", "mus1-primary-button")
        self.import_project_button.clicked.connect(self.handle_import_project)
        self.import_project_button.setEnabled(False) # Disable until a plugin is selected
        button_row.addWidget(self.import_project_button)

        self.add_page(self.import_project_page, "Import") # Add page to stacked widget
        self.populate_importer_plugins() # Populate the dropdown

    def populate_importer_plugins(self):
        """Populates the importer plugin selection dropdown using new architecture."""
        if not hasattr(self, 'importer_plugin_combo'):
            return

        self.importer_plugin_combo.blockSignals(True)
        self.importer_plugin_combo.clear()
        self.importer_plugin_combo.addItem("Select an importer...", None)

        # For now, add a placeholder since plugin system integration is pending
        self.importer_plugin_combo.addItem("Plugin system integration pending", None)
        self.navigation_pane.add_log_message("Importer plugin integration pending in clean architecture.", "info")

        self.importer_plugin_combo.blockSignals(False)
        self.on_importer_plugin_selected(self.importer_plugin_combo.currentIndex())

    def on_importer_plugin_selected(self, index):
        """Handles selection changes in the importer plugin dropdown."""
        # Clear previous dynamic widgets and layout content
        self._clear_layout(self.importer_params_layout)
        self.importer_param_widgets.clear()
        self.importer_params_group.setVisible(False) # Hide group if no plugin selected
        self.import_project_button.setEnabled(False)

        plugin_name = self.importer_plugin_combo.itemData(index)
        if not plugin_name or plugin_name == "Plugin system integration pending":
            return # Placeholder selected

        # Plugin system integration is pending, so we can't get plugin metadata yet
        self.navigation_pane.add_log_message(f"Plugin system integration pending for '{plugin_name}'.", "info")
        return

        # TODO: Re-enable when plugin system is integrated
        # self.importer_params_group.setVisible(True) # Show the parameter group
        self.importer_params_group.setTitle(f"{plugin_name} Parameters") # Update title

        # Get fields from the selected plugin
        required_fields = plugin.required_fields()
        # optional_fields = plugin.optional_fields() # Add if needed later
        field_types = plugin.get_field_types()
        field_descriptions = plugin.get_field_descriptions()

        # Dynamically create widgets for required fields
        for field_name in required_fields:
             field_type = field_types.get(field_name, "string") # Default to string
             description = field_descriptions.get(field_name, "")

             row_layout = self.create_form_row(self.importer_params_layout)
             label_text = f"{field_name.replace('_', ' ').title()}:"
             label = self.create_form_label(label_text)
             label.setToolTip(description)
             row_layout.addWidget(label)

             widget = None
             if field_type == 'file':
                  widget = QLineEdit()
                  widget.setProperty("class", "mus1-text-input")
                  browse_button = QPushButton("Browse...")
                  browse_button.setProperty("class", "mus1-secondary-button")
                  # Use lambda to pass the line edit widget to the browse function
                  browse_button.clicked.connect(lambda checked=False, le=widget: self._browse_file_for_importer(le))
                  row_layout.addWidget(widget, 1) # Line edit takes stretch
                  row_layout.addWidget(browse_button)
             elif field_type == 'directory': # Example for directory
                 widget = QLineEdit()
                 widget.setProperty("class", "mus1-text-input")
                 browse_button = QPushButton("Browse...")
                 browse_button.setProperty("class", "mus1-secondary-button")
                 browse_button.clicked.connect(lambda checked=False, le=widget: self._browse_directory_for_importer(le))
                 row_layout.addWidget(widget, 1)
                 row_layout.addWidget(browse_button)
             # Add other types (string, int, float, enum -> QComboBox) as needed
             else: # Default to QLineEdit for string or unknown
                 widget = QLineEdit()
                 widget.setProperty("class", "mus1-text-input")
                 row_layout.addWidget(widget, 1)

             if widget:
                 # Store reference to the input widget (not the browse button)
                 self.importer_param_widgets[field_name] = widget

        # Enable the import button now that parameters are displayed
        self.import_project_button.setEnabled(True)

    def _clear_layout(self, layout):
        """Removes all widgets from a layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    # If it's a layout item, clear it recursively
                    layout_item = item.layout()
                    if layout_item is not None:
                        self._clear_layout(layout_item)

    def _browse_file_for_importer(self, line_edit_widget: QLineEdit):
        """Opens a file dialog and sets the path in the provided QLineEdit."""
        # Consider adding file type filters based on plugin requirements if possible
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            line_edit_widget.setText(file_path)

    def _browse_directory_for_importer(self, line_edit_widget: QLineEdit):
         """Opens a directory dialog and sets the path in the provided QLineEdit."""
         dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
         if dir_path:
              line_edit_widget.setText(dir_path)

    def handle_import_project(self):
        """Handles the 'Import Project Settings' button click."""
        selected_index = self.importer_plugin_combo.currentIndex()
        plugin_name = self.importer_plugin_combo.itemData(selected_index)

        if not plugin_name:
            QMessageBox.warning(self, "Import Error", "Please select an importer type.")
            return

        plugin = self.plugin_manager.get_plugin_by_name(plugin_name)
        if not plugin:
             QMessageBox.critical(self, "Import Error", f"Could not find plugin: {plugin_name}")
             return

        # Assume the first capability is the one we want for importers, or use a specific one
        capabilities = plugin.analysis_capabilities()
        if not capabilities:
             QMessageBox.critical(self, "Import Error", f"Plugin '{plugin_name}' has no defined capabilities.")
             return
        capability_name = capabilities[0] # e.g., 'import_dlc_project_settings'

        # Collect parameters from dynamically created widgets
        parameters: Dict[str, Any] = {}
        missing_required = []
        try:
            required_fields = plugin.required_fields()
            for field_name, widget in self.importer_param_widgets.items():
                value = ""
                if isinstance(widget, QLineEdit):
                    value = widget.text().strip()
                # Add elif for other widget types (QComboBox, QSpinBox, etc.) if used
                parameters[field_name] = value
                # Check if required field is empty
                if field_name in required_fields and not value:
                    missing_required.append(field_name)

            if missing_required:
                 QMessageBox.warning(self, "Missing Information",
                                     f"Please fill in the required fields: {', '.join(missing_required)}")
                 return

        except Exception as e:
             QMessageBox.critical(self, "Parameter Error", f"Error collecting parameters: {e}")
             return

        # Run the project-level action via ProjectManager
        self.navigation_pane.add_log_message(f"Starting import using {plugin_name}...", "info")
        try:
            result = self.project_manager.run_project_level_plugin_action(
                plugin_name=plugin_name,
                capability_name=capability_name,
                parameters=parameters
            )

            if result.get("status") == "success":
                 msg = result.get("message", "Import completed successfully.")
                 imported = result.get("imported_bodyparts") # Example specific data
                 if imported:
                      msg += f" Imported: {', '.join(imported)}"
                 QMessageBox.information(self, "Import Successful", msg)
                 self.navigation_pane.add_log_message(msg, "success")
                 # Optionally refresh other parts of the UI if needed (e.g., body part lists)
                 # self.window().refresh_all_views() # Maybe too broad?
            else:
                 error_msg = result.get("error", "Unknown error during import.")
                 QMessageBox.critical(self, "Import Failed", error_msg)
                 self.navigation_pane.add_log_message(f"Import failed: {error_msg}", "error")

        except Exception as e:
            error_msg = f"An unexpected error occurred during import: {e}"
            QMessageBox.critical(self, "Import Error", error_msg)
            self.navigation_pane.add_log_message(error_msg, "error")

    def setup_general_settings_page(self):
        """Setup the General Settings page with application-wide settings."""
        self.general_settings_page = QWidget()
        layout = QVBoxLayout(self.general_settings_page)
        layout.setSpacing(self.SECTION_SPACING)
        
        # 1. Display Settings Group
        display_group, display_layout = self.create_form_section("Display Settings", layout)
        theme_row = self.create_form_row(display_layout)
        theme_label = self.create_form_label("Application Theme:")
        self.theme_dropdown = QComboBox()
        self.theme_dropdown.setProperty("class", "mus1-combo-box")
        self.theme_dropdown.addItems(["dark", "light", "os"])
        theme_button = QPushButton("Apply Theme")
        theme_button.setProperty("class", "mus1-primary-button")
        theme_button.clicked.connect(lambda: self.handle_change_theme(self.theme_dropdown.currentText()))
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_dropdown, 1)
        theme_row.addWidget(theme_button)
        
        # 2. List Sort Settings Group
        sort_group, sort_layout = self.create_form_section("List Sort Settings", layout)
        sort_row = self.create_form_row(sort_layout)
        sort_label = self.create_form_label("Global Sort Mode:")
        self.sort_mode_dropdown = QComboBox()
        self.sort_mode_dropdown.setProperty("class", "mus1-combo-box")
        self.sort_mode_dropdown.addItems([
            "Natural Order (Numbers as Numbers)",
            "Lexicographical Order (Numbers as Characters)",
            "Date Added",
            "By ID"
        ])
        sort_row.addWidget(sort_label)
        sort_row.addWidget(self.sort_mode_dropdown, 1)
        apply_sort_mode_button = QPushButton("Apply Sort Mode")
        apply_sort_mode_button.setProperty("class", "mus1-primary-button")
        apply_sort_mode_button.clicked.connect(lambda: self.on_sort_mode_changed(self.sort_mode_dropdown.currentText()))
        sort_row.addWidget(apply_sort_mode_button)
        
        # 3. Video Settings Group
        video_group, video_layout = self.create_form_section("Video Settings", layout)
        
        # Create the frame rate row first
        frame_rate_row = self.create_form_row(video_layout)
        
        self.enable_frame_rate_checkbox = QCheckBox("Enable Global Frame Rate")
        self.enable_frame_rate_checkbox.setChecked(False)
        
        self.frame_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_rate_slider.setRange(0, 120)
        self.frame_rate_slider.setValue(60)
        self.frame_rate_slider.setProperty("mus1-slider", True)
        self.frame_rate_slider.setEnabled(False)
        self.enable_frame_rate_checkbox.toggled.connect(self.frame_rate_slider.setEnabled)
        
        # Create a label to display the current slider value
        self.frame_rate_value_label = QLabel(str(self.frame_rate_slider.value()))
        self.frame_rate_value_label.setFixedWidth(40)  # Fixed width for consistent UI sizing
        self.frame_rate_slider.valueChanged.connect(lambda val: self.frame_rate_value_label.setText(str(val)))
        
        frame_rate_row.addWidget(self.enable_frame_rate_checkbox)
        frame_rate_row.addWidget(self.frame_rate_slider, 1)  # Slider with stretch factor
        frame_rate_row.addWidget(self.frame_rate_value_label)
        apply_frame_rate_button = QPushButton("Apply Frame Rate")
        apply_frame_rate_button.setProperty("class", "mus1-primary-button")
        apply_frame_rate_button.clicked.connect(self.handle_apply_frame_rate)
        frame_rate_row.addWidget(apply_frame_rate_button)
        
        help_label = QLabel("When enabled, this global frame rate will be used for all files unless explicitly overridden.")
        help_label.setWordWrap(True)
        help_label.setProperty("class", "mus1-help-text")
        help_label.setVisible(False)
        video_layout.addWidget(help_label)
        
        self.enable_frame_rate_checkbox.toggled.connect(lambda checked: help_label.setVisible(checked))
        
        apply_button_row = self.create_button_row(layout)
        apply_settings_button = QPushButton("Apply All Settings")
        apply_settings_button.setProperty("class", "mus1-primary-button")
        apply_settings_button.clicked.connect(self.handle_apply_general_settings)
        apply_button_row.addWidget(apply_settings_button)
        
        layout.addStretch(1)
        self.add_page(self.general_settings_page, "Settings")
        
        self.populate_project_list()
        self.update_sort_mode_from_state()
        self.update_frame_rate_from_state()  # Initialize frame rate settings from state
        
    def set_initial_project(self, project_name: str):
        """
        Updates UI elements specific to ProjectView when a project is loaded or switched.
        Called by MainWindow after successful project load.
        """
        self.navigation_pane.add_log_message(f"Updating ProjectView for project: {project_name}", "info")
        # Update the label showing the current project
        if hasattr(self, 'current_project_label'):
            self.current_project_label.setText("Current Project: " + project_name)
        # Pre-fill rename field
        if hasattr(self, 'rename_line_edit'):
            self.rename_line_edit.setText(project_name)

        # Load project notes (still relevant here)
        if hasattr(self, 'project_notes_box') and self.window().project_manager:
            pm = self.window().project_manager
            notes = pm.config.settings.get("project_notes", "")
            self.project_notes_box.set_text(notes)

        # Update UI settings from the loaded project state
        self.update_frame_rate_from_state()
        self.update_sort_mode_from_state()
        # Update theme dropdown based on loaded project
        self.update_theme_dropdown_from_state()

        # Refresh the project list dropdown to ensure it's up-to-date
        self.populate_project_list()
        # Select the current project in the dropdown
        if hasattr(self, 'switch_project_combo'):
            index = self.switch_project_combo.findText(project_name)
            if index >= 0:
                self.switch_project_combo.setCurrentIndex(index)

        # Refresh importer plugin list as well (in case available plugins change based on project context, unlikely but good practice)
        self.populate_importer_plugins()

    def update_theme_dropdown_from_state(self):
        # Theme management moved to ConfigManager, handled by MainWindow
        if hasattr(self, 'theme_dropdown'):
            self.navigation_pane.add_log_message("Theme management now handled by ConfigManager.", "info")

    def handle_apply_general_settings(self):
        """Apply the general settings."""
        # First, apply the theme based on the theme dropdown
        theme_choice = self.theme_dropdown.currentText()
        
        # Retrieve other settings from the UI
        sort_mode = self.sort_mode_dropdown.currentText()
        frame_rate_enabled = self.enable_frame_rate_checkbox.isChecked()
        frame_rate = self.frame_rate_slider.value()  # Get value from slider instead of spin box
        
        # Create settings dictionary with all values
        settings = {
            "theme_mode": theme_choice,
            "global_sort_mode": sort_mode,
            "global_frame_rate_enabled": frame_rate_enabled,
            "global_frame_rate": frame_rate
        }
        
        # Update settings using project config
        if self.project_manager:
            self.project_manager.config.settings.update(settings)
            # Save the project to persist these settings
            self.project_manager.save_project()
            
            # Call through MainWindow to propagate theme changes across the application
            self.window().change_theme(theme_choice)
                
        self.navigation_pane.add_log_message("Applied general settings to current project.", "success")
   
    def handle_apply_frame_rate(self):
        """Handle the 'Apply Frame Rate' button click."""
        frame_rate_enabled = self.enable_frame_rate_checkbox.isChecked()
        frame_rate = self.frame_rate_slider.value()
        
        # Create settings dictionary with frame rate values
        settings = {
            "global_frame_rate_enabled": frame_rate_enabled,
            "global_frame_rate": frame_rate
        }
        
        # Update settings using project config
        if self.project_manager:
            self.project_manager.config.settings.update(settings)
            # Save project to persist changes
            self.project_manager.save_project()
            
        self.navigation_pane.add_log_message(f"Applied frame rate settings: {'Enabled' if frame_rate_enabled else 'Disabled'}, {frame_rate} fps", "success")
   
    def on_sort_mode_changed(self, new_sort_mode: str):
        """Update the project config's global_sort_mode and refresh data."""
        if self.project_manager:
            # Update sort mode using project config
            self.project_manager.config.settings["global_sort_mode"] = new_sort_mode
            # Save project to persist changes
            self.project_manager.save_project()

            # Refresh lists to show new sorting (repositories will use the updated sort mode)
            self.refresh_lists()

    def closeEvent(self, event):
        """Handle clean up when the view is closed."""
        # Clean up resources
        super().closeEvent(event)

    def handle_change_theme(self, theme_choice: str):
        """
        UI handler for theme change requests, delegates actual change to MainWindow.
        """
        main_window = self.window()
        if main_window:
            main_window.change_theme(theme_choice)

    def update_frame_rate_from_state(self):
        """Update frame rate settings from the current state using DataManager resolution."""
        # Frame rate management is not implemented in the new architecture yet
        # Set default values for now
        frame_rate_enabled = False
        display_rate = 60  # Default frame rate

        # Update UI elements if they exist
        if hasattr(self, 'frame_rate_slider'):
             # Ensure value is within slider range
             display_rate = max(self.frame_rate_slider.minimum(), min(display_rate, self.frame_rate_slider.maximum()))
             self.frame_rate_slider.setValue(display_rate)
        if hasattr(self, 'enable_frame_rate_checkbox'):
            # Block signals temporarily to avoid triggering handler during update
            self.enable_frame_rate_checkbox.blockSignals(True)
            self.enable_frame_rate_checkbox.setChecked(frame_rate_enabled)
            self.enable_frame_rate_checkbox.blockSignals(False)

        self.navigation_pane.add_log_message("Frame rate management not yet implemented in clean architecture.", "info")
        if hasattr(self, 'frame_rate_value_label'):
             self.frame_rate_value_label.setText(str(display_rate))


    def update_likelihood_filter_from_state(self):
        """Update likelihood filter settings from the current state."""
        pm = self.window().project_manager
        if not pm:
            return
        
        # Check if we have the likelihood filter components
        # These components might not exist yet in the current version
        # print("INFO: Likelihood filter update skipped - components not implemented yet") # Keep commented

    def update_sort_mode_from_state(self):
        """Update sort mode dropdown from the current state."""
        # Check if we have the sort mode dropdown
        if not hasattr(self, 'sort_mode_dropdown'):
            return

        # Sort mode management is not implemented in the new architecture yet
        # Set a default sort mode for now
        default_sort_mode = "name"  # or whatever the default should be
        index = self.sort_mode_dropdown.findText(default_sort_mode)
        if index >= 0:
            self.sort_mode_dropdown.setCurrentIndex(index)

        self.navigation_pane.add_log_message("Sort mode management not yet implemented in clean architecture.", "info")

    def populate_project_list(self):
        """Populates the project selection dropdown."""
        if not hasattr(self, 'switch_project_combo'):
            self.navigation_pane.add_log_message("Switch project combo box not found.", "warning")
            return

        current_selection = self.switch_project_combo.currentText()
        self.switch_project_combo.clear()

        # For now, add current project if available
        if hasattr(self.window(), 'selected_project_name') and self.window().selected_project_name:
            self.switch_project_combo.addItem(self.window().selected_project_name, self.window().selected_project_name)
            self.navigation_pane.add_log_message("Project switching not fully implemented in clean architecture.", "info")
        else:
            self.switch_project_combo.addItem("No projects available", None)
            self.navigation_pane.add_log_message("Project list population pending in clean architecture.", "info")

    def handle_switch_project(self):
        """Handles the 'Switch' button click."""
        selected_project = self.switch_project_combo.currentText()
        if selected_project:
            current_project = self.window().selected_project_name
            if selected_project == current_project:
                self.navigation_pane.add_log_message(f"Already in project: {selected_project}", 'info')
                return

            self.navigation_pane.add_log_message(f"Requesting switch to project: {selected_project}", 'info')
            # Try to use stored full path if present
            try:
                path_str = self.switch_project_combo.currentData()
                if path_str:
                    from pathlib import Path as _Path
                    self.window().load_project_path(_Path(path_str))
                else:
                    self.window().load_project(selected_project)
            except Exception:
                self.window().load_project(selected_project)
            # MainWindow's load_project now handles logging success/failure,
            # title updates, and view refreshes (including calling set_initial_project).
        else:
            msg = "No project selected in the dropdown to switch to."
            # print(msg) # Keep commented
            self.navigation_pane.add_log_message(msg, 'warning')

    def handle_rename_project(self):
        """Handles the 'Rename' button click."""
        new_name = self.rename_line_edit.text().strip()
        current_name = self.window().selected_project_name

        if not new_name:
            msg = "New project name cannot be empty."
            # print(msg) # Keep commented
            self.navigation_pane.add_log_message(msg, 'warning')
            return

        if new_name == current_name:
             msg = "New name is the same as the current project name."
             self.navigation_pane.add_log_message(msg, 'info')
             return

        if current_name is None:
             msg = "Cannot rename, no project is currently loaded."
             self.navigation_pane.add_log_message(msg, 'error')
             return

        try:
            self.navigation_pane.add_log_message(f"Attempting to rename project '{current_name}' to: {new_name}", 'info')
            # Perform rename using project_manager
            # Ensure project_manager exists
            if not self.project_manager:
                 self.navigation_pane.add_log_message("ProjectManager not available for rename.", "error")
                 return

            self.project_manager.rename_project(new_name)

            # --- Rename Successful ---
            self.navigation_pane.add_log_message(f"Project successfully renamed to: {new_name}", 'success')

            # Emit signal to notify MainWindow to update title etc.
            self.project_renamed.emit(new_name)

            # Update UI elements within this ProjectView
            if hasattr(self, 'current_project_label'):
                 self.current_project_label.setText("Current Project: " + new_name)
            # Keep rename_line_edit updated? Or clear it? Let's keep it updated.
            # self.rename_line_edit.setText(new_name) # Already set by user input

            # Refresh the project list dropdown
            self.populate_project_list()
            # Ensure the new name is selected in the dropdown
            if hasattr(self, 'switch_project_combo'):
                 index = self.switch_project_combo.findText(new_name)
                 if index >= 0:
                     self.switch_project_combo.setCurrentIndex(index)


        except Exception as e:
            error_msg = f"Error renaming project '{current_name}' to '{new_name}': {e}"
            # print(error_msg) # Keep commented
            self.navigation_pane.add_log_message(error_msg, 'error')
            # Restore rename line edit to current name on failure?
            if hasattr(self, 'rename_line_edit'):
                 self.rename_line_edit.setText(current_name)

    def setup_project_settings_page(self):
        """Setup the Project Settings page with project info controls."""
        # Create the page widget without redundant styling
        self.project_settings_page = QWidget()
        layout = QVBoxLayout(self.project_settings_page)
        layout.setSpacing(15)

        # Project selection group
        selection_group = QGroupBox("Project Selection")
        selection_group.setProperty("class", "mus1-input-group")
        selection_layout = QVBoxLayout(selection_group)
        
        # Current project display
        current_layout = QHBoxLayout()
        self.current_project_label = QLabel("Current Project: None")
        self.current_project_label.setProperty("formLabel", True)
        self.current_project_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        current_layout.addWidget(self.current_project_label)
        current_layout.addStretch(1)
        selection_layout.addLayout(current_layout)
        
        # Project selector
        selector_layout = self.create_form_row()
        switch_label = self.create_form_label("Switch to:")
        
        # Location chooser for listing projects (Local/Shared)
        self.switch_location_combo = QComboBox()
        self.switch_location_combo.setProperty("class", "mus1-combo-box")
        self.switch_location_combo.addItems(["Local", "Shared"])
        self.switch_location_combo.currentIndexChanged.connect(self.populate_project_list)

        self.switch_project_combo = QComboBox()
        self.switch_project_combo.setProperty("class", "mus1-combo-box")
        self.switch_project_button = QPushButton("Switch")
        self.switch_project_button.setProperty("class", "mus1-primary-button")
        self.switch_project_button.clicked.connect(self.handle_switch_project)
        
        selector_layout.addWidget(switch_label)
        selector_layout.addWidget(self.switch_location_combo)
        selector_layout.addWidget(self.switch_project_combo, 1)
        selector_layout.addWidget(self.switch_project_button)
        selection_layout.addLayout(selector_layout)
        
        # Add the selection group to the main layout to preserve its children (including the combo box)
        layout.addWidget(selection_group)
        
        # Project renaming group
        rename_group, rename_layout_container = self.create_form_section("Rename Project", layout)
        rename_layout = self.create_form_row(rename_layout_container)
        
        rename_label = self.create_form_label("New Name:")
        self.rename_line_edit = QLineEdit()
        self.rename_line_edit.setProperty("class", "mus1-text-input")
        self.rename_button = QPushButton("Rename")
        self.rename_button.setProperty("class", "mus1-primary-button")
        self.rename_button.clicked.connect(self.handle_rename_project)
        
        rename_layout.addWidget(rename_label)
        rename_layout.addWidget(self.rename_line_edit, 1)
        rename_layout.addWidget(self.rename_button)
        
        # Add rename group to main layout
        layout.addWidget(rename_group)
        
        # Project notes - placed last as requested
        # Shared storage group
        shared_group, shared_layout_container = self.create_form_section("Shared Storage", layout)
        shared_layout = self.create_form_row(shared_layout_container)

        self.shared_root_line = QLineEdit()
        self.shared_root_line.setProperty("class", "mus1-text-input")
        browse_shared_btn = QPushButton("Browse…")
        browse_shared_btn.setProperty("class", "mus1-secondary-button")
        browse_shared_btn.clicked.connect(self._browse_shared_root)

        set_shared_btn = QPushButton("Set Shared Root")
        set_shared_btn.setProperty("class", "mus1-primary-button")
        set_shared_btn.clicked.connect(self.handle_set_shared_root)

        move_to_shared_btn = QPushButton("Move Project to Shared")
        move_to_shared_btn.setProperty("class", "mus1-primary-button")
        move_to_shared_btn.clicked.connect(self.handle_move_project_to_shared)

        shared_layout.addWidget(self.create_form_label("Shared Root:"))
        shared_layout.addWidget(self.shared_root_line, 1)
        shared_layout.addWidget(browse_shared_btn)
        shared_layout.addWidget(set_shared_btn)
        shared_layout.addWidget(move_to_shared_btn)

        # Pre-fill from state if available
        try:
            if hasattr(self, 'project_service') and self.project_service:
                project_info = self.project_service.get_project_info()
                if project_info.get('shared_root'):
                    self.shared_root_line.setText(project_info['shared_root'])
        except Exception:
            pass

        self.project_notes_box = NotesBox(
            title="Project Notes",
            placeholder_text="Enter project notes, details, and important information here..."
        )
        self.project_notes_box.connect_save_button(self.handle_save_project_notes)
        
        # Add notes to main layout (placed last as requested) with vertical stretch
        layout.addWidget(self.project_notes_box, 1)  # Give it a stretch factor of 1
        
        # Add the page to the stacked widget - BaseView will apply styling
        self.add_page(self.project_settings_page, "Project Settings")
        
        # Initialize the project list
        self.populate_project_list()
        
    def handle_save_project_notes(self):
        """Save the project notes to the current project state."""
        if not hasattr(self, 'window') or not self.window():
            self.navigation_pane.add_log_message("Cannot save notes: window reference not available.", 'error')
            return
            
        notes = self.project_notes_box.get_text()
        try:
            # Ensure project_manager is available
            if not self.project_manager:
                 self.navigation_pane.add_log_message("Cannot save notes: Project manager not available.", 'error')
                 return

            # Update notes in project config settings
            self.project_manager.config.settings["project_notes"] = notes
            # Save the project to persist changes
            self.project_manager.save_project()
            
            self.navigation_pane.add_log_message("Project notes saved successfully.", 'success')
        except Exception as e:
            error_msg = f"Error saving project notes: {e}"
            # print(error_msg) # Keep commented
            self.navigation_pane.add_log_message(error_msg, 'error')

    def _browse_shared_root(self):
        try:
            directory = QFileDialog.getExistingDirectory(self, "Select Shared Root", str(Path.home()))
            if directory:
                self.shared_root_line.setText(directory)
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error selecting shared root: {e}", "error")

    def handle_set_shared_root(self):
        try:
            path_text = self.shared_root_line.text().strip()
            if not path_text:
                QMessageBox.warning(self, "Shared Root", "Please select or enter a shared root path.")
                return
            sr = Path(path_text).expanduser()
            if not sr.exists():
                # Offer to create
                create = QMessageBox.question(self, "Create Directory", f"Create directory?\n{sr}")
                if create == QMessageBox.StandardButton.Yes:
                    sr.mkdir(parents=True, exist_ok=True)
                else:
                    return
            self.window().project_manager.set_shared_root(sr)
            self.window().project_manager.save_project()
            self.navigation_pane.add_log_message(f"Shared root set to {sr}", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Failed to set shared root: {e}", "error")

    def handle_move_project_to_shared(self):
        try:
            pm = self.window().project_manager
            sr = pm.config.shared_root
            if not sr:
                QMessageBox.warning(self, "Shared Root", "Set a shared root first.")
                return
            new_path = pm.move_project_to_directory(Path(sr))
            self.navigation_pane.add_log_message(f"Project moved to {new_path}", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Failed to move project: {e}", "error")

    def update_theme(self, theme):
        """Update theme for this view and propagate any view-specific changes."""
        super().update_theme(theme)
        self.navigation_pane.add_log_message(f"Theme updated to {theme}.", "info")

    def refresh_lists(self):
        """Refreshes lists managed by this view."""
        self.navigation_pane.add_log_message("Refreshing ProjectView lists...", "info")
        self.populate_project_list()
        self.populate_importer_plugins() # Also refresh importer list
        # Refresh settings UI from state
        self.update_frame_rate_from_state()
        self.update_sort_mode_from_state()
        self.update_theme_dropdown_from_state()
        # Refresh new admin lists
        try:
            self.refresh_targets_admin_list()
            self.refresh_targets_list()
        except Exception:
            pass

    def setup_scan_ingest_page(self):
        """Setup a page to scan configured targets and ingest videos into the project."""
        self.scan_ingest_page = QWidget()
        layout = QVBoxLayout(self.scan_ingest_page)
        layout.setSpacing(self.SECTION_SPACING)

        # Targets selection
        targets_group, tg_layout = self.create_form_section("Scan Targets", layout)
        row = self.create_form_row(tg_layout)
        row.addWidget(self.create_form_label("Select targets:"))
        self.targets_list = QListWidget()
        self.targets_list.setProperty("class", "mus1-list-widget")
        self.targets_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        row.addWidget(self.targets_list, 1)

        # Options
        opt_group, opt_layout = self.create_form_section("Options", layout)
        opt_row1 = self.create_form_row(opt_layout)
        self.extensions_line = QLineEdit()
        self.extensions_line.setProperty("class", "mus1-text-input")
        self.extensions_line.setPlaceholderText("Extensions (e.g., .mp4 .avi .mov)")
        opt_row1.addWidget(self.create_form_label("Extensions:"))
        opt_row1.addWidget(self.extensions_line, 1)

        opt_row2 = self.create_form_row(opt_layout)
        self.exclude_line = QLineEdit()
        self.exclude_line.setProperty("class", "mus1-text-input")
        self.exclude_line.setPlaceholderText("Exclude dirs substrings (comma-separated)")
        opt_row2.addWidget(self.create_form_label("Excludes:"))
        opt_row2.addWidget(self.exclude_line, 1)

        opt_row3 = self.create_form_row(opt_layout)
        self.non_recursive_check = QCheckBox("Non-recursive")
        opt_row3.addWidget(self.non_recursive_check)

        # Actions and progress
        action_row = self.create_button_row(layout)
        self.scan_button = QPushButton("Scan Selected Targets")
        self.scan_button.setProperty("class", "mus1-primary-button")
        self.scan_button.clicked.connect(self.handle_scan_targets)
        action_row.addWidget(self.scan_button)

        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        layout.addWidget(self.scan_progress)

        # Summary and staging
        self.scan_summary_label = QLabel("")
        layout.addWidget(self.scan_summary_label)

        stage_group, stage_layout = self.create_form_section("Stage Off-Shared", layout)
        stage_row = self.create_form_row(stage_layout)
        self.stage_subdir_line = QLineEdit()
        self.stage_subdir_line.setProperty("class", "mus1-text-input")
        self.stage_subdir_line.setPlaceholderText("Destination subdir under shared root (e.g., recordings/raw)")
        self.stage_button = QPushButton("Stage Off-Shared to Subdir")
        self.stage_button.setProperty("class", "mus1-primary-button")
        self.stage_button.clicked.connect(self.handle_stage_off_shared)
        stage_row.addWidget(self.create_form_label("Subdir:"))
        stage_row.addWidget(self.stage_subdir_line, 1)
        stage_row.addWidget(self.stage_button)

        add_row = self.create_button_row(layout)
        self.add_shared_button = QPushButton("Add Unique Under Shared")
        self.add_shared_button.setProperty("class", "mus1-primary-button")
        self.add_shared_button.clicked.connect(self.handle_add_under_shared)
        add_row.addWidget(self.add_shared_button)

        layout.addStretch(1)
        self.add_page(self.scan_ingest_page, "Scan & Ingest")

        # Data holders
        self._dedup_results = []  # list of tuples (Path, hash, start_time)
        self._off_shared = []     # list of (Path, hash)
        self._in_shared = []      # list of (Path, hash, start_time)

        # Populate targets list initially
        self.refresh_targets_list()

    def refresh_targets_list(self):
        if not hasattr(self, 'targets_list'):
            return
        self.targets_list.clear()
        try:
            targets = list(self.project_manager.config.settings.get('scan_targets', []) or [])
        except Exception:
            targets = []
        for t in targets:
            item = QListWidgetItem(f"{t.name}  ({t.kind})")
            item.setData(Qt.ItemDataRole.UserRole, t.name)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.targets_list.addItem(item)

    def handle_scan_targets(self):
        try:
            sr = self.project_manager.config.shared_root
            selected_names = []
            for i in range(self.targets_list.count()):
                it = self.targets_list.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    selected_names.append(it.data(Qt.ItemDataRole.UserRole))
            if not selected_names:
                QMessageBox.warning(self, "Scan", "Select at least one target to scan.")
                return

            # Build filters
            exts_text = self.extensions_line.text().strip()
            extensions = [e.strip() for e in exts_text.split() if e.strip()] if exts_text else None
            excl_text = self.exclude_line.text().strip()
            excludes = [e.strip() for e in excl_text.split(',') if e.strip()] if excl_text else None
            non_recursive = self.non_recursive_check.isChecked()

            # Resolve targets
            all_targets = list(self.project_manager.config.settings.get('scan_targets', []) or [])
            targets = [t for t in all_targets if t.name in set(selected_names)]
            if not targets:
                QMessageBox.warning(self, "Scan", "No matching targets found.")
                return

            # Progress callback to update bar approximately
            self.scan_progress.setValue(0)
            def _cb(done: int, total: int):
                if total > 0:
                    val = max(0, min(100, int(done * 100 / total)))
                    self.scan_progress.setValue(val)

            # Collect and dedup - TODO: Integrate with clean architecture
            # items = collect_from_targets(self.state_manager, self.data_manager, targets, extensions=extensions, exclude_dirs=excludes, non_recursive=non_recursive)
            items = []  # Placeholder until integration is complete
            # dedup = list(self.data_manager.deduplicate_video_list(items, progress_cb=_cb))
            dedup = []  # Placeholder until integration is complete

            # Partition by shared root
            self._dedup_results = dedup
            self._in_shared = []
            self._off_shared = []
            for p, h, ts in dedup:
                try:
                    if sr and str(Path(p).resolve()).startswith(str(Path(sr).resolve())):
                        self._in_shared.append((p, h, ts))
                    else:
                        self._off_shared.append((p, h))
                except Exception:
                    self._off_shared.append((p, h))

            total = len(items)
            unique = len(dedup)
            off_shared = len(self._off_shared)
            self.scan_summary_label.setText(f"Scanned files: {total} | Unique: {unique} | Off-shared: {off_shared}")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Scan failed: {e}", "error")

    def handle_add_under_shared(self):
        try:
            if not self._in_shared:
                QMessageBox.information(self, "Add", "No items under shared root to add.")
                return
            added = self.project_manager.register_unlinked_videos(iter(self._in_shared))
            QMessageBox.information(self, "Add", f"Added {added} videos under shared root.")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Add under shared failed: {e}", "error")

    def handle_stage_off_shared(self):
        try:
            if not self._off_shared:
                QMessageBox.information(self, "Stage", "No off-shared items to stage.")
                return
            sr = self.project_manager.config.shared_root
            if not sr:
                QMessageBox.warning(self, "Stage", "Set shared root first in Project Settings.")
                return
            subdir = self.stage_subdir_line.text().strip()
            if not subdir:
                QMessageBox.warning(self, "Stage", "Enter a destination subdirectory under shared root.")
                return
            dest_base = Path(sr) / subdir

            # Convert to tuples for staging (Path, hash)
            src_with_hashes = list(self._off_shared)

            # Simple progress update
            self.scan_progress.setValue(0)
            def _cb(done: int, total: int):
                if total > 0:
                    self.scan_progress.setValue(max(0, min(100, int(done * 100 / total))))

            # staged_iter = self.data_manager.stage_files_to_shared(
            #     src_with_hashes,
            #     shared_root=Path(sr),
            #     dest_base=dest_base,
            #     overwrite=False,
            #     progress_cb=_cb,
            # )
            staged_iter = []  # Placeholder until integration is complete
            added = self.project_manager.register_unlinked_videos(staged_iter)
            QMessageBox.information(self, "Stage", f"Staged and added {added} videos.")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Stage failed: {e}", "error")

    def setup_targets_page(self):
        """Setup Targets management page (typed scan targets CRUD)."""
        self.targets_page = QWidget()
        layout = QVBoxLayout(self.targets_page)
        layout.setSpacing(self.SECTION_SPACING)

        list_group, list_layout = self.create_form_section("Scan Targets", layout)
        row = self.create_form_row(list_layout)
        self.targets_admin_list = QListWidget()
        self.targets_admin_list.setProperty("class", "mus1-list-widget")
        row.addWidget(self.targets_admin_list, 1)

        form_group, form_layout = self.create_form_section("Add Target", layout)
        r1 = self.create_form_row(form_layout)
        self.target_name_edit = QLineEdit()
        self.target_name_edit.setProperty("class", "mus1-text-input")
        self.target_kind_combo = QComboBox()
        self.target_kind_combo.setProperty("class", "mus1-combo-box")
        self.target_kind_combo.addItems(["local", "ssh", "wsl"])
        self.target_ssh_alias_edit = QLineEdit()
        self.target_ssh_alias_edit.setProperty("class", "mus1-text-input")
        r1.addWidget(self.create_form_label("Name:"))
        r1.addWidget(self.target_name_edit)
        r1.addWidget(self.create_form_label("Kind:"))
        r1.addWidget(self.target_kind_combo)
        r2 = self.create_form_row(form_layout)
        r2.addWidget(self.create_form_label("SSH Alias:"))
        r2.addWidget(self.target_ssh_alias_edit)
        r3 = self.create_form_row(form_layout)
        self.target_roots_edit = QLineEdit()
        self.target_roots_edit.setProperty("class", "mus1-text-input")
        self.target_roots_edit.setPlaceholderText("Roots (use ';' to separate multiple paths)")
        r3.addWidget(self.create_form_label("Roots:"))
        r3.addWidget(self.target_roots_edit, 1)

        btn_row = self.create_button_row(layout)
        add_btn = QPushButton("Add Target")
        add_btn.setProperty("class", "mus1-primary-button")
        add_btn.clicked.connect(self.handle_add_target)
        rem_btn = QPushButton("Remove Selected Target")
        rem_btn.setProperty("class", "mus1-secondary-button")
        rem_btn.clicked.connect(self.handle_remove_target)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)

        layout.addStretch(1)
        self.add_page(self.targets_page, "Targets")

        self.refresh_targets_admin_list()

    def refresh_targets_admin_list(self):
        if not hasattr(self, 'targets_admin_list'):
            return
        self.targets_admin_list.clear()
        try:
            targets = self.project_manager.config.settings.get('scan_targets', [])
        except Exception:
            targets = []
        for t in targets:
            roots_str = ", ".join(str(r) for r in t.get('roots', []))
            alias = t.get('ssh_alias', '') or ''
            item = QListWidgetItem(f"{t.get('name', '')}  kind={t.get('kind', '')}  alias={alias}  roots=[{roots_str}]")
            item.setData(Qt.ItemDataRole.UserRole, t.get('name', ''))
            self.targets_admin_list.addItem(item)

    def handle_add_target(self):
        try:
            name = self.target_name_edit.text().strip()
            kind = self.target_kind_combo.currentText().strip()
            ssh_alias = self.target_ssh_alias_edit.text().strip() or None
            roots_raw = self.target_roots_edit.text().strip()
            if not name or not kind:
                QMessageBox.warning(self, "Targets", "Name and kind are required.")
                return
            if kind in ("ssh", "wsl") and not ssh_alias:
                QMessageBox.warning(self, "Targets", "SSH alias is required for ssh/wsl targets.")
                return
            roots: list[Path] = []
            if roots_raw:
                for part in roots_raw.split(';'):
                    p = part.strip()
                    if p:
                        roots.append(Path(p).expanduser())
            if not roots:
                QMessageBox.warning(self, "Targets", "At least one root path is required.")
                return
            targets = self.project_manager.config.settings.get('scan_targets', [])
            if any(t.get('name') == name for t in targets):
                QMessageBox.warning(self, "Targets", f"Target '{name}' already exists.")
                return
            target_dict = {
                'name': name,
                'kind': kind,
                'roots': roots,
                'ssh_alias': ssh_alias
            }
            targets.append(target_dict)
            self.project_manager.config.settings['scan_targets'] = targets
            self.project_manager.save_project()
            self.refresh_targets_admin_list()
            self.refresh_targets_list()
            self.navigation_pane.add_log_message(f"Added target {name}", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Add target failed: {e}", "error")

    def handle_remove_target(self):
        try:
            item = self.targets_admin_list.currentItem()
            if not item:
                QMessageBox.information(self, "Targets", "Select a target to remove.")
                return
            name = item.data(Qt.ItemDataRole.UserRole)
            targets = self.project_manager.config.settings.get('scan_targets', [])
            before = len(targets)
            targets = [t for t in targets if t.get('name') != name]
            self.project_manager.config.settings['scan_targets'] = targets
            if len(targets) == before:
                QMessageBox.information(self, "Targets", f"No target named '{name}' found.")
                return
            self.window().project_manager.save_project()
            self.refresh_targets_admin_list()
            self.refresh_targets_list()
            self.navigation_pane.add_log_message(f"Removed target {name}", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Remove target failed: {e}", "error")


        
   