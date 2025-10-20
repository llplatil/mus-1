from .qt import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QDateTimeEdit, QPushButton, QGroupBox, QScrollArea,
    QCheckBox, QMessageBox, QListWidget, QListWidgetItem, QTextEdit, QHBoxLayout,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QDoubleSpinBox, QAbstractItemView, QStackedWidget, QLayout,
    QTimer, Qt, QDateTime
)
from datetime import datetime
from .navigation_pane import NavigationPane
from .base_view import BaseView
from .metadata_display import MetadataGridDisplay
from .gui_services import GUIExperimentService
from ..core.utils.file_hash import compute_sample_hash
from ..core.metadata import ProcessingStage, VideoFile
import os
import json
from pathlib import Path
from ..core.logging_bus import LoggingEventBus
from typing import List
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..plugins.base_plugin import BasePlugin

class ExperimentView(BaseView):
    def __init__(self, parent=None):
        super().__init__(parent, view_name="experiments")

        # Initialize logging
        self.log_bus = LoggingEventBus.get_instance()

        # Initialize GUI services and dependent service handles
        self.gui_services = None  # Will be set when project is loaded
        self.plugin_manager = None  # Will be set when project is loaded
        self.subject_service = None  # Avoid AttributeError before services are ready
        self.experiment_service = None
        self.plugin_service = None

        # Fetch processing stages from the new metadata
        self.PROCESSING_STAGES = [stage.value for stage in ProcessingStage]
        
        # Set up navigation first (added 'Add Multiple Experiments')
        self.setup_navigation(["Add Experiment", "Add Multiple Experiments", "View Experiments", "Create Batch"])
        
        # Set up pages
        self.setup_add_experiment_page()
        self.setup_add_multiple_experiments_page()
        self.setup_view_experiments_page()
        self.setup_create_batch_page()
        
        # Do not change pages or refresh here; lifecycle hooks will handle

    # --- Lifecycle hooks ---
    def on_services_ready(self, services):
        super().on_services_ready(services)
        # services is the GUIServiceFactory, create the services we need
        self.gui_services = services
        self.experiment_service = services.create_experiment_service()
        self.plugin_service = services.create_plugin_service()
        self.subject_service = services.create_subject_service()
        try:
            # Ensure UI controls like combos are populated once
            # then show default page
            self.change_page(0)
            self.refresh_data()
        except Exception as e:
            self.log_bus.log(f"Error in ExperimentView.on_services_ready: {e}", "error", "ExperimentView")
        # Subscribe to context changes to refresh when user/lab/project changes
        try:
            mw = self.window()
            if mw and hasattr(mw, 'contextChanged'):
                mw.contextChanged.connect(lambda _ctx: self.refresh_data())
        except Exception:
            pass

    def set_plugin_manager(self, plugin_manager):
        """Set the plugin manager for this view."""
        self.plugin_manager = plugin_manager
        self.log_bus.log("Plugin manager set on ExperimentView", "info", "ExperimentView")

    def on_activated(self):
        self.refresh_data()

    def setup_add_experiment_page(self):
        """Sets up the 'Add Experiment' sub-page according to the new workflow."""
        # ------------------------------------------------------------------
        # Build container → scroll area → content hierarchy
        # ------------------------------------------------------------------
        # Top-level container that will be inserted into the BaseView pages
        page_container = QWidget()
        container_layout = QVBoxLayout(page_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Scroll area keeps the long form usable on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container_layout.addWidget(scroll)

        # Inner widget – real content of the Add-Experiment form
        page_widget = QWidget()
        scroll.setWidget(page_widget)

        # Layout for the inner widget
        page_layout = QVBoxLayout(page_widget)
        page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        page_layout.setSpacing(self.SECTION_SPACING)

        # --- 1. Recording Details (placed first) ---
        rec_group, rec_container_layout = self.create_form_section("Recording Details", page_layout)

        # --- Video file row ---
        _, self.video_path_edit, browse_video_btn = self.create_form_field_with_button(
            "Video File", "line_edit", "Browse…", "Select video file…", parent_layout=rec_container_layout
        )
        if browse_video_btn:
            browse_video_btn.clicked.connect(lambda: self._browse_for_path(self.video_path_edit, "file"))

        # --- Arena image row (optional) ---
        _, self.arena_image_edit, browse_arena_btn = self.create_form_field_with_button(
            "Arena Image", "line_edit", "Browse…", "Select arena image (optional)…", parent_layout=rec_container_layout
        )
        if browse_arena_btn:
            browse_arena_btn.clicked.connect(lambda: self._browse_for_path(self.arena_image_edit, "file"))

        # --- Processing stage row ---
        _, self.processing_stage_combo = self.create_form_field("Processing Stage", "combo_box", parent_layout=rec_container_layout)
        self.processing_stage_combo.addItems(self.PROCESSING_STAGES)

        # --- Quick Sample Hash Row (auto-computed) ---
        self.sample_hash_value = QLabel("—")
        self.sample_hash_value.setProperty("class", "mus1-input-label")
        self.create_form_display_field("Sample Hash", self.sample_hash_value, rec_container_layout)

        # Auto-change stage when video selected
        self.video_path_edit.textChanged.connect(self._auto_stage_from_video)
        self.video_path_edit.textChanged.connect(self._suggest_experiment_id)
        self.video_path_edit.textChanged.connect(self._on_video_path_changed)

        # Initialize hash and date based on blank path
        self._on_video_path_changed("")

        # --- 2. Core Experiment Details ---
        details_group, details_layout = self.create_form_section("Core Experiment Details", page_layout)

        # Experiment ID
        _, self.experiment_id_input = self.create_form_field(
            "Experiment ID", "line_edit", "Enter unique experiment ID", True, details_layout
        )
        self.experiment_id_input.setObjectName("experimentIdInput")
        self.experiment_id_input.textChanged.connect(self._update_add_button_state)

        # Subject ID
        _, self.subject_id_combo = self.create_form_field("Subject ID", "combo_box", required=True, parent_layout=details_layout)
        self.subject_id_combo.setObjectName("subjectIdCombo")
        self.subject_id_combo.currentIndexChanged.connect(self._update_add_button_state)

        # Experiment Type
        _, self.experiment_type_combo = self.create_form_field("Experiment Type", "combo_box", required=True, parent_layout=details_layout)
        self.experiment_type_combo.setObjectName("experimentTypeCombo")
        self.experiment_type_combo.addItem("Select Type...", None)
        self.experiment_type_combo.currentIndexChanged.connect(self._on_experiment_type_changed)

        # Experiment Subtype (optional, driven by plugins)
        _, self.experiment_subtype_combo = self.create_form_field("Subtype", "combo_box", parent_layout=details_layout)
        self.experiment_subtype_combo.setObjectName("experimentSubtypeCombo")
        self.experiment_subtype_combo.setEnabled(False)
        self.experiment_subtype_combo.currentIndexChanged.connect(self._update_add_button_state)

        # Date Recorded
        date_row, self.date_recorded_edit = self.create_form_field("Date Recorded", "date_time_edit", required=True, parent_layout=details_layout)
        self.date_recorded_edit.setDisplayFormat("yyyy-MM-dd")

        # --- 3. Plugin Selection ---
        # Importer Plugins (includes handler-type plugins)
        importer_group, importer_layout = self.create_form_section("Importer Plugins", page_layout)
        self.importer_plugin_list = QListWidget()
        self.importer_plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.importer_plugin_list.itemSelectionChanged.connect(self._update_add_button_state)
        self.importer_plugin_list.itemSelectionChanged.connect(self._on_plugin_selection_changed)
        importer_layout.addWidget(self.importer_plugin_list)

        # Keep backward-compat alias so existing methods referencing data_handler_plugin_list still work
        self.data_handler_plugin_list = self.importer_plugin_list

        # Analysis Plugins
        analysis_group, analysis_layout = self.create_form_section("Analysis Plugins", page_layout)
        self.analysis_plugin_list = QListWidget()
        self.analysis_plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.analysis_plugin_list.itemSelectionChanged.connect(self._update_add_button_state)
        self.analysis_plugin_list.itemSelectionChanged.connect(self._on_plugin_selection_changed)
        analysis_layout.addWidget(self.analysis_plugin_list)

        # Exporter Plugins
        exporter_group, exporter_layout = self.create_form_section("Exporter Plugins", page_layout)
        self.exporter_plugin_list = QListWidget()
        self.exporter_plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.exporter_plugin_list.itemSelectionChanged.connect(self._update_add_button_state)
        self.exporter_plugin_list.itemSelectionChanged.connect(self._on_plugin_selection_changed)
        exporter_layout.addWidget(self.exporter_plugin_list)

        # --- 4. Plugin Parameters ---
        # Use a dedicated form layout that will be populated on-the-fly in update_plugin_fields()
        self.plugin_params_group, plugin_params_container_layout = self.create_form_section("Plugin Parameters", page_layout)
        self.plugin_fields_layout = QFormLayout()
        self.plugin_fields_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        self.plugin_fields_layout.setVerticalSpacing(self.CONTROL_SPACING)
        plugin_params_container_layout.addLayout(self.plugin_fields_layout)
        self.plugin_params_group.setVisible(False)  # Hidden until at least one field is shown

        # --- Add Button ---
        # Use helper to create a button row that aligns button to the right
        button_row = self.create_button_row(page_layout, add_stretch=True)
        self.add_experiment_button = QPushButton("Add Experiment")
        self.add_experiment_button.setObjectName("addExperimentButton")
        self.add_experiment_button.setProperty("class", "mus1-primary-button")
        self.add_experiment_button.setEnabled(False) # Disabled initially
        self.add_experiment_button.clicked.connect(self.handle_add_experiment)
        button_row.addWidget(self.add_experiment_button)

        # --- Add Page to Main View Stack ---
        # Add the top-level container (which now hosts the wizard) to the
        # ExperimentView's stacked widget system
        self.add_page(page_container, "Add Experiment")

        # Initial data population (like subject/type combos) will happen in refresh_data
        # Initial plugin discovery will also be triggered by refresh_data

        # Ensure button state is correct on first display
        self._update_add_button_state()

    def setup_add_multiple_experiments_page(self):
        """Sets up the 'Add Multiple Experiments' sub-page with an entry table."""
        page_container = QWidget()
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        page_layout.setSpacing(self.SECTION_SPACING)

        title_label = QLabel("Add Multiple Experiments")
        title_label.setProperty("class", "mus1-page-title")
        page_layout.addWidget(title_label)

        # Table for experiment entry
        self.multi_exp_table = QTableWidget(0, 6)
        self.multi_exp_table.setHorizontalHeaderLabels(["Experiment ID", "Subject", "Type", "Date", "Stage", "Video Path"])
        self.multi_exp_table.horizontalHeader().setStretchLastSection(True)
        self.multi_exp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        page_layout.addWidget(self.multi_exp_table)

        # Buttons row
        btn_row = self.create_button_row(page_layout, add_stretch=True)
        add_row_btn = QPushButton("Add Row")
        add_row_btn.setProperty("class", "mus1-secondary-button")
        add_row_btn.clicked.connect(self._multi_add_row)
        btn_row.addWidget(add_row_btn)

        remove_row_btn = QPushButton("Remove Selected")
        remove_row_btn.setProperty("class", "mus1-secondary-button")
        remove_row_btn.clicked.connect(self._multi_remove_selected_rows)
        btn_row.addWidget(remove_row_btn)

        save_btn = QPushButton("Save Experiments")
        save_btn.setProperty("class", "mus1-primary-button")
        save_btn.clicked.connect(self._multi_save_experiments)
        btn_row.addWidget(save_btn)

        # Back button
        back_button = QPushButton("Back to Single Experiment Add")
        back_button.setProperty("class", "mus1-secondary-button")
        back_button.clicked.connect(lambda: self.change_page(0))
        page_layout.addWidget(back_button)

        self.add_page(page_container, "Add Multiple Experiments")

    def setup_view_experiments_page(self):
        """Setup the View Experiments page."""
        # Create the page widget
        self.page_view_exp = QWidget()
        view_exp_layout = QVBoxLayout(self.page_view_exp)
        view_exp_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        view_exp_layout.setSpacing(self.SECTION_SPACING)
        
        # Add title
        view_exp_layout.addWidget(QLabel("Experiments"))
        
        # Create experiment list
        self.experimentListWidget = QListWidget()
        view_exp_layout.addWidget(self.experimentListWidget)
        
        # --- Actions Row ---
        actions_row = self.create_button_row(view_exp_layout)
        self.link_video_button = QPushButton("Link Video…")
        self.link_video_button.setObjectName("linkVideoButton")
        self.link_video_button.setProperty("class", "mus1-secondary-button")
        self.link_video_button.clicked.connect(self.handle_link_video)
        actions_row.addWidget(self.link_video_button)

        # --- Recording Info Group ---
        info_group, info_layout = self.create_form_section("Recording Info", view_exp_layout)
        self.rec_path_label = QLabel("Path: —")
        self.rec_status_label = QLabel("Status: —")
        self.rec_size_label = QLabel("Size: —")
        self.rec_hash_label = QLabel("Sample-hash: —")
        info_layout.addWidget(self.rec_path_label)
        info_layout.addWidget(self.rec_status_label)
        info_layout.addWidget(self.rec_size_label)
        info_layout.addWidget(self.rec_hash_label)

        # Connect selection change to update info
        self.experimentListWidget.currentItemChanged.connect(self._on_experiment_selected)
        
        # Add the page to the stacked widget
        self.add_page(self.page_view_exp, "View Experiments")
        
    def setup_create_batch_page(self):
        """Set up the Create Batch page."""
        # Main widget for the page
        self.page_create_batch = QWidget()
        batch_layout = QVBoxLayout(self.page_create_batch)
        batch_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        batch_layout.setSpacing(self.SECTION_SPACING)

        # Batch Details Section (explicit QFormLayout for predictability)
        batch_details_group, _container_layout = self.create_form_section("Batch Details", batch_layout)
        batch_details_form = QFormLayout()
        batch_details_form.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        batch_details_form.setVerticalSpacing(self.CONTROL_SPACING)
        # Do not replace the group's existing container layout; add the form layout inside it
        _container_layout.addLayout(batch_details_form)

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

        # Use MetadataGridDisplay for experiment selection with selectable rows
        self.batch_experiment_grid = MetadataGridDisplay(self)
        experiment_selection_layout.addWidget(self.batch_experiment_grid)
        # Double-click opens the experiment editor by ID
        try:
            self.batch_experiment_grid.row_activated.connect(self._handle_open_experiment_by_id)
        except Exception:
            pass
        
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

    def refresh_data(self):
        """Refresh data based on the current page."""
        current_index = self.pages.currentIndex()
        # Corrected: Get page title from the list stored in BaseView
        page_title = "Unknown Page" # Default title
        if hasattr(self, 'navigation_button_texts') and 0 <= current_index < len(self.navigation_button_texts):
             page_title = self.navigation_button_texts[current_index]
        else:
             self.log_bus.log(f"Could not determine page title for index {current_index}.", "warning", "ExperimentView")

        self.log_bus.log(f"Refreshing data for page: {page_title} (Index: {current_index})", "info", "ExperimentView")

        if page_title == "Add Experiment":
             # Populate subject combo using subject service
             self.subject_id_combo.clear()
             if self.subject_service:
                 subjects = self.subject_service.get_subjects_for_display()
                 if subjects:
                     for subject in subjects:
                         display_text = f"{subject.id} ({subject.sex_display}, {subject.age_display})"
                         self.subject_id_combo.addItem(display_text, subject.id)
                 else:
                      self.subject_id_combo.addItem("No subjects available", None)
             else:
                 self.subject_id_combo.addItem("Subject service not available", None)

             # Populate experiment type combo with basic types for now
             # TODO: Get from configuration when implemented
             self.experiment_type_combo.clear()
             self.experiment_type_combo.addItem("Select Type...", None)
             basic_types = ["OpenField", "NOR", "Rotarod", "FearConditioning", "MorrisWaterMaze"]
             for exp_type in basic_types:
                 self.experiment_type_combo.addItem(exp_type, exp_type)

             # Trigger plugin discovery now that plugin service is integrated
             self._discover_plugins()

        elif page_title == "View Experiments":
             self.refresh_experiment_list_display()
        elif page_title == "Create Batch":
             self.setup_batch_creation() # Re-initialize batch creation UI/data
             # Populate the grid with selectable experiments
             try:
                 experiments = self.experiment_service.get_experiments_for_display() if self.experiment_service else []
                 columns = ["Select", "ID", "Type", "Subject", "Date", "Stage", "Recordings"]
                 grid_data = []
                 for exp in experiments:
                     recordings = 0
                     try:
                         if hasattr(self.window(), 'project_manager') and self.window().project_manager:
                             recordings = len(self.window().project_manager.get_videos_for_experiment(exp.id))
                     except Exception as e:
                         self.log_bus.log(f"Error counting recordings for experiment {exp.id}: {e}", "warning", "ExperimentView")
                         recordings = 0
                     grid_data.append({
                         "Select": False,
                         "ID": exp.id,
                         "Type": exp.experiment_type,
                         "Subject": exp.subject_id,
                         "Date": exp.date_recorded,
                         "raw_date": exp.date_recorded,
                         "Stage": exp.processing_stage,
                         "raw_stage": exp.processing_stage,
                         "Recordings": recordings,
                     })
                 if hasattr(self, 'batch_experiment_grid'):
                     self.batch_experiment_grid.set_columns(columns)
                     self.batch_experiment_grid.populate_data(grid_data, columns, selectable=True, checkbox_column="Select")
             except Exception as e:
                 self.log_bus.log(f"Error loading batch experiments: {e}", "error", "ExperimentView")
                 if hasattr(self, 'batch_experiment_grid'):
                     self.batch_experiment_grid.set_columns(["Status"])
                     self.batch_experiment_grid.populate_data([{"Status": "Error loading experiments"}], ["Status"])

    def _handle_open_experiment_by_id(self, experiment_id: str):
        """Open/focus the experiment editor and preselect subject for a given experiment ID."""
        try:
            if not experiment_id:
                return
            # Switch to Add Experiment page
            if hasattr(self, 'navigation_button_texts'):
                try:
                    target_index = self.navigation_button_texts.index("Add Experiment")
                    self.change_page(target_index)
                except ValueError:
                    pass
            # Prefill subject combo
            if self.experiment_service and hasattr(self, 'subject_id_combo'):
                exp = self.experiment_service.get_experiment_by_id(experiment_id)
                if exp:
                    idx = self.subject_id_combo.findText(getattr(exp, 'subject_id', ''))
                    if idx >= 0:
                        self.subject_id_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _on_experiment_type_changed(self):
        """Handle changes to experiment type: refresh subtypes and plugins."""
        try:
            self._discover_plugins()
        finally:
            self._update_add_button_state()

    def clear_plugin_selection(self):
        """Removes all dynamically generated plugin checkboxes and info labels."""
        # This method is likely obsolete as plugins are now shown in ListWidgets
        self.log_bus.log("clear_plugin_selection may be obsolete with ListWidget approach.", "warning", "ExperimentView")
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
        self.log_bus.log("Attempting to add experiment...", "info", "ExperimentView")

        # --- Validation (Basic - more done by button state check) ---
        experiment_id = self.experiment_id_input.text().strip()
        subject_id = self.subject_id_combo.currentData()
        exp_type = self.experiment_type_combo.currentData()
        # Convert QDateTime -> datetime (PySide 6.4+: toPython(); older: toPyDateTime())
        qt_dt = self.date_recorded_edit.dateTime()
        try:
            date_recorded = qt_dt.toPython()
        except AttributeError:
            date_recorded = qt_dt.toPyDateTime()

        # Redundant basic checks, but good as a safeguard
        if not all([experiment_id, subject_id, exp_type]):
            self.show_error_message("Validation Error", "Experiment ID, Subject ID, and Experiment Type are required.")
            return

        selected_plugins = self._get_selected_plugins()  # May be empty
        # Allow experiment without plugins; but if none selected skip plugin validation
        if selected_plugins:
            associated_plugin_names = [p.plugin_self_metadata().name for p in selected_plugins]
        else:
            associated_plugin_names = []

        # Collect plugin parameters (empty dict if no plugins)
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
                     self.log_bus.log(f"No widgets found for plugin '{plugin_name}' even though it has fields.", "warning", "ExperimentView")
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
                            self.log_bus.log(f"Optional field '{field_name}' for plugin '{plugin_name}' has no widget, skipping.", "info", "ExperimentView")
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
                    elif isinstance(widget, QTextEdit):
                        value = widget.toPlainText().strip()
                        if not value:
                            is_empty = True
                    # Add other widget types if needed

                    plugin_params_data[plugin_name][field_name] = value

        except ValueError as e:
             self.show_error_message("Parameter Error", str(e))
             return
        except Exception as e: # Catch potential errors during value extraction
            self.log_bus.log(f"Error collecting parameters: {e}", "error", "ExperimentView", "ExperimentView")
            self.show_error_message("Parameter Error", f"Error processing parameters:\n{e}")
            return


        # Determine processing stage
        processing_stage = self.processing_stage_combo.currentText()
        if not processing_stage:
            processing_stage = "planned"

        if not associated_plugin_names:
            # If no plugins, keep stage as chosen (could be recorded if video provided)
            pass
        else:
            for plugin in selected_plugins:
                if 'load_tracking_data' in plugin.analysis_capabilities():
                    processing_stage = "recorded"
                    break

        # --- Call GUI Service ---
        try:
            self.log_bus.log(f"Adding experiment '{experiment_id}'", "info", "ExperimentView")

            # Ensure GUI services are available
            if not self.gui_services:
                 self.log_bus.log("GUI services not available. Cannot add experiment.", "error", "ExperimentView")
                 self.show_error_message("Internal Error", "GUI services not initialized.")
                 return

            # Call GUI service with simplified parameters for now
            # TODO: Add plugin support when plugins are integrated
            experiment = self.experiment_service.add_experiment(
                experiment_id=experiment_id,
                subject_id=subject_id,
                experiment_type=exp_type,
                date_recorded=date_recorded,
                processing_stage=processing_stage
            )

            if not experiment:
                return  # Error already handled by service
            # Clear form on success
            self.experiment_id_input.clear()
            # Keep Subject selected? Maybe useful for adding multiple experiments for one subject.
            # self.subject_id_combo.setCurrentIndex(-1)
            self.experiment_type_combo.setCurrentIndex(0) # Reset type triggers plugin clear
            # self.date_recorded_edit.setDateTime(datetime.now()) # Keep date?
            self.clear_plugin_fields() # This is called by _discover_plugins when type changes
            # Link video if provided
            video_path_text = self.video_path_edit.text().strip()
            if video_path_text:
                video_path = Path(video_path_text)
                try:
                    if video_path.exists():
                        self.log_bus.log(f"Linking video {video_path} to {experiment_id}", "info", "ExperimentView")
                        self.window().project_manager.link_video_to_experiment(
                            experiment_id=experiment_id,
                            video_path=video_path,
                            notes="Linked via Add-Experiment form",
                        )
                        self.log_bus.log("Video linked successfully", "info", "ExperimentView")
                        # Auto-set stage to recorded if not already
                        if processing_stage == "planned":
                            # Update the experiment's processing stage to recorded via ProjectManagerClean API
                            try:
                                updated = self.window().project_manager.get_experiment(experiment_id)
                                if updated:
                                    updated.processing_stage = ProcessingStage.RECORDED
                                    self.window().project_manager.add_experiment(updated)
                            except Exception:
                                pass
                except FileNotFoundError as fnf:
                    self.log_bus.log(f"Video file not found: {fnf}", "error", "ExperimentView")
                    self.show_error_message("File Error", str(fnf))
                except ValueError as ve:
                    self.log_bus.log(f"Linking failed: {ve}", "error", "ExperimentView")
                    self.show_error_message("Linking Error", str(ve))
                except Exception as e:
                    self.log_bus.log(f"Unexpected error linking video: {e}", "error", "ExperimentView", "ExperimentView")
                    self.show_error_message("Unexpected Error", str(e))
                    raise  # Re-raise unexpected errors

            # Manually clear lists after successful add
            try:
                if hasattr(self, 'data_handler_plugin_list') and self.data_handler_plugin_list:
                    self.data_handler_plugin_list.clearSelection()
            except RuntimeError:
                pass
            try:
                if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                    self.analysis_plugin_list.clearSelection()
            except RuntimeError:
                pass
            try:
                if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                    self.exporter_plugin_list.clearSelection()
            except RuntimeError:
                pass
            # Button will be disabled by _update_add_button_state triggered by combo/list changes

            self.log_bus.log(f"Experiment '{experiment_id}' added successfully.", "info", "ExperimentView")
            if hasattr(self, 'navigation_pane'):
                self.log_bus.log(f"Experiment '{experiment_id}' added.", "success", "ExperimentView")

        except ValueError as e:
            self.log_bus.log(f"Error adding experiment: {e}", "error", "ExperimentView", "ExperimentView")
            if hasattr(self, 'navigation_pane'):
                self.log_bus.log(f"Failed to add experiment: {e}", "error", "ExperimentView")
        except Exception as e:
            self.log_bus.log(f"Unexpected error adding experiment: {e}", "error", "ExperimentView", "ExperimentView")
            if hasattr(self, 'navigation_pane'):
                self.log_bus.log(f"Unexpected error adding experiment: {e}", "error", "ExperimentView")

    def refresh_experiment_list_display(self):
        if not self.gui_services:
             self.log_bus.log("GUI services not available, cannot refresh experiment list.", "warning", "ExperimentView")
             self.experimentListWidget.clear()
             self.experimentListWidget.addItem("Error: GUI services unavailable.")
             return

        experiments = self.experiment_service.get_experiments_for_display()
        self.experimentListWidget.clear()

        if experiments:
            for exp in experiments:
                # Check for associated videos using proper associations
                associated_videos = self._find_associated_videos(exp.id)
                has_video = len(associated_videos) > 0

                video_marker = " 📹" if has_video else ""

                display_text = f"{exp.id} ({exp.experiment_type}, Subj: {exp.subject_id}, Stage: {exp.processing_stage}){video_marker}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, exp.id)  # Store ID for reliable lookup
                self.experimentListWidget.addItem(item)
        else:
             self.experimentListWidget.addItem("No experiments found in project.")

    def setup_batch_creation(self):
        """Initialize the batch creation page with experiments grid."""
        # Enable batch creation UI elements
        if hasattr(self, 'batchIdLineEdit'):
            self.batchIdLineEdit.setEnabled(True)
        if hasattr(self, 'batchNameLineEdit'):
            self.batchNameLineEdit.setEnabled(True)
        if hasattr(self, 'batchDescriptionTextEdit'):
            self.batchDescriptionTextEdit.setEnabled(True)
        if hasattr(self, 'create_batch_button'):
            self.create_batch_button.setEnabled(False)  # Will be enabled when experiments are selected

        # Generate a unique suggested batch ID
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.batchIdLineEdit.setText(f"batch_{timestamp}")

        # Clear previous form state
        self.batchNameLineEdit.clear()
        self.batchDescriptionTextEdit.clear()

        # Populate experiment grid with actual experiments
        self.update_experiment_grid()

        # Reset notification and button state
        self.batch_notification_label.setText("")
        # The button state will be updated by on_experiment_selection_changed after grid population
        self.create_batch_button.setEnabled(False) # Start disabled until experiments are selected

    def update_experiment_grid(self):
        """Update the grid display with experiments for batch creation."""
        if not self.gui_services:
            self.log_bus.log("GUI services not available for experiment grid update.", "warning", "ExperimentView")
            if hasattr(self, 'batch_experiment_grid'):
                self.batch_experiment_grid.set_columns(["Status"])
                self.batch_experiment_grid.populate_data([{"Status": "GUI services unavailable"}], ["Status"])
            return

        try:
            # Get all experiments
            experiments = self.experiment_service.get_experiments_for_display()

            if experiments:
                # Convert to format expected by MetadataGridDisplay
                grid_data = []
                for exp in experiments:
                    # Check for associated videos
                    associated_videos = self._find_associated_videos(exp.id)
                    has_video = len(associated_videos) > 0
                    video_status = "Yes" if has_video else "No"

                    grid_data.append({
                        "ID": exp.id,
                        "Type": exp.experiment_type,
                        "Subject": exp.subject_id,
                        "Stage": exp.processing_stage.value if hasattr(exp.processing_stage, 'value') else str(exp.processing_stage),
                        "Date": exp.date_recorded.strftime('%Y-%m-%d') if exp.date_recorded else 'N/A',
                        "Video": video_status
                    })

                # Define columns to display
                columns = ["ID", "Type", "Subject", "Stage", "Date", "Video"]

                if hasattr(self, 'batch_experiment_grid'):
                    self.batch_experiment_grid.set_columns(columns)
                    self.batch_experiment_grid.populate_data(grid_data, columns)
                    self.log_bus.log(f"Populated experiment grid with {len(grid_data, "info", "ExperimentView")} experiments")
            else:
                if hasattr(self, 'batch_experiment_grid'):
                    self.batch_experiment_grid.set_columns(["Status"])
                    self.batch_experiment_grid.populate_data([{"Status": "No experiments found in project"}], ["Status"])

        except Exception as e:
            self.log_bus.log(f"Error updating experiment grid: {e}", "error", "ExperimentView", "ExperimentView")
            if hasattr(self, 'batch_experiment_grid'):
                self.batch_experiment_grid.set_columns(["Status"])
                self.batch_experiment_grid.populate_data([{"Status": f"Error loading experiments: {str(e)}"}], ["Status"])

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
        # self.log_bus.log(f"Batch grid selection changed. Triggered by ID: {exp_id}, Selected: {is_selected}. Total selected: {count}", "info", "ExperimentView")

    def handle_create_batch(self):
        """Create a new batch with the selected experiments."""
        if not self.window().project_manager:
            self.log_bus.log("ProjectManager not available for creating batch.", "error", "ExperimentView")
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
            self.log_bus.log(f"Attempting to create batch '{batch_id}' with {len(selected_experiment_ids, "info", "ExperimentView")} experiments.")
            # Basic selection criteria (can be expanded later if needed)
            selection_criteria = {"manual_selection": True}
            if batch_name:
                 selection_criteria["batch_name"] = batch_name # Store name if provided
            if batch_description:
                 selection_criteria["description"] = batch_description # Store description if provided

            # Call the ProjectManager method
            self.window().project_manager.create_batch(
                batch_id=batch_id,
                batch_name=batch_name, # Pass optional name
                description=batch_description, # Pass optional description
                experiment_ids=list(selected_experiment_ids), # Pass the list of selected IDs
                selection_criteria=selection_criteria
            )

            # --- Success ---
            self.log_bus.log(f"Batch '{batch_id}' created successfully.", "info", "ExperimentView")
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
             self.log_bus.log(f"Failed to create batch '{batch_id}': {ve}", "error", "ExperimentView") # Log concisely
             QMessageBox.critical(self, "Batch Creation Error", f"Failed to create batch:\n{ve}")
             self.batch_notification_label.setText("Batch creation failed.")
        except Exception as e: # Catch unexpected errors
            self.log_bus.log(f"Unexpected error creating batch '{batch_id}': {e}", "error", "ExperimentView", "ExperimentView")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during batch creation:\n{str(e)}")
            self.batch_notification_label.setText("Batch creation failed.")

    def closeEvent(self, event):
        """Clean up when the view is closed."""
        # No special cleanup needed for clean architecture
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
                    self.log_bus.log(f"Error updating plugin fields: {str(e, "ExperimentView")}", "warning")
        
    def _discover_plugins(self):
        """
        Discovers and updates the available data handler and analysis plugins
        based on the selected experiment type.
        Finds handlers based on 'load_tracking_data' capability.
        Finds analysis plugins by listing those with capabilities beyond loading data
        and matching the selected experiment type.
        """
        # self.log_bus.log("Discovering plugins...", "info", "ExperimentView") # Commented out
        # Ensure plugin_manager is available
        if not self.plugin_manager:
            self.log_bus.log("Plugin manager not available for discovery.", "warning", "ExperimentView")
            # Plugin system now integrated - clear lists if no plugins
            try:
                if hasattr(self, 'importer_plugin_list') and self.importer_plugin_list:
                    self.importer_plugin_list.clear()
            except RuntimeError:
                pass
            try:
                if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                    self.analysis_plugin_list.clear()
            except RuntimeError:
                pass
            try:
                if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                    self.exporter_plugin_list.clear()
            except RuntimeError:
                pass
            self.clear_plugin_fields()
            return

        # Clear previous entries and parameter fields
        try:
            if hasattr(self, 'importer_plugin_list') and self.importer_plugin_list:
                self.importer_plugin_list.clear()
        except RuntimeError:
            pass
        try:
            if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                self.analysis_plugin_list.clear()
        except RuntimeError:
            pass
        try:
            if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                self.exporter_plugin_list.clear()
        except RuntimeError:
            pass
        self.clear_plugin_fields()

        # Get the selected experiment type
        selected_type = self.experiment_type_combo.currentData()
        if not selected_type:
            # self.log_bus.log("No experiment type selected, skipping plugin discovery.", "info", "ExperimentView") # Commented out
            return # No type selected, nothing to discover

        # self.log_bus.log(f"Discovering plugins for experiment type: {selected_type}", "info", "ExperimentView") # Commented out

        # Update subtype list based on selected type
        # Plugin system now integrated
        # For now, disable subtypes
        self.experiment_subtype_combo.clear()
        self.experiment_subtype_combo.setEnabled(False)
        self.experiment_subtype_combo.addItem("(none)", None)

        # Fetch plugin groups from core (PluginManager owns selection logic)
        importer_plugins = self.plugin_service.get_importer_plugins()
        analysis_plugins = self.plugin_service.get_analysis_plugins_for_type(selected_type)
        exporter_plugins = self.plugin_service.get_exporter_plugins() if hasattr(self, 'exporter_plugin_list') else []

        # Populate Data Handler/Importer List (Plugin system now integrated)
        try:
            if hasattr(self, 'importer_plugin_list') and self.importer_plugin_list:
                for plugin in importer_plugins:
                    item = QListWidgetItem(plugin.plugin_self_metadata().name)
                    item.setData(Qt.ItemDataRole.UserRole, plugin) # Store the actual plugin object
                    self.importer_plugin_list.addItem(item)
        except RuntimeError:
            pass

        # Populate Analysis Plugin List
        try:
            if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                for plugin in analysis_plugins:
                    item = QListWidgetItem(plugin.plugin_self_metadata().name)
                    item.setData(Qt.ItemDataRole.UserRole, plugin) # Store the actual plugin object
                    self.analysis_plugin_list.addItem(item)
        except RuntimeError:
            pass

        # Populate Exporter Plugin List (if present)
        try:
            if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                for plugin in exporter_plugins:
                    item = QListWidgetItem(plugin.plugin_self_metadata().name)
                    item.setData(Qt.ItemDataRole.UserRole, plugin)
                    self.exporter_plugin_list.addItem(item)
        except RuntimeError:
            pass

        # Update button state based on whether plugins are now available etc.
        self._update_add_button_state()

    def _get_selected_plugins(self) -> List['BasePlugin']: # Forward reference if BasePlugin not imported yet
        """Helper to get the plugin objects currently selected in the UI lists."""
        selected_plugins = []
        # Importers/Data Handlers (respect multi-selection)
        try:
            if hasattr(self, 'data_handler_plugin_list') and self.data_handler_plugin_list:
                for i in range(self.data_handler_plugin_list.count()):
                    item = self.data_handler_plugin_list.item(i)
                    if item.isSelected():
                        plugin_data = item.data(Qt.ItemDataRole.UserRole)
                        if isinstance(plugin_data, dict) and 'plugin' in plugin_data:
                            plugin = plugin_data['plugin']
                            if plugin and plugin not in selected_plugins:
                                selected_plugins.append(plugin)
        except RuntimeError:
            pass

        # Analysis Plugins (multi-selection)
        try:
            if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                for i in range(self.analysis_plugin_list.count()):
                     item = self.analysis_plugin_list.item(i)
                     if item.isSelected():
                         plugin_data = item.data(Qt.ItemDataRole.UserRole)
                         if isinstance(plugin_data, dict) and 'plugin' in plugin_data:
                             plugin = plugin_data['plugin']
                             # Avoid adding the same plugin twice if it's both a handler and analyzer
                             if plugin and plugin not in selected_plugins:
                                 selected_plugins.append(plugin)
        except RuntimeError:
            pass

        # Exporter Plugins (multi-selection)
        try:
            if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                for i in range(self.exporter_plugin_list.count()):
                    item = self.exporter_plugin_list.item(i)
                    if item.isSelected():
                        plugin_data = item.data(Qt.ItemDataRole.UserRole)
                        if isinstance(plugin_data, dict) and 'plugin' in plugin_data:
                            plugin = plugin_data['plugin']
                            if plugin and plugin not in selected_plugins:
                                selected_plugins.append(plugin)
        except RuntimeError:
            pass

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

        # 2. Determine plugin selection status
        selected_plugins = self._get_selected_plugins()
        plugins_selected = bool(selected_plugins)

        # Determine selected processing stage
        processing_stage_selected = self.processing_stage_combo.currentText()

        # 3. Check required plugin parameters (only if plugins selected)
        required_params_filled = True
        if plugins_selected and hasattr(self, 'plugin_field_widgets'):
            for plugin in selected_plugins:
                plugin_name = plugin.plugin_self_metadata().name

                # Allow DeepLabCutHandler tracking file to be blank until stage >= tracked
                if plugin_name == "DeepLabCutHandler" and processing_stage_selected in ("planned", "recorded"):
                    # Skip checking its required fields in early stages
                    continue

                required_fields = plugin.required_fields()
                field_widgets = self.plugin_field_widgets.get(plugin_name, {})

                for req_field in required_fields:
                    widget = field_widgets.get(req_field)
                    if not widget:
                        self.log_bus.log(f"Required field '{req_field}' for plugin '{plugin_name}' has no corresponding widget.", "warning", "ExperimentView")
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
                    elif isinstance(widget, QTextEdit):
                        value = widget.toPlainText().strip()
                        if not value:
                            is_empty = True
                    # Add checks for other widget types if necessary

                    if is_empty:
                        required_params_filled = False
                        # self.log_bus.log(f"Required field '{req_field}' for plugin '{plugin_name}' is empty.", "info", "ExperimentView") # Commented out
                        break # Stop checking this plugin's fields
                if not required_params_filled:
                    break # Stop checking other plugins

        # 4. Final decision: button enabled when core valid AND (no plugins OR all plugin params valid)
        enable_create = core_details_valid and required_params_filled
        self.add_experiment_button.setEnabled(enable_create)

        # Tooltip for disabled state
        if not enable_create:
            tooltip_parts = []
            if not core_details_valid:
                tooltip_parts.append("Core details missing.")
            if plugins_selected and not required_params_filled:
                tooltip_parts.append("Required plugin parameters missing.")
            self.add_experiment_button.setToolTip("Cannot create experiment: " + " ".join(tooltip_parts))
        else:
            self.add_experiment_button.setToolTip("")

    def clear_plugin_fields(self):
        """Clears the dynamically generated plugin parameter fields."""
        # Remove widgets from the layout manager first
        if hasattr(self, 'plugin_fields_layout'): # Check if layout exists
            while self.plugin_fields_layout.count():
                # Take the row item (which contains label and widget/layout)
                row_item = self.plugin_fields_layout.takeAt(0)
                if row_item:
                    # Remove label if it exists
                    label_item = self.plugin_fields_layout.itemAt(0, QFormLayout.ItemRole.LabelRole)
                    if label_item and label_item.widget():
                        label_item.widget().deleteLater()
                    # Remove field widget/layout if it exists
                    field_item = self.plugin_fields_layout.itemAt(0, QFormLayout.ItemRole.FieldRole)
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
            # self.log_bus.log("No plugins selected, skipping field generation.", "info", "ExperimentView") # Commented out
            return # No plugins selected, nothing to show

        # self.log_bus.log(f"Updating fields for selected plugins: {[p.plugin_self_metadata(, "info", "ExperimentView").name for p in selected_plugins]}") # Commented out

        # Store widgets keyed by plugin name and field name for later retrieval
        self.plugin_field_widgets = {}
        any_fields_added = False

        # The self.plugin_fields_layout (a QFormLayout) was created in setup_add_experiment_page.
        # clear_plugin_fields() above has removed any previous rows, so we can reuse it here.

        for plugin in selected_plugins:
             plugin_name = plugin.plugin_self_metadata().name
             self.plugin_field_widgets[plugin_name] = {}

             required = plugin.required_fields()
             optional = plugin.optional_fields()
             all_fields = sorted(required + optional) # Sort for consistent order

             if not all_fields:
                 self.log_bus.log(f"Plugin '{plugin_name}' has no configurable parameters.", "info", "ExperimentView")
                 continue # Plugin has no configurable parameters

             any_fields_added = True # Mark that we are adding fields

             # Wrap this plugin's parameters in a collapsible QGroupBox
             plugin_box = QGroupBox(plugin_name)
             plugin_box.setCheckable(True)
             plugin_box.setChecked(True)
             plugin_box.setProperty("class", "mus1-plugin-groupbox")
             box_layout = QFormLayout(plugin_box)
             box_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
             box_layout.setVerticalSpacing(self.CONTROL_SPACING)

             field_types = plugin.get_field_types()
             field_descriptions = plugin.get_field_descriptions()

             for field_name in all_fields:
                 is_required = field_name in required
                 field_type = field_types.get(field_name, 'string')
                 description = field_descriptions.get(field_name, '')

                 widget_or_layout = self._create_field_widget(plugin, field_name, field_type)
                 if widget_or_layout:
                     label_text = f"{field_name}{' *' if is_required else ''}:"
                     form_label = self.create_form_label(label_text)
                     if description:
                         form_label.setToolTip(description)
                     form_label.setProperty("fieldRequired", is_required)

                     if isinstance(widget_or_layout, QLayout):
                         box_layout.addRow(form_label, widget_or_layout)
                         # find line edit inside layout for storage
                         input_widget = None
                         for i in range(widget_or_layout.count()):
                             w = widget_or_layout.itemAt(i).widget()
                             if isinstance(w, (QLineEdit, QTextEdit)):
                                 input_widget = w
                                 break
                         if input_widget:
                             self.plugin_field_widgets[plugin_name][field_name] = input_widget
                     else:
                         box_layout.addRow(form_label, widget_or_layout)
                         self.plugin_field_widgets[plugin_name][field_name] = widget_or_layout

             # Add the groupbox as a single row spanning both columns of the main layout
             self.plugin_fields_layout.addRow(plugin_box)

        # Make the parameters group box visible only if any fields were actually added
        self.plugin_params_group.setVisible(any_fields_added)
        # Adjust size policy or update layout if needed after adding widgets
        self.plugin_params_group.adjustSize()
        page_widget = self.plugin_params_group.parentWidget()
        if page_widget: page_widget.layout().activate() # Force layout update

    def _create_field_widget(self, plugin, field_name, field_type='string'):
        """Creates the appropriate input widget based on the field type."""
        # self.log_bus.log(f"Creating widget for field '{field_name}' with type '{field_type}'", "info", "ExperimentView") # Commented out
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
        elif field_type == 'text':
            # Multiline text
            widget = QTextEdit()
            widget.setProperty("class", "mus1-text-edit")
            widget.setPlaceholderText("Enter text…")
        elif field_type == 'dict':
            # Simple JSON dictionary input
            widget = QTextEdit()
            widget.setProperty("class", "mus1-text-edit")
            widget.setPlaceholderText("Enter JSON dictionary, e.g. {\"key\": \"value\"}")
            widget.setAcceptRichText(False)
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
                 self.log_bus.log(f"Unknown field type '{field_type}' for '{field_name}'. Defaulting to QLineEdit.", "warning", "ExperimentView")

        return widget

    def _browse_for_path(self, line_edit_widget: QLineEdit, field_type: str):
        """Opens a file or directory dialog and sets the path in the line edit."""
        current_path = line_edit_widget.text()
        start_dir = str(Path(current_path).parent if current_path and Path(current_path).exists() else Path.home())

        path = ""
        if field_type.startswith('file'):
            # Parse optional extensions after ':' in field_type, e.g., 'file:csv|h5|hdf5'
            filters = "All Files (*)"
            if ':' in field_type:
                _, ext_str = field_type.split(':', 1)
                exts = [e.strip().lstrip('.').lower() for e in ext_str.split('|') if e.strip()]
                if exts:
                    patterns = ' '.join([f"*.{e}" for e in exts])
                    filters = f"Supported Files ({patterns});;All Files (*)"
            path, _ = QFileDialog.getOpenFileName(self, "Select File", start_dir, filters)
        elif field_type == 'directory':
            path = QFileDialog.getExistingDirectory(self, "Select Directory", start_dir)

        if path:
            line_edit_widget.setText(path)
        
    def _auto_stage_from_video(self):
        """Automatically switch stage to 'recorded' when a video file is selected."""
        path_text = self.video_path_edit.text().strip()
        if path_text:
            idx_rec = self.processing_stage_combo.findText("recorded")
            idx_planned = self.processing_stage_combo.findText("planned")
            if idx_rec != -1 and self.processing_stage_combo.currentIndex() == idx_planned:
                self.processing_stage_combo.setCurrentIndex(idx_rec)

    def handle_link_video(self):
        """Prompt the user to pick a video file and link it to the currently
        selected experiment via ProjectManager.link_video_to_experiment."""

        # Validate ProjectManager availability
        if not self.window().project_manager:
            self.show_error_message("Internal Error", "Project Manager not initialized.")
            return

        # Validate selection
        current_item = self.experimentListWidget.currentItem()
        if current_item is None:
            QMessageBox.warning(self, "No Experiment Selected", "Please select an experiment from the list first.")
            return

        # Prefer the ID stored in UserRole for reliability
        exp_id = current_item.data(Qt.ItemDataRole.UserRole)
        if not exp_id:
            # Fallback: parse from text if for some reason data is missing
            exp_text = current_item.text()
            exp_id = exp_text.split(" ")[0]

        # Ask the user to choose a video file
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video File",
            str(Path.home()),
            "Video Files (*.mp4 *.avi *.mov *.mkv *.mpg *.mpeg *.m4v);;All Files (*)",
        )

        if not file_path:
            return  # Dialog cancelled

        try:
            # Link video to experiment using project manager
            video_path = Path(file_path)
            success = self.window().project_manager.link_video_to_experiment(
                experiment_id=exp_id,
                video_path=video_path,
                notes=f"Manually linked via experiment view"
            )

            if success:
                QMessageBox.information(self, "Success", f"Video linked to experiment '{exp_id}'.")
            else:
                QMessageBox.warning(self, "Warning", f"Video was added to project but could not be linked to experiment '{exp_id}'.")
        except Exception as e:
            self.log_bus.log(f"Failed to link video to experiment {exp_id}: {e}", "error", "ExperimentView", "ExperimentView")
            QMessageBox.critical(self, "Error", f"Failed to link video:\n{e}")

        # Refresh info
        self._update_recording_info(exp_id)

    # ------------------------------------------------------------------
    # Recording info UI helpers
    # ------------------------------------------------------------------

    def _on_experiment_selected(self, current, previous):
        """Slot triggered when user selects a different experiment in list."""
        if current is None:
            # Clear info
            self._clear_recording_info()
            return
        exp_id = current.data(Qt.ItemDataRole.UserRole) or current.text().split(" ")[0]
        self._update_recording_info(exp_id)

    def _clear_recording_info(self):
        self.rec_path_label.setText("Path: —")
        self.rec_status_label.setText("Status: —")
        self.rec_size_label.setText("Size: —")
        self.rec_hash_label.setText("Sample-hash: —")
        # Clear missing property styling
        self.rec_path_label.setProperty("missing", False)
        self.rec_path_label.style().unpolish(self.rec_path_label)
        self.rec_path_label.style().polish(self.rec_path_label)

    def _find_associated_videos(self, exp_id: str) -> List[VideoFile]:
        """Find videos that are associated with the given experiment ID.

        Uses the proper experiment-video association table.
        """
        try:
            # Use project manager to get properly associated videos
            return self.window().project_manager.get_videos_for_experiment(exp_id)
        except Exception as e:
            self.log_bus.log(f"Error finding associated videos for experiment {exp_id}: {e}", "info", "ExperimentView")
            return []

    def _update_recording_info(self, exp_id: str):
        """Populate the recording info panel for the given experiment ID."""
        self._clear_recording_info()

        if not self.gui_services:
            self.rec_status_label.setText("Status: GUI services not available")
            return

        try:
            # Look for videos that might be associated with this experiment
            associated_videos = self._find_associated_videos(exp_id)

            if associated_videos:
                # Show info for the first associated video (most common case)
                video = associated_videos[0]

                # Path
                self.rec_path_label.setText(f"Path: {video.path}")

                # Status - based on whether video exists and is accessible
                if video.path.exists():
                    self.rec_status_label.setText("Status: Video file found")
                    self.rec_path_label.setProperty("missing", False)
                else:
                    self.rec_status_label.setText("Status: Video file missing")
                    self.rec_path_label.setProperty("missing", True)
                    self.rec_path_label.style().unpolish(self.rec_path_label)
                    self.rec_path_label.style().polish(self.rec_path_label)

                # Size
                if video.size_bytes > 0:
                    size_mb = video.size_bytes / (1024 * 1024)
                    self.rec_size_label.setText(f"Size: {size_mb:.1f} MB")
                else:
                    self.rec_size_label.setText("Size: Unknown")

                # Hash
                if video.hash:
                    # Show first 8 characters of hash for readability
                    short_hash = video.hash[:8] if len(video.hash) > 8 else video.hash
                    self.rec_hash_label.setText(f"Sample-hash: {short_hash}...")
                else:
                    self.rec_hash_label.setText("Sample-hash: Not computed")

                # If multiple videos match, indicate this
                if len(associated_videos) > 1:
                    self.rec_status_label.setText(f"{self.rec_status_label.text()} ({len(associated_videos)} matching files)")

            else:
                # No associated videos found
                self.rec_path_label.setText("Path: No video associated")
                self.rec_status_label.setText("Status: No video found")
                self.rec_size_label.setText("Size: —")
                self.rec_hash_label.setText("Sample-hash: —")

        except Exception as e:
            self.log_bus.log(f"Error updating recording info for experiment {exp_id}: {e}", "error", "ExperimentView", "ExperimentView")
            self.rec_status_label.setText(f"Status: Error loading info - {str(e)}")

    def _suggest_experiment_id(self, video_path_text):
        """
        Automatically suggests an experiment ID based on the video filename.
        If the experiment ID input is empty, it will be filled with the video filename stem.
        """
        if not self.experiment_id_input.text().strip() and video_path_text:
            suggested_id = Path(video_path_text).stem
            self.experiment_id_input.setText(suggested_id)
            self.log_bus.log(f"Suggested experiment ID: {suggested_id} from video path: {video_path_text}", "info", "ExperimentView") 

    def _on_video_path_changed(self, path_text: str):
        """
        Computes and displays the sample hash of the currently linked video
        when the video path changes.
        """
        if not path_text:
            self.sample_hash_value.setText("—")
            return

        video_path = Path(path_text)
        if not video_path.exists():
            self.sample_hash_value.setText("—")
            return

        try:
            # Compute and display sample hash using core utility
            sample_hash = compute_sample_hash(video_path)
            short_hash = sample_hash[:8] if len(sample_hash) > 8 else sample_hash
            self.sample_hash_value.setText(f"{short_hash}...")

            # Auto-populate the Date Recorded field with the file's mtime
            mtime = int(video_path.stat().st_mtime)
            self.date_recorded_edit.setDateTime(QDateTime.fromSecsSinceEpoch(mtime))
            self.log_bus.log(f"Auto-set recording date from video mtime: {self.date_recorded_edit.dateTime().toString('yyyy-MM-dd')}", "info", "ExperimentView")
        except Exception as e:
            self.log_bus.log(f"Error computing sample hash for {video_path}: {e}", "error", "ExperimentView")
            self.sample_hash_value.setText("—") 

    # ------------- Multiple experiment helpers -------------
    def _multi_add_row(self):
        """Insert a new blank row with suitable widgets."""
        row = self.multi_exp_table.rowCount()
        self.multi_exp_table.insertRow(row)

        # Experiment ID
        self.multi_exp_table.setCellWidget(row, 0, QLineEdit())

        # Subject combo
        subj_combo = QComboBox()
        subj_combo.addItem("Subject selection not yet implemented", None)
        self.multi_exp_table.setCellWidget(row, 1, subj_combo)

        # Type combo
        type_combo = QComboBox()
        type_combo.addItem("OpenField", "OpenField")
        type_combo.addItem("NOR", "NOR")
        type_combo.addItem("Other", "Other")
        self.multi_exp_table.setCellWidget(row, 2, type_combo)

        # Date widget
        date_edit = QDateTimeEdit(QDateTime.currentDateTime())
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        self.multi_exp_table.setCellWidget(row, 3, date_edit)

        # Stage combo
        stage_combo = QComboBox()
        stage_combo.addItems(self.PROCESSING_STAGES)
        self.multi_exp_table.setCellWidget(row, 4, stage_combo)

        # Video path line edit
        self.multi_exp_table.setCellWidget(row, 5, QLineEdit())

    def _multi_remove_selected_rows(self):
        rows = sorted({idx.row() for idx in self.multi_exp_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.multi_exp_table.removeRow(r)

    def _multi_save_experiments(self):
        """Iterate rows and save experiments via ProjectManager."""
        # Multi-save experiments not yet implemented in clean architecture
        QMessageBox.information(self, "Not Implemented", "Multi-save experiments not yet implemented in clean architecture.")
        return

    def on_experiment_selection_changed(self, exp_id: str, is_selected: bool):
        """Handle experiment selection changes from the MetadataGridDisplay."""
        # Batch experiment selection not yet implemented in clean architecture
        if hasattr(self, 'batch_experiment_grid'):
            # Update the create button state based on the grid's current selection count
            selected_ids = self.batch_experiment_grid.get_selected_items()
            count = len(selected_ids)
            if hasattr(self, 'create_batch_button'):
                self.create_batch_button.setEnabled(count > 0)
            if hasattr(self, 'batch_notification_label'):
                self.batch_notification_label.setText(f"{count} experiment(s) selected")
        return

    def handle_create_batch(self):
        """Create a new batch with the selected experiments."""
        if not self.window().project_manager:
            self.log_bus.log("ProjectManager not available for creating batch.", "error", "ExperimentView")
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
            self.log_bus.log(f"Attempting to create batch '{batch_id}' with {len(selected_experiment_ids, "info", "ExperimentView")} experiments.")
            # Basic selection criteria (can be expanded later if needed)
            selection_criteria = {"manual_selection": True}
            if batch_name:
                 selection_criteria["batch_name"] = batch_name # Store name if provided
            if batch_description:
                 selection_criteria["description"] = batch_description # Store description if provided

            # Call the ProjectManager method
            self.window().project_manager.create_batch(
                batch_id=batch_id,
                batch_name=batch_name, # Pass optional name
                description=batch_description, # Pass optional description
                experiment_ids=list(selected_experiment_ids), # Pass the list of selected IDs
                selection_criteria=selection_criteria
            )

            # --- Success ---
            self.log_bus.log(f"Batch '{batch_id}' created successfully.", "info", "ExperimentView")
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
             self.log_bus.log(f"Failed to create batch '{batch_id}': {ve}", "error", "ExperimentView") # Log concisely
             QMessageBox.critical(self, "Batch Creation Error", f"Failed to create batch:\n{ve}")
             self.batch_notification_label.setText("Batch creation failed.")
        except Exception as e: # Catch unexpected errors
            self.log_bus.log(f"Unexpected error creating batch '{batch_id}': {e}", "error", "ExperimentView", "ExperimentView")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during batch creation:\n{str(e)}")
            self.batch_notification_label.setText("Batch creation failed.")

    def closeEvent(self, event):
        """Handle cleanup when the experiment view is closed."""
        # No special cleanup needed for clean architecture
        event.accept()

    def update_theme(self, theme):
        """Update the theme for this view and its components."""
        # Theme propagation is handled by MainWindow
        pass

    def _discover_plugins(self):
        """
        Discovers and updates the available data handler and analysis plugins
        based on the selected experiment type.
        Finds handlers based on 'load_tracking_data' capability.
        Finds analysis plugins by listing those with capabilities beyond loading data
        and matching the selected experiment type.
        """
        # Clear previous entries and parameter fields
        try:
            if hasattr(self, 'importer_plugin_list') and self.importer_plugin_list:
                self.importer_plugin_list.clear()
        except RuntimeError:
            pass
        try:
            if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                self.analysis_plugin_list.clear()
        except RuntimeError:
            pass
        try:
            if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                self.exporter_plugin_list.clear()
        except RuntimeError:
            pass
        self.clear_plugin_fields()

        # Get the selected experiment type
        selected_type = self.experiment_type_combo.currentData()
        if not selected_type:
            return # No type selected, nothing to discover

        # Discover plugins using plugin service
        if not self.plugin_service:
            self.log_bus.log("Plugin service not available for discovery.", "warning", "ExperimentView")
            return

        # Update subtype list based on selected type
        # Plugin system now integrated
        # For now, disable subtypes
        self.experiment_subtype_combo.clear()
        self.experiment_subtype_combo.setEnabled(False)
        self.experiment_subtype_combo.addItem("(none)", None)

        # Fetch plugin groups from core (PluginManager owns selection logic)
        importer_plugins = self.plugin_service.get_importer_plugins()
        analysis_plugins = self.plugin_service.get_analysis_plugins_for_type(selected_type)
        exporter_plugins = self.plugin_service.get_exporter_plugins() if hasattr(self, 'exporter_plugin_list') else []

        # Populate Importer List
        try:
            if hasattr(self, 'importer_plugin_list') and self.importer_plugin_list:
                for plugin_data in importer_plugins:
                    item = QListWidgetItem(plugin_data['name'])
                    item.setData(Qt.ItemDataRole.UserRole, plugin_data) # Store the plugin data dict
                    self.importer_plugin_list.addItem(item)
        except RuntimeError:
            pass

        # Populate Analysis Plugin List
        try:
            if hasattr(self, 'analysis_plugin_list') and self.analysis_plugin_list:
                for plugin_data in analysis_plugins:
                    item = QListWidgetItem(plugin_data['name'])
                    item.setData(Qt.ItemDataRole.UserRole, plugin_data) # Store the plugin data dict
                    self.analysis_plugin_list.addItem(item)
        except RuntimeError:
            pass

        # Populate Exporter Plugin List (if present)
        try:
            if hasattr(self, 'exporter_plugin_list') and self.exporter_plugin_list:
                for plugin_data in exporter_plugins:
                    item = QListWidgetItem(plugin_data['name'])
                    item.setData(Qt.ItemDataRole.UserRole, plugin_data) # Store the plugin data dict
                    self.exporter_plugin_list.addItem(item)
        except RuntimeError:
            pass

        # Update button state based on whether plugins are now available etc.
        self._update_add_button_state()

    def show_error_message(self, title: str, message: str):
        """Show an error message dialog."""
        QMessageBox.critical(self, title, message)

