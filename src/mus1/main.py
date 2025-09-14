import logging
import sys
from pathlib import Path
import logging.handlers  # Import the handlers module

# ===========================================
# DETERMINISTIC MUS1 ROOT & LOGGING SETUP
# ===========================================

# First, resolve MUS1 root deterministically
from .core.config_manager import resolve_mus1_root
mus1_root = resolve_mus1_root()
logs_dir = mus1_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Configure logging to use MUS1 logs directory
logger = logging.getLogger('mus1')
logger.setLevel(logging.DEBUG)
logger.propagate = False

formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Use MUS1 logs directory for log files
log_file = logs_dir / "mus1.log"
max_bytes = 5 * 1024 * 1024  # 5 MB
backup_count = 3

try:
    # Clean up any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file), maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(f"MUS1 logging initialized - logs at: {log_file}")
    logger.info(f"MUS1 root directory: {mus1_root}")

except Exception as e:
    # Fallback to console logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    logging.error(f"Failed to set up log handler: {e}. Falling back to console.", exc_info=True)


from PySide6.QtWidgets import QApplication, QMessageBox
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
    setup_completed = False

    if not setup_service.is_user_configured():
        logger.info("First-time setup required - showing setup wizard")
        from .gui.setup_wizard import show_setup_wizard
        setup_wizard = show_setup_wizard()

        if setup_wizard is None:
            logger.info("Setup cancelled by user")
            reply = QMessageBox.question(
                None, "Setup Required",
                "MUS1 requires initial setup to continue. Would you like to run setup again?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                setup_wizard = show_setup_wizard()
                if setup_wizard is None:
                    sys.exit(0)  # User cancelled again - exit cleanly
            else:
                sys.exit(0)  # User doesn't want to setup - exit cleanly

        logger.info("Setup wizard completed successfully")
        setup_completed = True

    # Show project selection dialog
    from .gui.main_window import MainWindow

    # Pass setup completion status to MainWindow
    main_window = MainWindow(selected_project=None, setup_completed=setup_completed)
    main_window.apply_theme()
    main_window.show()

    logger.info("MUS1 GUI started successfully")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()