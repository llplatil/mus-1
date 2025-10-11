"""
Platform-agnostic Qt facade for the MUS1 GUI.

Automatically detects and uses the best available Qt backend (PySide6 or PyQt6).
All GUI modules should import Qt classes from this module to ensure a single
binding is used across the application. This prevents mixed-binding issues
and maximizes cross-platform compatibility.
"""

# Platform-agnostic Qt backend detection and import
QT_BACKEND = None
QtCore = None
QtGui = None
QtWidgets = None

# Try PySide6 first (better macOS compatibility)
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    QT_BACKEND = "PySide6"
except ImportError:
    # Fall back to PyQt6
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets
        QT_BACKEND = "PyQt6"
    except ImportError:
        raise ImportError(
            "Neither PySide6 nor PyQt6 is available. "
            "Please install a Qt Python binding: pip install PySide6 or pip install PyQt6"
        )

# Commonly used classes and namespaces re-exported for convenience
# Import from the detected backend
if QT_BACKEND == "PySide6":
    from PySide6.QtCore import (
        Qt,
        QTimer,
        QDateTime,
        QSize,
        QThread,
        QObject,
        Signal,
    )
    from PySide6.QtGui import (
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
    from PySide6.QtWidgets import (
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
elif QT_BACKEND == "PyQt6":
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

# API compatibility shims for PySide6 vs PyQt6 differences
if QT_BACKEND == "PySide6":
    # PySide6 uses different enum structures
    QDialog.Accepted = QDialog.DialogCode.Accepted
    QDialog.Rejected = QDialog.DialogCode.Rejected

    # PySide6 uses ColorRole enum differently
    QPalette.Window = QPalette.ColorRole.Window
    QPalette.Base = QPalette.ColorRole.Base
    QPalette.Text = QPalette.ColorRole.Text
    QPalette.Button = QPalette.ColorRole.Button
elif QT_BACKEND == "PyQt6":
    # PyQt6 already has the correct enum structure
    pass


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

