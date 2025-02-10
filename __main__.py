"""
Entry point for MUS1 application
"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap

# Initialize logging first
from .utils import init_logging, get_logger
if not init_logging():
    print("CRITICAL: Failed to initialize logging system")
    sys.exit(1)

# Import initialization functions
from .core import init_core
from .plugins import init_plugins
from .gui import init_gui

logger = get_logger("main")

def main() -> int:
    """Main application entry point"""
    logger.info("Starting MUS1")
    
    try:
        # Create Qt application
        app = QApplication(sys.argv)
        
        # Show splash screen
        splash_path = Path(__file__).parent / "tests/test_data/dlc_examples/arena_images/arena_image.png"
        splash = QSplashScreen(QPixmap(str(splash_path)))
        splash.show()
        app.processEvents()
        
        # Initialize systems
        if not all([init_core(), init_plugins(), init_gui()]):
            logger.critical("Failed to initialize one or more systems")
            return 1
            
        # Create managers
        from .core.state_manager import StateManager
        from .core.data_manager import DataManager
        from .core.project_manager import ProjectManager
        
        state_manager = StateManager()
        data_manager = DataManager(state_manager)
        project_manager = ProjectManager(state_manager, data_manager)
        
        # Create main window but don't show yet
        from .gui.main_window import MainWindow
        window = MainWindow()
        
        # Connect core - this will trigger initialization sequence
        window.connect_core(state_manager, data_manager, project_manager)
        
        # Wait for project view to be ready before closing splash
        window.project_view.selection_mode_ready.connect(
            lambda: splash.finish(window)
        )
        
        return app.exec()
        
    except Exception as e:
        logger.critical(f"Application startup failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())