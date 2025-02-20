from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidget,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel, QDateTimeEdit, QCheckBox
)
from core.metadata import Sex
from gui.navigation_pane import NavigationPane  # Import the new NavigationPane
from PySide6.QtCore import QDateTime

class SubjectView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)

        # Left navigation (using NavigationPane)
        self.nav_pane = NavigationPane(self)
        self.nav_pane.add_button("Add Subject")
        self.nav_pane.add_button("View Subjects")
        self.nav_pane.connect_button_group()
        self.nav_pane.button_clicked.connect(self.on_nav_change)
        main_layout.addWidget(self.nav_pane)

        # Right area: a stacked widget with multiple sub-pages
        self.pages = QStackedWidget()

        # ----- Page: Add Subject -----
        self.page_add_subject = QWidget()
        add_layout = QVBoxLayout(self.page_add_subject)

        self.subject_group = QGroupBox("Add Subject")
        subject_form_layout = QFormLayout()
        self.subject_id_edit = QLineEdit()
        self.sex_combo = QComboBox()
        self.sex_combo.addItems([Sex.M.value, Sex.F.value, Sex.UNKNOWN.value])
        self.genotype_edit = QLineEdit()
        self.treatment_edit = QLineEdit()
        self.subject_notes_edit = QTextEdit()
        self.birth_date_edit = QDateTimeEdit()
        self.birth_date_edit.setCalendarPopup(True)
        self.birth_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.birth_date_edit.setDateTime(QDateTime.currentDateTime())
        self.in_training_set_checkbox = QCheckBox("In Training Set")
        self.add_subject_button = QPushButton("Add Subject")
        self.add_subject_button.clicked.connect(self.handle_add_subject)

        subject_form_layout.addRow("Subject ID:", self.subject_id_edit)
        subject_form_layout.addRow("Sex:", self.sex_combo)
        subject_form_layout.addRow("Genotype:", self.genotype_edit)
        subject_form_layout.addRow("Treatment:", self.treatment_edit)
        subject_form_layout.addRow("Notes:", self.subject_notes_edit)
        subject_form_layout.addRow("Birth Date:", self.birth_date_edit)
        subject_form_layout.addRow(self.in_training_set_checkbox)
        subject_form_layout.addWidget(self.add_subject_button)
        self.subject_group.setLayout(subject_form_layout)

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
        self.nav_pane.set_button_checked(0)

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
            return

        subject_id = self.subject_id_edit.text().strip()
        if not subject_id:
            # You might show a dialog or warning here
            return

        # 1) Verify the subject ID is unique
        existing_ids = [subj.id for subj in self.project_manager.get_sorted_subjects()]
        if subject_id in existing_ids:
            # You could show a dialog, e.g.: QMessageBox.warning(self, "Error", "Subject ID already exists.")
            print("Subject ID already exists!")  # placeholder
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

        # Switch to the "View Subjects" page to show the updated list
        self.nav_pane.set_button_checked(1)

    def refresh_subject_list_display(self):
        """Refresh the list of all subjects in the project."""
        if not self.project_manager:
            return
        self.subject_list_widget.clear()
        all_subjects = self.project_manager.get_sorted_subjects()
        for subj in all_subjects:
            self.subject_list_widget.addItem(subj.id)

    def refresh_experiment_list_by_subject_display(self):
        """Refresh the list widget displaying experiments by subject."""
        # Implementation pending
        pass