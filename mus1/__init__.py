"""MUS1: Mouse Behavior Analysis Tool"""

from .core import StateManager, ProjectManager, DataManager
from .gui import MainWindow

__version__ = "0.1.0"

# Expose main components
__all__ = [
    'StateManager',
    'ProjectManager', 
    'DataManager',
    'MainWindow',
] 