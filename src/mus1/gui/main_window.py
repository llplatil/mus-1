from PySide6.QtWidgets import QMainWindow, QTabWidget, QDialog, QMenu, QMenuBar, QApplication
from PySide6.QtGui import QAction, QIcon, QPixmap
from .project_view import ProjectView
from .subject_view import SubjectView
from .experiment_view import ExperimentView
from .project_selection_dialog import ProjectSelectionDialog
from ..core.logging_bus import LoggingEventBus
from ..core import ThemeManager, PluginManager
import logging
import sys
from pathlib import Path
from PySide6.QtCore import Qt, Signal

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
    def __init__(self, state_manager, data_manager, project_manager, plugin_manager, selected_project=None):
        super().__init__()
        
        # Set object name and class for styling
        self.setObjectName("mainWindow")
        self.setProperty("class", "mus1-main-window")
        
        # Configure main window
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)  # Enforce minimum size as per UI guidelines
        
        # Store core managers
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.project_manager = project_manager
        self.plugin_manager = plugin_manager
        self.selected_project_name = selected_project
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

        # Connect the rename signal from ProjectView
        if hasattr(self.project_view, 'project_renamed'):
             self.project_view.project_renamed.connect(self.handle_project_rename)
        else:
             self.log_bus.log("ProjectView does not have 'project_renamed' signal.", "warning", "MainWindow")

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
        if self.selected_project_name is not None:
            # Use pre-selected project name
            self.load_project(self.selected_project_name)
        else:
            # Show project selection dialog
            self.show_project_selection_dialog()

    def load_project(self, project_name):
        """
        Loads a project by name, updates UI including title, initializes views,
        and refreshes data. This is the central method for loading projects.
        """
        self.log_bus.log(f"Attempting to load project: {project_name}", "info", "MainWindow")
        available_projects = self.project_manager.list_available_projects()
        project_path = next((p for p in available_projects if p.name == project_name), None)

        if project_path:
            try:
                # Check for large project state file
                project_state_path = project_path / "project_state.json"
                is_large_project = project_state_path.exists() and project_state_path.stat().st_size > 5 * 1024 * 1024  # 5MB

                # Load the project using project_manager
                self.project_manager.load_project(project_path, optimize_for_large_files=is_large_project)

                # --- Project Loaded Successfully ---
                self.selected_project_name = project_name
                self.update_window_title() # Update the window title

                # Notify views of the newly loaded project via their refresh methods
                # ExperimentView subscribes to StateManager changes automatically and will refresh below.
                # SubjectView likewise handles state updates internally.
                
                # Project View - Update its internal state/display
                # This call ensures ProjectView's labels/fields reflect the loaded project
                self.project_view.set_initial_project(project_name)

                self.log_bus.log(f"Project '{project_name}' loaded successfully.", "success", "MainWindow")

                # Refresh data across all views
                self.refresh_all_views()

                # Re-apply theme in case project settings affect it
                self.apply_theme()

            except Exception as e:
                self.log_bus.log(f"Error loading project '{project_name}': {e}", "error", "MainWindow")
                # Reset state on error
                self.selected_project_name = None
                self.update_window_title() # Update title to 'No Project Loaded'
                # Optionally, show an error dialog to the user here
        else:
            self.log_bus.log(f"Could not find project path for '{project_name}'. Available: {[p.name for p in available_projects]}", "error", "MainWindow")
            # Reset state if project not found
            self.selected_project_name = None
            self.update_window_title() # Update title to 'No Project Loaded'
            # Optionally, show an error dialog

    def load_project_path(self, project_path: Path):
        """Loads a project directly from a full path, then updates UI."""
        try:
            project_name = project_path.name
            project_state_path = project_path / "project_state.json"
            is_large_project = project_state_path.exists() and project_state_path.stat().st_size > 5 * 1024 * 1024
            self.project_manager.load_project(project_path, optimize_for_large_files=is_large_project)
            self.selected_project_name = project_name
            self.update_window_title()
            self.project_view.set_initial_project(project_name)
            self.refresh_all_views()
            self.apply_theme()
            self.log_bus.log(f"Project '{project_name}' loaded successfully from path.", "success", "MainWindow")
        except Exception as e:
            self.log_bus.log(f"Error loading project from '{project_path}': {e}", "error", "MainWindow")

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
        self.log_bus.log("View refresh complete.", "info", "MainWindow")

    def show_project_selection_dialog(self):
        """Show dialog for selecting a project."""
        dialog = ProjectSelectionDialog(self.project_manager, self)

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
