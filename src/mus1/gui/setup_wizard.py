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
from typing import Optional, Dict, Any
from pathlib import Path
import platform

from .qt import (
    QWizard, QWizardPage, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QFormLayout, QCheckBox, QPushButton,
    QTextEdit, QMessageBox, QGroupBox, QRadioButton,
    QComboBox, QListWidget, QListWidgetItem,
    Qt, Signal, QThread, QObject, QFileDialog
)

from ..core.setup_service import (
    UserProfileDTO, SharedStorageDTO,
    SetupWorkflowDTO, SetupStatusDTO, get_setup_service, MUS1RootLocationDTO
)
from ..core.metadata import LabDTO
from ..core.config_manager import resolve_mus1_root
from ..core.config_manager import init_config_manager
from ..core.utils.ssh_config import list_ssh_aliases


# ===========================================
# WORKER THREAD FOR ASYNC SETUP
# ===========================================

class SetupWorker(QObject):
    """Worker thread for running setup operations asynchronously."""

    finished = Signal(dict)  # Emits result dict
    progress = Signal(str)   # Emits progress message
    error = Signal(str)      # Emits error message
    warning = Signal(str)    # Emits warning message

    def __init__(self, workflow_dto: SetupWorkflowDTO):
        super().__init__()
        self.workflow_dto = workflow_dto
        self.setup_service = get_setup_service()

    def run(self):
        """Run the setup workflow in background thread with proper state management."""
        try:
            self.progress.emit("Starting MUS1 setup...")

            # Step 1: Handle MUS1 root location FIRST (critical for config re-initialization)
            if self.workflow_dto.mus1_root_location:
                self.progress.emit("Setting up MUS1 root location...")
                root_result = self.setup_service.setup_mus1_root_location(self.workflow_dto.mus1_root_location)

                if not root_result["success"]:
                    self.error.emit(f"MUS1 root setup failed: {root_result['message']}")
                    return

                # CRITICAL: Re-initialize ConfigManager immediately after root setup succeeds
                config_db_path = self.workflow_dto.mus1_root_location.path / "config" / "config.db"
                init_config_manager(config_db_path)

                # Re-create SetupService so it uses the new ConfigManager
                self.setup_service = get_setup_service()

                self.progress.emit("MUS1 root location configured successfully")

                # Emit any warnings about root pointer changes
                if "warnings" in root_result:
                    for warning in root_result["warnings"]:
                        self.warning.emit(warning)

            # Step 2: Continue with unified workflow for remaining steps
            result = self._run_remaining_workflow()

            if result["success"]:
                self.progress.emit("Setup completed successfully!")
                self.finished.emit(result)
            else:
                error_msg = "; ".join(result.get("errors", ["Unknown error"]))
                self.error.emit(f"Setup failed: {error_msg}")

        except Exception as e:
            self.error.emit(f"Setup failed: {str(e)}")

    def _run_remaining_workflow(self) -> Dict[str, Any]:
        """Run the remaining setup steps (user profile, storage, lab) using unified workflow."""
        # Create a workflow DTO without the MUS1 root (already handled)
        remaining_workflow = SetupWorkflowDTO(
            mus1_root_location=None,  # Already handled above
            user_profile=self.workflow_dto.user_profile,
            shared_storage=self.workflow_dto.shared_storage,
            lab=self.workflow_dto.lab,
            colony=self.workflow_dto.colony
        )

        return self.setup_service.run_setup_workflow(remaining_workflow)


# ===========================================
# SETUP WIZARD PAGES
# ===========================================

class SimplifiedWelcomePage(QWizardPage):
    """Simplified welcome page for the setup wizard."""

    def __init__(self):
        super().__init__()
        self.setTitle("Welcome to MUS1 Setup")
        self.setSubTitle("Get started with your research workflow")

        layout = QVBoxLayout()

        # Welcome message
        welcome_label = QLabel(
            "Welcome to MUS1!\n\n"
            "Choose how you'd like to organize your research:\n\n"
            "• **Local Projects**: Work with projects on your computer only\n"
            "• **Lab Collaboration**: Join or create a lab for team collaboration\n\n"
            "You can change this later in settings."
        )
        welcome_label.setWordWrap(True)
        layout.addWidget(welcome_label)

        # Check existing configuration
        self.setup_service = get_setup_service()
        if self.setup_service.is_user_configured():
            existing_profile = self.setup_service.get_user_profile()
            info_label = QLabel(
                f"ℹ️  Updating configuration for: {existing_profile.name}"
            )
            info_label.setStyleSheet("color: blue; font-weight: bold;")
            layout.addWidget(info_label)

        self.setLayout(layout)


class LabChoicePage(QWizardPage):
    """Choose between local-only or lab collaboration."""

    def __init__(self):
        super().__init__()
        self.setTitle("Research Organization")
        self.setSubTitle("How would you like to organize your research?")

        layout = QVBoxLayout()

        # Choice description
        desc_label = QLabel(
            "Choose how you'd like to work with MUS1:"
        )
        layout.addWidget(desc_label)

        # Radio buttons for choice
        self.local_radio = QRadioButton("Local Projects Only")
        self.local_radio.setChecked(True)  # Default choice
        self.lab_radio = QRadioButton("Join or Create a Lab")

        local_desc = QLabel(
            "Work with projects stored locally on your computer.\n"
            "Good for individual researchers or small projects."
        )
        local_desc.setStyleSheet("color: gray; margin-left: 20px;")

        lab_desc = QLabel(
            "Collaborate with a research team using shared storage.\n"
            "Access shared projects and collaborate with lab members."
        )
        lab_desc.setStyleSheet("color: gray; margin-left: 20px;")

        layout.addWidget(self.local_radio)
        layout.addWidget(local_desc)
        layout.addWidget(self.lab_radio)
        layout.addWidget(lab_desc)

        # Existing labs info
        self.setup_service = get_setup_service()
        existing_labs = self.setup_service.get_labs()
        if existing_labs:
            labs_info = QLabel(
                f"ℹ️  {len(existing_labs)} existing lab(s) available to join"
            )
            labs_info.setStyleSheet("color: blue; margin-top: 10px;")
            layout.addWidget(labs_info)

        layout.addStretch()
        self.setLayout(layout)

    def nextId(self):
        """Determine next page based on choice."""
        if self.lab_radio.isChecked():
            return 2  # Lab config page
        else:
            return 3  # Skip to conclusion (local-only)


class LabConfigPage(QWizardPage):
    """Configure lab settings if creating/joining a lab."""

    def __init__(self):
        super().__init__()
        self.setTitle("Lab Configuration")
        self.setSubTitle("Set up your research lab")

        layout = QVBoxLayout()

        # Lab choice: create new or join existing
        choice_group = QGroupBox("Lab Setup")
        choice_layout = QVBoxLayout(choice_group)

        self.create_radio = QRadioButton("Create New Lab")
        self.create_radio.setChecked(True)
        self.join_radio = QRadioButton("Join Existing Lab")

        choice_layout.addWidget(self.create_radio)
        choice_layout.addWidget(self.join_radio)

        # Show existing labs if join is selected
        self.existing_labs_combo = QComboBox()
        self.existing_labs_combo.setVisible(False)
        choice_layout.addWidget(self.existing_labs_combo)

        # New lab fields
        self.new_lab_group = QGroupBox("New Lab Details")
        new_lab_layout = QFormLayout(self.new_lab_group)

        self.lab_name_edit = QLineEdit()
        self.lab_name_edit.setPlaceholderText("e.g., Smith Lab")
        new_lab_layout.addRow("Lab Name:", self.lab_name_edit)

        self.institution_edit = QLineEdit()
        self.institution_edit.setPlaceholderText("e.g., University of Example")
        new_lab_layout.addRow("Institution:", self.institution_edit)

        self.pi_edit = QLineEdit()
        self.pi_edit.setPlaceholderText("e.g., Dr. Jane Smith")
        new_lab_layout.addRow("Principal Investigator:", self.pi_edit)

        # Sharing setup
        sharing_group = QGroupBox("Shared Storage (Optional)")
        sharing_layout = QVBoxLayout(sharing_group)

        self.enable_sharing_check = QCheckBox("Enable lab sharing")
        self.enable_sharing_check.setToolTip("Allow lab members to access shared projects")
        sharing_layout.addWidget(self.enable_sharing_check)

        sharing_path_layout = QHBoxLayout()
        self.storage_path_edit = QLineEdit()
        self.storage_path_edit.setPlaceholderText("Path to shared storage directory")
        self.storage_path_edit.setEnabled(False)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_storage_path)

        sharing_path_layout.addWidget(self.storage_path_edit)
        sharing_path_layout.addWidget(browse_button)
        sharing_layout.addLayout(sharing_path_layout)

        layout.addWidget(choice_group)
        layout.addWidget(self.new_lab_group)
        layout.addWidget(sharing_group)
        layout.addStretch()

        # Connect signals
        self.create_radio.toggled.connect(self.on_lab_choice_changed)
        self.join_radio.toggled.connect(self.on_lab_choice_changed)
        self.enable_sharing_check.toggled.connect(self.storage_path_edit.setEnabled)

        self.setLayout(layout)

        # Initialize
        self.populate_existing_labs()
        self.on_lab_choice_changed()

    def populate_existing_labs(self):
        """Populate dropdown with existing labs."""
        self.setup_service = get_setup_service()
        labs = self.setup_service.get_labs()
        self.existing_labs_combo.clear()
        for lab_id, lab_data in labs.items():
            display_name = f"{lab_data.get('name', 'Unknown')} ({lab_data.get('institution', 'No institution')})"
            self.existing_labs_combo.addItem(display_name, lab_id)

    def on_lab_choice_changed(self):
        """Handle create vs join radio button changes."""
        is_create = self.create_radio.isChecked()
        self.new_lab_group.setVisible(is_create)
        self.existing_labs_combo.setVisible(not is_create)

    def browse_storage_path(self):
        """Browse for storage path."""
        path = QFileDialog.getExistingDirectory(self, "Select Shared Storage Directory")
        if path:
            self.storage_path_edit.setText(path)

    def validatePage(self):
        """Validate the lab configuration."""
        if self.create_radio.isChecked():
            if not self.lab_name_edit.text().strip():
                QMessageBox.warning(self, "Validation Error", "Lab name is required.")
                return False
        elif self.join_radio.isChecked():
            if self.existing_labs_combo.currentData() is None:
                QMessageBox.warning(self, "Validation Error", "Please select a lab to join.")
                return False
        return True


class SimplifiedConclusionPage(QWizardPage):
    """Final page showing setup summary."""

    def __init__(self):
        super().__init__()
        self.setTitle("Setup Complete")
        self.setSubTitle("MUS1 is ready to use!")

        layout = QVBoxLayout()

        self.summary_label = QLabel("Setup completed successfully!")
        self.summary_label.setStyleSheet("font-size: 14px; font-weight: bold; color: green;")
        layout.addWidget(self.summary_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        layout.addWidget(self.details_text)

        layout.addStretch()
        self.setLayout(layout)

    def initializePage(self):
        """Initialize the conclusion page with setup summary."""
        wizard = self.wizard()
        if hasattr(wizard, 'user_dto') and wizard.user_dto:
            summary = f"Welcome, {wizard.user_dto.name}!\n\n"
            if wizard.lab_choice == "lab":
                if wizard.lab_dto:
                    summary += f"Created lab: {wizard.lab_dto.name}\n"
                    if getattr(wizard, '_lab_sharing_enabled', False):
                        summary += "Lab sharing enabled\n"
                else:
                    summary += "Joined existing lab\n"
                summary += "\nYou can now create local projects or collaborate with lab members."
            else:
                summary += "Local-only setup\n\nYou can create local projects and manage your research data."
        else:
            summary = "Setup completed successfully!"

        self.details_text.setPlainText(summary)


# ===========================================
# UTILITY FUNCTIONS
# ===========================================

def show_setup_wizard(parent=None) -> Optional[SimplifiedSetupWizard]:
    """Show the simplified MUS1 setup wizard dialog."""
    try:
        wizard = SimplifiedSetupWizard(parent)
        result = wizard.exec()

        if result == QWizard.DialogCode.Accepted:
            return wizard
        return None
    except Exception as e:
        QMessageBox.critical(
            parent, "Setup Error",
            f"Failed to start setup wizard:\n\n{str(e)}"
        )
        return None
