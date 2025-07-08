from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit,
    QComboBox, QPushButton, QListWidget, QLabel, QFileDialog, QTextEdit,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider, QMessageBox
)
from pathlib import Path
from .base_view import BaseView
from PySide6.QtCore import Qt, Signal
from ..core import ObjectMetadata, BodyPartMetadata, PluginManager
from ..core.data_manager import FrameRateResolutionError
from ..plugins.base_plugin import BasePlugin
from typing import Dict, Any


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
        self.state_manager = self.window().state_manager
        self.project_manager = self.window().project_manager
        self.plugin_manager = self.window().plugin_manager
        self.data_manager = self.window().data_manager
        self.importer_param_widgets: Dict[str, QWidget] = {} # Initialize the dictionary here
        self.setup_navigation(["Import Project", "Project Settings", "General Settings"])
        self.setup_import_project_page()
        self.setup_project_settings_page()
        self.setup_general_settings_page()
        self.change_page(0)

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
        """Populates the importer plugin selection dropdown using StateManager."""
        if not hasattr(self, 'importer_plugin_combo') or not self.state_manager:
            return

        self.importer_plugin_combo.blockSignals(True)
        self.importer_plugin_combo.clear()
        self.importer_plugin_combo.addItem("Select an importer...", None)

        # --- Find Importer Plugins via StateManager ---
        importer_plugins_meta = self.state_manager.get_plugins_by_type('importer')

        if not importer_plugins_meta:
            self.navigation_pane.add_log_message("No importer plugins found in state.", "warning")
        else:
            # The method already returns metadata, so we just sort and add it.
            for meta in sorted(importer_plugins_meta, key=lambda m: m.name):
                self.importer_plugin_combo.addItem(meta.name, meta.name)

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
        if not plugin_name:
            return # Placeholder selected

        plugin = self.plugin_manager.get_plugin_by_name(plugin_name)
        if not plugin:
            self.navigation_pane.add_log_message(f"Selected importer plugin '{plugin_name}' not found.", "error")
            return

        self.importer_params_group.setVisible(True) # Show the parameter group
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
        
        self.frame_rate_slider = QSlider(Qt.Horizontal)
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
        if hasattr(self, 'project_notes_box') and self.window().project_manager.state_manager:
            state = self.window().project_manager.state_manager.project_state
            # Check if project_metadata exists before accessing settings through it
            if state.project_metadata:
                 notes = state.settings.get("project_notes", "") # Still access notes via settings for now
                 self.project_notes_box.set_text(notes)
            else:
                 self.project_notes_box.set_text("") # Clear notes if no project loaded

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
        if hasattr(self, 'theme_dropdown') and self.state_manager:
            theme_pref = self.state_manager.get_theme_preference()
            index = self.theme_dropdown.findText(theme_pref)
            if index >= 0:
                self.theme_dropdown.setCurrentIndex(index)

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
        
        # Update settings using the unified method
        if self.state_manager:
            self.state_manager.update_project_settings(settings)
            
            # Save the project to persist these settings
            self.window().project_manager.save_project()
            
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
        
        # Update settings using the unified method
        if self.state_manager:
            self.state_manager.update_project_settings(settings)
            
            # Save project to persist changes
            self.window().project_manager.save_project()
            
        self.navigation_pane.add_log_message(f"Applied frame rate settings: {'Enabled' if frame_rate_enabled else 'Disabled'}, {frame_rate} fps", "success")
   
    def on_sort_mode_changed(self, new_sort_mode: str):
        """Update the project state's global_sort_mode using the unified settings method."""
        if self.state_manager:
            # Update sort mode using the unified method
            self.state_manager.update_project_settings({"global_sort_mode": new_sort_mode})
            
            # Save project to persist changes
            self.window().project_manager.save_project()
            
            # Refresh lists to show new sorting (e.g., project list if sorting applies)
            self.refresh_lists()

    def closeEvent(self, event):
        """Handle clean up when the view is closed."""
        # Unsubscribe from state manager to prevent memory leaks
        if hasattr(self, 'state_manager') and self.state_manager:
            self.state_manager.unsubscribe(self.refresh_lists)
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
        try:
            # Check if data_manager exists before calling resolve_frame_rate
            if not self.data_manager:
                 self.navigation_pane.add_log_message("DataManager not available.", "warning")
                 return

            final_frame_rate = self.data_manager.resolve_frame_rate(None, None, None)
        except FrameRateResolutionError as e:
            self.navigation_pane.add_log_message(f"Frame rate resolution error: {str(e)}", "error")
            final_frame_rate = "OFF" # Default to OFF on error
        except AttributeError:
             self.navigation_pane.add_log_message("DataManager not fully initialized.", "warning")
             return


        if final_frame_rate == "OFF":
            frame_rate_enabled = False
            # Get default from metadata if available, otherwise fallback
            default_rate = 60
            if self.state_manager and self.state_manager.project_state and self.state_manager.project_state.project_metadata:
                 default_rate = self.state_manager.project_state.project_metadata.global_frame_rate
            display_rate = default_rate
        else:
            frame_rate_enabled = True
            display_rate = final_frame_rate

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
        if hasattr(self, 'frame_rate_value_label'):
             self.frame_rate_value_label.setText(str(display_rate))


    def update_likelihood_filter_from_state(self):
        """Update likelihood filter settings from the current state."""
        pm = self.window().project_manager
        if not pm or not pm.state_manager:
            return
        
        state = pm.state_manager.project_state
        
        # Check if we have the likelihood filter components
        # These components might not exist yet in the current version
        # print("INFO: Likelihood filter update skipped - components not implemented yet") # Keep commented

    def update_sort_mode_from_state(self):
        """Update sort mode dropdown from the current state."""
        if not self.state_manager: return # Check if state_manager exists

        state = self.state_manager.project_state

        # Check if we have the sort mode dropdown
        if not hasattr(self, 'sort_mode_dropdown'):
            # print("WARNING: Sort mode dropdown not found") # Keep commented
            return

        # Get sort mode using the consolidated property access
        sort_mode = self.state_manager.get_global_sort_mode()

        # Find and select the appropriate item in the dropdown
        index = self.sort_mode_dropdown.findText(sort_mode)
        if index >= 0:
            self.sort_mode_dropdown.setCurrentIndex(index)
        else:
             # Log if the sort mode from state isn't in the dropdown options
             self.navigation_pane.add_log_message(f"Sort mode '{sort_mode}' from state not found in dropdown.", "warning")

    def populate_project_list(self):
        """Populates the project selection dropdown."""
        if not hasattr(self, 'switch_project_combo'):
            self.navigation_pane.add_log_message("Switch project combo box not found.", "warning")
            return

        current_selection = self.switch_project_combo.currentText()
        self.switch_project_combo.clear()
        try:
            # Ensure project_manager exists before calling list_available_projects
            if not self.project_manager:
                 self.navigation_pane.add_log_message("ProjectManager not available.", "error")
                 return

            projects = self.project_manager.list_available_projects()
            project_names = sorted([p.name for p in projects]) # Sort alphabetically
            self.switch_project_combo.addItems(project_names)

            # Try to restore previous selection or select current project
            current_project = self.window().selected_project_name
            if current_project in project_names:
                 index = self.switch_project_combo.findText(current_project)
                 if index >= 0:
                     self.switch_project_combo.setCurrentIndex(index)
            elif current_selection in project_names:
                 index = self.switch_project_combo.findText(current_selection)
                 if index >= 0:
                     self.switch_project_combo.setCurrentIndex(index)

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error populating project list: {e}", "error")

    def handle_switch_project(self):
        """Handles the 'Switch' button click."""
        selected_project = self.switch_project_combo.currentText()
        if selected_project:
            current_project = self.window().selected_project_name
            if selected_project == current_project:
                self.navigation_pane.add_log_message(f"Already in project: {selected_project}", 'info')
                return

            self.navigation_pane.add_log_message(f"Requesting switch to project: {selected_project}", 'info')
            # Delegate loading entirely to MainWindow
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
        self.current_project_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        current_layout.addWidget(self.current_project_label)
        current_layout.addStretch(1)
        selection_layout.addLayout(current_layout)
        
        # Project selector
        selector_layout = self.create_form_row()
        switch_label = self.create_form_label("Switch to:")
        
        self.switch_project_combo = QComboBox()
        self.switch_project_combo.setProperty("class", "mus1-combo-box")
        self.switch_project_button = QPushButton("Switch")
        self.switch_project_button.setProperty("class", "mus1-primary-button")
        self.switch_project_button.clicked.connect(self.handle_switch_project)
        
        selector_layout.addWidget(switch_label)
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
            # Ensure project_manager and state_manager are available
            if not self.project_manager or not self.project_manager.state_manager:
                 self.navigation_pane.add_log_message("Cannot save notes: Project or State manager not available.", 'error')
                 return

            # Get the current project state
            state = self.project_manager.state_manager.project_state
            # Update the notes in the state
            state.settings["project_notes"] = notes
            # Update internal state and persist changes to disk
            self.project_manager.state_manager.notify_observers()
            self.project_manager.save_project()
            
            self.navigation_pane.add_log_message("Project notes saved successfully.", 'success')
        except Exception as e:
            error_msg = f"Error saving project notes: {e}"
            # print(error_msg) # Keep commented
            self.navigation_pane.add_log_message(error_msg, 'error')

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


        
   