"""
Entry point for MUS1 application
"""
import sys
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from PySide6.QtWidgets import QApplication

# Import utils first
from .utils import init_logging
if not init_logging():
    print("CRITICAL: Failed to initialize logging system")
    sys.exit(1)

# Then get logger for main
from .utils import get_logger
logger = get_logger("main")

# Import core components
from .core import (
    StateManager,
    DataManager, 
    ProjectManager
)
from .core.metadata import (
    MouseMetadata,
    ExperimentMetadata, 
    BatchMetadata,
    ProjectState
    #TODO: add TrackingData once its integrated in core
)

# Import only needed GUI components
from .gui.dialogs import StartupDialog
from .gui.main_window import MainWindow
from .gui.widgets.base import BaseWidget

# Import plugin system
from .plugins import init_plugins as init_plugin_system

def init_metadata() -> Tuple[bool, Optional[str]]:
    """Initialize metadata system and verify core classes are available"""
    logger.info("Initializing metadata system")
    
    try:
        required_classes = {
            'MouseMetadata': MouseMetadata,
            'ExperimentMetadata': ExperimentMetadata,
            'BatchMetadata': BatchMetadata,
            'ProjectState': ProjectState
        }
        
        # Verify all required classes are available
        for name, cls in required_classes.items():
            if not cls:
                return False, f"Required metadata class not found: {name}"
                
        logger.info("Metadata system initialized successfully")
        return True, None
        
    except Exception as e:
        logger.error(f"Failed to initialize metadata system: {e}")
        return False, str(e)

def init_core() -> Tuple[Optional[StateManager], 
                        Optional[DataManager], 
                        Optional[ProjectManager]]:
    """Initialize core components"""
    logger.info("Initializing core components")
    
    try:
        # Initialize managers in dependency order
        data_manager = DataManager()
        state_manager = StateManager(data_manager)
        project_manager = ProjectManager(state_manager, data_manager)
        
        return state_manager, data_manager, project_manager
        
    except Exception as e:
        logger.error(f"Failed to initialize core: {e}")
        return None, None, None

def init_plugins() -> bool:
    """Initialize plugin system"""
    logger.info("Initializing plugin system")
    
    try:
        # Initialize plugin system using the imported function
        success = init_plugin_system()
        if success:
            logger.info("Plugin system initialized successfully")
        else:
            logger.error("Plugin system initialization returned False")
        return success
        
    except Exception as e:
        logger.error(f"Failed to initialize plugins: {e}")
        return False

def init_gui(state_manager: StateManager, 
             project_manager: ProjectManager, 
             data_manager: DataManager) -> Optional[MainWindow]:
    """Initialize GUI system including startup flow"""
    logger.info("Initializing GUI system")
    
    try:
        # Create main window first
        main_window = MainWindow(state_manager, data_manager, project_manager)
        
        # Handle project selection through startup dialog
        startup = StartupDialog(project_manager, state_manager, data_manager)
        if startup.exec() != StartupDialog.Accepted:
            logger.info("Startup cancelled by user")
            return None
            
        # Initialize main UI only after successful startup
        main_window.initialize_after_startup()
        main_window.show()
        
        return main_window
        
    except Exception as e:
        logger.error(f"Failed to initialize GUI: {e}")
        return None

def main() -> int:
    """Main application entry point"""
    logger.info("Starting MUS1 application")
    
    try:
        # First initialize metadata
        metadata_ok, error = init_metadata()
        if not metadata_ok:
            logger.error(f"Failed to initialize metadata: {error}")
            return 1
            
        app = QApplication(sys.argv)
        
        # Initialize core components
        state_manager, data_manager, project_manager = init_core()
        if not all((state_manager, data_manager, project_manager)):
            logger.error("Failed to initialize core components")
            return 1
            
        # Initialize plugin system
        if not init_plugins():
            logger.error("Failed to initialize plugin system")
            return 1
            
        # Initialize GUI including startup
        main_window = init_gui(state_manager, project_manager, data_manager)
        if main_window is None:
            return 1
            
        return app.exec()
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        return 1

def main_dev(*, core_only: bool = False, skip_plugins: bool = False, 
             skip_startup: bool = False, skip_metadata: bool = False) -> int:
    """Development entry point with configurable initialization"""
    logger.info("Starting MUS1 in development mode")
    
    try:
        # Metadata initialization can be skipped in dev mode
        if not skip_metadata:
            metadata_ok, error = init_metadata()
            if not metadata_ok:
                logger.error(f"Failed to initialize metadata: {error}")
                return 1
                
        app = QApplication(sys.argv)
        
        # Core is always needed
        state_manager, data_manager, project_manager = init_core()
        if not all((state_manager, data_manager, project_manager)):
            return 1
            
        if core_only:
            logger.info("Core-only mode, running core tests...")
            return 0
            
        # Optional plugin initialization
        if not skip_plugins:
            if not init_plugins():
                return 1
                
        # Handle startup if needed
        if not skip_startup:
            main_window = init_gui(state_manager, project_manager, data_manager)
            if main_window is None:
                return 1
            
        return app.exec()
        
    except Exception as e:
        logger.error(f"Development mode failed: {e}")
        return 1
    finally:
        # Ensure logging is properly shutdown
        from .utils import shutdown_logging
        shutdown_logging()

if __name__ == "__main__":
    try:
        # Can be launched different ways:
        sys.exit(main())  # Normal launch
        # sys.exit(main_dev(core_only=True))  # Core testing
        # sys.exit(main_dev(skip_plugins=True))  # No plugins
    finally:
        # Always ensure logging is shutdown
        from .utils import shutdown_logging
        shutdown_logging()
    