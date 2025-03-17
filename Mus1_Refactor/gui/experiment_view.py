from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, 
                         QComboBox, QDateTimeEdit, QPushButton, QGroupBox, QScrollArea, 
                         QCheckBox, QMessageBox, QListWidget, QTextEdit, QHBoxLayout,
                         QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView)
from PySide6.QtCore import QTimer, Qt
from datetime import datetime
from gui.navigation_pane import NavigationPane 
from gui.base_view import BaseView
from gui.metadata_display import MetadataGridDisplay
import os
import json
from pathlib import Path

class ExperimentView(BaseView):
    def __init__(self, parent=None):
        # Initialize with base view and specific name
        super().__init__(parent, view_name="experiment")
        
        # Store reference to state_manager for cleaner access
        if parent and hasattr(parent, 'project_manager'):
            self._state_manager = parent.project_manager.state_manager
            # Subscribe to state changes
            self._state_manager.subscribe(self.refresh_data)

        # Setup navigation for this view
        self.setup_navigation([
            "Add Experiment",
            "View Experiments",
            "Create Batch"
        ])
        
        # Create pages
        self.setup_add_experiment_page()
        self.setup_view_experiments_page()
        self.setup_create_batch_page()
        
        # Set default selection
        self.change_page(0)
        
    def setup_add_experiment_page(self):
        """Setup the Add Experiment page."""
        # Create the page widget
        self.page_add_exp = QWidget()
        ae_layout = QVBoxLayout(self.page_add_exp)
        ae_layout.setContentsMargins(10, 10, 10, 10)
        ae_layout.setSpacing(10)
        
        # Basic experiment info group
        basic_info_group = QGroupBox("Experiment Information")
        basic_info_group.setProperty("class", "mus1-input-group")
        basic_info_layout = QVBoxLayout(basic_info_group)
        
        # Experiment Type Selection
        basic_info_layout.addWidget(QLabel("Experiment Type:"))
        self.expTypeCombo = QComboBox()
        self.expTypeCombo.setProperty("class", "mus1-combo-box")
        self.expTypeCombo.currentIndexChanged.connect(self.on_experiment_type_changed)
        basic_info_layout.addWidget(self.expTypeCombo)

        # Processing Stage Selection
        basic_info_layout.addWidget(QLabel("Processing Stage:"))
        self.stageCombo = QComboBox()
        self.stageCombo.setProperty("class", "mus1-combo-box")
        self.stageCombo.currentIndexChanged.connect(self.on_stage_changed)
        basic_info_layout.addWidget(self.stageCombo)

        # Data Source Selection
        basic_info_layout.addWidget(QLabel("Data Source:"))
        self.sourceCombo = QComboBox()
        self.sourceCombo.setProperty("class", "mus1-combo-box")
        self.sourceCombo.currentIndexChanged.connect(self.update_plugin_selection)
        basic_info_layout.addWidget(self.sourceCombo)
        
        # Basic Experiment Info
        form_layout = QFormLayout()
        
        self.idLineEdit = QLineEdit()
        self.idLineEdit.setProperty("class", "mus1-text-input")
        form_layout.addRow(QLabel("Experiment ID:"), self.idLineEdit)
        
        self.subjectComboBox = QComboBox()
        self.subjectComboBox.setProperty("class", "mus1-combo-box")
        form_layout.addRow(QLabel("Subject ID:"), self.subjectComboBox)
        
        self.dateRecordedEdit = QDateTimeEdit(datetime.now())
        self.dateRecordedEdit.setCalendarPopup(True)
        form_layout.addRow(QLabel("Date Recorded:"), self.dateRecordedEdit)
        
        basic_info_layout.addLayout(form_layout)
        
        # Add basic info group to page layout
        ae_layout.addWidget(basic_info_group)
        
        # Plugin Selection Section
        self.plugin_selection_group = QGroupBox("Available Plugins")
        self.plugin_selection_group.setProperty("class", "mus1-input-group")
        plugin_selection_layout = QVBoxLayout(self.plugin_selection_group)
        
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
        self.add_experiment_button.setProperty("class", "mus1-primary-button")
        self.add_experiment_button.clicked.connect(self.handle_add_experiment)
        ae_layout.addWidget(self.add_experiment_button)
        
        # Add a notification label to show experiment addition success message
        self.experiment_notification_label = QLabel("")
        ae_layout.addWidget(self.experiment_notification_label)
        
        # Storage for plugin field widgets
        self.plugin_field_widgets = {}
        
        # Add the page to the stacked widget
        self.add_page(self.page_add_exp, "Add Experiment")
        
    def setup_view_experiments_page(self):
        """Setup the View Experiments page."""
        # Create the page widget
        self.page_view_exp = QWidget()
        view_exp_layout = QVBoxLayout(self.page_view_exp)
        view_exp_layout.setContentsMargins(10, 10, 10, 10)
        view_exp_layout.setSpacing(10)
        
        # Add title
        view_exp_layout.addWidget(QLabel("Experiments"))
        
        # Create experiment list
        self.experimentListWidget = QListWidget()
        view_exp_layout.addWidget(self.experimentListWidget)
        
        # Add the page to the stacked widget
        self.add_page(self.page_view_exp, "View Experiments")
        
    def setup_create_batch_page(self):
        """Setup the Create Batch page."""
        # Create the page widget
        self.page_create_batch = QWidget()
        create_batch_layout = QVBoxLayout(self.page_create_batch)
        create_batch_layout.setContentsMargins(10, 10, 10, 10)
        create_batch_layout.setSpacing(10)
        
        # Batch info section
        batch_info_group = QGroupBox("Batch Information")
        batch_info_group.setProperty("class", "mus1-input-group")
        batch_info_layout = QFormLayout(batch_info_group)
        
        self.batchIdLineEdit = QLineEdit()
        self.batchIdLineEdit.setProperty("class", "mus1-text-input")
        batch_info_layout.addRow(QLabel("Batch ID:"), self.batchIdLineEdit)
        
        self.batchNameLineEdit = QLineEdit()
        self.batchNameLineEdit.setProperty("class", "mus1-text-input")
        batch_info_layout.addRow(QLabel("Batch Name:"), self.batchNameLineEdit)
        
        self.batchDescriptionLineEdit = QLineEdit()
        self.batchDescriptionLineEdit.setProperty("class", "mus1-text-input")
        batch_info_layout.addRow(QLabel("Description:"), self.batchDescriptionLineEdit)
        
        create_batch_layout.addWidget(batch_info_group)
        
        # Experiment selection section
        exp_selection_group = QGroupBox("Select Experiments for Batch")
        exp_selection_group.setProperty("class", "mus1-input-group")
        exp_selection_layout = QVBoxLayout(exp_selection_group)
        
        # Create the grid display using the MetadataGridDisplay component
        self.batch_experiment_grid = MetadataGridDisplay()
        self.batch_experiment_grid.setMinimumHeight(300)
        exp_selection_layout.addWidget(self.batch_experiment_grid)
        
        # Sorting and filtering controls
        controls_layout = QHBoxLayout()
        
        # Sorting
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort By:"))
        
        self.sortComboBox = QComboBox()
        self.sortComboBox.setProperty("class", "mus1-combo-box")
        self.sortComboBox.addItems(["ID", "Type", "Subject", "Date"])
        self.sortComboBox.currentIndexChanged.connect(self.sort_experiment_grid)
        sort_layout.addWidget(self.sortComboBox)
        
        controls_layout.addLayout(sort_layout)
        controls_layout.addStretch()
        
        # Filtering
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        
        self.filterTypeCombo = QComboBox()
        self.filterTypeCombo.setProperty("class", "mus1-combo-box")
        self.filterTypeCombo.currentIndexChanged.connect(self.filter_experiment_grid)
        filter_layout.addWidget(self.filterTypeCombo)
        
        controls_layout.addLayout(filter_layout)
        
        exp_selection_layout.addLayout(controls_layout)
        create_batch_layout.addWidget(exp_selection_group)
        
        # Create Batch button
        self.create_batch_button = QPushButton("Create Batch")
        self.create_batch_button.setObjectName("createBatchButton")
        self.create_batch_button.setProperty("class", "mus1-primary-button")
        self.create_batch_button.clicked.connect(self.handle_create_batch)
        create_batch_layout.addWidget(self.create_batch_button)
        
        # Add notification label for batch creation
        self.batch_notification_label = QLabel("")
        create_batch_layout.addWidget(self.batch_notification_label)
        
        # Track selected experiments for batch creation
        self.selected_experiments = set()
        
        # Add the page to the stacked widget
        self.add_page(self.page_create_batch, "Create Batch")
        
    def change_subpage(self, index: int):
        """Redirect to base class page change method for compatibility."""
        self.change_page(index)
        
    def change_page(self, index):
        """
        Override change_page to refresh data when switching pages.
        """
        super().change_page(index)
        
        # Do specific actions based on the page
        if index == 1:  # View Experiments page
            self.refresh_data()
        elif index == 2:  # Create Batch page
            self.setup_batch_creation()
        
    def set_core(self, project_manager, state_manager):
        """Set the core managers for this view."""
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.refresh_data()
        
        # Log that core is set
        self.add_log_message("Core managers set for Experiment View", "info")
        
        # Subscribe to state changes
        if hasattr(self.state_manager, 'subscribe'):
            self.state_manager.subscribe(self.refresh_data)

    def refresh_data(self):
        if not self.state_manager:
            return

        self.add_log_message("Refreshing experiment data...", 'info')

        # Update experiment types dropdown
        self.expTypeCombo.clear()
        supported_types = sorted(self.state_manager.get_supported_experiment_types())
        for t in supported_types:
            self.expTypeCombo.addItem(t)
            
        # Also update filter dropdown in batch creation page
        self.filterTypeCombo.clear()
        self.filterTypeCombo.addItem("All Types")
        self.filterTypeCombo.addItems(supported_types)

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

        self.add_log_message(f"Found {len(supported_types)} experiment types and {len(all_experiments)} experiments", 'success')

    def on_experiment_type_changed(self, index):
        """When experiment type changes, update processing stages, data sources, and plugin selection."""
        if index < 0 or not self.project_manager:
            return

        exp_type = self.expTypeCombo.currentText()
        
        # Add log message
        self.add_log_message(f"Selected experiment type: {exp_type}", 'info')

        # Clear plugin selections
        self.clear_plugin_selection()

        # Update Processing Stage combo based on exp_type
        stages = self.state_manager.get_compatible_processing_stages(self.project_manager.plugin_manager, exp_type)
        self.stageCombo.clear()
        
        if not stages:
            self.add_log_message(f"No processing stages found for {exp_type}", 'warning')
            self.stageCombo.setEnabled(False)
        else:
            self.stageCombo.setEnabled(True)
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

        # Get selected plugins that match the criteria
        selected_plugins = []
        if hasattr(self, 'plugin_checkboxes'):
            for name, checkbox in self.plugin_checkboxes.items():
                if checkbox.isChecked():
                    for plugin in self.project_manager.plugin_manager.get_plugins_by_criteria(exp_type, stage, source):
                        if plugin.plugin_self_metadata().name == name:
                            selected_plugins.append(plugin)
                            break

        # If more than one plugin is selected, mark the fields container for combined overrides
        if len(selected_plugins) > 1:
            self.plugin_fields_widget.setProperty("class", "plugin-combined-overrides")
        else:
            self.plugin_fields_widget.setProperty("class", "")

        # Create UI for each selected plugin
        for plugin in selected_plugins:
            plugin_id = plugin.plugin_self_metadata().name
            plugin_group = QGroupBox(plugin_id)
            
            # Apply plugin styling classes from StateManager
            styling_classes = self.state_manager.get_plugin_styling_classes(plugin_id)
            plugin_class = f"mus1-plugin-group {' '.join(styling_classes)}"
            plugin_group.setProperty("class", plugin_class)
            
            # Use form layout for fields
            group_layout = QFormLayout(plugin_group)
            
            # Track widgets for this plugin
            if plugin_id not in self.plugin_field_widgets:
                self.plugin_field_widgets[plugin_id] = {}

            # Add required fields
            req_fields = plugin.required_fields()
            for field in req_fields:
                label = QLabel(f"{field} <span style='color:var(--plugin-required-color);'>*</span>")
                field_widget = self._create_field_widget(plugin, field)
                field_styling = plugin.get_field_styling(field)
                field_widget.setProperty("class", f"{field_styling['widget_class']} {field_styling['status_class']} {field_styling['stage_class']}")
                group_layout.addRow(label, field_widget)
                self.plugin_field_widgets[plugin_id][field] = field_widget

            # Add optional fields
            opt_fields = plugin.optional_fields()
            for field in opt_fields:
                label = QLabel(f"{field} <span style='color:var(--text-muted-color);'>(optional)</span>")
                field_widget = self._create_field_widget(plugin, field)
                field_styling = plugin.get_field_styling(field)
                field_widget.setProperty("class", f"{field_styling['widget_class']} {field_styling['status_class']} {field_styling['stage_class']}")
                group_layout.addRow(label, field_widget)
                self.plugin_field_widgets[plugin_id][field] = field_widget

            # Add the plugin group to the layout
            self.plugin_fields_layout.addWidget(plugin_group)

        # Add stretch to push everything to the top
        self.plugin_fields_layout.addStretch()
        
    def _create_field_widget(self, plugin, field_name):
        """
        Create an appropriate widget based on field type.
        
        Args:
            plugin: The plugin that defines the field
            field_name: The name of the field
            
        Returns:
            QWidget: An appropriate widget for the field type
        """
        # Default to QLineEdit
        field_widget = QLineEdit()
        
        # Check if plugin provides field types
        if hasattr(plugin, 'get_field_types') and callable(plugin.get_field_types):
            field_types = plugin.get_field_types()
            field_type = field_types.get(field_name, "text")
            
            # Create appropriate widget based on type
            if field_type == "text":
                field_widget = QLineEdit()
            elif field_type == "file":
                # Create a file selector
                file_layout = QHBoxLayout()
                file_edit = QLineEdit()
                file_button = QPushButton("Browse...")
                file_button.setProperty("class", "mus1-secondary-button")
                
                # Create a placeholder for the browse button callback
                file_button.clicked.connect(lambda: self._browse_for_file(file_edit))
                
                file_layout.addWidget(file_edit, 1)
                file_layout.addWidget(file_button, 0)
                
                container = QWidget()
                container.setLayout(file_layout)
                field_widget = container
                
                # Store the line edit for accessing the value later
                self.plugin_field_widgets.setdefault(plugin.plugin_self_metadata().name, {})[field_name] = file_edit
            elif field_type.startswith("enum:"):
                # Create dropdown for enum values
                options = field_type.split(":", 1)[1].split(",")
                combo = QComboBox()
                combo.addItems(options)
                field_widget = combo
            elif field_type == "dict":
                # For complex types, provide a simplified text input with placeholder
                text_input = QLineEdit()
                text_input.setPlaceholderText("Enter as JSON: {\"key\": \"value\"}")
                field_widget = text_input
                
        # Apply common styling
        if isinstance(field_widget, QLineEdit):
            field_widget.setProperty("class", "mus1-text-input")
        elif isinstance(field_widget, QComboBox):
            field_widget.setProperty("class", "mus1-combo-box")
            
        return field_widget
        
    def _browse_for_file(self, line_edit):
        """
        Open a file dialog to browse for a file and update the line edit.
        
        Args:
            line_edit: The QLineEdit to update with the selected file path
        """
        from PySide6.QtWidgets import QFileDialog
        
        # Get the current file path if any
        current_path = line_edit.text()
        
        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            current_path or "",
            "All Files (*.*)"
        )
        
        if file_path:
            line_edit.setText(file_path)

    def on_stage_changed(self, index):
        """When processing stage changes, update data source combo accordingly."""
        exp_type = self.expTypeCombo.currentText()
        if not exp_type:
            return

        stage = self.stageCombo.currentText()
        if stage:
            self.add_log_message(f"Selected processing stage: {stage}", 'info')
        
        sources = self.state_manager.get_compatible_data_sources(self.project_manager.plugin_manager, exp_type, stage)
        self.sourceCombo.clear()
        
        if not sources:
            self.add_log_message(f"No data sources found for {exp_type} at {stage} stage", 'warning')
            self.sourceCombo.setEnabled(False)
        else:
            self.sourceCombo.setEnabled(True)
            for src in sources:
                self.sourceCombo.addItem(src)

        self.update_plugin_selection()

    def update_plugin_selection(self):
        """Update the plugin selection checkboxes based on current experiment type, stage, and source."""
        exp_type = self.expTypeCombo.currentText()
        stage = self.stageCombo.currentText()
        source = self.sourceCombo.currentText()
        
        if source:
            self.add_log_message(f"Selected data source: {source}", 'info')

        # Clear previous plugin selection UI
        self.clear_plugin_selection()

        # Get compatible plugins based on criteria
        compatible_plugins = self.project_manager.plugin_manager.get_plugins_by_criteria(exp_type, stage, source)
        
        if not compatible_plugins:
            self.add_log_message(f"No compatible plugins found for the selected criteria", 'warning')
        else:
            self.add_log_message(f"Found {len(compatible_plugins)} compatible plugins", 'success')

        for plugin in compatible_plugins:
            metadata = plugin.plugin_self_metadata()
            checkbox = QCheckBox(metadata.name)
            checkbox.stateChanged.connect(self.update_plugin_fields)
            info_label = QLabel(f"<i>{metadata.description}</i>")
            info_label.setWordWrap(True)

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
            self.add_log_message("Error: No ProjectManager is set", 'error')
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
            self.add_log_message("Error: No plugins selected", 'error')
            return

        # Validate basic fields
        if not experiment_id:
            QMessageBox.warning(self, "Error", "Please enter an experiment ID.")
            self.add_log_message("Error: Missing experiment ID", 'error')
            return

        if not subject_id:
            QMessageBox.warning(self, "Error", "Please select a subject.")
            self.add_log_message("Error: No subject selected", 'error')
            return

        # Gather plugin parameters
        plugin_params = {}
        for plugin in selected_plugins:
            plugin_id = plugin.plugin_self_metadata().name
            plugin_params[plugin_id] = {}
            
            # Get field values from widgets
            if plugin_id in self.plugin_field_widgets:
                for field_name, widget in self.plugin_field_widgets[plugin_id].items():
                    # Extract value based on widget type
                    if isinstance(widget, QLineEdit):
                        value = widget.text().strip()
                    elif isinstance(widget, QComboBox):
                        value = widget.currentText()
                    elif isinstance(widget, QTextEdit):
                        value = widget.toPlainText().strip()
                    elif isinstance(widget, QCheckBox):
                        value = "true" if widget.isChecked() else "false"
                    else:
                        # For custom widgets or compound widgets, try to get their text
                        if hasattr(widget, 'text'):
                            value = widget.text().strip()
                        else:
                            value = ""
                            
                    # Store the value
                    plugin_params[plugin_id][field_name] = value

        try:
            # Add the experiment with hierarchical workflow
            self.add_log_message(f"Adding experiment '{experiment_id}' with {len(selected_plugins)} plugins...", 'info')
            
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
            self.add_log_message(f"Successfully added experiment '{new_experiment.id}'", 'success')
            self.change_page(1)
            self.refresh_data()
            self.experiment_notification_label.setText("Experiment added successfully!")
            QTimer.singleShot(3000, lambda: self.experiment_notification_label.setText(""))
        except Exception as e:
            error_msg = str(e)
            QMessageBox.warning(self, "Error", error_msg)
            self.add_log_message(f"Error adding experiment: {error_msg}", 'error')

    def refresh_experiment_list_display(self):
        sorted_exps = self.state_manager.get_sorted_list("experiments")
        self.experimentListWidget.clear()
        for e in sorted_exps:
            self.experimentListWidget.addItem(f"{e.id} ({e.type}, Stage: {e.processing_stage}, Source: {e.data_source})")
        
    def setup_batch_creation(self):
        """Initialize the batch creation page with experiments grid."""
        if not self.state_manager:
            return
            
        # Generate a unique batch ID
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.batchIdLineEdit.setText(f"batch_{timestamp}")
        
        # Clear selection status
        self.selected_experiments = set()
        
        # Populate experiment grid
        self.update_experiment_grid()
        
        # Update notification
        self.batch_notification_label.setText("")
        
    def update_experiment_grid(self):
        """Update the grid display with experiments."""
        if not self.state_manager:
            return
            
        # Get all experiments from state manager
        all_experiments = self.state_manager.get_sorted_list("experiments")
        
        # Set up the grid with selectable checkboxes
        columns = ["Select", "ID", "Type", "Subject", "Date", "Stage"]
        
        # Build experiment data for grid
        exp_data = []
        for exp in all_experiments:
            # Format date string
            date_str = exp.date_recorded.strftime("%Y-%m-%d") if hasattr(exp, 'date_recorded') and exp.date_recorded else "N/A"
            
            # Create dict for each experiment row
            exp_dict = {
                "Select": False,  # Checkbox state
                "ID": exp.id,
                "Type": exp.type,
                "Subject": exp.subject_id,
                "Date": date_str,
                "Stage": exp.processing_stage
            }
            exp_data.append(exp_dict)
        
        # Update the grid
        self.batch_experiment_grid.set_columns(columns)
        self.batch_experiment_grid.populate_data(exp_data, columns, selectable=True, checkbox_column="Select")
        
        # Connect selection changed signal
        self.batch_experiment_grid.selection_changed.connect(self.on_experiment_selection_changed)
    
    def sort_experiment_grid(self, index):
        """Sort the experiment grid based on selected column."""
        if not self.state_manager:
            return
            
        # Get sort key from combo box
        sort_options = ["ID", "Type", "Subject", "Date"]
        sort_key = sort_options[index]
        
        # Preserve current selection
        selected_ids = self.selected_experiments
        
        # Get all experiments and sort them
        all_experiments = self.state_manager.get_sorted_list("experiments")
        
        # Sort based on the selected option
        if sort_key == "ID":
            sorted_exps = sorted(all_experiments, key=lambda e: e.id)
        elif sort_key == "Type":
            sorted_exps = sorted(all_experiments, key=lambda e: e.type)
        elif sort_key == "Subject":
            sorted_exps = sorted(all_experiments, key=lambda e: e.subject_id)
        elif sort_key == "Date":
            sorted_exps = sorted(all_experiments, key=lambda e: e.date_recorded if hasattr(e, 'date_recorded') and e.date_recorded else datetime.min)
        
        # Apply current filter
        filtered_exps = self.apply_experiment_filter(sorted_exps)
        
        # Update grid with sorted and filtered data
        columns = ["Select", "ID", "Type", "Subject", "Date", "Stage"]
        exp_data = []
        
        for exp in filtered_exps:
            date_str = exp.date_recorded.strftime("%Y-%m-%d") if hasattr(exp, 'date_recorded') and exp.date_recorded else "N/A"
            
            # Create dict for each experiment row, preserving selection state
            exp_dict = {
                "Select": exp.id in selected_ids,
                "ID": exp.id,
                "Type": exp.type,
                "Subject": exp.subject_id,
                "Date": date_str,
                "Stage": exp.processing_stage
            }
            exp_data.append(exp_dict)
        
        # Update the grid
        self.batch_experiment_grid.set_columns(columns)
        self.batch_experiment_grid.populate_data(exp_data, columns, selectable=True, checkbox_column="Select")
    
    def filter_experiment_grid(self, index):
        """Filter the experiment grid based on experiment type."""
        # Get current sort order
        sort_index = self.sortComboBox.currentIndex()
        # Re-sort with new filter
        self.sort_experiment_grid(sort_index)
    
    def apply_experiment_filter(self, experiments):
        """Apply filter to experiment list."""
        if not self.filterTypeCombo:
            return experiments
            
        filter_type = self.filterTypeCombo.currentText()
        if filter_type == "All Types":
            return experiments
        
        # Filter by experiment type
        return [exp for exp in experiments if exp.type == filter_type]
    
    def on_experiment_selection_changed(self, exp_id, is_selected):
        """Handle experiment selection changes."""
        if is_selected:
            self.selected_experiments.add(exp_id)
        else:
            self.selected_experiments.discard(exp_id)
        
        # Update the create button state
        self.create_batch_button.setEnabled(len(self.selected_experiments) > 0)
        
        # Update notification with count
        count = len(self.selected_experiments)
        self.batch_notification_label.setText(f"{count} experiment(s) selected")
    
    def handle_create_batch(self):
        """Create a new batch with the selected experiments."""
        if not self.project_manager or not self.state_manager:
            return
            
        # Get batch info
        batch_id = self.batchIdLineEdit.text().strip()
        batch_name = self.batchNameLineEdit.text().strip()
        batch_description = self.batchDescriptionLineEdit.text().strip()
        
        # Validate inputs
        if not batch_id:
            QMessageBox.warning(self, "Validation Error", "Batch ID is required.")
            return
            
        if len(self.selected_experiments) == 0:
            QMessageBox.warning(self, "Validation Error", "Please select at least one experiment.")
            return
        
        # Create the batch
        try:
            # Create batch with selection criteria
            selection_criteria = {
                "manual_selection": True,
                "filter_type": self.filterTypeCombo.currentText(),
                "sort_by": self.sortComboBox.currentText()
            }
            
            # Call the project manager to create the batch
            self.project_manager.create_batch(
                batch_id=batch_id,
                batch_name=batch_name,
                description=batch_description,
                experiment_ids=list(self.selected_experiments),
                selection_criteria=selection_criteria
            )
            
            # Show success message
            self.batch_notification_label.setText(f"Batch '{batch_id}' created successfully!")
            
            # Clear form for next batch
            self.batchNameLineEdit.clear()
            self.batchDescriptionLineEdit.clear()
            
            # Generate a new batch ID
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.batchIdLineEdit.setText(f"batch_{timestamp}")
            
            # Clear selection
            self.selected_experiments = set()
            self.update_experiment_grid()
            
        except Exception as e:
            # Show error message
            QMessageBox.critical(self, "Error", f"Failed to create batch: {str(e)}")
            self.batch_notification_label.setText("Batch creation failed.")
        
    def closeEvent(self, event):
        """Clean up when the view is closed."""
        # Unsubscribe the observer when the view is closed
        if hasattr(self, '_state_manager'):
            self._state_manager.unsubscribe(self.refresh_data)
        super().closeEvent(event)
        
    def update_theme(self, theme):
        """Update the theme for this view and all its components.
        Called when the application theme changes.
        
        Args:
            theme: The theme name ("dark" or "light"), passed from MainWindow
        """
        # Propagate theme changes using the base update_theme, which handles styling
        super().update_theme(theme)
        
        # Optionally, perform additional view-specific theme updates here (e.g., update plugin fields)
        if hasattr(self, 'plugin_field_widgets') and hasattr(self, 'update_plugin_fields'):
            try:
                self.update_plugin_fields()
            except Exception as e:
                if hasattr(self, 'navigation_pane'):
                    self.navigation_pane.add_log_message(f"Error updating plugin fields: {str(e)}", "warning")
        