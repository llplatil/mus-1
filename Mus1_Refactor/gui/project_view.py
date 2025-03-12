from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit,
    QComboBox, QPushButton, QListWidget, QLabel, QFileDialog, QTextEdit
)
from pathlib import Path
from gui.base_view import BaseView


class ProjectView(BaseView):
    def __init__(self, parent=None):
        super().__init__(parent, view_name="project")
        # Setup navigation with new consolidated options
        self.setup_navigation(["Project Settings", "Body Parts", "Objects", "General Settings"])
        self.setup_body_parts_page()
        self.change_page(0)

        # Directly retrieve core managers from window
        self.project_manager = self.window().project_manager
        self.data_manager = self.window().data_manager
        self.state_manager = self.window().state_manager
        self.state_manager.subscribe(self.refresh_lists)

        from PySide6.QtWidgets import QComboBox
        self.switch_project_combo = QComboBox(self)  # Added to fix missing attribute error
        
        # Add missing attributes referenced in methods
        self.current_project_label = QLabel("Current Project: None")
        self.rename_line_edit = QLineEdit()
        self.project_notes_edit = QTextEdit()
        self.all_body_parts_list = QListWidget()
        self.current_objects_list = QListWidget()

    def setup_body_parts_page(self):
        """Initialize the user interface for managing body parts."""
        self.bodyparts_page = QGroupBox("Body Parts Management")
        page_layout = QVBoxLayout(self.bodyparts_page)

        # ----- Extraction Section -----
        extract_group = QGroupBox("Extract Body Parts")
        extract_layout = QHBoxLayout(extract_group)
        self.csv_path_input = QLineEdit()
        self.csv_path_input.setPlaceholderText("Enter CSV/YAML file path")
        self.extraction_method_dropdown = QComboBox()
        self.extraction_method_dropdown.addItems(["BasicCSV", "DLC yaml"])
        extract_button = QPushButton("Extract")
        extract_button.clicked.connect(self.handle_extract_bodyparts)
        extract_layout.addWidget(QLabel("File Path:"))
        extract_layout.addWidget(self.csv_path_input)
        extract_layout.addWidget(QLabel("Method:"))
        extract_layout.addWidget(self.extraction_method_dropdown)
        extract_layout.addWidget(extract_button)
        page_layout.addWidget(extract_group)

        # ----- Extracted Body Parts Display -----
        page_layout.addWidget(QLabel("Extracted Body Parts:"))
        self.extracted_bodyparts_list = QListWidget()
        page_layout.addWidget(self.extracted_bodyparts_list)

        # ----- Management Section -----
        management_group = QGroupBox("Manage Body Parts")
        mgmt_layout = QHBoxLayout(management_group)

        # Master body parts (all known)
        master_layout = QVBoxLayout()
        master_layout.addWidget(QLabel("Master Body Parts"))
        self.all_bodyparts_list = QListWidget()
        master_button_all = QPushButton("Add All to Master")
        master_button_selected = QPushButton("Add Selected to Master")
        master_button_all.clicked.connect(self.handle_add_all_bodyparts_to_master)
        master_button_selected.clicked.connect(self.handle_add_selected_bodyparts_to_master)
        master_layout.addWidget(self.all_bodyparts_list)
        master_layout.addWidget(master_button_all)
        master_layout.addWidget(master_button_selected)

        # Active body parts (currently in use)
        active_layout = QVBoxLayout()
        active_layout.addWidget(QLabel("Active Body Parts"))
        self.current_body_parts_list = QListWidget()
        active_button_add = QPushButton("Add Selected to Active")
        active_button_remove = QPushButton("Remove Selected")
        active_button_add.clicked.connect(self.handle_add_selected_bodyparts_to_active)
        active_button_remove.clicked.connect(self.handle_remove_active_bodyparts)
        active_layout.addWidget(self.current_body_parts_list)
        active_layout.addWidget(active_button_add)
        active_layout.addWidget(active_button_remove)

        mgmt_layout.addLayout(master_layout)
        mgmt_layout.addLayout(active_layout)
        page_layout.addWidget(management_group)

        # Add this page to the stacked widget from BaseView
        self.add_page(self.bodyparts_page, "Body Parts")

        # Initial refresh to populate lists
        self.refresh_lists()

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
                self.current_project_label.setText("Current Project: " + selected_project)
                self.rename_line_edit.setText(selected_project)
                state = self.window().project_manager.state_manager.project_state
                notes = state.settings.get("project_notes", "")
                self.project_notes_edit.setPlainText(notes)

                self.current_body_parts_list.clear()
                for bp in state.settings.get("body_parts", []):
                    self.current_body_parts_list.addItem(bp)
                self.all_body_parts_list.clear()
                if state.project_metadata and hasattr(state.project_metadata, "master_body_parts"):
                    for bp in state.project_metadata.master_body_parts:
                        self.all_body_parts_list.addItem(bp)

                self.current_objects_list.clear()
                for obj in state.settings.get("tracked_objects", []):
                    self.current_objects_list.addItem(obj)

                self.navigation_pane.add_log_message(f"Successfully switched to project: {selected_project}", 'success')
                self.refresh_lists()
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

   