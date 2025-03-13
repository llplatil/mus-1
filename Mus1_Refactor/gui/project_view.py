from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit,
    QComboBox, QPushButton, QListWidget, QLabel, QFileDialog, QTextEdit,
    QCheckBox, QSpinBox, QDoubleSpinBox
)
from pathlib import Path
from gui.base_view import BaseView


class NotesBox(QGroupBox):
    """A reusable notes component that can be added to any view."""
    def __init__(self, parent=None, title="Notes", placeholder_text="Enter notes here...", max_height=None):
        super().__init__(title, parent)
        self.setProperty("class", "mus1-notes-container")
        
        # Set up the layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(10)
        
        # Title label (optional)
        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "mus1-notes-title")
        # Ensure transparent background
        self.title_label.setProperty("formLabel", True) 
        
        # Create the text edit for notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setProperty("class", "mus1-notes-edit")
        self.notes_edit.setPlaceholderText(placeholder_text)
        
        if max_height:
            self.notes_edit.setMaximumHeight(max_height)
        else:
            self.notes_edit.setMinimumHeight(120)
        
        # Add save button
        self.save_button = QPushButton("Save Notes")
        self.save_button.setProperty("class", "mus1-notes-save-button")
        
        # Add widgets to layout
        layout.addWidget(self.notes_edit)
        layout.addWidget(self.save_button)
    
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
    def __init__(self, parent=None):
        super().__init__(parent, view_name="project")
        self.setup_navigation(["Project Settings", "Body Parts", "Objects", "General Settings"])
        self.setup_project_settings_page()
        self.setup_body_parts_page()
        self.setup_objects_page()
        self.setup_general_settings_page()
        self.change_page(0)

        # Retrieve core managers from window
        self.project_manager = self.window().project_manager
        self.data_manager = self.window().data_manager
        self.state_manager = self.window().state_manager
        self.state_manager.subscribe(self.refresh_lists)

    def setup_body_parts_page(self):
        """Initialize the user interface for managing body parts."""
        # Create the page widget without redundant styling
        self.bodyparts_page = QWidget()
        layout = QVBoxLayout(self.bodyparts_page)
        layout.setSpacing(15)

        # ----- Extraction Section -----
        extract_group = QGroupBox("Extract Body Parts")
        extract_group.setProperty("class", "mus1-input-group")
        extract_layout = QHBoxLayout(extract_group)
        
        self.csv_path_input = QLineEdit()
        self.csv_path_input.setPlaceholderText("Enter CSV/YAML file path")
        self.csv_path_input.setProperty("class", "mus1-text-input")
        
        browse_button = QPushButton("Browse...")
        browse_button.setProperty("class", "mus1-secondary-button")
        browse_button.clicked.connect(self.handle_browse_for_bodyparts_file)
        
        self.extraction_method_dropdown = QComboBox()
        self.extraction_method_dropdown.setProperty("class", "mus1-combo-box")
        self.extraction_method_dropdown.addItems(["BasicCSV", "DLC yaml"])
        
        extract_button = QPushButton("Extract")
        extract_button.setProperty("class", "mus1-primary-button")
        extract_button.clicked.connect(self.handle_extract_bodyparts)
        
        file_path_label = QLabel("File Path:")
        file_path_label.setProperty("formLabel", True)
        method_label = QLabel("Method:")
        method_label.setProperty("formLabel", True)
        
        extract_layout.addWidget(file_path_label)
        extract_layout.addWidget(self.csv_path_input, 1)
        extract_layout.addWidget(browse_button)
        extract_layout.addWidget(method_label)
        extract_layout.addWidget(self.extraction_method_dropdown)
        extract_layout.addWidget(extract_button)
        
        layout.addWidget(extract_group)

        # ----- Extracted Body Parts Display -----
        extracted_group = QGroupBox("Extracted Body Parts")
        extracted_group.setProperty("class", "mus1-input-group")
        extracted_layout = QVBoxLayout(extracted_group)
        
        self.extracted_bodyparts_list = QListWidget()
        self.extracted_bodyparts_list.setProperty("class", "mus1-list-widget")
        self.extracted_bodyparts_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        # Buttons for adding to master list
        buttons_layout = QHBoxLayout()
        master_button_all = QPushButton("Add All to Master")
        master_button_all.setProperty("class", "mus1-primary-button")
        master_button_all.clicked.connect(self.handle_add_all_bodyparts_to_master)
        
        master_button_selected = QPushButton("Add Selected to Master")
        master_button_selected.setProperty("class", "mus1-secondary-button")
        master_button_selected.clicked.connect(self.handle_add_selected_bodyparts_to_master)
        
        buttons_layout.addWidget(master_button_all)
        buttons_layout.addWidget(master_button_selected)
        
        extracted_layout.addWidget(self.extracted_bodyparts_list)
        extracted_layout.addLayout(buttons_layout)
        
        layout.addWidget(extracted_group)

        # ----- Management Section -----
        management_group = QGroupBox("Manage Body Parts")
        management_group.setProperty("class", "mus1-input-group")
        management_layout = QHBoxLayout(management_group)
        
        # Master body parts (all known)
        master_layout = QVBoxLayout()
        master_label = QLabel("Master Body Parts")
        master_label.setProperty("class", "mus1-section-label")
        master_label.setProperty("formLabel", True)
        master_layout.addWidget(master_label)
        
        self.all_bodyparts_list = QListWidget()
        self.all_bodyparts_list.setProperty("class", "mus1-list-widget")
        self.all_bodyparts_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        add_to_active_button = QPushButton("Add Selected to Active →")
        add_to_active_button.setProperty("class", "mus1-secondary-button")
        add_to_active_button.clicked.connect(self.handle_add_selected_bodyparts_to_active)
        
        master_layout.addWidget(self.all_bodyparts_list)
        master_layout.addWidget(add_to_active_button)
        
        # Active body parts (currently in use)
        active_layout = QVBoxLayout()
        active_label = QLabel("Active Body Parts")
        active_label.setProperty("class", "mus1-section-label")
        active_label.setProperty("formLabel", True)
        active_layout.addWidget(active_label)
        
        self.current_body_parts_list = QListWidget()
        self.current_body_parts_list.setProperty("class", "mus1-list-widget")
        self.current_body_parts_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        remove_button = QPushButton("← Remove Selected")
        remove_button.setProperty("class", "mus1-secondary-button")
        remove_button.clicked.connect(self.handle_remove_active_bodyparts)
        
        active_layout.addWidget(self.current_body_parts_list)
        active_layout.addWidget(remove_button)
        
        management_layout.addLayout(master_layout)
        management_layout.addLayout(active_layout)
        
        layout.addWidget(management_group)
        
        # Add a stretch to push everything to the top
        layout.addStretch(1)
        
        # Add this page to the stacked widget from BaseView
        self.add_page(self.bodyparts_page, "Body Parts")
        
        # Initial refresh to populate lists
        self.refresh_lists()
        
    def handle_browse_for_bodyparts_file(self):
        """Open a file dialog to select a CSV or YAML file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Body Parts File",
            "",
            "CSV Files (*.csv);;YAML Files (*.yaml *.yml);;All Files (*)"
        )
        if file_path:
            self.csv_path_input.setText(file_path)
            
    def handle_extract_bodyparts(self):
        """Extract body parts from the specified file using DataManager."""
        try:
            file_path = Path(self.csv_path_input.text().strip())
            method = self.extraction_method_dropdown.currentText()
            if not file_path.exists():
                self.navigation_pane.add_log_message("File does not exist.", "error")
                return
            if method == "BasicCSV":
                extracted = self.window().data_manager.extract_bodyparts_from_dlc_csv(file_path)
            elif method == "DLC yaml":
                extracted = self.window().data_manager.extract_bodyparts_from_dlc_config(file_path)
            else:
                self.navigation_pane.add_log_message("Unknown extraction method.", "error")
                return
            self.extracted_bodyparts_list.clear()
            for bp in extracted:
                self.extracted_bodyparts_list.addItem(str(bp))
            self.navigation_pane.add_log_message(f"Extracted {len(extracted)} body parts.", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Extraction error: {e}", "error")

    def handle_add_all_bodyparts_to_master(self):
        """Add every extracted body part to the master list."""
        bodyparts = [self.extracted_bodyparts_list.item(i).text() for i in range(self.extracted_bodyparts_list.count())]
        self.window().project_manager.update_master_body_parts(bodyparts)
        self.navigation_pane.add_log_message(f"Added all {len(bodyparts)} body parts to master list.", "success")
        self.refresh_lists()

    def handle_add_selected_bodyparts_to_master(self):
        """Add selected extracted body parts to the master list."""
        selected_items = self.extracted_bodyparts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for master list.", "warning")
            return
        bodyparts = [item.text() for item in selected_items]
        self.window().project_manager.update_master_body_parts(bodyparts)
        self.navigation_pane.add_log_message(f"Added {len(bodyparts)} selected body parts to master list.", "success")
        self.refresh_lists()

    def handle_add_selected_bodyparts_to_active(self):
        """Add selected body parts from the master list into the active list."""
        selected_items = self.all_bodyparts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for active list.", "warning")
            return
        selected = [item.text() for item in selected_items]
        current = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
        updated = current + [bp for bp in selected if bp not in current]
        self.window().project_manager.update_active_body_parts(updated)
        self.navigation_pane.add_log_message(f"Added {len(selected)} body parts to active list.", "success")
        self.refresh_lists()

    def handle_remove_active_bodyparts(self):
        """Remove selected body parts from the active list."""
        selected_items = self.current_body_parts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for removal.", "warning")
            return
        current = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
        to_remove = [item.text() for item in selected_items]
        updated = [bp for bp in current if bp not in to_remove]
        self.window().project_manager.update_active_body_parts(updated)
        self.navigation_pane.add_log_message(f"Removed {len(to_remove)} body parts from active list.", "success")
        self.refresh_lists()

    def refresh_lists(self):
        """Refresh the master and active lists from the current state."""
        state = self.window().state_manager.project_state
        if state.project_metadata:
            master = state.project_metadata.master_body_parts
            active = state.project_metadata.active_body_parts
        else:
            master = self.window().state_manager.global_settings.get("body_parts", [])
            active = self.window().state_manager.global_settings.get("active_body_parts", [])
        self.all_bodyparts_list.clear()
        for bp in master:
            self.all_bodyparts_list.addItem(bp.name if hasattr(bp, "name") else str(bp))
        self.current_body_parts_list.clear()
        for bp in active:
            self.current_body_parts_list.addItem(bp.name if hasattr(bp, "name") else str(bp))
        self.navigation_pane.add_log_message("Body parts lists refreshed.", "info")

    def update_theme(self, theme):
        """Update theme for this view and propagate any view–specific changes."""
        super().update_theme(theme)
        self.navigation_pane.add_log_message(f"Theme updated to {theme}.", "info")
   

    def handle_add_object(self):
        if not hasattr(self, '_state_manager'):
            return
        state = self._state_manager.project_state
        new_obj = self.new_object_line_edit.text().strip()
        if not new_obj:
            msg = "No object name entered."
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')
            return
        
        pm = self.window().project_manager
        tracked_objects = state.settings.get("tracked_objects", [])
        
        # Check for duplicates by name
        existing_object_names = []
        for obj in tracked_objects:
            if hasattr(obj, 'name'):
                existing_object_names.append(obj.name)
            else:
                existing_object_names.append(str(obj))
        
        if new_obj in existing_object_names:
            msg = f"Object '{new_obj}' already exists in tracked objects."
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')
            return
        
        # Add the new object
        tracked_objects.append(new_obj)
        pm.update_tracked_objects(tracked_objects)
        self.new_object_line_edit.clear()
        self.navigation_pane.add_log_message(f"Added new object: {new_obj}", 'success')
        
        # Refresh the UI
        self.refresh_lists()

    def handle_add_to_active_objects(self):
        """Handle adding selected objects to the active objects list."""
        selected_items = self.all_objects_list.selectedItems()
        if not selected_items:
            msg = "No objects selected to add."
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')
            return
        
        pm = self.window().project_manager
        state = self.window().project_manager.state_manager.project_state
        current_active = [obj for obj in state.settings.get("tracked_objects", []) 
                         if hasattr(obj, 'name') and obj.name or str(obj)]
        
        selected = [item.text() for item in selected_items]
        new_active = list(set(current_active + selected))
        
        pm.update_tracked_objects(new_active)
        self.navigation_pane.add_log_message(f"Added {len(selected)} objects to active list", 'success')
        self.refresh_lists()
    

    def handle_remove_object(self):
        selected_items = self.current_objects_list.selectedItems()
        if not selected_items:
            msg = "No objects selected for removal."
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')
            return
        pm = self.window().project_manager
        state = self.window().project_manager.state_manager.project_state
        tracked_objects = state.settings.get("tracked_objects", [])
        to_remove = [item.text() for item in selected_items]
        new_objects = [obj for obj in tracked_objects if obj not in to_remove]
        pm.update_tracked_objects(new_objects)
        self.navigation_pane.add_log_message(f"Removed {len(to_remove)} object(s) from tracked objects", 'success')
        self.refresh_lists()

    def handle_save_objects(self):
        new_objects = [self.current_objects_list.item(i).text() for i in range(self.current_objects_list.count())]
        self.window().project_manager.update_tracked_objects(new_objects)
        print("Saved objects only. (Entire project not fully re-saved.)")
        self.refresh_lists()

    def set_initial_project(self, project_name: str):
        self.populate_project_list()
        index = self.switch_project_combo.findText(project_name)
        if index >= 0:
            self.switch_project_combo.setCurrentIndex(index)
            self.handle_switch_project()
        else:
            print(f"Project '{project_name}' was not found in combo box; selection unchanged.")

    def on_sort_mode_changed(self):
        new_sort_mode = self.sort_mode_dropdown.currentText()
        # Update the project state's global_sort_mode if project_manager is accessible via parent
        if self.parent() and hasattr(self.parent(), 'project_manager'):
            self.parent().project_manager.state_manager.project_state.settings["global_sort_mode"] = new_sort_mode
            # Refresh lists to reflect new sorting
            self.parent().project_manager.refresh_all_lists()
        
    def closeEvent(self, event):
        """Handle clean up when the view is closed."""
        # Unsubscribe from state manager to prevent memory leaks
        if hasattr(self, '_state_manager'):
            self._state_manager.unsubscribe(self.refresh_lists)
        super().closeEvent(event)

    def handle_change_theme(self, theme_choice: str):
        """
        UI handler for theme change requests, delegates actual change to MainWindow.
        """
        main_window = self.window()
        if main_window:
            main_window.change_theme(theme_choice)

    def update_frame_rate_from_state(self):
        """Update frame rate settings from the current state."""
        if not hasattr(self, '_state_manager'):
            return
            
        # Get frame rate directly from state manager's global settings
        frame_rate = self._state_manager.global_settings.get("global_frame_rate", 60)
        frame_rate_enabled = self._state_manager.global_settings.get("global_frame_rate_enabled", True)
            
        # Update UI components
        if hasattr(self, 'frame_rate_spin'):
            self.frame_rate_spin.setValue(frame_rate)
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

    def update_objects_from_state(self):
        """Update objects list from the current state."""
        pm = self.window().project_manager
        if not pm or not pm.state_manager:
            return
        
        if not hasattr(self, '_state_manager'):
            return
        state = self._state_manager.project_state
        
        # Clear existing lists - if they exist
        if hasattr(self, 'all_objects_list'):
            self.all_objects_list.clear()
        
        if hasattr(self, 'current_objects_list'):
            self.current_objects_list.clear()
        
        # Get tracked objects from state
        tracked_objects = []
        if state.project_metadata and hasattr(state.project_metadata, 'tracked_objects'):
            tracked_objects = state.project_metadata.tracked_objects
        else:
            tracked_objects = state.settings.get('tracked_objects', [])
        
        # Update the lists
        if hasattr(self, 'current_objects_list') and isinstance(tracked_objects, list):
            for obj in tracked_objects:
                obj_name = obj if isinstance(obj, str) else obj.name if hasattr(obj, 'name') else str(obj)
                self.current_objects_list.addItem(obj_name)
        
        # Update all objects list - these might be the same in current implementation
        if hasattr(self, 'all_objects_list') and isinstance(tracked_objects, list):
            for obj in tracked_objects:
                obj_name = obj if isinstance(obj, str) else obj.name if hasattr(obj, 'name') else str(obj)
                self.all_objects_list.addItem(obj_name)
    
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
        self.switch_project_combo.clear()
        for path in self.window().project_manager.list_available_projects():
            self.switch_project_combo.addItem(path.name)

    def handle_switch_project(self):
        selected_project = self.switch_project_combo.currentText()
        if selected_project:
            # Use the project_manager's list of available projects instead of building the path manually
            available_projects = self.window().project_manager.list_available_projects()
            project_path = next((p for p in available_projects if p.name == selected_project), None)
            if project_path is None:
                error_msg = f"Project directory for '{selected_project}' not found."
                print(error_msg)
                self.navigation_pane.add_log_message(error_msg, 'error')
                return
            try:
                self.navigation_pane.add_log_message(f"Switching to project: {selected_project}", 'info')
                self.window().project_manager.load_project(project_path)
                
                # Update UI elements with project data
                self.current_project_label.setText("Current Project: " + selected_project)
                self.rename_line_edit.setText(selected_project)
                
                # Get the project state
                state = self.window().project_manager.state_manager.project_state
                
                # Load notes from state - only project notes now
                self.project_notes_box.set_text(state.settings.get("project_notes", ""))
                
                # Update all lists
                self.refresh_lists()
                
                self.navigation_pane.add_log_message(f"Successfully switched to project: {selected_project}", 'success')
            except Exception as e:
                error_msg = f"Error switching project: {e}"
                print(error_msg)
                self.navigation_pane.add_log_message(error_msg, 'error')
        else:
            msg = "No project selected to switch."
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')

    def handle_rename_project(self):
        new_name = self.rename_line_edit.text().strip()
        if new_name:
            try:
                self.navigation_pane.add_log_message(f"Renaming project to: {new_name}", 'info')
                self.window().project_manager.rename_project(new_name)
                self.navigation_pane.add_log_message(f"Project successfully renamed to: {new_name}", 'success')
                self.populate_project_list()
            except Exception as e:
                error_msg = f"Error renaming project: {e}"
                print(error_msg)
                self.navigation_pane.add_log_message(error_msg, 'error')
        else:
            msg = "New project name cannot be empty."
            print(msg)
            self.navigation_pane.add_log_message(msg, 'warning')

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
        
        # Project selector
        selector_layout = QHBoxLayout()
        select_label = QLabel("Select Project:")
        select_label.setProperty("formLabel", True)
        
        self.switch_project_combo = QComboBox()
        self.switch_project_combo.setProperty("class", "mus1-combo-box")
        self.switch_project_button = QPushButton("Switch")
        self.switch_project_button.setProperty("class", "mus1-primary-button")
        self.switch_project_button.clicked.connect(self.handle_switch_project)
        
        selector_layout.addWidget(select_label)
        selector_layout.addWidget(self.switch_project_combo, 1)
        selector_layout.addWidget(self.switch_project_button)
        selection_layout.addLayout(selector_layout)
        
        # Current project display
        current_layout = QHBoxLayout()
        self.current_project_label = QLabel("Current Project: None")
        self.current_project_label.setProperty("formLabel", True)
        current_layout.addWidget(self.current_project_label)
        current_layout.addStretch(1)
        selection_layout.addLayout(current_layout)
        
        # Add selection group to main layout
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
        # Using a larger height to make better use of the space
        self.project_notes_box = NotesBox(
            title="Project Notes",
            placeholder_text="Enter project notes, details, and important information here...",
            max_height=300  # Increased height to use vertical space better
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
            # Update internal state without full project save
            self.window().project_manager.state_manager.notify_observers()
            
            self.navigation_pane.add_log_message("Project notes saved successfully.", 'success')
        except Exception as e:
            error_msg = f"Error saving project notes: {e}"
            print(error_msg)
            self.navigation_pane.add_log_message(error_msg, 'error')

    def setup_objects_page(self):
        """Setup the Objects page with object list widgets."""
        # Create the page widget without redundant styling
        self.objects_page = QWidget()
        layout = QVBoxLayout(self.objects_page)
        layout.setSpacing(15)

        # Create objects management group
        objects_group = QGroupBox("Objects Management")
        objects_group.setProperty("class", "mus1-input-group")
        objects_layout = QVBoxLayout(objects_group)
        
        # Add new object section
        add_layout = QHBoxLayout()
        self.new_object_line_edit = QLineEdit()
        self.new_object_line_edit.setProperty("class", "mus1-text-input")
        self.new_object_line_edit.setPlaceholderText("Enter new object name...")
        
        add_button = QPushButton("Add Object")
        add_button.setProperty("class", "mus1-primary-button")
        add_button.clicked.connect(self.handle_add_object)
        
        new_object_label = QLabel("New Object:")
        new_object_label.setProperty("formLabel", True)
        
        add_layout.addWidget(new_object_label)
        add_layout.addWidget(self.new_object_line_edit, 1)
        add_layout.addWidget(add_button)
        
        objects_layout.addLayout(add_layout)
        
        # Object lists section in a horizontal layout
        lists_layout = QHBoxLayout()
        
        # Available objects list
        available_layout = QVBoxLayout()
        available_label = QLabel("Available Objects:")
        available_label.setProperty("class", "mus1-section-label")
        available_label.setProperty("formLabel", True)
        
        self.all_objects_list = QListWidget()
        self.all_objects_list.setProperty("class", "mus1-list-widget")
        self.all_objects_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        add_to_active_button = QPushButton("Add Selected to Active →")
        add_to_active_button.setProperty("class", "mus1-secondary-button")
        add_to_active_button.clicked.connect(self.handle_add_to_active_objects)
        
        available_layout.addWidget(available_label)
        available_layout.addWidget(self.all_objects_list)
        available_layout.addWidget(add_to_active_button)
        
        # Current objects list
        current_layout = QVBoxLayout()
        current_label = QLabel("Active Objects:")
        current_label.setProperty("class", "mus1-section-label")
        current_label.setProperty("formLabel", True)
        
        self.current_objects_list = QListWidget()
        self.current_objects_list.setProperty("class", "mus1-list-widget")
        self.current_objects_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        remove_button = QPushButton("← Remove Selected")
        remove_button.setProperty("class", "mus1-secondary-button")
        remove_button.clicked.connect(self.handle_remove_object)
        
        current_layout.addWidget(current_label)
        current_layout.addWidget(self.current_objects_list)
        current_layout.addWidget(remove_button)
        
        # Add the list layouts to the horizontal layout
        lists_layout.addLayout(available_layout)
        lists_layout.addLayout(current_layout)
        
        objects_layout.addLayout(lists_layout)
        
        # Save button for objects
        save_button = QPushButton("Save Objects")
        save_button.setProperty("class", "mus1-primary-button")
        save_button.clicked.connect(self.handle_save_objects)
        
        objects_layout.addWidget(save_button)
        
        # Add the objects group to the main layout
        layout.addWidget(objects_group)
        
        # Add a stretch to push everything to the top
        layout.addStretch(1)
        
        # Add the page to the stacked widget
        self.add_page(self.objects_page, "Objects")

    def setup_general_settings_page(self):
        """Setup the General Settings page with application-wide settings."""
        # Create the page widget without redundant styling
        self.general_settings_page = QWidget()
        layout = QVBoxLayout(self.general_settings_page)
        layout.setSpacing(15)

        # Display preferences group
        display_group = QGroupBox("Display Preferences")
        display_group.setProperty("class", "mus1-input-group")
        display_layout = QVBoxLayout(display_group)
        
        # Theme selection
        theme_layout = QHBoxLayout()
        theme_label = QLabel("Application Theme:")
        theme_label.setProperty("formLabel", True)
        theme_layout.addWidget(theme_label)
        
        self.theme_dropdown = QComboBox()
        self.theme_dropdown.setProperty("class", "mus1-combo-box")
        self.theme_dropdown.addItems(["dark", "light", "os"])
        
        theme_button = QPushButton("Apply Theme")
        theme_button.setProperty("class", "mus1-primary-button")
        theme_button.clicked.connect(lambda: self.handle_change_theme(self.theme_dropdown.currentText()))
        
        theme_layout.addWidget(self.theme_dropdown, 1)
        theme_layout.addWidget(theme_button)
        display_layout.addLayout(theme_layout)
        
        # Sort mode selection
        sort_layout = QHBoxLayout()
        sort_label = QLabel("Global Sort Mode:")
        sort_label.setProperty("formLabel", True)
        sort_layout.addWidget(sort_label)
        
        self.sort_mode_dropdown = QComboBox()
        self.sort_mode_dropdown.setProperty("class", "mus1-combo-box")
        self.sort_mode_dropdown.addItems([
            "Natural Order (Numbers as Numbers)",
            "Alphabetical",
            "By Creation Date",
            "By ID"
        ])
        self.sort_mode_dropdown.currentTextChanged.connect(self.on_sort_mode_changed)
        
        sort_layout.addWidget(self.sort_mode_dropdown, 1)
        display_layout.addLayout(sort_layout)
        
        # Frame rate settings
        frame_rate_layout = QHBoxLayout()
        
        self.enable_frame_rate_checkbox = QCheckBox("Enable Frame Rate Limit")
        self.enable_frame_rate_checkbox.setChecked(True)
        
        frame_rate_layout.addWidget(self.enable_frame_rate_checkbox)
        
        frame_rate_label = QLabel("Frame Rate:")
        frame_rate_label.setProperty("formLabel", True)
        frame_rate_layout.addWidget(frame_rate_label)
        
        self.frame_rate_spin = QSpinBox()
        self.frame_rate_spin.setRange(1, 120)
        self.frame_rate_spin.setValue(60)
        self.frame_rate_spin.setProperty("class", "mus1-text-input")
        
        frame_rate_layout.addWidget(self.frame_rate_spin)
        frame_rate_layout.addStretch(1)
        
        display_layout.addLayout(frame_rate_layout)
        
        # Add display group to main layout
        layout.addWidget(display_group)
        
        # Data preferences group
        data_group = QGroupBox("Data Preferences")
        data_group.setProperty("class", "mus1-input-group")
        data_layout = QVBoxLayout(data_group)
        
        # Likelihood filter
        likelihood_layout = QHBoxLayout()
        likelihood_label = QLabel("Likelihood Filter Threshold:")
        likelihood_label.setProperty("formLabel", True)
        likelihood_layout.addWidget(likelihood_label)
        
        self.likelihood_filter_spin = QDoubleSpinBox()
        self.likelihood_filter_spin.setRange(0.0, 1.0)
        self.likelihood_filter_spin.setValue(0.5)
        self.likelihood_filter_spin.setSingleStep(0.05)
        self.likelihood_filter_spin.setProperty("class", "mus1-text-input")
        
        likelihood_layout.addWidget(self.likelihood_filter_spin)
        likelihood_layout.addStretch(1)
        
        data_layout.addLayout(likelihood_layout)
        
        # Add data group to main layout
        layout.addWidget(data_group)
        
        # Add a stretch to push everything to the top
        layout.addStretch(1)
        
        # Add the page to the stacked widget
        self.add_page(self.general_settings_page, "General Settings")
        
        # Initialize settings from state
        self.update_frame_rate_from_state()
        self.update_likelihood_filter_from_state()
        self.update_sort_mode_from_state()
   