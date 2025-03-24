from PySide6.QtWidgets import QMainWindow, QTabWidget, QDialog, QMenu, QMenuBar, QApplication
from PySide6.QtGui import QAction, QIcon, QPixmap
from gui.project_view import ProjectView
from gui.subject_view import SubjectView
from gui.experiment_view import ExperimentView
from gui.project_selection_dialog import ProjectSelectionDialog
from core.logging_bus import LoggingEventBus
import logging
import sys
from core.theme_manager import ThemeManager
from pathlib import Path
from PySide6.QtCore import Qt

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
    def __init__(self, state_manager, data_manager, project_manager, selected_project=None):
        super().__init__()
        
        # Set object name and class for styling
        self.setObjectName("mainWindow")
        self.setProperty("class", "mus1-main-window")
        
        # Configure main window
        self.setWindowTitle("Mus1")
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)  # Enforce minimum size as per UI guidelines
        
        # Store core managers
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.project_manager = project_manager
        self.selected_project = selected_project
        self.theme_manager = ThemeManager(self.state_manager)
        
        # Get the LoggingEventBus singleton
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("MainWindow initializing", "info", "MainWindow")

        # Create menu bar with application options
        self.create_menu_bar()

        # Create tab widget to hold all views
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("mainTabs")
        self.tab_widget.setProperty("class", "mus1-tab-widget")
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.tab_widget.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.tab_widget)

        # Setup and initialize views
        self.setup_views()
        
        # Apply theme during initialization
        self.apply_theme()
        
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

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.project_view, "Project")
        self.tab_widget.addTab(self.subject_view, "Subjects")
        self.tab_widget.addTab(self.experiment_view, "Experiments")
        
        # Register navigation panes with log_bus for message display
        self.register_log_observers()
        
        # Set initial active tab
        self.tab_widget.setCurrentIndex(0)
        self.on_tab_changed(0)
    
    def register_log_observers(self):
        """Register all navigation panes as log observers."""
        # Each view has a navigation pane that can display logs
        views = [self.project_view, self.subject_view, self.experiment_view]
        
        for view in views:
            if hasattr(view, 'navigation_pane'):
                self.log_bus.add_observer(view.navigation_pane)
                self.log_bus.log(f"Registered log observer for {view.objectName()}", "info", "MainWindow")

    def on_tab_changed(self, index):
        """
        Handle tab change events.
        Updates active log observers and refreshes the current view if needed.
        """
        tab_names = ["Project", "Subjects", "Experiments"]
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
        if self.selected_project is not None:
            # Use pre-selected project
            self.load_project(self.selected_project)
        else:
            # Show project selection dialog
            self.show_project_selection_dialog()

    def load_project(self, project_name):
        """Load a project by name and initialize all views."""
        # First, find the project path based on name
        available_projects = self.project_manager.list_available_projects()
        project_path = next((p for p in available_projects if p.name == project_name), None)
        
        if project_path:
            # Check if this is likely a large project (could be based on file size or other criteria)
            project_state_path = project_path / "project_state.json"
            is_large_project = project_state_path.exists() and project_state_path.stat().st_size > 5 * 1024 * 1024  # 5MB
            
            # Load the project with optimization flag for large projects
            self.project_manager.load_project(project_path, optimize_for_large_files=is_large_project)
            
            # Initialize experiment view
            if hasattr(self.experiment_view, 'set_core'):
                self.experiment_view.set_core(self.project_manager, self.state_manager)

            # Initialize subject view
            if hasattr(self.subject_view, 'set_state_manager'):
                self.subject_view.set_state_manager(self.state_manager)
            else:
                # Fallback if subject_view doesn't have set_state_manager, simply pass state_manager if possible
                if hasattr(self.subject_view, 'set_project_manager'):
                    self.subject_view.set_project_manager(self.state_manager)

            # Initialize project view solely using state_manager
            self.project_view.set_initial_project(project_name)
            
            # Log success
            self.log_bus.log(f"Project '{project_name}' loaded successfully", "success", "MainWindow")

            # Refresh all views
            self.refresh_all_views()
            
            # Apply theme after project loading and view initialization
            self.apply_theme()
        else:
            self.log_bus.log(f"Could not find project path for '{project_name}'", "error", "MainWindow")

    def refresh_all_views(self):
        """Refresh data in all views."""
        if hasattr(self.experiment_view, 'refresh_data'):
            self.experiment_view.refresh_data()
            
        if hasattr(self.subject_view, 'refresh_subject_list_display'):
            self.subject_view.refresh_subject_list_display()
            
        if hasattr(self.project_view, 'refresh_lists'):
            self.project_view.refresh_lists()

    def show_project_selection_dialog(self):
        """Show dialog for selecting a project."""
        dialog = ProjectSelectionDialog(self.project_manager, self)
        
        if dialog.exec() == QDialog.Accepted:
            # Get the selected project name
            chosen_project = getattr(dialog, 'selected_project_name', None)
            
            if chosen_project:
                # Load the selected project
                self.load_project(chosen_project)
            else:
                self.log_bus.log("No project selected from dialog", "warning", "MainWindow")
        else:
            # User cancelled the dialog
            self.log_bus.log("Project selection cancelled, closing application", "warning", "MainWindow")
            self.close()

    def apply_theme(self):
        """Apply the current theme to the application and propagate to all views."""
        effective_theme = self.theme_manager.apply_theme(QApplication.instance())
        self.setProperty("theme", effective_theme)
        self.style().unpolish(self)
        self.style().polish(self)
        self.propagate_theme_to_views(effective_theme)

    def propagate_theme_to_views(self, theme):
        """Propagate theme changes to all views."""
        for view in [self.project_view, self.subject_view, self.experiment_view]:
            if view and hasattr(view, 'update_theme'):
                view.update_theme(theme)

    def change_theme(self, theme_choice):
        """Handle theme changes and propagate to all views."""
        self.state_manager.set_theme_preference(theme_choice)
        self.apply_theme()

    # Additional methods for hooking up signals, responding to user actions, etc.
