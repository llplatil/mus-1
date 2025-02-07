"""GUI components for MUS1"""

from ..utils import get_logger
from .widgets.base.base_widget import BaseWidget

logger = get_logger("gui")

def init_gui() -> bool:
    """Initialize GUI system
    
    Follows initialization chain:
    1. Base widget system (core connection point)
    2. Widget system (depends on base)
    3. Main window (coordinates widgets)
    """
    try:
        logger.info("Initializing GUI system")
        
        # Initialize base widget system first
        from .widgets.base import init_base_widgets
        if not init_base_widgets():
            logger.error("Failed to initialize base widget system")
            return False
            
        # Then initialize widget system
        from .widgets import init_widgets
        if not init_widgets():
            logger.error("Failed to initialize widget system")
            return False
            
        # Finally verify main window can be created
        from .main_window import MainWindow
        
        logger.info("GUI system initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize GUI system: {e}")
        return False

__all__ = ['init_gui', 'BaseWidget']