from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidget,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel, QDateTimeEdit, QCheckBox
)
from core.metadata import Sex
from gui.navigation_pane import NavigationPane  
from gui.base_view import BaseView
from PySide6.QtCore import QDateTime
from core.logging_bus import LoggingEventBus

class SubjectView(BaseView):
    def __init__(self, parent=None):
        # Initialize with base view and specific name
        super().__init__(parent, view_name="subject")
        
        # Log initialization
        self.log_bus = LoggingEventBus.get_instance()
        self.log_bus.log("SubjectView initialized", "info", "SubjectView")

        # Setup navigation for this view
        self.setup_navigation([
            "Add Subject",
            "View Subjects"
        ])
        
        # Create pages
        self.setup_add_subject_page()
        self.setup_view_subjects_page()
        
        # Set default selection
        self.change_page(0)

        # Insert the following line:
        self.project_manager = self.window().project_manager
        
    def setup_add_subject_page(self):
        """Setup the Add Subject page."""
        # Create the page widget
        self.page_add_subject = QWidget()
        add_layout = QVBoxLayout(self.page_add_subject)
        add_layout.setContentsMargins(10, 10, 10, 10)
        add_layout.setSpacing(10)

        self.subject_group = QGroupBox("Add Subject")
        self.subject_group.setProperty("class", "mus1-input-group")
        
        # Switch to a horizontal layout with two columns to make better use of space
        subject_layout = QHBoxLayout(self.subject_group)
        
        # Left column
        left_form_layout = QFormLayout()
        self.subject_id_edit = QLineEdit()
        self.subject_id_edit.setProperty("class", "mus1-text-input")
        
        self.sex_combo = QComboBox()
        self.sex_combo.setProperty("class", "mus1-combo-box")
        self.sex_combo.addItems([Sex.M.value, Sex.F.value, Sex.UNKNOWN.value])
        
        self.genotype_edit = QLineEdit()
        self.genotype_edit.setProperty("class", "mus1-text-input")
        
        self.treatment_edit = QLineEdit()
        self.treatment_edit.setProperty("class", "mus1-text-input")
        
        left_form_layout.addRow("Subject ID:", self.subject_id_edit)
        left_form_layout.addRow("Sex:", self.sex_combo)
        left_form_layout.addRow("Genotype:", self.genotype_edit)
        left_form_layout.addRow("Treatment:", self.treatment_edit)
        
        # Right column
        right_form_layout = QFormLayout()
        self.birthdate_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.birthdate_edit.setCalendarPopup(True)
        self.birthdate_edit.setDisplayFormat("yyyy-MM-dd")
        
        self.training_set_check = QCheckBox()
        
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setProperty("class", "mus1-text-input")
        
        right_form_layout.addRow("Birth Date:", self.birthdate_edit)
        right_form_layout.addRow("Training Set:", self.training_set_check)
        right_form_layout.addRow("Notes:", self.notes_edit)
        
        # Add layouts to main subject layout
        subject_layout.addLayout(left_form_layout)
        subject_layout.addLayout(right_form_layout)
        
        # Add the subject group to the page layout
        add_layout.addWidget(self.subject_group)
        
        # Add subject button
        self.add_subject_button = QPushButton("Add Subject")
        self.add_subject_button.setProperty("class", "mus1-primary-button")
        self.add_subject_button.clicked.connect(self.handle_add_subject)
        
        # Add button at the bottom
        add_layout.addWidget(self.add_subject_button)
        
        # Add a stretch to push content to the top
        add_layout.addStretch(1)
        
        # Add the page to the stacked widget
        self.add_page(self.page_add_subject, "Add Subject")
    
    def setup_view_subjects_page(self):
        """Setup the View Subjects page."""
        # Create the page widget
        self.page_view_subjects = QWidget()
        view_subjects_layout = QVBoxLayout(self.page_view_subjects)
        view_subjects_layout.setContentsMargins(10, 10, 10, 10)
        view_subjects_layout.setSpacing(10)
        
        # Subjects list
        self.subjects_list = QListWidget()
        view_subjects_layout.addWidget(QLabel("Subjects:"))
        view_subjects_layout.addWidget(self.subjects_list)
        
        # Add the page to the stacked widget
        self.add_page(self.page_view_subjects, "View Subjects")
        
    def handle_add_subject(self):
        """Handle the logic for adding a new subject, as before."""
        if not self.project_manager:
            self.log_bus.log("Error: No ProjectManager is set", "error", "SubjectView")
            return

        subject_id = self.subject_id_edit.text().strip()
        if not subject_id:
            # You might show a dialog or warning here
            self.log_bus.log("Error: Subject ID cannot be empty", "error", "SubjectView")
            return

        # 1) Verify the subject ID is unique
        existing_ids = [subj.id for subj in self.project_manager.state_manager.get_sorted_list("subjects")]
        if subject_id in existing_ids:
            # You could show a dialog, e.g.: QMessageBox.warning(self, "Error", "Subject ID already exists.")
            print("Subject ID already exists!")  # placeholder
            self.log_bus.log(f"Error: Subject ID '{subject_id}' already exists", "error", "SubjectView")
            return

        # 2) Retrieve the sex enum from the combo
        sex_value = self.sex_combo.currentText()
        if sex_value == Sex.M.value:
            sex_enum = Sex.M
        elif sex_value == Sex.F.value:
            sex_enum = Sex.F
        else:
            sex_enum = Sex.UNKNOWN

        genotype = self.genotype_edit.text().strip()
        treatment = self.treatment_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()
        birth_date = self.birthdate_edit.dateTime().toPython()
        in_training_set = self.training_set_check.isChecked()

        # Call ProjectManager to add the mouse with additional metadata
        self.project_manager.add_mouse(
            mouse_id=subject_id,
            sex=sex_enum,
            genotype=genotype,
            treatment=treatment,
            notes=notes,
            birth_date=birth_date,
            in_training_set=in_training_set,
        )

        # Clear the input fields for new entry after successful addition
        self.subject_id_edit.clear()
        self.genotype_edit.clear()
        self.treatment_edit.clear()
        self.notes_edit.clear()
        self.birthdate_edit.setDateTime(QDateTime.currentDateTime())
        self.training_set_check.setChecked(False)

        # Refresh the displayed subject list based on current global sort preference
        self.refresh_subject_list_display()
        
        # Log successful addition
        self.log_bus.log(f"Subject '{subject_id}' added successfully", "success", "SubjectView")

        # Show success notification
        self.subject_notification_label.setText("Subject added successfully!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.subject_notification_label.setText(""))

        # Switch to the "View Subjects" page to show the updated list
        self.change_page(1)

    def refresh_subject_list_display(self):
        """Refresh the list of all subjects in the project with full metadata details."""
        if not self.project_manager:
            return
        self.subjects_list.clear()
        all_subjects = self.project_manager.state_manager.get_sorted_list("subjects")
        
        # Log the refresh activity
        self.log_bus.log(f"Refreshing subject list: {len(all_subjects)} subjects found", "info", "SubjectView")
        
        for subj in all_subjects:
            birth_str = subj.birth_date.strftime('%Y-%m-%d %H:%M:%S') if subj.birth_date else 'N/A'
            details = (f"ID: {subj.id} | Sex: {subj.sex.value} | Genotype: {subj.genotype or 'N/A'} "
                       f"| Treatment: {subj.treatment or 'N/A'} | Birth: {birth_str} "
                       f"| Training: {subj.in_training_set}")
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
        Override change_page to refresh data when switching to the View Subjects page.
        """
        super().change_page(index)
        
        # If switching to View Subjects page, refresh the subject list
        if index == 1:
            self.refresh_subject_list_display()