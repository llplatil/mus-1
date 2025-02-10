"""Test utilities for MUS1"""

from pathlib import Path
from ...utils.logging_config import get_class_logger, get_logger
from mus1.core import (
    StateManager, DataManager, ProjectManager
)

class HeadlessApp:
    """Headless version of MUS1 for testing real app flows"""
    
    def __init__(self):
        """Initialize app without GUI - mirrors __main__.py flow"""
        self.logger = get_logger("test.headless")
        
        # Initialize core components as in __main__.py
        self.state_manager = StateManager()
        self.data_manager = DataManager(self.state_manager)
        self.project_manager = ProjectManager(
            self.state_manager,
            self.data_manager
        )
        
    def create_project(self, path: Path) -> None:
        """Create new project - mirrors main app project creation"""
        self.project_manager.create_project(path)
        
    def add_mouse(self, mouse_id: str, metadata: dict) -> str:
        """Add mouse - mirrors main app mouse addition"""
        return self.project_manager.add_mouse(mouse_id, metadata)
        
    def add_experiment(self, **kwargs) -> str:
        """Add experiment - mirrors main app experiment addition"""
        return self.project_manager.add_experiment(**kwargs)

def get_test_data_path(filename: str) -> Path:
    """Helper to get path to test data file"""
    return Path(__file__).parent / "test_data" / filename