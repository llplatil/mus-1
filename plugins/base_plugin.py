"""Base class for MUS1 analysis plugins"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from ..utils import get_logger
from ..core.metadata import PluginMetadata, ExperimentMetadata, TrackingData
from ..gui.widgets.base.base_widget import BaseWidget  # Import connection pattern

class BasePlugin(ABC):
    """Base class for all analysis plugins"""
    
    def __init__(self, parent: Optional[BaseWidget] = None):
        """Initialize plugin with optional parent widget
        
        Args:
            parent: Optional parent BaseWidget for core connections
        """
        self.logger = get_logger(f"plugins.{self.__class__.__name__.lower()}")
        self._parent = parent
        
        # Get core connections from parent if available
        if parent:
            self._state_manager = parent._state_manager
            self._data_manager = parent._data_manager
        else:
            self._state_manager = None
            self._data_manager = None
            
        if not hasattr(self, 'metadata'):
            self.logger.warning(f"{self.__class__.__name__} missing metadata")

    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """Get default parameters for plugin"""
        return {}

    @abstractmethod
    def process_tracking_data(
        self,
        tracking_data: TrackingData,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process tracking data with optional parameters
        
        Args:
            tracking_data: Tracking data to process
            params: Optional processing parameters
            
        Returns:
            Dict containing analysis results
        """
        pass

    def get_required_body_parts(self) -> List[str]:
        """Get list of required body parts for this plugin"""
        return []

    def get_required_objects(self) -> List[str]:
        """Get list of required tracked objects for this plugin"""
        return []

