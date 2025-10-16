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
    Qt, Signal, QThread, QObject, QFileDialog
)

from ..core.setup_service import (
    UserProfileDTO, SharedStorageDTO,
    SetupWorkflowDTO, SetupStatusDTO, get_setup_service, MUS1RootLocationDTO
)
from ..core.metadata import LabDTO
from ..core.config_manager import resolve_mus1_root
from ..core.config_manager import init_config_manager


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

        # Also check for existing root pointer that might be affected
        from ..core.config_manager import get_root_pointer_info
        root_pointer_info = get_root_pointer_info()
        if root_pointer_info["exists"]:
            root_warning_label = QLabel()
            if root_pointer_info["valid"]:
                root_warning_label.setText(
                    f"⚠️  Existing root pointer will be overwritten: {root_pointer_info['target']}"
                )
            else:
                root_warning_label.setText(
                    f"⚠️  Invalid root pointer will be cleaned up: {root_pointer_info['target']}"
                )
            root_warning_label.setStyleSheet("color: orange; font-weight: bold;")
            layout.addWidget(root_warning_label)

        self.setLayout(layout)


class MUS1RootLocationPage(QWizardPage):
    """Page for choosing MUS1 root location."""

    def __init__(self):
        super().__init__()
        self.setTitle("MUS1 Root Location")
        self.setSubTitle("Choose where MUS1 should store its configuration and data")

        layout = QVBoxLayout()

        # Detected configuration (if any)
        from ..core.config_manager import resolve_mus1_root
        detected_root = resolve_mus1_root()
        detected_valid = (detected_root / "config" / "config.db").exists()

        # Mode selection
        mode_group = QGroupBox("Configuration Source")
        mode_layout = QVBoxLayout()
        self.mode_use_detected = QRadioButton("Use detected configuration" + (f" at {detected_root}" if detected_valid else " (none detected)"))
        self.mode_use_detected.setEnabled(detected_valid)
        self.mode_use_detected.setChecked(detected_valid)

        self.mode_locate_existing = QRadioButton("Locate existing configuration…")
        self.mode_create_new = QRadioButton("Create new configuration at selected location")
        if not detected_valid:
            self.mode_create_new.setChecked(True)

        mode_layout.addWidget(self.mode_use_detected)
        mode_layout.addWidget(self.mode_locate_existing)
        mode_layout.addWidget(self.mode_create_new)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Description
        desc_label = QLabel(
            "MUS1 needs a directory to store its configuration, logs, and other data.\n\n"
            "You can use the current location (where you cloned the MUS1 repository) "
            "or choose a different location for better organization."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Current location info
        current_location_group = QGroupBox("Current Repository Location")
        current_layout = QVBoxLayout()

        self.current_path_label = QLabel()
        self.current_path_label.setText(f"📁 {Path.cwd()}")
        self.current_path_label.setStyleSheet("font-family: monospace; color: blue;")
        current_layout.addWidget(self.current_path_label)

        use_current_checkbox = QCheckBox("Use this location as MUS1 root")
        use_current_checkbox.setChecked(True)
        use_current_checkbox.toggled.connect(self.on_use_current_toggled)
        current_layout.addWidget(use_current_checkbox)

        current_location_group.setLayout(current_layout)
        layout.addWidget(current_location_group)

        # Custom location option (used when creating new)
        custom_location_group = QGroupBox("Choose Custom Location")
        custom_layout = QVBoxLayout()

        custom_desc = QLabel(
            "Select a different directory for MUS1 data. This keeps your codebase "
            "separate from your configuration and project data."
        )
        custom_desc.setWordWrap(True)
        custom_layout.addWidget(custom_desc)

        # Path selection
        path_layout = QHBoxLayout()
        self.custom_path_edit = QLineEdit()
        self.custom_path_edit.setPlaceholderText("Select or enter MUS1 root directory path")
        self.custom_path_edit.setEnabled(False)
        path_layout.addWidget(self.custom_path_edit)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.setEnabled(False)
        self.browse_button.clicked.connect(self.browse_custom_path)
        path_layout.addWidget(self.browse_button)

        custom_layout.addLayout(path_layout)

        # Platform-specific suggestions
        if platform.system() == "Darwin":  # macOS
            suggestion_label = QLabel(
                "💡 Suggested: ~/Documents/MUS1-Data or /Volumes/MUS1-Data"
            )
        else:
            suggestion_label = QLabel(
                "💡 Suggested: ~/mus1-data or /opt/mus1-data"
            )
        suggestion_label.setStyleSheet("color: gray; font-size: 11px;")
        custom_layout.addWidget(suggestion_label)

        custom_location_group.setLayout(custom_layout)
        layout.addWidget(custom_location_group)

        # Locate existing configuration option
        locate_group = QGroupBox("Locate Existing Configuration")
        locate_layout = QVBoxLayout()
        locate_desc = QLabel("Select a directory that contains config/config.db (the MUS1 configuration database).")
        locate_desc.setWordWrap(True)
        locate_layout.addWidget(locate_desc)
        locate_path_layout = QHBoxLayout()
        self.locate_path_edit = QLineEdit()
        self.locate_browse_button = QPushButton("Browse…")
        self.locate_browse_button.clicked.connect(self.browse_locate_path)
        locate_path_layout.addWidget(self.locate_path_edit)
        locate_path_layout.addWidget(self.locate_browse_button)
        locate_layout.addLayout(locate_path_layout)
        locate_group.setLayout(locate_layout)
        layout.addWidget(locate_group)

        # Copy existing config option
        self.copy_config_checkbox = QCheckBox(
            "Copy existing configuration (if any) to new location"
        )
        self.copy_config_checkbox.setChecked(True)
        self.copy_config_checkbox.setEnabled(False)
        layout.addWidget(self.copy_config_checkbox)

        self.setLayout(layout)

        # Connect signals
        self.use_current_checkbox = use_current_checkbox
        # Toggle visibility/enabled fields based on mode
        self.mode_use_detected.toggled.connect(self._on_mode_changed)
        self.mode_locate_existing.toggled.connect(self._on_mode_changed)
        self.mode_create_new.toggled.connect(self._on_mode_changed)
        self._on_mode_changed()

    def on_use_current_toggled(self, checked: bool):
        """Handle toggling between current and custom location."""
        self.custom_path_edit.setEnabled(not checked)
        self.browse_button.setEnabled(not checked)
        self.copy_config_checkbox.setEnabled(not checked)

        if checked:
            self.copy_config_checkbox.setChecked(False)

    def _on_mode_changed(self):
        is_create = self.mode_create_new.isChecked()
        is_locate = self.mode_locate_existing.isChecked()
        # New config controls
        self.use_current_checkbox.setEnabled(is_create)
        self.custom_path_edit.setEnabled(is_create and not self.use_current_checkbox.isChecked())
        self.browse_button.setEnabled(is_create and not self.use_current_checkbox.isChecked())
        self.copy_config_checkbox.setEnabled(is_create and not self.use_current_checkbox.isChecked())
        if is_create and self.use_current_checkbox.isChecked():
            self.copy_config_checkbox.setChecked(False)
        # Locate controls
        self.locate_path_edit.setEnabled(is_locate)
        self.locate_browse_button.setEnabled(is_locate)

    def browse_custom_path(self):
        """Browse for custom MUS1 root path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select MUS1 Root Directory",
            self.custom_path_edit.text() or str(Path.home())
        )
        if path:
            self.custom_path_edit.setText(path)

    def browse_locate_path(self):
        """Browse for an existing MUS1 config root (expects config/config.db inside)."""
        path = QFileDialog.getExistingDirectory(
            self, "Select MUS1 Configuration Root",
            self.locate_path_edit.text() or str(Path.home())
        )
        if path:
            self.locate_path_edit.setText(path)

    def validatePage(self) -> bool:
        """Validate MUS1 root location selection."""
        # If using detected, accept
        if self.mode_use_detected.isChecked():
            return True

        if self.mode_locate_existing.isChecked():
            root_str = self.locate_path_edit.text().strip()
            if not root_str:
                QMessageBox.warning(self, "Validation Error", "Please select a configuration root directory")
                return False
            root = Path(root_str)
            if not (root / "config" / "config.db").exists():
                QMessageBox.warning(self, "Validation Error", "Selected directory does not contain config/config.db")
                return False
            return True

        # Creating new configuration
        if self.use_current_checkbox.isChecked():
            return True  # Current location is always valid

        # Validate custom path
        custom_path = self.custom_path_edit.text().strip()
        if not custom_path:
            QMessageBox.warning(self, "Validation Error", "Please enter a path for MUS1 root location")
            return False

        path = Path(custom_path)
        if path.exists() and not path.is_dir():
            QMessageBox.warning(self, "Validation Error", "Selected path is not a directory")
            return False

        return True

    def get_selected_path(self) -> Path:
        """Get the selected MUS1 root path."""
        if self.mode_use_detected.isChecked():
            from ..core.config_manager import resolve_mus1_root
            return resolve_mus1_root()
        if self.mode_locate_existing.isChecked():
            return Path(self.locate_path_edit.text().strip())
        if self.use_current_checkbox.isChecked():
            return Path.cwd()
        else:
            return Path(self.custom_path_edit.text().strip())


class UserProfilePage(QWizardPage):
    """Page for setting up user profile."""

    def __init__(self):
        super().__init__()
        self.setTitle("User Profile Setup")
        self.setSubTitle("Please provide your personal information")

        layout = QVBoxLayout()

        # Existing user selection
        from ..core.setup_service import get_setup_service as _get_ss
        self.use_existing_user_checkbox = QCheckBox("Use existing user")
        layout.addWidget(self.use_existing_user_checkbox)
        self.existing_user_combo = QComboBox()
        self.existing_user_combo.setEnabled(False)
        layout.addWidget(self.existing_user_combo)
        try:
            svc = _get_ss()
            users = svc.get_all_users() or {}
            # Expect dict of id -> profile
            for uid, profile in users.items():
                display = f"{profile.get('name','')} <{profile.get('email','')}>"
                self.existing_user_combo.addItem(display, uid)
        except Exception:
            pass
        self.use_existing_user_checkbox.toggled.connect(self.existing_user_combo.setEnabled)

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
        if self.use_existing_user_checkbox.isChecked():
            # Using existing user selection
            if self.existing_user_combo.currentIndex() < 0:
                QMessageBox.warning(self, "Validation Error", "Please select an existing user")
                return False
            return True
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

        # Existing or new lab controls
        self.use_existing_lab_checkbox = QCheckBox("Use existing lab")
        layout.addWidget(self.use_existing_lab_checkbox)
        self.existing_lab_combo = QComboBox()
        self.existing_lab_combo.setEnabled(False)
        layout.addWidget(self.existing_lab_combo)
        try:
            from ..core.setup_service import get_setup_service as _get_ss
            svc = _get_ss()
            labs = svc.get_labs() or {}
            # Expect dict id -> data
            for lid, lab in labs.items():
                name = lab.get('name', lid)
                inst = lab.get('institution')
                display = f"{name} ({inst})" if inst else name
                self.existing_lab_combo.addItem(display, lid)
        except Exception:
            pass
        self.use_existing_lab_checkbox.toggled.connect(self.existing_lab_combo.setEnabled)

        # Create lab checkbox
        self.create_checkbox = QCheckBox("Create a lab now")
        self.create_checkbox.setChecked(True)
        layout.addWidget(self.create_checkbox)

        # Lab configuration group
        self.lab_group = QGroupBox("Lab Configuration")
        lab_layout = QFormLayout()

        # Lab ID is auto-generated from name, so we hide it to reduce UI clutter
        self.lab_id_edit = QLineEdit()
        self.lab_id_edit.setVisible(False)  # Hidden since auto-generated
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

        # Optional lab storage root
        self.lab_storage_path_edit = QLineEdit()
        self.lab_storage_path_edit.setPlaceholderText("Optional: Root directory for this lab's data")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.browse_lab_storage)
        path_row = QHBoxLayout()
        path_row.addWidget(self.lab_storage_path_edit)
        path_row.addWidget(browse_btn)
        lab_layout.addRow("Lab Storage Root:", path_row)

        self.lab_group.setLayout(lab_layout)
        layout.addWidget(self.lab_group)

        # Connect signals
        self.create_checkbox.toggled.connect(self.toggle_lab_config)
        # Disable creation group when using existing lab
        self.use_existing_lab_checkbox.toggled.connect(lambda checked: self.toggle_lab_config(not checked and self.create_checkbox.isChecked()))
        self.lab_name_edit.textChanged.connect(self.update_lab_id)

        self.setLayout(layout)

    def browse_lab_storage(self):
        """Browse for optional lab storage root path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Lab Storage Root",
            self.lab_storage_path_edit.text() or str(Path.home())
        )
        if path:
            self.lab_storage_path_edit.setText(path)

    def toggle_lab_config(self, checked: bool):
        """Enable/disable lab configuration based on checkbox."""
        self.lab_group.setEnabled(checked)

    def update_lab_id(self, text: str):
        """Auto-generate lab ID from lab name."""
        if text.strip():
            # Create a clean lab ID from the lab name
            lab_id = text.strip().lower()
            lab_id = ''.join(c for c in lab_id if c.isalnum() or c in ' _-')
            lab_id = lab_id.replace(' ', '_')
            self.lab_id_edit.setText(lab_id)
        else:
            self.lab_id_edit.clear()

    def validatePage(self) -> bool:
        """Validate lab configuration."""
        if self.use_existing_lab_checkbox.isChecked():
            if self.existing_lab_combo.currentIndex() < 0:
                QMessageBox.warning(self, "Validation Error", "Please select an existing lab")
                return False
            return True
        if not self.create_checkbox.isChecked():
            return True  # Skip validation if not creating lab

        lab_name = self.lab_name_edit.text().strip()

        # Ensure lab name is provided
        if not lab_name or len(lab_name) < 3:
            QMessageBox.warning(self, "Validation Error", "Lab name must be at least 3 characters")
            return False

        # Auto-generate lab ID if needed
        if not self.lab_id_edit.text().strip():
            self.update_lab_id(lab_name)

        lab_id = self.lab_id_edit.text().strip()

        # Ensure lab ID is valid
        if not lab_id or len(lab_id) < 3:
            QMessageBox.warning(self, "Validation Error", "Could not generate valid lab ID. Please enter a lab name first.")
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
        self.next_steps_text.setTextFormat(Qt.TextFormat.RichText)
        next_steps_layout.addWidget(self.next_steps_text)

        next_steps_group.setLayout(next_steps_layout)
        layout.addWidget(next_steps_group)

        self.setLayout(layout)

    def initializePage(self):
        """Initialize the conclusion page - setup is running asynchronously."""
        # Show initial status - setup is in progress
        self.show_setup_in_progress()

        # Connect to setup completion signal to update when done
        wizard = self.wizard()
        if hasattr(wizard, 'setup_completed'):
            wizard.setup_completed.connect(self.on_setup_completed)

    def show_setup_in_progress(self):
        """Show that setup is currently in progress."""
        summary = "<h3>MUS1 Setup in Progress</h3><br>"
        summary += "<p>Please wait while MUS1 is being configured...</p>"
        summary += "<table border='1' cellpadding='5'>"
        summary += "<tr><th>Component</th><th>Status</th></tr>"
        summary += "<tr><td>MUS1 Root</td><td>⟳ Configuring...</td></tr>"
        summary += "<tr><td>User Profile</td><td>⟳ Configuring...</td></tr>"
        summary += "<tr><td>Shared Storage</td><td>⟳ Checking...</td></tr>"
        summary += "<tr><td>Lab</td><td>⟳ Checking...</td></tr>"
        summary += "<tr><td>Projects</td><td>ℹ Ready when setup completes</td></tr>"
        summary += "</table>"

        self.summary_text.setHtml(summary)
        self.next_steps_text.setText("<p>Setup will complete shortly...</p>")

    def on_setup_completed(self, result: dict):
        """Handle setup completion and update the summary."""
        wizard = self.wizard()

        if result.get("success"):
            self.show_setup_success(wizard)
        else:
            self.show_setup_error(result)

    def show_setup_success(self, wizard):
        """Show successful setup completion."""
        summary = "<h3>MUS1 Setup Complete</h3><br>"
        summary += "<table border='1' cellpadding='5'>"
        summary += "<tr><th>Component</th><th>Status</th><th>Details</th></tr>"

        # MUS1 Root Location
        if hasattr(wizard, 'mus1_root_dto') and wizard.mus1_root_dto:
            summary += f"<tr><td>MUS1 Root</td><td>✓ Configured</td><td>{wizard.mus1_root_dto.path}</td></tr>"
        else:
            summary += "<tr><td>MUS1 Root</td><td>✓ Configured</td><td>Using default location</td></tr>"

        # User Profile
        if hasattr(wizard, 'user_dto') and wizard.user_dto:
            summary += f"<tr><td>User Profile</td><td>✓ Configured</td><td>{wizard.user_dto.name}</td></tr>"
        else:
            summary += "<tr><td>User Profile</td><td>⚠ Skipped</td><td>Not configured</td></tr>"

        # Shared Storage
        if hasattr(wizard, 'shared_dto') and wizard.shared_dto:
            summary += f"<tr><td>Shared Storage</td><td>✓ Configured</td><td>{wizard.shared_dto.path}</td></tr>"
        else:
            summary += "<tr><td>Shared Storage</td><td>⚠ Skipped</td><td>Not configured</td></tr>"

        # Lab
        if hasattr(wizard, 'lab_dto') and wizard.lab_dto:
            summary += f"<tr><td>Lab</td><td>✓ Created</td><td>{wizard.lab_dto.name}</td></tr>"
        else:
            summary += "<tr><td>Lab</td><td>⚠ Skipped</td><td>Not created</td></tr>"

        summary += "<tr><td>Projects</td><td>ℹ Ready</td><td>Create projects in GUI</td></tr>"
        summary += "</table>"

        self.summary_text.setHtml(summary)

        # Next steps
        next_steps = "<ul>"
        next_steps += "<li>Create your first project</li>"
        next_steps += "<li>Add subjects and experiments</li>"
        if not (hasattr(wizard, 'shared_dto') and wizard.shared_dto):
            next_steps += "<li>Configure shared storage if needed</li>"
        next_steps += "</ul>"

        self.next_steps_text.setText(next_steps)

    def show_setup_error(self, result: dict):
        """Show setup error."""
        error_msg = result.get("message", "Unknown error")
        summary = f"<h3>MUS1 Setup Failed</h3><br><p>Error: {error_msg}</p>"
        self.summary_text.setHtml(summary)
        self.next_steps_text.setText("<p>Please try again or contact support.</p>")


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
        self.mus1_root_dto = None
        self.user_dto = None
        self.shared_dto = None
        self.lab_dto = None
        self.selected_user_id = None
        self.selected_lab_id = None

        # Add pages
        self.addPage(WelcomePage())
        # Removed MUS1RootLocationPage from the default flow to avoid conflating app root with data roots
        self.addPage(UserProfilePage())
        self.addPage(SharedStoragePage())
        self.addPage(LabSetupPage())
        self.addPage(ConclusionPage())

        # Connect signals
        self.currentIdChanged.connect(self.on_page_changed)

    def on_page_changed(self, page_id: int):
        """Handle page changes."""
        if page_id == 5:  # Conclusion page (index 5, not 4)
            # Collect data from pages before initializing conclusion page
            self.collect_setup_data()
            self.run_setup()

    def run_setup(self):
        """Run the setup process."""
        # Data collection already done in on_page_changed

        # Create workflow DTO
        workflow_dto = SetupWorkflowDTO(
            mus1_root_location=self.mus1_root_dto,
            user_profile=self.user_dto,
            shared_storage=self.shared_dto,
            lab=self.lab_dto
        )

        # Run setup in background thread
        self.worker = SetupWorker(workflow_dto)
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_setup_finished)
        self.worker.error.connect(self.on_setup_error)
        self.worker.progress.connect(self.on_setup_progress)
        self.worker.warning.connect(self.on_setup_warning)
        # Ensure thread cleanup
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)

        # Connect the wizard's setup_completed signal to update conclusion page
        self.setup_completed.connect(self.update_conclusion_page)

        # Show progress on conclusion page
        conclusion_page = self.page(5)  # Conclusion page is at index 5
        progress_label = QLabel("Running setup...")
        conclusion_page.layout().addWidget(progress_label)

        # Start the worker thread
        self.thread.start()

    def collect_setup_data(self):
        """Collect setup data from wizard pages."""
        # MUS1 Root Location: use deterministic resolution; app root is OS-default and not chosen here
        mus1_root = resolve_mus1_root()
        self.mus1_root_dto = MUS1RootLocationDTO(
            path=mus1_root,
            create_if_missing=True,
            copy_existing_config=False
        )

        # User profile
        user_page = self.page(2)  # UserProfilePage
        if hasattr(user_page, 'use_existing_user_checkbox') and user_page.use_existing_user_checkbox.isChecked():
            # Use existing user
            self.user_dto = None
            self.selected_user_id = user_page.existing_user_combo.currentData()
        else:
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
        storage_page = self.page(3)  # SharedStoragePage
        if storage_page.configure_checkbox.isChecked():
            self.shared_dto = SharedStorageDTO(
                path=Path(storage_page.path_edit.text().strip()),
                create_if_missing=storage_page.create_checkbox.isChecked(),
                verify_permissions=storage_page.verify_checkbox.isChecked()
            )

        # Lab
        lab_page = self.page(4)  # LabSetupPage
        if hasattr(lab_page, 'use_existing_lab_checkbox') and lab_page.use_existing_lab_checkbox.isChecked():
            self.lab_dto = None
            self.selected_lab_id = lab_page.existing_lab_combo.currentData()
            self._lab_storage_root = None
        elif lab_page.create_checkbox.isChecked():
            lab_id = lab_page.lab_id_edit.text().strip()
            lab_name = lab_page.lab_name_edit.text().strip()
            # Generate creator_id from user email (same logic as in setup_service)
            user_email = user_page.field("user_email").strip()
            creator_id = user_email.lower().replace("@", "_").replace(".", "_")
            self.lab_dto = LabDTO(
                id=lab_id,
                name=lab_name,
                institution=lab_page.institution_edit.text().strip() or "",
                pi_name=lab_page.pi_edit.text().strip() or "",
                creator_id=creator_id
            )
            # Optional: lab storage root retained locally; set via service after workflow
            self._lab_storage_root = Path(lab_page.lab_storage_path_edit.text().strip()) if lab_page.lab_storage_path_edit.text().strip() else None
        else:
            self.lab_dto = None
            self._lab_storage_root = None

    def on_setup_finished(self, result: dict):
        """Handle successful setup completion."""
        # ConfigManager is already re-initialized in the worker thread after root setup
        self.setup_completed.emit(result)
        # If lab was created and a lab storage root was provided, set it now via service
        try:
            if getattr(self, 'lab_dto', None) and getattr(self, '_lab_storage_root', None):
                from ..core.setup_service import get_setup_service
                svc = get_setup_service()
                svc.set_lab_storage_root(self.lab_dto.id, self._lab_storage_root)
            # If shared storage was set and a project is active, offer to set project shared_root
            parent = self.parent()
            if getattr(self, 'shared_dto', None) and parent and hasattr(parent, 'project_manager') and parent.project_manager:
                try:
                    parent.project_manager.set_shared_root(self.shared_dto.path)
                    parent.project_manager.save_project()
                except Exception:
                    pass
        except Exception:
            pass
        QMessageBox.information(
            self, "Setup Complete",
            "MUS1 has been configured successfully!\n\n"
            "You can now create projects and start your research workflow."
        )

    def on_setup_error(self, error_msg: str):
        """Handle setup error."""
        QMessageBox.critical(self, "Setup Error", f"Setup failed:\n\n{error_msg}")
        # Propagate to conclusion page
        try:
            self.setup_completed.emit({"success": False, "message": error_msg})
        except Exception:
            pass

    def on_setup_progress(self, message: str):
        """Handle setup progress updates."""
        # Could update progress bar here
        print(f"Setup progress: {message}")

    def on_setup_warning(self, warning_msg: str):
        """Handle setup warnings."""
        QMessageBox.warning(self, "Setup Warning", warning_msg)

    def update_conclusion_page(self, result: dict):
        """Update the conclusion page when setup completes."""
        conclusion_page = self.page(5)  # Conclusion page is at index 5
        try:
            # Cast to the concrete page type that defines the methods
            from typing import Any
            cp: Any = conclusion_page
            if result.get("success"):
                cp.show_setup_success(self)
            else:
                cp.show_setup_error(result)
        except Exception:
            pass


# ===========================================
# UTILITY FUNCTIONS
# ===========================================

def show_setup_wizard(parent=None) -> Optional[MUS1SetupWizard]:
    """Show the MUS1 setup wizard dialog."""
    wizard = MUS1SetupWizard(parent)
    result = wizard.exec()

    if result == QWizard.DialogCode.Accepted:
        return wizard
    return None


def check_setup_status() -> SetupStatusDTO:
    """Check current MUS1 setup status."""
    setup_service = get_setup_service()
    return setup_service.get_setup_status()