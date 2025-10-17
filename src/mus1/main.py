import logging
import sys
from pathlib import Path

# Core components
from .core.logging_bus import LoggingEventBus
from .core.config_manager import ConfigManager, resolve_mus1_root, get_root_pointer_info, get_config
from .gui.theme_manager import ThemeManager

# Qt imports - unified PyQt6 facade
from .gui.qt import QApplication, QIcon, QFileDialog, QMessageBox

def main():
    """MUS1 GUI Application Entry Point"""
    # Initialize core components first (before QApplication)
    log_bus = LoggingEventBus.get_instance()

    # If a root pointer exists but is invalid, prompt user to locate a valid root
    # Note: This check happens before QApplication creation, so we handle it differently
    info = get_root_pointer_info()
    if info.get("exists") and info.get("target") and not info.get("valid"):
        # We'll handle this after QApplication is created
        needs_root_selection = True
        invalid_root_target = info["target"]
    else:
        needs_root_selection = False
        invalid_root_target = None

    # Configure a single rotating file handler; prefer configured mus1.root_path if set
    try:
        configured_root = get_config("mus1.root_path")
        log_bus.configure_app_file_handler(max_size=5 * 1024 * 1024, backups=3)
    except Exception:
        # Fallback to default app root logs directory
        log_bus.configure_app_file_handler(max_size=5 * 1024 * 1024, backups=3)

    config_manager = ConfigManager()
    # One-time migration: move legacy user profile keys to SQL if present
    try:
        from .core.setup_service import get_setup_service
        get_setup_service().migrate_legacy_user_profile_if_needed()
    except Exception:
        pass
    theme_manager = ThemeManager(config_manager)

    # Create QApplication AFTER core initialization
    app = QApplication(sys.argv)

    # Handle invalid root pointer now that QApplication exists
    if needs_root_selection:
        reply = QMessageBox.question(
            None,
            "Configuration Not Found",
            f"The configured MUS1 root at '{invalid_root_target}' is unavailable.\n"
            "Would you like to locate an existing configuration?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            selected = QFileDialog.getExistingDirectory(None, "Select MUS1 Configuration Root")
            if selected:
                from .core.config_manager import set_root_pointer
                set_root_pointer(Path(selected))
                # Reconfigure logging to app logs under the (potentially) new root
                log_bus.configure_app_file_handler(max_size=5 * 1024 * 1024, backups=3)

    logger = logging.getLogger('mus1')
    logger.info("Launching MUS1 GUI...")
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

    # Check command line arguments or environment variable for setup wizard
    import os
    run_setup_wizard = "--setup" in sys.argv or "-s" in sys.argv or os.environ.get('MUS1_SETUP_REQUESTED') == '1'

    if run_setup_wizard or not setup_service.is_user_configured():
        if run_setup_wizard:
            logger.info("Setup wizard requested via command line")
        else:
            logger.info("First-time setup required - showing setup wizard")

        from .gui.setup_wizard import show_setup_wizard
        setup_wizard = show_setup_wizard()

        if setup_wizard is None:
            logger.info("Setup cancelled by user")
            if not setup_service.is_user_configured():
                reply = QMessageBox.question(
                    None, "Setup Required",
                    "MUS1 requires initial setup to continue. Would you like to run setup again?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    setup_wizard = show_setup_wizard()
                    if setup_wizard is None:
                        sys.exit(0)  # User cancelled again - exit cleanly
                else:
                    sys.exit(0)  # User doesn't want to setup - exit cleanly

        logger.info("Setup wizard completed successfully")
        setup_completed = True

    # Show project selection dialog
    from .gui.main_window import MainWindow

    # Pass setup completion status and ThemeManager to MainWindow
    main_window = MainWindow(selected_project=None, setup_completed=setup_completed, theme_manager=theme_manager)
    main_window.apply_theme()
    main_window.show()

    logger.info("MUS1 GUI started successfully")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
