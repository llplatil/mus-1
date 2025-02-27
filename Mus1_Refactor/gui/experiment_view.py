from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QMessageBox, QHBoxLayout, 
                           QStackedWidget, QListWidget, QFormLayout, QComboBox, QPushButton, 
                           QLineEdit, QListWidget as QList, QDateTimeEdit, QGroupBox, 
                           QCheckBox, QScrollArea)
from PySide6.QtCore import QTimer, Qt
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
        
        # Experiment Type Selection
        ae_layout.addWidget(QLabel("Experiment Type:"))
        self.expTypeCombo = QComboBox()
        self.expTypeCombo.currentIndexChanged.connect(self.on_experiment_type_changed)
        ae_layout.addWidget(self.expTypeCombo)

        # Processing Stage Selection
        ae_layout.addWidget(QLabel("Processing Stage:"))
        self.stageCombo = QComboBox()
        self.stageCombo.currentIndexChanged.connect(self.on_stage_changed)
        ae_layout.addWidget(self.stageCombo)

        # Data Source Selection
        ae_layout.addWidget(QLabel("Data Source:"))
        self.sourceCombo = QComboBox()
        self.sourceCombo.currentIndexChanged.connect(self.update_plugin_selection)
        ae_layout.addWidget(self.sourceCombo)

        # Basic Experiment Info
        form_layout = QFormLayout()
        
        self.idLineEdit = QLineEdit()
        form_layout.addRow(QLabel("Experiment ID:"), self.idLineEdit)

        self.subjectComboBox = QComboBox()
        form_layout.addRow(QLabel("Subject ID:"), self.subjectComboBox)

        self.dateRecordedEdit = QDateTimeEdit(datetime.now())
        self.dateRecordedEdit.setCalendarPopup(True)
        form_layout.addRow(QLabel("Date Recorded:"), self.dateRecordedEdit)
        
        ae_layout.addLayout(form_layout)
        
        # Plugin Selection Section
        self.plugin_selection_group = QGroupBox("Available Plugins")
        plugin_selection_layout = QVBoxLayout()
        self.plugin_selection_group.setLayout(plugin_selection_layout)
        
        self.plugin_checkboxes = {}  # Will store plugin checkboxes
        self.plugin_info_labels = {}  # Will store plugin descriptions
        
        # Add scrollable area for plugin selection
        plugin_scroll = QScrollArea()
        plugin_scroll.setWidgetResizable(True)
        plugin_scroll_widget = QWidget()
        self.plugin_scroll_layout = QVBoxLayout(plugin_scroll_widget)
        plugin_scroll.setWidget(plugin_scroll_widget)
        plugin_selection_layout.addWidget(plugin_scroll)
        
        ae_layout.addWidget(self.plugin_selection_group)
        
        # Plugin Fields Section (will be dynamically populated)
        self.plugin_fields_scroll = QScrollArea()
        self.plugin_fields_scroll.setWidgetResizable(True)
        self.plugin_fields_widget = QWidget()
        self.plugin_fields_layout = QVBoxLayout(self.plugin_fields_widget)
        self.plugin_fields_scroll.setWidget(self.plugin_fields_widget)
        ae_layout.addWidget(self.plugin_fields_scroll)
        
        # Add Experiment Button
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
        
        # Storage for plugin field widgets
        self.plugin_field_widgets = {}

    def set_core(self, project_manager, state_manager):
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.state_manager.register_observer(self.refresh_data)
        self.refresh_data()

    def change_subpage(self, index: int):
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.refresh_data()  # refresh experiment list when viewing them

    def refresh_data(self):
        if not self.state_manager:
            return

        # Update experiment types dropdown
        self.expTypeCombo.clear()
        supported_types = sorted(self.state_manager.get_supported_experiment_types())
        for t in supported_types:
            self.expTypeCombo.addItem(t)

        # Update experiment list
        self.experimentListWidget.clear()
        all_experiments = self.state_manager.get_sorted_list("experiments")
        for e in all_experiments:
            self.experimentListWidget.addItem(f"{e.id} ({e.type})")

        # Update subject dropdown
        self.subjectComboBox.clear()
        for sid in self.state_manager.get_subject_ids():
            self.subjectComboBox.addItem(sid)
            
        # If there's at least one experiment type, update plugin selection
        if self.expTypeCombo.count() > 0:
            self.on_experiment_type_changed(0)

    def on_experiment_type_changed(self, index):
        """When experiment type changes, update processing stages, data sources, and plugin selection."""
        if index < 0 or not self.project_manager:
            return

        exp_type = self.expTypeCombo.currentText()

        # Clear plugin selections
        self.clear_plugin_selection()

        # Update Processing Stage combo based on exp_type
        stages = self.state_manager.get_compatible_processing_stages(self.project_manager.plugin_manager, exp_type)
        self.stageCombo.clear()
        for stage in stages:
            self.stageCombo.addItem(stage)

        # Trigger update of Data Source combo
        self.on_stage_changed(0)

        # Update plugin selection
        self.update_plugin_selection()

    def clear_plugin_selection(self):
        """Clear all plugin selection widgets."""
        # Clear checkboxes
        if hasattr(self, 'plugin_checkboxes'):
            for checkbox in self.plugin_checkboxes.values():
                checkbox.deleteLater()
            self.plugin_checkboxes.clear()

        # Clear info labels
        if hasattr(self, 'plugin_info_labels'):
            for label in self.plugin_info_labels.values():
                label.deleteLater()
            self.plugin_info_labels.clear()

        # Remove all items from layout
        while self.plugin_scroll_layout.count():
            item = self.plugin_scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    subitem = item.layout().takeAt(0)
                    if subitem.widget():
                        subitem.widget().deleteLater()

        # Clear plugin fields
        self.update_plugin_fields()

    def update_plugin_fields(self):
        """Update the plugin fields based on selected plugins."""
        # Clear existing plugin fields
        while self.plugin_fields_layout.count():
            item = self.plugin_fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.plugin_field_widgets = {}
        
        # Get selected plugins based on criteria
        exp_type = self.expTypeCombo.currentText()
        stage = self.stageCombo.currentText()
        source = self.sourceCombo.currentText()

        selected_plugins = self.project_manager.plugin_manager.get_plugins_by_criteria(exp_type, stage, source)

        # Create UI for each selected plugin
        for plugin in selected_plugins:
            plugin_name = plugin.plugin_self_metadata().name
            group_box = QGroupBox(plugin_name)
            group_layout = QFormLayout()
            group_box.setLayout(group_layout)

            # Add required fields
            req_fields = plugin.required_fields()
            for field in req_fields:
                label = QLabel(f"{field} (required):")
                line_edit = QLineEdit()
                group_layout.addRow(label, line_edit)
                self.plugin_field_widgets[(plugin_name, field)] = line_edit

            # Add optional fields
            opt_fields = plugin.optional_fields()
            for field in opt_fields:
                label = QLabel(f"{field} (optional):")
                line_edit = QLineEdit()
                group_layout.addRow(label, line_edit)
                self.plugin_field_widgets[(plugin_name, field)] = line_edit

            self.plugin_fields_layout.addWidget(group_box)

        self.plugin_fields_layout.addStretch()

    def on_stage_changed(self, index):
        """When processing stage changes, update data source combo accordingly."""
        exp_type = self.expTypeCombo.currentText()
        if not exp_type:
            return

        stage = self.stageCombo.currentText()
        sources = self.state_manager.get_compatible_data_sources(self.project_manager.plugin_manager, exp_type, stage)
        self.sourceCombo.clear()
        for src in sources:
            self.sourceCombo.addItem(src)

        self.update_plugin_selection()

    def update_plugin_selection(self):
        """Update the plugin selection checkboxes based on current experiment type, stage, and source."""
        exp_type = self.expTypeCombo.currentText()
        stage = self.stageCombo.currentText()
        source = self.sourceCombo.currentText()

        # Clear previous plugin selection UI
        self.clear_plugin_selection()

        # Get compatible plugins based on criteria
        compatible_plugins = self.project_manager.plugin_manager.get_plugins_by_criteria(exp_type, stage, source)

        for plugin in compatible_plugins:
            metadata = plugin.plugin_self_metadata()
            checkbox = QCheckBox(metadata.name)
            checkbox.stateChanged.connect(self.update_plugin_fields)
            info_label = QLabel(f"<i>{metadata.description}</i>")
            info_label.setWordWrap(True)
            info_label.setStyleSheet("color: gray;")

            plugin_container = QVBoxLayout()
            plugin_container.addWidget(checkbox)
            plugin_container.addWidget(info_label)

            self.plugin_scroll_layout.addLayout(plugin_container)

            if not hasattr(self, 'plugin_checkboxes'):
                self.plugin_checkboxes = {}
            self.plugin_checkboxes[metadata.name] = checkbox
            if not hasattr(self, 'plugin_info_labels'):
                self.plugin_info_labels = {}
            self.plugin_info_labels[metadata.name] = info_label

    def handle_add_experiment(self):
        """Handle adding a new experiment."""
        if not self.project_manager:
            QMessageBox.warning(self, "Error", "No ProjectManager is set.")
            return

        # Get basic experiment info
        experiment_id = self.idLineEdit.text().strip()
        exp_type = self.expTypeCombo.currentText()
        processing_stage = self.stageCombo.currentText()
        data_source = self.sourceCombo.currentText()
        subject_id = self.subjectComboBox.currentText().strip()
        recorded_date = self.dateRecordedEdit.dateTime().toPython()

        # Get selected plugins from the updated plugin checkboxes
        selected_plugins = []
        if hasattr(self, 'plugin_checkboxes'):
            for name, checkbox in self.plugin_checkboxes.items():
                if checkbox.isChecked():
                    for plugin in self.project_manager.plugin_manager.get_all_plugins():
                        if plugin.plugin_self_metadata().name == name:
                            selected_plugins.append(plugin)
                            break

        if not selected_plugins:
            QMessageBox.warning(self, "Error", "Please select at least one plugin.")
            return

        # Validate basic fields
        if not experiment_id:
            QMessageBox.warning(self, "Error", "Please enter an experiment ID.")
            return

        if not subject_id:
            QMessageBox.warning(self, "Error", "Please select a subject.")
            return

        # Gather plugin parameters
        plugin_params = {}
        for key, widget in self.plugin_field_widgets.items():
            plugin_name, field = key
            if plugin_name not in plugin_params:
                plugin_params[plugin_name] = {}
            plugin_params[plugin_name][field] = widget.text().strip()

        try:
            # Add the experiment with hierarchical workflow
            new_experiment = self.project_manager.add_experiment(
                experiment_id,
                subject_id,
                recorded_date,
                exp_type,
                processing_stage,
                data_source,
                selected_plugins,
                plugin_params
            )

            QMessageBox.information(self, "Success", f"Experiment '{new_experiment.id}' added.")
            self.navigation_pane.set_button_checked(1)
            self.refresh_experiment_list_display()
            self.experiment_notification_label.setText("Experiment added successfully!")
            QTimer.singleShot(3000, lambda: self.experiment_notification_label.setText(""))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def refresh_experiment_list_display(self):
        sorted_exps = self.state_manager.get_sorted_list("experiments")
        self.experimentListWidget.clear()
        for e in sorted_exps:
            self.experimentListWidget.addItem(f"{e.id} ({e.type}, Stage: {e.processing_stage}, Source: {e.data_source})")
        