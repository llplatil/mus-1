from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QComboBox, QTextEdit, QPushButton
from core.metadata import Sex

class SubjectView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        message = QLabel("Subjects")
        layout.addWidget(message)

        # clean this up based on gui refactoring notes
        self.subject_group = QGroupBox("Add Subject")
        subject_layout = QFormLayout()
        self.subject_id_edit = QLineEdit()
        self.sex_combo = QComboBox()
        # Use enum values
        self.sex_combo.addItems([Sex.M.value, Sex.F.value, Sex.UNKNOWN.value])
        self.genotype_edit = QLineEdit()
        self.treatment_edit = QLineEdit()
        self.subject_notes_edit = QTextEdit()
        self.add_subject_button = QPushButton("Add Subject")
        self.add_subject_button.clicked.connect(self.handle_add_subject)
        
        subject_layout.addRow("Subject ID:", self.subject_id_edit)
        subject_layout.addRow("Sex:", self.sex_combo)
        subject_layout.addRow("Genotype:", self.genotype_edit)
        subject_layout.addRow("Treatment:", self.treatment_edit)
        subject_layout.addRow("Notes:", self.subject_notes_edit)
        subject_layout.addRow(self.add_subject_button)
        self.subject_group.setLayout(subject_layout)

    def handle_add_subject(self):
        """Handle adding a new subject."""
        if not hasattr(self, "project_manager") or self.project_manager is None:
            # Without a ProjectManager, we cannot save
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

        # 3) Call ProjectManager to add the mouse
        self.project_manager.add_mouse(
            mouse_id=subject_id,
            sex=sex_enum,
            genotype=genotype,
            treatment=treatment,
            notes=notes,
        )

        # 4) Refresh the subject list
        self.refresh_subject_list_display()
        # (Optional) self.project_manager.refresh_all_lists()

    def refresh_subject_list_display(self):
        """Refresh the list widget displaying subjects."""
        if not hasattr(self, 'project_manager') or self.project_manager is None:
            return
        self.subject_list_widget.clear()
        subjects = self.project_manager.get_sorted_subjects()
        for subject in subjects:
            self.subject_list_widget.addItem(subject.id)

    def refresh_experiment_list_by_subject_display(self):
        """Refresh the list widget displaying experiments by subject."""
        # Implementation pending
        pass