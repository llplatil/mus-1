import logging
import sys
from pathlib import Path
import logging.handlers  # Import the handlers module



# --- Configure RotatingFileHandler ---
# Get the specific logger used by LoggingEventBus and other parts of the app
logger = logging.getLogger('mus1')
logger.setLevel(logging.DEBUG) # Set the desired minimum level for this logger

# Prevent logs from propagating to the root logger if it has other handlers
logger.propagate = False

# Create formatter - consistent with CLI formatter for unified logging
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Configure RotatingFileHandler
# Use a default log file location that will be updated when a project is selected
# For now, use the same directory as main.py for consistency
default_log_file = Path(__file__).parent / "mus1.log"

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
        str(default_log_file), maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
    )
    # file_handler level is not explicitly set, so it inherits INFO from the logger
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    # Fallback to basic console logging if file handler setup fails
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    logging.error(f"Failed to set up rotating file log handler: {e}. Falling back to basic config.", exc_info=True)
# --- End Logging Configuration ---


from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

# Core components
from .core.logging_bus import LoggingEventBus
from .core.config_manager import ConfigManager
from .core.theme_manager import ThemeManager

def main():
    """MUS1 GUI Application Entry Point"""
    # Initialize core components
    log_bus = LoggingEventBus.get_instance()
    config_manager = ConfigManager()
    theme_manager = ThemeManager(config_manager)

    logger = logging.getLogger('mus1')
    logger.info("Launching MUS1 GUI...")

    app = QApplication(sys.argv)

    # Set application icon
    app_icon = QIcon()
    icon_dir = Path(__file__).parent / "themes"
    app_icon.addFile(str(icon_dir / "m1logo.ico"))  # Windows
    app_icon.addFile(str(icon_dir / "m1logo no background for big sur.icns"))  # macOS
    app_icon.addFile(str(icon_dir / "m1logo no background.png"))  # Linux
    app.setWindowIcon(app_icon)

    # Apply theme
    effective_theme = theme_manager.apply_theme(app)
    logger.info(f"Theme applied: {effective_theme}")

    # Check setup status and show setup wizard if needed
    from .core.setup_service import get_setup_service
    setup_service = get_setup_service()

    if not setup_service.is_user_configured():
        logger.info("First-time setup required")
        from .gui.setup_wizard import show_setup_wizard
        setup_wizard = show_setup_wizard()
        if setup_wizard is None:
            logger.info("Setup cancelled by user")
            return  # User cancelled setup
        logger.info("Setup wizard completed")

    # Show project selection dialog
    from .gui.main_window import MainWindow

    # TODO: Implement proper project selection workflow
    # For now, create MainWindow with no selected project
    main_window = MainWindow(selected_project=None)
    main_window.apply_theme()
    main_window.show()

    logger.info("MUS1 GUI started successfully")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()