from .qt import (
    Qt,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDateTimeEdit,
    QCheckBox,
    QTextEdit,
    QListWidget,
    QPushButton,
    QLabel,
    QDateTime,
    QTimer,
    QAbstractItemView,
)

from ..core.metadata import Sex
from .navigation_pane import NavigationPane  
from .base_view import BaseView
from ..core.logging_bus import LoggingEventBus
from .metadata_display import MetadataTreeView  # Import for overview display
from pathlib import Path
from .gui_services import GUISubjectService
# TODO: Update to use new clean architecture models
# from ..core import ObjectMetadata, BodyPartMetadata  # Import needed for body parts and objects pages

class SubjectView(BaseView):
    def __init__(self, parent=None):
        # Initialize with base view and specific name
        super().__init__(parent, view_name="subject")
        
        # Log initialization
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("SubjectView initialized", "info", "SubjectView")

        # Initialize GUI services
        self.gui_services = None  # Will be set when project is loaded
        self.subject_service = None  # Will be set when project is loaded

        # Setup navigation for this view with six pages
        self.setup_navigation(["Subject Overview", "Bodyparts", "Genotypes", "Treatments", "Objects", "Subjects"])
        
        # Create all pages in the new order:
        self.setup_view_subjects_page()       # 1. Subject Overview
        self.setup_body_parts_page()          # 2. Bodyparts
        self.setup_genotypes_page()           # 3. Genotypes
        self.setup_treatments_page()          # 4. Treatments
        self.setup_objects_page()             # 5. Objects
        self.setup_add_subject_page()         # 6. Subjects
        
        # Do not change pages or refresh here; wait until services injected

        # TODO: Update state subscription to use new architecture
        # --- New: subscribe to state changes so overview auto-updates ---
        # Store reference for cleanup and ensure immediate population
        # self._state_manager = self.state_manager
        # self._state_subscription = self._handle_state_change
        # self._state_manager.subscribe(self._state_subscription)
        # Populate UI immediately (in case a project is already loaded)
        # self._handle_state_change()

    # --- Lifecycle hooks ---
    def on_services_ready(self, services):
        super().on_services_ready(services)
        # services is now the GUIServiceFactory, create the services we need
        self.gui_services = services.create_subject_service()
        self.subject_service = services.create_subject_service()
        self.experiment_service = services.create_experiment_service()
        try:
            self.refresh_subject_list_display()
            self.refresh_overview()
            self.change_page(0)
        except Exception:
            pass

    def on_activated(self):
        # Lightweight refresh when tab becomes active
        self.refresh_subject_list_display()
        if self.pages.currentIndex() == 0:
            self.refresh_overview()

    def setup_add_subject_page(self):
        """Setup the Subjects page (previously named Add Subject)."""
        # Create the page widget
        self.page_add_subject = QWidget()
        add_layout = QVBoxLayout(self.page_add_subject)
        add_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        add_layout.setSpacing(self.SECTION_SPACING)

        # Create input form for adding a subject
        self.subject_group = QGroupBox("Add Subject")
        self.subject_group.setProperty("class", "mus1-input-group")
        
        # Switch to a horizontal layout with two columns for inputs
        subject_layout = QHBoxLayout(self.subject_group)
        
        # Left column
        left_form_layout = QFormLayout()
        self.subject_id_edit = QLineEdit()
        self.subject_id_edit.setProperty("class", "mus1-text-input")
        self.sex_combo = QComboBox()
        self.sex_combo.setProperty("class", "mus1-combo-box")
        self.sex_combo.addItems([Sex.MALE.value, Sex.FEMALE.value, Sex.UNKNOWN.value])
        # Replace free-text genotype with combo box populated from active metadata
        self.genotype_combo = QComboBox()
        self.genotype_combo.setProperty("class", "mus1-combo-box")
        # Similarly, add a combo box for Treatment
        self.treatment_combo = QComboBox()
        self.treatment_combo.setProperty("class", "mus1-combo-box")
        left_form_layout.addRow("Subject ID:", self.subject_id_edit)
        left_form_layout.addRow("Sex:", self.sex_combo)
        left_form_layout.addRow("Genotype:", self.genotype_combo)
        left_form_layout.addRow("Treatment:", self.treatment_combo)
        
        # Right column
        right_form_layout = QFormLayout()
        self.birthdate_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.birthdate_edit.setCalendarPopup(True)
        self.birthdate_edit.setDisplayFormat("yyyy-MM-dd")
        self.training_set_check = QCheckBox()
        
        # Add death date field
        self.deathdate_edit = QDateTimeEdit()
        self.deathdate_edit.setCalendarPopup(True)
        self.deathdate_edit.setDisplayFormat("yyyy-MM-dd")
        self.deathdate_edit.setEnabled(False)  # Disabled by default
        self.death_check = QCheckBox("Record Death")
        self.death_check.toggled.connect(lambda checked: self.deathdate_edit.setEnabled(checked))
        
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setProperty("class", "mus1-text-input")
        right_form_layout.addRow("Birth Date:", self.birthdate_edit)
        right_form_layout.addRow("Death:", self.death_check)
        right_form_layout.addRow("Death Date:", self.deathdate_edit)
        right_form_layout.addRow("Training Set:", self.training_set_check)
        right_form_layout.addRow("Notes:", self.notes_edit)
        
        subject_layout.addLayout(left_form_layout)
        subject_layout.addLayout(right_form_layout)
        
        # Add the subject input form to the page layout
        add_layout.addWidget(self.subject_group)
        
        # Add the add subject button
        self.add_subject_button = QPushButton("Add Subject")
        self.add_subject_button.setProperty("class", "mus1-primary-button")
        self.add_subject_button.clicked.connect(self.handle_add_subject)
        add_layout.addWidget(self.add_subject_button)
        
        # Add notification label for status messages
        self.subject_notification_label = QLabel("")
        self.subject_notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        add_layout.addWidget(self.subject_notification_label)
        
        # Create a list widget for displaying all subjects
        subjects_group, subjects_layout = self.create_form_section("All Subjects", add_layout)
        self.subjects_list = QListWidget()
        self.subjects_list.setProperty("class", "mus1-list-widget")
        self.subjects_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        subjects_layout.addWidget(self.subjects_list)
        
        # Add buttons for subject operations
        buttons_row = self.create_button_row(subjects_layout)
        edit_button = QPushButton("Edit Selected")
        edit_button.setProperty("class", "mus1-secondary-button")
        edit_button.clicked.connect(self.handle_edit_subject)
        remove_button = QPushButton("Remove Selected")
        remove_button.setProperty("class", "mus1-secondary-button")
        remove_button.clicked.connect(self.handle_remove_selected_subject)
        view_notes_button = QPushButton("View Notes")
        view_notes_button.setProperty("class", "mus1-secondary-button")
        view_notes_button.clicked.connect(self.handle_view_subject_notes)
        buttons_row.addWidget(edit_button)
        buttons_row.addWidget(remove_button)
        buttons_row.addWidget(view_notes_button)
        
        add_layout.addStretch(1)
        
        # Before adding the page, refresh the genotype and treatment dropdowns from active metadata
        self.refresh_active_metadata_dropdowns()
        self.add_page(self.page_add_subject, "Subjects")
    
    def handle_add_subject(self):
        """Handle the logic for adding a new subject using GUI services."""
        if not self.subject_service:
            self.log_bus.log("Error: GUI services not available", "error", "SubjectView")
            return

        subject_id = self.subject_id_edit.text().strip()
        if not subject_id:
            self.log_bus.log("Error: Subject ID cannot be empty", "error", "SubjectView")
            return

        # Check if subject ID already exists
        existing_subject = self.subject_service.get_subject_by_id(subject_id)
        if existing_subject:
            self.log_bus.log(f"Error: Subject ID '{subject_id}' already exists", "error", "SubjectView")
            return

        # Get sex value from combo
        sex_value = self.sex_combo.currentText().upper()
        try:
            sex_enum = Sex(sex_value) if sex_value != "UNKNOWN" else None
        except ValueError:
            sex_enum = None

        genotype = self.genotype_combo.currentText().strip() or None
        notes = self.notes_edit.toPlainText().strip() if hasattr(self, 'notes_edit') else ""
        birth_date = self.birthdate_edit.dateTime().toPython()

        # Determine designation based on training set checkbox (if available)
        designation = "experimental"  # Default
        if hasattr(self, 'training_set_check') and self.training_set_check.isChecked():
            # For now, training set subjects are still experimental
            # In the future, this could be a separate designation
            designation = "experimental"

        # Add the subject via GUI service
        subject = self.subject_service.add_subject(
            subject_id=subject_id,
            sex=sex_value if sex_enum else "UNKNOWN",
            genotype=genotype,
            birth_date=birth_date,
            notes=notes,
            designation=designation
        )

        if subject:
            # Clear the input fields after successful addition
            self.subject_id_edit.clear()
            self.genotype_combo.clear()
            if hasattr(self, 'notes_edit'):
                self.notes_edit.clear()
            if hasattr(self, 'training_set_check'):
                self.training_set_check.setChecked(False)
            self.birthdate_edit.setDateTime(QDateTime.currentDateTime())

            # Refresh the displayed subject list on the same page
            self.refresh_subject_list_display()
            self.log_bus.log(f"Subject '{subject_id}' added successfully", "success", "SubjectView")
        
        # Log the successful addition and show notification
        self.log_bus.log(f"Subject '{subject_id}' added successfully", "success", "SubjectView")
        self.subject_notification_label.setText("Subject added successfully!")
        QTimer.singleShot(3000, lambda: self.subject_notification_label.setText(""))

    def refresh_subject_list_display(self):
        """Refresh the list of all subjects in the project with full metadata details."""
        if not self.subject_service:
            return

        # Ensure the list widget exists before proceeding
        if not hasattr(self, 'subjects_list'):
            return

        # Update the UI by clearing and repopulating the subjects list regardless of the current page
        self.subjects_list.clear()

        # Get subjects using GUI services
        subjects_display_dto = self.subject_service.get_subjects_for_display()

        # Log the refresh activity
        self.log_bus.log(f"Refreshing subject list: {len(subjects_display_dto)} subjects found", "info", "SubjectView")

        for subj_dto in subjects_display_dto:
            birth_str = subj_dto.birth_date.strftime('%Y-%m-%d %H:%M:%S') if subj_dto.birth_date else 'N/A'

            # Create the basic details string
            details = (f"ID: {subj_dto.id} | Sex: {subj_dto.sex_display} | Genotype: {subj_dto.genotype or 'N/A'} "
                      f"| Age: {subj_dto.age_display}")

            # Add notes snippet if available (though Subject model may not have notes yet)
            # details += f" | Notes: {subj_dto.notes or 'None'}"

            self.subjects_list.addItem(details)

    def refresh_experiment_list_by_subject_display(self):
        """Refresh the list widget displaying experiments by subject."""
        # Implementation pending
        pass


    def _handle_state_change(self):
        """Observer callback that updates all widgets on state changes or initial assignment."""
        # Refresh both the overview tree and the subjects list so they stay in sync.
        self.refresh_overview()
        self.refresh_subject_list_display()

    def closeEvent(self, event):
        """Clean up when the view is closed."""
        # No state manager subscription to clean up in clean architecture
        super().closeEvent(event)

    def update_theme(self, theme):
        """Update the theme for this view and its components.
        Args:
            theme: The theme name ('dark' or 'light') passed from MainWindow
        """
        # Propagate theme changes using the base update_theme method
        super().update_theme(theme)

        # Optionally, perform additional view-specific theme updates
        # For example, refresh the view based on new theme settings
        # Log the theme update if navigation pane is available
        if hasattr(self, 'navigation_pane'):
            self.navigation_pane.add_log_message(f"Updated to {theme} theme", 'info')

    def change_page(self, index):
        """
        Override change_page to refresh data when switching between pages.
        """
        super().change_page(index)
        
        # Update appropriate data based on which page we're viewing
        if index == 0:  # Subject Overview
            # Refresh the overview only
            self.refresh_overview()
        elif index == 1:  # Bodyparts
            # Refresh the body parts page
            self.refresh_body_parts_page()
        elif index == 2:  # Genotypes
            # Refresh the genotypes page
            self.refresh_genotypes_page()
        elif index == 3:  # Treatments
            # Refresh the treatments page
            self.refresh_treatments_page()
        elif index == 4:  # Objects
            # Refresh the objects page
            self.refresh_objects_page()
        elif index == 5:  # Subjects
            # Refresh the subjects list and the active dropdowns
            self.refresh_subject_list_display()
            self.refresh_active_metadata_dropdowns()

    def handle_remove_selected_subject(self):
        """Handle removal of the selected subject from the list."""
        selected_item = self.subjects_list.currentItem()
        if not selected_item:
            return
        text = selected_item.text()
        parts = text.split('|')
        if not parts:
            return
        # Expecting item text format "ID: <subject_id> | ..."
        id_part = parts[0].strip()
        if id_part.startswith("ID:"):
            subject_id = id_part[3:].strip()
        else:
            subject_id = id_part
        if self.subject_service:
            self.subject_service.remove_subject(subject_id)
            self.refresh_subject_list_display()

    def setup_view_subjects_page(self):
        """Setup the Subjects Overview page."""
        self.page_overview = QWidget()
        overview_layout = QVBoxLayout(self.page_overview)
        overview_layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        overview_layout.setSpacing(self.SECTION_SPACING)
        
        # Create a metadata tree view for hierarchical display of subjects and experiments
        tree_group, tree_layout = self.create_form_section("Subjects and Experiments Overview", overview_layout)
        self.metadata_tree = MetadataTreeView(tree_group)
        tree_layout.addWidget(self.metadata_tree)

        # Add toolbar row with refresh button
        toolbar_row = self.create_button_row(tree_layout, add_stretch=False)
        refresh_button = QPushButton("Refresh Overview")
        refresh_button.setProperty("class", "mus1-secondary-button")
        refresh_button.clicked.connect(self.refresh_overview)

        # Edit mode disabled to prevent data corruption
        # Users should use proper workflows for data changes
        edit_info_label = QLabel("Use proper workflows to edit data")
        edit_info_label.setStyleSheet("color: #666; font-style: italic;")

        toolbar_row.addWidget(refresh_button)
        toolbar_row.addStretch(1)
        toolbar_row.addWidget(edit_info_label)
        
        # Add the overview page with title "Subjects Overview" to the stacked widget
        self.add_page(self.page_overview, "Subjects Overview")

    def refresh_overview(self):
        """Refresh the Subjects Overview display using metadata_tree."""
        if not self.subject_service or not self.gui_services:
            # Clear the tree view if services are not available
            if hasattr(self, 'metadata_tree'):
                self.metadata_tree.clear()
            return

        # Get subjects and experiments using GUI services
        subjects_dto = self.subject_service.get_subjects_for_display()
        experiments_dto = self.experiment_service.get_experiments_for_display()

        # Convert DTOs to proper dictionaries expected by metadata_tree
        subjects_dict = {}
        for subj_dto in subjects_dto:
            # Create a simple dict representation for the tree
            subjects_dict[subj_dto.id] = {
                'id': subj_dto.id,
                'sex': subj_dto.sex,
                'genotype': subj_dto.genotype or "N/A"
            }

        experiments_dict = {}
        for exp_dto in experiments_dto:
            # Create a simple dict representation for the tree
            experiments_dict[exp_dto.id] = {
                'id': exp_dto.id,
                'subject_id': exp_dto.subject_id,
                'type': exp_dto.experiment_type,
                'date_recorded': exp_dto.date_recorded,
                'processing_stage': exp_dto.processing_stage
            }

        # Populate the metadata tree view with subjects and their experiments
        # Pass the project manager so the tree can get video/recording counts
        project_manager = getattr(self.window(), 'project_manager', None)
        self.metadata_tree.populate_subjects_with_experiments(subjects_dict, experiments_dict, project_manager)

    def handle_edit_subject(self):
        """Handle editing of a selected subject."""
        selected_item = self.subjects_list.currentItem()
        if not selected_item:
            self.navigation_pane.add_log_message("No subject selected for editing.", "warning")
            return
        
        # Extract subject ID from the selected item text
        item_text = selected_item.text()
        parts = item_text.split('|')
        if not parts:
            return
        
        id_part = parts[0].strip()
        if id_part.startswith("ID:"):
            subject_id = id_part[3:].strip()
        else:
            subject_id = id_part
        
        # Get the subject using GUI services
        subject_dto = self.subject_service.get_subject_by_id(subject_id)
        if not subject_dto:
            self.navigation_pane.add_log_message(f"Subject {subject_id} not found.", "error")
            return
        
        # Populate the form with subject data for editing
        self.subject_id_edit.setText(subject_id)
        self.sex_combo.setCurrentText(subject_dto.sex_display)
        self.genotype_combo.setCurrentText(subject_dto.genotype or "")
        # self.notes_edit.setText(subject_dto.notes or "")  # Notes not in DTO yet

        if subject_dto.birth_date:
            self.birthdate_edit.setDateTime(QDateTime(subject_dto.birth_date))
        else:
            self.birthdate_edit.setDateTime(QDateTime.currentDateTime())

        # self.training_set_check.setChecked(subject_dto.in_training_set)  # Not in DTO yet

        # Enable death date if it exists (not in DTO yet)
        # has_death_date = subject_dto.death_date is not None
        # self.death_check.setChecked(has_death_date)
        # if has_death_date:
        #     self.deathdate_edit.setDateTime(QDateTime(subject_dto.death_date))
        # else:
        #     self.deathdate_edit.setDateTime(QDateTime.currentDateTime())
        
        # Change add button to update button
        self.add_subject_button.setText("Update Subject")
        self.add_subject_button.clicked.disconnect()
        self.add_subject_button.clicked.connect(lambda: self.handle_update_subject(subject_id))
        
        # Focus on first field for editing
        self.genotype_combo.setFocus()

    def handle_update_subject(self, original_id):
        """Update an existing subject with edited data."""
        if not self.subject_service:
            self.log_bus.log("Error: Subject service not available", "error", "SubjectView")
            return

        # Get form values
        subject_id = self.subject_id_edit.text().strip()

        # Skip unique check if ID hasn't changed
        if subject_id != original_id:
            # Verify subject ID uniqueness via service
            existing_subject = self.subject_service.get_subject_by_id(subject_id)
            if existing_subject:
                self.log_bus.log(f"Error: Subject ID '{subject_id}' already exists", "error", "SubjectView")
                return

        # Get other form values
        sex_value = self.sex_combo.currentText()
        if sex_value == Sex.MALE.value:
            sex_enum = Sex.MALE
        elif sex_value == Sex.FEMALE.value:
            sex_enum = Sex.FEMALE
        else:
            sex_enum = Sex.UNKNOWN

        genotype = self.genotype_combo.currentText().strip()
        notes = self.notes_edit.toPlainText().strip()
        birth_date = self.birthdate_edit.dateTime().toPython()
        in_training_set = self.training_set_check.isChecked()

        # Get death date if enabled
        death_date = None
        if self.death_check.isChecked():
            death_date = self.deathdate_edit.dateTime().toPython()

        # For now, subject updates are not fully implemented in GUI services
        # Show a message directing users to proper workflows
        self.log_bus.log("Subject updates should be done through proper project management workflows", "warning", "SubjectView")
        self.subject_notification_label.setText("Use project management for subject updates")
        QTimer.singleShot(3000, lambda: self.subject_notification_label.setText(""))

        # Reset the form and button
        self.add_subject_button.setText("Add Subject")
        self.add_subject_button.clicked.disconnect()
        self.add_subject_button.clicked.connect(self.handle_add_subject)

        # Clear the form
        self.subject_id_edit.clear()
        self.genotype_combo.clear()
        self.notes_edit.clear()
        self.birthdate_edit.setDateTime(QDateTime.currentDateTime())
        self.training_set_check.setChecked(False)
        self.death_check.setChecked(False)
        self.deathdate_edit.setEnabled(False)
        self.deathdate_edit.setDateTime(QDateTime.currentDateTime())

        # Refresh the list
        self.refresh_subject_list_display()

    def handle_view_subject_notes(self):
        """Display the notes for the selected subject in a popup dialog."""
        selected_item = self.subjects_list.currentItem()
        if not selected_item:
            self.navigation_pane.add_log_message("No subject selected for viewing notes.", "warning")
            return
        
        # Extract subject ID
        item_text = selected_item.text()
        parts = item_text.split('|')
        if not parts:
            return
        
        id_part = parts[0].strip()
        if id_part.startswith("ID:"):
            subject_id = id_part[3:].strip()
        else:
            subject_id = id_part
        
        # Get the subject using GUI services
        subject_dto = self.subject_service.get_subject_by_id(subject_id)
        if not subject_dto:
            self.navigation_pane.add_log_message(f"Subject {subject_id} not found.", "error")
            return

        # Notes are not implemented in the current Subject model/DTO
        # Show a message indicating this feature is not available yet
        self.navigation_pane.add_log_message(f"Notes feature not yet implemented for subject {subject_id}.", "info")

    # New methods for Treatments and Genotypes management (naming now consistent with core modules)
    def _add_metadata_item(self, name: str, line_edit, add_method, refresh_method, item_type: str):
        """Generic helper method for adding metadata items (treatments, genotypes, etc.)."""
        value = line_edit.text().strip()
        if not value:
            self.log_bus.log(f"{item_type} name cannot be empty.", "error", "SubjectView")
            return
        try:
            add_method(value)
            line_edit.clear()
            refresh_method()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log(f"Added {item_type.lower()} '{value}' successfully.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error adding {item_type.lower()}: {e}", "error", "SubjectView")

    def handle_add_treatment(self):
        """Handles adding a new treatment to available treatments."""
        self._add_metadata_item(
            "treatment",
            self.new_treatment_line_edit,
            self.subject_service.add_treatment,
            self.refresh_treatments_lists,
            "Treatment"
        )

    def handle_add_genotype(self):
        """Handles adding a new genotype to available genotypes."""
        self._add_metadata_item(
            "genotype",
            self.new_genotype_line_edit,
            self.subject_service.add_genotype,
            self.refresh_genotypes_lists,
            "Genotype"
        )

    def handle_add_to_active_treatments(self):
        """Adds selected treatments from the available list to active treatments."""
        selected_items = self.all_treatments_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No treatments selected to add to active.", "warning", "SubjectView")
            return

        # For now, all available treatments are automatically active
        # In the future, this could implement selective activation
        self.log_bus.log("All available treatments are already active.", "info", "SubjectView")

    def handle_remove_active_treatments(self):
        """Removes selected treatments from the colony active list."""
        selected_items = self.current_treatments_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No treatments selected for removal from colony.", "warning", "SubjectView")
            return

        # This would need colony-specific treatment management
        # For now, just show that it's not implemented
        self.log_bus.log("Colony-specific treatment management not yet implemented.", "info", "SubjectView")

    def handle_promote_treatments_to_master(self):
        """Promote selected colony treatments to project master level."""
        selected_items = self.current_treatments_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No treatments selected to promote.", "warning")
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current master treatments
            current_master = self.subject_service.get_master_treatments()

            # Add selected items to master (avoiding duplicates)
            updated_master = current_master.copy()
            added_count = 0
            for tr in selected_names:
                if tr not in updated_master:
                    updated_master.append(tr)
                    added_count += 1

            if added_count > 0:
                self.subject_service.update_master_treatments(updated_master)
                self.navigation_pane.add_log_message(f"Promoted {added_count} treatment(s) to project master.", "success")
                self.refresh_treatments_lists()
            else:
                self.navigation_pane.add_log_message("All selected treatments already exist in project master.", "info")

        except Exception as e:
            self.log_bus.log(f"Error promoting treatments: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error promoting treatments: {str(e)}", "error")

    def handle_add_to_active_genotypes(self):
        """Adds selected genotypes from the available list to active genotypes."""
        selected_items = self.all_genotypes_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No genotypes selected to add to active.", "warning", "SubjectView")
            return

        # For now, all available genotypes are automatically active
        # In the future, this could implement selective activation
        self.log_bus.log("All available genotypes are already active.", "info", "SubjectView")

    def handle_remove_active_genotypes(self):
        """Removes selected genotypes from the colony active list."""
        selected_items = self.current_genotypes_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No genotypes selected for removal from colony.", "warning", "SubjectView")
            return

        # This would need colony-specific genotype management
        # For now, just show that it's not implemented
        self.log_bus.log("Colony-specific genotype management not yet implemented.", "info", "SubjectView")

    def handle_promote_genotypes_to_master(self):
        """Promote selected colony genotypes to project master level."""
        selected_items = self.current_genotypes_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No genotypes selected to promote.", "warning")
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current master genotypes
            current_master = self.subject_service.get_master_genotypes()

            # Add selected items to master (avoiding duplicates)
            updated_master = current_master.copy()
            added_count = 0
            for gt in selected_names:
                if gt not in updated_master:
                    updated_master.append(gt)
                    added_count += 1

            if added_count > 0:
                self.subject_service.update_master_genotypes(updated_master)
                self.navigation_pane.add_log_message(f"Promoted {added_count} genotype(s) to project master.", "success")
                self.refresh_genotypes_lists()
            else:
                self.navigation_pane.add_log_message("All selected genotypes already exist in project master.", "info")

        except Exception as e:
            self.log_bus.log(f"Error promoting genotypes: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error promoting genotypes: {str(e)}", "error")

    def refresh_treatments_lists(self):
        """Refresh the available and active treatments list widgets."""
        if hasattr(self, 'all_treatments_list'):
            self.all_treatments_list.clear()
            if self.subject_service:
                treatments = self.subject_service.get_available_treatments()
                if treatments:
                    for treatment in treatments:
                        self.all_treatments_list.addItem(treatment)
                else:
                    self.all_treatments_list.addItem("No treatments configured")

        if hasattr(self, 'current_treatments_list'):
            self.current_treatments_list.clear()
            # For now, all available treatments are considered active
            if self.subject_service:
                treatments = self.subject_service.get_available_treatments()
                if treatments:
                    for treatment in treatments:
                        self.current_treatments_list.addItem(treatment)
                else:
                    self.current_treatments_list.addItem("No active treatments")

    def refresh_genotypes_lists(self):
        """Refresh the available and active genotypes list widgets."""
        if hasattr(self, 'all_genotypes_list'):
            self.all_genotypes_list.clear()
            if self.subject_service:
                genotypes = self.subject_service.get_available_genotypes()
                if genotypes:
                    for genotype in genotypes:
                        self.all_genotypes_list.addItem(genotype)
                else:
                    self.all_genotypes_list.addItem("No genotypes configured")

        if hasattr(self, 'current_genotypes_list'):
            self.current_genotypes_list.clear()
            # For now, all available genotypes are considered active
            if self.subject_service:
                genotypes = self.subject_service.get_available_genotypes()
                if genotypes:
                    for genotype in genotypes:
                        self.current_genotypes_list.addItem(genotype)
                else:
                    self.current_genotypes_list.addItem("No active genotypes")

    def refresh_body_parts_page(self):
        """Refresh the body parts lists."""
        if not hasattr(self, 'all_bodyparts_list') or not hasattr(self, 'current_body_parts_list'):
            return

        # Clear lists
        self.all_bodyparts_list.clear()
        self.current_body_parts_list.clear()

        # Get body parts from subject service
        if self.subject_service:
            try:
                master_body_parts = self.subject_service.get_master_body_parts()
                active_body_parts = self.subject_service.get_active_body_parts()

                # Populate master list
                if master_body_parts:
                    for bp in master_body_parts:
                        self.all_bodyparts_list.addItem(bp)
                else:
                    self.all_bodyparts_list.addItem("No master body parts defined")

                # Populate active list
                if active_body_parts:
                    for bp in active_body_parts:
                        self.current_body_parts_list.addItem(bp)
                else:
                    self.current_body_parts_list.addItem("No active body parts")

                self.navigation_pane.add_log_message("Body parts lists refreshed.", "info")
            except Exception as e:
                self.log_bus.log(f"Error refreshing body parts: {e}", "error", "SubjectView")
                self.all_bodyparts_list.addItem("Error loading body parts")
                self.current_body_parts_list.addItem("Error loading body parts")
        else:
            self.all_bodyparts_list.addItem("Subject service not available")
            self.current_body_parts_list.addItem("Subject service not available")

    def refresh_objects_page(self):
        """Refresh the objects lists."""
        self.refresh_objects_ui()  # Reuse the existing refresh_objects_ui method

    def refresh_genotypes_page(self):
        """Refresh the genotypes lists."""
        self.refresh_genotypes_lists()  # Reuse the existing refresh method

    def refresh_treatments_page(self):
        """Refresh the treatments lists."""
        self.refresh_treatments_lists()  # Reuse the existing refresh method

    def format_item(self, item):
        """Utility to return the proper display string for an item."""
        return item.name if hasattr(item, "name") else str(item)

    def setup_genotypes_page(self):
        """Initialize the Genotypes page with project master ↔ colony active management."""
        self.genotypes_page = QWidget()
        layout = self.setup_page_layout(self.genotypes_page)

        # ---- Add New Genotype Section ----
        add_group, add_layout = self.create_form_section("Add Genotype", layout)

        add_row = self.create_form_row(add_layout)
        add_label = self.create_form_label("New Genotype:")
        self.new_genotype_line_edit = QLineEdit()
        self.new_genotype_line_edit.setPlaceholderText("Enter new genotype name...")
        self.new_genotype_line_edit.setProperty("class", "mus1-text-input")
        add_genotype_button = QPushButton("Add to Project Master")
        add_genotype_button.setProperty("class", "mus1-primary-button")
        add_genotype_button.clicked.connect(self.handle_add_genotype)
        add_row.addWidget(add_label)
        add_row.addWidget(self.new_genotype_line_edit, 1)
        add_row.addWidget(add_genotype_button)

        # ---- Genotypes Management Section ----
        genotypes_group, genotypes_layout = self.create_form_section("Manage Genotypes (Project Master ↔ Colony Active)", layout)

        genotypes_lists_layout = QHBoxLayout()
        genotypes_layout.addLayout(genotypes_lists_layout)

        available_genotype_col, available_genotype_layout = self.create_form_section("Project Master Genotypes", None, is_subgroup=True)
        self.all_genotypes_list = QListWidget()
        self.all_genotypes_list.setProperty("class", "mus1-list-widget")
        self.all_genotypes_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        available_genotype_layout.addWidget(self.all_genotypes_list)
        available_genotype_buttons = self.create_button_row(available_genotype_layout, False)
        add_to_active_genotype_button = QPushButton("Add Selected to Colony →")
        add_to_active_genotype_button.setProperty("class", "mus1-secondary-button")
        add_to_active_genotype_button.clicked.connect(self.handle_add_to_active_genotypes)
        available_genotype_buttons.addWidget(add_to_active_genotype_button)
        available_genotype_buttons.addStretch(1)

        active_genotype_col, active_genotype_layout = self.create_form_section("Colony Active Genotypes", None, is_subgroup=True)
        self.current_genotypes_list = QListWidget()
        self.current_genotypes_list.setProperty("class", "mus1-list-widget")
        self.current_genotypes_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        active_genotype_layout.addWidget(self.current_genotypes_list)
        active_genotype_buttons = self.create_button_row(active_genotype_layout, False)
        remove_genotype_button = QPushButton("← Remove from Colony")
        remove_genotype_button.setProperty("class", "mus1-secondary-button")
        remove_genotype_button.clicked.connect(self.handle_remove_active_genotypes)
        active_genotype_buttons.addWidget(remove_genotype_button)

        promote_genotype_button = QPushButton("↑ Promote to Project Master")
        promote_genotype_button.setProperty("class", "mus1-primary-button")
        promote_genotype_button.clicked.connect(self.handle_promote_genotypes_to_master)
        active_genotype_buttons.addWidget(promote_genotype_button)
        active_genotype_buttons.addStretch(1)

        genotypes_lists_layout.addWidget(available_genotype_col, 1)
        genotypes_lists_layout.addWidget(active_genotype_col, 1)

        layout.addStretch(1)
        self.add_page(self.genotypes_page, "Genotypes")
        self.refresh_genotypes_lists()

    def setup_treatments_page(self):
        """Initialize the Treatments page with project master ↔ colony active management."""
        self.treatments_page = QWidget()
        layout = self.setup_page_layout(self.treatments_page)

        # ---- Add New Treatment Section ----
        add_group, add_layout = self.create_form_section("Add Treatment", layout)

        add_row = self.create_form_row(add_layout)
        add_label = self.create_form_label("New Treatment:")
        self.new_treatment_line_edit = QLineEdit()
        self.new_treatment_line_edit.setPlaceholderText("Enter new treatment name...")
        self.new_treatment_line_edit.setProperty("class", "mus1-text-input")
        add_treatment_button = QPushButton("Add to Project Master")
        add_treatment_button.setProperty("class", "mus1-primary-button")
        add_treatment_button.clicked.connect(self.handle_add_treatment)
        add_row.addWidget(add_label)
        add_row.addWidget(self.new_treatment_line_edit, 1)
        add_row.addWidget(add_treatment_button)

        # ---- Treatments Management Section ----
        treatments_group, treatments_layout = self.create_form_section("Manage Treatments (Project Master ↔ Colony Active)", layout)

        treatments_lists_layout = QHBoxLayout()
        treatments_layout.addLayout(treatments_lists_layout)

        available_treatment_col, available_treatment_layout = self.create_form_section("Project Master Treatments", None, is_subgroup=True)
        self.all_treatments_list = QListWidget()
        self.all_treatments_list.setProperty("class", "mus1-list-widget")
        self.all_treatments_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        available_treatment_layout.addWidget(self.all_treatments_list)
        available_treatment_buttons = self.create_button_row(available_treatment_layout, False)
        add_to_active_treatment_button = QPushButton("Add Selected to Colony →")
        add_to_active_treatment_button.setProperty("class", "mus1-secondary-button")
        add_to_active_treatment_button.clicked.connect(self.handle_add_to_active_treatments)
        available_treatment_buttons.addWidget(add_to_active_treatment_button)
        available_treatment_buttons.addStretch(1)

        active_treatment_col, active_treatment_layout = self.create_form_section("Colony Active Treatments", None, is_subgroup=True)
        self.current_treatments_list = QListWidget()
        self.current_treatments_list.setProperty("class", "mus1-list-widget")
        self.current_treatments_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        active_treatment_layout.addWidget(self.current_treatments_list)
        active_treatment_buttons = self.create_button_row(active_treatment_layout, False)
        remove_treatment_button = QPushButton("← Remove from Colony")
        remove_treatment_button.setProperty("class", "mus1-secondary-button")
        remove_treatment_button.clicked.connect(self.handle_remove_active_treatments)
        active_treatment_buttons.addWidget(remove_treatment_button)

        promote_treatment_button = QPushButton("↑ Promote to Project Master")
        promote_treatment_button.setProperty("class", "mus1-primary-button")
        promote_treatment_button.clicked.connect(self.handle_promote_treatments_to_master)
        active_treatment_buttons.addWidget(promote_treatment_button)
        active_treatment_buttons.addStretch(1)

        treatments_lists_layout.addWidget(available_treatment_col, 1)
        treatments_lists_layout.addWidget(active_treatment_col, 1)

        layout.addStretch(1)
        self.add_page(self.treatments_page, "Treatments")
        self.refresh_treatments_lists()

    def setup_body_parts_page(self):
        """Initialize the user interface for managing body parts (Project Master ↔ Colony Active)."""
        self.bodyparts_page = QWidget()
        layout = self.setup_page_layout(self.bodyparts_page)

        # ---- Add New Body Part Section ----
        add_group, add_layout = self.create_form_section("Add Body Part", layout)

        add_row = self.create_form_row(add_layout)
        add_label = self.create_form_label("New Body Part:")
        self.new_bodypart_line_edit = QLineEdit()
        self.new_bodypart_line_edit.setPlaceholderText("Enter new body part name...")
        self.new_bodypart_line_edit.setProperty("class", "mus1-text-input")
        add_bodypart_button = QPushButton("Add to Project Master")
        add_bodypart_button.setProperty("class", "mus1-primary-button")
        add_bodypart_button.clicked.connect(self.handle_add_bodypart)
        add_row.addWidget(add_label)
        add_row.addWidget(self.new_bodypart_line_edit, 1)
        add_row.addWidget(add_bodypart_button)

        # --- Enhanced: Manage Body Parts Section ---
        management_group, management_layout = self.create_form_section("Manage Body Parts (Project Master ↔ Colony Active)", layout)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(self.SECTION_SPACING)
        management_layout.addLayout(columns_layout)

        # Project Master Column
        master_column, master_layout = self.create_form_section("Project Master Body Parts", None, is_subgroup=True)

        self.all_bodyparts_list = QListWidget()
        self.all_bodyparts_list.setProperty("class", "mus1-list-widget")
        self.all_bodyparts_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        master_layout.addWidget(self.all_bodyparts_list)

        master_buttons_row = self.create_button_row(master_layout)

        # Button to remove from master list completely
        remove_from_master_button = QPushButton("Remove from Master")
        remove_from_master_button.setProperty("class", "mus1-secondary-button")
        remove_from_master_button.clicked.connect(self.handle_remove_from_master)
        master_buttons_row.addWidget(remove_from_master_button)

        # Button to move selected from master TO colony active
        add_to_active_button = QPushButton("Add Selected to Colony →")
        add_to_active_button.setProperty("class", "mus1-secondary-button")
        add_to_active_button.clicked.connect(self.handle_add_selected_bodyparts_to_active)
        master_buttons_row.addWidget(add_to_active_button)
        master_buttons_row.addStretch(1)

        # Colony Active Column
        active_column, active_layout = self.create_form_section("Colony Active Body Parts", None, is_subgroup=True)

        self.current_body_parts_list = QListWidget()
        self.current_body_parts_list.setProperty("class", "mus1-list-widget")
        self.current_body_parts_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        active_layout.addWidget(self.current_body_parts_list)

        active_buttons_row = self.create_button_row(active_layout)

        # Button to remove selected FROM colony active
        remove_button = QPushButton("← Remove from Colony")
        remove_button.setProperty("class", "mus1-secondary-button")
        remove_button.clicked.connect(self.handle_remove_active_bodyparts)
        active_buttons_row.addWidget(remove_button)

        # Button to promote colony items to project master
        promote_button = QPushButton("↑ Promote to Project Master")
        promote_button.setProperty("class", "mus1-primary-button")
        promote_button.clicked.connect(self.handle_promote_bodyparts_to_master)
        active_buttons_row.addWidget(promote_button)
        active_buttons_row.addStretch(1)

        # Add columns to layout
        columns_layout.addWidget(master_column, 1)
        columns_layout.addWidget(active_column, 1)

        layout.addStretch(1)
        self.add_page(self.bodyparts_page, "Bodyparts")

        # Refresh the lists initially
        self.refresh_body_parts_page()

    def handle_remove_from_master(self):
        """Delete selected body parts from the master list."""
        selected_items = self.all_bodyparts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for deletion from master list.", "warning")
            return
        selected = [item.text() for item in selected_items]
        # Use project manager to get master body parts
        current_master = self.project_manager.get_master_body_parts()
        new_master = [bp for bp in current_master if bp not in selected]

        current_active = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
        new_active = [bp for bp in current_active if bp not in selected]
        
        self.window().project_manager.update_master_body_parts(new_master)
        self.window().project_manager.update_active_body_parts(new_active)
        self.navigation_pane.add_log_message(f"Deleted {len(selected)} body parts from project.", "success")
        self.refresh_body_parts_page()

    def handle_add_selected_bodyparts_to_active(self):
        """Add selected body parts from the master list into the active list."""
        selected_items = self.all_bodyparts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for active list.", "warning")
            return
        selected = [item.text() for item in selected_items]
        current = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
        updated = current + [bp for bp in selected if bp not in current]
        if self.subject_service:
            self.subject_service.update_active_body_parts(updated)
        self.navigation_pane.add_log_message(f"Added {len(selected)} body parts to active list.", "success")
        self.refresh_body_parts_page()

    def handle_remove_active_bodyparts(self):
        """Move selected body parts from the active list back to the master list."""
        selected_items = self.current_body_parts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected from active list.", "warning")
            return
        current_active = [self.current_body_parts_list.item(i).text() for i in range(self.current_body_parts_list.count())]
        items_to_move = [item.text() for item in selected_items]
        updated_active = [bp for bp in current_active if bp not in items_to_move]
        if self.subject_service:
            self.subject_service.update_active_body_parts(updated_active)

        # Use project manager to get master body parts
        current_master = self.project_manager.get_master_body_parts()
        
        new_master = current_master.copy()
        for bp in items_to_move:
            if bp not in new_master:
                new_master.append(bp)
        if new_master != current_master:
            if self.subject_service:
                self.subject_service.update_master_body_parts(new_master)
        
        self.navigation_pane.add_log_message(f"Moved {len(items_to_move)} body parts from active to master list.", "success")
        self.refresh_body_parts_page()

    def handle_add_bodypart(self):
        """Add a new body part to the project master list."""
        new_bp = self.new_bodypart_line_edit.text().strip()
        if not new_bp:
            self.navigation_pane.add_log_message("Body part name cannot be empty.", "warning")
            return

        try:
            # Add to master body parts
            current_master = self.subject_service.get_master_body_parts()
            if new_bp in current_master:
                self.navigation_pane.add_log_message(f"Body part '{new_bp}' already exists in master list.", "warning")
                return

            updated_master = current_master + [new_bp]
            self.subject_service.update_master_body_parts(updated_master)

            self.new_bodypart_line_edit.clear()
            self.navigation_pane.add_log_message(f"Added body part '{new_bp}' to project master.", "success")
            self.refresh_body_parts_page()
        except Exception as e:
            self.log_bus.log(f"Error adding body part: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error adding body part: {str(e)}", "error")

    def handle_promote_bodyparts_to_master(self):
        """Promote selected colony body parts to project master level."""
        selected_items = self.current_body_parts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected to promote.", "warning")
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current lists
            current_master = self.subject_service.get_master_body_parts()

            # Add selected items to master (avoiding duplicates)
            updated_master = current_master.copy()
            added_count = 0
            for bp in selected_names:
                if bp not in updated_master:
                    updated_master.append(bp)
                    added_count += 1

            if added_count > 0:
                self.subject_service.update_master_body_parts(updated_master)
                self.navigation_pane.add_log_message(f"Promoted {added_count} body part(s) to project master.", "success")
                self.refresh_body_parts_page()
            else:
                self.navigation_pane.add_log_message("All selected body parts already exist in project master.", "info")

        except Exception as e:
            self.log_bus.log(f"Error promoting body parts: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error promoting body parts: {str(e)}", "error")

    def setup_objects_page(self):
        """Setup the Objects page with project master ↔ colony active management."""
        self.objects_page = QWidget()
        layout = self.setup_page_layout(self.objects_page)

        # ---- Add New Object Section ----
        add_group, add_layout = self.create_form_section("Add Object", layout)

        add_row = self.create_form_row(add_layout)
        add_label = self.create_form_label("New Object:")
        self.new_object_line_edit = QLineEdit()
        self.new_object_line_edit.setPlaceholderText("Enter new object name...")
        self.new_object_line_edit.setProperty("class", "mus1-text-input")
        add_button = QPushButton("Add to Project Master")
        add_button.setProperty("class", "mus1-primary-button")
        add_button.clicked.connect(self.handle_add_object)
        add_row.addWidget(add_label)
        add_row.addWidget(self.new_object_line_edit, 1)
        add_row.addWidget(add_button)

        # ---- Objects Management Section ----
        objects_group, objects_layout = self.create_form_section("Manage Objects (Project Master ↔ Colony Active)", layout)

        lists_layout = QHBoxLayout()
        lists_layout.setSpacing(self.SECTION_SPACING)
        objects_layout.addLayout(lists_layout)

        # Project Master Objects Column
        available_column, available_layout = self.create_form_section("Project Master Objects", None, is_subgroup=True)
        self.all_objects_list = QListWidget()
        self.all_objects_list.setProperty("class", "mus1-list-widget")
        self.all_objects_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        available_layout.addWidget(self.all_objects_list)

        available_button_row = self.create_button_row(available_layout, add_stretch=False)
        add_to_active_button = QPushButton("Add Selected to Colony →")
        add_to_active_button.setProperty("class", "mus1-secondary-button")
        add_to_active_button.clicked.connect(self.move_objects_master_to_active)
        available_button_row.addWidget(add_to_active_button)
        remove_from_master_object_button = QPushButton("Remove from Master")
        remove_from_master_object_button.setProperty("class", "mus1-secondary-button")
        remove_from_master_object_button.clicked.connect(self.delete_object_from_master)
        available_button_row.addWidget(remove_from_master_object_button)
        available_button_row.addStretch(1)

        # Colony Active Objects Column
        active_column, active_layout = self.create_form_section("Colony Active Objects", None, is_subgroup=True)
        self.current_objects_list = QListWidget()
        self.current_objects_list.setProperty("class", "mus1-list-widget")
        self.current_objects_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        active_layout.addWidget(self.current_objects_list)

        active_button_row = self.create_button_row(active_layout, add_stretch=False)
        remove_from_active_object_button = QPushButton("← Remove from Colony")
        remove_from_active_object_button.setProperty("class", "mus1-secondary-button")
        remove_from_active_object_button.clicked.connect(self.move_objects_active_to_master)
        active_button_row.addWidget(remove_from_active_object_button)

        promote_object_button = QPushButton("↑ Promote to Project Master")
        promote_object_button.setProperty("class", "mus1-primary-button")
        promote_object_button.clicked.connect(self.handle_promote_objects_to_master)
        active_button_row.addWidget(promote_object_button)
        active_button_row.addStretch(1)

        lists_layout.addWidget(available_column, 1)
        lists_layout.addWidget(active_column, 1)

        layout.addStretch(1)
        self.add_page(self.objects_page, "Objects")
        self.refresh_objects_ui()

    def handle_add_object(self):
        """Add a new object to the project master list."""
        new_obj = self.new_object_line_edit.text().strip()
        if not new_obj:
            self.navigation_pane.add_log_message("Object name cannot be empty.", "warning")
            return

        try:
            # Add to master tracked objects
            current_master = self.subject_service.get_master_tracked_objects()
            if new_obj in current_master:
                self.navigation_pane.add_log_message(f"Object '{new_obj}' already exists in master list.", "warning")
                return

            updated_master = current_master + [new_obj]
            self.subject_service.update_master_tracked_objects(updated_master)

            self.new_object_line_edit.clear()
            self.navigation_pane.add_log_message(f"Added object '{new_obj}' to project master.", "success")
            self.refresh_objects_ui()
        except Exception as e:
            self.log_bus.log(f"Error adding object: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error adding object: {str(e)}", "error")

    def handle_promote_objects_to_master(self):
        """Promote selected colony objects to project master level."""
        selected_items = self.current_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected to promote.", "warning")
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current master objects
            current_master = self.subject_service.get_master_tracked_objects()

            # Add selected items to master (avoiding duplicates)
            updated_master = current_master.copy()
            added_count = 0
            for obj in selected_names:
                if obj not in updated_master:
                    updated_master.append(obj)
                    added_count += 1

            if added_count > 0:
                self.subject_service.update_master_tracked_objects(updated_master)
                self.navigation_pane.add_log_message(f"Promoted {added_count} object(s) to project master.", "success")
                self.refresh_objects_ui()
            else:
                self.navigation_pane.add_log_message("All selected objects already exist in project master.", "info")

        except Exception as e:
            self.log_bus.log(f"Error promoting objects: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error promoting objects: {str(e)}", "error")

    def move_objects_master_to_active(self):
        """Move selected objects from project master to colony active."""
        selected_items = self.all_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected to move to colony.", 'warning')
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current colony active objects
            current_active = self.subject_service.get_active_tracked_objects()

            # Add selected items to active (avoiding duplicates)
            updated_active = current_active.copy()
            added_count = 0
            for obj in selected_names:
                if obj not in updated_active:
                    updated_active.append(obj)
                    added_count += 1

            if added_count > 0:
                # For now, this updates the project-level active list
                # In the future, this should update colony-specific lists
                if self.subject_service:
                    self.subject_service.update_tracked_objects(updated_active, list_type="active")
                self.navigation_pane.add_log_message(f"Added {added_count} object(s) to colony active.", 'success')
                self.refresh_objects_ui()
            else:
                self.navigation_pane.add_log_message("All selected objects already active in colony.", 'info')

        except Exception as e:
            self.log_bus.log(f"Error moving objects to active: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error moving objects: {str(e)}", "error")

    def move_objects_active_to_master(self):
        """Move selected objects from colony active back to available status."""
        selected_items = self.current_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected to remove from colony.", 'warning')
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current colony active objects
            current_active = self.subject_service.get_active_tracked_objects()

            # Remove selected items from active
            updated_active = [obj for obj in current_active if obj not in selected_names]

            if self.subject_service:
                self.subject_service.update_tracked_objects(updated_active, list_type="active")

            self.navigation_pane.add_log_message(f"Removed {len(selected_names)} object(s) from colony active.", 'success')
            self.refresh_objects_ui()

        except Exception as e:
            self.log_bus.log(f"Error moving objects from active: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error moving objects: {str(e)}", "error")

    def delete_object_from_master(self):
        """Delete selected objects from project master list."""
        selected_items = self.all_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected for deletion from master.", 'warning')
            return

        selected_names = [item.text() for item in selected_items]

        try:
            # Get current master objects
            current_master = self.subject_service.get_master_tracked_objects()
            current_active = self.subject_service.get_active_tracked_objects()

            # Remove from master and active lists
            updated_master = [obj for obj in current_master if obj not in selected_names]
            updated_active = [obj for obj in current_active if obj not in selected_names]

            self.subject_service.update_master_tracked_objects(updated_master)
            if self.subject_service:
                self.subject_service.update_tracked_objects(updated_active, list_type="active")

            self.navigation_pane.add_log_message(f"Deleted {len(selected_names)} object(s) from project master.", 'success')
            self.refresh_objects_ui()

        except Exception as e:
            self.log_bus.log(f"Error deleting objects: {e}", "error", "SubjectView")
            self.navigation_pane.add_log_message(f"Error deleting objects: {str(e)}", "error")

    def refresh_objects_ui(self):
        # Clear list widgets if they exist
        if hasattr(self, 'all_objects_list'):
            self.all_objects_list.clear()
        if hasattr(self, 'current_objects_list'):
            self.current_objects_list.clear()

        # Get tracked objects from subject service
        if self.subject_service:
            try:
                master_objects = self.subject_service.get_master_tracked_objects()
                active_objects = self.subject_service.get_active_tracked_objects()

                # Populate master list
                if master_objects:
                    for obj in master_objects:
                        self.all_objects_list.addItem(obj)
                else:
                    self.all_objects_list.addItem("No master objects defined")

                # Populate active list
                if active_objects:
                    for obj in active_objects:
                        self.current_objects_list.addItem(obj)
                else:
                    self.current_objects_list.addItem("No active objects")
            except Exception as e:
                self.log_bus.log(f"Error refreshing objects: {e}", "error", "SubjectView")
                if hasattr(self, 'all_objects_list'):
                    self.all_objects_list.addItem("Error loading objects")
                if hasattr(self, 'current_objects_list'):
                    self.current_objects_list.addItem("Error loading objects")
        else:
            if hasattr(self, 'all_objects_list'):
                self.all_objects_list.addItem("Subject service not available")
            if hasattr(self, 'current_objects_list'):
                self.current_objects_list.addItem("Subject service not available")

    def _get_active_objects(self):
        """Get active tracked objects from subject service."""
        if self.subject_service:
            try:
                return self.subject_service.get_active_tracked_objects()
            except Exception as e:
                self.log_bus.log(f"Error getting active objects: {e}", "error", "SubjectView")
                return []
        return []

    def _get_master_objects(self):
        """Get master tracked objects from subject service."""
        if self.subject_service:
            try:
                return self.subject_service.get_master_tracked_objects()
            except Exception as e:
                self.log_bus.log(f"Error getting master objects: {e}", "error", "SubjectView")
                return []
        return []

    def refresh_active_metadata_dropdowns(self):
        """Populate the genotype and treatment dropdowns in the Add Subject page from the available lists."""
        self.genotype_combo.clear()
        self.treatment_combo.clear()

        # Get available genotypes and treatments from the service
        if self.subject_service:
            available_genotypes = self.subject_service.get_available_genotypes()
            available_treatments = self.subject_service.get_available_treatments()

            # Populate genotype combo
            if available_genotypes:
                for genotype in available_genotypes:
                    self.genotype_combo.addItem(genotype)
            else:
                # Add some defaults if none configured
                default_genotypes = ["WT", "HET", "KO"]
                for genotype in default_genotypes:
                    self.genotype_combo.addItem(genotype)

            # Populate treatment combo
            if available_treatments:
                for treatment in available_treatments:
                    self.treatment_combo.addItem(treatment)
            else:
                self.treatment_combo.addItem("No treatments configured")
        else:
            # Fallback if service not available
            self.genotype_combo.addItem("Service unavailable")
            self.treatment_combo.addItem("Service unavailable")

