"""Base class for MUS1 analysis plugins"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from ...utils.logging_config import get_class_logger
from ...core import StateManager, DataManager

@dataclass
class PluginMetadata:
    """Plugin metadata structure"""
    name: str
    version: str
    description: str
    author: str

class BasePlugin(ABC):
    """Base class for all analysis plugins"""
    
    # Class-level metadata - must be overridden by subclasses
    metadata: PluginMetadata
    
    def __init__(self, state_manager: StateManager, data_manager: DataManager):
        """Initialize plugin with core managers"""
        self.logger = get_class_logger(self.__class__)
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.logger.info(f"Initialized {self.metadata.name} plugin v{self.metadata.version}")

    @abstractmethod
    def process_experiment(self, tracking_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Process experiment data - must be implemented by subclasses"""
        pass

    def validate_analysis_inputs(self, experiment: ExperimentMetadata) -> Tuple[bool, str]:
        """Standard prerequisite check"""
        errors = []
        if not experiment.tracking_data:
            errors.append("Missing tracking data")
        if not experiment.analysis_ready:
            errors.append("Experiment not analysis-ready")
        return len(errors) == 0, " | ".join(errors)
         
class NORPlugin(BasePlugin):
    def process_experiment(self, tracking_data: Dict, params: Dict) -> Dict:
        # Get frame rate from DataManager
        frame_rate = self.data_manager.get_effective_frame_rate(experiment)
        # Use frame_rate in analysis
        pass

    def validate_metadata(self, metadata: ExperimentMetadata) -> Tuple[bool, str]:
        """NOR-specific validation"""
        errors = []
        # Check required object roles
        if not {'novel', 'familiar'}.issubset(metadata.object_roles.values()):
            errors.append("Missing required object roles (novel/familiar)")
        
        # Check optional fields if available
        if metadata.phase not in ['familiarization', 'test']:
            errors.append("Invalid phase for NOR experiment")
            
        return len(errors) == 0, " | ".join(errors)
