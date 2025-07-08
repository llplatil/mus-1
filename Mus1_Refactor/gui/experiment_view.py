from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, 
                         QComboBox, QDateTimeEdit, QPushButton, QGroupBox, QScrollArea, 
                         QCheckBox, QMessageBox, QListWidget, QTextEdit, QHBoxLayout,
                         QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QDoubleSpinBox, QAbstractItemView)
from PySide6.QtCore import QTimer, Qt, QDateTime
from datetime import datetime
from .navigation_pane import NavigationPane 
from .base_view import BaseView
from .metadata_display import MetadataGridDisplay
import os
import json
from pathlib import Path
import logging # Add logging import if not already present
logger = logging.getLogger(__name__) # Setup logger for the module
from typing import List # Ensure List is imported

class ExperimentView(BaseView):
    def __init__(self, parent=None):
        super().__init__(parent, view_name="experiments")
        
        # Set up core managers from window
        self.state_manager = self.window().state_manager
        self.project_manager = self.window().project_manager
        self.data_manager = self.window().data_manager
        self.plugin_manager = self.window().plugin_manager
        
        # Set up navigation first
        self.setup_navigation(["Add Experiment", "View Experiments", "Create Batch"])
        
        # Set up pages
        self.setup_add_experiment_page()
        self.setup_view_experiments_page()
        self.setup_create_batch_page()
        
        # Start with first page
        self.change_page(0)
        
        # Initialize data
        self.refresh_data()

    def setup_add_experiment_page(self):
        """Sets up the 'Add Experiment' sub-page according to the new workflow."""
        page_widget = QWidget()
        page_layout = QVBoxLayout(page_widget)
        page_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Keep content at the top
        page_layout.setSpacing(self.SECTION_SPACING) # Use BaseView spacing

        # --- 1. Core Experiment Details ---
        # Use create_form_section for the group box and layout
        details_group, details_layout = self.create_form_section("Core Experiment Details", page_layout)

        # Experiment ID
        id_row = self.create_form_row(details_layout) # Use helper for row
        id_label = self.create_form_label("Experiment ID*:") # Use helper for label
        self.experiment_id_input = QLineEdit()
        self.experiment_id_input.setObjectName("experimentIdInput")
        self.experiment_id_input.setProperty("class", "mus1-text-input")
        self.experiment_id_input.setPlaceholderText("Enter unique experiment ID")
        id_row.addWidget(id_label)
        id_row.addWidget(self.experiment_id_input)
        self.experiment_id_input.textChanged.connect(self._update_add_button_state) # Connect state update

        # Subject ID
        subject_row = self.create_form_row(details_layout) # Use helper for row
        subject_label = self.create_form_label("Subject ID*:") # Use helper for label
        self.subject_id_combo = QComboBox()
        self.subject_id_combo.setObjectName("subjectIdCombo")
        self.subject_id_combo.setProperty("class", "mus1-combo-box")
        # Items will be populated by refresh_data
        subject_row.addWidget(subject_label)
        subject_row.addWidget(self.subject_id_combo)
        self.subject_id_combo.currentIndexChanged.connect(self._update_add_button_state) # Connect state update

        # Experiment Type
        type_row = self.create_form_row(details_layout) # Use helper for row
        type_label = self.create_form_label("Experiment Type*:") # Use helper for label
        self.experiment_type_combo = QComboBox()
        self.experiment_type_combo.setObjectName("experimentTypeCombo")
        self.experiment_type_combo.setProperty("class", "mus1-combo-box")
        self.experiment_type_combo.addItem("Select Type...", None) # Add placeholder
        # Items will be populated by refresh_data
        type_row.addWidget(type_label)
        type_row.addWidget(self.experiment_type_combo)
        # Connect type change to DISCOVER PLUGINS and update button state
        self.experiment_type_combo.currentIndexChanged.connect(self._discover_plugins)
        self.experiment_type_combo.currentIndexChanged.connect(self._update_add_button_state)

        # Date Recorded
        date_row = self.create_form_row(details_layout) # Use helper for row
        date_label = self.create_form_label("Date Recorded*:") # Use helper for label
        self.date_recorded_edit = QDateTimeEdit(QDateTime.currentDateTime()) # Use QDateTime
        self.date_recorded_edit.setCalendarPopup(True)
        self.date_recorded_edit.setDisplayFormat("yyyy-MM-dd")
        date_row.addWidget(date_label)
        date_row.addWidget(self.date_recorded_edit)

        # --- 2. Select Tools (Plugins) ---
        tools_group, tools_section_layout = self.create_form_section("Select Tools (Plugins)", page_layout)
        # Use a horizontal layout for the two columns
        plugin_columns_layout = QHBoxLayout()
        plugin_columns_layout.setSpacing(self.CONTROL_SPACING * 2) # More spacing between lists
        tools_section_layout.addLayout(plugin_columns_layout)

        # Column 1: Data Handlers
        # Use is_subgroup=True for consistent styling within the main section
        handler_group, handler_layout = self.create_form_section("Data Handler Plugin:", None, is_subgroup=True)
        self.data_handler_plugin_list = QListWidget()
        self.data_handler_plugin_list.setObjectName("dataHandlerPluginList")
        self.data_handler_plugin_list.setProperty("class", "mus1-list-widget")
        self.data_handler_plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection) # Assuming one handler
        self.data_handler_plugin_list.currentItemChanged.connect(self._on_plugin_selection_changed) # Connect update
        handler_layout.addWidget(self.data_handler_plugin_list)
        plugin_columns_layout.addWidget(handler_group, 1) # Add column with stretch factor 1

        # Column 2: Analysis Plugins
        analysis_group, analysis_layout = self.create_form_section("Analysis Plugin(s):", None, is_subgroup=True)
        self.analysis_plugin_list = QListWidget()
        self.analysis_plugin_list.setObjectName("analysisPluginList")
        self.analysis_plugin_list.setProperty("class", "mus1-list-widget")
        self.analysis_plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection) # Allow multiple analysis plugins
        self.analysis_plugin_list.itemSelectionChanged.connect(self._on_plugin_selection_changed) # Connect update
        analysis_layout.addWidget(self.analysis_plugin_list)
        plugin_columns_layout.addWidget(analysis_group, 1) # Add column with stretch factor 1

        # --- 3. Plugin Parameters ---
        # Create the group box and layout, keep reference to layout
        self.plugin_params_group, self.plugin_fields_layout = self.create_form_section("Plugin Parameters", page_layout)
        # Ensure layout is QFormLayout as expected by _update_plugin_fields
        if not isinstance(self.plugin_fields_layout, QFormLayout):
             # If create_form_section returns QVBoxLayout, replace it
             qgroupbox_layout = self.plugin_params_group.layout()
             if qgroupbox_layout:
                 # Remove existing layout items if any
                 while qgroupbox_layout.count():
                      item = qgroupbox_layout.takeAt(0)
                      if item.widget(): item.widget().deleteLater()
             self.plugin_fields_layout = QFormLayout() # Create the correct layout type
             self.plugin_params_group.setLayout(self.plugin_fields_layout) # Set the new layout
             self.plugin_fields_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
             self.plugin_fields_layout.setVerticalSpacing(self.CONTROL_SPACING)

        self.plugin_params_group.setVisible(False) # Hide initially

        # --- Add Button ---
        # Use helper to create a button row that aligns button to the right
        button_row = self.create_button_row(page_layout, add_stretch=True)
        self.add_experiment_button = QPushButton("Add Experiment")
        self.add_experiment_button.setObjectName("addExperimentButton")
        self.add_experiment_button.setProperty("class", "mus1-primary-button")
        self.add_experiment_button.setEnabled(False) # Disabled initially
        self.add_experiment_button.clicked.connect(self.handle_add_experiment)
        button_row.addWidget(self.add_experiment_button)

        # --- Add Page to Stack ---
        # Add the container widget holding the entire page layout
        self.add_page(page_widget, "Add Experiment")

        # Initial data population (like subject/type combos) will happen in refresh_data
        # Initial plugin discovery will also be triggered by refresh_data

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
        """Set up the Create Batch page."""
        # Main widget for the page
        self.page_create_batch = QWidget()
        batch_layout = QVBoxLayout(self.page_create_batch)
        batch_layout.setContentsMargins(10, 10, 10, 10)
        batch_layout.setSpacing(10)

        # Batch Details Section
        batch_details_group, batch_details_form = self.create_form_section("Batch Details", batch_layout)
        
        # Ensure batch_details_form is a QFormLayout
        if not isinstance(batch_details_form, QFormLayout):
            # If create_form_section returned a QVBoxLayout inside the groupbox, get/create the QFormLayout
            qgroupbox_layout = batch_details_group.layout()
            if qgroupbox_layout and isinstance(qgroupbox_layout, QVBoxLayout):
                 # Assuming the QVBoxLayout was just a container, replace it
                 while qgroupbox_layout.count():
                      item = qgroupbox_layout.takeAt(0)
                      if item.widget(): item.widget().deleteLater()
                 batch_details_form = QFormLayout() # Create the correct layout type
                 batch_details_group.setLayout(batch_details_form) # Set the new layout
                 batch_details_form.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
                 batch_details_form.setVerticalSpacing(self.CONTROL_SPACING)
            else:
                 # Fallback if the structure isn't as expected
                 logger.error("Could not reliably get or create QFormLayout for batch details.")
                 # Handle error appropriately, maybe return or raise
                 return 

        # Batch ID (auto-generated, but user can modify)
        self.batchIdLineEdit = QLineEdit()
        self.batchIdLineEdit.setProperty("class", "mus1-text-input")
        batch_details_form.addRow(self.create_form_label("Batch ID:"), self.batchIdLineEdit)
        
        # Batch Name (optional)
        self.batchNameLineEdit = QLineEdit()
        self.batchNameLineEdit.setProperty("class", "mus1-text-input")
        self.batchNameLineEdit.setPlaceholderText("Optional batch name...")
        batch_details_form.addRow(self.create_form_label("Batch Name:"), self.batchNameLineEdit)
        
        # Batch Description (optional)
        self.batchDescriptionTextEdit = QTextEdit()
        self.batchDescriptionTextEdit.setProperty("class", "mus1-text-input")
        self.batchDescriptionTextEdit.setPlaceholderText("Optional description...")
        batch_details_form.addRow(self.create_form_label("Description:"), self.batchDescriptionTextEdit)

        # Experiment Selection Section
        experiment_selection_group, experiment_selection_layout = self.create_form_section("Select Experiments", batch_layout)

        # Use MetadataGridDisplay for experiment selection
        self.batch_experiment_grid = MetadataGridDisplay(self)
        experiment_selection_layout.addWidget(self.batch_experiment_grid)
        
        # Batch Creation Button
        create_batch_row = self.create_button_row(batch_layout)
        self.create_batch_button = QPushButton("Create Batch")
        self.create_batch_button.setObjectName("createBatchButton")
        self.create_batch_button.setProperty("class", "mus1-primary-button")
        self.create_batch_button.clicked.connect(self.handle_create_batch)
        self.create_batch_button.setEnabled(False) # Disable initially until experiments are selected
        create_batch_row.addWidget(self.create_batch_button)
        
        # Notification Label
        self.batch_notification_label = QLabel("")
        self.batch_notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        batch_layout.addWidget(self.batch_notification_label)

        # Add stretch to keep elements at the top
        batch_layout.addStretch(1)
        
        # Add the page to the main stacked widget
        self.add_page(self.page_create_batch, "Create Batch")

    def change_page(self, index):
        """Change the active page in the view."""
        # Use BaseView's change_page implementation
        super().change_page(index)
        
        # Refresh data if needed
        self.refresh_data()

    def set_core(self, project_manager, state_manager):
        """
        This method is now deprecated as we get managers from window.
        Kept for backward compatibility but logs a warning.
        """
        logger.warning("ExperimentView.set_core is deprecated. Managers are accessed via self.window()")
        # Still update if called, but prefer window() access
        self.project_manager = project_manager
        self.state_manager = state_manager
        
        # Re-subscribe if managers are set late
        if self.state_manager:
            self.state_manager.unsubscribe(self.refresh_data)
            self.state_manager.subscribe(self.refresh_data)
        self.refresh_data()

    def refresh_data(self):
        """Refresh data based on the current page."""
        current_index = self.pages.currentIndex()
        # Corrected: Get page title from the list stored in BaseView
        page_title = "Unknown Page" # Default title
        if hasattr(self, 'navigation_button_texts') and 0 <= current_index < len(self.navigation_button_texts):
             page_title = self.navigation_button_texts[current_index]
        else:
             logger.warning(f"Could not determine page title for index {current_index}.")
             
        logger.debug(f"Refreshing data for page: {page_title} (Index: {current_index})")

        if page_title == "Add Experiment":
             # Populate subject combo
             self.subject_id_combo.clear()
             if self.state_manager:
                 subjects = self.state_manager.get_sorted_subjects()
                 if subjects:
                     for subj in subjects:
                         self.subject_id_combo.addItem(subj.id, subj.id) # Display ID, store ID as data
                 else:
                      self.subject_id_combo.addItem("No subjects available", None)
             else:
                 self.subject_id_combo.addItem("State Mgr Error", None)

             # Populate experiment type combo
             self.experiment_type_combo.clear()
             self.experiment_type_combo.addItem("Select Type...", None)
             if self.state_manager:
                 exp_types = self.state_manager.get_supported_experiment_types()
                 if exp_types:
                      for etype in exp_types:
                           self.experiment_type_combo.addItem(etype, etype) # Display name, store name as data
                 else:
                     self.experiment_type_combo.addItem("No types found", None)
             else:
                  self.experiment_type_combo.addItem("State Mgr Error", None)

             # Trigger initial plugin discovery if a type is pre-selected or form is ready
             self._discover_plugins()

        elif page_title == "View Experiments":
             self.refresh_experiment_list_display()
        elif page_title == "Create Batch":
             self.setup_batch_creation() # Re-initialize batch creation UI/data

    def clear_plugin_selection(self):
        """Removes all dynamically generated plugin checkboxes and info labels."""
        # This method is likely obsolete as plugins are now shown in ListWidgets
        logger.warning("clear_plugin_selection may be obsolete with ListWidget approach.")
        if hasattr(self, 'plugin_checkboxes'):
            for checkbox in self.plugin_checkboxes.values():
                checkbox.deleteLater()
            self.plugin_checkboxes = {}
        if hasattr(self, 'plugin_info_labels'):
             for label in self.plugin_info_labels.values():
                 label.deleteLater()
             self.plugin_info_labels = {}
        # Clear the layout as well if checkboxes were added directly
        # while self.plugin_scroll_layout.count():
        #    item = self.plugin_scroll_layout.takeAt(0)
        #    if item.widget():
        #        item.widget().deleteLater()
        #    elif item.layout():
        #        # Recursively clear nested layouts if necessary
        #        pass # Add recursive clearing if needed

    def handle_add_experiment(self):
        """Handles the 'Add Experiment' button click."""
        logger.info("Attempting to add experiment...")

        # --- Validation (Basic - more done by button state check) ---
        experiment_id = self.experiment_id_input.text().strip()
        subject_id = self.subject_id_combo.currentData()
        exp_type = self.experiment_type_combo.currentData()
        date_recorded = self.date_recorded_edit.dateTime().toPyDateTime() # Use toPyDateTime

        # Redundant basic checks, but good as a safeguard
        if not all([experiment_id, subject_id, exp_type]):
            self.show_error_message("Validation Error", "Experiment ID, Subject ID, and Experiment Type are required.")
            return

        selected_plugins = self._get_selected_plugins()
        if not selected_plugins:
            self.show_error_message("Validation Error", "At least one data handler or analysis plugin must be selected.")
            return

        # --- Collect Data ---
        associated_plugin_names = [p.plugin_self_metadata().name for p in selected_plugins]

        # Collect plugin parameters
        plugin_params_data = {}
        try:
            # Ensure plugin_field_widgets exists
            if not hasattr(self, 'plugin_field_widgets'):
                 raise RuntimeError("Plugin field widgets dictionary not initialized.")

            for plugin in selected_plugins:
                plugin_name = plugin.plugin_self_metadata().name
                plugin_params_data[plugin_name] = {}
                current_plugin_fields = self.plugin_field_widgets.get(plugin_name, {})
                if not current_plugin_fields and (plugin.required_fields() or plugin.optional_fields()):
                     logger.warning(f"No widgets found for plugin '{plugin_name}' even though it has fields.")
                     # Decide if this is an error or just continue
                     # continue

                all_plugin_fields_def = plugin.required_fields() + plugin.optional_fields()
                field_types = plugin.get_field_types()

                # Iterate through the fields defined by the plugin to ensure all are captured
                for field_name in all_plugin_fields_def:
                    widget = current_plugin_fields.get(field_name)
                    if not widget:
                        # This might happen if a field is optional and wasn't rendered, or an error occurred.
                        # We might choose to skip it or log a more significant warning.
                        # For now, we'll skip non-rendered optional fields.
                        if field_name not in plugin.required_fields():
                            logger.debug(f"Optional field '{field_name}' for plugin '{plugin_name}' has no widget, skipping.")
                            continue
                        else:
                            # This case should ideally be caught by the button state check, but raise error defensively.
                            raise ValueError(f"Required parameter '{field_name}' for plugin '{plugin_name}' is missing its input widget.")

                    value = None
                    # Extract value based on widget type
                    if isinstance(widget, QLineEdit):
                        value = widget.text().strip()
                    elif isinstance(widget, QComboBox):
                        value = widget.currentText()
                    elif isinstance(widget, QSpinBox):
                        value = widget.value()
                    elif isinstance(widget, QDoubleSpinBox):
                        value = widget.value()
                    elif isinstance(widget, QCheckBox):
                        value = widget.isChecked()
                    # Add other widget types if needed

                    plugin_params_data[plugin_name][field_name] = value

        except ValueError as e:
             self.show_error_message("Parameter Error", str(e))
             return
        except Exception as e: # Catch potential errors during value extraction
            logger.error(f"Error collecting parameters: {e}", exc_info=True)
            self.show_error_message("Parameter Error", f"Error processing parameters:\n{e}")
            return


        # Determine initial processing stage based on selected plugins
        initial_stage = "planned" # Default
        for plugin in selected_plugins:
             # If any selected plugin can load tracking data, assume it's at least 'recorded'
             if 'load_tracking_data' in plugin.analysis_capabilities():
                 initial_stage = "recorded"
                 # Check if the file path parameter for this handler is actually filled
                 # (Requires knowing the specific parameter name, e.g., 'tracking_file_path')
                 # This adds complexity - maybe defer stage inference to ProjectManager?
                 # For now, 'recorded' if handler is selected is a reasonable starting point.
                 break


        # --- Call ProjectManager ---
        try:
            logger.info(f"Adding experiment '{experiment_id}' with plugins: {associated_plugin_names}")
            logger.debug(f"Plugin Params: {plugin_params_data}")

            # Ensure ProjectManager reference is valid
            if not self.project_manager:
                 logger.error("ProjectManager is not available. Cannot add experiment.")
                 self.show_error_message("Internal Error", "Project Manager not initialized.")
                 return

            # Call ProjectManager with the updated signature
            self.project_manager.add_experiment(
                experiment_id=experiment_id,
                subject_id=subject_id,
                date_recorded=date_recorded,
                exp_type=exp_type,
                processing_stage=initial_stage, # Pass inferred stage
                associated_plugins=associated_plugin_names,
                plugin_params=plugin_params_data
            )
            # Clear form on success
            self.experiment_id_input.clear()
            # Keep Subject selected? Maybe useful for adding multiple experiments for one subject.
            # self.subject_id_combo.setCurrentIndex(-1)
            self.experiment_type_combo.setCurrentIndex(0) # Reset type triggers plugin clear
            # self.date_recorded_edit.setDateTime(datetime.now()) # Keep date?
            self.clear_plugin_fields() # This is called by _discover_plugins when type changes
            # Manually clear lists after successful add
            self.data_handler_plugin_list.clearSelection()
            self.analysis_plugin_list.clearSelection()
            # Button will be disabled by _update_add_button_state triggered by combo/list changes

            logger.info(f"Experiment '{experiment_id}' added successfully.")
            self.show_info_message("Success", f"Experiment '{experiment_id}' added.")

        except ValueError as e:
            logger.error(f"Error adding experiment: {e}", exc_info=True)
            self.show_error_message("Error", f"Failed to add experiment:\n{e}")
        except Exception as e:
            logger.error(f"Unexpected error adding experiment: {e}", exc_info=True)
            self.show_error_message("Error", f"An unexpected error occurred:\n{e}")

    def refresh_experiment_list_display(self):
        if not self.state_manager:
             logger.warning("StateManager not available, cannot refresh experiment list.")
             self.experimentListWidget.clear()
             self.experimentListWidget.addItem("Error: StateManager unavailable.")
             return

        sorted_exps = self.state_manager.get_sorted_list("experiments")
        self.experimentListWidget.clear()
        if sorted_exps:
            for e in sorted_exps:
                # Use more robust access with defaults
                exp_id = getattr(e, 'id', 'N/A')
                exp_type = getattr(e, 'type', 'N/A')
                stage = getattr(e, 'processing_stage', 'N/A')
                # data_source removed, maybe add subject_id?
                subject_id = getattr(e, 'subject_id', 'N/A')
                self.experimentListWidget.addItem(f"{exp_id} ({exp_type}, Subj: {subject_id}, Stage: {stage})")
        else:
             self.experimentListWidget.addItem("No experiments found in project.")

    def setup_batch_creation(self):
        """Initialize the batch creation page with experiments grid."""
        if not self.state_manager:
            logger.warning("StateManager not available for batch creation setup.")
            # Potentially disable parts of the UI or show an error
            self.batchIdLineEdit.setEnabled(False)
            self.batchNameLineEdit.setEnabled(False)
            self.batchDescriptionTextEdit.setEnabled(False)
            self.create_batch_button.setEnabled(False)
            self.batch_experiment_grid.set_columns(["Error"])
            self.batch_experiment_grid.populate_data([{"Error": "State Manager unavailable"}], ["Error"])
            return
        else:
            # Re-enable fields if they were disabled
            self.batchIdLineEdit.setEnabled(True)
            self.batchNameLineEdit.setEnabled(True)
            self.batchDescriptionTextEdit.setEnabled(True)

        # Generate a unique suggested batch ID
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.batchIdLineEdit.setText(f"batch_{timestamp}")

        # Clear previous form state
        self.batchNameLineEdit.clear()
        self.batchDescriptionTextEdit.clear()

        # Populate experiment grid using the existing method
        # This will also clear previous selections in the grid
        self.update_experiment_grid()

        # Reset notification and button state
        self.batch_notification_label.setText("")
        # The button state will be updated by on_experiment_selection_changed after grid population
        self.create_batch_button.setEnabled(False) # Start disabled

    def update_experiment_grid(self):
        """Update the grid display with experiments for batch creation."""
        if not self.state_manager:
            logger.warning("StateManager not available, cannot update experiment grid.")
            self.batch_experiment_grid.set_columns(["Error"])
            self.batch_experiment_grid.populate_data([{"Error": "State Manager unavailable"}], ["Error"])
            return

        # Get experiments (already sorted by StateManager's default)
        all_experiments = self.state_manager.get_sorted_list("experiments")
        logger.debug(f"Populating batch grid with {len(all_experiments)} experiments.")

        # Define columns matching MetadataGridDisplay's expectations
        columns = ["Select", "ID", "Type", "Subject", "Date", "Stage"]

        # Build experiment data including raw values for sorting
        exp_data = []
        for exp in all_experiments:
            raw_date = getattr(exp, 'date_recorded', None)
            raw_stage = getattr(exp, 'processing_stage', None)

            # Format date string for display
            date_str = "N/A"
            if raw_date and isinstance(raw_date, datetime):
                 date_str = raw_date.strftime("%Y-%m-%d")
            elif raw_date:
                 try:
                     parsed_date = datetime.fromisoformat(str(raw_date))
                     date_str = parsed_date.strftime("%Y-%m-%d")
                     raw_date = parsed_date # Use the actual datetime object for sorting key
                 except (ValueError, TypeError):
                     logger.warning(f"Could not parse date '{raw_date}' for exp {exp.id}. Displaying N/A.")
                     raw_date = None # Ensure raw_date is None if parsing fails

            # Create dict for each experiment row
            exp_dict = {
                "Select": False,  # Checkbox state (initial state is unchecked)
                "ID": getattr(exp, 'id', 'N/A'),
                "Type": getattr(exp, 'type', 'N/A'),
                "Subject": getattr(exp, 'subject_id', 'N/A'),
                "Date": date_str,                 # Display string
                "Stage": raw_stage or 'N/A',      # Display string
                # Raw data for sorting keys used by SortableTableWidgetItem
                "raw_date": raw_date,
                "raw_stage": raw_stage
            }
            exp_data.append(exp_dict)

        # Update the grid
        # Disconnect previous signal connection to avoid duplicates
        try:
             self.batch_experiment_grid.selection_changed.disconnect(self.on_experiment_selection_changed)
        except (RuntimeError, TypeError): pass # Ignore if not connected

        # Populate grid with selectable checkboxes
        self.batch_experiment_grid.set_columns(columns)
        self.batch_experiment_grid.populate_data(exp_data, columns, selectable=True, checkbox_column="Select")

        # Connect selection changed signal AFTER populating data
        self.batch_experiment_grid.selection_changed.connect(self.on_experiment_selection_changed)
        # Trigger initial update for button state and count label
        self.on_experiment_selection_changed("", False)

    def on_experiment_selection_changed(self, exp_id: str, is_selected: bool):
        """Handle experiment selection changes from the MetadataGridDisplay."""
        # No need to maintain self.selected_experiments separately.

        # Update the create button state based on the grid's current selection count
        selected_ids = self.batch_experiment_grid.get_selected_items()
        count = len(selected_ids)
        self.create_batch_button.setEnabled(count > 0)

        # Update notification label with count
        self.batch_notification_label.setText(f"{count} experiment(s) selected")
        # Optional: Log the change for debugging
        # logger.debug(f"Batch grid selection changed. Triggered by ID: {exp_id}, Selected: {is_selected}. Total selected: {count}")

    def handle_create_batch(self):
        """Create a new batch with the selected experiments."""
        if not self.project_manager or not self.state_manager:
            logger.error("ProjectManager or StateManager not available for creating batch.")
            QMessageBox.critical(self, "Error", "Core managers not available. Cannot create batch.")
            return

        # Get batch info from UI
        batch_id = self.batchIdLineEdit.text().strip()
        batch_name = self.batchNameLineEdit.text().strip() # Optional
        batch_description = self.batchDescriptionTextEdit.toPlainText().strip() # Optional

        # Validate required Batch ID
        if not batch_id:
            QMessageBox.warning(self, "Validation Error", "Batch ID is required.")
            return

        # Get selected experiments directly from the grid component
        selected_experiment_ids = self.batch_experiment_grid.get_selected_items()

        if not selected_experiment_ids:
            QMessageBox.warning(self, "Validation Error", "Please select at least one experiment to include in the batch.")
            return

        # Create the batch via ProjectManager
        try:
            logger.info(f"Attempting to create batch '{batch_id}' with {len(selected_experiment_ids)} experiments.")
            # Basic selection criteria (can be expanded later if needed)
            selection_criteria = {"manual_selection": True}
            if batch_name:
                 selection_criteria["batch_name"] = batch_name # Store name if provided
            if batch_description:
                 selection_criteria["description"] = batch_description # Store description if provided

            # Call the ProjectManager method
            self.project_manager.create_batch(
                batch_id=batch_id,
                batch_name=batch_name, # Pass optional name
                description=batch_description, # Pass optional description
                experiment_ids=list(selected_experiment_ids), # Pass the list of selected IDs
                selection_criteria=selection_criteria
            )

            # --- Success ---
            logger.info(f"Batch '{batch_id}' created successfully.")
            # Show success message via notification label, clear after delay
            self.batch_notification_label.setText(f"Batch '{batch_id}' created successfully!")
            QTimer.singleShot(3000, lambda: self.batch_notification_label.setText(""))

            # Reset the form for the next batch creation
            self.batchNameLineEdit.clear()
            self.batchDescriptionTextEdit.clear()
            # Generate a new suggested batch ID
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.batchIdLineEdit.setText(f"batch_{timestamp}")
            # Clear grid selection by re-populating
            self.update_experiment_grid() # This re-populates and inherently clears checkboxes

        except ValueError as ve: # Catch specific errors like duplicate batch ID
             logger.error(f"Failed to create batch '{batch_id}': {ve}", exc_info=False) # Log concisely
             QMessageBox.critical(self, "Batch Creation Error", f"Failed to create batch:\n{ve}")
             self.batch_notification_label.setText("Batch creation failed.")
        except Exception as e: # Catch unexpected errors
            logger.error(f"Unexpected error creating batch '{batch_id}': {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during batch creation:\n{str(e)}")
            self.batch_notification_label.setText("Batch creation failed.")

    def closeEvent(self, event):
        """Clean up when the view is closed."""
        # Unsubscribe the observer when the view is closed
        if hasattr(self, 'state_manager') and self.state_manager: # Check if state_manager exists
             try:
                 self.state_manager.unsubscribe(self.refresh_data)
                 logger.debug("Unsubscribed ExperimentView.refresh_data from StateManager.")
             except Exception as e:
                  logger.error(f"Error unsubscribing ExperimentView: {e}")
        else:
             logger.warning("StateManager not found during ExperimentView closeEvent, skipping unsubscribe.")
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
        
    def _discover_plugins(self):
        """
        Discovers and updates the available data handler and analysis plugins
        based on the selected experiment type.
        Finds handlers based on 'load_tracking_data' capability.
        Finds analysis plugins by listing those with capabilities beyond loading data
        and matching the selected experiment type.
        """
        # logger.debug("Discovering plugins...") # Commented out
        # Ensure plugin_manager is available
        if not self.plugin_manager:
            logger.warning("Plugin manager not available for discovery.")
            # Attempt to re-acquire if needed (e.g., if view was initialized before project loaded fully)
            if self.window() and hasattr(self.window(), 'project_manager') and self.window().project_manager:
                 self.plugin_manager = self.window().project_manager.plugin_manager
            if not self.plugin_manager:
                 logger.error("Plugin manager still not available after re-check.")
                 # Clear lists to avoid showing stale data
                 self.data_handler_plugin_list.clear()
                 self.analysis_plugin_list.clear()
                 self.clear_plugin_fields()
                 return

        # Clear previous entries and parameter fields
        self.data_handler_plugin_list.clear()
        self.analysis_plugin_list.clear()
        self.clear_plugin_fields()

        # Get the selected experiment type
        selected_type = self.experiment_type_combo.currentData()
        if not selected_type:
            # logger.debug("No experiment type selected, skipping plugin discovery.") # Commented out
            return # No type selected, nothing to discover

        # logger.debug(f"Discovering plugins for experiment type: {selected_type}") # Commented out

        all_plugins = self.plugin_manager.get_all_plugins()
        handler_plugins = set()
        analysis_plugins = set()

        # --- Find Data Handler Plugins ---
        # Find plugins capable of loading data. We generally don't filter handlers by experiment type,
        # as their primary function is data format recognition.
        data_loading_capability = 'load_tracking_data'
        potential_handlers = self.plugin_manager.get_plugins_with_capability(data_loading_capability)
        handler_plugins.update(potential_handlers)
        # logger.debug(f"Found {len(handler_plugins)} potential data handler plugins with capability '{data_loading_capability}'.") # Commented out

        # Populate Data Handler List (Sorted)
        for plugin in sorted(list(handler_plugins), key=lambda p: p.plugin_self_metadata().name):
            item = QListWidgetItem(plugin.plugin_self_metadata().name)
            item.setData(Qt.ItemDataRole.UserRole, plugin) # Store the actual plugin object
            self.data_handler_plugin_list.addItem(item)

        # --- Find Analysis Plugins ---
        # Find plugins that offer capabilities other than just data loading AND support the selected experiment type.
        # logger.debug(f"Filtering all {len(all_plugins)} plugins for analysis capabilities matching type '{selected_type}'...") # Commented out
        for plugin in all_plugins:
            capabilities = plugin.analysis_capabilities()
            # Check if it has *any* capability other than data loading
            has_analysis_capability = any(cap != data_loading_capability for cap in capabilities)

            # Check if it supports the selected experiment type
            meta = plugin.plugin_self_metadata()
            supports_type = (selected_type in getattr(meta, 'supported_experiment_types', []))

            if has_analysis_capability and supports_type:
                analysis_plugins.add(plugin)

        # logger.debug(f"Found {len(analysis_plugins)} potential analysis plugins supporting type '{selected_type}'.") # Commented out

        # Populate Analysis Plugin List (Sorted)
        for plugin in sorted(list(analysis_plugins), key=lambda p: p.plugin_self_metadata().name):
            item = QListWidgetItem(plugin.plugin_self_metadata().name)
            item.setData(Qt.ItemDataRole.UserRole, plugin) # Store the actual plugin object
            self.analysis_plugin_list.addItem(item)

        # Update button state based on whether plugins are now available etc.
        self._update_add_button_state()

    def _get_selected_plugins(self) -> List['BasePlugin']: # Forward reference if BasePlugin not imported yet
        """Helper to get the plugin objects currently selected in the UI lists."""
        selected_plugins = []
        # Data Handler (single selection)
        selected_handler_item = self.data_handler_plugin_list.currentItem()
        if selected_handler_item:
            plugin = selected_handler_item.data(Qt.ItemDataRole.UserRole)
            if plugin:
                selected_plugins.append(plugin)

        # Analysis Plugins (multi-selection)
        for i in range(self.analysis_plugin_list.count()):
             item = self.analysis_plugin_list.item(i)
             if item.isSelected():
                 plugin = item.data(Qt.ItemDataRole.UserRole)
                 # Avoid adding the same plugin twice if it's both a handler and analyzer
                 if plugin and plugin not in selected_plugins:
                     selected_plugins.append(plugin)

        return selected_plugins

    def _on_plugin_selection_changed(self):
        """Called when the selection in either plugin list changes."""
        self.update_plugin_fields()
        self._update_add_button_state()

    def _update_add_button_state(self):
        """
        Enables/disables the 'Add Experiment' button based on required core details
        AND validation of required plugin parameters.
        """
        # 1. Check core details
        core_details_valid = bool(
             self.experiment_id_input.text().strip() and
             self.subject_id_combo.currentIndex() > -1 and self.subject_id_combo.currentData() is not None and
             self.experiment_type_combo.currentIndex() > 0 and self.experiment_type_combo.currentData() is not None
        )

        # 2. Check if at least one plugin is selected
        selected_plugins = self._get_selected_plugins()
        plugins_selected = bool(selected_plugins)

        # 3. Check if all required plugin parameters are filled
        required_params_filled = True
        if plugins_selected and hasattr(self, 'plugin_field_widgets'):
            for plugin in selected_plugins:
                plugin_name = plugin.plugin_self_metadata().name
                required_fields = plugin.required_fields()
                field_widgets = self.plugin_field_widgets.get(plugin_name, {})

                for req_field in required_fields:
                    widget = field_widgets.get(req_field)
                    if not widget:
                        logger.warning(f"Required field '{req_field}' for plugin '{plugin_name}' has no corresponding widget.")
                        required_params_filled = False
                        break # No point checking further for this plugin

                    # Check widget value based on type
                    value = None
                    is_empty = False
                    if isinstance(widget, QLineEdit):
                        value = widget.text().strip()
                        if not value: is_empty = True
                    elif isinstance(widget, QComboBox):
                        # Assuming empty isn't possible unless no items exist, which shouldn't happen for required enums
                        value = widget.currentText() # Or check currentIndex > -1 if placeholder is possible
                    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                        value = widget.value() # Numeric types usually have a default, check if default is invalid? (More complex validation)
                    elif isinstance(widget, QCheckBox):
                        value = widget.isChecked() # Boolean always has a value
                    # Add checks for other widget types if necessary

                    if is_empty:
                        required_params_filled = False
                        # logger.debug(f"Required field '{req_field}' for plugin '{plugin_name}' is empty.") # Commented out
                        break # Stop checking this plugin's fields
                if not required_params_filled:
                    break # Stop checking other plugins

        # 4. Determine final state
        can_add = core_details_valid and plugins_selected and required_params_filled
        self.add_experiment_button.setEnabled(can_add)

        # Optional: Provide feedback if button is disabled
        if not self.add_experiment_button.isEnabled():
             tooltip_parts = []
             if not core_details_valid: tooltip_parts.append("Core details missing.")
             if not plugins_selected: tooltip_parts.append("Plugin selection missing.")
             if not required_params_filled and plugins_selected: tooltip_parts.append("Required plugin parameters missing.")
             self.add_experiment_button.setToolTip("Cannot add experiment: " + " ".join(tooltip_parts))
        else:
             self.add_experiment_button.setToolTip("") # Clear tooltip when enabled

    def clear_plugin_fields(self):
        """Clears the dynamically generated plugin parameter fields."""
        # Remove widgets from the layout manager first
        if hasattr(self, 'plugin_fields_layout'): # Check if layout exists
            while self.plugin_fields_layout.count():
                # Take the row item (which contains label and widget/layout)
                row_item = self.plugin_fields_layout.takeAt(0)
                if row_item:
                    # Remove label if it exists
                    label_item = self.plugin_fields_layout.itemAt(0, QFormLayout.LabelRole)
                    if label_item and label_item.widget():
                        label_item.widget().deleteLater()
                    # Remove field widget/layout if it exists
                    field_item = self.plugin_fields_layout.itemAt(0, QFormLayout.FieldRole)
                    if field_item:
                        if field_item.widget():
                             field_item.widget().deleteLater()
                        elif field_item.layout():
                            # Clean up layout children if it's a layout (like for file browser)
                            layout_to_clear = field_item.layout()
                            while layout_to_clear.count():
                                 child_item = layout_to_clear.takeAt(0)
                                 if child_item.widget():
                                     child_item.widget().deleteLater()
                            # Remove the layout itself (might not be necessary if parent group is hidden)
                            # but good practice
                            # field_item.layout().deleteLater() # Seems problematic, hiding group is enough
            # Hide the group box
            if hasattr(self, 'plugin_params_group'):
                 self.plugin_params_group.setVisible(False)
        # Reset the storage for widgets
        self.plugin_field_widgets = {}

    def update_plugin_fields(self):
        """
        Dynamically generates input fields in the 'Plugin Parameters' section
        based on the requirements of the currently selected plugin(s).
        """
        self.clear_plugin_fields() # Clear previous fields first
        selected_plugins = self._get_selected_plugins()

        if not selected_plugins:
            # logger.debug("No plugins selected, skipping field generation.") # Commented out
            return # No plugins selected, nothing to show

        # logger.debug(f"Updating fields for selected plugins: {[p.plugin_self_metadata().name for p in selected_plugins]}") # Commented out

        # Store widgets keyed by plugin name and field name for later retrieval
        self.plugin_field_widgets = {}
        any_fields_added = False

        for plugin in selected_plugins:
             plugin_name = plugin.plugin_self_metadata().name
             self.plugin_field_widgets[plugin_name] = {}

             required = plugin.required_fields()
             optional = plugin.optional_fields()
             all_fields = sorted(required + optional) # Sort for consistent order

             if not all_fields:
                 logger.debug(f"Plugin '{plugin_name}' has no configurable parameters.")
                 continue # Plugin has no configurable parameters

             any_fields_added = True # Mark that we are adding fields

             # Add a separator/label for the plugin's parameters
             plugin_label = QLabel(f"Parameters for {plugin_name}:")
             # Set a property to allow styling via QSS instead of inline
             plugin_label.setProperty("class", "mus1-plugin-param-header") 
             # Add label spanning both columns of the QFormLayout
             self.plugin_fields_layout.addRow(plugin_label)

             field_types = plugin.get_field_types()
             field_descriptions = plugin.get_field_descriptions()

             for field_name in all_fields:
                 is_required = field_name in required
                 field_type = field_types.get(field_name, 'string') # Default to string
                 description = field_descriptions.get(field_name, '')

                 widget_or_layout = self._create_field_widget(plugin, field_name, field_type)
                 if widget_or_layout:
                     label_text = f"{field_name}{' *' if is_required else ''}:"
                     form_label = self.create_form_label(label_text)
                     if description:
                         form_label.setToolTip(description) # Add tooltip for description

                     # Set property for QSS styling of required fields
                     form_label.setProperty("fieldRequired", is_required)
                     # Reapply style to ensure property takes effect (might be redundant if theme updates handle it)
                     # self.style().unpolish(form_label)
                     # self.style().polish(form_label)

                     # Add the row with the label and the widget/layout
                     if isinstance(widget_or_layout, QLayout):
                         self.plugin_fields_layout.addRow(form_label, widget_or_layout)
                         # Find the primary input widget within the layout for storage
                         # (Assuming QLineEdit is the main input for file/dir)
                         input_widget = None
                         for i in range(widget_or_layout.count()):
                              item_widget = widget_or_layout.itemAt(i).widget()
                              if isinstance(item_widget, QLineEdit):
                                  input_widget = item_widget
                                  break
                         if input_widget:
                             self.plugin_field_widgets[plugin_name][field_name] = input_widget
                         else:
                              logger.warning(f"Could not find primary input widget in layout for field '{field_name}'")
                     else: # It's a simple widget
                         self.plugin_fields_layout.addRow(form_label, widget_or_layout)
                         self.plugin_field_widgets[plugin_name][field_name] = widget_or_layout

        # Make the parameters group box visible only if any fields were actually added
        self.plugin_params_group.setVisible(any_fields_added)
        # Adjust size policy or update layout if needed after adding widgets
        self.plugin_params_group.adjustSize()
        page_widget = self.plugin_params_group.parentWidget()
        if page_widget: page_widget.layout().activate() # Force layout update

    def _create_field_widget(self, plugin, field_name, field_type='string'):
        """Creates the appropriate input widget based on the field type."""
        # logger.debug(f"Creating widget for field '{field_name}' with type '{field_type}'") # Commented out
        widget = None

        if field_type == 'int':
            widget = QSpinBox()
            widget.setRange(-10000, 10000) # Example range, adjust as needed
            widget.setProperty("class", "mus1-spin-box")
        elif field_type == 'float':
            widget = QDoubleSpinBox()
            widget.setRange(-10000.0, 10000.0) # Example range
            widget.setDecimals(3) # Example precision
            widget.setProperty("class", "mus1-double-spin-box")
        elif field_type == 'bool':
            widget = QCheckBox()
            widget.setProperty("class", "mus1-check-box")
        elif field_type.startswith('enum:'):
            widget = QComboBox()
            widget.setProperty("class", "mus1-combo-box")
            options = field_type.split(':', 1)[1].split(',')
            widget.addItems([opt.strip() for opt in options])
        elif field_type == 'file' or field_type == 'directory':
            # Create a layout with LineEdit and Browse button
            hbox = QHBoxLayout()
            hbox.setContentsMargins(0,0,0,0)
            hbox.setSpacing(self.CONTROL_SPACING)
            line_edit = QLineEdit()
            line_edit.setProperty("class", "mus1-text-input")
            line_edit.setPlaceholderText(f"Select {field_type}...")
            browse_button = QPushButton("Browse...")
            browse_button.setProperty("class", "mus1-secondary-button")
            # Use lambda to pass the specific line_edit and type to the browser function
            browse_button.clicked.connect(lambda checked=False, le=line_edit, ft=field_type: self._browse_for_path(le, ft))
            hbox.addWidget(line_edit, 1) # Line edit takes most space
            hbox.addWidget(browse_button)
            return hbox # Return the layout itself
        else: # Default to string/text
            widget = QLineEdit()
            widget.setProperty("class", "mus1-text-input")
            if field_type != 'string': # Log if using fallback
                 logger.warning(f"Unknown field type '{field_type}' for '{field_name}'. Defaulting to QLineEdit.")

        return widget

    def _browse_for_path(self, line_edit_widget: QLineEdit, field_type: str):
        """Opens a file or directory dialog and sets the path in the line edit."""
        current_path = line_edit_widget.text()
        start_dir = str(Path(current_path).parent if current_path and Path(current_path).exists() else Path.home())

        path = ""
        if field_type == 'file':
            # TODO: Could potentially get specific file filters from plugin?
            path, _ = QFileDialog.getOpenFileName(self, "Select File", start_dir, "All Files (*)")
        elif field_type == 'directory':
            path = QFileDialog.getExistingDirectory(self, "Select Directory", start_dir)

        if path:
            line_edit_widget.setText(path)
        