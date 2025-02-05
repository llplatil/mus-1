"""Base widget class for MUS1"""

from PySide6.QtWidgets import QWidget, QComboBox
from PySide6.QtCore import Signal
from typing import Optional
from ....core import (
    StateManager, ProjectManager, DataManager
)
from ...utils.logging_config import get_class_logger, get_logger  # Single import from utils

class BaseWidget(QWidget):
    """
    Base widget providing core manager access and common functionality.
    All MUS1 widgets should inherit from this.
    """
    state_changed = Signal(str)  # Signal for widget-specific state changes
    
    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        data_manager: DataManager,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize base widget with core managers.
        
        Args:
            state_manager: Central state management
            project_manager: Project lifecycle management
            data_manager: Data processing and validation
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.data_manager = data_manager
        self.logger = get_class_logger(self.__class__)
        
        self.setup_ui()
        self.setup_connections()
    
    def setup_ui(self) -> None:
        """Initialize widget UI - override in subclasses"""
        # Add common elements:
        self.mouse_combo = QComboBox()
        self._update_mouse_dropdown()
        
        super().setup_ui()  # For override
        
    def setup_connections(self) -> None:
        """Setup signal/slot connections - override in subclasses"""
        pass
        
    def update_from_state(self) -> None:
        """Update widget based on state changes - override in subclasses"""
        pass 

    def _update_mouse_dropdown(self):
        """Refresh mouse selection dropdown (callable by all subclasses)"""
        self.mouse_combo.clear()
        for mouse_id in self.state_manager.get_mouse_ids():
            mouse = self.state_manager.get_mouse(mouse_id)
            display_text = f"{mouse.id} ({mouse.sex}) - {mouse.birth_date.strftime('%Y-%m-%d')}"
            self.mouse_combo.addItem(display_text, mouse_id) 

#TODO: decide where to track the current state of dropdowns for mouse IDs, bodyparts, objects, experiments, batches, etc.