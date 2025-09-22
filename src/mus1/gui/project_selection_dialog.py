from pathlib import Path
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox,
    QGridLayout, QFrame, QListWidget, QListWidgetItem, QFileDialog, QCheckBox, QWidget,
    QApplication
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QPalette, QBrush, QColor, QPainter, QImage, QIcon
from ..core.project_manager_clean import ProjectManagerClean
from ..core.config_manager import get_config, set_config
from ..core.setup_service import get_setup_service


class ProjectSelectionDialog(QDialog):
    """Dialog for creating or selecting existing projects."""
    
    def __init__(self, project_root=None, parent=None):
        super().__init__(parent)

        self.setObjectName("projectSelectionDialog")
        self.project_root = Path(project_root) if project_root else Path("./projects")
        self.project_manager = None  # Will be initialized when project is selected
        self.selected_project_name = None  # Will be set when a project is selected
        self.selected_project_path = None  # Full path to selected project (string)
        
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

        # Location type (Local/Shared)
        self.location_type_combo = QComboBox(input_group)
        self.location_type_combo.setObjectName("locationTypeCombo")
        self.location_type_combo.setProperty("class", "mus1-combo-box")
        self.location_type_combo.addItems(["Local", "Shared"])  # Default to Local
        self.location_type_combo.currentIndexChanged.connect(lambda _: self.refresh_projects_list())
        input_group_layout.addWidget(self.location_type_combo)

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
        
        # Location selector for existing projects
        self.existing_location_combo = QComboBox(right_frame)
        self.existing_location_combo.setObjectName("existingLocationCombo")
        self.existing_location_combo.setProperty("class", "mus1-combo-box")
        self.existing_location_combo.addItems(["Local", "Shared"])  # Mirrors creation side
        self.existing_location_combo.currentIndexChanged.connect(self.on_existing_location_changed)
        right_layout.addWidget(self.existing_location_combo)

        # Lab selector for shared projects
        self.existing_lab_combo = QComboBox(right_frame)
        self.existing_lab_combo.setObjectName("existingLabCombo")
        self.existing_lab_combo.setProperty("class", "mus1-combo-box")
        self.existing_lab_combo.setVisible(False)
        self.existing_lab_combo.currentIndexChanged.connect(self.refresh_projects_list)
        right_layout.addWidget(self.existing_lab_combo)

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
        
        # Load labs and populate the projects list
        self._labs_cache = {}
        self.load_labs()
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
        """Refresh the list of existing projects using lab-aware discovery."""
        self.projects_list.clear()

        try:
            mode = self.existing_location_combo.currentText().lower()
            if mode == "shared":
                # Lab-aware: list projects registered under the selected lab
                if not self._labs_cache:
                    self.load_labs()
                lab_id = self.existing_lab_combo.currentData()
                if lab_id and lab_id in self._labs_cache:
                    lab = self._labs_cache[lab_id]
                    for proj in lab.get("projects", []):
                        project_path = Path(proj["path"]) if proj.get("path") else None
                        project_name = proj.get("name") or (project_path.name if project_path else "Unknown")
                        display_name = f"{project_name} (Lab: {lab.get('name','')})"
                        item = QListWidgetItem(display_name)
                        item.setData(Qt.UserRole, str(project_path) if project_path else "")
                        item.setData(Qt.UserRole + 1, project_name)
                        self.projects_list.addItem(item)
                else:
                    # No lab selection or no labs; show hint
                    hint = QListWidgetItem("Select a lab to view shared projects")
                    hint.setFlags(hint.flags() & ~Qt.ItemIsSelectable)
                    hint.setForeground(QColor("gray"))
                    self.projects_list.addItem(hint)
            else:
                # Local discovery: use discovery service without lab filtering
                from ..core.project_discovery_service import get_project_discovery_service
                discovery_service = get_project_discovery_service()
                project_paths = discovery_service.discover_existing_projects()
                for project_path in project_paths:
                    project_name = project_path.name
                    item = QListWidgetItem(project_name)
                    item.setData(Qt.UserRole, str(project_path))
                    item.setData(Qt.UserRole + 1, project_name)
                    self.projects_list.addItem(item)
        except Exception as e:
            print(f"Error listing projects: {e}")

        # Show helpful message if no projects found
        if self.projects_list.count() == 0:
            empty_item = QListWidgetItem("No projects found. Create your first project!")
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemIsSelectable)
            empty_item.setForeground(QColor("gray"))
            self.projects_list.addItem(empty_item)
    
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
            # Choose Local or Shared base automatically
            location_choice = self.location_type_combo.currentText().lower()
            if location_choice == "shared":
                shared_root = get_config("storage.shared_root")
                if shared_root:
                    base_path = Path(shared_root) / "Projects"
                else:
                    print("Shared storage not configured")
                    return
            else:
                # Use simplified project discovery to get default location
                from ..core.project_discovery_service import get_project_discovery_service
                discovery_service = get_project_discovery_service()
                base_path = discovery_service.get_project_root_for_dialog()

        # Create the full project directory path
        project_root = base_path / project_name

        try:
            # Check if project already exists
            if (project_root / "mus1.db").exists():
                print(f"Project '{project_name}' already exists")
                return

            # Create project directory
            project_root.mkdir(parents=True, exist_ok=True)

            # Initialize the project with ProjectManagerClean
            project_manager = ProjectManagerClean(project_root)

            # Attempt to associate project with a lab if one exists or is selected
            from ..core.setup_service import get_setup_service
            setup_service = get_setup_service()
            labs = setup_service.get_labs()  # SQL-backed
            chosen_lab_id = None
            # If creating in Shared mode, use selected lab if available
            if self.location_type_combo.currentText().lower() == "shared" and hasattr(self, "create_lab_combo"):
                chosen_lab_id = self.create_lab_combo.currentData()
            # Fallback: if exactly one lab exists
            if not chosen_lab_id and labs and len(labs) == 1:
                chosen_lab_id = next(iter(labs.keys()))
            # If a lab was chosen, set lab_id in project and register in SQL database
            if chosen_lab_id:
                try:
                    project_manager.set_lab_id(chosen_lab_id)
                    # Add project to lab using SQL repository
                    from ..core.schema import Database
                    from ..core.repository import get_repository_factory
                    from ..core.config_manager import get_config_manager

                    config_manager = get_config_manager()
                    db = Database(str(config_manager.db_path))
                    db.create_tables()
                    repo_factory = get_repository_factory(db)
                    repo_factory.labs.add_project(
                        lab_id=chosen_lab_id,
                        project_name=project_name,
                        project_path=project_root,
                        created_date=project_manager.config.date_created
                    )
                except Exception:
                    pass

            # Project creation complete - lab association handled by ProjectManagerClean

            self.selected_project_name = project_name
            self.selected_project_path = str(project_root)
            # Persist last opened project in SQL config (user scope)
            try:
                from ..core.config_manager import set_config
                set_config("app.last_opened_project", self.selected_project_path, scope="user")
            except Exception:
                pass
            self.accept()  # Close dialog with "accept" result

        except Exception as e:
            print(f"Error creating project: {str(e)}")
    
    def select_project(self):
        """Select an existing project."""
        current_item = self.projects_list.currentItem()
        if not current_item:
            # No project selected
            print("Please select a project")
            return

        # Get clean project name (stored separately to avoid lab info in name)
        clean_name = current_item.data(Qt.UserRole + 1)
        if clean_name:
            self.selected_project_name = clean_name
        else:
            # Fallback to text but try to clean it
            text = current_item.text()
            if " (Lab: " in text:
                self.selected_project_name = text.split(" (Lab: ")[0]
            else:
                self.selected_project_name = text

        # Capture full path from user data
        data_path = current_item.data(Qt.UserRole)
        if data_path:
            self.selected_project_path = data_path
        # Persist last opened project
        try:
            from ..core.config_manager import set_config
            set_config("app.last_opened_project", self.selected_project_path, scope="user")
        except Exception:
            pass
        self.accept()  # Close dialog with "accept" result

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def on_existing_location_changed(self):
        """Toggle lab selector visibility based on location and reload labs."""
        is_shared = self.existing_location_combo.currentText().lower() == "shared"
        self.existing_lab_combo.setVisible(is_shared)
        if is_shared:
            self.load_labs()
        self.refresh_projects_list()

    def load_labs(self):
        """Load labs accessible to the current user and populate lab combos."""
        try:
            setup_service = get_setup_service()
            labs = setup_service.get_labs()
            self._labs_cache = labs or {}
            # Populate existing_lab_combo
            self.existing_lab_combo.blockSignals(True)
            self.existing_lab_combo.clear()
            for lab_id, lab in self._labs_cache.items():
                self.existing_lab_combo.addItem(lab.get("name", lab_id), lab_id)
            self.existing_lab_combo.blockSignals(False)
            # Populate create_lab_combo if present/needed
            if not hasattr(self, "create_lab_combo"):
                # Create lab selector under the creation side (visible only in Shared)
                self.create_lab_combo = QComboBox(self)
                self.create_lab_combo.setObjectName("createLabCombo")
                self.create_lab_combo.setProperty("class", "mus1-combo-box")
                self.create_lab_combo.setVisible(False)
                # Insert below location type combo on left panel
                # Since we don't keep direct refs to layouts, add to input_group_layout via parent traversal
                # Safely append to left input group
                # Note: Using the existing input group layout variable is out of scope here; rely on visibility toggles elsewhere
            # Update items
            if hasattr(self, "create_lab_combo"):
                self.create_lab_combo.blockSignals(True)
                self.create_lab_combo.clear()
                for lab_id, lab in self._labs_cache.items():
                    self.create_lab_combo.addItem(lab.get("name", lab_id), lab_id)
                self.create_lab_combo.blockSignals(False)
        except Exception as e:
            print(f"Error loading labs: {e}")

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