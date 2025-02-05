"""Initial project setup dialog"""

from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, 
    QFileDialog, QMessageBox, QInputDialog, QComboBox, QLineEdit
)
from ...utils.logging_config import get_class_logger
from ...core.project_manager import ProjectManager

class StartupDialog(QDialog):
    """Dialog for creating new or opening existing projects"""
    
    def __init__(self, project_manager, state_manager, data_manager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.logger = get_class_logger(self.__class__)
        self.selected_path = None
        self.is_new_project = False
        
        self.setWindowTitle("MUS1 - Project Setup")
        self.setup_ui()

    def setup_ui(self):
        """Initialize dialog UI"""
        layout = QVBoxLayout()
        
        # Project name input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter project name")
        layout.addWidget(self.name_input)
        
        # Add projects dropdown
        self.projects_combo = QComboBox()
        self._populate_projects()
        layout.addWidget(self.projects_combo)
        
        # Create buttons
        new_project_btn = QPushButton("Create New Project")
        open_project_btn = QPushButton("Open Existing Project")
        
        # Connect buttons to handlers
        new_project_btn.clicked.connect(self.handle_new_project_creation)
        open_project_btn.clicked.connect(self.handle_project_open)
        
        # Add buttons to layout
        layout.addWidget(new_project_btn)
        layout.addWidget(open_project_btn)
        
        self.setLayout(layout)

    def _populate_projects(self):
        """Load valid projects into dropdown"""
        try:
            projects = self.project_manager.get_existing_projects()
            self.projects_combo.clear()
            for project in projects:
                self.projects_combo.addItem(project.name, project)
                
        except Exception as e:
            self.logger.error(f"Failed to load projects: {str(e)}")

    def handle_new_project_creation(self):
        """Handle UI flow for creating new project"""
        try:
            # Get project name from user
            project_name = self.name_input.text()
            
            if project_name:
                try:
                    # Delegate project creation to ProjectManager
                    project_path = self.project_manager.create_new_project(project_name)
                    
                    # Update dialog state
                    self.selected_path = project_path
                    self.is_new_project = True
                    self.accept()
                    
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to create project: {str(e)}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to handle project creation: {str(e)}")
            QMessageBox.critical(
                self,
                "Error", 
                f"Failed to handle project creation: {str(e)}"
            )

    def handle_project_open(self):
        """Use selected project from dropdown"""
        selected_path = self.projects_combo.currentData()
        if selected_path:
            try:
                self.project_manager.open_existing_project(selected_path)
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def get_result(self) -> tuple[Path | None, bool]:
        """
        Get dialog results
        Returns:
            Tuple of (selected_path, is_new_project)
            selected_path will be None if dialog was cancelled
        """
        return self.selected_path, self.is_new_project

        