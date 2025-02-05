"""Main window with tabbed interface"""

from PySide6.QtWidgets import QMainWindow, QWidget, QTabWidget
from ..utils.logging_config import get_class_logger
from .widgets.base import BaseWidget
from .dialogs import StartupDialog
from .widgets import ProjectView, MethodsExplorer

class MainWindow(QMainWindow):
    """
    Main application window with tab-based interface.
    Coordinates between core managers and UI components.
    """
    def __init__(self, state_manager, data_manager, project_manager):
        super().__init__()
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.project_manager = project_manager
        self.logger = get_class_logger(self.__class__)
        
        # Central widget will be initialized after startup
        self.central_widget = None
        
        # Setup base window structure
        self.setup_base_window()
        
    def setup_base_window(self):
        """Initialize base window structure"""
        self.setWindowTitle("MUS1")
        self.resize(1200, 800)
        
        # ... base window setup

    def initialize_after_startup(self):
        """Initialize tabbed interface after startup"""
        self.tab_widget = QTabWidget()
        
        # Create and add tabs
        self.project_tab = ProjectView(
            self.state_manager,
            self.project_manager,
            self.data_manager
        )
        self.methods_tab = MethodsExplorer(
            self.state_manager,
            self.project_manager,
            self.data_manager
        )
        
        self.tab_widget.addTab(self.project_tab, "Project")
        self.tab_widget.addTab(self.methods_tab, "Methods")
        
        self.setCentralWidget(self.tab_widget)

    def _setup_tabs(self):
        """Configure tabbed interface"""
        self.tab_widget.setTabPosition(QTabWidget.West)
        self.tab_widget.setMovable(True)