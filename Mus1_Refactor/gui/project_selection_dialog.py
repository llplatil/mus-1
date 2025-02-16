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
        # List directories in self.base_dir that contain a project_state.json
        for item in self.base_dir.iterdir():
            if item.is_dir() and (item / "project_state.json").exists():
                self.project_combo.addItem(item.name)

    def open_project(self):
        selected = self.project_combo.currentText()
        if not selected:
            QMessageBox.warning(self, "Warning", "No project selected.")
            return
        project_path = self.base_dir / selected
        try:
            self.project_manager.load_project(project_path)
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