"""GUI components for MUS1"""

from .main_window import MainWindow
from .widgets.base import BaseWidget
from .dialogs import StartupDialog

__all__ = [
    'MainWindow',     # Main window that coordinates GUI
    'BaseWidget',     # Base for all widgets
    'StartupDialog'   # Initial project setup
]