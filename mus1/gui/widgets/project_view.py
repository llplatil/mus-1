"""Main project view tab for project creation and selection"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                              QPushButton, QLabel, QFileDialog,
                              QSpacerItem, QSizePolicy)
from PySide6.QtCore import Qt, Signal
from .base.base_widget import BaseWidget
from pathlib import Path

class ProjectView(BaseWidget):
    """Project management view"""
    
    # View state signals
    selection_mode_ready = Signal()  # Emitted when selection view is ready
    project_mode_ready = Signal()    # Emitted when project view is ready
    
    def __init__(self, parent=None, initial_mode="selection"):
        super().__init__(parent)
        self.logger.info(f"Initializing ProjectView in {initial_mode} mode")
        
        self._mode = initial_mode
        self._setup_mode()
        
    def _setup_mode(self):
        """Setup UI based on current mode"""
        if self._mode == "selection":
            self._setup_selection_mode()
        else:
            self._setup_project_mode()
            
    def _setup_selection_mode(self):
        """Setup project selection interface"""
        # Clear any existing widgets
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
                
        # Welcome message
        welcome_label = QLabel("Welcome to MUS1")
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setStyleSheet("font-size: 24px; margin: 20px;")
        
        # Instructions
        instructions = QLabel("Please select an existing project or create a new one")
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setStyleSheet("margin-bottom: 40px;")
        
        # Buttons container
        buttons_layout = QHBoxLayout()
        
        # Create New Project button
        self.new_project_btn = QPushButton("Create New Project")
        self.new_project_btn.setMinimumSize(200, 100)
        self.new_project_btn.clicked.connect(self.create_new_project)
        
        # Open Existing Project button
        self.open_project_btn = QPushButton("Open Existing Project")
        self.open_project_btn.setMinimumSize(200, 100)
        self.open_project_btn.clicked.connect(self.open_existing_project)
        
        # Add buttons with spacing
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.new_project_btn)
        buttons_layout.addSpacing(40)
        buttons_layout.addWidget(self.open_project_btn)
        buttons_layout.addStretch()
        
        # Recent projects section
        recent_label = QLabel("Recent Projects")
        recent_label.setAlignment(Qt.AlignCenter)
        recent_label.setStyleSheet("margin-top: 40px;")
        
        # Add all elements to scroll layout
        self.scroll_layout.addStretch()
        self.scroll_layout.addWidget(welcome_label)
        self.scroll_layout.addWidget(instructions)
        self.scroll_layout.addLayout(buttons_layout)
        self.scroll_layout.addWidget(recent_label)
        self.scroll_layout.addStretch()
        
        self.selection_mode_ready.emit()
        
    def _setup_project_mode(self):
        """Setup project management interface"""
        # Clear selection UI
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
                
        # Setup project management UI
        # TODO: Add project management widgets
        
        self.project_mode_ready.emit()
        
    def switch_mode(self, mode: str):
        """Switch between selection and project modes"""
        if mode != self._mode:
            self._mode = mode
            self._setup_mode()
        
    def _connect_core_signals(self):
        """Connect to core state signals"""
        super()._connect_core_signals()
        # Connect project state signals
        self._state_manager.project_state_changed.connect(self._on_project_state)
        
    def create_new_project(self):
        """Handle new project creation"""
        self.logger.info("Creating new project")
        # TODO: Implement project creation workflow
        pass
        
    def open_existing_project(self):
        """Handle opening existing project"""
        self.logger.info("Opening existing project")
        project_path = QFileDialog.getExistingDirectory(
            self,
            "Select Project Directory",
            str(Path.home()),
            QFileDialog.ShowDirsOnly
        )
        if project_path:
            self.logger.info(f"Selected project path: {project_path}")
            # TODO: Implement project loading
            # Emit signal when project is loaded
            self.project_loaded.emit()

