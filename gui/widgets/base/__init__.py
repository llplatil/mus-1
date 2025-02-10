"""Base widget components for MUS1"""

from ....utils import get_logger
logger = get_logger("gui.widgets.base")

def init_base_widgets() -> bool:
    """Initialize base widget system
    
    BaseWidget serves as the main connection point between:
    - GUI widgets
    - Core managers 
    - Plugin system
    """
    try:
        logger.info("Initializing base widget system")
        
        # Import after logging is ready
        from .base_widget import BaseWidget
        
        # Verify core connection methods exist
        required_methods = [
            'connect_core',
            '_connect_core_signals',
            'disconnect_core'
        ]
        
        for method in required_methods:
            if not hasattr(BaseWidget, method):
                logger.error(f"BaseWidget missing required method: {method}")
                return False
            
        logger.info("Base widget system initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize base widget system: {e}")
        return False

# Only export initialization and base widget
__all__ = ['init_base_widgets', 'BaseWidget'] 