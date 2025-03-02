from PySide6.QtWidgets import QMainWindow, QTabWidget, QDialog
from gui.project_view import ProjectView
from gui.subject_view import SubjectView
from gui.experiment_view import ExperimentView
from gui.project_selection_dialog import ProjectSelectionDialog
from core.logging_bus import LoggingEventBus
import logging

logger = logging.getLogger("mus1.gui.main_window")

class MainWindow(QMainWindow):
    """
    The main QMainWindow of the MUS1 application, with tabs for different views.
    """
    def __init__(self, state_manager, data_manager, project_manager, selected_project=None):
        super().__init__()
        self.setWindowTitle("mus1")
        self.resize(1200, 800)
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.project_manager = project_manager
        self.selected_project = selected_project
        
        # Get the LoggingEventBus singleton
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("MainWindow initializing", "info", "MainWindow")

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.setCentralWidget(self.tab_widget)

        self.setup_ui()
        self.perform_project_selection()
        
        # Connect tab changes to update active log observer
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def setup_ui(self):
        # Create new tabs
        self.project_view = ProjectView(self)
        self.subject_view = SubjectView(self)
        self.experiment_view = ExperimentView(self)

        self.tab_widget.addTab(self.project_view, "Project")
        self.tab_widget.addTab(self.subject_view, "Subjects")
        self.tab_widget.addTab(self.experiment_view, "Experiments")
        
        # Register navigation panes with log_bus
        if hasattr(self.project_view, 'navigation_pane'):
            self.log_bus.add_observer(self.project_view.navigation_pane)
            
        if hasattr(self.subject_view, 'navigation_pane'):
            self.log_bus.add_observer(self.subject_view.navigation_pane)
            
        if hasattr(self.experiment_view, 'navigation_pane'):
            self.log_bus.add_observer(self.experiment_view.navigation_pane)
        
        # Set initial active tab
        self.on_tab_changed(0)

    def on_tab_changed(self, index):
        """Update which log observers are considered 'active'."""
        # This method is a placeholder for more advanced observer management
        # In a more sophisticated implementation, you might want to:
        # 1. Prioritize logs to the active tab
        # 2. Filter logs by relevance to the current tab
        # 3. Only send certain logs to certain observers
        
        # Here we're just logging the tab change
        tab_names = ["Project", "Subjects", "Experiments"]
        self.log_bus.log(f"Switched to {tab_names[index]} tab", "info", "MainWindow")

    def perform_project_selection(self):
        # If a project was already selected (passed from main), perform sync and update views
        if self.selected_project is not None:
            # Sync data with the plugin_manager
            self.state_manager.sync_supported_experiment_types(self.project_manager.plugin_manager)
            self.state_manager.sync_plugin_metadatas(self.project_manager.plugin_manager)

            # Update experiment view if applicable
            if hasattr(self.experiment_view, 'set_core'):
                self.experiment_view.set_core(self.project_manager, self.state_manager)

            # Set the initial project in the project view
            self.project_view.set_initial_project(self.selected_project)
            self.log_bus.log(f"Project '{self.selected_project}' selected", "success", "MainWindow")

            # Refresh experiment view if needed
            if hasattr(self.experiment_view, 'refresh_data'):
                self.experiment_view.refresh_data()
        else:
            # No project pre-selected, so display the project selection dialog
            dialog = ProjectSelectionDialog(self.project_manager, self)
            if dialog.exec() == QDialog.Accepted:
                # Sync and update views
                self.state_manager.sync_supported_experiment_types(self.project_manager.plugin_manager)
                self.state_manager.sync_plugin_metadatas(self.project_manager.plugin_manager)

                if hasattr(self.experiment_view, 'set_core'):
                    self.experiment_view.set_core(self.project_manager, self.state_manager)

                chosen_project = getattr(dialog, 'selected_project_name', None)
                if chosen_project:
                    self.project_view.set_initial_project(chosen_project)
                    self.log_bus.log(f"Project '{chosen_project}' selected", "success", "MainWindow")

                if hasattr(self.experiment_view, 'refresh_data'):
                    self.experiment_view.refresh_data()
            else:
                self.log_bus.log("No project selected, closing application", "warning", "MainWindow")
                self.close()

    # Additional methods for hooking up signals, responding to user actions, etc.
