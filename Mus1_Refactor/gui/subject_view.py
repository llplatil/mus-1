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

        # Setup navigation for this view with two pages:
        # "Add Subject" for adding new subjects and
        # "Subjects Overview" for viewing subjects using a tree display.
        self.setup_navigation(["Add Subject", "Subjects Overview"])
        
        # Create both pages
        self.setup_add_subject_page()
        self.setup_view_subjects_page()
        
        # Set default selection to the "Add Subject" page
        self.change_page(0)

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
        
        # NEW: Add the embedded subject list group with remove functionality
        subject_list_group = QGroupBox("Subjects List")
        subject_list_group.setProperty("class", "mus1-input-group")
        subject_list_layout = QVBoxLayout(subject_list_group)
        subject_list_layout.setContentsMargins(10, 10, 10, 10)
        subject_list_layout.setSpacing(10)

        self.subjects_list = QListWidget()
        self.subjects_list.setProperty("class", "mus1-list-widget")
        subject_list_layout.addWidget(self.subjects_list)

        # Add a button row for removing the selected subject
        remove_button_layout = QHBoxLayout()
        remove_button_layout.addStretch(1)
        self.remove_subject_button = QPushButton("Remove Selected Subject")
        self.remove_subject_button.setProperty("class", "mus1-secondary-button")
        self.remove_subject_button.clicked.connect(self.handle_remove_selected_subject)
        remove_button_layout.addWidget(self.remove_subject_button)
        subject_list_layout.addLayout(remove_button_layout)

        add_layout.addWidget(subject_list_group)
        
        add_layout.addStretch(1)
        
        # Add the combined page to the stacked widget with title "Subjects"
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

        genotype = self.genotype_edit.text().strip()
        treatment = self.treatment_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()
        birth_date = self.birthdate_edit.dateTime().toPython()
        in_training_set = self.training_set_check.isChecked()

        # Add the subject via ProjectManager
        self.project_manager.add_subject(
            subject_id=subject_id,
            sex=sex_enum,
            genotype=genotype,
            treatment=treatment,
            notes=notes,
            birth_date=birth_date,
            in_training_set=in_training_set,
        )

        # Clear the input fields after successful addition
        self.subject_id_edit.clear()
        self.genotype_edit.clear()
        self.treatment_edit.clear()
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
        self.subjects_list.clear()
        all_subjects = self.project_manager.state_manager.get_sorted_subjects()
        
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
        Override change_page to refresh data when switching between pages.
        """
        super().change_page(index)
        
        if index == 0:
            self.refresh_subject_list_display()
        elif index == 1:
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
        self.metadata_tree = MetadataTreeView(self.page_overview)
        overview_layout.addWidget(self.metadata_tree)
        
        # Optionally add a refresh button to allow manual updates
        refresh_button = QPushButton("Refresh Overview")
        refresh_button.setProperty("class", "mus1-secondary-button")
        refresh_button.clicked.connect(self.refresh_overview)
        overview_layout.addWidget(refresh_button)
        
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