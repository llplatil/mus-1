"""
Centralized PyQt6 facade for the MUS1 GUI.

All GUI modules should import Qt classes from this module to ensure a single
binding is used across the application. This prevents mixed-binding issues
and stabilizes widget lifecycles.
"""

# Explicitly use PyQt6 only
from PyQt6 import QtCore, QtGui, QtWidgets  # re-exported below via __all__

# Commonly used classes and namespaces re-exported for convenience
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QDateTime,
    QSize,
    QThread,
    QObject,
    pyqtSignal as Signal,
)
from PyQt6.QtGui import (
    QAction,
    QIcon,
    QPixmap,
    QPalette,
    QColor,
    QFont,
    QTextCharFormat,
    QPainter,
    QImage,
    QBrush,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QDialog,
    QMessageBox,
    QMenu,
    QMenuBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSplitter,
    QStackedWidget,
    QLabel,
    QGroupBox,
    QFrame,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDateTimeEdit,
    QCheckBox,
    QTextEdit,
    QScrollArea,
    QSlider,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QSizePolicy,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QDoubleSpinBox,
    QLayout,
    QWizard,
    QWizardPage,
    QDialogButtonBox,
    QRadioButton,
    QButtonGroup,
    QFileDialog,
)

QT_BACKEND = "PyQt6"

__all__ = [
    # Modules
    "QtCore", "QtGui", "QtWidgets",
    # Aliases / constants
    "Signal", "Qt", "QT_BACKEND",
    # Core/GUI
    "QAction", "QIcon", "QPixmap",
    "QApplication", "QMainWindow", "QTabWidget", "QDialog", "QMenu", "QMenuBar",
    "QMessageBox",
    # Widgets/layouts
    "QWidget", "QVBoxLayout", "QHBoxLayout", "QGridLayout", "QSplitter", "QStackedWidget", "QLabel", "QGroupBox", "QFrame",
    "QPushButton", "QListWidget", "QListWidgetItem", "QFormLayout", "QLineEdit", "QComboBox", "QDateTimeEdit", "QCheckBox", "QTextEdit",
    "QScrollArea", "QSlider", "QProgressBar",
    "QTreeWidget", "QTreeWidgetItem", "QAbstractItemView", "QSizePolicy", "QHeaderView", "QTableWidget", "QTableWidgetItem", "QSpinBox", "QDoubleSpinBox", "QLayout",
    "QWizard", "QWizardPage", "QDialogButtonBox", "QRadioButton", "QButtonGroup",
    # Core types/utilities
    "QTimer", "QDateTime", "QSize", "QThread", "QObject", "QFileDialog", "QPalette", "QColor", "QFont", "QTextCharFormat", "QPainter", "QImage", "QBrush", "QTextOption",
]

