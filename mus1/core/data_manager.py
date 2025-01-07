"""
Data management and processing for MUS1

Handles data loading, validation, and processing.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import pandas as pd
import yaml
from .state_manager import ExperimentData

class DataManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        

