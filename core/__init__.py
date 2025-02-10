"""Core functionality for MUS1"""

from pathlib import Path
from typing import Optional, Dict, Type
from ..utils import get_logger

logger = get_logger("core")

CORE_PATH = Path(__file__).parent
REQUIRED_PATHS = {
    'data_manager': CORE_PATH / 'data_manager.py',
    'state_manager': CORE_PATH / 'state_manager.py',
    'project_manager': CORE_PATH / 'project_manager.py'
}

def verify_core_paths() -> bool:
    """Verify all required core files exist
    
    Returns:
        bool: True if all required files exist
    """
    missing = [str(p) for p in REQUIRED_PATHS.values() if not p.exists()]
    if missing:
        logger.error(f"Missing required files: {missing}")
        return False
    return True

def init_core() -> bool:
    """Initialize core system
    
    Returns:
        bool: True if core system initialized successfully
    """
    try:
        logger.info("Initializing core system")
        
        # First verify all required files exist
        if not verify_core_paths():
            return False
            
        # Initialize metadata system
        from .metadata import init_metadata
        if not init_metadata():
            logger.error("Failed to initialize metadata system")
            return False
            
        # Import manager classes
        from .data_manager import DataManager
        from .state_manager import StateManager 
        from .project_manager import ProjectManager
        
        # Verify manager classes
        managers: Dict[str, Type] = {
            'data': DataManager,
            'state': StateManager,
            'project': ProjectManager
        }
        
        for name, manager_cls in managers.items():
            if not hasattr(manager_cls, '__init__'):
                logger.error(f"{name} manager missing initialization")
                return False
                
        logger.info("Core system initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize core system: {e}")
        return False

def get_core_path() -> Path:
    """Get path to core directory"""
    return CORE_PATH

def get_file_path(file_name: str) -> Optional[Path]:
    """Get path to a core file
    
    Args:
        file_name: Name of file (e.g. 'metadata.py', 'data_manager.py')
        
    Returns:
        Path to file or None if not found
    """
    path = CORE_PATH / file_name
    return path if path.exists() else None


# Only export what's needed
__all__ = [
    'init_core',
    'DataManager',
    'StateManager', 
    'ProjectManager',
    'get_core_path',
    'get_file_path'
]

