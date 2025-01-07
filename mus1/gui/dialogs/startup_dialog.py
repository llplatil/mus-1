"""Initial project setup dialog"""

from PySide6.QtWidgets import QDialog
from ..core import ProjectManager

class StartupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        