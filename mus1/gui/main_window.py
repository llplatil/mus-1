"""Main application window for MUS1"""

from PySide6.QtWidgets import QMainWindow
from .widgets import ProjectView, MethodsExplorer
from .dialogs import StartupDialog
from ..core import StateManager

class MainWindow(QMainWindow):
    def __init__(self, state_manager: StateManager):
        super().__init__()
        self.state_manager = state_manager
        self.setWindowTitle("MUS1")
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize UI components"""
        # Placeholder for UI setup
        pass 