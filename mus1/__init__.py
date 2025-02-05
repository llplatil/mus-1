"""
MUS1 - Mouse Behavior Analysis Tool
"""

# Simply expose what core defines
from .core import metadata, DataManager, StateManager, ProjectManager

__version__ = '0.1.0'

__all__ = [
    'metadata',
    'DataManager',
    'StateManager',
    'ProjectManager'
] 