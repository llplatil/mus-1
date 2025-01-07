"""Methods Explorer widget for parameter testing"""

from .base_widget import BaseWidget
from ..core import StateManager

class MethodsExplorer(BaseWidget):
    def __init__(self, state_manager: StateManager):
        super().__init__()
        self.state_manager = state_manager 