"""
Entry point for MUS1 application
"""

from PySide6.QtWidgets import QApplication
import sys
from .gui.main_window import MainWindow
from .core import StateManager

def main():
    app = QApplication(sys.argv)
    state_manager = StateManager()
    window = MainWindow(state_manager)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 