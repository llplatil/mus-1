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
    ProjectManager
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

    # Show a splash screen
    splash_pix = QPixmap("assets/m1logo.jpg")  # Updated path to use the assets directory
    # Try fallback paths if the image isn't found
    if splash_pix.isNull():
        alternate_paths = [
            "Mus1_Refactor/assets/m1logo.jpg",
            "../assets/m1logo.jpg",
            "m1logo.jpg"
        ]
        for path in alternate_paths:
            splash_pix = QPixmap(path)
            if not splash_pix.isNull():
                break
        
    splash = QSplashScreen(splash_pix)
    splash.show()
    # Process events so that the splash screen is displayed immediately
    app.processEvents()
    QTest.qWait(1000)  # Wait for 1 second
    splash.close()  # Close splash before proceeding

    # Initialize the LoggingEventBus singleton
    log_bus = LoggingEventBus.get_instance()
    log_bus.log("LoggingEventBus initialized", "info", "MainApp")

    # Create the core managers (no longer need to pass log_bus)
    state_manager = StateManager()
    data_manager = DataManager(state_manager)
    project_manager = ProjectManager(state_manager)

    logger.info("Core managers created. Launching Project Selection Dialog.")

    # Show the project selection dialog
    from PySide6.QtWidgets import QDialog
    dialog = ProjectSelectionDialog(project_manager)
    if dialog.exec() != QDialog.Accepted:
        logger.info("Project selection was cancelled. Exiting application.")
        sys.exit(0)

    logger.info("Project selected: {}".format(getattr(dialog, 'selected_project_name', 'Unknown')))

    # Create and launch our MainWindow after project selection
    from gui.main_window import MainWindow
    selected_project = getattr(dialog, 'selected_project_name', None)
    main_window = MainWindow(state_manager, data_manager, project_manager, selected_project=selected_project)
    main_window.show()

    # Splash already closed; no need to finish splash

    logger.info("MUS1 init complete. Starting application event loop.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()