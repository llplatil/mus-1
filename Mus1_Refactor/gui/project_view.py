from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QCheckBox, QSpinBox, QPushButton, QHBoxLayout, QComboBox

class ProjectView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)

        # Title label
        title_label = QLabel("Project Settings")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title_label)

        # Project Management Group: for switching and renaming projects
        project_management_group = QGroupBox("Project Management")
        pm_layout = QFormLayout()

        # Row 1: Switch Project (dropdown and button)
        self.switch_project_combo = QComboBox()
        self.populate_project_list()
        self.switch_project_button = QPushButton("Switch Project")
        switch_layout = QHBoxLayout()
        switch_layout.addWidget(self.switch_project_combo)
        switch_layout.addWidget(self.switch_project_button)
        pm_layout.addRow("Switch Project:", switch_layout)

        # Row 2: Rename Project (line edit prepopulated with current project name and a rename button)
        self.rename_line_edit = QLineEdit()
        # Attempt to get current project name from parent's project_manager if available
        if self.parent() and hasattr(self.parent(), 'project_manager') and self.parent().project_manager.state_manager.project_state and self.parent().project_manager.state_manager.project_state.project_metadata:
            current_name = self.parent().project_manager.state_manager.project_state.project_metadata.project_name
            self.rename_line_edit.setText(current_name)
        self.rename_project_button = QPushButton("Rename Project")
        rename_layout = QHBoxLayout()
        rename_layout.addWidget(self.rename_line_edit)
        rename_layout.addWidget(self.rename_project_button)
        pm_layout.addRow("Rename Project:", rename_layout)

        project_management_group.setLayout(pm_layout)
        main_layout.addWidget(project_management_group)

        # Connect signals for project management
        self.switch_project_button.clicked.connect(self.handle_switch_project)
        self.rename_project_button.clicked.connect(self.handle_rename_project)

        # Group box for general settings
        settings_group = QGroupBox("General Settings")
        settings_layout = QFormLayout()

        # Project Name input
        project_name_edit = QLineEdit()
        project_name_edit.setPlaceholderText("Enter project name")
        settings_layout.addRow("Project Name:", project_name_edit)

        # Global Frame Rate input using a spin box
        frame_rate_spin = QSpinBox()
        frame_rate_spin.setRange(1, 240)
        frame_rate_spin.setValue(60)
        settings_layout.addRow("Global Frame Rate:", frame_rate_spin)

        # Likelihood Filter switch (using a check box as a toggle)
        likelihood_filter_checkbox = QCheckBox("Enable Likelihood Filter")
        settings_layout.addRow(likelihood_filter_checkbox)

        # Body Parts input (comma-separated values)
        body_parts_edit = QLineEdit()
        body_parts_edit.setPlaceholderText("e.g., head, tail, left_paw, right_paw")
        settings_layout.addRow("Body Parts:", body_parts_edit)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # Buttons for actions
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save Settings")
        cancel_button = QPushButton("Cancel")
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

        main_layout.addStretch()

        # Connect button signals
        save_button.clicked.connect(self.handle_save)
        cancel_button.clicked.connect(self.handle_cancel)

        # Store widget references for later use
        self.project_name_edit = project_name_edit
        self.frame_rate_spin = frame_rate_spin
        self.likelihood_filter_checkbox = likelihood_filter_checkbox
        self.body_parts_edit = body_parts_edit

    def handle_save(self):
        # Retrieve current settings from input widgets (ignoring the general Project Name field for renaming,
        # as renaming is done in the Project Management section)
        frame_rate = self.frame_rate_spin.value()
        likelihood_enabled = self.likelihood_filter_checkbox.isChecked()
        body_parts_str = self.body_parts_edit.text().strip()
        body_parts_list = [bp.strip() for bp in body_parts_str.split(",") if bp.strip()]

        # Update the core project state via project_manager
        pm = self.parent().project_manager
        state = pm.state_manager.project_state
        state.settings["global_frame_rate"] = frame_rate
        state.settings["body_parts"] = body_parts_list
        state.likelihood_filter_enabled = likelihood_enabled

        print("Saving Project Settings:")
        print("Global Frame Rate:", frame_rate)
        print("Likelihood Filter Enabled:", likelihood_enabled)
        print("Body Parts:", body_parts_list)

        # Persist changes to disk
        pm.save_project()

    def handle_cancel(self):
        # Reset the UI input fields to reflect the current project state
        pm = self.parent().project_manager
        state = pm.state_manager.project_state

        # For the general settings Project Name field, use the project_metadata if available
        if state.project_metadata and state.project_metadata.project_name:
            self.project_name_edit.setText(state.project_metadata.project_name)
        else:
            self.project_name_edit.clear()

        self.frame_rate_spin.setValue(state.settings.get("global_frame_rate", 60))
        self.likelihood_filter_checkbox.setChecked(state.likelihood_filter_enabled)
        body_parts = state.settings.get("body_parts", [])
        if isinstance(body_parts, list):
            self.body_parts_edit.setText(", ".join(body_parts))
        else:
            self.body_parts_edit.clear()

        print("Cancelled changes. Reset UI to current project state.")

    def populate_project_list(self):
        from pathlib import Path
        projects_dir = Path("projects")
        if not projects_dir.exists():
            projects_dir.mkdir(parents=True, exist_ok=True)
        self.switch_project_combo.clear()
        for item in projects_dir.iterdir():
            if item.is_dir() and (item / "project_state.json").exists():
                self.switch_project_combo.addItem(item.name)

    def handle_switch_project(self):
        from pathlib import Path
        selected_project = self.switch_project_combo.currentText()
        if selected_project:
            projects_dir = Path("projects")
            project_path = projects_dir / selected_project
            try:
                # Call parent's project_manager to load the selected project
                self.parent().project_manager.load_project(project_path)
                # Update the rename field with the new project name
                self.rename_line_edit.setText(selected_project)
                print("Switched to project:", selected_project)
            except Exception as e:
                print("Error switching project:", e)
        else:
            print("No project selected to switch.")

    def handle_rename_project(self):
        new_name = self.rename_line_edit.text().strip()
        if new_name:
            try:
                self.parent().project_manager.rename_project(new_name)
                print("Project renamed to:", new_name)
                self.populate_project_list()
            except Exception as e:
                print("Error renaming project:", e)
        else:
            print("New project name cannot be empty.")
        
   
        
   