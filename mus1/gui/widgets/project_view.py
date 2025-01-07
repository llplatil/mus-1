"""Project navigation widget"""

from .base_widget import BaseWidget
from ..core import StateManager, ProjectManager

class ProjectView(BaseWidget):
    def __init__(self, state_manager: StateManager, project_manager: ProjectManager):
        super().__init__()
        self.state_manager = state_manager
        self.project_manager = project_manager 