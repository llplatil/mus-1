"""Main window coordinator for MUS1"""

from PySide6.QtWidgets import QMainWindow, QTabWidget
from PySide6.QtCore import Qt, Slot, Signal
from .widgets import ProjectView, MethodsExplorer
from .widgets.base import BaseWidget

class MainWindow(BaseWidget):
    """Main application window coordinator"""
    
    # Add signal for window ready state
    window_ready = Signal()
    
    def __init__(self):
        super().__init__()
        self.logger.info("Initializing MainWindow")
        self._setup_window_frame()
        
    def _setup_window_frame(self):
        """Setup window frame before core connection"""
        self.setWindowTitle("MUS1")
        self.resize(1200, 800)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.West)
        self.setCentralWidget(self.tab_widget)
        
    def connect_core(self, state_manager, data_manager, project_manager):
        """Override to handle startup sequence
        
        Order:
        1. Connect core (through BaseWidget)
        2. Initialize project selection
        3. once core ready show window
        """
        # 1. Base connection
        super().connect_core(state_manager, data_manager, project_manager)
        
        # 2. Initialize views
        self._init_project_selection()
        
        # 3. Setup window visibility
        self._state_manager.core_ready.connect(self.show)
        
        # 4. Signal system ready
        self._state_manager.core_ready.emit()
            
    def _init_project_selection(self):
        """Initialize project selection view"""
        self.logger.info("Initializing project selection")
        self.project_view = ProjectView(self, initial_mode="selection")
        self.tab_widget.addTab(self.project_view, "Project")
        
        # Connect project state changes
        if self._state_manager:
            self._state_manager.project_state_changed.connect(self._on_project_state_changed)

    @Slot(bool)
    def _on_project_state_changed(self, has_project: bool):
        """Handle project state transitions"""
        if has_project and self.tab_widget.count() == 1:
            # Add analysis tabs when project loaded
            self.methods_explorer = MethodsExplorer(self)
            self.tab_widget.addTab(self.methods_explorer, "Analysis")
        elif not has_project and self.tab_widget.count() > 1:
            # Remove analysis tabs when project closed
            while self.tab_widget.count() > 1:
                self.tab_widget.removeTab(1)
                
    @Slot(int, int)
    def _handle_widget_resize(self, width: int, height: int):
        """Handle widget resize requests"""
        # TODO: Implement smart resize handling
        pass
    def handle_main_window_resize(self, width: int, height: int):
        """Handle main window resize requests"""
        # TODO: Implement smart resize handling, with connect to widgets
        pass
    def resizeEvent(self, event):
        """Propagate resize to base widgets"""
        super().resizeEvent(event)
        # TODO: propagate resize to base widgets, and tabs so that they resize properly 
        event.accept()
