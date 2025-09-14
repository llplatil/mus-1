"""
GUI Setup Wizard - PySide6/QT-based setup wizard for MUS1.

This provides a graphical interface for the first-time MUS1 setup process,
reusing the same business logic as the CLI setup commands.

Integration points:
- Uses existing ConfigManager for persistence
- Integrates with existing ThemeManager for styling
- Does NOT duplicate logging, theme application, or other startup mechanisms
- Focuses solely on first-time user/lab/project setup
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path
import platform
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QFormLayout, QCheckBox, QPushButton, QProgressBar,
    QTextEdit, QMessageBox, QGroupBox, QRadioButton, QButtonGroup,
    QFileDialog, QComboBox, QSpinBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont, QPixmap, QIcon

from ..core.setup_service import (
    SetupService, UserProfileDTO, SharedStorageDTO, LabDTO, ColonyDTO,
    SetupWorkflowDTO, SetupStatusDTO, get_setup_service
)


# ===========================================
# WORKER THREAD FOR ASYNC SETUP
# ===========================================

class SetupWorker(QObject):
    """Worker thread for running setup operations asynchronously."""

    finished = Signal(dict)  # Emits result dict
    progress = Signal(str)   # Emits progress message
    error = Signal(str)      # Emits error message

    def __init__(self, workflow_dto: SetupWorkflowDTO):
        super().__init__()
        self.workflow_dto = workflow_dto
        self.setup_service = get_setup_service()

    def run(self):
        """Run the setup workflow in background thread."""
        try:
            self.progress.emit("Starting MUS1 setup...")

            # Step 1: User Profile
            if self.workflow_dto.user_profile:
                self.progress.emit("Setting up user profile...")
                result = self.setup_service.setup_user_profile(self.workflow_dto.user_profile)
                if not result["success"]:
                    self.error.emit(f"User profile setup failed: {result['message']}")
                    return

            # Step 2: Shared Storage
            if self.workflow_dto.shared_storage:
                self.progress.emit("Configuring shared storage...")
                result = self.setup_service.setup_shared_storage(self.workflow_dto.shared_storage)
                if not result["success"]:
                    self.error.emit(f"Shared storage setup failed: {result['message']}")
                    return

            # Step 3: Lab
            if self.workflow_dto.lab:
                self.progress.emit("Creating lab...")
                result = self.setup_service.create_lab(self.workflow_dto.lab)
                if not result["success"]:
                    self.error.emit(f"Lab creation failed: {result['message']}")
                    return

            # Step 4: Colony
            if self.workflow_dto.colony:
                self.progress.emit("Adding colony...")
                result = self.setup_service.add_colony_to_lab(self.workflow_dto.colony)
                if not result["success"]:
                    self.error.emit(f"Colony creation failed: {result['message']}")
                    return

            self.progress.emit("Setup completed successfully!")
            self.finished.emit({"success": True, "message": "MUS1 setup completed successfully!"})

        except Exception as e:
            self.error.emit(f"Setup failed: {str(e)}")


# ===========================================
# SETUP WIZARD PAGES
# ===========================================

class WelcomePage(QWizardPage):
    """Welcome page for the setup wizard."""

    def __init__(self):
        super().__init__()
        self.setTitle("Welcome to MUS1 Setup")
        self.setSubTitle("Let's get MUS1 configured for your research workflow")

        layout = QVBoxLayout()

        # Welcome message
        welcome_label = QLabel(
            "Welcome to the MUS1 Setup Wizard!\n\n"
            "This wizard will help you configure MUS1 for your research workflow. "
            "We'll set up your user profile, shared storage, labs, and projects.\n\n"
            "Click 'Next' to begin the setup process."
        )
        welcome_label.setWordWrap(True)
        layout.addWidget(welcome_label)

        # Check existing configuration
        self.setup_service = get_setup_service()
        if self.setup_service.is_user_configured():
            existing_profile = self.setup_service.get_user_profile()
            warning_label = QLabel(
                f"⚠️  MUS1 is already configured for user: {existing_profile.name}\n"
                "Continuing will allow you to modify the configuration."
            )
            warning_label.setStyleSheet("color: orange; font-weight: bold;")
            layout.addWidget(warning_label)

        self.setLayout(layout)


class UserProfilePage(QWizardPage):
    """Page for setting up user profile."""

    def __init__(self):
        super().__init__()
        self.setTitle("User Profile Setup")
        self.setSubTitle("Please provide your personal information")

        layout = QVBoxLayout()

        # Form layout for inputs
        form_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter your full name")
        form_layout.addRow("Full Name:", self.name_edit)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Enter your email address")
        form_layout.addRow("Email:", self.email_edit)

        self.organization_edit = QLineEdit()
        self.organization_edit.setPlaceholderText("Enter your organization/lab name")
        form_layout.addRow("Organization:", self.organization_edit)

        layout.addLayout(form_layout)

        # Platform-specific info
        if platform.system() == "Darwin":  # macOS
            info_label = QLabel(
                "📁 Default project location: ~/Documents/MUS1/Projects\n"
                "💾 Suggested shared storage: /Volumes/CuSSD3"
            )
        else:
            info_label = QLabel(
                "📁 Default project location: ~/mus1-projects\n"
                "💾 Suggested shared storage: ~/mus1-shared"
            )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info_label)

        self.setLayout(layout)

        # Register fields
        self.registerField("user_name*", self.name_edit)
        self.registerField("user_email*", self.email_edit)
        self.registerField("user_organization*", self.organization_edit)

    def validatePage(self) -> bool:
        """Validate user input."""
        name = self.name_edit.text().strip()
        email = self.email_edit.text().strip()
        organization = self.organization_edit.text().strip()

        if not name or len(name) < 2:
            QMessageBox.warning(self, "Validation Error", "Name must be at least 2 characters")
            return False

        if not email or "@" not in email:
            QMessageBox.warning(self, "Validation Error", "Please enter a valid email address")
            return False

        if not organization or len(organization) < 2:
            QMessageBox.warning(self, "Validation Error", "Organization must be at least 2 characters")
            return False

        return True


class SharedStoragePage(QWizardPage):
    """Page for configuring shared storage."""

    def __init__(self):
        super().__init__()
        self.setTitle("Shared Storage Setup")
        self.setSubTitle("Configure shared storage for collaborative projects")

        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "MUS1 can use shared storage to store projects that multiple users can access. "
            "This is useful for collaborative research environments.\n\n"
            "You can configure this later if you prefer."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Configure shared storage checkbox
        self.configure_checkbox = QCheckBox("Configure shared storage now")
        self.configure_checkbox.setChecked(True)
        layout.addWidget(self.configure_checkbox)

        # Shared storage configuration group
        self.storage_group = QGroupBox("Shared Storage Configuration")
        storage_layout = QVBoxLayout()

        # Path selection
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        if platform.system() == "Darwin":
            self.path_edit.setText("/Volumes/CuSSD3")
        else:
            self.path_edit.setText(str(Path.home() / "mus1-shared"))
        path_layout.addWidget(self.path_edit)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_path)
        path_layout.addWidget(self.browse_button)

        storage_layout.addLayout(path_layout)

        # Options
        self.create_checkbox = QCheckBox("Create directory if it doesn't exist")
        self.create_checkbox.setChecked(True)
        storage_layout.addWidget(self.create_checkbox)

        self.verify_checkbox = QCheckBox("Verify write permissions")
        self.verify_checkbox.setChecked(True)
        storage_layout.addWidget(self.verify_checkbox)

        self.storage_group.setLayout(storage_layout)
        layout.addWidget(self.storage_group)

        self.setLayout(layout)

        # Connect signals
        self.configure_checkbox.toggled.connect(self.toggle_storage_config)

    def toggle_storage_config(self, checked: bool):
        """Enable/disable storage configuration based on checkbox."""
        self.storage_group.setEnabled(checked)

    def browse_path(self):
        """Browse for shared storage path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Shared Storage Directory",
            self.path_edit.text()
        )
        if path:
            self.path_edit.setText(path)

    def validatePage(self) -> bool:
        """Validate shared storage configuration."""
        if not self.configure_checkbox.isChecked():
            return True  # Skip validation if not configuring

        path = Path(self.path_edit.text().strip())
        if not path:
            QMessageBox.warning(self, "Validation Error", "Please enter a valid path")
            return False

        return True


class LabSetupPage(QWizardPage):
    """Page for setting up lab configuration."""

    def __init__(self):
        super().__init__()
        self.setTitle("Lab Setup")
        self.setSubTitle("Create your first research lab")

        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "Labs in MUS1 represent research groups or laboratories. "
            "You can create multiple labs and organize your research projects within them.\n\n"
            "You can create labs later if you prefer to start with a simple project first."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Create lab checkbox
        self.create_checkbox = QCheckBox("Create a lab now")
        self.create_checkbox.setChecked(True)
        layout.addWidget(self.create_checkbox)

        # Lab configuration group
        self.lab_group = QGroupBox("Lab Configuration")
        lab_layout = QFormLayout()

        self.lab_id_edit = QLineEdit()
        self.lab_id_edit.setPlaceholderText("e.g., copperlab, neurology_lab")
        lab_layout.addRow("Lab ID:", self.lab_id_edit)

        self.lab_name_edit = QLineEdit()
        self.lab_name_edit.setPlaceholderText("Full lab name")
        lab_layout.addRow("Lab Name:", self.lab_name_edit)

        self.institution_edit = QLineEdit()
        self.institution_edit.setPlaceholderText("University or institution name")
        lab_layout.addRow("Institution:", self.institution_edit)

        self.pi_edit = QLineEdit()
        self.pi_edit.setPlaceholderText("Principal Investigator name")
        lab_layout.addRow("PI Name:", self.pi_edit)

        self.lab_group.setLayout(lab_layout)
        layout.addWidget(self.lab_group)

        # Connect signals
        self.create_checkbox.toggled.connect(self.toggle_lab_config)

        self.setLayout(layout)

    def toggle_lab_config(self, checked: bool):
        """Enable/disable lab configuration based on checkbox."""
        self.lab_group.setEnabled(checked)

    def validatePage(self) -> bool:
        """Validate lab configuration."""
        if not self.create_checkbox.isChecked():
            return True  # Skip validation if not creating lab

        lab_id = self.lab_id_edit.text().strip()
        lab_name = self.lab_name_edit.text().strip()

        if not lab_id or len(lab_id) < 3:
            QMessageBox.warning(self, "Validation Error", "Lab ID must be at least 3 characters")
            return False

        if not lab_name or len(lab_name) < 3:
            QMessageBox.warning(self, "Validation Error", "Lab name must be at least 3 characters")
            return False

        return True


class ConclusionPage(QWizardPage):
    """Final page showing setup summary and next steps."""

    def __init__(self):
        super().__init__()
        self.setTitle("Setup Complete")
        self.setSubTitle("MUS1 has been configured successfully!")

        layout = QVBoxLayout()

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)

        # Next steps
        next_steps_group = QGroupBox("Next Steps")
        next_steps_layout = QVBoxLayout()

        self.next_steps_text = QLabel()
        self.next_steps_text.setTextFormat(Qt.RichText)
        next_steps_layout.addWidget(self.next_steps_text)

        next_steps_group.setLayout(next_steps_layout)
        layout.addWidget(next_steps_group)

        self.setLayout(layout)

    def initializePage(self):
        """Initialize the conclusion page with setup results."""
        wizard = self.wizard()

        # Build summary
        summary = "<h3>🎉 MUS1 Setup Complete!</h3><br>"
        summary += "<table border='1' cellpadding='5'>"
        summary += "<tr><th>Component</th><th>Status</th><th>Details</th></tr>"

        # User Profile
        if hasattr(wizard, 'user_dto'):
            summary += f"<tr><td>User Profile</td><td>✓ Configured</td><td>Name: {wizard.user_dto.name}</td></tr>"
            summary += f"<tr><td>Email</td><td>✓ Configured</td><td>{wizard.user_dto.email}</td></tr>"
            summary += f"<tr><td>Organization</td><td>✓ Configured</td><td>{wizard.user_dto.organization}</td></tr>"

        # Shared Storage
        if hasattr(wizard, 'shared_dto') and wizard.shared_dto:
            summary += f"<tr><td>Shared Storage</td><td>✓ Configured</td><td>{wizard.shared_dto.path}</td></tr>"
        else:
            summary += "<tr><td>Shared Storage</td><td>⚠ Not configured</td><td>Run setup wizard later</td></tr>"

        # Lab
        if hasattr(wizard, 'lab_dto') and wizard.lab_dto:
            summary += f"<tr><td>Lab</td><td>✓ Created</td><td>{wizard.lab_dto.id}</td></tr>"
        else:
            summary += "<tr><td>Lab</td><td>⚠ Not created</td><td>Create lab manually</td></tr>"

        summary += "<tr><td>Projects</td><td>ℹ Ready</td><td>Create projects in GUI</td></tr>"
        summary += "</table>"

        self.summary_text.setHtml(summary)

        # Next steps
        next_steps = "<ul>"
        if not (hasattr(wizard, 'lab_dto') and wizard.lab_dto):
            next_steps += "<li>Create a lab in the GUI</li>"
        if not (hasattr(wizard, 'shared_dto') and wizard.shared_dto):
            next_steps += "<li>Configure shared storage in settings</li>"
        next_steps += "<li>Create your first project</li>"
        next_steps += "<li>Add subjects and experiments</li>"
        next_steps += "</ul>"

        self.next_steps_text.setText(next_steps)


# ===========================================
# MAIN SETUP WIZARD
# ===========================================

class MUS1SetupWizard(QWizard):
    """Main setup wizard for MUS1."""

    setup_completed = Signal(dict)  # Emits setup results

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("MUS1 Setup Wizard")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoCancelButtonOnLastPage, False)
        self.setOption(QWizard.HaveHelpButton, False)

        # Set window properties
        self.setMinimumSize(600, 500)

        # Initialize data
        self.user_dto = None
        self.shared_dto = None
        self.lab_dto = None

        # Add pages
        self.addPage(WelcomePage())
        self.addPage(UserProfilePage())
        self.addPage(SharedStoragePage())
        self.addPage(LabSetupPage())
        self.addPage(ConclusionPage())

        # Connect signals
        self.currentIdChanged.connect(self.on_page_changed)

    def on_page_changed(self, page_id: int):
        """Handle page changes."""
        if page_id == 4:  # Conclusion page
            self.run_setup()

    def run_setup(self):
        """Run the setup process."""
        # Collect data from pages
        self.collect_setup_data()

        # Create workflow DTO
        workflow_dto = SetupWorkflowDTO(
            user_profile=self.user_dto,
            shared_storage=self.shared_dto,
            lab=self.lab_dto
        )

        # Run setup in background thread
        self.worker = SetupWorker(workflow_dto)
        self.worker.finished.connect(self.on_setup_finished)
        self.worker.error.connect(self.on_setup_error)
        self.worker.progress.connect(self.on_setup_progress)

        # Show progress on conclusion page
        conclusion_page = self.page(4)
        progress_label = QLabel("Running setup...")
        conclusion_page.layout().addWidget(progress_label)

        # Start the worker
        self.worker.run()

    def collect_setup_data(self):
        """Collect setup data from wizard pages."""
        # User profile
        user_page = self.page(1)  # UserProfilePage
        self.user_dto = UserProfileDTO(
            name=user_page.field("user_name").strip(),
            email=user_page.field("user_email").strip(),
            organization=user_page.field("user_organization").strip(),
            default_projects_dir=Path.home() / "Documents" / "MUS1" / "Projects" if platform.system() == "Darwin"
                                 else Path.home() / "mus1-projects",
            default_shared_dir=Path("/Volumes/CuSSD3") if platform.system() == "Darwin"
                             else Path.home() / "mus1-shared"
        )

        # Shared storage
        storage_page = self.page(2)  # SharedStoragePage
        if storage_page.configure_checkbox.isChecked():
            self.shared_dto = SharedStorageDTO(
                path=Path(storage_page.path_edit.text().strip()),
                create_if_missing=storage_page.create_checkbox.isChecked(),
                verify_permissions=storage_page.verify_checkbox.isChecked()
            )

        # Lab
        lab_page = self.page(3)  # LabSetupPage
        if lab_page.create_checkbox.isChecked():
            self.lab_dto = LabDTO(
                id=lab_page.lab_id_edit.text().strip(),
                name=lab_page.lab_name_edit.text().strip(),
                institution=lab_page.institution_edit.text().strip() or "",
                pi_name=lab_page.pi_edit.text().strip() or "",
                description=f"Research lab at {lab_page.institution_edit.text().strip() or 'Unknown'}"
            )

    def on_setup_finished(self, result: dict):
        """Handle successful setup completion."""
        self.setup_completed.emit(result)
        QMessageBox.information(
            self, "Setup Complete",
            "MUS1 has been configured successfully!\n\n"
            "You can now create projects and start your research workflow."
        )

    def on_setup_error(self, error_msg: str):
        """Handle setup error."""
        QMessageBox.critical(self, "Setup Error", f"Setup failed:\n\n{error_msg}")

    def on_setup_progress(self, message: str):
        """Handle setup progress updates."""
        # Could update progress bar here
        print(f"Setup progress: {message}")


# ===========================================
# UTILITY FUNCTIONS
# ===========================================

def show_setup_wizard(parent=None) -> Optional[MUS1SetupWizard]:
    """Show the MUS1 setup wizard dialog."""
    wizard = MUS1SetupWizard(parent)
    result = wizard.exec()

    if result == QWizard.Accepted:
        return wizard
    return None


def check_setup_status() -> SetupStatusDTO:
    """Check current MUS1 setup status."""
    setup_service = get_setup_service()
    return setup_service.get_setup_status()