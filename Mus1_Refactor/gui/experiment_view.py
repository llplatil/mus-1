from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMessageBox
from PySide6.QtWidgets import QComboBox, QPushButton, QLineEdit, QListWidget, QDateTimeEdit
from datetime import datetime

class ExperimentView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = None  # Will be set via set_core
        self.state_manager = None    # We'll pass this in from main_window or similarly

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Experiments"))

        # Example UI controls
        self.experimentListWidget = QListWidget()
        layout.addWidget(self.experimentListWidget)

        self.expTypeCombo = QComboBox()
        layout.addWidget(self.expTypeCombo)

        self.idLineEdit = QLineEdit()
        layout.addWidget(self.idLineEdit)

        self.subjectLabel = QLabel("Subject ID:")
        self.subjectComboBox = QComboBox()
        layout.addWidget(self.subjectLabel)
        layout.addWidget(self.subjectComboBox)

        self.dateRecordedLabel = QLabel("Recorded Date:")
        self.dateRecordedEdit = QDateTimeEdit(datetime.now())
        self.dateRecordedEdit.setCalendarPopup(True)
        layout.addWidget(self.dateRecordedLabel)
        layout.addWidget(self.dateRecordedEdit)

        self.csvPathLabel = QLabel("CSV Path:")
        self.csvPathLineEdit = QLineEdit()
        self.csvPathLabel.setVisible(False)
        self.csvPathLineEdit.setVisible(False)
        layout.addWidget(self.csvPathLabel)
        layout.addWidget(self.csvPathLineEdit)

        self.arenaPathLabel = QLabel("Arena Image:")
        self.arenaPathLineEdit = QLineEdit()
        self.arenaPathLabel.setVisible(False)
        self.arenaPathLineEdit.setVisible(False)
        layout.addWidget(self.arenaPathLabel)
        layout.addWidget(self.arenaPathLineEdit)

        self.saveButton = QPushButton("Add Experiment")
        self.saveButton.clicked.connect(self.saveExperiment)
        layout.addWidget(self.saveButton)

        # Hook up the combo box change signal to show/hide required fields
        self.expTypeCombo.currentIndexChanged.connect(self.updatePluginFields)

    def set_core(self, project_manager, state_manager):
        self.project_manager = project_manager
        self.state_manager = state_manager

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

        self.updatePluginFields()

    def updatePluginFields(self):
        """
        UPDATED: Replace 'SomeArenaPlugin' with 'NOR'. 
        Optional: Show/hide fields differently for each plugin type.
        """
        plugin_type = self.expTypeCombo.currentText()

        if plugin_type == "BasicCSVPlot":
            self.csvPathLabel.setVisible(True)
            self.csvPathLineEdit.setVisible(True)
            self.arenaPathLabel.setVisible(True)
            self.arenaPathLineEdit.setVisible(True)

        elif plugin_type == "NOR":  # Replaces "SomeArenaPlugin"
            self.arenaPathLabel.setVisible(True)
            self.arenaPathLineEdit.setVisible(True)
            self.csvPathLabel.setVisible(True)
            self.csvPathLineEdit.setVisible(True)

        # (Optional) If you'd like to handle "OpenField" as well:
        # elif plugin_type == "OpenField":
        #     self.arenaPathLabel.setVisible(True)
        #     self.arenaPathLineEdit.setVisible(True)
        #     self.csvPathLabel.setVisible(False)
        #     self.csvPathLineEdit.setVisible(False)

        else:
            # Default: hide everything if not recognized
            self.csvPathLabel.setVisible(False)
            self.csvPathLineEdit.setVisible(False)
            self.arenaPathLabel.setVisible(False)
            self.arenaPathLineEdit.setVisible(False)

    def saveExperiment(self):
        """
        UPDATED: Replace 'SomeArenaPlugin' references with 'NOR'.
        """
        if not self.project_manager:
            QMessageBox.warning(self, "Error", "No ProjectManager is set.")
            return

        experiment_id = self.idLineEdit.text().strip()
        exp_type = self.expTypeCombo.currentText()
        subject_id = self.subjectComboBox.currentText().strip()

        if not experiment_id:
            QMessageBox.warning(self, "Error", "You must specify an experiment ID.")
            return
        if not subject_id:
            QMessageBox.warning(self, "Error", "You must select a subject ID.")
            return

        plugin_params = {}
        if exp_type == "BasicCSVPlot":
            csv_path = self.csvPathLineEdit.text().strip()
            if not csv_path:
                QMessageBox.warning(self, "Error", "You must specify a CSV path for BasicCSVPlot.")
                return
            plugin_params["csv_path"] = csv_path

        elif exp_type == "NOR":  # Replaces 'SomeArenaPlugin'
            arena_path = self.arenaPathLineEdit.text().strip()
            if arena_path:
                plugin_params["arena_path"] = arena_path

        recorded_date = self.dateRecordedEdit.dateTime().toPython()
        try:
            # Assuming add_experiment expects: experiment_id, subject_id, date, exp_type, plugin_params
            new_experiment = self.project_manager.add_experiment(
                experiment_id,
                subject_id,
                recorded_date,
                exp_type,
                plugin_params
            )
            QMessageBox.information(self, "Success", f"Experiment '{new_experiment.id}' added.")

            # Refresh both subject and experiment lists
            self.project_manager.refresh_all_lists()
            self.refresh_data()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def refresh_experiment_list_display(self):
        sorted_exps = self.project_manager.get_sorted_experiments()
        self.experimentListWidget.clear()
        for e in sorted_exps:
            self.experimentListWidget.addItem(f"{e.id} ({e.type})")
        