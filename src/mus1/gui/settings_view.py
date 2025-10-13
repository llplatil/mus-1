from .qt import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QComboBox, QFileDialog, QMessageBox,
    Qt
)
"""
Settings View - GUI for application-wide settings including users, labs, and workers.

This view provides centralized management for:
- User settings and preferences
- Lab configuration and management
- Worker configuration for distributed processing
"""

from pathlib import Path
from .base_view import BaseView
from typing import Dict, Any


class SettingsView(BaseView):
    """Settings view for application-wide configuration."""

    def __init__(self, parent=None):
        super().__init__(parent, view_name="settings")
        self.setup_navigation(["User Settings", "Lab Settings", "Workers"])
        self.setup_user_settings_page()
        self.setup_lab_settings_page()
        self.setup_workers_page()
        # Do not change pages here; lifecycle handles activation

    # --- Lifecycle hooks ---
    def on_services_ready(self, services):
        super().on_services_ready(services)

    def on_activated(self):
        # Refresh lists when settings tab becomes active
        self.refresh_lists()

    def setup_user_settings_page(self):
        """Setup the User Settings page."""
        self.user_settings_page = QWidget()
        layout = self.setup_page_layout(self.user_settings_page)

        # User Profile Group
        profile_group, profile_layout = self.create_form_section("User Profile", layout)

        # Create labeled input rows using helper method
        self.user_name_edit = QLineEdit()
        self.user_name_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Name:", self.user_name_edit, profile_layout)

        self.user_email_edit = QLineEdit()
        self.user_email_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Email:", self.user_email_edit, profile_layout)

        self.user_org_edit = QLineEdit()
        self.user_org_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Organization:", self.user_org_edit, profile_layout)

        # Default Directories Group
        dirs_group, dirs_layout = self.create_form_section("Default Directories", layout)

        # Projects directory row
        projects_row = self.create_form_row(dirs_layout)
        projects_label = self.create_form_label("Projects Directory:")
        self.projects_dir_edit = QLineEdit()
        self.projects_dir_edit.setProperty("class", "mus1-text-input")
        self.projects_dir_btn = QPushButton("Browse...")
        self.projects_dir_btn.setProperty("class", "mus1-secondary-button")
        self.projects_dir_btn.clicked.connect(self._browse_projects_dir)
        projects_row.addWidget(projects_label)
        projects_row.addWidget(self.projects_dir_edit, 1)
        projects_row.addWidget(self.projects_dir_btn)

        # Shared directory row
        shared_row = self.create_form_row(dirs_layout)
        shared_label = self.create_form_label("Shared Directory:")
        self.shared_dir_edit = QLineEdit()
        self.shared_dir_edit.setProperty("class", "mus1-text-input")
        self.shared_dir_btn = QPushButton("Browse...")
        self.shared_dir_btn.setProperty("class", "mus1-secondary-button")
        self.shared_dir_btn.clicked.connect(self._browse_shared_dir)
        shared_row.addWidget(shared_label)
        shared_row.addWidget(self.shared_dir_edit, 1)
        shared_row.addWidget(self.shared_dir_btn)

        # Save button
        button_row = self.create_button_row(layout)
        save_btn = QPushButton("Save User Settings")
        save_btn.setProperty("class", "mus1-primary-button")
        save_btn.clicked.connect(self.handle_save_user_settings)
        button_row.addWidget(save_btn)

        layout.addStretch(1)
        self.add_page(self.user_settings_page, "User")

        # Load current user settings
        self.load_user_settings()

    def setup_lab_settings_page(self):
        """Setup the Lab Settings page."""
        self.lab_settings_page = QWidget()
        layout = self.setup_page_layout(self.lab_settings_page)

        # Labs List Group
        self.labs_list = QListWidget()
        self.labs_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Your Labs", self.labs_list, layout)

        # Lab Details Group
        details_group, details_layout = self.create_form_section("Lab Details", layout)

        # Create labeled input rows using helper method
        self.lab_name_edit = QLineEdit()
        self.lab_name_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Name:", self.lab_name_edit, details_layout)

        self.lab_institution_edit = QLineEdit()
        self.lab_institution_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Institution:", self.lab_institution_edit, details_layout)

        self.lab_pi_edit = QLineEdit()
        self.lab_pi_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("PI Name:", self.lab_pi_edit, details_layout)

        # Projects in Lab Group
        self.lab_projects_list = QListWidget()
        self.lab_projects_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Projects in Lab", self.lab_projects_list, layout)

        # Action buttons
        button_row = self.create_button_row(layout)
        create_btn = QPushButton("Create New Lab")
        create_btn.setProperty("class", "mus1-primary-button")
        create_btn.clicked.connect(self.handle_create_lab)
        button_row.addWidget(create_btn)

        update_btn = QPushButton("Update Lab")
        update_btn.setProperty("class", "mus1-secondary-button")
        update_btn.clicked.connect(self.handle_update_lab)
        button_row.addWidget(update_btn)

        layout.addStretch(1)
        self.add_page(self.lab_settings_page, "Labs")

        # Connect lab selection
        self.labs_list.itemSelectionChanged.connect(self.on_lab_selected)

        # Load labs
        self.load_labs()

    def setup_workers_page(self):
        """Setup Workers management page (moved from ProjectView)."""
        self.workers_page = QWidget()
        layout = self.setup_page_layout(self.workers_page)

        # List existing workers
        self.workers_list = QListWidget()
        self.workers_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Workers", self.workers_list, layout)

        # Add form
        form_group, form_layout = self.create_form_section("Add Worker", layout)

        # First row: Name and SSH Alias
        r1 = self.create_form_row(form_layout)
        self.worker_name_edit = QLineEdit()
        self.worker_name_edit.setProperty("class", "mus1-text-input")
        r1.addWidget(self.create_form_label("Name:"))
        r1.addWidget(self.worker_name_edit)

        self.worker_ssh_alias_edit = QLineEdit()
        self.worker_ssh_alias_edit.setProperty("class", "mus1-text-input")
        r1.addWidget(self.create_form_label("SSH Alias:"))
        r1.addWidget(self.worker_ssh_alias_edit)

        # Second row: Role and Provider
        r2 = self.create_form_row(form_layout)
        self.worker_role_edit = QLineEdit()
        self.worker_role_edit.setProperty("class", "mus1-text-input")
        r2.addWidget(self.create_form_label("Role:"))
        r2.addWidget(self.worker_role_edit)

        self.worker_provider_combo = QComboBox()
        self.worker_provider_combo.setProperty("class", "mus1-combo-box")
        self.worker_provider_combo.addItems(["ssh", "wsl"])
        r2.addWidget(self.create_form_label("Provider:"))
        r2.addWidget(self.worker_provider_combo)

        btn_row = self.create_button_row(layout)
        add_btn = QPushButton("Add Worker")
        add_btn.setProperty("class", "mus1-primary-button")
        add_btn.clicked.connect(self.handle_add_worker)
        rem_btn = QPushButton("Remove Selected Worker")
        rem_btn.setProperty("class", "mus1-secondary-button")
        rem_btn.clicked.connect(self.handle_remove_worker)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)

        layout.addStretch(1)
        self.add_page(self.workers_page, "Workers")

        self.refresh_workers_list()

    def load_user_settings(self):
        """Load current user settings."""
        try:
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            profile = svc.get_user_profile()
            if profile:
                self.user_name_edit.setText(profile.name or "")
                self.user_email_edit.setText(profile.email or "")
                self.user_org_edit.setText(profile.organization or "")
                self.projects_dir_edit.setText(str(profile.default_projects_dir or ""))
                self.shared_dir_edit.setText(str(profile.default_shared_dir or ""))
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading user settings: {e}", "error")

    def load_labs(self):
        """Load user's labs."""
        try:
            from ..core.setup_service import get_setup_service
            setup_service = get_setup_service()
            labs = setup_service.get_labs()

            self.labs_list.clear()
            for lab_id, lab_data in labs.items():
                display_text = f"{lab_data['name']} ({lab_data.get('institution', 'Unknown')})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, lab_id)
                item.setData(Qt.ItemDataRole.UserRole + 1, lab_data)
                self.labs_list.addItem(item)
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading labs: {e}", "error")

    def on_lab_selected(self):
        """Handle lab selection."""
        current_item = self.labs_list.currentItem()
        if not current_item:
            return

        lab_data = current_item.data(Qt.ItemDataRole.UserRole + 1)
        self.lab_name_edit.setText(lab_data.get('name', ''))
        self.lab_institution_edit.setText(lab_data.get('institution', ''))
        self.lab_pi_edit.setText(lab_data.get('pi_name', ''))

        # Load projects for this lab
        self.lab_projects_list.clear()
        projects = lab_data.get('projects', [])
        for project in projects:
            item = QListWidgetItem(f"{project['name']} - {project['path']}")
            self.lab_projects_list.addItem(item)

    def _browse_projects_dir(self):
        """Browse for projects directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Projects Directory")
        if directory:
            self.projects_dir_edit.setText(directory)

    def _browse_shared_dir(self):
        """Browse for shared directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Shared Directory")
        if directory:
            self.shared_dir_edit.setText(directory)

    def handle_save_user_settings(self):
        """Save user settings."""
        try:
            from pathlib import Path
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            result = svc.update_user_profile(
                name=self.user_name_edit.text().strip() or None,
                organization=self.user_org_edit.text().strip() or None,
                default_projects_dir=Path(self.projects_dir_edit.text().strip()) if self.projects_dir_edit.text().strip() else None,
                default_shared_dir=Path(self.shared_dir_edit.text().strip()) if self.shared_dir_edit.text().strip() else None,
            )
            if result.get("success"):
                self.navigation_pane.add_log_message("User settings saved successfully", "success")
            else:
                self.navigation_pane.add_log_message(result.get("message", "Failed to save user settings"), "error")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error saving user settings: {e}", "error")

    def handle_create_lab(self):
        """Create a new lab."""
        try:
            from ..core.setup_service import get_setup_service, LabDTO
            from ..core.config_manager import get_config

            lab_name = self.lab_name_edit.text().strip()
            if not lab_name:
                QMessageBox.warning(self, "Validation Error", "Lab name is required")
                return

            # Generate lab ID from name
            lab_id = lab_name.lower().replace(' ', '_').replace('-', '_')

            # Get current user as creator
            user_id = get_config("user.id", scope="user")
            if not user_id:
                QMessageBox.warning(self, "Error", "No user configured")
                return

            lab_dto = LabDTO(
                id=lab_id,
                name=lab_name,
                institution=self.lab_institution_edit.text().strip(),
                pi_name=self.lab_pi_edit.text().strip(),
                creator_id=user_id
            )

            setup_service = get_setup_service()
            result = setup_service.create_lab(lab_dto)

            if result["success"]:
                self.navigation_pane.add_log_message(f"Lab '{lab_name}' created successfully", "success")
                self.load_labs()  # Refresh the list
                # Clear form
                self.lab_name_edit.clear()
                self.lab_institution_edit.clear()
                self.lab_pi_edit.clear()
            else:
                QMessageBox.warning(self, "Error", result["message"])

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error creating lab: {e}", "error")

    def handle_update_lab(self):
        """Update selected lab."""
        current_item = self.labs_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a lab to update.")
            return

        lab_id = current_item.data(Qt.ItemDataRole.UserRole)
        lab_name = self.lab_name_edit.text().strip()
        institution = self.lab_institution_edit.text().strip()
        pi_name = self.lab_pi_edit.text().strip()

        if not lab_name:
            QMessageBox.warning(self, "Validation Error", "Lab name is required.")
            return

        try:
            from ..core.setup_service import get_setup_service
            setup_service = get_setup_service()

            # Update lab in the database
            result = setup_service.update_lab(lab_id, name=lab_name, institution=institution, pi_name=pi_name)

            if result["success"]:
                self.navigation_pane.add_log_message(f"Lab '{lab_name}' updated successfully", "success")
                self.load_labs()  # Refresh the list
                # Clear form
                self.lab_name_edit.clear()
                self.lab_institution_edit.clear()
                self.lab_pi_edit.clear()
            else:
                QMessageBox.warning(self, "Update Failed", result["message"])

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error updating lab: {e}", "error")

    def refresh_workers_list(self):
        """Refresh the workers list."""
        if not hasattr(self, 'workers_list'):
            return
        self.workers_list.clear()
        try:
            # Get workers from project manager config
            pm = self.window().project_manager
            if pm:
                workers = pm.config.settings.get('workers', [])
            else:
                workers = []
        except Exception:
            workers = []
        for w in workers:
            item = QListWidgetItem(f"{w.get('name', '')}  alias={w.get('ssh_alias', '')}  role={w.get('role', '') or ''}  provider={w.get('provider', '')}")
            item.setData(Qt.ItemDataRole.UserRole, w.get('name', ''))
            self.workers_list.addItem(item)

    def handle_add_worker(self):
        """Add a new worker."""
        try:
            name = self.worker_name_edit.text().strip()
            alias = self.worker_ssh_alias_edit.text().strip()
            role = self.worker_role_edit.text().strip() or None
            provider = self.worker_provider_combo.currentText().strip()
            if not name or not alias:
                QMessageBox.warning(self, "Workers", "Name and SSH alias are required.")
                return

            pm = self.window().project_manager
            if not pm:
                QMessageBox.warning(self, "Workers", "No project loaded.")
                return

            workers = pm.config.settings.get('workers', [])
            if any(w.get('name') == name for w in workers):
                QMessageBox.warning(self, "Workers", f"Worker '{name}' already exists.")
                return
            worker_dict = {
                'name': name,
                'ssh_alias': alias,
                'role': role,
                'provider': provider
            }
            workers.append(worker_dict)
            pm.config.settings['workers'] = workers
            pm.save_project()
            self.refresh_workers_list()
            self.navigation_pane.add_log_message(f"Added worker {name}", "success")
            # Clear form
            self.worker_name_edit.clear()
            self.worker_ssh_alias_edit.clear()
            self.worker_role_edit.clear()
        except Exception as e:
            self.navigation_pane.add_log_message(f"Add worker failed: {e}", "error")

    def handle_remove_worker(self):
        """Remove selected worker."""
        try:
            item = self.workers_list.currentItem()
            if not item:
                QMessageBox.information(self, "Workers", "Select a worker to remove.")
                return
            name = item.data(Qt.ItemDataRole.UserRole)

            pm = self.window().project_manager
            if not pm:
                QMessageBox.warning(self, "Workers", "No project loaded.")
                return

            workers = pm.config.settings.get('workers', [])
            before = len(workers)
            workers = [w for w in workers if w.get('name') != name]
            pm.config.settings['workers'] = workers
            if len(workers) == before:
                QMessageBox.information(self, "Workers", f"No worker named '{name}' found.")
                return
            pm.save_project()
            self.refresh_workers_list()
            self.navigation_pane.add_log_message(f"Removed worker {name}", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Remove worker failed: {e}", "error")

    def refresh_lists(self):
        """Refresh all lists in the settings view."""
        self.load_user_settings()
        self.load_labs()
        self.refresh_workers_list()
