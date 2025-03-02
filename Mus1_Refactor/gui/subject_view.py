from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidget,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel, QDateTimeEdit, QCheckBox
)
from core.metadata import Sex
from gui.navigation_pane import NavigationPane  
from PySide6.QtCore import QDateTime
from core.logging_bus import LoggingEventBus

class SubjectView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)
        
        # Get the LoggingEventBus singleton
        self.log_bus = LoggingEventBus.get_instance()

        # Left navigation (using NavigationPane)
        self.navigation_pane = NavigationPane(self)
        self.navigation_pane.add_button("Add Subject")
        self.navigation_pane.add_button("View Subjects")
        self.navigation_pane.connect_button_group()
        self.navigation_pane.button_clicked.connect(self.on_nav_change)
        main_layout.addWidget(self.navigation_pane)
        
        # Log initialization
        self.log_bus.log("SubjectView initialized", "info", "SubjectView")

        # Right area: a stacked widget with multiple sub-pages
        self.pages = QStackedWidget()

        # ----- Page: Add Subject -----
        self.page_add_subject = QWidget()
        add_layout = QVBoxLayout(self.page_add_subject)

        self.subject_group = QGroupBox("Add Subject")
        
        # Switch to a horizontal layout with two columns to make better use of space
        subject_layout = QHBoxLayout()
        
        # Left column
        left_form_layout = QFormLayout()
        self.subject_id_edit = QLineEdit()
        self.sex_combo = QComboBox()
        self.sex_combo.addItems([Sex.M.value, Sex.F.value, Sex.UNKNOWN.value])
        self.genotype_edit = QLineEdit()
        self.treatment_edit = QLineEdit()
        
        left_form_layout.addRow("Subject ID:", self.subject_id_edit)
        left_form_layout.addRow("Sex:", self.sex_combo)
        left_form_layout.addRow("Genotype:", self.genotype_edit)
        left_form_layout.addRow("Treatment:", self.treatment_edit)
        
        # Right column
        right_form_layout = QFormLayout()
        self.subject_notes_edit = QTextEdit()
        self.subject_notes_edit.setMaximumHeight(80)  # Limit height to save space
        self.birth_date_edit = QDateTimeEdit()
        self.birth_date_edit.setCalendarPopup(True)
        self.birth_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.birth_date_edit.setDateTime(QDateTime.currentDateTime())
        self.in_training_set_checkbox = QCheckBox("In Training Set")
        
        right_form_layout.addRow("Notes:", self.subject_notes_edit)
        right_form_layout.addRow("Birth Date:", self.birth_date_edit)
        right_form_layout.addRow(self.in_training_set_checkbox)
        
        # Add columns to the layout
        left_column = QWidget()
        left_column.setLayout(left_form_layout)
        right_column = QWidget()
        right_column.setLayout(right_form_layout)
        
        subject_layout.addWidget(left_column)
        subject_layout.addWidget(right_column)
        
        # Add the button and notification label below the columns
        button_layout = QFormLayout()
        self.add_subject_button = QPushButton("Add Subject")
        self.add_subject_button.clicked.connect(self.handle_add_subject)
        self.subject_notification_label = QLabel("")
        
        button_layout.addWidget(self.add_subject_button)
        button_layout.addRow("", self.subject_notification_label)
        
        # Set up the overall layout
        main_subject_layout = QVBoxLayout()
        main_subject_layout.addLayout(subject_layout)
        main_subject_layout.addLayout(button_layout)
        
        self.subject_group.setLayout(main_subject_layout)
        add_layout.addWidget(self.subject_group)
        self.page_add_subject.setLayout(add_layout)
        self.pages.addWidget(self.page_add_subject)

        # ----- Page: View Subjects -----
        self.page_view_subjects = QWidget()
        vs_layout = QVBoxLayout(self.page_view_subjects)

        self.subject_list_label = QLabel("All Subjects:")
        vs_layout.addWidget(self.subject_list_label)

        # For example, a list widget to show all subject IDs
        self.subject_list_widget = QListWidget()
        vs_layout.addWidget(self.subject_list_widget)

        self.page_view_subjects.setLayout(vs_layout)
        self.pages.addWidget(self.page_view_subjects)

        # Finally, add the stacked widget to the layout
        main_layout.addWidget(self.pages)
        self.setLayout(main_layout)

        # If you want to default to the first page:
        self.navigation_pane.set_button_checked(0)

        # (Optionally) we might have a reference to project_manager set later
        self.project_manager = None

    def on_nav_change(self, index: int):
        """Switch between Add Subject vs. View Subjects pages."""
        self.pages.setCurrentIndex(index)
        if index == 1:
            # If user navigates to "View Subjects," refresh the list
            self.refresh_subject_list_display()

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
        notes = self.subject_notes_edit.toPlainText().strip()
        birth_date = self.birth_date_edit.dateTime().toPython()
        in_training_set = self.in_training_set_checkbox.isChecked()

        # Retrieve additional fields from UI
        birth_date = self.birth_date_edit.dateTime().toPython()
        in_training_set = self.in_training_set_checkbox.isChecked()

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
        self.subject_notes_edit.clear()
        self.birth_date_edit.setDateTime(QDateTime.currentDateTime())
        self.in_training_set_checkbox.setChecked(False)

        # Refresh the displayed subject list based on current global sort preference
        self.refresh_subject_list_display()
        
        # Log successful addition
        self.log_bus.log(f"Subject '{subject_id}' added successfully", "success", "SubjectView")

        # Show success notification
        self.subject_notification_label.setText("Subject added successfully!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.subject_notification_label.setText(""))

        # Switch to the "View Subjects" page to show the updated list
        self.navigation_pane.set_button_checked(1)

    def refresh_subject_list_display(self):
        """Refresh the list of all subjects in the project with full metadata details."""
        if not self.project_manager:
            return
        self.subject_list_widget.clear()
        all_subjects = self.project_manager.get_sorted_subjects()
        
        # Log the refresh activity
        self.log_bus.log(f"Refreshing subject list: {len(all_subjects)} subjects found", "info", "SubjectView")
        
        for subj in all_subjects:
            birth_str = subj.birth_date.strftime('%Y-%m-%d %H:%M:%S') if subj.birth_date else 'N/A'
            details = (f"ID: {subj.id} | Sex: {subj.sex.value} | Genotype: {subj.genotype or 'N/A'} "
                       f"| Treatment: {subj.treatment or 'N/A'} | Birth: {birth_str} "
                       f"| Training: {subj.in_training_set}")
            self.subject_list_widget.addItem(details)

    def refresh_experiment_list_by_subject_display(self):
        """Refresh the list widget displaying experiments by subject."""
        # Implementation pending
        pass

    def set_project_manager(self, project_manager):
        """Assign the project_manager and subscribe for automatic refresh from state changes."""
        self.project_manager = project_manager
        if hasattr(project_manager.state_manager, 'subscribe'):
            project_manager.state_manager.subscribe(self.refresh_subject_list_display)
        self.refresh_subject_list_display()