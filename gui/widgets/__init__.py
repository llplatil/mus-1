"""GUI widgets for MUS1"""

from ...utils import get_logger
logger = get_logger("gui.widgets")

def init_widgets() -> bool:
    """Initialize widget system
    
    Depends on base widget system for core connections
    """
    try:
        logger.info("Initializing widget system")
        
        # Verify base system is ready
        from .base import init_base_widgets
        if not init_base_widgets():
            logger.error("Base widget system not ready")
            return False
        
        # Import widgets that depend on base
        from .base.base_widget import BaseWidget
        from .methods_explorer import MethodsExplorer
        from .project_view import ProjectView
        
        logger.info("Widget system initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize widget system: {e}")
        return False

__all__ = [
    'init_widgets',
    'BaseWidget',
    'MethodsExplorer', 
    'ProjectView'
] 