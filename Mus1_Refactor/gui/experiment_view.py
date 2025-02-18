from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMessageBox, QHBoxLayout, QStackedWidget, QListWidget
from PySide6.QtWidgets import QComboBox, QPushButton, QLineEdit, QListWidget as QList, QDateTimeEdit
from datetime import datetime

class ExperimentView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = None  # Will be set via set_core
        self.state_manager = None    # We'll pass this in from main_window or similarly

        main_layout = QHBoxLayout(self)

        # Left navigation to pick sub-pages
        self.nav_list = QListWidget()
        self.nav_list.addItems(["View Experiments", "Add Experiment"])
        self.nav_list.currentRowChanged.connect(self.change_subpage)
        main_layout.addWidget(self.nav_list)

        # Right side: stacked pages
        self.pages = QStackedWidget()

        # ----- Page: View Experiments -----
        self.page_view_exps = QWidget()
        ve_layout = QVBoxLayout(self.page_view_exps)
        ve_layout.addWidget(QLabel("Experiments"))
        self.experimentListWidget = QListWidget()
        ve_layout.addWidget(self.experimentListWidget)
        self.page_view_exps.setLayout(ve_layout)
        self.pages.addWidget(self.page_view_exps)

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

        main_layout.addWidget(self.pages)
        self.setLayout(main_layout)

        self.nav_list.setCurrentRow(0)

    def set_core(self, project_manager, state_manager):
        self.project_manager = project_manager
        self.state_manager = state_manager

    def change_subpage(self, index: int):
        self.pages.setCurrentIndex(index)
        if index == 0:
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
            self.nav_list.setCurrentRow(0)  # Go back to "View Experiments"
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def refresh_experiment_list_display(self):
        sorted_exps = self.project_manager.get_sorted_experiments()
        self.experimentListWidget.clear()
        for e in sorted_exps:
            self.experimentListWidget.addItem(f"{e.id} ({e.type})")
        