from PySide6.QtWidgets import QMainWindow, QTabWidget, QApplication
from PySide6.QtCore import Qt
import sys


class BaseWidget(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MUS1")
        self.resize(1200, 800)
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabPosition(QTabWidget.West)
        self.setCentralWidget(self.tab_widget)
        
    def connect_core(self, state_manager, data_manager, project_manager):
        # Setup references and signals between the GUI and core managers
        pass


def main():
    app = QApplication(sys.argv)
    window = BaseWidget()
    # Here we would connect core managers, e.g.:
    # window.connect_core(state_manager, data_manager, project_manager)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main() 