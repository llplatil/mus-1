from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMessageBox, QHBoxLayout, QStackedWidget, QListWidget
from PySide6.QtWidgets import QComboBox, QPushButton, QLineEdit, QListWidget as QList, QDateTimeEdit
from datetime import datetime
from gui.navigation_pane import NavigationPane 

class ExperimentView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = None  # Will be set via set_core
        self.state_manager = None    # We'll pass this in from main_window or similarly

        main_layout = QHBoxLayout(self)

        # Left navigation (using NavigationPane)
        self.navigation_pane = NavigationPane(self)
        self.navigation_pane.add_button("Add Experiment")
        self.navigation_pane.add_button("View Experiments")
        self.navigation_pane.connect_button_group()
        self.navigation_pane.button_clicked.connect(self.change_subpage)
        main_layout.addWidget(self.navigation_pane)

        # Right side: stacked pages
        self.pages = QStackedWidget()

        # ----- Page: Add Experiment -----
        self.page_add_exp = QWidget()
        ae_layout = QVBoxLayout(self.page_add_exp)
        
        self.expTypeCombo = QComboBox()
        ae_layout.addWidget(self.expTypeCombo)

        self.idLineEdit = QLineEdit()
        ae_layout.addWidget(self.idLineEdit)

        self.subjectComboBox = QComboBox()
        ae_layout.addWidget(QLabel("Subject ID:"))
        ae_layout.addWidget(self.subjectComboBox)

        self.dateRecordedEdit = QDateTimeEdit(datetime.now())
        self.dateRecordedEdit.setCalendarPopup(True)
        ae_layout.addWidget(QLabel("Date Recorded:"))
        ae_layout.addWidget(self.dateRecordedEdit)

        self.csvPathLineEdit = QLineEdit()
        ae_layout.addWidget(QLabel("CSV Path:"))
        ae_layout.addWidget(self.csvPathLineEdit)

        self.arenaPathLineEdit = QLineEdit()
        ae_layout.addWidget(QLabel("Arena Image:"))
        ae_layout.addWidget(self.arenaPathLineEdit)

        self.saveButton = QPushButton("Add Experiment")
        self.saveButton.clicked.connect(self.saveExperiment)
        ae_layout.addWidget(self.saveButton)

        self.page_add_exp.setLayout(ae_layout)
        self.pages.addWidget(self.page_add_exp)

        # ----- Page: View Experiments -----
        self.page_view_exps = QWidget()
        ve_layout = QVBoxLayout(self.page_view_exps)
        ve_layout.addWidget(QLabel("Experiments"))
        self.experimentListWidget = QListWidget()
        ve_layout.addWidget(self.experimentListWidget)
        self.page_view_exps.setLayout(ve_layout)
        self.pages.addWidget(self.page_view_exps)

        main_layout.addWidget(self.pages)
        self.setLayout(main_layout)

        self.navigation_pane.set_button_checked(0) # Set initial selection

    def set_core(self, project_manager, state_manager):
        self.project_manager = project_manager
        self.state_manager = state_manager

    def change_subpage(self, index: int):
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.refresh_data()  # refresh experiment list when viewing them

    def refresh_data(self):
        if not self.state_manager:
            return

        self.expTypeCombo.clear()
        supported_types = sorted(self.state_manager.get_supported_experiment_types())
        for t in supported_types:
            self.expTypeCombo.addItem(t)

        self.experimentListWidget.clear()
        all_experiments = self.state_manager.get_experiments_list()
        for e in all_experiments:
            self.experimentListWidget.addItem(f"{e.id} ({e.type})")

        self.subjectComboBox.clear()
        for sid in self.state_manager.get_subject_ids():
            self.subjectComboBox.addItem(sid)

    def saveExperiment(self):
        if not self.project_manager:
            QMessageBox.warning(self, "Error", "No ProjectManager is set.")
            return

        experiment_id = self.idLineEdit.text().strip()
        exp_type = self.expTypeCombo.currentText()
        subject_id = self.subjectComboBox.currentText().strip()
        recorded_date = self.dateRecordedEdit.dateTime().toPython()

        plugin_params = {}
        csv_path = self.csvPathLineEdit.text().strip()
        arena_path = self.arenaPathLineEdit.text().strip()
        if csv_path:
            plugin_params["csv_path"] = csv_path
        if arena_path:
            plugin_params["arena_path"] = arena_path

        try:
            new_experiment = self.project_manager.add_experiment(
                experiment_id,
                subject_id,
                recorded_date,
                exp_type,
                plugin_params
            )
            QMessageBox.information(self, "Success", f"Experiment '{new_experiment.id}' added.")
            self.navigation_pane.set_button_checked(1)  # Go to "View Experiments" after adding
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def refresh_experiment_list_display(self):
        sorted_exps = self.project_manager.get_sorted_experiments()
        self.experimentListWidget.clear()
        for e in sorted_exps:
            self.experimentListWidget.addItem(f"{e.id} ({e.type})")
        