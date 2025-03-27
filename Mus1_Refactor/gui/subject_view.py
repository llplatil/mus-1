from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidget,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel, QDateTimeEdit, QCheckBox,
    QSpinBox, QDoubleSpinBox, QSlider, QFileDialog
)
from core.metadata import Sex
from gui.navigation_pane import NavigationPane  
from gui.base_view import BaseView
from PySide6.QtCore import QDateTime
from core.logging_bus import LoggingEventBus
from PySide6.QtCore import Qt
from gui.metadata_display import MetadataTreeView  # Import for overview display
from pathlib import Path
from core import ObjectMetadata, BodyPartMetadata  # Import needed for body parts and objects pages

class SubjectView(BaseView):
    def __init__(self, parent=None):
        # Initialize with base view and specific name
        super().__init__(parent, view_name="subject")
        
        # Log initialization
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("SubjectView initialized", "info", "SubjectView")

        # Immediately assign the project_manager so that subsequent methods can use it
        self.project_manager = self.window().project_manager
        # Assign state_manager for easier access
        self.state_manager = self.window().state_manager

        # Setup navigation for this view with six pages
        self.setup_navigation(["Subject Overview", "Bodyparts", "Genotypes", "Treatments", "Objects", "Subjects"])
        
        # Create all pages in the new order:
        self.setup_view_subjects_page()       # 1. Subject Overview
        self.setup_body_parts_page()          # 2. Bodyparts
        self.setup_genotypes_page()           # 3. Genotypes
        self.setup_treatments_page()          # 4. Treatments
        self.setup_objects_page()             # 5. Objects
        self.setup_add_subject_page()         # 6. Subjects
        
        # Set default selection to Subject Overview
        self.change_page(0)

    def setup_add_subject_page(self):
        """Setup the Subjects page (previously named Add Subject)."""
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
        self.add_page(self.page_add_subject, "Subjects")
    
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

    def refresh_body_parts_page(self):
        """Refresh the body parts lists."""
        if not hasattr(self, 'all_bodyparts_list') or not hasattr(self, 'current_body_parts_list'):
            return
        
        # Get sorted body parts from state_manager
        sorted_parts = self.state_manager.get_sorted_body_parts()
        
        self.all_bodyparts_list.clear()
        for bp in sorted_parts["master"]:
            self.all_bodyparts_list.addItem(self.format_item(bp))
        
        self.current_body_parts_list.clear()
        for bp in sorted_parts["active"]:
            self.current_body_parts_list.addItem(self.format_item(bp))
        
        self.navigation_pane.add_log_message("Body parts lists refreshed.", "info")

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
        """Initialize the Genotypes page."""
        self.genotypes_page = QWidget()
        layout = QVBoxLayout(self.genotypes_page)
        layout.setSpacing(self.SECTION_SPACING)

        # ---- Genotypes Management Section ----
        genotypes_group, genotypes_layout = self.create_form_section("Genotypes Management", layout)

        new_genotype_row = self.create_form_row(genotypes_layout)
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

        genotypes_lists_layout = QHBoxLayout()
        genotypes_layout.addLayout(genotypes_lists_layout)

        available_genotype_col, available_genotype_layout = self.create_form_section("Available Genotypes:", None, is_subgroup=True)
        self.all_genotypes_list = QListWidget()
        self.all_genotypes_list.setProperty("class", "mus1-list-widget")
        self.all_genotypes_list.setSelectionMode(QListWidget.ExtendedSelection)
        available_genotype_layout.addWidget(self.all_genotypes_list)
        available_genotype_buttons = self.create_button_row(available_genotype_layout, True)
        add_to_active_genotype_button = QPushButton("Add Selected to Active →")
        add_to_active_genotype_button.setProperty("class", "mus1-secondary-button")
        add_to_active_genotype_button.clicked.connect(self.handle_add_to_active_genotypes)
        available_genotype_buttons.addWidget(add_to_active_genotype_button)

        active_genotype_col, active_genotype_layout = self.create_form_section("Active Genotypes:", None, is_subgroup=True)
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

        layout.addStretch(1)
        self.add_page(self.genotypes_page, "Genotypes")
        self.refresh_genotypes_lists()

    def setup_treatments_page(self):
        """Initialize the Treatments page."""
        self.treatments_page = QWidget()
        layout = QVBoxLayout(self.treatments_page)
        layout.setSpacing(self.SECTION_SPACING)

        # ---- Treatments Management Section ----
        treatments_group, treatments_layout = self.create_form_section("Treatments Management", layout)

        # New Treatment entry row
        new_treatment_row = self.create_form_row(treatments_layout)
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

        # Treatments lists: available and active
        treatments_lists_layout = QHBoxLayout()
        treatments_layout.addLayout(treatments_lists_layout)

        available_treatment_col, available_treatment_layout = self.create_form_section("Available Treatments:", None, is_subgroup=True)
        self.all_treatments_list = QListWidget()
        self.all_treatments_list.setProperty("class", "mus1-list-widget")
        self.all_treatments_list.setSelectionMode(QListWidget.ExtendedSelection)
        available_treatment_layout.addWidget(self.all_treatments_list)
        available_treatment_buttons = self.create_button_row(available_treatment_layout, True)
        add_to_active_treatment_button = QPushButton("Add Selected to Active →")
        add_to_active_treatment_button.setProperty("class", "mus1-secondary-button")
        add_to_active_treatment_button.clicked.connect(self.handle_add_to_active_treatments)
        available_treatment_buttons.addWidget(add_to_active_treatment_button)

        active_treatment_col, active_treatment_layout = self.create_form_section("Active Treatments:", None, is_subgroup=True)
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

        layout.addStretch(1)
        self.add_page(self.treatments_page, "Treatments")
        self.refresh_treatments_lists()

    def setup_body_parts_page(self):
        """Initialize the user interface for managing body parts."""
        self.bodyparts_page = QWidget()
        layout = QVBoxLayout(self.bodyparts_page)
        layout.setSpacing(self.SECTION_SPACING)

        extract_group, extract_layout = self.create_form_section("Extract Body Parts", layout)

        file_row = self.create_form_row(extract_layout)
        file_label = self.create_form_label("File Path:")

        self.csv_path_input = QLineEdit()
        self.csv_path_input.setPlaceholderText("Enter CSV/YAML file path")
        self.csv_path_input.setProperty("class", "mus1-text-input")

        browse_button = QPushButton("Browse...")
        browse_button.setProperty("class", "mus1-secondary-button")
        browse_button.clicked.connect(self.handle_browse_for_bodyparts_file)

        file_row.addWidget(file_label)
        file_row.addWidget(self.csv_path_input, 1)
        file_row.addWidget(browse_button)

        method_row = self.create_form_row(extract_layout)
        method_label = self.create_form_label("Method:")

        self.extraction_method_dropdown = QComboBox()
        self.extraction_method_dropdown.setObjectName("mus1-combo-box")
        self.extraction_method_dropdown.addItems(["BasicCSV", "DLC yaml"])
        self.extraction_method_dropdown.currentTextChanged.connect(self.update_extraction_method)
        self.extraction_method_dropdown.style().unpolish(self.extraction_method_dropdown)
        self.extraction_method_dropdown.style().polish(self.extraction_method_dropdown)

        extract_button = QPushButton("Extract")
        extract_button.setProperty("class", "mus1-primary-button")
        extract_button.clicked.connect(self.handle_extract_bodyparts)

        method_row.addWidget(method_label)
        method_row.addWidget(self.extraction_method_dropdown, 1)
        method_row.addWidget(extract_button)

        extracted_group, extracted_layout = self.create_form_section("Extracted Body Parts", layout)

        self.extracted_bodyparts_list = QListWidget()
        self.extracted_bodyparts_list.setProperty("class", "mus1-list-widget")
        self.extracted_bodyparts_list.setSelectionMode(QListWidget.ExtendedSelection)
        extracted_layout.addWidget(self.extracted_bodyparts_list)

        buttons_row = self.create_button_row(extracted_layout, add_stretch=False)

        master_button_all = QPushButton("Add All to Master")
        master_button_all.setProperty("class", "mus1-primary-button")
        master_button_all.clicked.connect(self.handle_add_all_bodyparts_to_master)

        master_button_selected = QPushButton("Add Selected to Master")
        master_button_selected.setProperty("class", "mus1-secondary-button")
        master_button_selected.clicked.connect(self.handle_add_selected_bodyparts_to_master)

        buttons_row.addWidget(master_button_all)
        buttons_row.addWidget(master_button_selected)
        buttons_row.addStretch(1)

        management_group, management_layout = self.create_form_section("Manage Body Parts", layout)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(self.SECTION_SPACING)
        management_layout.addLayout(columns_layout)

        master_column, master_layout = self.create_form_section("Master Body Parts", None, is_subgroup=True)

        self.all_bodyparts_list = QListWidget()
        self.all_bodyparts_list.setProperty("class", "mus1-list-widget")
        self.all_bodyparts_list.setSelectionMode(QListWidget.ExtendedSelection)
        master_layout.addWidget(self.all_bodyparts_list)

        master_buttons_row = self.create_button_row(master_layout)
        remove_from_master_button = QPushButton("Remove Selected from Master")
        remove_from_master_button.setProperty("class", "mus1-secondary-button")
        remove_from_master_button.clicked.connect(self.handle_remove_from_master)
        master_buttons_row.addWidget(remove_from_master_button)

        add_to_active_button = QPushButton("Add Selected to Active →")
        add_to_active_button.setProperty("class", "mus1-secondary-button")
        add_to_active_button.clicked.connect(self.handle_add_selected_bodyparts_to_active)
        master_buttons_row.addWidget(add_to_active_button)

        active_column, active_layout = self.create_form_section("Active Body Parts", None, is_subgroup=True)

        self.current_body_parts_list = QListWidget()
        self.current_body_parts_list.setProperty("class", "mus1-list-widget")
        self.current_body_parts_list.setSelectionMode(QListWidget.ExtendedSelection)
        active_layout.addWidget(self.current_body_parts_list)

        active_buttons_row = self.create_button_row(active_layout)
        remove_button = QPushButton("← Remove Selected from Active List")
        remove_button.setProperty("class", "mus1-secondary-button")
        remove_button.clicked.connect(self.handle_remove_active_bodyparts)
        active_buttons_row.addWidget(remove_button)

        columns_layout.addWidget(master_column, 1)
        columns_layout.addWidget(active_column, 1)

        layout.addStretch(1)
        self.add_page(self.bodyparts_page, "Bodyparts")
        
        # Refresh the lists initially
        self.refresh_body_parts_page()

    def update_extraction_method(self):
        """Update any UI elements based on the selected extraction method."""
        method = self.extraction_method_dropdown.currentText()
        if method == "DLC yaml":
            self.csv_path_input.setPlaceholderText("Enter YAML config file path")
        else:
            self.csv_path_input.setPlaceholderText("Enter CSV file path")
        
    def handle_browse_for_bodyparts_file(self):
        """Open a file dialog to select a CSV or YAML file."""
        method = self.extraction_method_dropdown.currentText()
        
        # Determine file filter based on selected method
        if method == "DLC yaml":
            file_filter = "YAML Files (*.yaml *.yml);;All Files (*)"
            dialog_title = "Select DLC Config File"
        else:
            file_filter = "CSV Files (*.csv);;All Files (*)"
            dialog_title = "Select Body Parts File"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            dialog_title,
            "",
            file_filter
        )
        if file_path:
            self.csv_path_input.setText(file_path)
        
    def handle_extract_bodyparts(self):
        """Extract body parts from the specified file using DataManager."""
        try:
            file_path = Path(self.csv_path_input.text().strip())
            method = self.extraction_method_dropdown.currentText()
            
            if method == "BasicCSV":
                extracted = self.window().data_manager.extract_bodyparts_from_dlc_csv(file_path)
            elif method == "DLC yaml":
                extracted = self.window().data_manager.extract_bodyparts_from_dlc_config(file_path)
            else:
                self.navigation_pane.add_log_message("Unknown extraction method.", "error")
                return

            self.extracted_bodyparts_list.clear()
            for bp in extracted:
                self.extracted_bodyparts_list.addItem(self.format_item(bp))
            self.navigation_pane.add_log_message(f"Extracted {len(extracted)} body parts.", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Extraction error: {e}", "error")

    def handle_add_all_bodyparts_to_master(self):
        """Add every extracted body part to the master list."""
        new_bodyparts = [self.extracted_bodyparts_list.item(i).text() 
                         for i in range(self.extracted_bodyparts_list.count())]
        state = self.state_manager.project_state
        current_master = []
        if state.project_metadata:
            current_master = [self.format_item(bp) for bp in state.project_metadata.master_body_parts]
        else:
            current_master = [str(bp) for bp in self.state_manager.global_settings.get("body_parts", [])]
        
        additions = [bp for bp in new_bodyparts if bp not in current_master]
        if additions:
            self.window().project_manager.update_master_body_parts(additions)
            self.navigation_pane.add_log_message(f"Added {len(additions)} body parts to master list.", "success")
        else:
            self.navigation_pane.add_log_message("No new body parts to add.", "info")
        self.refresh_body_parts_page()

    def handle_add_selected_bodyparts_to_master(self):
        """Add selected extracted body parts to the master list."""
        selected_items = self.extracted_bodyparts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for master list.", "warning")
            return
        selected = [item.text() for item in selected_items]
        state = self.state_manager.project_state
        if state.project_metadata:
            current_master = [self.format_item(bp) for bp in state.project_metadata.master_body_parts]
        else:
            current_master = [str(bp) for bp in self.state_manager.global_settings.get("body_parts", [])]
        
        new_master = current_master.copy()
        for bp in selected:
            if bp not in new_master:
                new_master.append(bp)
        
        if new_master != current_master:
            self.window().project_manager.update_master_body_parts(new_master)
            added_count = len(new_master) - len(current_master)
            self.navigation_pane.add_log_message(f"Added {added_count} selected body parts to master list.", "success")
        else:
            self.navigation_pane.add_log_message("No new body parts selected for master list.", "info")
        self.refresh_body_parts_page()

    def handle_remove_from_master(self):
        """Delete selected body parts from the master list."""
        selected_items = self.all_bodyparts_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No body parts selected for deletion from master list.", "warning")
            return
        selected = [item.text() for item in selected_items]
        state = self.state_manager.project_state
        if state.project_metadata:
            current_master = [self.format_item(bp) for bp in state.project_metadata.master_body_parts]
        else:
            current_master = [str(bp) for bp in self.state_manager.global_settings.get("body_parts", [])]
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
        self.window().project_manager.update_active_body_parts(updated)
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
        self.window().project_manager.update_active_body_parts(updated_active)
        
        state = self.state_manager.project_state
        if state.project_metadata:
            current_master = [self.format_item(bp) for bp in state.project_metadata.master_body_parts]
        else:
            current_master = [str(bp) for bp in self.state_manager.global_settings.get("body_parts", [])]
        
        new_master = current_master.copy()
        for bp in items_to_move:
            if bp not in new_master:
                new_master.append(bp)
        if new_master != current_master:
            self.window().project_manager.update_master_body_parts(new_master)
        
        self.navigation_pane.add_log_message(f"Moved {len(items_to_move)} body parts from active to master list.", "success")
        self.refresh_body_parts_page()

    def setup_objects_page(self):
        """Setup the Objects page with object list widgets."""
        self.objects_page = QWidget()
        layout = QVBoxLayout(self.objects_page)
        layout.setSpacing(self.SECTION_SPACING)

        objects_group, objects_layout = self.create_form_section("Objects Management", layout)

        add_row = self.create_form_row(objects_layout)
        new_object_label = self.create_form_label("New Object:")
        self.new_object_line_edit = QLineEdit()
        self.new_object_line_edit.setPlaceholderText("Enter new object name...")
        self.new_object_line_edit.setProperty("class", "mus1-text-input")
        add_button = QPushButton("Add Object")
        add_button.setProperty("class", "mus1-primary-button")
        add_button.clicked.connect(self.add_object_by_name)
        add_row.addWidget(new_object_label)
        add_row.addWidget(self.new_object_line_edit, 1)
        add_row.addWidget(add_button)

        lists_layout = QHBoxLayout()
        lists_layout.setSpacing(self.SECTION_SPACING)
        objects_layout.addLayout(lists_layout)

        # Available (Master) Objects Column
        available_column, available_layout = self.create_form_section("Available Objects:", None, is_subgroup=True)
        self.all_objects_list = QListWidget()
        self.all_objects_list.setProperty("class", "mus1-list-widget")
        self.all_objects_list.setSelectionMode(QListWidget.ExtendedSelection)
        available_layout.addWidget(self.all_objects_list)
        
        # Button row for available (master) objects
        available_button_row = self.create_button_row(available_layout, add_stretch=True)
        add_to_active_button = QPushButton("Add Selected to Active →")
        add_to_active_button.setProperty("class", "mus1-secondary-button")
        add_to_active_button.clicked.connect(self.move_objects_master_to_active)
        available_button_row.addWidget(add_to_active_button)
        remove_from_master_object_button = QPushButton("Remove Selected from Master")
        remove_from_master_object_button.setProperty("class", "mus1-secondary-button")
        remove_from_master_object_button.clicked.connect(self.delete_object_from_master)
        available_button_row.addWidget(remove_from_master_object_button)

        # Active Objects Column
        active_column, active_layout = self.create_form_section("Active Objects:", None, is_subgroup=True)
        self.current_objects_list = QListWidget()
        self.current_objects_list.setProperty("class", "mus1-list-widget")
        self.current_objects_list.setSelectionMode(QListWidget.ExtendedSelection)
        active_layout.addWidget(self.current_objects_list)
        
        # Button row for active objects with a "move back" button
        active_button_row = self.create_button_row(active_layout, add_stretch=True)
        remove_from_active_object_button = QPushButton("← Remove Selected from Active")
        remove_from_active_object_button.setProperty("class", "mus1-secondary-button")
        remove_from_active_object_button.clicked.connect(self.move_objects_active_to_master)
        active_button_row.addWidget(remove_from_active_object_button)

        lists_layout.addWidget(available_column, 1)
        lists_layout.addWidget(active_column, 1)

        layout.addStretch(1)
        self.add_page(self.objects_page, "Objects")
        self.refresh_objects_ui()

    def add_object_by_name(self):
        new_obj = self.new_object_line_edit.text().strip()
        if not new_obj:
            self.navigation_pane.add_log_message("No object name entered.", 'warning')
            return
        try:
            self.window().project_manager.add_tracked_object(new_obj)
            self.new_object_line_edit.clear()
            self.navigation_pane.add_log_message(f"Added new object: {new_obj}", 'success')
        except ValueError as e:
            self.navigation_pane.add_log_message(str(e), 'warning')
        self.refresh_objects_ui()

    def move_objects_master_to_active(self):
        selected_items = self.all_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected to move to Active.", 'warning')
            return
        master_list = self._get_master_objects()
        active_list = self._get_active_objects()
        existing_active = [self.format_item(obj) for obj in active_list]
        selected_names = [item.text() for item in selected_items]
        moving_objects = [obj for obj in master_list if self.format_item(obj) in selected_names]
        for obj in moving_objects:
            if self.format_item(obj) not in existing_active:
                active_list.append(obj)
        self.window().project_manager.update_tracked_objects(active_list, list_type="active")
        self.navigation_pane.add_log_message(f"Moved {len(moving_objects)} object(s) from Master to Active.", 'success')
        self.refresh_objects_ui()

    def move_objects_active_to_master(self):
        selected_items = self.current_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected to move back to Master.", 'warning')
            return
        active_list = self._get_active_objects()
        master_list = self._get_master_objects()
        selected_names = [item.text() for item in selected_items]
        active_list = [obj for obj in active_list if self.format_item(obj) not in selected_names]
        master_names = [self.format_item(obj) for obj in master_list]
        for item in selected_items:
            obj_name = item.text()
            if obj_name not in master_names:
                master_list.append(ObjectMetadata(name=obj_name))
        self.window().project_manager.update_tracked_objects(active_list, list_type="active")
        self.window().project_manager.update_tracked_objects(master_list, list_type="master")
        self.navigation_pane.add_log_message(f"Moved {len(selected_items)} object(s) from Active to Master.", 'success')
        self.refresh_objects_ui()

    def delete_object_from_master(self):
        selected_items = self.all_objects_list.selectedItems()
        if not selected_items:
            self.navigation_pane.add_log_message("No objects selected for deletion from Master.", 'warning')
            return
        selected_names = [item.text() for item in selected_items]
        master_list = self._get_master_objects()
        active_list = self._get_active_objects()
        master_list = [obj for obj in master_list if self.format_item(obj) not in selected_names]
        active_list = [obj for obj in active_list if self.format_item(obj) not in selected_names]
        self.window().project_manager.update_tracked_objects(master_list, list_type="master")
        self.window().project_manager.update_tracked_objects(active_list, list_type="active")
        self.navigation_pane.add_log_message(f"Deleted {len(selected_names)} object(s) from Master.", 'success')
        self.refresh_objects_ui()

    def refresh_objects_ui(self):
        # Clear list widgets if they exist
        if hasattr(self, 'all_objects_list'):
            self.all_objects_list.clear()
        if hasattr(self, 'current_objects_list'):
            self.current_objects_list.clear()
        # Retrieve sorted objects via state_manager for consistency
        master_list = self.state_manager.get_sorted_objects("master")
        active_list = self.state_manager.get_sorted_objects("active")
        for obj in master_list:
            self.all_objects_list.addItem(self.format_item(obj))
        for obj in active_list:
            self.current_objects_list.addItem(self.format_item(obj))

    def _get_active_objects(self):
        return self.state_manager.project_state.project_metadata.active_tracked_objects

    def _get_master_objects(self):
        return self.state_manager.project_state.project_metadata.master_tracked_objects

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