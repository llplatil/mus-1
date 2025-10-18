# Qt imports - unified PyQt6 facade
from .qt import (
    QMainWindow,
    QTabWidget,
    QDialog,
    QMenu,
    QMenuBar,
    QAction,
    QIcon,
)
from .project_view import ProjectView
from .subject_view import SubjectView
from .experiment_view import ExperimentView
from .lab_view import LabView
from .settings_view import SettingsView
from .user_lab_selection_dialog import UserLabSelectionDialog
from ..core.logging_bus import LoggingEventBus
from ..core.service_factory import ProjectServiceFactory
from .theme_manager import ThemeManager
from ..core.setup_service import get_setup_service
import logging
from pathlib import Path


class GlobalServices:
    """Container for global services that don't depend on projects."""

    def __init__(self):
        self._lab_service = None

    @property
    def lab_service(self):
        """Get or create the global lab service."""
        if self._lab_service is None:
            from .gui_services import LabService
            self._lab_service = LabService()
            self._lab_service.set_services(get_setup_service())
        return self._lab_service

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """
    The main QMainWindow of the MUS1 application, with tabs for different views.
    
    Responsibilities:
    - Manages the tab container for all main views
    - Coordinates theme application across the application
    - Handles global menu actions
    - Manages project selection and view setup
    """
    def __init__(self, project_path=None, selected_project=None, setup_completed=False, theme_manager: ThemeManager | None = None):
        super().__init__()

        # Set object name and class for styling
        self.setObjectName("mainWindow")
        self.setProperty("class", "mus1-main-window")

        # Configure main window
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)  # Enforce minimum size as per UI guidelines

        # Initialize project manager and services
        self.project_path = Path(project_path) if project_path else None
        self.service_factory = None
        self.selected_project_name = selected_project
        self.setup_completed = setup_completed

        # Initialize global services (available even without project)
        self._global_services = GlobalServices()

        # Initialize user and lab selection (will be set later)
        self.selected_user_id = None
        self.selected_lab_id = None

        # Initialize theme manager (provided by main.py)
        self.theme_manager = theme_manager
        
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

    @property
    def project_manager(self):
        """Provide project manager for views that query window().project_manager."""
        try:
            return self.service_factory.project_manager if self.service_factory else None
        except Exception:
            return None

    @property
    def plugin_manager(self):
        """Provide plugin manager for views that query window().plugin_manager."""
        try:
            return self.service_factory.plugin_manager if self.service_factory else None
        except Exception:
            return None

    def update_window_title(self):
        """Sets the window title based on the current project."""
        # Fetch active user profile (if configured)
        try:
            setup_service = get_setup_service()
            profile = setup_service.get_user_profile()
            user_str = f" — {profile.name} <{profile.email}>" if profile else ""
        except Exception:
            user_str = ""

        if self.selected_project_name:
            self.setWindowTitle(f"Mus1 — {self.selected_project_name}{user_str}")
        else:
            # Consistent title when no project is loaded or selected yet
            self.setWindowTitle(f"Mus1 — No Project Loaded{user_str}")

    def create_menu_bar(self):
        """Create the main menu bar with application menus."""
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        
        # File menu
        file_menu = QMenu("&File", self)
        menu_bar.addMenu(file_menu)

        # Add file actions
        setup_wizard_action = QAction("&Setup Wizard...", self)
        setup_wizard_action.triggered.connect(self.show_setup_wizard)
        file_menu.addAction(setup_wizard_action)

        file_menu.addSeparator()

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
        self.lab_view = LabView(self)
        self.project_view = ProjectView(self)
        self.subject_view = SubjectView(self)
        self.experiment_view = ExperimentView(self)
        self.settings_view = SettingsView(self)

        # Immediately provide global services to LabView
        if hasattr(self.lab_view, 'on_services_ready'):
            self.log_bus.log("MainWindow providing global services to LabView", "info", "MainWindow")
            self.lab_view.on_services_ready(self._global_services)
        else:
            self.log_bus.log("LabView does not have on_services_ready method", "warning", "MainWindow")

        # Connect the rename signal from ProjectView
        if hasattr(self.project_view, 'project_renamed'):
             self.project_view.project_renamed.connect(self.handle_project_rename)
        else:
             self.log_bus.log("ProjectView does not have 'project_renamed' signal.", "warning", "MainWindow")

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.lab_view, "Lab")
        self.tab_widget.addTab(self.project_view, "Project")
        self.tab_widget.addTab(self.subject_view, "Subjects")
        self.tab_widget.addTab(self.experiment_view, "Experiments")
        self.tab_widget.addTab(self.settings_view, "Settings")

        # Register navigation panes with log_bus for message display
        self.register_log_observers()

        # Defer tab activation to ensure all setup is complete
        from .qt import QTimer
        QTimer.singleShot(0, lambda: self._activate_initial_tab())
    
    def _activate_initial_tab(self):
        """Activate the initial tab after all setup is complete."""
        # Only activate once we have enough context to avoid early warnings
        if self.selected_project_name is not None or self.selected_user_id is not None:
            self.tab_widget.setCurrentIndex(0)
            self.on_tab_changed(0)

    def register_log_observers(self):
        """Register all navigation panes as log observers."""
        # Each view has a navigation pane that can display logs
        views = [self.lab_view, self.project_view, self.subject_view, self.experiment_view, self.settings_view]

        for view in views:
            if hasattr(view, 'navigation_pane'):
                self.log_bus.add_observer(view.navigation_pane)
                self.log_bus.log(f"Registered log observer for {view.objectName()}", "info", "MainWindow")

    def on_tab_changed(self, index):
        """
        Handle tab change events.
        Updates active log observers and refreshes the current view if needed.
        """
        tab_names = ["Lab", "Project", "Subjects", "Experiments", "Settings"]
        current_tab_name = tab_names[index] if index < len(tab_names) else "Unknown"
        
        # Log the tab change
        self.log_bus.log(f"Switched to {current_tab_name} tab", "info", "MainWindow")
        
        # Deactivate previous view and activate current view
        try:
            prev_index = getattr(self, "_prev_tab_index", None)
            if prev_index is not None and 0 <= prev_index < self.tab_widget.count():
                prev_view = self.tab_widget.widget(prev_index)
                if hasattr(prev_view, "on_deactivated"):
                    prev_view.on_deactivated()
        except Exception:
            pass

        self._prev_tab_index = index

        current_view = self.tab_widget.widget(index)
        
        # Remove redundant navigation pane sizing - BaseView now handles this
        # through its resize event handler
        
        # Activate the current view
        if hasattr(current_view, "on_activated"):
            current_view.on_activated()
    
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
        """Handle user/lab selection followed by project management."""
        # Always show user/lab selection first (unless we already have a project loaded)
        if self.selected_project_name is not None:
            # Project already loaded, just refresh
            return
        else:
            # Always show user/lab selection dialog (it will be pre-populated with saved selections)
            self.show_user_lab_selection_dialog()

    def try_restore_selections(self):
        """Try to restore previously saved user and lab selections."""
        try:
            from ..core.config_manager import get_config

            # Get saved selections
            saved_user_id = get_config("app.selected_user_id", scope="user")
            saved_lab_id = get_config("app.selected_lab_id", scope="user")

            if saved_user_id and saved_lab_id:
                # Validate that the saved selections still exist
                setup_service = get_setup_service()

                # Check if user exists
                users = setup_service.get_all_users()
                if not any(user_data.get('id') == saved_user_id for user_data in users.values()):
                    return False

                # Check if lab exists
                labs = setup_service.get_labs()
                if not any(lab_id == saved_lab_id for lab_id in labs.keys()):
                    return False

                # Selections are valid, restore them
                self.selected_user_id = saved_user_id
                self.selected_lab_id = saved_lab_id

                self.log_bus.log(f"Restored user: {self.selected_user_id}, lab: {self.selected_lab_id}", "info", "MainWindow")
                return True

        except Exception as e:
            self.log_bus.log(f"Failed to restore selections: {e}", "warning", "MainWindow")

        return False

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
            # Initialize project service factory (standardized pattern)
            self.service_factory = ProjectServiceFactory(project_path)

            # Update UI state
            self.selected_project_name = project_name
            self.update_window_title()

            # Initialize views
            self.project_view.set_initial_project(project_name)

            # Set services on views via lifecycle hook - pass factory to all views for consistency
            if hasattr(self.lab_view, 'on_services_ready'):
                self.lab_view.on_services_ready(self.service_factory.gui_services)  # LabView creates lab service internally
            if hasattr(self.project_view, 'on_services_ready'):
                self.project_view.on_services_ready(self.service_factory.gui_services)  # ProjectView creates project service internally
            if hasattr(self.subject_view, 'on_services_ready'):
                self.subject_view.on_services_ready(self.service_factory.gui_services)  # SubjectView creates subject/experiment services internally
            if hasattr(self.experiment_view, 'on_services_ready'):
                self.experiment_view.on_services_ready(self.service_factory.gui_services)  # ExperimentView creates experiment service internally
            if hasattr(self.experiment_view, 'set_plugin_manager') and hasattr(self.service_factory, 'plugin_manager'):
                self.experiment_view.set_plugin_manager(self.service_factory.plugin_manager)  # Set plugin manager on ExperimentView
            if hasattr(self.settings_view, 'on_services_ready'):
                self.settings_view.on_services_ready(self.service_factory.gui_services)  # SettingsView doesn't use services

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
        self.service_factory = None
        self.update_window_title()

    def load_project_path(self, project_path: Path):
        """Loads a project directly from a full path."""
        if not project_path.exists() or not (project_path / "mus1.db").exists():
            self.log_bus.log(f"Invalid project path: {project_path}", "error", "MainWindow")
            self.show_user_lab_selection_dialog()
            return

        try:
            project_name = project_path.name

            # Initialize project service factory (standardized pattern)
            self.service_factory = ProjectServiceFactory(project_path)

            # Update UI state
            self.selected_project_name = project_name
            self.update_window_title()

            # Initialize views
            self.project_view.set_initial_project(project_name)

            # Set services on views via lifecycle hook - pass factory to all views for consistency
            if hasattr(self.lab_view, 'on_services_ready'):
                self.lab_view.on_services_ready(self.service_factory.gui_services)  # LabView creates lab service internally
            if hasattr(self.project_view, 'on_services_ready'):
                self.project_view.on_services_ready(self.service_factory.gui_services)  # ProjectView creates project service internally
            if hasattr(self.subject_view, 'on_services_ready'):
                self.subject_view.on_services_ready(self.service_factory.gui_services)  # SubjectView creates subject/experiment services internally
            if hasattr(self.experiment_view, 'on_services_ready'):
                self.experiment_view.on_services_ready(self.service_factory.gui_services)  # ExperimentView creates experiment service internally
            if hasattr(self.experiment_view, 'set_plugin_manager') and hasattr(self.service_factory, 'plugin_manager'):
                self.experiment_view.set_plugin_manager(self.service_factory.plugin_manager)  # Set plugin manager on ExperimentView
            if hasattr(self.settings_view, 'on_services_ready'):
                self.settings_view.on_services_ready(self.service_factory.gui_services)  # SettingsView doesn't use services

            # Refresh and apply theme
            self.refresh_all_views()
            self.apply_theme()

            self.log_bus.log(f"Project '{project_name}' loaded successfully", "success", "MainWindow")

        except Exception as e:
            self.log_bus.log(f"Error loading project from '{project_path}': {e}", "error", "MainWindow")
            self._reset_project_state()
            self.show_user_lab_selection_dialog()

    def refresh_all_views(self):
        """Refresh data in all views."""
        self.log_bus.log("Refreshing all views...", "info", "MainWindow")
        # Use getattr for safer checks
        if getattr(self.lab_view, 'refresh_lab_data', None):
            self.lab_view.refresh_lab_data()

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
        from .qt import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, Qt

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
            self.show_user_lab_selection_dialog()
        elif choice == "open":
            # Show user/lab selection then proceed to project management
            self.show_user_lab_selection_dialog()

    def discover_existing_projects(self):
        """Discover existing projects from configured locations."""
        from ..core.project_discovery_service import get_project_discovery_service

        discovery_service = get_project_discovery_service()
        return discovery_service.discover_existing_projects()


    def show_user_lab_selection_dialog(self):
        """Show dialog for selecting user and lab, then proceed to project management."""
        dialog = UserLabSelectionDialog(parent=self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Store selected user and lab for later use
            self.selected_user_id = dialog.selected_user_id
            self.selected_lab_id = dialog.selected_lab_id

            selected_project_path = getattr(dialog, 'selected_project_path', None)

            self.log_bus.log(f"Selected user: {self.selected_user_id}, lab: {self.selected_lab_id}", "info", "MainWindow")
            if selected_project_path:
                self.log_bus.log(f"Selected project: {selected_project_path}", "info", "MainWindow")

            # If a project was selected, load it directly
            if selected_project_path:
                self.load_project_path(Path(selected_project_path))
            else:
                # Now switch to project management tab
                self.tab_widget.setCurrentWidget(self.project_view)
                # The project_view will handle project creation/selection from here
            # Activate initial tab flow now that selections are available
            self._activate_initial_tab()
        else:
            # User cancelled the dialog
            self.log_bus.log("User/lab selection cancelled.", "warning", "MainWindow")
            # Close if no project was previously loaded and selection is cancelled
            if not self.selected_project_name:
                 self.log_bus.log("Closing application as no user/lab was selected.", "info", "MainWindow")
                 self.close()

    def show_setup_wizard(self):
        """Show the MUS1 setup wizard dialog."""
        from .setup_wizard import show_setup_wizard
        wizard = show_setup_wizard(self)
        if wizard:
            self.log_bus.log("Setup wizard completed successfully", "success", "MainWindow")
            # Refresh the user/lab selection if needed
            # This would trigger a refresh of any cached lab/user data

    def handle_project_rename(self, new_name: str):
        """Slot to handle the project_renamed signal from ProjectView."""
        self.log_bus.log(f"MainWindow received project rename to: {new_name}", "info", "MainWindow")
        self.selected_project_name = new_name
        self.update_window_title()
        # The project list in ProjectView should already be updated by its own handler.

    def apply_theme(self):
        """Apply the current theme to the application and propagate to all views."""
        if self.theme_manager:
            # Theme palette is applied once in main.py. Here we only propagate
            # the effective theme to widgets for styling and QSS variable usage.
            effective_theme = getattr(self.theme_manager, "get_effective_theme", lambda: "dark")()
            self.setProperty("theme", effective_theme)
            self.style().unpolish(self)
            self.style().polish(self)
            self.propagate_theme_to_views(effective_theme)

    def propagate_theme_to_views(self, theme):
        """Propagate theme changes to all views."""
        for view in [self.lab_view, self.project_view, self.subject_view, self.experiment_view, self.settings_view]:
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
