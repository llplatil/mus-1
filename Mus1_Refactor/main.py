import logging
import sys
from pathlib import Path

# Set log file path to be in the same directory as main.py
log_file = Path(__file__).parent / "mus1.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    filename=str(log_file),
    filemode="a"
)

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap
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
    logger = logging.getLogger(__name__)
    logger.info("Launching MUS1...")

    # Initialize data-model checks
    if not init_metadata():
        logger.error("Metadata init failed. Exiting.")
        sys.exit(1)

    # Create our Qt application
    app = QApplication(sys.argv)
    
    # Initialize the LoggingEventBus singleton
    log_bus = LoggingEventBus.get_instance()
    log_bus.log("LoggingEventBus initialized", "info", "MainApp")

    # Create the core managers (no longer need to pass log_bus)
    state_manager = StateManager()
    data_manager = DataManager(state_manager)
    project_manager = ProjectManager(state_manager)
    theme_manager = ThemeManager(state_manager)

    logger.info("Core managers created. Launching Project Selection Dialog.")

    # Show the project selection dialog
    from PySide6.QtWidgets import QDialog
    dialog = ProjectSelectionDialog(project_manager)
    if dialog.exec() != QDialog.Accepted:
        logger.info("Project selection was cancelled. Exiting application.")
        sys.exit(0)

    logger.info("Project selected: {}".format(getattr(dialog, 'selected_project_name', 'Unknown')))

    # Apply theme using ThemeManager instead of ProjectManager
    effective_theme = theme_manager.get_effective_theme()
    if effective_theme not in ["light", "dark"]:
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

    logger.info("MUS1 init complete. Starting application event loop.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()