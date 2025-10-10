# Qt imports - platform-specific handling
try:
    from PyQt6.QtWidgets import QMainWindow, QTabWidget, QDialog, QMenu, QMenuBar, QApplication
    from PyQt6.QtGui import QAction, QIcon, QPixmap
    QT_BACKEND = "PyQt6"
except ImportError:
    try:
        from PySide6.QtWidgets import QMainWindow, QTabWidget, QDialog, QMenu, QMenuBar, QApplication
        from PySide6.QtGui import QAction, QIcon, QPixmap
        QT_BACKEND = "PySide6"
    except ImportError:
        raise ImportError("Neither PyQt6 nor PySide6 is available. Please install a Qt Python binding.")
from .project_view import ProjectView
from .subject_view import SubjectView
from .experiment_view import ExperimentView
from .settings_view import SettingsView
from .project_selection_dialog import ProjectSelectionDialog
from .gui_services import GUIServiceFactory
from ..core.logging_bus import LoggingEventBus
from ..core.project_manager_clean import ProjectManagerClean
from ..core import ThemeManager
import logging
import sys
from pathlib import Path

logger = logging.getLogger("mus1.gui.main_window")

class MainWindow(QMainWindow):
    """
    The main QMainWindow of the MUS1 application, with tabs for different views.
    
    Responsibilities:
    - Manages the tab container for all main views
    - Coordinates theme application across the application
    - Handles global menu actions
    - Manages project selection and view setup
    """
    def __init__(self, project_path=None, selected_project=None, setup_completed=False):
        super().__init__()

        # Set object name and class for styling
        self.setObjectName("mainWindow")
        self.setProperty("class", "mus1-main-window")

        # Configure main window
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)  # Enforce minimum size as per UI guidelines

        # Initialize project manager and services
        self.project_path = Path(project_path) if project_path else None
        self.project_manager = None
        self.gui_services = None
        self.selected_project_name = selected_project
        self.setup_completed = setup_completed

        # Initialize theme manager (will be updated when project is loaded)
        self.theme_manager = None
        
        # Get the LoggingEventBus singleton
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("MainWindow initializing", "info", "MainWindow")

        # Create menu bar with application options
        self.create_menu_bar()

        # Create tab widget to hold all views
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("mainTabs")
        self.tab_widget.setProperty("class", "mus1-tab-widget")
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.tab_widget)

        # Setup and initialize views
        self.setup_views()
        
        # Apply theme during initialization
        self.apply_theme()
        
        # Set initial window title before project selection
        self.update_window_title()
        
        # Perform project selection (either load selected or show dialog)
        self.perform_project_selection()
        
        # Connect tab changes to update active observers
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # Set window icon using multiple formats for better compatibility
        icon_path = Path(__file__).parent.parent / "themes"
        window_icon = QIcon()
        
        # Add all icon formats for better compatibility
        window_icon.addFile(str(icon_path / "m1logo.ico"))  # For Windows
        window_icon.addFile(str(icon_path / "m1logo no background.icns"))  # For macOS
        window_icon.addFile(str(icon_path / "m1logo no background.png"))  # For Linux/general
        
        self.setWindowIcon(window_icon)

    def update_window_title(self):
        """Sets the window title based on the current project."""
        if self.selected_project_name:
            self.setWindowTitle(f"Mus1 - {self.selected_project_name}")
        else:
            # Consistent title when no project is loaded or selected yet
            self.setWindowTitle("Mus1 - No Project Loaded")

    def create_menu_bar(self):
        """Create the main menu bar with application menus."""
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        
        # File menu
        file_menu = QMenu("&File", self)
        menu_bar.addMenu(file_menu)
        
        # Add file actions
        new_project_action = QAction("&New Project...", self)
        file_menu.addAction(new_project_action)
        
        open_project_action = QAction("&Open Project...", self)
        file_menu.addAction(open_project_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Theme menu
        theme_menu = QMenu("&Theme", self)
        menu_bar.addMenu(theme_menu)
        
        # Add theme actions
        light_theme_action = QAction("&Light", self)
        light_theme_action.triggered.connect(lambda: self.change_theme("light"))
        theme_menu.addAction(light_theme_action)
        
        dark_theme_action = QAction("&Dark", self)
        dark_theme_action.triggered.connect(lambda: self.change_theme("dark"))
        theme_menu.addAction(dark_theme_action)
        
        system_theme_action = QAction("&System Default", self)
        system_theme_action.triggered.connect(lambda: self.change_theme("os"))
        theme_menu.addAction(system_theme_action)
        
        # Help menu
        help_menu = QMenu("&Help", self)
        menu_bar.addMenu(help_menu)
        
        about_action = QAction("&About MUS1", self)
        help_menu.addAction(about_action)

    def setup_views(self):
        """Initialize all view tabs with proper configuration."""
        # Create the main view tabs
        self.project_view = ProjectView(self)
        self.subject_view = SubjectView(self)
        self.experiment_view = ExperimentView(self)
        self.settings_view = SettingsView(self)

        # Connect the rename signal from ProjectView
        if hasattr(self.project_view, 'project_renamed'):
             self.project_view.project_renamed.connect(self.handle_project_rename)
        else:
             self.log_bus.log("ProjectView does not have 'project_renamed' signal.", "warning", "MainWindow")

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.project_view, "Project")
        self.tab_widget.addTab(self.subject_view, "Subjects")
        self.tab_widget.addTab(self.experiment_view, "Experiments")
        self.tab_widget.addTab(self.settings_view, "Settings")

        # Register navigation panes with log_bus for message display
        self.register_log_observers()

        # Set initial active tab
        self.tab_widget.setCurrentIndex(0)
        self.on_tab_changed(0)
    
    def register_log_observers(self):
        """Register all navigation panes as log observers."""
        # Each view has a navigation pane that can display logs
        views = [self.project_view, self.subject_view, self.experiment_view, self.settings_view]

        for view in views:
            if hasattr(view, 'navigation_pane'):
                self.log_bus.add_observer(view.navigation_pane)
                self.log_bus.log(f"Registered log observer for {view.objectName()}", "info", "MainWindow")

    def on_tab_changed(self, index):
        """
        Handle tab change events.
        Updates active log observers and refreshes the current view if needed.
        """
        tab_names = ["Project", "Subjects", "Experiments", "Settings"]
        current_tab_name = tab_names[index] if index < len(tab_names) else "Unknown"
        
        # Log the tab change
        self.log_bus.log(f"Switched to {current_tab_name} tab", "info", "MainWindow")
        
        # Get the current view
        current_view = self.tab_widget.widget(index)
        
        # Remove redundant navigation pane sizing - BaseView now handles this
        # through its resize event handler
        
        # Refresh the current view's data if possible
        self.refresh_current_view(current_view)
    
    def refresh_current_view(self, view):
        """Refresh data in the current view if applicable."""
        # Different views have different refresh methods
        if hasattr(view, 'refresh_data'):
            view.refresh_data()
        elif hasattr(view, 'refresh_lists'):
            view.refresh_lists()
        elif hasattr(view, 'refresh_subject_list_display'):
            view.refresh_subject_list_display()

    def perform_project_selection(self):
        """Handle project selection or load pre-selected project."""
        if self.selected_project_name is not None:
            # Use pre-selected project name
            self.load_project(self.selected_project_name)
        else:
            # Check if setup was just completed
            if self.setup_completed:
                # Show welcome dialog for first project creation
                self.show_welcome_dialog()
            else:
                # Show project selection dialog
                self.show_project_selection_dialog()

    def load_project(self, project_name):
        """
        Loads a project by name using simplified discovery and initialization.
        """
        self.log_bus.log(f"Loading project: {project_name}", "info", "MainWindow")

        # Find project path using simplified discovery
        from ..core.project_discovery_service import get_project_discovery_service
        discovery_service = get_project_discovery_service()
        project_path = discovery_service.find_project_path(project_name)

        if not project_path or not project_path.exists():
            self.log_bus.log(f"Project '{project_name}' not found at {project_path}", "error", "MainWindow")
            self._reset_project_state()
            return False

        try:
            # Initialize project manager
            self.project_manager = ProjectManagerClean(project_path)
            self.gui_services = GUIServiceFactory(self.project_manager)
            self.theme_manager = ThemeManager()

            # Update UI state
            self.selected_project_name = project_name
            self.update_window_title()

            # Initialize views
            self.project_view.set_initial_project(project_name)

            # Set services on views
            if hasattr(self.experiment_view, 'set_gui_services'):
                self.experiment_view.set_gui_services(self.gui_services.create_experiment_service())
            if hasattr(self.subject_view, 'set_gui_services'):
                self.subject_view.set_gui_services(self.gui_services.create_subject_service())
            if hasattr(self.project_view, 'set_gui_services'):
                self.project_view.set_gui_services(self.gui_services.create_project_service())

            # Refresh and apply theme
            self.refresh_all_views()
            self.apply_theme()

            self.log_bus.log(f"Project '{project_name}' loaded successfully", "success", "MainWindow")
            return True

        except Exception as e:
            self.log_bus.log(f"Error loading project '{project_name}': {e}", "error", "MainWindow")
            self._reset_project_state()
            return False

    def _reset_project_state(self):
        """Reset project-related state variables."""
        self.selected_project_name = None
        self.project_manager = None
        self.gui_services = None
        self.update_window_title()

    def load_project_path(self, project_path: Path):
        """Loads a project directly from a full path."""
        if not project_path.exists() or not (project_path / "mus1.db").exists():
            self.log_bus.log(f"Invalid project path: {project_path}", "error", "MainWindow")
            self.show_project_selection_dialog()
            return

        try:
            project_name = project_path.name

            # Initialize project components
            self.project_manager = ProjectManagerClean(project_path)
            self.gui_services = GUIServiceFactory(self.project_manager)
            self.theme_manager = ThemeManager()

            # Update UI state
            self.selected_project_name = project_name
            self.update_window_title()

            # Initialize views
            self.project_view.set_initial_project(project_name)

            # Set services on views
            if hasattr(self.experiment_view, 'set_gui_services'):
                self.experiment_view.set_gui_services(self.gui_services.create_experiment_service())
            if hasattr(self.subject_view, 'set_gui_services'):
                self.subject_view.set_gui_services(self.gui_services.create_subject_service())
            if hasattr(self.project_view, 'set_gui_services'):
                self.project_view.set_gui_services(self.gui_services.create_project_service())

            # Refresh and apply theme
            self.refresh_all_views()
            self.apply_theme()

            self.log_bus.log(f"Project '{project_name}' loaded successfully", "success", "MainWindow")

        except Exception as e:
            self.log_bus.log(f"Error loading project from '{project_path}': {e}", "error", "MainWindow")
            self._reset_project_state()
            self.show_project_selection_dialog()

    def refresh_all_views(self):
        """Refresh data in all views."""
        self.log_bus.log("Refreshing all views...", "info", "MainWindow")
        # Use getattr for safer checks
        if getattr(self.experiment_view, 'refresh_data', None):
            self.experiment_view.refresh_data()

        if getattr(self.subject_view, 'refresh_subject_list_display', None):
            self.subject_view.refresh_subject_list_display()

        if getattr(self.project_view, 'refresh_lists', None):
            # ProjectView refresh might be implicitly handled by set_initial_project
            # but calling it ensures consistency if other lists are added later.
            self.project_view.refresh_lists()

        if getattr(self.settings_view, 'refresh_lists', None):
            self.settings_view.refresh_lists()
        self.log_bus.log("View refresh complete.", "info", "MainWindow")

    def show_welcome_dialog(self):
        """Show welcome dialog after setup completion."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        from PySide6.QtCore import Qt
        from pathlib import Path

        # Check if there are existing projects
        existing_projects = self.discover_existing_projects()

        dialog = QDialog(self)
        dialog.setWindowTitle("Welcome to MUS1!")
        dialog.setMinimumSize(500, 300)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Welcome message
        welcome_label = QLabel("Welcome to MUS1!")
        welcome_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2e7d32;")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(welcome_label)

        # Setup completion message
        setup_msg = QLabel("Your MUS1 setup is complete! Now let's get you started with your first project.")
        setup_msg.setWordWrap(True)
        setup_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(setup_msg)

        layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()

        if existing_projects:
            # Show both create and open options
            create_button = QPushButton("Create New Project")
            create_button.clicked.connect(lambda: self.handle_welcome_choice(dialog, "create"))
            button_layout.addWidget(create_button)

            open_button = QPushButton("Open Existing Project")
            open_button.clicked.connect(lambda: self.handle_welcome_choice(dialog, "open"))
            button_layout.addWidget(open_button)
        else:
            # Only show create option
            create_button = QPushButton("Create Your First Project")
            create_button.clicked.connect(lambda: self.handle_welcome_choice(dialog, "create"))
            button_layout.addWidget(create_button)

        layout.addLayout(button_layout)

        # Show project count if any exist
        if existing_projects:
            count_label = QLabel(f"You have {len(existing_projects)} existing project(s) configured.")
            count_label.setStyleSheet("color: gray; font-size: 11px;")
            count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(count_label)

        dialog.exec()

    def handle_welcome_choice(self, dialog, choice):
        """Handle user's choice from welcome dialog."""
        dialog.accept()

        if choice == "create":
            self.show_project_selection_dialog()
        elif choice == "open":
            # Show project selection but focus on existing projects
            from ..core.project_discovery_service import get_project_discovery_service

            discovery_service = get_project_discovery_service()
            project_root = discovery_service.get_project_root_for_dialog()

            dialog = ProjectSelectionDialog(project_root=str(project_root), parent=self)
            # Could set dialog to show existing projects tab by default
            if dialog.exec() == QDialog.Accepted:
                chosen_project = getattr(dialog, 'selected_project_name', None)
                chosen_path = getattr(dialog, 'selected_project_path', None)
                if chosen_path:
                    try:
                        self.load_project_path(Path(chosen_path))
                    except Exception:
                        if chosen_project:
                            self.load_project(chosen_project)
                elif chosen_project:
                    self.load_project(chosen_project)
                else:
                    self.log_bus.log("No project selected from dialog.", "warning", "MainWindow")
                    self.update_window_title()

    def discover_existing_projects(self):
        """Discover existing projects from configured locations."""
        from ..core.project_discovery_service import get_project_discovery_service

        discovery_service = get_project_discovery_service()
        return discovery_service.discover_existing_projects()


    def show_project_selection_dialog(self):
        """Show dialog for selecting a project."""
        from ..core.project_discovery_service import get_project_discovery_service

        discovery_service = get_project_discovery_service()
        project_root = discovery_service.get_project_root_for_dialog()

        dialog = ProjectSelectionDialog(project_root=str(project_root), parent=self)

        if dialog.exec() == QDialog.Accepted:
            chosen_project = getattr(dialog, 'selected_project_name', None)
            chosen_path = getattr(dialog, 'selected_project_path', None)
            if chosen_path:
                try:
                    self.load_project_path(Path(chosen_path))
                except Exception:
                    if chosen_project:
                        self.load_project(chosen_project)
            elif chosen_project:
                self.load_project(chosen_project) # Use the central load method
            else:
                self.log_bus.log("No project selected from dialog.", "warning", "MainWindow")
                self.update_window_title() # Ensure title is correct
                # Decide if the app should close or stay open with 'No Project'
                # self.close()
        else:
            # User cancelled the dialog
            self.log_bus.log("Project selection cancelled.", "warning", "MainWindow")
            self.update_window_title() # Ensure title is correct
            # Close if no project was previously loaded and selection is cancelled
            if not self.selected_project_name:
                 self.log_bus.log("Closing application as no project was selected.", "info", "MainWindow")
                 self.close()

    def handle_project_rename(self, new_name: str):
        """Slot to handle the project_renamed signal from ProjectView."""
        self.log_bus.log(f"MainWindow received project rename to: {new_name}", "info", "MainWindow")
        self.selected_project_name = new_name
        self.update_window_title()
        # The project list in ProjectView should already be updated by its own handler.

    def apply_theme(self):
        """Apply the current theme to the application and propagate to all views."""
        if self.theme_manager:
            effective_theme = self.theme_manager.apply_theme(QApplication.instance())
            self.setProperty("theme", effective_theme)
            self.style().unpolish(self)
            self.style().polish(self)
            self.propagate_theme_to_views(effective_theme)

    def propagate_theme_to_views(self, theme):
        """Propagate theme changes to all views."""
        for view in [self.project_view, self.subject_view, self.experiment_view, self.settings_view]:
            if view and hasattr(view, 'update_theme'):
                view.update_theme(theme)

    def change_theme(self, theme_choice):
        """Handle theme changes and propagate to all views."""
        if self.theme_manager:
            # Update theme preference in config manager
            effective_theme = self.theme_manager.change_theme(theme_choice)
            # Apply the theme to the application
            self.setProperty("theme", effective_theme)
            self.style().unpolish(self)
            self.style().polish(self)
            self.propagate_theme_to_views(effective_theme)

    # Additional methods for hooking up signals, responding to user actions, etc.
