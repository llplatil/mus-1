"""Main project view tab"""
from .base import BaseWidget
from PyQt5.QtWidgets import QPushButton, QFileDialog, QMessageBox
from pathlib import Path

class ProjectView(BaseWidget):
    def __init__(self, state_manager, project_manager, data_manager):
        super().__init__(state_manager, project_manager, data_manager)
        
    def setup_ui(self):
        """Project-level actions"""
        super().setup_ui()  # Gets mouse_combo from BaseWidget
        
        # Project management controls
        self.import_btn = QPushButton("Import Data")
        self.export_btn = QPushButton("Export Project")
        
        # Connect to ProjectManager
        self.import_btn.clicked.connect(self.handle_data_import)
        self.export_btn.clicked.connect(self.handle_project_export)


    def handle_data_import(self):
        """Handle DLC config import"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select DLC Config",
            "",
            "YAML Files (*.yaml *.yml)"
        )
        
        if path:
            try:
                self.project_manager.load_dlc_config(Path(path))
                QMessageBox.information(self, "Success", "DLC config loaded successfully")
            except Exception as e:
                self.logger.error(f"Config load failed: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to load config:\n{str(e)}") 