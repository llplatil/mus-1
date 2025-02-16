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

# 1) Bring in relevant classes/functions from core
from core import (
    init_metadata,
    StateManager,
    DataManager,
    ProjectManager
)

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
    splash_pix = QPixmap("path_or_resource_for_splash.png")  # Replace with your image path
    splash = QSplashScreen(splash_pix)
    splash.show()
    # Process events so that the splash screen is displayed immediately
    app.processEvents()

    # Create the core managers
    state_manager = StateManager()
    data_manager = DataManager(state_manager)
    project_manager = ProjectManager(state_manager)

    logger.info("Core managers created. Setting up the MainWindow.")

    # Create and launch our MainWindow
    from gui.main_window import MainWindow
    main_window = MainWindow(state_manager, data_manager, project_manager)
    main_window.show()

    # Once the project is selected/loaded, we close the splash screen
    splash.finish(main_window)

    logger.info("MUS1 init complete. Starting application event loop.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()