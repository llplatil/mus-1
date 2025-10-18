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
    Qt, QWidget, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QFormLayout, QCheckBox, QPushButton,
    QTextEdit, QMessageBox, QGroupBox, QRadioButton,
    QComboBox, QDialog, QStackedWidget, Signal, QObject, QFileDialog
)

from ..core.setup_service import SetupWorkflowDTO, UserProfileDTO
from ..core.config_manager import set_config as set_active_config
from ..core.config_manager import init_config_manager
from ..core.setup_service import get_setup_service
from .gui_services import GlobalGUIServiceFactory
from .background import apply_watermark_background


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

class UserSelectionPage(QWidget):
    """User selection/management page: pick existing, add, edit, delete."""

    user_selected = Signal(str)
    request_add = Signal()
    request_edit = Signal(str)
    request_delete = Signal(str)
    continue_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setProperty("class", "mus1-page")
        layout = QVBoxLayout(self)

        title_label = QLabel("Select User")
        title_label.setProperty("class", "mus1-section-label")
        layout.addWidget(title_label)

        # Users group
        users_group = QGroupBox("Configured Users")
        users_group.setProperty("class", "mus1-input-group")
        group_layout = QVBoxLayout(users_group)

        self.users_combo = QComboBox()
        group_layout.addWidget(self.users_combo)

        buttons_row = QHBoxLayout()
        self.add_btn = QPushButton("Add New User")
        self.add_btn.setProperty("class", "mus1-primary-button")
        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setProperty("class", "mus1-secondary-button")
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setProperty("class", "mus1-secondary-button")
        buttons_row.addWidget(self.add_btn)
        buttons_row.addWidget(self.edit_btn)
        buttons_row.addWidget(self.delete_btn)
        group_layout.addLayout(buttons_row)

        layout.addWidget(users_group)

        # Continue row
        continue_row = QHBoxLayout()
        continue_row.addStretch()
        self.continue_btn = QPushButton("Continue with Selected User")
        self.continue_btn.setProperty("class", "mus1-primary-button")
        continue_row.addWidget(self.continue_btn)
        layout.addLayout(continue_row)

        layout.addStretch()

        # Wire
        self.users_combo.currentIndexChanged.connect(self._emit_selected)
        self.add_btn.clicked.connect(self.request_add)
        self.edit_btn.clicked.connect(self._emit_edit)
        self.delete_btn.clicked.connect(self._emit_delete)
        self.continue_btn.clicked.connect(self._emit_continue)

        # Populate
        self._populate_users()

    def _populate_users(self):
        self.users_combo.clear()
        try:
            service = get_setup_service()
            users = service.get_all_users()
            if users:
                for user_id, data in users.items():
                    display = f"{data.get('name') or user_id}  <{data.get('email','?')}>"
                    self.users_combo.addItem(display, user_id)
            else:
                self.users_combo.addItem("No users configured", None)
                self.edit_btn.setEnabled(False)
                self.delete_btn.setEnabled(False)
                self.continue_btn.setEnabled(False)
        except Exception:
            self.users_combo.addItem("Failed to load users", None)
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.continue_btn.setEnabled(False)

    def _current_user_id(self) -> Optional[str]:
        return self.users_combo.currentData()

    def _emit_selected(self, _idx: int):
        user_id = self._current_user_id()
        if user_id:
            self.user_selected.emit(user_id)

    def _emit_edit(self):
        user_id = self._current_user_id()
        if user_id:
            self.request_edit.emit(user_id)

    def _emit_delete(self):
        user_id = self._current_user_id()
        if user_id:
            self.request_delete.emit(user_id)

    def _emit_continue(self):
        user_id = self._current_user_id()
        if user_id:
            self.continue_requested.emit(user_id)


class UserProfilePage(QWidget):
    """Page for collecting user profile information."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Apply page styling
        self.setProperty("class", "mus1-page")

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("User Profile")
        title_label.setProperty("class", "mus1-section-label")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Please provide your information")
        subtitle_label.setProperty("class", "mus1-section-label")
        layout.addWidget(subtitle_label)

        # Form layout for user input
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # Name field
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., John Smith")
        name_label = QLabel("Full Name:")
        name_label.setProperty("formLabel", True)
        form_layout.addRow(name_label, self.name_edit)

        # Email field
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("e.g., john.smith@university.edu")
        email_label = QLabel("Email Address:")
        email_label.setProperty("formLabel", True)
        form_layout.addRow(email_label, self.email_edit)

        # Organization field
        self.organization_edit = QLineEdit()
        self.organization_edit.setPlaceholderText("e.g., University of Example")
        org_label = QLabel("Organization:")
        org_label.setProperty("formLabel", True)
        form_layout.addRow(org_label, self.organization_edit)

        # Projects directory field
        self.projects_dir_edit = QLineEdit()
        self.projects_dir_edit.setPlaceholderText("Leave empty for default")
        self.projects_dir_edit.setToolTip("Directory where your local projects will be stored")

        # Browse button for projects directory
        browse_projects_layout = QHBoxLayout()
        browse_projects_layout.addWidget(self.projects_dir_edit)
        browse_projects_btn = QPushButton("Browse...")
        browse_projects_btn.clicked.connect(self.browse_projects_dir)
        browse_projects_layout.addWidget(browse_projects_btn)
        projects_dir_label = QLabel("Projects Directory:")
        projects_dir_label.setProperty("formLabel", True)
        form_layout.addRow(projects_dir_label, browse_projects_layout)

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

    # Declare Qt signal at class level per PySide6 requirements
    lab_choice_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Apply page styling
        self.setProperty("class", "mus1-page")

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Research Organization")
        title_label.setProperty("class", "mus1-section-label")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("How would you like to organize your research?")
        subtitle_label.setProperty("class", "mus1-section-label")
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
            labs_info = QLabel(f"ℹ️  {len(existing_labs)} existing lab(s) available to join")
            labs_info.setProperty("class", "mus1-section-label")
            layout.addWidget(labs_info)

        layout.addStretch()

        # Wire radio buttons to emit choice
        self.local_radio.toggled.connect(lambda checked: checked and self._emit_choice("local"))
        self.lab_radio.toggled.connect(lambda checked: checked and self._emit_choice("lab"))

    def _emit_choice(self, choice: str):
        self.lab_choice_changed.emit(choice)


class LabConfigPage(QWidget):
    """Configure lab settings if creating/joining a lab."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Apply page styling
        self.setProperty("class", "mus1-page")

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Lab Configuration")
        title_label.setProperty("class", "mus1-section-label")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Set up your research lab")
        subtitle_label.setProperty("class", "mus1-section-label")
        layout.addWidget(subtitle_label)

        # Lab choice: create new or join existing
        choice_group = QGroupBox("Lab Setup")
        choice_group.setProperty("class", "mus1-input-group")
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
        self.new_lab_group.setProperty("class", "mus1-input-group")
        new_lab_layout = QFormLayout(self.new_lab_group)

        self.lab_name_edit = QLineEdit()
        self.lab_name_edit.setPlaceholderText("e.g., Smith Lab")
        lab_name_label = QLabel("Lab Name:")
        lab_name_label.setProperty("formLabel", True)
        new_lab_layout.addRow(lab_name_label, self.lab_name_edit)

        self.institution_edit = QLineEdit()
        self.institution_edit.setPlaceholderText("e.g., University of Example")
        inst_label = QLabel("Institution:")
        inst_label.setProperty("formLabel", True)
        new_lab_layout.addRow(inst_label, self.institution_edit)

        self.pi_edit = QLineEdit()
        self.pi_edit.setPlaceholderText("e.g., Dr. Jane Smith")
        pi_label = QLabel("Principal Investigator:")
        pi_label.setProperty("formLabel", True)
        new_lab_layout.addRow(pi_label, self.pi_edit)

        # Sharing setup
        sharing_group = QGroupBox("Shared Storage (Optional)")
        sharing_group.setProperty("class", "mus1-subgroup")
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
        if isinstance(labs, dict):
            for lab_id, lab_data in labs.items():
                display_name = f"{lab_data.get('name', 'Unknown')} ({lab_data.get('institution', 'No institution')})"
                self.existing_labs_combo.addItem(display_name, lab_id)
        elif isinstance(labs, list):
            for lab_data in labs:
                if isinstance(lab_data, dict):
                    lab_id = lab_data.get('id', lab_data.get('name', 'Unknown'))
                    display_name = f"{lab_data.get('name', 'Unknown')} ({lab_data.get('institution', 'No institution')})"
                    self.existing_labs_combo.addItem(display_name, lab_id)
        else:
            # Handle other cases or empty
            self.existing_labs_combo.addItem("No labs available", None)

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

        # Apply page styling
        self.setProperty("class", "mus1-page")

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Setup Complete")
        title_label.setProperty("class", "mus1-section-label")
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("MUS1 is ready to use!")
        subtitle_label.setProperty("class", "mus1-section-label")
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

        # User section
        if wizard_view and hasattr(wizard_view, 'user_dto') and wizard_view.user_dto:
            # A profile was created/edited in this run
            user_profile = wizard_view.user_dto
            summary += f"User:\n"
            summary += f"  Name: {user_profile.name}\n"
            summary += f"  Email: {user_profile.email}\n"
            summary += f"  Organization: {user_profile.organization}\n"
            if user_profile.default_projects_dir:
                summary += f"  Projects Directory: {user_profile.default_projects_dir}\n"
            summary += "\n"
        else:
            # No profile edits this run; show currently selected/active user if present
            try:
                setup_service = get_setup_service()
                profile = setup_service.get_user_profile()
                if profile:
                    summary += f"User: {profile.name} <{profile.email}> (no changes made)\n\n"
                else:
                    summary += "User: Not configured\n\n"
            except Exception:
                summary += "User: Not configured\n\n"

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


class SetupWizardDialog(QDialog):
    """Setup wizard dialog for MUS1 configuration."""

    def __init__(self, parent=None, theme_manager=None):
        super().__init__(parent)

        # Initialize wizard data
        self.user_dto = None
        self.lab_choice = "local"  # Default to local
        self.lab_dto = None
        self._lab_sharing_enabled = False
        self._user_profile_edit_requested = False

        # Initialize services
        self.setup_service = None

        # Setup dialog properties
        self.setObjectName("setupWizardDialog")
        self.setWindowTitle("MUS1 Setup Wizard")
        self.setMinimumSize(800, 600)
        self.setModal(True)

        # Apply application stylesheet
        from .qt import QApplication
        app = QApplication.instance()
        if app:
            self.setStyleSheet(app.styleSheet())

        # Apply theme
        if theme_manager:
            effective_theme = getattr(theme_manager, "get_effective_theme", lambda: "dark")()
            self.setProperty("theme", effective_theme)
            self.style().unpolish(self)
            self.style().polish(self)

        # Setup services
        global_factory = GlobalGUIServiceFactory()
        self.setup_service = global_factory.create_setup_service()

        # Setup UI
        self.setup_ui()
        self.setup_background()

        # Start with welcome page
        self.show_page(0)

    def setup_ui(self):
        """Setup the main UI layout."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Title
        title_label = QLabel("MUS1 Setup Wizard")
        title_label.setProperty("class", "mus1-title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(title_label)

        # Progress indicator
        self.progress_label = QLabel("Step 1 of 5: Welcome")
        self.progress_label.setProperty("class", "mus1-subtitle")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(self.progress_label)

        # Create stacked widget for pages
        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages)

        # Create pages
        self.user_selection_page = self.create_user_selection_page()
        self.user_profile_page = self.create_user_profile_page()
        self.lab_choice_page = self.create_lab_choice_page()
        self.lab_config_page = self.create_lab_config_page()
        self.conclusion_page = self.create_conclusion_page()

        # Add pages to stacked widget
        self.pages.addWidget(self.user_selection_page)
        self.pages.addWidget(self.user_profile_page)
        self.pages.addWidget(self.lab_choice_page)
        self.pages.addWidget(self.lab_config_page)
        self.pages.addWidget(self.conclusion_page)

        # Navigation buttons
        main_layout.addLayout(self.create_navigation_layout())

    def create_navigation_layout(self):
        """Create the navigation buttons layout."""
        nav_layout = QHBoxLayout()

        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setEnabled(False)
        self.back_button.setProperty("class", "mus1-secondary-button")
        nav_layout.addWidget(self.back_button)

        nav_layout.addStretch()

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.go_next)
        self.next_button.setProperty("class", "mus1-primary-button")
        nav_layout.addWidget(self.next_button)

        self.finish_button = QPushButton("Finish Setup")
        self.finish_button.clicked.connect(self.finish_setup)
        self.finish_button.setVisible(False)
        self.finish_button.setProperty("class", "mus1-primary-button")
        nav_layout.addWidget(self.finish_button)

        return nav_layout

    def show_page(self, index):
        """Show the specified page and update UI."""
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)
            self.update_navigation_buttons()
            self.update_progress_label(index)
            # Refresh conclusion page content when shown
            current_widget = self.pages.widget(index)
            if current_widget is self.conclusion_page and hasattr(self.conclusion_page, 'initialize_page'):
                self.conclusion_page.initialize_page()

    def update_progress_label(self, page_index):
        """Update the progress label based on current page."""
        steps = [
            "Step 1 of 5: Select User",
            "Step 2 of 5: User Profile",
            "Step 3 of 5: Organization",
            "Step 4 of 5: Lab Setup",
            "Step 5 of 5: Complete"
        ]
        if 0 <= page_index < len(steps):
            self.progress_label.setText(steps[page_index])

    def go_back(self):
        """Go to previous page."""
        current_index = self.pages.currentIndex()
        if current_index > 0:
            self.show_page(current_index - 1)

    def go_next(self):
        """Go to next page."""
        current_index = self.pages.currentIndex()
        if current_index < self.pages.count() - 1:
            # Validate current page before proceeding
            if self.validate_current_page():
                self.show_page(current_index + 1)

    def finish_setup(self):
        """Complete the setup process."""
        if self.validate_current_page():
            success = self._run_setup()
            if success:
                self.accept()  # Close dialog successfully
            # If setup failed, don't close dialog so user can try again

    def update_navigation_buttons(self):
        """Update navigation button states based on current page."""
        current_index = self.pages.currentIndex()
        total_pages = self.pages.count()

        # Update back button
        self.back_button.setEnabled(current_index > 0)

        # Update next/finish buttons
        if current_index == total_pages - 1:  # Last page
            self.next_button.setVisible(False)
            self.finish_button.setVisible(True)
        else:
            self.next_button.setVisible(True)
            self.finish_button.setVisible(False)

    def setup_background(self):
        """Apply watermark background."""
        apply_watermark_background(self)

    def resizeEvent(self, event):
        """Handle resize events to update background."""
        super().resizeEvent(event)
        # Update background when dialog is resized
        if hasattr(self, 'setup_background'):
            self.setup_background()

    def validate_current_page(self) -> bool:
        """Validate the current page before proceeding."""
        current_index = self.pages.currentIndex()

        if current_index == 1:  # User profile page
            return self.validate_user_profile_page()
        elif current_index == 3:  # Lab config page
            return self.validate_lab_config_page()
        elif current_index == 4:  # Conclusion page
            return True

        return True

    def validate_user_profile_page(self) -> bool:
        """Validate user profile page."""
        # Only validate if user explicitly chose to add/edit the profile this run
        if getattr(self, '_user_profile_edit_requested', False):
            if hasattr(self, 'user_profile_page') and hasattr(self.user_profile_page, 'validate_page'):
                return self.user_profile_page.validate_page()
            return True
        # No edit requested → skip validation
        return True

    def validate_lab_config_page(self) -> bool:
        """Validate lab configuration page."""
        # Add validation logic here
        return True

    def create_user_selection_page(self):
        """Create the user selection page."""
        page = UserSelectionPage()

        # When continuing, set active user and advance
        def _continue_with(user_id: str):
            try:
                set_active_config("user.id", user_id, scope="user")
            except Exception:
                pass
            self.selected_user_id = user_id
            self._user_profile_edit_requested = False
            # Move to lab selection (skip profile editing by default)
            self.show_page(2)  # index: 0 user-select, 1 profile, 2 lab-choice

        page.continue_requested.connect(_continue_with)

        # Add new → go to profile page (cleared)
        def _add_new():
            self.user_dto = None
            self._user_profile_edit_requested = True
            # Clear fields for fresh entry
            try:
                self.user_profile_page.name_edit.setText("")
                self.user_profile_page.email_edit.setText("")
                self.user_profile_page.organization_edit.setText("")
                self.user_profile_page.projects_dir_edit.setText("")
            except Exception:
                pass
            self.show_page(1)

        page.request_add.connect(_add_new)

        # Edit selected → load values into profile page then navigate
        def _edit_user(user_id: str):
            try:
                service = get_setup_service()
                all_users = service.get_all_users()
                data = all_users.get(user_id)
                if data and hasattr(self, 'user_profile_page'):
                    # Prefill fields
                    self.user_profile_page.name_edit.setText(data.get('name') or "")
                    self.user_profile_page.email_edit.setText(data.get('email') or "")
                    self.user_profile_page.organization_edit.setText(data.get('organization') or "")
                    proj_dir = data.get('default_projects_dir') or ""
                    self.user_profile_page.projects_dir_edit.setText(proj_dir)
            except Exception:
                pass
            self._user_profile_edit_requested = True
            self.show_page(1)

        page.request_edit.connect(_edit_user)

        # Delete selected → not implemented in repository; disable for now
        page.delete_btn.setEnabled(False)
        page.delete_btn.setToolTip("Delete user is not available yet")

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
        # Populate existing labs list for join flow
        try:
            labs = self.setup_service.get_labs() if self.setup_service else None
            if labs is not None and hasattr(page, 'populate_existing_labs'):
                page.populate_existing_labs(labs)
        except Exception:
            # Non-fatal if labs cannot be loaded here
            pass
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
            if getattr(self, '_user_profile_edit_requested', False):
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
                user_profile=self.user_dto if getattr(self, '_user_profile_edit_requested', False) else None,
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

def show_setup_wizard(parent=None, theme_manager=None) -> bool:
    """Show the MUS1 setup wizard dialog."""
    try:
        # Create and show the setup wizard dialog
        wizard_dialog = SetupWizardDialog(parent, theme_manager)

        # Show dialog and return success
        result = wizard_dialog.exec()

        # Return True if setup completed successfully
        return result == QDialog.DialogCode.Accepted

    except Exception as e:
        QMessageBox.critical(
            parent, "Setup Error",
            f"Failed to start setup wizard:\n\n{str(e)}"
        )
        return False
