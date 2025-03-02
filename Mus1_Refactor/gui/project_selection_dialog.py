from pathlib import Path
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox,
    QGridLayout, QFrame
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QPalette, QBrush, QColor, QPainter, QImage


class ProjectSelectionDialog(QDialog):
    def __init__(self, project_manager, parent=None):
        super().__init__(parent)
        self.setStyleSheet("color: white;")
        self.project_manager = project_manager
        self.setWindowTitle("Project Selection")
        self.setModal(True)
        self.resize(600, 400)  # Larger dialog for better layout

        # Base directory for projects
        self.base_dir = Path("projects")
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)
            
        # Set background with M1 logo as darker grayscale watermark
        self.setup_background()
        
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Add some top padding instead of the title
        main_layout.addSpacing(15)
        
        # Two-column layout
        content_layout = QHBoxLayout()
        
        # Left column (New Project)
        left_frame = QFrame(self)
        left_frame.setFrameShape(QFrame.StyledPanel)
        left_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0.3); border-radius: 5px;")
        left_layout = QVBoxLayout(left_frame)
        
        new_project_label = QLabel("Create New Project", left_frame)
        new_project_label.setAlignment(Qt.AlignCenter)
        new_project_label.setStyleSheet("font-weight: bold; color: white;")
        left_layout.addWidget(new_project_label)
        
        # Input for new project name
        self.new_project_line = QLineEdit(left_frame)
        self.new_project_line.setPlaceholderText("Enter new project name")
        self.new_project_line.setStyleSheet("color: white;")
        left_layout.addWidget(self.new_project_line)
        
        # Create project button
        self.new_button = QPushButton("Create New Project", left_frame)
        self.new_button.setAutoDefault(False)
        left_layout.addWidget(self.new_button)
        left_layout.addStretch()
        
        # Right column (Existing Project)
        right_frame = QFrame(self)
        right_frame.setFrameShape(QFrame.StyledPanel)
        right_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0.3); border-radius: 5px;")
        right_layout = QVBoxLayout(right_frame)
        
        existing_project_label = QLabel("Open Existing Project", right_frame)
        existing_project_label.setAlignment(Qt.AlignCenter)
        existing_project_label.setStyleSheet("font-weight: bold; color: white;")
        right_layout.addWidget(existing_project_label)
        
        # Combo box for existing projects
        self.project_combo = QComboBox(right_frame)
        self.project_combo.setMinimumWidth(200)
        self.project_combo.setStyleSheet("color: white;")
        self.refresh_project_list()
        right_layout.addWidget(self.project_combo)
        
        # Open project button
        self.open_button = QPushButton("Open Selected Project", right_frame)
        self.open_button.setAutoDefault(False)
        right_layout.addWidget(self.open_button)
        right_layout.addStretch()
        
        # Add both frames to the content layout
        content_layout.addWidget(left_frame)
        content_layout.addWidget(right_frame)
        
        # Add content layout to main layout
        main_layout.addLayout(content_layout)
        
        # Cancel button at the bottom
        cancel_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel", self)
        cancel_layout.addStretch()
        cancel_layout.addWidget(self.cancel_button)
        cancel_layout.addStretch()
        main_layout.addLayout(cancel_layout)
        
        # Add spacing before the slogan to move it down
        main_layout.addSpacing(15)
        
        # Slogan at the bottom
        slogan_label = QLabel("to move, to infer: open-source vision for mouse models", self)
        slogan_label.setAlignment(Qt.AlignCenter)
        slogan_label.setStyleSheet("font-style: italic; color: white; font-weight: normal;")
        main_layout.addWidget(slogan_label)
        
        # Connect signals
        self.open_button.clicked.connect(self.open_project)
        self.new_button.clicked.connect(self.create_project)
        self.cancel_button.clicked.connect(self.reject)

    def setup_background(self):
        """Set up the background with the M1 logo as a dark grayscale watermark"""
        try:
            # Load the logo (using the PNG version with no background)
            pixmap = QPixmap("assets/m1logo no background.png")
            if pixmap.isNull():
                # Fallback paths
                alternate_paths = [
                    "Mus1_Refactor/assets/m1logo no background.png",
                    "../assets/m1logo no background.png",
                    "m1logo no background.png"
                ]
                for path in alternate_paths:
                    pixmap = QPixmap(path)
                    if not pixmap.isNull():
                        break
                if pixmap.isNull():
                    print("Could not find the logo image")
                    return  # Skip if image not found
            
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
            
            # Scale the logo to fit the dialog while maintaining aspect ratio
            scaled_pixmap = darkened_pixmap.scaled(
                self.width() * 0.8,  # Use 80% of dialog width
                self.height() * 0.8,  # Use 80% of dialog height
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
                
            # Create a semi-transparent version of the logo
            transparent_pixmap = QPixmap(self.size())
            transparent_pixmap.fill(Qt.transparent)
            
            # Center the image in the pixmap
            painter = QPainter(transparent_pixmap)
            painter.setOpacity(0.15)  # 15% opacity for watermark effect
            
            # Calculate center position
            x = (self.width() - scaled_pixmap.width()) / 2
            y = (self.height() - scaled_pixmap.height()) / 2
            
            painter.drawPixmap(int(x), int(y), scaled_pixmap)
            painter.end()
            
            # Set as background
            palette = self.palette()
            # Set a light background color
            palette.setColor(QPalette.Window, QColor(245, 245, 245))
            self.setPalette(palette)
            self.setAutoFillBackground(True)
            
            # Now overlay the watermark
            brush = QBrush(transparent_pixmap)
            palette.setBrush(QPalette.Window, brush)
            self.setPalette(palette)
        except Exception as e:
            print(f"Error setting background: {e}")
            # Fallback to a plain light background
            palette = self.palette()
            palette.setColor(QPalette.Window, QColor(245, 245, 245))
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def refresh_project_list(self):
        self.project_combo.clear()
        for path in self.project_manager.list_available_projects():
            self.project_combo.addItem(path.name)

    def open_project(self):
        selected = self.project_combo.currentText()
        if not selected:
            QMessageBox.warning(self, "Warning", "No project selected.")
            return
        # Verify selected project exists
        available_projects = self.project_manager.list_available_projects()
        project_path = next((p for p in available_projects if p.name == selected), None)
        if project_path is None:
            QMessageBox.warning(self, "Warning", f"Project directory for '{selected}' not found.")
            return
        # Instead of loading the project here, we leave that to the main window after selection
        self.selected_project_name = selected
        self.accept()

    def create_project(self):
        name = self.new_project_line.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a project name.")
            return
        project_path = self.base_dir / name
        try:
            self.project_manager.create_project(project_path, name)
            self.selected_project_name = name
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create project: {e}")

    def reject(self):
        super().reject()
        
    def resizeEvent(self, event):
        """Handle resize events to update the background"""
        super().resizeEvent(event)
        self.setup_background()  # Update background when dialog is resized 