from PySide6.QtWidgets import QMainWindow, QTabWidget, QDialog
from gui.project_view import ProjectView
from gui.subject_view import SubjectView
from gui.experiment_view import ExperimentView
from gui.project_selection_dialog import ProjectSelectionDialog
import logging

logger = logging.getLogger("mus1.gui.main_window")

class MainWindow(QMainWindow):
    """
    The main QMainWindow of the MUS1 application, with tabs for different views.
    """
    def __init__(self, state_manager, data_manager, project_manager):
        super().__init__()
        self.setWindowTitle("MUS1")
        self.resize(1200, 800)
        self.state_manager = state_manager
        self.data_manager = data_manager
        self.project_manager = project_manager

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.setCentralWidget(self.tab_widget)

        self.setup_ui()
        self.perform_project_selection()

    def setup_ui(self):
        # Create new tabs
        self.project_view = ProjectView(self)
        self.subject_view = SubjectView(self)
        self.experiment_view = ExperimentView(self)

        self.tab_widget.addTab(self.project_view, "Project")
        self.tab_widget.addTab(self.subject_view, "Subjects")
        self.tab_widget.addTab(self.experiment_view, "Experiments")

    def perform_project_selection(self):
        dialog = ProjectSelectionDialog(self.project_manager, self)
        if dialog.exec() == QDialog.Accepted:
            # 1) The user picked a project, so do any needed sync
            self.state_manager.sync_supported_experiment_types(self.project_manager.plugin_manager)
            self.state_manager.sync_plugin_metadatas(self.project_manager.plugin_manager)

            # 2) Set up experiment view with new core references
            if hasattr(self.experiment_view, 'set_core'):
                self.experiment_view.set_core(self.project_manager, self.state_manager)

            # 3) IMPORTANT: now tell the ProjectView which project was chosen
            #    (assuming you stored the chosen name in dialog.selected_project_name)
            chosen_project = getattr(dialog, 'selected_project_name', None)
            if chosen_project:
                # A: Either call set_initial_project directly:
                self.project_view.set_initial_project(chosen_project)

                # Or B: Wrap it in a "set_current_project" method:
                # self.set_current_project(chosen_project)

            # 4) Refresh
            if hasattr(self.experiment_view, 'refresh_data'):
                self.experiment_view.refresh_data()
        else:
            self.close()

    # Additional methods for hooking up signals, responding to user actions, etc.
