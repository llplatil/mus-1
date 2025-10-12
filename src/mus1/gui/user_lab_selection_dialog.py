from pathlib import Path
import os

from .qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox,
    QGridLayout, QFrame, QListWidget, QListWidgetItem, QFileDialog, QWidget, QApplication, QCheckBox,
    Qt, QSize, QPixmap, QPalette, QBrush, QColor, QPainter, QImage, QIcon
)
from ..core.config_manager import get_config, set_config
from ..core.setup_service import get_setup_service


class UserLabSelectionDialog(QDialog):
    """Dialog for selecting user and lab context before project management."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("userLabSelectionDialog")
        self.selected_user_id = None
        self.selected_lab_id = None

        self.setWindowTitle("MUS1 User & Lab Selection")
        self.setMinimumSize(600, 400)

        # Get the current application instance and its stylesheet
        app = QApplication.instance()
        if app:
            self.setStyleSheet(app.styleSheet())

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)

        # Welcome message
        welcome_label = QLabel("Welcome to MUS1")
        welcome_label.setProperty("class", "mus1-title")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(welcome_label)

        subtitle_label = QLabel("Please select your user profile and lab to continue.")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(subtitle_label)

        # User selection section
        user_group = QFrame(self)
        user_group.setProperty("class", "mus1-panel")
        user_group.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        user_layout = QVBoxLayout(user_group)
        user_layout.setContentsMargins(20, 20, 20, 20)

        user_title = QLabel("Select User Profile", user_group)
        user_title.setProperty("class", "mus1-section-title")
        user_layout.addWidget(user_title)

        self.user_combo = QComboBox(user_group)
        self.user_combo.setProperty("class", "mus1-combo-box")
        self.user_combo.currentIndexChanged.connect(self.on_user_changed)
        user_layout.addWidget(self.user_combo)

        main_layout.addWidget(user_group)

        # Lab selection section
        lab_group = QFrame(self)
        lab_group.setProperty("class", "mus1-panel")
        lab_group.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        lab_layout = QVBoxLayout(lab_group)
        lab_layout.setContentsMargins(20, 20, 20, 20)

        lab_title = QLabel("Select Lab", lab_group)
        lab_title.setProperty("class", "mus1-section-title")
        lab_layout.addWidget(lab_title)

        self.lab_combo = QComboBox(lab_group)
        self.lab_combo.setProperty("class", "mus1-combo-box")
        lab_layout.addWidget(self.lab_combo)

        main_layout.addWidget(lab_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.continue_button = QPushButton("Continue to Project Management")
        self.continue_button.setProperty("class", "mus1-primary-button")
        self.continue_button.clicked.connect(self.accept_selection)
        button_layout.addWidget(self.continue_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setProperty("class", "mus1-secondary-button")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        main_layout.addLayout(button_layout)

        # Load data
        self.load_users()
        self.load_labs()

    def load_users(self):
        """Load available user profiles."""
        try:
            setup_service = get_setup_service()
            users = setup_service.get_all_users()  # This would need to be implemented in setup_service

            self.user_combo.clear()
            if not users:
                self.user_combo.addItem("No users configured", None)
                self.continue_button.setEnabled(False)
            else:
                for user_id, user_data in users.items():
                    display_name = f"{user_data.get('name', 'Unknown')} ({user_data.get('email', 'no email')})"
                    self.user_combo.addItem(display_name, user_id)
                self.continue_button.setEnabled(True)

                # Auto-select if only one user
                if len(users) == 1:
                    self.user_combo.setCurrentIndex(0)

        except Exception as e:
            print(f"Error loading users: {e}")
            self.user_combo.addItem("Error loading users", None)
            self.continue_button.setEnabled(False)

    def load_labs(self):
        """Load available labs for the selected user."""
        try:
            setup_service = get_setup_service()
            labs = setup_service.get_labs()

            self.lab_combo.clear()
            if not labs:
                self.lab_combo.addItem("No labs configured", None)
            else:
                for lab_id, lab_data in labs.items():
                    display_name = f"{lab_data.get('name', 'Unknown Lab')} ({lab_data.get('institution', 'Unknown Institution')})"
                    self.lab_combo.addItem(display_name, lab_id)

                # Auto-select if only one lab
                if len(labs) == 1:
                    self.lab_combo.setCurrentIndex(0)

        except Exception as e:
            print(f"Error loading labs: {e}")
            self.lab_combo.addItem("Error loading labs", None)

    def on_user_changed(self, index):
        """Handle user selection change."""
        user_id = self.user_combo.currentData()
        self.selected_user_id = user_id

        # Could filter labs based on user permissions here
        # For now, just update selection
        if user_id:
            self.load_labs()  # Reload labs in case user permissions affect visibility

    def accept_selection(self):
        """Accept the user and lab selection."""
        self.selected_user_id = self.user_combo.currentData()
        self.selected_lab_id = self.lab_combo.currentData()

        if not self.selected_user_id:
            QMessageBox.warning(self, "Selection Required", "Please select a user profile.")
            return

        if not self.selected_lab_id:
            QMessageBox.warning(self, "Selection Required", "Please select a lab.")
            return

        # Store selections for later retrieval
        self.accept()

    def setup_background(self):
        """Set up the background with the M1 logo as a dark grayscale watermark"""
        try:
            # Use the consistent logo asset from themes folder
            from pathlib import Path
            logo_path = str(Path(__file__).parent.parent / "themes" / "m1logo no background.png")
            pixmap = QPixmap(logo_path)

            if (pixmap is None) or pixmap.isNull():
                print("Could not find the logo image")
                return

            # Convert to grayscale and darken
            image = pixmap.toImage()

            # Convert to grayscale and darken while preserving alpha channel
            for y in range(image.height()):
                for x in range(image.width()):
                    pixel = QColor(image.pixel(x, y))
                    # Preserve the alpha channel
                    alpha = pixel.alpha()
                    if alpha > 0:  # Only process non-transparent pixels
                        gray = int(0.299 * pixel.red() + 0.587 * pixel.green() + 0.114 * pixel.blue())
                        # Make it darker (reduce brightness by 50% instead of 70%)
                        gray = max(0, int(gray * 0.5))
                        image.setPixelColor(x, y, QColor(gray, gray, gray, alpha))

            darkened_pixmap = QPixmap.fromImage(image)

            # Scale the logo to fill the entire dialog background using KeepAspectRatioByExpanding
            scaled_pixmap = darkened_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )

            # Create a semi-transparent version of the logo
            transparent_pixmap = QPixmap(self.size())
            transparent_pixmap.fill(Qt.GlobalColor.transparent)

            # Center the image in the pixmap
            painter = QPainter(transparent_pixmap)
            painter.setOpacity(0.15)  # 15% opacity for watermark effect

            # Calculate offsets so the scaled image is centered and covers the dialog completely
            offset_x = (scaled_pixmap.width() - self.width()) / 2
            offset_y = (scaled_pixmap.height() - self.height()) / 2
            painter.drawPixmap(-int(offset_x), -int(offset_y), scaled_pixmap)
            painter.end()

            # Set as background
            palette = self.palette()
            # Set a light background color (PyQt6 ColorRole API)
            palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
            self.setPalette(palette)
            self.setAutoFillBackground(True)

            # Now overlay the watermark
            brush = QBrush(transparent_pixmap)
            palette.setBrush(QPalette.ColorRole.Window, brush)
            self.setPalette(palette)
        except Exception as e:
            print(f"Error setting background: {e}")
            # Fallback to a plain light background
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def resizeEvent(self, event):
        """Handle resize events to update the background"""
        super().resizeEvent(event)
        self.setup_background()  # Update background when dialog is resized 