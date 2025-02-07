"""Core functionality for MUS1"""

from ..utils import get_logger
logger = get_logger("core")

def init_core() -> bool:
    """Initialize core system
    
    Returns:
        bool: True if core system initialized successfully
    """
    try:
        logger.info("Initializing core system")
        
        # First initialize metadata system
        from .metadata import init_metadata
        if not init_metadata():
            logger.error("Failed to initialize metadata system")
            return False
            
        # Then initialize managers in dependency order
        from .data_manager import DataManager
        from .state_manager import StateManager 
        from .project_manager import ProjectManager
        
        # Verify manager classes are properly configured
        managers = {
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

# Only export what's needed
__all__ = [
    'init_core',
    'DataManager',
    'StateManager', 
    'ProjectManager'
]

