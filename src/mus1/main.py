import logging
import sys
from pathlib import Path


from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

# Core components
from .core.logging_bus import LoggingEventBus
from .core.config_manager import ConfigManager, resolve_mus1_root
from .core.theme_manager import ThemeManager

def main():
    """MUS1 GUI Application Entry Point"""
    # Initialize core components
    log_bus = LoggingEventBus.get_instance()
    # Configure a single rotating file handler under the resolved MUS1 root
    mus1_root = resolve_mus1_root()
    (mus1_root / "logs").mkdir(exist_ok=True)
    log_bus.configure_default_file_handler(mus1_root / "logs", max_size=5 * 1024 * 1024, backups=3)
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