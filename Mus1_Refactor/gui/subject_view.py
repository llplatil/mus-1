from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidget,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel, QDateTimeEdit, QCheckBox
)
from core.metadata import Sex
from gui.navigation_pane import NavigationPane  
from gui.base_view import BaseView
from PySide6.QtCore import QDateTime
from core.logging_bus import LoggingEventBus
from PySide6.QtCore import Qt
from gui.metadata_display import MetadataTreeView  # Import for overview display

class SubjectView(BaseView):
    def __init__(self, parent=None):
        # Initialize with base view and specific name
        super().__init__(parent, view_name="subject")
        
        # Log initialization
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("SubjectView initialized", "info", "SubjectView")

        # Immediately assign the project_manager so that subsequent methods can use it
        self.project_manager = self.window().project_manager

        # Setup navigation for this view with three pages:
        # "Subject Metadata" for adding new subjects and
        # "Add Subject" for adding new subjects and
        # "Subjects Overview" for viewing subjects using a tree display.
        self.setup_navigation(["Subject Metadata", "Add Subject", "Subjects Overview"])
        
        # Create all pages:
        self.setup_subject_metadata_page()
        self.setup_add_subject_page()
        self.setup_view_subjects_page()
        
        # Set default selection; you can change which page is default (here index 1 = "Add Subject")
        self.change_page(1)  # This will trigger the appropriate refresh methods

    def setup_subject_metadata_page(self):
        """Setup the Subject Metadata page for managing treatments and genotypes."""
        self.page_metadata = QWidget()
        meta_layout = QVBoxLayout(self.page_metadata)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(10)

        # ---- Treatments Management Section ----
        treatments_group, treatments_layout = self.create_form_section("Treatments Management", meta_layout)

        # New Treatment entry row
        new_treatment_row = QHBoxLayout()
        new_treatment_label = self.create_form_label("New Treatment:")
        self.new_treatment_line_edit = QLineEdit()
        self.new_treatment_line_edit.setPlaceholderText("Enter new treatment name...")
        self.new_treatment_line_edit.setProperty("class", "mus1-text-input")
        treatment_add_button = QPushButton("Add Treatment")
        treatment_add_button.setProperty("class", "mus1-primary-button")
        treatment_add_button.clicked.connect(self.handle_add_treatment)
        new_treatment_row.addWidget(new_treatment_label)
        new_treatment_row.addWidget(self.new_treatment_line_edit, 1)
        new_treatment_row.addWidget(treatment_add_button)
        treatments_layout.addLayout(new_treatment_row)

        # Treatments lists: available and active
        treatments_lists_layout = QHBoxLayout()
        treatments_layout.addLayout(treatments_lists_layout)

        available_treatment_col, available_treatment_layout = self.create_form_section("Available Treatments:", treatments_lists_layout, True)
        self.all_treatments_list = QListWidget()
        self.all_treatments_list.setProperty("class", "mus1-list-widget")
        self.all_treatments_list.setSelectionMode(QListWidget.ExtendedSelection)
        available_treatment_layout.addWidget(self.all_treatments_list)
        available_treatment_buttons = self.create_button_row(available_treatment_layout, True)
        add_to_active_treatment_button = QPushButton("Add Selected to Active →")
        add_to_active_treatment_button.setProperty("class", "mus1-secondary-button")
        add_to_active_treatment_button.clicked.connect(self.handle_add_to_active_treatments)
        available_treatment_buttons.addWidget(add_to_active_treatment_button)

        active_treatment_col, active_treatment_layout = self.create_form_section("Active Treatments:", treatments_lists_layout, True)
        self.current_treatments_list = QListWidget()
        self.current_treatments_list.setProperty("class", "mus1-list-widget")
        self.current_treatments_list.setSelectionMode(QListWidget.ExtendedSelection)
        active_treatment_layout.addWidget(self.current_treatments_list)
        active_treatment_buttons = self.create_button_row(active_treatment_layout, True)
        remove_treatment_button = QPushButton("← Remove Selected")
        remove_treatment_button.setProperty("class", "mus1-secondary-button")
        remove_treatment_button.clicked.connect(self.handle_remove_active_treatments)
        active_treatment_buttons.addWidget(remove_treatment_button)

        treatments_lists_layout.addWidget(available_treatment_col, 1)
        treatments_lists_layout.addWidget(active_treatment_col, 1)

        # ---- Genotypes Management Section ----
        genotypes_group, genotypes_layout = self.create_form_section("Genotypes Management", meta_layout)

        new_genotype_row = QHBoxLayout()
        new_genotype_label = self.create_form_label("New Genotype:")
        self.new_genotype_line_edit = QLineEdit()
        self.new_genotype_line_edit.setPlaceholderText("Enter new genotype name...")
        self.new_genotype_line_edit.setProperty("class", "mus1-text-input")
        genotype_add_button = QPushButton("Add Genotype")
        genotype_add_button.setProperty("class", "mus1-primary-button")
        genotype_add_button.clicked.connect(self.handle_add_genotype)
        new_genotype_row.addWidget(new_genotype_label)
        new_genotype_row.addWidget(self.new_genotype_line_edit, 1)
        new_genotype_row.addWidget(genotype_add_button)
        genotypes_layout.addLayout(new_genotype_row)

        genotypes_lists_layout = QHBoxLayout()
        genotypes_layout.addLayout(genotypes_lists_layout)

        available_genotype_col, available_genotype_layout = self.create_form_section("Available Genotypes:", genotypes_lists_layout, True)
        self.all_genotypes_list = QListWidget()
        self.all_genotypes_list.setProperty("class", "mus1-list-widget")
        self.all_genotypes_list.setSelectionMode(QListWidget.ExtendedSelection)
        available_genotype_layout.addWidget(self.all_genotypes_list)
        available_genotype_buttons = self.create_button_row(available_genotype_layout, True)
        add_to_active_genotype_button = QPushButton("Add Selected to Active →")
        add_to_active_genotype_button.setProperty("class", "mus1-secondary-button")
        add_to_active_genotype_button.clicked.connect(self.handle_add_to_active_genotypes)
        available_genotype_buttons.addWidget(add_to_active_genotype_button)

        active_genotype_col, active_genotype_layout = self.create_form_section("Active Genotypes:", genotypes_lists_layout, True)
        self.current_genotypes_list = QListWidget()
        self.current_genotypes_list.setProperty("class", "mus1-list-widget")
        self.current_genotypes_list.setSelectionMode(QListWidget.ExtendedSelection)
        active_genotype_layout.addWidget(self.current_genotypes_list)
        active_genotype_buttons = self.create_button_row(active_genotype_layout, True)
        remove_genotype_button = QPushButton("← Remove Selected")
        remove_genotype_button.setProperty("class", "mus1-secondary-button")
        remove_genotype_button.clicked.connect(self.handle_remove_active_genotypes)
        active_genotype_buttons.addWidget(remove_genotype_button)

        genotypes_lists_layout.addWidget(available_genotype_col, 1)
        genotypes_lists_layout.addWidget(active_genotype_col, 1)

        meta_layout.addStretch(1)
        self.add_page(self.page_metadata, "Subject Metadata")

    def refresh_active_metadata_dropdowns(self):
        """Populate the genotype and treatment dropdowns in the Add Subject page from the active lists."""
        self.genotype_combo.clear()
        self.treatment_combo.clear()
        # Fetch updated active lists from state
        active_genotypes = self.project_manager.state_manager.get_genotypes().get("active", [])
        active_treatments = self.project_manager.state_manager.get_treatments().get("active", [])
        for genotype in active_genotypes:
            if hasattr(genotype, "name"):
                self.genotype_combo.addItem(genotype.name)
            else:
                self.genotype_combo.addItem(genotype)
        for treatment in active_treatments:
            if hasattr(treatment, "name"):
                self.treatment_combo.addItem(treatment.name)
            else:
                self.treatment_combo.addItem(treatment)

    def setup_add_subject_page(self):
        """Setup the Add Subject page."""
        # Create the page widget
        self.page_add_subject = QWidget()
        add_layout = QVBoxLayout(self.page_add_subject)
        add_layout.setContentsMargins(10, 10, 10, 10)
        add_layout.setSpacing(10)

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
        self.sex_combo.addItems([Sex.M.value, Sex.F.value, Sex.UNKNOWN.value])
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
        self.subject_notification_label.setAlignment(Qt.AlignCenter)
        add_layout.addWidget(self.subject_notification_label)
        
        # Create a list widget for displaying all subjects
        subjects_group, subjects_layout = self.create_form_section("All Subjects", add_layout)
        self.subjects_list = QListWidget()
        self.subjects_list.setProperty("class", "mus1-list-widget")
        self.subjects_list.setSelectionMode(QListWidget.SingleSelection)
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
        self.add_page(self.page_add_subject, "Add Subject")
    
    def handle_add_subject(self):
        """Handle the logic for adding a new subject, as before."""
        if not self.project_manager:
            self.log_bus.log("Error: No ProjectManager is set", "error", "SubjectView")
            return

        subject_id = self.subject_id_edit.text().strip()
        if not subject_id:
            self.log_bus.log("Error: Subject ID cannot be empty", "error", "SubjectView")
            return

        # Verify subject ID uniqueness
        existing_ids = [subj.id for subj in self.project_manager.state_manager.get_sorted_list("subjects")]
        if subject_id in existing_ids:
            print("Subject ID already exists!")
            self.log_bus.log(f"Error: Subject ID '{subject_id}' already exists", "error", "SubjectView")
            return

        # Retrieve the sex enum from the combo
        sex_value = self.sex_combo.currentText()
        if sex_value == Sex.M.value:
            sex_enum = Sex.M
        elif sex_value == Sex.F.value:
            sex_enum = Sex.F
        else:
            sex_enum = Sex.UNKNOWN

        genotype = self.genotype_combo.currentText().strip()
        notes = self.notes_edit.toPlainText().strip()
        birth_date = self.birthdate_edit.dateTime().toPython()
        in_training_set = self.training_set_check.isChecked()

        # Add the subject via ProjectManager
        self.project_manager.add_subject(
            subject_id=subject_id,
            sex=sex_enum,
            genotype=genotype,
            notes=notes,
            birth_date=birth_date,
            in_training_set=in_training_set,
        )

        # Clear the input fields after successful addition
        self.subject_id_edit.clear()
        self.genotype_combo.clear()
        self.notes_edit.clear()
        self.birthdate_edit.setDateTime(QDateTime.currentDateTime())
        self.training_set_check.setChecked(False)

        # Refresh the displayed subject list on the same page
        self.refresh_subject_list_display()
        
        # Log the successful addition and show notification
        self.log_bus.log(f"Subject '{subject_id}' added successfully", "success", "SubjectView")
        self.subject_notification_label.setText("Subject added successfully!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.subject_notification_label.setText(""))

    def refresh_subject_list_display(self):
        """Refresh the list of all subjects in the project with full metadata details."""
        if not self.project_manager:
            return
            
        # Only refresh if the subjects list exists and we're on the right page (Add Subject)
        if hasattr(self, 'subjects_list') and self.pages.currentIndex() == 1:
            # Update the UI by clearing and repopulating the subjects list
            self.subjects_list.clear()
            all_subjects = self.project_manager.state_manager.get_sorted_subjects()
            
            # Log the refresh activity
            self.log_bus.log(f"Refreshing subject list: {len(all_subjects)} subjects found", "info", "SubjectView")
            
            for subj in all_subjects:
                birth_str = subj.birth_date.strftime('%Y-%m-%d %H:%M:%S') if subj.birth_date else 'N/A'
                
                # Create the basic details string
                details = (f"ID: {subj.id} | Sex: {subj.sex.value} | Genotype: {subj.genotype or 'N/A'} "
                          f"| Training: {subj.in_training_set}")
                
                # Add notes snippet if available
                if subj.notes and subj.notes.strip():
                    # Get a truncated version of the notes
                    notes_snippet = subj.notes.strip()
                    if len(notes_snippet) > 30:
                        notes_snippet = notes_snippet[:30] + "..."
                    
                    # Append notes to details string
                    details += f" | Notes: {notes_snippet}"
                
                self.subjects_list.addItem(details)

    def refresh_experiment_list_by_subject_display(self):
        """Refresh the list widget displaying experiments by subject."""
        # Implementation pending
        pass

    def assign_project_manager(self, project_manager):
        """Assign the project_manager and subscribe for automatic refresh from state changes."""
        self.project_manager = project_manager
        # Set the observer callback to refresh_subject_list_display
        self._state_subscription = self.refresh_subject_list_display
        # Store reference to state_manager for cleaner access
        self._state_manager = project_manager.state_manager
        self._state_manager.subscribe(self._state_subscription)

    def closeEvent(self, event):
        """Clean up when the view is closed."""
        # Unsubscribe the observer when the view is closed
        if hasattr(self, '_state_manager') and hasattr(self, '_state_subscription'):
            self._state_manager.unsubscribe(self._state_subscription)
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
        if index == 0:  # Subject Metadata
            # Refresh the treatments and genotypes lists
            self.refresh_treatments_lists()
            self.refresh_genotypes_lists()
        elif index == 1:  # Add Subject
            # Refresh the subjects list and the active dropdowns
            self.refresh_subject_list_display()
            self.refresh_active_metadata_dropdowns()
        elif index == 2:  # Subjects Overview
            # Refresh the overview only
            self.refresh_overview()

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
        if hasattr(self, 'project_manager'):
            self.project_manager.remove_subject(subject_id)
            self.refresh_subject_list_display()

    def setup_view_subjects_page(self):
        """Setup the Subjects Overview page."""
        self.page_overview = QWidget()
        overview_layout = QVBoxLayout(self.page_overview)
        overview_layout.setContentsMargins(10, 10, 10, 10)
        overview_layout.setSpacing(10)
        
        # Create a metadata tree view for hierarchical display of subjects and experiments
        tree_group, tree_layout = self.create_form_section("Subjects and Experiments Overview", overview_layout)
        self.metadata_tree = MetadataTreeView(tree_group)
        tree_layout.addWidget(self.metadata_tree)
        
        # Add a refresh button to allow manual updates
        refresh_row = self.create_button_row(tree_layout)
        refresh_button = QPushButton("Refresh Overview")
        refresh_button.setProperty("class", "mus1-primary-button")
        refresh_button.clicked.connect(self.refresh_overview)
        refresh_row.addWidget(refresh_button)
        
        # Add the overview page with title "Subjects Overview" to the stacked widget
        self.add_page(self.page_overview, "Subjects Overview")

    def refresh_overview(self):
        """Refresh the Subjects Overview display using metadata_tree."""
        if not self.project_manager:
            return
        state = self.project_manager.state_manager.project_state
        subjects = state.subjects          # Dictionary of subject metadata
        experiments = state.experiments      # Dictionary of experiment metadata
        # Populate the metadata tree view with subjects and their experiments
        self.metadata_tree.populate_subjects_with_experiments(subjects, experiments)

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
        
        # Get the subject from the state manager
        subject = self.project_manager.state_manager.project_state.subjects.get(subject_id)
        if not subject:
            self.navigation_pane.add_log_message(f"Subject {subject_id} not found.", "error")
            return
        
        # Populate the form with subject data for editing
        self.subject_id_edit.setText(subject_id)
        self.sex_combo.setCurrentText(subject.sex.value)
        self.genotype_combo.setCurrentText(subject.genotype or "")
        self.notes_edit.setText(subject.notes or "")
        
        if subject.birth_date:
            self.birthdate_edit.setDateTime(QDateTime(subject.birth_date))
        else:
            self.birthdate_edit.setDateTime(QDateTime.currentDateTime())
        
        self.training_set_check.setChecked(subject.in_training_set)
        
        # Enable death date if it exists
        has_death_date = hasattr(subject, 'death_date') and subject.death_date is not None
        self.death_check.setChecked(has_death_date)
        if has_death_date:
            self.deathdate_edit.setDateTime(QDateTime(subject.death_date))
        else:
            self.deathdate_edit.setDateTime(QDateTime.currentDateTime())
        
        # Change add button to update button
        self.add_subject_button.setText("Update Subject")
        self.add_subject_button.clicked.disconnect()
        self.add_subject_button.clicked.connect(lambda: self.handle_update_subject(subject_id))
        
        # Focus on first field for editing
        self.genotype_combo.setFocus()

    def handle_update_subject(self, original_id):
        """Update an existing subject with edited data."""
        # Similar to handle_add_subject but updates existing subject
        if not self.project_manager:
            self.log_bus.log("Error: No ProjectManager is set", "error", "SubjectView")
            return

        # Get form values
        subject_id = self.subject_id_edit.text().strip()
        
        # Skip unique check if ID hasn't changed
        if subject_id != original_id:
            # Verify subject ID uniqueness
            existing_ids = [subj.id for subj in self.project_manager.state_manager.get_sorted_list("subjects")]
            if subject_id in existing_ids:
                self.log_bus.log(f"Error: Subject ID '{subject_id}' already exists", "error", "SubjectView")
                return

        # Get other form values
        sex_value = self.sex_combo.currentText()
        if sex_value == Sex.M.value:
            sex_enum = Sex.M
        elif sex_value == Sex.F.value:
            sex_enum = Sex.F
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

        # Update the subject via ProjectManager
        if original_id != subject_id:
            # If ID changed, remove the old one first
            self.project_manager.remove_subject(original_id)
        
        # Add with updated data    
        self.project_manager.add_subject(
            subject_id=subject_id,
            sex=sex_enum,
            genotype=genotype,
            notes=notes,
            birth_date=birth_date,
            in_training_set=in_training_set,
            death_date=death_date
        )

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
        
        # Show notification
        self.subject_notification_label.setText("Subject updated successfully!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.subject_notification_label.setText(""))

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
        
        # Get the subject
        subject = self.project_manager.state_manager.project_state.subjects.get(subject_id)
        if not subject:
            self.navigation_pane.add_log_message(f"Subject {subject_id} not found.", "error")
            return
        
        # If there are no notes, show a message
        if not subject.notes or subject.notes.strip() == "":
            self.navigation_pane.add_log_message(f"No notes for subject {subject_id}.", "info")
            return
        
        # Create and show dialog with notes
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Notes for Subject {subject_id}")
        dialog.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        notes_display = QTextEdit()
        notes_display.setReadOnly(True)
        notes_display.setText(subject.notes)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        
        layout.addWidget(notes_display)
        layout.addWidget(close_button)
        
        dialog.exec()

    # New methods for Treatments and Genotypes management (naming now consistent with core modules)
    def handle_add_treatment(self):
        """Handles adding a new treatment to available treatments."""
        new_treatment = self.new_treatment_line_edit.text().strip()
        if not new_treatment:
            self.log_bus.log("Treatment name cannot be empty.", "error", "SubjectView")
            return
        try:
            self.project_manager.add_treatment(new_treatment)
            self.new_treatment_line_edit.clear()
            self.refresh_treatments_lists()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log(f"Added treatment '{new_treatment}' successfully.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error adding treatment: {e}", "error", "SubjectView")

    def handle_add_genotype(self):
        """Handles adding a new genotype to available genotypes."""
        new_genotype = self.new_genotype_line_edit.text().strip()
        if not new_genotype:
            self.log_bus.log("Genotype name cannot be empty.", "error", "SubjectView")
            return
        try:
            self.project_manager.add_genotype(new_genotype)
            self.new_genotype_line_edit.clear()
            self.refresh_genotypes_lists()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log(f"Added genotype '{new_genotype}' successfully.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error adding genotype: {e}", "error", "SubjectView")

    def handle_add_to_active_treatments(self):
        """Adds selected treatments from the available list to active treatments."""
        selected_items = self.all_treatments_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No treatments selected to add to active.", "warning", "SubjectView")
            return
        current_active = self.project_manager.state_manager.get_treatments().get("active", [])
        for item in selected_items:
            treatment = item.text().strip()
            if treatment not in current_active:
                current_active.append(treatment)
        try:
            self.project_manager.update_active_treatments(current_active)
            self.refresh_treatments_lists()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log("Active treatments updated.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error updating active treatments: {e}", "error", "SubjectView")

    def handle_remove_active_treatments(self):
        """Removes selected treatments from the active treatments list."""
        selected_items = self.current_treatments_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No active treatments selected for removal.", "warning", "SubjectView")
            return
        current_active = self.project_manager.state_manager.get_treatments().get("active", [])
        for item in selected_items:
            treatment = item.text().strip()
            if treatment in current_active:
                current_active.remove(treatment)
        try:
            self.project_manager.update_active_treatments(current_active)
            self.refresh_treatments_lists()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log("Active treatments updated after removal.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error updating active treatments: {e}", "error", "SubjectView")

    def handle_add_to_active_genotypes(self):
        """Adds selected genotypes from the available list to active genotypes."""
        selected_items = self.all_genotypes_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No genotypes selected to add to active.", "warning", "SubjectView")
            return
        current_active = self.project_manager.state_manager.get_genotypes().get("active", [])
        for item in selected_items:
            genotype = item.text().strip()
            if genotype not in current_active:
                current_active.append(genotype)
        try:
            self.project_manager.update_active_genotypes(current_active)
            self.refresh_genotypes_lists()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log("Active genotypes updated.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error updating active genotypes: {e}", "error", "SubjectView")

    def handle_remove_active_genotypes(self):
        """Removes selected genotypes from the active genotypes list."""
        selected_items = self.current_genotypes_list.selectedItems()
        if not selected_items:
            self.log_bus.log("No active genotypes selected for removal.", "warning", "SubjectView")
            return
        current_active = self.project_manager.state_manager.get_genotypes().get("active", [])
        for item in selected_items:
            genotype = item.text().strip()
            if genotype in current_active:
                current_active.remove(genotype)
        try:
            self.project_manager.update_active_genotypes(current_active)
            self.refresh_genotypes_lists()
            self.refresh_active_metadata_dropdowns()
            self.log_bus.log("Active genotypes updated after removal.", "success", "SubjectView")
        except Exception as e:
            self.log_bus.log(f"Error updating active genotypes: {e}", "error", "SubjectView")

    def refresh_treatments_lists(self):
        """Refresh the available and active treatments list widgets."""
        treatments = self.project_manager.state_manager.get_treatments()
        self.all_treatments_list.clear()
        self.current_treatments_list.clear()
        for treatment in treatments.get("available", []):
            if hasattr(treatment, "name"):
                self.all_treatments_list.addItem(treatment.name)
            else:
                self.all_treatments_list.addItem(treatment)
        for treatment in treatments.get("active", []):
            if hasattr(treatment, "name"):
                self.current_treatments_list.addItem(treatment.name)
            else:
                self.current_treatments_list.addItem(treatment)

    def refresh_genotypes_lists(self):
        """Refresh the available and active genotypes list widgets."""
        genotypes = self.project_manager.state_manager.get_genotypes()
        self.all_genotypes_list.clear()
        self.current_genotypes_list.clear()
        for genotype in genotypes.get("available", []):
            if hasattr(genotype, "name"):
                self.all_genotypes_list.addItem(genotype.name)
            else:
                self.all_genotypes_list.addItem(genotype)
        for genotype in genotypes.get("active", []):
            if hasattr(genotype, "name"):
                self.current_genotypes_list.addItem(genotype.name)
            else:
                self.current_genotypes_list.addItem(genotype)