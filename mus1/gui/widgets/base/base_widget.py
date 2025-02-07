"""Base widget providing common UI elements and core connections"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QScrollArea
from PySide6.QtCore import Qt, Signal
from ....utils import get_logger

class BaseWidget(QWidget):
    """Base widget with common UI elements and core connections"""
    
    # Core connection signals
    core_ready = Signal()  # Emitted when core is connected
    core_disconnected = Signal()  # Emitted when core disconnects
    core_connected = Signal()  # New signal for core connection state
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(f"gui.{self.__class__.__name__.lower()}")
        
        # Core manager references
        self._state_manager = None
        self._data_manager = None
        self._project_manager = None
        
        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create scrollable content widget
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        
        # Setup scroll area
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)
        
        # Common UI elements
        self.mouse_combo = QComboBox()
        self.bodyparts_combo = QComboBox()
        self.batch_combo = QComboBox()
        
        # Initialize UI
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize common UI elements - override in subclasses"""
        # Add common elements to scroll layout
        self.scroll_layout.addWidget(self.mouse_combo)
        self.scroll_layout.addWidget(self.bodyparts_combo)
        self.scroll_layout.addWidget(self.batch_combo)

    def connect_core(self, state_manager, data_manager, project_manager):
        """Connect to core managers"""
        self._state_manager = state_manager
        self._data_manager = data_manager
        self._project_manager = project_manager
        
        self._connect_core_signals()
        self.core_connected.emit()
        
    def disconnect_core(self):
        """Disconnect from core systems"""
        if self._state_manager:
            self._disconnect_core_signals()
            
        self._state_manager = None
        self._data_manager = None
        self._project_manager = None
        self.core_disconnected.emit()
        
    #TODO: house display of lists of experiments, mice, bodyparts, batches, global frame rate, available methods etc.
        