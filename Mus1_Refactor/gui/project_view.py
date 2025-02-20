from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidget, QFormLayout, QLineEdit, QComboBox, QPushButton, QTextEdit, QSpinBox, QCheckBox, QLabel, QFileDialog, QAbstractItemView, QSizePolicy
from gui.navigation_pane import NavigationPane


class ProjectView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Main horizontal layout
        main_layout = QHBoxLayout(self)

        # Left navigation pane (using the new NavigationPane)
        self.navigation_pane = NavigationPane(self)
        self.navigation_pane.add_button("Current Project")
        self.navigation_pane.add_button("General Settings")
        self.navigation_pane.add_button("Body Parts")
        self.navigation_pane.add_button("Objects")
        self.navigation_pane.connect_button_group()
        self.navigation_pane.button_clicked.connect(self.changePage)
        main_layout.addWidget(self.navigation_pane)

        # Right area: contains a stacked widget for pages and a single "save all" button
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)

        # Stacked widget to hold different pages
        self.pages = QStackedWidget()

        # ----- Page: Current Project -----
        self.page_current_project = QWidget()
        cp_layout = QVBoxLayout(self.page_current_project)

        # Display current project label at the top
        self.current_project_label = QLabel("Current Project: None")
        cp_layout.addWidget(self.current_project_label)

        # Row: Switch Project (combo box and button)
        switch_project_layout = QHBoxLayout()
        switch_project_label = QLabel("Switch Project:")
        self.switch_project_combo = QComboBox()
        self.populate_project_list()
        self.switch_project_button = QPushButton("Switch Project")
        switch_project_layout.addWidget(switch_project_label)
        switch_project_layout.addWidget(self.switch_project_combo)
        switch_project_layout.addWidget(self.switch_project_button)
        cp_layout.addLayout(switch_project_layout)

        # Row: Rename Project (line edit and button)
        rename_layout = QHBoxLayout()
        rename_label = QLabel("Rename Project:")
        self.rename_line_edit = QLineEdit()
        if self.parent() and hasattr(self.parent(), 'project_manager') and \
           self.parent().project_manager.state_manager.project_state and \
           self.parent().project_manager.state_manager.project_state.project_metadata:
            current_name = self.parent().project_manager.state_manager.project_state.project_metadata.project_name
            self.rename_line_edit.setText(current_name)
        self.rename_project_button = QPushButton("Rename Project")
        rename_layout.addWidget(rename_label)
        rename_layout.addWidget(self.rename_line_edit)
        rename_layout.addWidget(self.rename_project_button)
        cp_layout.addLayout(rename_layout)

        # Row: Project Notes (multiline text edit)
        notes_label = QLabel("Project Notes:")
        self.project_notes_edit = QTextEdit()
        self.project_notes_edit.setPlaceholderText("Enter project notes here...")
        self.project_notes_edit.setMinimumHeight(150)
        self.project_notes_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cp_layout.addWidget(notes_label)
        cp_layout.addWidget(self.project_notes_edit)

        self.pages.addWidget(self.page_current_project)

        # ----- Page: General Settings -----
        self.page_general_settings = QWidget()
        gs_layout = QFormLayout(self.page_general_settings)
        self.frame_rate_spin = QSpinBox()
        self.frame_rate_spin.setRange(1, 240)
        self.frame_rate_spin.setValue(60)
        gs_layout.addRow("Global Frame Rate:", self.frame_rate_spin)
        self.enable_frame_rate_checkbox = QCheckBox("Enable Global Frame Rate")
        self.enable_frame_rate_checkbox.setChecked(True)
        self.enable_frame_rate_checkbox.toggled.connect(lambda checked: self.frame_rate_spin.setEnabled(checked))
        gs_layout.addRow("Global Frame Rate Enabled:", self.enable_frame_rate_checkbox)
        self.likelihood_filter_checkbox = QCheckBox("Enable Likelihood Filter")
        gs_layout.addRow(self.likelihood_filter_checkbox)
        self.sort_mode_combo = QComboBox()
        self.sort_mode_combo.addItem("Natural Order (Numbers as Numbers)")
        self.sort_mode_combo.addItem("Lexicographical Order (Numbers as Characters)")
        self.sort_mode_combo.addItem("Date Added")
        gs_layout.addRow("Global Sort Mode:", self.sort_mode_combo)
        self.sort_mode_combo.currentIndexChanged.connect(self.on_sort_mode_changed)
        self.pages.addWidget(self.page_general_settings)

        # ----- Page: Body Parts -----
        self.page_body_parts = QWidget()
        bp_layout = QVBoxLayout(self.page_body_parts)
        # Label and list for current body parts
        current_bp_label = QLabel("Current Body Parts:")
        self.current_body_parts_list = QListWidget()
        self.current_body_parts_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        bp_layout.addWidget(current_bp_label)
        bp_layout.addWidget(self.current_body_parts_list)

        # Label and list for all body parts in project
        all_bp_label = QLabel("All Body Parts in Project:")
        self.all_body_parts_list = QListWidget()
        self.all_body_parts_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        bp_layout.addWidget(all_bp_label)
        bp_layout.addWidget(self.all_body_parts_list)

        # Button to extract body parts from DLC config
        self.extract_bodyparts_button = QPushButton("Extract from DLC Config")
        bp_layout.addWidget(self.extract_bodyparts_button)

        # >>> NEW CODE: Buttons for refining master -> active body parts
        add_remove_layout = QHBoxLayout()
        self.add_to_active_button = QPushButton("Add Selected to Active ->")
        self.remove_from_active_button = QPushButton("<- Remove Selected from Active")
        add_remove_layout.addWidget(self.add_to_active_button)
        add_remove_layout.addWidget(self.remove_from_active_button)
        bp_layout.addLayout(add_remove_layout)

        self.save_body_parts_button = QPushButton("Save Body Parts Only")
        bp_layout.addWidget(self.save_body_parts_button)
        # <<< END NEW CODE

        self.pages.addWidget(self.page_body_parts)

        # ----- Page: Objects -----
        self.page_objects = QWidget()
        obj_layout = QVBoxLayout(self.page_objects)
        label_current_objects = QLabel("Current Objects:")
        self.current_objects_list = QListWidget()
        obj_layout.addWidget(label_current_objects)
        obj_layout.addWidget(self.current_objects_list)

        # Layout for adding new object
        add_obj_layout = QHBoxLayout()
        self.new_object_line_edit = QLineEdit()
        self.new_object_line_edit.setPlaceholderText("Enter new object name")
        self.add_object_button = QPushButton("Add Object")
        add_obj_layout.addWidget(self.new_object_line_edit)
        add_obj_layout.addWidget(self.add_object_button)
        obj_layout.addLayout(add_obj_layout)

        # >>> NEW CODE: Buttons for removing and saving object list changes
        remove_save_obj_layout = QHBoxLayout()
        self.remove_object_button = QPushButton("Remove Selected")
        self.save_objects_button = QPushButton("Save Objects Only")
        remove_save_obj_layout.addWidget(self.remove_object_button)
        remove_save_obj_layout.addWidget(self.save_objects_button)
        obj_layout.addLayout(remove_save_obj_layout)
        # <<< END NEW CODE

        self.pages.addWidget(self.page_objects)

        right_layout.addWidget(self.pages)

        # Action Buttons at the bottom (shared across all pages)
        buttons_layout = QHBoxLayout()
        self.save_all_button = QPushButton("Save All Project Changes")
        self.cancel_button = QPushButton("Cancel")
        buttons_layout.addWidget(self.save_all_button)
        buttons_layout.addWidget(self.cancel_button)
        right_layout.addLayout(buttons_layout)

        main_layout.addWidget(right_area)

        # Set default selection
        self.navigation_pane.set_button_checked(0)

        # Connect signals
        self.switch_project_button.clicked.connect(self.handle_switch_project)
        self.rename_project_button.clicked.connect(self.handle_rename_project)
        self.extract_bodyparts_button.clicked.connect(self.handle_extract_bodyparts)
        self.add_object_button.clicked.connect(self.handle_add_object)
        self.add_to_active_button.clicked.connect(self.handle_add_to_active)
        self.remove_from_active_button.clicked.connect(self.handle_remove_from_active)
        self.save_body_parts_button.clicked.connect(self.handle_save_body_parts)
        self.remove_object_button.clicked.connect(self.handle_remove_object)
        self.save_objects_button.clicked.connect(self.handle_save_objects)
        self.save_all_button.clicked.connect(self.handle_save_all)
        self.cancel_button.clicked.connect(self.handle_cancel)

    def changePage(self, index):
        self.pages.setCurrentIndex(index)

    def handle_extract_bodyparts(self):
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path
        # Open a file dialog to let the user select a DLC config YAML file
        config_file_path, _ = QFileDialog.getOpenFileName(self, "Select DLC Config", ".", "YAML Files (*.yaml *.yml)")
        if not config_file_path:
            print("No config file selected.")
            return

        try:
            # Extract body parts from the selected config file using DataManager
            extracted = self.window().data_manager.extract_bodyparts_from_dlc_config(Path(config_file_path))
            print("Extracted body parts:", extracted)

            # Update master body parts via ProjectManager core logic
            self.window().project_manager.update_master_body_parts(extracted)

            # Refresh the UI for 'All Body Parts in Project'
            state = self.window().project_manager.state_manager.project_state
            self.all_body_parts_list.clear()
            if state.project_metadata and hasattr(state.project_metadata, "master_body_parts"):
                for bp in state.project_metadata.master_body_parts:
                    self.all_body_parts_list.addItem(bp)

            print("Extraction complete. Updated master body parts:", state.project_metadata.master_body_parts)
        except Exception as e:
            print("Error extracting body parts:", e)

    def handle_save_all(self):
        """
        Gather data from all portions of the UI and save it all at once.
        """
        pm = self.window().project_manager
        state = pm.state_manager.project_state

        # --- Current Project & Notes ---
        project_notes = self.project_notes_edit.toPlainText().strip()

        # --- General Settings ---
        frame_rate = self.frame_rate_spin.value()
        likelihood_enabled = self.likelihood_filter_checkbox.isChecked()

        # --- Body Parts Page (active body parts) ---
        current_body_parts = []
        for i in range(self.current_body_parts_list.count()):
            current_body_parts.append(self.current_body_parts_list.item(i).text())

        # --- Objects Page (tracked objects) ---
        current_objects = []
        for i in range(self.current_objects_list.count()):
            current_objects.append(self.current_objects_list.item(i).text())

        # Store collected data in state
        state.settings["global_frame_rate"] = frame_rate
        state.settings["body_parts"] = current_body_parts
        state.settings["tracked_objects"] = current_objects
        state.settings["project_notes"] = project_notes
        state.settings["global_frame_rate_enabled"] = self.enable_frame_rate_checkbox.isChecked()
        state.settings["global_sort_mode"] = self.sort_mode_combo.currentText()
        state.likelihood_filter_enabled = likelihood_enabled

        print("Saving all project changes:")
        print("Global Frame Rate:", frame_rate)
        print("Global Frame Rate Enabled:", self.enable_frame_rate_checkbox.isChecked())
        print("Global Sort Mode:", self.sort_mode_combo.currentText())
        print("Likelihood Filter Enabled:", likelihood_enabled)
        print("Active Body Parts:", current_body_parts)
        print("Tracked Objects:", current_objects)
        print("Project Notes:", project_notes)

        # Persist to disk
        pm.save_project()
        print("All project changes have been saved successfully.")

    def handle_cancel(self):
        pm = self.window().project_manager
        state = pm.state_manager.project_state

        if state.project_metadata and state.project_metadata.project_name:
            self.rename_line_edit.setText(state.project_metadata.project_name)
        else:
            self.rename_line_edit.clear()

        notes = state.settings.get("project_notes", "")
        self.project_notes_edit.setPlainText(notes)

        self.frame_rate_spin.setValue(state.settings.get("global_frame_rate", 60))
        self.likelihood_filter_checkbox.setChecked(state.likelihood_filter_enabled)
        self.enable_frame_rate_checkbox.setChecked(state.settings.get("global_frame_rate_enabled", True))
        self.frame_rate_spin.setEnabled(state.settings.get("global_frame_rate_enabled", True))

        # Restore sort mode from state
        sort_mode = state.settings.get("global_sort_mode", "Natural Order (Numbers as Numbers)")
        index = self.sort_mode_combo.findText(sort_mode)
        if index >= 0:
            self.sort_mode_combo.setCurrentIndex(index)

        self.current_body_parts_list.clear()
        for bp in state.settings.get("body_parts", []):
            self.current_body_parts_list.addItem(bp)

        self.all_body_parts_list.clear()
        if state.project_metadata and hasattr(state.project_metadata, "master_body_parts"):
            for bp in state.project_metadata.master_body_parts:
                self.all_body_parts_list.addItem(bp)

        self.current_objects_list.clear()
        tracked_objects = state.settings.get("tracked_objects", [])
        if isinstance(tracked_objects, list):
            for obj in tracked_objects:
                self.current_objects_list.addItem(obj)

        print("Cancelled changes. Reset UI to current project state.")

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
                print(f"Project directory for '{selected_project}' not found.")
                return
            try:
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

                print("Switched to project:", selected_project)
            except Exception as e:
                print("Error switching project:", e)
        else:
            print("No project selected to switch.")

    def handle_rename_project(self):
        new_name = self.rename_line_edit.text().strip()
        if new_name:
            try:
                self.window().project_manager.rename_project(new_name)
                print("Project renamed to:", new_name)
                self.populate_project_list()
            except Exception as e:
                print("Error renaming project:", e)
        else:
            print("New project name cannot be empty.")

    def handle_add_object(self):
        new_obj = self.new_object_line_edit.text().strip()
        if not new_obj:
            print("No object name entered.")
            return
        try:
            self.window().project_manager.add_tracked_object(new_obj)
            self.current_objects_list.addItem(new_obj)
            self.new_object_line_edit.clear()
            print("Added new object:", new_obj)
        except Exception as e:
            print("Error adding object:", e)

    def handle_add_to_active(self):
        selected_items = self.all_body_parts_list.selectedItems()
        for item in selected_items:
            text = item.text()
            # Avoid duplicates in 'current_body_parts_list'
            existing_active = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
            if text not in existing_active:
                self.current_body_parts_list.addItem(text)
        print("Added selected body parts to the active list.")

    def handle_remove_from_active(self):
        selected_items = self.current_body_parts_list.selectedItems()
        for item in selected_items:
            self.current_body_parts_list.takeItem(self.current_body_parts_list.row(item))
        print("Removed selected body parts from the active list.")

    def handle_save_body_parts(self):
        # Gather current items in current_body_parts_list
        new_active = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
        # Call project_manager to update the active body parts
        self.window().project_manager.update_active_body_parts(new_active)
        print("Saved active body parts only. (Entire project not fully re-saved.)")

    def handle_remove_object(self):
        selected_items = self.current_objects_list.selectedItems()
        for item in selected_items:
            self.current_objects_list.takeItem(self.current_objects_list.row(item))
        print("Removed selected object(s) from current list.")

    def handle_save_objects(self):
        # Gather current items in current_objects_list
        new_objects = [self.current_objects_list.item(i).text() for i in range(self.current_objects_list.count())]
        # Update the project state with the new objects list
        self.window().project_manager.update_tracked_objects(new_objects)
        print("Saved objects only. (Entire project not fully re-saved.)")

    def set_initial_project(self, project_name: str):
        index = self.switch_project_combo.findText(project_name)
        if index >= 0:
            self.switch_project_combo.setCurrentIndex(index)
            self.handle_switch_project()
        else:
            print(f"Project '{project_name}' was not found in combo box; selection unchanged.")

    def on_sort_mode_changed(self):
        new_sort_mode = self.sort_mode_combo.currentText()
        # Update the project state's global_sort_mode if project_manager is accessible via parent
        if self.parent() and hasattr(self.parent(), 'project_manager'):
            self.parent().project_manager.state_manager.project_state.settings["global_sort_mode"] = new_sort_mode
            # Refresh lists to reflect new sorting
            self.parent().project_manager.refresh_all_lists()
        
   
        
   