from pathlib import Path
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox
)
from PySide6.QtCore import Qt


class ProjectSelectionDialog(QDialog):
    def __init__(self, project_manager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.setWindowTitle("Project Selection")
        self.setModal(True)
        self.resize(400, 200)

        # Base directory for projects
        self.base_dir = Path("projects")
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

        layout = QVBoxLayout(self)

        instruction = QLabel("Select an existing project or create a new one:")
        layout.addWidget(instruction)

        # Combo box for existing projects
        self.project_combo = QComboBox(self)
        self.refresh_project_list()
        layout.addWidget(self.project_combo)

        # Layout for buttons
        button_layout = QHBoxLayout()
        self.open_button = QPushButton("Open Project", self)
        self.new_button = QPushButton("New Project", self)
        self.cancel_button = QPushButton("Cancel", self)
        button_layout.addWidget(self.open_button)
        button_layout.addWidget(self.new_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Input for new project name
        self.new_project_line = QLineEdit(self)
        self.new_project_line.setPlaceholderText("Enter new project name")
        layout.addWidget(self.new_project_line)

        # Connect signals
        self.open_button.clicked.connect(self.open_project)
        self.new_button.clicked.connect(self.create_project)
        self.cancel_button.clicked.connect(self.reject)

    def refresh_project_list(self):
        self.project_combo.clear()
        for path in self.project_manager.list_available_projects():
            self.project_combo.addItem(path.name)

    def open_project(self):
        selected = self.project_combo.currentText()
        if not selected:
            QMessageBox.warning(self, "Warning", "No project selected.")
            return
        # Use the project_manager's list of available projects to find the project directory
        available_projects = self.project_manager.list_available_projects()
        project_path = next((p for p in available_projects if p.name == selected), None)
        if project_path is None:
            QMessageBox.warning(self, "Warning", f"Project directory for '{selected}' not found.")
            return
        try:
            self.project_manager.load_project(project_path)
            # Store it in a property so the main window can read it
            self.selected_project_name = selected
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project: {e}")

    def create_project(self):
        name = self.new_project_line.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a project name.")
            return
        project_path = self.base_dir / name
        try:
            self.project_manager.create_project(project_path, name)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create project: {e}") 