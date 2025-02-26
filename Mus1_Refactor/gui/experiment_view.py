from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMessageBox, QHBoxLayout, QStackedWidget, QListWidget, QFormLayout
from PySide6.QtWidgets import QComboBox, QPushButton, QLineEdit, QListWidget as QList, QDateTimeEdit
from datetime import datetime
from gui.navigation_pane import NavigationPane 
from PySide6.QtCore import QTimer

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

        # Plugin-specific fields will be added dynamically based on the selected experiment type
        self.pluginFieldsContainer = QWidget()
        self.pluginFieldsLayout = QFormLayout(self.pluginFieldsContainer)
        ae_layout.addWidget(self.pluginFieldsContainer)

        self.expTypeCombo.currentIndexChanged.connect(self.update_plugin_fields_display)

        self.add_experiment_button = QPushButton("Add Experiment")
        self.add_experiment_button.clicked.connect(self.handle_add_experiment)
        ae_layout.addWidget(self.add_experiment_button)

        # Add a notification label to show experiment addition success message
        self.experiment_notification_label = QLabel("")
        ae_layout.addWidget(self.experiment_notification_label)

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
        self.state_manager.register_observer(self.refresh_data)

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

    def handle_add_experiment(self):
        if not self.project_manager:
            QMessageBox.warning(self, "Error", "No ProjectManager is set.")
            return

        experiment_id = self.idLineEdit.text().strip()
        exp_type = self.expTypeCombo.currentText()
        subject_id = self.subjectComboBox.currentText().strip()
        recorded_date = self.dateRecordedEdit.dateTime().toPython()

        plugin_params = {}
        # Gather plugin-specific parameters from dynamic fields
        if (hasattr(self, 'plugin_field_widgets')):
            for field, widget in self.plugin_field_widgets.items():
                value = widget.text().strip()
                plugin_params[field] = value

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
            self.refresh_experiment_list_display()
            # Set notification text
            self.experiment_notification_label.setText("Experiment added successfully!")
            QTimer.singleShot(3000, lambda: self.experiment_notification_label.setText(""))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def refresh_experiment_list_display(self):
        sorted_exps = self.state_manager.get_sorted_list("experiments")
        self.experimentListWidget.clear()
        for e in sorted_exps:
            self.experimentListWidget.addItem(f"{e.id} ({e.type})")

    def update_plugin_fields_display(self):
        # Clear any existing fields in the plugin fields layout
        while self.pluginFieldsLayout.count() > 0:
            child = self.pluginFieldsLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        exp_type = self.expTypeCombo.currentText()
        if not exp_type or not self.project_manager:
            return
        try:
            # Attempt to retrieve the plugin for the selected experiment type
            if hasattr(self.project_manager.plugin_manager, 'get_plugin'):
                plugin = self.project_manager.plugin_manager.get_plugin(exp_type)
            else:
                plugin = self.project_manager.plugin_manager.plugins.get(exp_type)
            if not plugin:
                raise KeyError(f"Plugin for experiment type '{exp_type}' not found.")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", str(e))
            return

        req_fields = plugin.required_fields()
        opt_fields = plugin.optional_fields()

        self.plugin_field_widgets = {}
        for field in req_fields:
            label = QLabel(f"{field} (required):")
            line_edit = QLineEdit()
            self.plugin_field_widgets[field] = line_edit
            self.pluginFieldsLayout.addRow(label, line_edit)

        for field in opt_fields:
            label = QLabel(f"{field} (optional):")
            line_edit = QLineEdit()
            self.plugin_field_widgets[field] = line_edit
            self.pluginFieldsLayout.addRow(label, line_edit)
        