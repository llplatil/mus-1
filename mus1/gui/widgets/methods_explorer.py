"""Methods Explorer widget for parameter testing"""

from PySide6.QtWidgets import (QListWidget, QPushButton, 
                              QVBoxLayout, QHBoxLayout)
from .base.base_widget import BaseWidget

class MethodsExplorer(BaseWidget):
    """Tab for exploring and testing analysis methods"""
    
    def __init__(self, parent=None):
        super().__init__(parent)  # BaseWidget already sets up logger
        self.logger.info("Initializing Methods Explorer")
        
    def setup_ui(self):
        """Initialize methods explorer UI"""
        super().setup_ui()  # Get common elements from BaseWidget
        
        #TODO: Import lists from base widget 
        
        # Controls
        controls_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run Analysis")
        self.settings_btn = QPushButton("Method Settings")
        controls_layout.addWidget(self.run_btn)
        controls_layout.addWidget(self.settings_btn)
        
        # Add to scroll layout
        self.scroll_layout.addLayout(controls_layout)

    def _connect_core_signals(self):
        """Connect to core state signals"""
        super()._connect_core_signals()
        # Connect to method-specific signals
        self._state_manager.experiment_updated.connect(self._update_methods)
        self._state_manager.batch_updated.connect(self._update_batch_methods)