from pathlib import Path
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox,
    QGridLayout, QFrame, QListWidget, QListWidgetItem, QFileDialog, QCheckBox, QWidget,
    QApplication
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QPalette, QBrush, QColor, QPainter, QImage, QIcon


class ProjectSelectionDialog(QDialog):
    """Dialog for creating or selecting existing projects."""
    
    def __init__(self, project_manager, parent=None):
        super().__init__(parent)
        
        self.setObjectName("projectSelectionDialog")
        self.project_manager = project_manager
        self.selected_project_name = None  # Will be set when a project is selected
        
        self.setWindowTitle("MUS1 Project Selection")
        self.setMinimumSize(700, 400)
        
        # Get the current application instance and its stylesheet
        app = QApplication.instance()
        if app:
            self.setStyleSheet(app.styleSheet())
        
        # Main layout 
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        
        # Left frame: Create new project
        left_frame = QFrame(self)
        left_frame.setObjectName("newProjectPanel")
        left_frame.setProperty("class", "mus1-panel")
        left_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(5)
        
        # New project title
        new_project_title = QLabel("Create New Project", left_frame)
        new_project_title.setObjectName("newProjectTitle")
        new_project_title.setProperty("class", "mus1-title")
        new_project_title.setAlignment(Qt.AlignHCenter)
        left_layout.addWidget(new_project_title)
        
        # Input group for project name and optional location
        input_group = QWidget(left_frame)
        input_group.setProperty("class", "mus1-input-group")
        input_group_layout = QVBoxLayout(input_group)
        input_group_layout.setContentsMargins(5, 5, 5, 5)
        input_group_layout.setSpacing(5)

        self.new_project_line = QLineEdit(input_group)
        self.new_project_line.setObjectName("newProjectInput")
        self.new_project_line.setProperty("class", "mus1-text-input")
        self.new_project_line.setPlaceholderText("Enter new project name")
        input_group_layout.addWidget(self.new_project_line)

        self.custom_location_check = QCheckBox("Use custom location", input_group)
        self.custom_location_check.setObjectName("customLocationCheck")
        self.custom_location_check.toggled.connect(self.toggle_location_input)
        input_group_layout.addWidget(self.custom_location_check)

        self.location_line = QLineEdit(input_group)
        self.location_line.setObjectName("locationInput")
        self.location_line.setProperty("class", "mus1-text-input")
        self.location_line.setPlaceholderText("Project location (optional)")
        self.location_line.setVisible(False)
        input_group_layout.addWidget(self.location_line)

        self.browse_button = QPushButton("Browse...", input_group)
        self.browse_button.setObjectName("browseButton")
        self.browse_button.setProperty("class", "mus1-secondary-button")
        self.browse_button.clicked.connect(self.browse_location)
        self.browse_button.setVisible(False)
        input_group_layout.addWidget(self.browse_button)

        left_layout.addWidget(input_group)
        
        # Spacer
        left_layout.addStretch()
        
        # Create project button
        self.new_button = QPushButton("Create New Project", left_frame)
        self.new_button.setObjectName("createButton")
        self.new_button.setProperty("class", "mus1-primary-button")
        self.new_button.clicked.connect(self.create_new_project)
        left_layout.addWidget(self.new_button)
        
        # Right frame: Existing projects
        right_frame = QFrame(self)
        right_frame.setObjectName("existingProjectsPanel")
        right_frame.setProperty("class", "mus1-panel")
        right_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(5)
        
        # Existing projects title
        existing_title = QLabel("Existing Projects", right_frame)
        existing_title.setObjectName("existingProjectsTitle")
        existing_title.setProperty("class", "mus1-title")
        existing_title.setAlignment(Qt.AlignHCenter)
        right_layout.addWidget(existing_title)
        
        # Projects list
        self.projects_list = QListWidget(right_frame)
        self.projects_list.setObjectName("projectsList")
        self.projects_list.setProperty("class", "mus1-list-view")
        self.projects_list.itemDoubleClicked.connect(self.select_project)
        right_layout.addWidget(self.projects_list)
        
        # Open project button
        self.open_button = QPushButton("Open Selected Project", right_frame)
        self.open_button.setObjectName("openButton")
        self.open_button.setProperty("class", "mus1-primary-button")
        self.open_button.clicked.connect(self.select_project)
        right_layout.addWidget(self.open_button)
        
        # Add frames to the main layout
        main_layout.addWidget(left_frame)
        main_layout.addWidget(right_frame)
        
        # Populate the projects list
        self.refresh_projects_list()

        # Connect Enter key to create project
        self.new_project_line.returnPressed.connect(self.create_new_project)

    def toggle_location_input(self, checked):
        """Show or hide the custom location input based on checkbox state."""
        self.location_line.setVisible(checked)
        self.browse_button.setVisible(checked)
        
    def browse_location(self):
        """Open a file dialog to select a directory."""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Project Location",
            os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly
        )
        if directory:
            self.location_line.setText(directory)
    
    def refresh_projects_list(self):
        """Refresh the list of existing projects."""
        self.projects_list.clear()
        projects = self.project_manager.list_available_projects()
        for project_path in projects:
            item = QListWidgetItem(project_path.name)
            self.projects_list.addItem(item)
    
    def create_new_project(self):
        """Create a new project with the given name."""
        project_name = self.new_project_line.text().strip()
        
        if not project_name:
            # Handle empty project name
            # In a real app, you might show a dialog
            print("Project name cannot be empty")
            return
        
        # Get custom location if enabled
        location = None
        if self.custom_location_check.isChecked():
            location = self.location_line.text().strip()
            if not location:
                # Handle empty location when checkbox is checked
                print("Please specify a location or uncheck 'Use custom location'")
                return
        
        # Determine base path for the new project
        if self.custom_location_check.isChecked() and location:
            base_path = Path(location)
        else:
            base_path = self.project_manager.get_projects_directory()

        # Create the full project directory path
        project_root = base_path / project_name

        try:
            self.project_manager.create_project(project_root, project_name)
            self.selected_project_name = project_name
            self.accept()  # Close dialog with "accept" result
        except Exception as e:
            # Handle errors (e.g., project already exists)
            print(f"Error creating project: {str(e)}")
    
    def select_project(self):
        """Select an existing project."""
        current_item = self.projects_list.currentItem()
        if not current_item:
            # No project selected
            # In a real app, you might show a dialog
            print("Please select a project")
            return
        
        self.selected_project_name = current_item.text()
        self.accept()  # Close dialog with "accept" result

    def resizeEvent(self, event):
        super().resizeEvent(event)

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
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
                
            # Create a semi-transparent version of the logo
            transparent_pixmap = QPixmap(self.size())
            transparent_pixmap.fill(Qt.transparent)
            
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

    def resizeEvent(self, event):
        """Handle resize events to update the background"""
        super().resizeEvent(event)
        self.setup_background()  # Update background when dialog is resized 