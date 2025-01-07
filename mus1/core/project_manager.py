"""
Project management for MUS1

Handles project file structure and configuration.
"""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import yaml
import json
from .state_manager import MouseMetadata, ExperimentData

class ProjectManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager
 