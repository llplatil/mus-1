"""Novel Object Recognition analysis implementation"""

from typing import Dict, Any
from ..base_plugin import BasePlugin
import numpy as np
import pandas as pd

class NORPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.name = "nor"
        self.description = "Novel Object Recognition Analysis"
        self.parameters = {
            "familiar_object_zone": None,
            "novel_object_zone": None,
            "habituation_time": 600,  # 10 minutes in seconds as default
            "test_duration": 600,     # 10 minutes in seconds as default
        }
        
        #placeholder for explaiantion of what we learend from last NOR Analysis Script buildout 