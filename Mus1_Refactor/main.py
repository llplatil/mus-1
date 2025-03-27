import logging
import sys
from pathlib import Path
import logging.handlers  # Import the handlers module

# Set log file path to be in the same directory as main.py
log_file = Path(__file__).parent / "mus1.log"

# --- Configure RotatingFileHandler ---
# Get the specific logger used by LoggingEventBus and other parts of the app
logger = logging.getLogger('mus1') 
logger.setLevel(logging.INFO) # Set the desired minimum level for this logger

# Prevent logs from propagating to the root logger if it has other handlers
logger.propagate = False 

# Create formatter - consistent with the previous basicConfig format
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Configure RotatingFileHandler
# Rotate log when it reaches 5MB, keep 3 backup logs. Adjust as needed.
max_bytes = 5 * 1024 * 1024 # 5 MB
backup_count = 3
try:
    # Make sure any existing handlers are removed before adding new ones
    # This prevents duplicate logs if the script is re-run or setup is complex
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close() # Close the handler properly

    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file), maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    # Fallback to basic console logging if file handler setup fails
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    logging.error(f"Failed to set up rotating file log handler: {e}. Falling back to basic config.", exc_info=True)
# --- End Logging Configuration ---


from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtTest import QTest

# 1) Bring in relevant classes/functions from core
from core import (
    init_metadata,
    StateManager,
    DataManager,
    ProjectManager,
    ThemeManager
)
from core.logging_bus import LoggingEventBus

# Import the project selection dialog
from gui.project_selection_dialog import ProjectSelectionDialog

def main():
    # Use the configured 'mus1' logger instead of the root logger (__name__)
    logger = logging.getLogger('mus1') 
    logger.info("Launching MUS1...")

    # Initialize data-model checks
    if not init_metadata():
        logger.error("Metadata init failed. Exiting.")
        sys.exit(1)

    # Create our Qt application
    app = QApplication(sys.argv)
    
    # Set application icon
    app_icon = QIcon()
    # Ensure paths are correct and use Path objects
    icon_dir = Path(__file__).parent / "themes"
    app_icon.addFile(str(icon_dir / "m1logo.ico"))  # For Windows
    app_icon.addFile(str(icon_dir / "m1logo no background for big sur.icns"))  # For macOS
    app_icon.addFile(str(icon_dir / "m1logo no background.png"))  # For Linux/general
    app.setWindowIcon(app_icon)
    
    # Initialize the LoggingEventBus singleton
    log_bus = LoggingEventBus.get_instance()
    # Log bus already uses the 'mus1' logger internally, so this log goes through the handler
    log_bus.log("LoggingEventBus initialized", "info", "MainApp") 

    # Create the core managers (no longer need to pass log_bus)
    state_manager = StateManager()
    data_manager = DataManager(state_manager)
    project_manager = ProjectManager(state_manager)
    theme_manager = ThemeManager(state_manager)

    # Use the 'mus1' logger for consistency
    logger.info("Core managers created. Launching Project Selection Dialog.") 

    # Show the project selection dialog
    from PySide6.QtWidgets import QDialog
    dialog = ProjectSelectionDialog(project_manager)
    if dialog.exec() != QDialog.Accepted:
        # Use the 'mus1' logger
        logger.info("Project selection was cancelled. Exiting application.") 
        sys.exit(0)

    # Use the 'mus1' logger
    logger.info("Project selected: {}".format(getattr(dialog, 'selected_project_name', 'Unknown'))) 

    # Apply theme using ThemeManager instead of ProjectManager
    effective_theme = theme_manager.get_effective_theme()
    if effective_theme not in ["light", "dark"]:
        # Log bus uses 'mus1' logger
        log_bus.log("Invalid theme preference detected. Defaulting to dark.", "warning", "Main") 
        effective_theme = "dark"
        theme_manager.change_theme(effective_theme)
    else:
        # Apply the theme to the application
        theme_manager.apply_theme(app)

    # Create and launch our MainWindow after project selection
    from gui.main_window import MainWindow
    selected_project = getattr(dialog, 'selected_project_name', None)
    main_window = MainWindow(state_manager, data_manager, project_manager, selected_project=selected_project)
    main_window.show()

    # Use the 'mus1' logger
    logger.info("MUS1 init complete. Starting application event loop.") 
    sys.exit(app.exec())

if __name__ == "__main__":
    main()