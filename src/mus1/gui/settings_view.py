from .qt import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QComboBox, QFileDialog, QMessageBox,
    Qt, QCheckBox, QSlider
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
from ..core.setup_service import SharedStorageDTO


class SettingsView(BaseView):
    """Settings view for application-wide configuration."""

    def __init__(self, parent=None):
        super().__init__(parent, view_name="settings")
        self.setup_navigation(["User Settings", "Workers", "General Settings"])
        self.setup_user_settings_page()
        self.setup_workers_page()
        self.setup_general_settings_page()
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

        # Shared Storage Group (Global Configuration)
        storage_group, storage_layout = self.create_form_section("Shared Storage", layout)

        storage_row = self.create_form_row(storage_layout)
        storage_label = self.create_form_label("Shared Storage Root:")
        self.shared_storage_edit = QLineEdit()
        self.shared_storage_edit.setProperty("class", "mus1-text-input")
        self.shared_storage_btn = QPushButton("Browse...")
        self.shared_storage_btn.setProperty("class", "mus1-secondary-button")
        self.shared_storage_btn.clicked.connect(self._browse_shared_storage)
        storage_row.addWidget(storage_label)
        storage_row.addWidget(self.shared_storage_edit, 1)
        storage_row.addWidget(self.shared_storage_btn)

        storage_help = QLabel("Global shared storage root used for collaborative projects. Projects under this path will be discoverable by all users.")
        storage_help.setWordWrap(True)
        storage_help.setStyleSheet("color: gray; font-size: 11px;")
        storage_layout.addWidget(storage_help)

        # Lab Shared Library (per-lab storage root)
        lab_group, lab_layout = self.create_form_section("Lab Shared Library", layout)

        # Show currently selected lab
        lab_info_row = self.create_form_row(lab_layout)
        self.current_lab_label = self.create_form_label("Current Lab: (none)")
        lab_info_row.addWidget(self.current_lab_label)

        # Path editor for lab shared library
        lab_path_row = self.create_form_row(lab_layout)
        lab_path_label = self.create_form_label("Lab Library Root:")
        self.lab_library_edit = QLineEdit()
        self.lab_library_edit.setProperty("class", "mus1-text-input")
        lab_browse_btn = QPushButton("Browse...")
        lab_browse_btn.setProperty("class", "mus1-secondary-button")
        lab_browse_btn.clicked.connect(self._browse_lab_library)
        lab_path_row.addWidget(lab_path_label)
        lab_path_row.addWidget(self.lab_library_edit, 1)
        lab_path_row.addWidget(lab_browse_btn)

        lab_help = QLabel("Designate a lab-specific shared library root. Lab members and workers use this location for shared recordings and subjects.")
        lab_help.setWordWrap(True)
        lab_help.setStyleSheet("color: gray; font-size: 11px;")
        lab_layout.addWidget(lab_help)

        # Save lab library button
        lab_btn_row = self.create_button_row(lab_layout)
        save_lab_btn = QPushButton("Save Lab Library")
        save_lab_btn.setProperty("class", "mus1-primary-button")
        save_lab_btn.clicked.connect(self.handle_save_lab_library)
        lab_btn_row.addWidget(save_lab_btn)

        # Sharing mode and status
        mode_row = self.create_form_row(lab_layout)
        mode_row.addWidget(self.create_form_label("Sharing Mode:"))
        self.lab_sharing_mode_combo = QComboBox()
        self.lab_sharing_mode_combo.setProperty("class", "mus1-combo-box")
        self.lab_sharing_mode_combo.addItems(["always_on", "peer_hosted"])  # required, not optional
        mode_row.addWidget(self.lab_sharing_mode_combo)
        set_mode_btn = QPushButton("Set Mode")
        set_mode_btn.setProperty("class", "mus1-secondary-button")
        set_mode_btn.clicked.connect(self.handle_set_lab_sharing_mode)
        mode_row.addWidget(set_mode_btn)

        status_row = self.create_form_row(lab_layout)
        status_row.addWidget(self.create_form_label("Library Status:"))
        self.lab_library_status_label = QLabel("unknown")
        status_row.addWidget(self.lab_library_status_label)

        # Designate as Shared Library (validates and persists)
        designate_row = self.create_form_row(storage_layout)
        designate_btn = QPushButton("Designate as Shared Library")
        designate_btn.setProperty("class", "mus1-primary-button")
        designate_btn.clicked.connect(self.handle_designate_shared_library)
        designate_row.addWidget(designate_btn)

        # Save button
        button_row = self.create_button_row(layout)
        save_btn = QPushButton("Save User Settings")
        save_btn.setProperty("class", "mus1-primary-button")
        save_btn.clicked.connect(self.handle_save_user_settings)
        save_storage_btn = QPushButton("Save Storage Settings")
        save_storage_btn.setProperty("class", "mus1-primary-button")
        save_storage_btn.clicked.connect(self.handle_save_storage_settings)
        button_row.addWidget(save_btn)
        button_row.addWidget(save_storage_btn)

        layout.addStretch(1)
        self.add_page(self.user_settings_page, "User")

        # Load current user settings
        self.load_user_settings()


    def setup_workers_page(self):
        """Setup Workers management page (moved from ProjectView)."""
        self.workers_page = QWidget()
        layout = self.setup_page_layout(self.workers_page)

        # List existing workers
        self.workers_list = QListWidget()
        self.workers_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Workers", self.workers_list, layout)

        # Scope toggle: project-level vs lab-level workers
        scope_group, scope_layout = self.create_form_section("Scope", layout)
        scope_row = self.create_form_row(scope_layout)
        self.scope_workers_to_lab_check = QCheckBox("Scope workers to selected lab")
        self.scope_workers_to_lab_check.setChecked(False)
        self.scope_workers_to_lab_check.toggled.connect(lambda _c: self.refresh_workers_list())
        scope_row.addWidget(self.scope_workers_to_lab_check)

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

            # Load shared storage setting
            shared_storage_path = svc.get_shared_storage_path()
            if shared_storage_path:
                self.shared_storage_edit.setText(str(shared_storage_path))
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading user settings: {e}", "error")


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

    def _browse_shared_storage(self):
        """Browse for shared storage root directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Shared Storage Root")
        if directory:
            self.shared_storage_edit.setText(directory)

    def _browse_lab_library(self):
        """Browse for lab shared library root directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Lab Library Root")
        if directory:
            self.lab_library_edit.setText(directory)

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

    def handle_save_storage_settings(self):
        """Save shared storage settings."""
        try:
            from pathlib import Path
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()

            storage_path_str = self.shared_storage_edit.text().strip()
            if not storage_path_str:
                # Clear shared storage setting
                from ..core.config_manager import set_config
                set_config("storage.shared_root", None, scope="user")
                self.navigation_pane.add_log_message("Shared storage cleared", "success")
                return

            storage_path = Path(storage_path_str)

            # Validate the path exists and is a directory
            if not storage_path.exists() or not storage_path.is_dir():
                self.navigation_pane.add_log_message(f"Invalid shared storage path: {storage_path}", "error")
                return

            # Configure shared storage
            result = svc.setup_shared_storage(
                SharedStorageDTO(
                    path=storage_path,
                    create_if_missing=False,  # Directory should already exist
                    verify_permissions=True
                )
            )

            if result.get("success"):
                self.navigation_pane.add_log_message("Shared storage settings saved successfully", "success")
            else:
                self.navigation_pane.add_log_message(result.get("message", "Failed to save shared storage settings"), "error")

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error saving shared storage settings: {e}", "error")

    def handle_designate_shared_library(self):
        """Validate and set the shared library root using SetupService helper."""
        try:
            from pathlib import Path
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()

            storage_path_str = self.shared_storage_edit.text().strip()
            if not storage_path_str:
                self.navigation_pane.add_log_message("Please enter a path to designate as shared library.", "warning")
                return
            storage_path = Path(storage_path_str)
            result = svc.designate_shared_folder(storage_path, ensure_exists=True, verify_permissions=True)
            if result.get("success"):
                self.navigation_pane.add_log_message("Shared library designated successfully.", "success")
            else:
                self.navigation_pane.add_log_message(result.get("message", "Failed to designate shared library"), "error")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Designate shared library failed: {e}", "error")

    def handle_save_lab_library(self):
        """Save per-lab shared library root (lab storage root)."""
        try:
            # Determine current lab
            lab_id = getattr(self.window(), 'selected_lab_id', None)
            if not lab_id:
                self.navigation_pane.add_log_message("No lab selected. Select a lab first (User/Lab dialog).", "warning")
                return

            path_str = self.lab_library_edit.text().strip()
            if not path_str:
                self.navigation_pane.add_log_message("Please enter a lab library path.", "warning")
                return

            from pathlib import Path as _P
            path = _P(path_str)
            if not path.exists() or not path.is_dir():
                self.navigation_pane.add_log_message(f"Invalid lab library path: {path}", "error")
                return

            # Persist via SetupService → ConfigManager
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            result = svc.set_lab_storage_root(lab_id, path)
            if result.get("success"):
                self.navigation_pane.add_log_message("Lab library saved successfully.", "success")
            else:
                self.navigation_pane.add_log_message(result.get("message", "Failed to save lab library"), "error")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error saving lab library: {e}", "error")


    def refresh_workers_list(self):
        """Refresh the workers list."""
        if not hasattr(self, 'workers_list'):
            return
        self.workers_list.clear()
        try:
            # Get workers from project manager config
            pm = self.window().project_manager
            if pm:
                # Determine scope
                use_lab_scope = getattr(self, 'scope_workers_to_lab_check', None) and self.scope_workers_to_lab_check.isChecked()
                if use_lab_scope and hasattr(self.window(), 'selected_lab_id') and self.window().selected_lab_id:
                    lab_id = self.window().selected_lab_id
                    lab_workers_map = pm.config.settings.get('lab_workers', {}) or {}
                    workers = lab_workers_map.get(lab_id, [])
                else:
                    workers = pm.config.settings.get('workers', [])
            else:
                workers = []
        except Exception:
            workers = []
        for w in workers:
            item = QListWidgetItem(f"{w.get('name', '')}  alias={w.get('ssh_alias', '')}  role={w.get('role', '') or ''}  provider={w.get('provider', '')}")
            item.setData(Qt.ItemDataRole.UserRole, w.get('name', ''))
            self.workers_list.addItem(item)

    def handle_set_lab_sharing_mode(self):
        """Persist lab sharing mode and refresh status."""
        try:
            lab_id = getattr(self.window(), 'selected_lab_id', None)
            if not lab_id:
                self.navigation_pane.add_log_message("No lab selected. Select a lab first (User/Lab dialog).", "warning")
                return
            mode = self.lab_sharing_mode_combo.currentText()
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            res = svc.set_lab_sharing_preferences(lab_id, mode)
            if res.get("success"):
                self.navigation_pane.add_log_message(f"Lab sharing mode set to {mode}", "success")
                self._refresh_lab_library_status()
            else:
                self.navigation_pane.add_log_message(res.get("message", "Failed to set sharing mode"), "error")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error setting lab sharing mode: {e}", "error")

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

            # Determine scope
            use_lab_scope = getattr(self, 'scope_workers_to_lab_check', None) and self.scope_workers_to_lab_check.isChecked()
            workers = None
            lab_id = None
            if use_lab_scope and hasattr(self.window(), 'selected_lab_id') and self.window().selected_lab_id:
                lab_id = self.window().selected_lab_id
                lab_workers_map = pm.config.settings.get('lab_workers', {}) or {}
                workers = list(lab_workers_map.get(lab_id, []))
            else:
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
            if use_lab_scope and lab_id:
                lab_workers_map = pm.config.settings.get('lab_workers', {}) or {}
                lab_workers_map[lab_id] = workers
                pm.config.settings['lab_workers'] = lab_workers_map
            else:
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

            # Determine scope
            use_lab_scope = getattr(self, 'scope_workers_to_lab_check', None) and self.scope_workers_to_lab_check.isChecked()
            workers = None
            lab_id = None
            if use_lab_scope and hasattr(self.window(), 'selected_lab_id') and self.window().selected_lab_id:
                lab_id = self.window().selected_lab_id
                lab_workers_map = pm.config.settings.get('lab_workers', {}) or {}
                workers = list(lab_workers_map.get(lab_id, []))
            else:
                workers = pm.config.settings.get('workers', [])
            before = len(workers)
            workers = [w for w in workers if w.get('name') != name]
            if use_lab_scope and lab_id:
                lab_workers_map = pm.config.settings.get('lab_workers', {}) or {}
                lab_workers_map[lab_id] = workers
                pm.config.settings['lab_workers'] = lab_workers_map
            else:
                pm.config.settings['workers'] = workers
            if len(workers) == before:
                QMessageBox.information(self, "Workers", f"No worker named '{name}' found.")
                return
            pm.save_project()
            self.refresh_workers_list()
            self.navigation_pane.add_log_message(f"Removed worker {name}", "success")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Remove worker failed: {e}", "error")

    def setup_general_settings_page(self):
        """Setup the General Settings page with application-wide settings."""
        self.general_settings_page = QWidget()
        layout = self.setup_page_layout(self.general_settings_page)

        # 1. Display Settings Group
        display_group, display_layout = self.create_form_section("Display Settings", layout)
        theme_row = self.create_form_row(display_layout)
        theme_label = self.create_form_label("Application Theme:")
        self.theme_dropdown = QComboBox()
        self.theme_dropdown.setProperty("class", "mus1-combo-box")
        self.theme_dropdown.addItems(["dark", "light", "os"])
        theme_button = QPushButton("Apply Theme")
        theme_button.setProperty("class", "mus1-primary-button")
        theme_button.clicked.connect(lambda: self.handle_change_theme(self.theme_dropdown.currentText()))
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_dropdown, 1)
        theme_row.addWidget(theme_button)

        # 2. List Sort Settings Group
        sort_group, sort_layout = self.create_form_section("List Sort Settings", layout)
        sort_row = self.create_form_row(sort_layout)
        sort_label = self.create_form_label("Global Sort Mode:")
        self.sort_mode_dropdown = QComboBox()
        self.sort_mode_dropdown.setProperty("class", "mus1-combo-box")
        self.sort_mode_dropdown.addItems([
            "Newest First",
            "Recording Date",
            "ID Order",
            "By Type"
        ])
        sort_row.addWidget(sort_label)
        sort_row.addWidget(self.sort_mode_dropdown, 1)
        apply_sort_mode_button = QPushButton("Apply Sort Mode")
        apply_sort_mode_button.setProperty("class", "mus1-primary-button")
        apply_sort_mode_button.clicked.connect(lambda: self.on_sort_mode_changed(self.sort_mode_dropdown.currentText()))
        sort_row.addWidget(apply_sort_mode_button)

        # 3. Video Settings Group
        video_group, video_layout = self.create_form_section("Video Settings", layout)

        # Create the frame rate row first
        frame_rate_row = self.create_form_row(video_layout)

        self.enable_frame_rate_checkbox = QCheckBox("Enable Global Frame Rate")
        self.enable_frame_rate_checkbox.setChecked(False)

        self.frame_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_rate_slider.setRange(0, 120)
        self.frame_rate_slider.setValue(60)
        self.frame_rate_slider.setProperty("mus1-slider", True)
        self.frame_rate_slider.setEnabled(False)
        self.enable_frame_rate_checkbox.toggled.connect(self.frame_rate_slider.setEnabled)

        # Create a label to display the current slider value
        self.frame_rate_value_label = QLabel(str(self.frame_rate_slider.value()))
        self.frame_rate_value_label.setFixedWidth(40)  # Fixed width for consistent UI sizing
        self.frame_rate_slider.valueChanged.connect(lambda val: self.frame_rate_value_label.setText(str(val)))

        frame_rate_row.addWidget(self.enable_frame_rate_checkbox)
        frame_rate_row.addWidget(self.frame_rate_slider, 1)  # Slider with stretch factor
        frame_rate_row.addWidget(self.frame_rate_value_label)
        apply_frame_rate_button = QPushButton("Apply Frame Rate")
        apply_frame_rate_button.setProperty("class", "mus1-primary-button")
        apply_frame_rate_button.clicked.connect(self.handle_apply_frame_rate)
        frame_rate_row.addWidget(apply_frame_rate_button)

        help_label = QLabel("When enabled, this global frame rate will be used for all files unless explicitly overridden.")
        help_label.setWordWrap(True)
        help_label.setProperty("class", "mus1-help-text")
        help_label.setVisible(False)
        video_layout.addWidget(help_label)

        self.enable_frame_rate_checkbox.toggled.connect(lambda checked: help_label.setVisible(checked))

        apply_button_row = self.create_button_row(layout)
        apply_settings_button = QPushButton("Apply All Settings")
        apply_settings_button.setProperty("class", "mus1-primary-button")
        apply_settings_button.clicked.connect(self.handle_apply_general_settings)
        apply_button_row.addWidget(apply_settings_button)

        layout.addStretch(1)
        self.add_page(self.general_settings_page, "General Settings")

        # Initialize settings from state
        self.update_sort_mode_from_state()
        self.update_frame_rate_from_state()

    def handle_apply_general_settings(self):
        """Apply the general settings."""
        # First, apply the theme based on the theme dropdown
        theme_choice = self.theme_dropdown.currentText()

        # Retrieve other settings from the UI
        sort_mode = self.sort_mode_dropdown.currentText()
        frame_rate_enabled = self.enable_frame_rate_checkbox.isChecked()
        frame_rate = self.frame_rate_slider.value()  # Get value from slider instead of spin box

        # Create settings dictionary with all values
        settings = {
            "theme_mode": theme_choice,
            "global_sort_mode": sort_mode,
            "global_frame_rate_enabled": frame_rate_enabled,
            "global_frame_rate": frame_rate
        }

        # Update settings using project config
        if self.window().project_manager:
            self.window().project_manager.config.settings.update(settings)
            # Save the project to persist these settings
            self.window().project_manager.save_project()

            # Call through MainWindow to propagate theme changes across the application
            self.window().change_theme(theme_choice)

        self.navigation_pane.add_log_message("Applied general settings to current project.", "success")

    def handle_apply_frame_rate(self):
        """Handle the 'Apply Frame Rate' button click."""
        frame_rate_enabled = self.enable_frame_rate_checkbox.isChecked()
        frame_rate = self.frame_rate_slider.value()

        # Create settings dictionary with frame rate values
        settings = {
            "global_frame_rate_enabled": frame_rate_enabled,
            "global_frame_rate": frame_rate
        }

        # Update settings using project config
        if self.window().project_manager:
            self.window().project_manager.config.settings.update(settings)
            # Save project to persist changes
            self.window().project_manager.save_project()

        self.navigation_pane.add_log_message(f"Applied frame rate settings: {'Enabled' if frame_rate_enabled else 'Disabled'}, {frame_rate} fps", "success")

    def on_sort_mode_changed(self, new_sort_mode: str):
        """Update the project config's global_sort_mode and refresh data."""
        if self.window().project_manager:
            # Update sort mode using project config
            self.window().project_manager.config.settings["global_sort_mode"] = new_sort_mode
            # Save project to persist changes
            self.window().project_manager.save_project()

            # Refresh lists to show new sorting (repositories will use the updated sort mode)
            self.refresh_lists()

    def handle_change_theme(self, theme_choice: str):
        """
        UI handler for theme change requests, delegates actual change to MainWindow.
        """
        main_window = self.window()
        if main_window:
            main_window.change_theme(theme_choice)

    def update_frame_rate_from_state(self):
        """Update frame rate settings from the current state using DataManager resolution."""
        # Frame rate management is not implemented in the new architecture yet
        # Set default values for now
        frame_rate_enabled = False
        display_rate = 60  # Default frame rate

        # Update UI elements if they exist
        if hasattr(self, 'frame_rate_slider'):
             # Ensure value is within slider range
             display_rate = max(self.frame_rate_slider.minimum(), min(display_rate, self.frame_rate_slider.maximum()))
             self.frame_rate_slider.setValue(display_rate)
        if hasattr(self, 'enable_frame_rate_checkbox'):
            # Block signals temporarily to avoid triggering handler during update
            self.enable_frame_rate_checkbox.blockSignals(True)
            self.enable_frame_rate_checkbox.setChecked(frame_rate_enabled)
            self.enable_frame_rate_checkbox.blockSignals(False)

        self.navigation_pane.add_log_message("Frame rate management not yet implemented in clean architecture.", "info")
        if hasattr(self, 'frame_rate_value_label'):
             self.frame_rate_value_label.setText(str(display_rate))

    def update_sort_mode_from_state(self):
        """Update sort mode dropdown from the current state."""
        # Check if we have the sort mode dropdown
        if not hasattr(self, 'sort_mode_dropdown'):
            return

        # Get current sort mode from project config, default to "Newest First"
        pm = self.window().project_manager if self.window() else None
        if pm:
            current_sort_mode = pm.config.settings.get("global_sort_mode", "Newest First")
            index = self.sort_mode_dropdown.findText(current_sort_mode)
            if index >= 0:
                self.sort_mode_dropdown.setCurrentIndex(index)
        else:
            # Default to first item if no project loaded
            self.sort_mode_dropdown.setCurrentIndex(0)

        self.navigation_pane.add_log_message("Sort mode loaded from project settings.", "info")

    def update_theme_dropdown_from_state(self):
        """Update theme dropdown based on current theme setting"""
        if not hasattr(self, 'theme_dropdown'):
            return

        # Get current theme from config manager
        try:
            from ..core.config_manager import get_config_manager
            config_manager = get_config_manager()
            current_theme = config_manager.get("ui.theme", "dark")  # Default to dark

            # Update dropdown to match current theme
            index = self.theme_dropdown.findText(current_theme)
            if index >= 0:
                self.theme_dropdown.setCurrentIndex(index)
                self.navigation_pane.add_log_message(f"Theme dropdown set to: {current_theme}", "info")
            else:
                self.navigation_pane.add_log_message(f"Theme '{current_theme}' not found in dropdown options", "warning")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading theme setting: {e}", "error")

    def refresh_lists(self):
        """Refresh all lists in the settings view."""
        self.load_user_settings()
        self.refresh_workers_list()
        # Initialize general settings from state
        self.update_sort_mode_from_state()
        self.update_frame_rate_from_state()
        self.update_theme_dropdown_from_state()

        # Also refresh shared storage setting
        try:
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            shared_storage_path = svc.get_shared_storage_path()
            if shared_storage_path and hasattr(self, 'shared_storage_edit'):
                self.shared_storage_edit.setText(str(shared_storage_path))
        except Exception:
            pass

        # Refresh current lab and lab library path
        try:
            lab_id = getattr(self.window(), 'selected_lab_id', None)
            if hasattr(self, 'current_lab_label'):
                self.current_lab_label.setText(f"Current Lab: {lab_id or '(none)'}")
            if lab_id and hasattr(self, 'lab_library_edit'):
                from ..core.config_manager import get_lab_storage_root
                lab_root = get_lab_storage_root(lab_id)
                if lab_root:
                    self.lab_library_edit.setText(str(lab_root))
            # Update sharing mode and status
            if lab_id and hasattr(self, 'lab_sharing_mode_combo'):
                from ..core.config_manager import get_lab_sharing_mode
                mode = get_lab_sharing_mode(lab_id) or "always_on"
                idx = self.lab_sharing_mode_combo.findText(mode)
                if idx >= 0:
                    self.lab_sharing_mode_combo.setCurrentIndex(idx)
                self._refresh_lab_library_status()
        except Exception:
            pass

    def _refresh_lab_library_status(self):
        """Refresh label showing online/offline status for current lab library."""
        try:
            lab_id = getattr(self.window(), 'selected_lab_id', None)
            if not lab_id or not hasattr(self, 'lab_library_status_label'):
                return
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            st = svc.get_lab_library_online_status(lab_id)
            if st.get("success"):
                online = st.get("online")
                path = st.get("path")
                reason = st.get("reason")
                mode = st.get("mode") or "always_on"
                txt = f"{ 'online' if online else 'offline' } ({mode})"
                if path:
                    txt += f" — {path}"
                if not online and reason:
                    txt += f" — {reason}"
                self.lab_library_status_label.setText(txt)
            else:
                self.lab_library_status_label.setText("unknown")
        except Exception:
            pass
