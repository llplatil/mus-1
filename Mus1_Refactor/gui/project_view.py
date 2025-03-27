from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit,
    QComboBox, QPushButton, QListWidget, QLabel, QFileDialog, QTextEdit,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider
)
from pathlib import Path
from gui.base_view import BaseView
from PySide6.QtCore import Qt, Signal
from core import ObjectMetadata, BodyPartMetadata  # Import both from core package consistently
from core.data_manager import FrameRateResolutionError  # Import custom exception


class NotesBox(QGroupBox):
    """A reusable notes component that can be added to any view."""
    def __init__(self, parent=None, title="Notes", placeholder_text="Enter notes here..."):
        super().__init__(title, parent)
        self.setProperty("class", "mus1-notes-container")
        
        # Get access to BaseView constants through parent
        base_view = self.find_base_view_parent(parent)
        form_margin = BaseView.FORM_MARGIN
        control_spacing = BaseView.CONTROL_SPACING
        
        if base_view:
            form_margin = base_view.FORM_MARGIN
            control_spacing = base_view.CONTROL_SPACING
        
        # Set up the layout using the BaseView constants
        layout = QVBoxLayout(self)
        layout.setContentsMargins(form_margin, form_margin, form_margin, form_margin)
        layout.setSpacing(control_spacing)
        
        # Create the text edit for notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setProperty("class", "mus1-notes-edit")
        self.notes_edit.setPlaceholderText(placeholder_text)
        
        # Create a button row layout with consistent spacing
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(control_spacing)
        
        # Add save button to the button row
        self.save_button = QPushButton("Save Notes")
        self.save_button.setProperty("class", "mus1-primary-button")
        button_row.addWidget(self.save_button)
        button_row.addStretch(1)
        
        # Add widgets to layout with consistent spacing
        layout.addWidget(self.notes_edit)
        layout.addLayout(button_row)
    
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
        self.data_manager = self.window().data_manager
        self.setup_navigation(["Project Settings", "General Settings"])
        self.setup_project_settings_page()
        self.setup_general_settings_page()
        self.change_page(0)

    def format_item(self, item):
        """Utility to return the proper display string for an item."""
        return item.name if hasattr(item, "name") else str(item)

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
            notes = state.settings.get("project_notes", "")
            self.project_notes_box.set_text(notes)

        # Update UI settings from the loaded project state if needed here
        # These might be redundant if MainWindow.refresh_all_views covers them via state changes
        self.update_frame_rate_from_state()
        self.update_sort_mode_from_state()

        # Refresh the project list dropdown to ensure it's up-to-date
        self.populate_project_list()
        # Select the current project in the dropdown
        if hasattr(self, 'switch_project_combo'):
            index = self.switch_project_combo.findText(project_name)
            if index >= 0:
                self.switch_project_combo.setCurrentIndex(index)

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
            final_frame_rate = self.window().data_manager._resolve_frame_rate(None, None, None)
        except FrameRateResolutionError as e:
            self.navigation_pane.add_log_message(f"Frame rate resolution error: {str(e)}", "error")
            final_frame_rate = 0

        if final_frame_rate == "OFF":
            frame_rate_enabled = False
            display_rate = 60  # Default display value when disabled
            self.navigation_pane.add_log_message("Global frame rate is disabled - experiment-specific rates will be required", "info")
        else:
            frame_rate_enabled = True
            display_rate = final_frame_rate
            self.navigation_pane.add_log_message(f"Global frame rate is enabled: {final_frame_rate} fps", "info")

        # Update UI elements if they exist
        if hasattr(self, 'frame_rate_slider'):
            self.frame_rate_slider.setValue(display_rate)
        if hasattr(self, 'enable_frame_rate_checkbox'):
            self.enable_frame_rate_checkbox.setChecked(frame_rate_enabled)

    def update_likelihood_filter_from_state(self):
        """Update likelihood filter settings from the current state."""
        pm = self.window().project_manager
        if not pm or not pm.state_manager:
            return
        
        state = pm.state_manager.project_state
        
        # Check if we have the likelihood filter components
        # These components might not exist yet in the current version
        print("INFO: Likelihood filter update skipped - components not implemented yet")

    def update_sort_mode_from_state(self):
        """Update sort mode dropdown from the current state."""
        pm = self.window().project_manager
        if not pm or not pm.state_manager:
            return
        
        state = pm.state_manager.project_state
        
        # Check if we have the sort mode dropdown
        if not hasattr(self, 'sort_mode_dropdown'):
            print("WARNING: Sort mode dropdown not found")
            return
            
        # Get sort mode from state
        sort_mode = "Natural Order (Numbers as Numbers)"  # Default value
        if state.project_metadata and hasattr(state.project_metadata, 'global_sort_mode'):
            sort_mode = state.project_metadata.global_sort_mode
        elif 'global_sort_mode' in state.settings:
            sort_mode = state.settings['global_sort_mode']
        
        # Find and select the appropriate item in the dropdown
        index = self.sort_mode_dropdown.findText(sort_mode)
        if index >= 0:
            self.sort_mode_dropdown.setCurrentIndex(index)
   
    def populate_project_list(self):
        """Populates the project selection dropdown."""
        if not hasattr(self, 'switch_project_combo'):
            self.navigation_pane.add_log_message("Switch project combo box not found.", "warning")
            return

        current_selection = self.switch_project_combo.currentText()
        self.switch_project_combo.clear()
        try:
            projects = self.window().project_manager.list_available_projects()
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
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')

    def handle_rename_project(self):
        """Handles the 'Rename' button click."""
        new_name = self.rename_line_edit.text().strip()
        current_name = self.window().selected_project_name

        if not new_name:
            msg = "New project name cannot be empty."
            print(msg)
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
            self.window().project_manager.rename_project(new_name)

            # --- Rename Successful ---
            self.navigation_pane.add_log_message(f"Project successfully renamed to: {new_name}", 'success')

            # Emit signal to notify MainWindow to update title etc.
            self.project_renamed.emit(new_name)

            # Update UI elements within this ProjectView
            self.current_project_label.setText("Current Project: " + new_name)
            # Keep rename_line_edit updated? Or clear it? Let's keep it updated.
            # self.rename_line_edit.setText(new_name) # Already set by user input

            # Refresh the project list dropdown
            self.populate_project_list()
            # Ensure the new name is selected in the dropdown
            index = self.switch_project_combo.findText(new_name)
            if index >= 0:
                self.switch_project_combo.setCurrentIndex(index)


        except Exception as e:
            error_msg = f"Error renaming project '{current_name}' to '{new_name}': {e}"
            print(error_msg)
            self.navigation_pane.add_log_message(error_msg, 'error')
            # Restore rename line edit to current name on failure?
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
        current_layout.addWidget(self.current_project_label)
        current_layout.addStretch(1)
        selection_layout.addLayout(current_layout)
        
        # Project selector
        selector_layout = QHBoxLayout()
        switch_label = QLabel("Switch to:")
        switch_label.setProperty("formLabel", True)
        
        self.switch_project_combo = QComboBox(selection_group)  # Set parent to selection_group
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
        rename_group = QGroupBox("Rename Project")
        rename_group.setProperty("class", "mus1-input-group")
        rename_layout = QHBoxLayout(rename_group)
        
        rename_label = QLabel("New Name:")
        rename_label.setProperty("formLabel", True)
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
            # Get the current project state
            state = self.window().project_manager.state_manager.project_state
            # Update the notes in the state
            state.settings["project_notes"] = notes
            # Update internal state and persist changes to disk
            self.window().project_manager.state_manager.notify_observers()
            self.window().project_manager.save_project()
            
            self.navigation_pane.add_log_message("Project notes saved successfully.", 'success')
        except Exception as e:
            error_msg = f"Error saving project notes: {e}"
            print(error_msg)
            self.navigation_pane.add_log_message(error_msg, 'error')

    def update_theme(self, theme):
        """Update theme for this view and propagate any view-specific changes."""
        super().update_theme(theme)
        self.navigation_pane.add_log_message(f"Theme updated to {theme}.", "info")

    def refresh_lists(self):
        """Refreshes lists managed by this view, primarily the project list."""
        self.navigation_pane.add_log_message("Refreshing ProjectView lists...", "info")
        self.populate_project_list()
        # Add other list refreshes here if needed in the future


        
   