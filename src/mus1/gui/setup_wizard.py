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

from .qt import (
    QWidget, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QFormLayout, QCheckBox, QPushButton,
    QTextEdit, QMessageBox, QGroupBox, QRadioButton,
    QComboBox, Signal, QObject, QFileDialog
)

from ..core.setup_service import SetupWorkflowDTO, UserProfileDTO
from ..core.config_manager import init_config_manager
from ..core.setup_service import get_setup_service
from .base_view import BaseView
from .gui_services import GlobalGUIServiceFactory


# ===========================================
# WORKER THREAD FOR ASYNC SETUP
# ===========================================

class SetupWorker(QObject):
    """Worker thread for running setup operations asynchronously."""

    finished = Signal(dict)  # Emits result dict
    progress = Signal(str)   # Emits progress message
    error = Signal(str)      # Emits error message
    warning = Signal(str)    # Emits warning message

    def __init__(self, workflow_dto: SetupWorkflowDTO, setup_service=None):
        super().__init__()
        self.workflow_dto = workflow_dto
        self.setup_service = setup_service

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

class WelcomePage(QWidget):
    """Welcome page for the setup wizard."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Welcome to MUS1 Setup")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Get started with your research workflow")
        subtitle_label.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 20px;")
        layout.addWidget(subtitle_label)

        # Welcome message
        welcome_label = QLabel(
            "Welcome to MUS1!\n\n"
            "Choose how you'd like to organize your research:\n\n"
            "• **Local Projects**: Work with projects on your computer only\n"
            "• **Lab Collaboration**: Join or create a lab for team collaboration\n\n"
            "You can change this later in settings."
        )
        welcome_label.setWordWrap(True)
        welcome_label.setStyleSheet("font-size: 13px; line-height: 1.4;")
        layout.addWidget(welcome_label)

        # Check existing configuration
        setup_service = get_setup_service()
        if setup_service.is_user_configured():
            existing_profile = setup_service.get_user_profile()
            info_label = QLabel(
                f"ℹ️  Updating configuration for: {existing_profile.name}"
            )
            info_label.setStyleSheet("color: blue; font-weight: bold;")
            layout.addWidget(info_label)

        layout.addStretch()


class UserProfilePage(QWidget):
    """Page for collecting user profile information."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("User Profile")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Please provide your information")
        subtitle_label.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 20px;")
        layout.addWidget(subtitle_label)

        # Form layout for user input
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # Name field
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., John Smith")
        form_layout.addRow("Full Name:", self.name_edit)

        # Email field
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("e.g., john.smith@university.edu")
        form_layout.addRow("Email Address:", self.email_edit)

        # Organization field
        self.organization_edit = QLineEdit()
        self.organization_edit.setPlaceholderText("e.g., University of Example")
        form_layout.addRow("Organization:", self.organization_edit)

        # Projects directory field
        self.projects_dir_edit = QLineEdit()
        self.projects_dir_edit.setPlaceholderText("Leave empty for default")
        self.projects_dir_edit.setToolTip("Directory where your local projects will be stored")
        form_layout.addRow("Projects Directory:", self.projects_dir_edit)

        # Browse button for projects directory
        browse_projects_layout = QHBoxLayout()
        browse_projects_layout.addWidget(self.projects_dir_edit)
        browse_projects_btn = QPushButton("Browse...")
        browse_projects_btn.clicked.connect(self.browse_projects_dir)
        browse_projects_layout.addWidget(browse_projects_btn)
        form_layout.addRow("", browse_projects_layout)

        layout.addLayout(form_layout)
        layout.addStretch()

    def browse_projects_dir(self):
        """Browse for projects directory."""
        path = QFileDialog.getExistingDirectory(self, "Select Projects Directory")
        if path:
            self.projects_dir_edit.setText(path)

    def validate_page(self) -> bool:
        """Validate the user profile input."""
        name = self.name_edit.text().strip()
        email = self.email_edit.text().strip()
        organization = self.organization_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Name is required.")
            return False

        if not email or "@" not in email:
            QMessageBox.warning(self, "Validation Error", "Valid email address is required.")
            return False

        if not organization:
            QMessageBox.warning(self, "Validation Error", "Organization is required.")
            return False

        return True

    def get_user_profile_dto(self) -> UserProfileDTO:
        """Get the user profile DTO from the form data."""
        from pathlib import Path

        projects_dir = None
        if self.projects_dir_edit.text().strip():
            projects_dir = Path(self.projects_dir_edit.text().strip())

        return UserProfileDTO(
            name=self.name_edit.text().strip(),
            email=self.email_edit.text().strip(),
            organization=self.organization_edit.text().strip(),
            default_projects_dir=projects_dir
        )


class LabChoicePage(QWidget):
    """Choose between local-only or lab collaboration."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Research Organization")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("How would you like to organize your research?")
        subtitle_label.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 20px;")
        layout.addWidget(subtitle_label)

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


class LabConfigPage(QWidget):
    """Configure lab settings if creating/joining a lab."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Lab Configuration")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Set up your research lab")
        subtitle_label.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 20px;")
        layout.addWidget(subtitle_label)

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

        # Initialize (labs will be populated via populate_existing_labs)
        self.on_lab_choice_changed()

    def populate_existing_labs(self, labs):
        """Populate the existing labs dropdown."""
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


class ConclusionPage(QWidget):
    """Final page showing setup summary."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Setup Complete")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("MUS1 is ready to use!")
        subtitle_label.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 20px;")
        layout.addWidget(subtitle_label)

        self.summary_label = QLabel("Setup completed successfully!")
        self.summary_label.setStyleSheet("font-size: 14px; font-weight: bold; color: green;")
        layout.addWidget(self.summary_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        layout.addWidget(self.details_text)

        layout.addStretch()

    def initialize_page(self):
        """Initialize the conclusion page with setup summary."""
        # Get the wizard view from parent hierarchy
        wizard_view = self.parent()
        while wizard_view and not hasattr(wizard_view, 'user_dto'):
            wizard_view = wizard_view.parent()

        summary = "Setup Summary:\n\n"

        if wizard_view and hasattr(wizard_view, 'user_dto') and wizard_view.user_dto:
            user_profile = wizard_view.user_dto
            summary += f"User Profile:\n"
            summary += f"  Name: {user_profile.name}\n"
            summary += f"  Email: {user_profile.email}\n"
            summary += f"  Organization: {user_profile.organization}\n"
            if user_profile.default_projects_dir:
                summary += f"  Projects Directory: {user_profile.default_projects_dir}\n"
            summary += "\n"
        else:
            summary += "User profile: Not configured\n\n"

        if wizard_view and hasattr(wizard_view, 'lab_choice'):
            if wizard_view.lab_choice == "lab":
                summary += "Lab Setup: Enabled\n"
                if wizard_view.lab_dto:
                    summary += f"  Lab Name: {wizard_view.lab_dto.name}\n"
                    summary += f"  Institution: {wizard_view.lab_dto.institution}\n"
                    summary += f"  PI: {wizard_view.lab_dto.pi_name}\n"
                    if getattr(wizard_view, '_lab_sharing_enabled', False):
                        summary += "  Lab sharing: Enabled\n"
                else:
                    summary += "  Joined existing lab\n"
                summary += "\nYou can now create shared projects and collaborate with lab members."
            else:
                summary += "Lab Setup: Local projects only\n\nYou can create local projects and manage your research data."
        else:
            summary += "Lab Setup: Not configured"

        self.details_text.setPlainText(summary)


class SetupWizardView(BaseView):
    """Setup wizard view that follows the BaseView pattern with wizard navigation."""

    def __init__(self, parent=None):
        super().__init__(parent, view_name="setup_wizard")

        # Initialize wizard data
        self.user_dto = None
        self.lab_choice = "local"  # Default to local
        self.lab_dto = None
        self._lab_sharing_enabled = False

        # Initialize services (will be set via on_services_ready)
        self.setup_service = None

        # Set up wizard pages
        self.setup_wizard_pages()

        # Set up navigation for wizard flow
        self.setup_wizard_navigation()

        # Start with welcome page
        self.change_page(0)

    def on_services_ready(self, services):
        """Called when services are ready to be injected."""
        if hasattr(services, 'create_setup_service'):
            # Global services factory
            self.setup_service = services.create_setup_service()
        else:
            # Fallback for backward compatibility
            global_factory = GlobalGUIServiceFactory()
            self.setup_service = global_factory.create_setup_service()

        # Populate existing labs if service is available
        if self.setup_service:
            self.populate_existing_labs()

    def update_theme(self, theme):
        """Update theme for the setup wizard."""
        self.setProperty("theme", theme)
        self.style().unpolish(self)
        self.style().polish(self)

    def populate_existing_labs(self):
        """Populate existing labs in all relevant pages."""
        if not self.setup_service:
            return

        labs = self.setup_service.get_labs()
        # Update any pages that need lab data
        if hasattr(self, 'lab_config_page') and hasattr(self.lab_config_page, 'populate_existing_labs'):
            self.lab_config_page.populate_existing_labs(labs)

    def setup_wizard_pages(self):
        """Set up the wizard pages in the content area."""
        # Create page widgets
        self.welcome_page = self.create_welcome_page()
        self.user_profile_page = self.create_user_profile_page()
        self.lab_choice_page = self.create_lab_choice_page()
        self.lab_config_page = self.create_lab_config_page()
        self.conclusion_page = self.create_conclusion_page()

        # Add pages to stacked widget (inherited from BaseView)
        self.content_area.addWidget(self.welcome_page)
        self.content_area.addWidget(self.user_profile_page)
        self.content_area.addWidget(self.lab_choice_page)
        self.content_area.addWidget(self.lab_config_page)
        self.content_area.addWidget(self.conclusion_page)

    def setup_wizard_navigation(self):
        """Set up wizard-style navigation."""
        # Clear existing navigation
        self.navigation_pane.clear_buttons()

        # Add wizard navigation buttons
        self.add_navigation_button("Welcome", page_index=0)
        self.add_navigation_button("Profile", page_index=1)
        self.add_navigation_button("Organization", page_index=2)
        self.add_navigation_button("Lab Setup", page_index=3)
        self.add_navigation_button("Complete", page_index=4)

        # Add action buttons at bottom
        self.setup_wizard_actions()

    def setup_wizard_actions(self):
        """Set up wizard action buttons (Back/Next/Finish)."""
        # Create action buttons layout
        actions_layout = QVBoxLayout()
        actions_layout.setContentsMargins(10, 10, 10, 10)

        # Back button
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setEnabled(False)  # Disabled on first page
        actions_layout.addWidget(self.back_button)

        # Next button
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.go_next)
        actions_layout.addWidget(self.next_button)

        # Finish button (hidden initially)
        self.finish_button = QPushButton("Finish Setup")
        self.finish_button.clicked.connect(self.finish_setup)
        self.finish_button.setVisible(False)
        actions_layout.addWidget(self.finish_button)

        actions_layout.addStretch()

        # Add to navigation pane
        actions_widget = QWidget()
        actions_widget.setLayout(actions_layout)
        self.navigation_pane.add_widget(actions_widget)

    def go_back(self):
        """Go to previous page."""
        current_index = self.content_area.currentIndex()
        if current_index > 0:
            self.change_page(current_index - 1)
            self.update_navigation_buttons()

    def go_next(self):
        """Go to next page."""
        current_index = self.content_area.currentIndex()
        if current_index < self.content_area.count() - 1:
            # Validate current page before proceeding
            if self.validate_current_page():
                self.change_page(current_index + 1)
                self.update_navigation_buttons()

    def finish_setup(self):
        """Complete the setup process."""
        if self.validate_current_page():
            success = self._run_setup()
            if success:
                # Signal completion to parent dialog
                parent = self.parent()
                if parent and hasattr(parent, 'accept'):
                    parent.accept()
            # If setup failed, don't accept the dialog so user can try again

    def update_navigation_buttons(self):
        """Update navigation button states based on current page."""
        current_index = self.content_area.currentIndex()
        total_pages = self.content_area.count()

        # Update back button
        self.back_button.setEnabled(current_index > 0)

        # Update next/finish buttons
        if current_index == total_pages - 1:  # Last page
            self.next_button.setVisible(False)
            self.finish_button.setVisible(True)
        else:
            self.next_button.setVisible(True)
            self.finish_button.setVisible(False)

    def validate_current_page(self) -> bool:
        """Validate the current page before proceeding."""
        current_index = self.content_area.currentIndex()

        if current_index == 1:  # User profile page
            return self.validate_user_profile_page()
        elif current_index == 3:  # Lab config page
            return self.validate_lab_config_page()
        elif current_index == 4:  # Conclusion page
            return True

        return True

    def validate_user_profile_page(self) -> bool:
        """Validate user profile page."""
        if hasattr(self, 'user_profile_page') and hasattr(self.user_profile_page, 'validate_page'):
            return self.user_profile_page.validate_page()
        return True

    def validate_lab_config_page(self) -> bool:
        """Validate lab configuration page."""
        # Add validation logic here
        return True

    def create_welcome_page(self):
        """Create the welcome page."""
        page = WelcomePage()
        return page

    def create_user_profile_page(self):
        """Create the user profile page."""
        page = UserProfilePage()
        return page

    def create_lab_choice_page(self):
        """Create the lab choice page."""
        page = LabChoicePage()
        # Connect to update wizard data
        if hasattr(page, 'lab_choice_changed'):
            page.lab_choice_changed.connect(self.on_lab_choice_changed)
        return page

    def create_lab_config_page(self):
        """Create the lab config page."""
        page = LabConfigPage()
        return page

    def create_conclusion_page(self):
        """Create the conclusion page."""
        page = ConclusionPage()
        # Initialize the page when created (it will be shown)
        if hasattr(page, 'initialize_page'):
            page.initialize_page()
        return page

    def on_lab_choice_changed(self, choice):
        """Handle lab choice changes."""
        self.lab_choice = choice

    def _run_setup(self) -> bool:
        """Run the setup process based on user selections."""
        try:
            if not self.setup_service:
                QMessageBox.critical(self, "Setup Error", "Setup service not available")
                return False

            # Collect user profile data from the user profile page
            if hasattr(self, 'user_profile_page') and hasattr(self.user_profile_page, 'get_user_profile_dto'):
                try:
                    self.user_dto = self.user_profile_page.get_user_profile_dto()
                except Exception as e:
                    QMessageBox.critical(self, "Setup Error", f"Invalid user profile data: {e}")
                    return False

            # Collect lab data if lab setup was chosen
            if self.lab_choice == "lab" and hasattr(self, 'lab_config_page'):
                # Collect lab data from lab config page
                # For now, we'll use default lab creation logic
                pass

            # Create workflow DTO based on wizard data
            workflow_dto = SetupWorkflowDTO(
                user_profile=self.user_dto,
                lab=self.lab_dto if self.lab_choice == "lab" else None
            )

            # Run setup workflow
            result = self.setup_service.run_setup_workflow(workflow_dto)

            if not result["success"]:
                errors = result.get("errors", ["Unknown error"])
                QMessageBox.warning(
                    self, "Setup Warning",
                    f"Setup completed with warnings:\n\n{chr(10).join(errors)}"
                )
                return True  # Setup completed with warnings, still consider it successful

            return True

        except Exception as e:
            QMessageBox.critical(
                self, "Setup Error",
                f"Setup failed:\n\n{str(e)}"
            )
            return False


# ===========================================
# UTILITY FUNCTIONS
# ===========================================

def show_setup_wizard(parent=None, theme_manager=None) -> Optional[SetupWizardView]:
    """Show the MUS1 setup wizard dialog."""
    try:
        from .qt import QDialog, QVBoxLayout

        # Create modal dialog
        dialog = QDialog(parent)
        dialog.setWindowTitle("MUS1 Setup")
        dialog.setModal(True)
        dialog.resize(800, 600)

        # Create wizard view
        wizard_view = SetupWizardView(dialog)

        # Inject global services
        global_services = GlobalGUIServiceFactory()
        wizard_view.on_services_ready(global_services)

        # Apply theme if theme manager is available
        if theme_manager:
            effective_theme = getattr(theme_manager, "get_effective_theme", lambda: "dark")()
            wizard_view.update_theme(effective_theme)
        else:
            # Default to dark theme
            wizard_view.update_theme("dark")

        # Set up dialog layout
        layout = QVBoxLayout(dialog)
        layout.addWidget(wizard_view)
        dialog.setLayout(layout)

        # Show dialog
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            return wizard_view
        return None
    except Exception as e:
        QMessageBox.critical(
            parent, "Setup Error",
            f"Failed to start setup wizard:\n\n{str(e)}"
        )
        return None
