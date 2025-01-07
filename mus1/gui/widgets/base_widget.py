"""Base widget class for MUS1"""

from PySide6.QtWidgets import QWidget
from typing import Optional

class BaseWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize widget UI"""
        pass 