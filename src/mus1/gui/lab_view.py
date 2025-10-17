from .qt import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QComboBox, QFileDialog, QMessageBox,
    Qt, QCheckBox, QSlider, QGroupBox
)
"""
Lab View - GUI for lab-wide management including colonies, shared projects, and lab settings.

This view provides centralized management for:
- Colony management within labs
- Shared projects accessible to lab members
- Lab member management
- Lab settings and configuration
"""

from pathlib import Path
from .base_view import BaseView
from typing import Dict, Any


class LabView(BaseView):
    """Lab view for lab-wide management and configuration."""

    def __init__(self, parent=None):
        super().__init__(parent, view_name="lab")
        self.lab_service = None
        self.setup_navigation(["Colonies", "Lab Library", "Shared Projects", "Lab Members", "Lab Settings"])
        self.setup_colonies_page()
        self.setup_lab_library_page()
        self.setup_shared_projects_page()
        self.setup_lab_members_page()
        self.setup_lab_settings_page()
        # Do not change pages here; lifecycle handles activation

    # --- Lifecycle hooks ---
    def on_services_ready(self, services):
        super().on_services_ready(services)
        # Services is the factory, create our lab service
        self.lab_service = services.create_lab_service()
        self.navigation_pane.add_log_message("LabView services ready", "info")

    def on_activated(self):
        # Refresh data when lab tab becomes active
        self.refresh_lab_data()

        # Auto-select the lab that was chosen in user/lab selection dialog
        main_window = self.window()
        if main_window and hasattr(main_window, 'selected_lab_id') and main_window.selected_lab_id:
            self.navigation_pane.add_log_message(f"Auto-selecting lab: {main_window.selected_lab_id}", "info")
            # Try immediate selection first
            self._delayed_auto_select(main_window.selected_lab_id)
        else:
            self.navigation_pane.add_log_message("No lab selected from user/lab dialog", "warning")

    def _delayed_auto_select(self, lab_id: str):
        """Delayed auto-selection after labs are loaded."""
        from .qt import QTimer
        # Use a short timer to ensure labs are fully loaded
        QTimer.singleShot(100, lambda: self._do_auto_select(lab_id))

    def _do_auto_select(self, lab_id: str):
        """Automatically select the lab with the given ID in the labs list and load associated data."""
        if not hasattr(self, 'labs_list'):
            self.navigation_pane.add_log_message("labs_list not available for auto-select", "error")
            return

        self.navigation_pane.add_log_message(f"Looking for lab {lab_id} in {self.labs_list.count()} items", "info")

        # Find the item with matching lab_id
        for i in range(self.labs_list.count()):
            item = self.labs_list.item(i)
            item_lab_id = item.data(Qt.ItemDataRole.UserRole) if item else None
            self.navigation_pane.add_log_message(f"Item {i}: {item_lab_id}", "info")
            if item and item_lab_id == lab_id:
                self.labs_list.setCurrentItem(item)
                self.navigation_pane.add_log_message(f"Auto-selected lab: {item.text()}", "info")

                # Now load lab-specific data for the selected lab
                self.navigation_pane.add_log_message(f"Lab selected, loading lab-specific data", "info")
                self.load_colonies()
                self.load_shared_projects()
                self.load_lab_members()
                return

        self.navigation_pane.add_log_message(f"Lab {lab_id} not found in labs list", "warning")

    def setup_colonies_page(self):
        """Setup the Colonies page for managing colonies within the lab."""
        self.colonies_page = QWidget()
        layout = self.setup_page_layout(self.colonies_page)

        # Colonies List Group
        self.colonies_list = QListWidget()
        self.colonies_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Lab Colonies", self.colonies_list, layout)

        # Colony Details Group
        details_group, details_layout = self.create_form_section("Colony Details", layout)

        # Create labeled input rows using helper method
        self.colony_name_edit = QLineEdit()
        self.colony_name_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Colony Name:", self.colony_name_edit, details_layout)

        self.colony_strain_edit = QLineEdit()
        self.colony_strain_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Background Strain:", self.colony_strain_edit, details_layout)

        self.colony_gene_edit = QLineEdit()
        self.colony_gene_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Gene of Interest:", self.colony_gene_edit, details_layout)

        # Genotype Distribution Group
        genotype_group, genotype_layout = self.create_form_section("Genotype Distribution", layout)

        # Show the three genotypes that exist within this colony for the gene of interest
        genotype_info = QLabel("Within this colony, subjects will have genotypes: KO, HET, WT\nfor the gene of interest. Cross-breeding maintains this distribution.")
        genotype_info.setWordWrap(True)
        genotype_info.setProperty("class", "mus1-help-text")
        genotype_layout.addWidget(genotype_info)

        # Subjects in Colony Group
        self.colony_subjects_list = QListWidget()
        self.colony_subjects_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Subjects in Colony", self.colony_subjects_list, layout)

        # Action buttons
        button_row = self.create_button_row(layout)
        create_btn = QPushButton("Create New Colony")
        create_btn.setProperty("class", "mus1-primary-button")
        create_btn.clicked.connect(self.handle_create_colony)
        button_row.addWidget(create_btn)

        update_btn = QPushButton("Update Colony")
        update_btn.setProperty("class", "mus1-secondary-button")
        update_btn.clicked.connect(self.handle_update_colony)
        button_row.addWidget(update_btn)

        layout.addStretch(1)
        self.add_page(self.colonies_page, "Colonies")

        # Connect colony selection
        self.colonies_list.itemSelectionChanged.connect(self.on_colony_selected)

        # Load colonies
        self.load_colonies()

    def setup_shared_projects_page(self):
        """Setup the Shared Projects page for managing lab-shared projects."""
        self.shared_projects_page = QWidget()
        layout = self.setup_page_layout(self.shared_projects_page)

        # Shared Projects List Group
        self.shared_projects_list = QListWidget()
        self.shared_projects_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Shared Projects", self.shared_projects_list, layout)

        # Project Details Group
        details_group, details_layout = self.create_form_section("Project Details", layout)

        # Create labeled input rows
        self.shared_project_name_edit = QLineEdit()
        self.shared_project_name_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Name:", self.shared_project_name_edit, details_layout)

        self.shared_project_path_edit = QLineEdit()
        self.shared_project_path_edit.setProperty("class", "mus1-text-input")
        path_row = self.create_form_row(details_layout)
        path_label = self.create_form_label("Path:")
        path_browse_btn = QPushButton("Browse...")
        path_browse_btn.setProperty("class", "mus1-secondary-button")
        path_browse_btn.clicked.connect(self._browse_shared_project_path)
        path_row.addWidget(path_label)
        path_row.addWidget(self.shared_project_path_edit, 1)
        path_row.addWidget(path_browse_btn)

        # Action buttons
        button_row = self.create_button_row(layout)
        add_btn = QPushButton("Add Shared Project")
        add_btn.setProperty("class", "mus1-primary-button")
        add_btn.clicked.connect(self.handle_add_shared_project)
        button_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.setProperty("class", "mus1-secondary-button")
        remove_btn.clicked.connect(self.handle_remove_shared_project)
        button_row.addWidget(remove_btn)

        layout.addStretch(1)
        self.add_page(self.shared_projects_page, "Shared Projects")

        # Load shared projects
        self.load_shared_projects()

    def setup_lab_library_page(self):
        """Setup the Lab Library page to browse shared recordings and lab subjects."""
        self.lab_library_page = QWidget()
        layout = self.setup_page_layout(self.lab_library_page)

        # Recordings list
        self.recordings_list = QListWidget()
        self.recordings_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Recordings in Lab Library", self.recordings_list, layout)

        # Subjects list
        self.lab_subjects_list = QListWidget()
        self.lab_subjects_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Subjects in Lab (aggregated)", self.lab_subjects_list, layout)

        # Actions
        button_row = self.create_button_row(layout)
        refresh_btn = QPushButton("Refresh Lab Library")
        refresh_btn.setProperty("class", "mus1-secondary-button")
        refresh_btn.clicked.connect(self.load_lab_library)
        button_row.addWidget(refresh_btn)

        add_to_project_btn = QPushButton("Add Selected Recordings to Current Project")
        add_to_project_btn.setProperty("class", "mus1-primary-button")
        add_to_project_btn.clicked.connect(self.add_selected_recordings_to_project)
        button_row.addWidget(add_to_project_btn)

        # Link/copy toggle (link-only for now; copy not implemented)
        mode_row = self.create_form_row(layout)
        self.link_only_check = QCheckBox("Link only (do not copy files)")
        self.link_only_check.setChecked(True)
        mode_row.addWidget(self.link_only_check)
        layout.addStretch(1)
        self.add_page(self.lab_library_page, "Lab Library")

    def setup_lab_members_page(self):
        """Setup the Lab Members page for managing lab membership."""
        self.lab_members_page = QWidget()
        layout = self.setup_page_layout(self.lab_members_page)

        # Current Lab Members List Group
        self.lab_members_list = QListWidget()
        self.lab_members_list.setProperty("class", "mus1-list-widget")
        self.create_form_with_list("Current Lab Members", self.lab_members_list, layout)

        # Add Member Group
        add_group, add_layout = self.create_form_section("Add Lab Member", layout)

        # Create labeled input rows
        self.member_email_edit = QLineEdit()
        self.member_email_edit.setProperty("class", "mus1-text-input")
        self.create_labeled_input_row("Email:", self.member_email_edit, add_layout)

        self.member_role_combo = QComboBox()
        self.member_role_combo.setProperty("class", "mus1-combo-box")
        self.member_role_combo.addItems(["member", "admin"])
        role_row = self.create_form_row(add_layout)
        role_label = self.create_form_label("Role:")
        role_row.addWidget(role_label)
        role_row.addWidget(self.member_role_combo, 1)

        # Action buttons
        button_row = self.create_button_row(layout)
        add_btn = QPushButton("Add Member")
        add_btn.setProperty("class", "mus1-primary-button")
        add_btn.clicked.connect(self.handle_add_lab_member)
        button_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected Member")
        remove_btn.setProperty("class", "mus1-secondary-button")
        remove_btn.clicked.connect(self.handle_remove_lab_member)
        button_row.addWidget(remove_btn)

        layout.addStretch(1)
        self.add_page(self.lab_members_page, "Lab Members")

        # Load lab members
        self.load_lab_members()

    def setup_lab_settings_page(self):
        """Setup the Lab Settings page (moved from Settings view)."""
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
        self.add_page(self.lab_settings_page, "Lab Settings")

        # Connect lab selection
        self.labs_list.itemSelectionChanged.connect(self.on_lab_selected)

        # Load labs
        self.load_labs()

    # ---- Colonies Methods ----
    def load_colonies(self):
        """Load lab colonies for the currently selected lab."""
        self.navigation_pane.add_log_message("Loading colonies...", "info")
        if not self.lab_service:
            self.colonies_list.clear()
            self.navigation_pane.add_log_message("Lab service not available", "error")
            return

        try:
            # Get the currently selected lab
            current_lab_item = self.labs_list.currentItem()
            if not current_lab_item:
                self.colonies_list.clear()
                self.navigation_pane.add_log_message("No lab selected - cannot load colonies", "warning")
                return

            lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)
            self.navigation_pane.add_log_message(f"Loading colonies for lab: {lab_id}", "info")

            # Get colonies for this lab
            colonies = self.lab_service.get_lab_colonies(lab_id)
            self.navigation_pane.add_log_message(f"Retrieved {len(colonies)} colonies from service", "info")

            self.colonies_list.clear()
            for colony in colonies:
                display_text = f"{colony['genotype_of_interest']} Colony ({colony['background_strain']} background)"
                item = QListWidgetItem(display_text)
                # Store colony data for operations
                item.setData(Qt.ItemDataRole.UserRole, colony['id'])
                item.setData(Qt.ItemDataRole.UserRole + 1, colony)
                self.colonies_list.addItem(item)

            self.navigation_pane.add_log_message(f"Loaded {len(colonies)} colonies into list", "info")

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading colonies: {e}", "error")
            self.colonies_list.clear()

    def on_colony_selected(self):
        """Handle colony selection."""
        current_item = self.colonies_list.currentItem()
        if not current_item:
            return

        colony_data = current_item.data(Qt.ItemDataRole.UserRole + 1)

        self.colony_name_edit.setText(colony_data.get('name', ''))
        self.colony_gene_edit.setText(colony_data.get('genotype_of_interest', ''))
        self.colony_strain_edit.setText(colony_data.get('background_strain', ''))

        # Load subjects for this colony
        self.load_colony_subjects(colony_data['id'])

    def load_colony_subjects(self, colony_id):
        """Load subjects for a colony."""
        if not self.lab_service:
            self.colony_subjects_list.clear()
            self.navigation_pane.add_log_message("Lab service not available", "error")
            return

        try:
            # Get subjects for this colony
            subjects = self.lab_service.get_colony_subjects(colony_id)

            self.colony_subjects_list.clear()
            for subject in subjects:
                genotype_display = subject.get('genotype') or "Unknown"
                display_text = f"{subject['id']} ({genotype_display})"
                item = QListWidgetItem(display_text)
                self.colony_subjects_list.addItem(item)

            self.navigation_pane.add_log_message(f"Loaded {len(subjects)} subjects for colony", "info")

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading colony subjects: {e}", "error")
            self.colony_subjects_list.clear()

    def handle_create_colony(self):
        """Create a new colony."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        colony_name = self.colony_name_edit.text().strip()
        gene_of_interest = self.colony_gene_edit.text().strip()
        background_strain = self.colony_strain_edit.text().strip()

        if not colony_name:
            QMessageBox.warning(self, "Validation Error", "Colony name is required")
            return

        if not gene_of_interest:
            QMessageBox.warning(self, "Validation Error", "Gene of interest is required")
            return

        if not background_strain:
            QMessageBox.warning(self, "Validation Error", "Background strain is required")
            return

        # Get the currently selected lab
        current_lab_item = self.labs_list.currentItem()
        if not current_lab_item:
            QMessageBox.warning(self, "No Selection", "Please select a lab first")
            return

        lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)

        # Generate colony ID
        import uuid
        colony_id = str(uuid.uuid4())

        success = self.lab_service.create_colony(lab_id, colony_id, colony_name, gene_of_interest, background_strain)

        if success:
            # Refresh colonies list
            self.load_colonies()

            # Clear form
            self.colony_name_edit.clear()
            self.colony_gene_edit.clear()
            self.colony_strain_edit.clear()

    def handle_update_colony(self):
        """Update selected colony."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        current_item = self.colonies_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a colony to update.")
            return

        colony_name = self.colony_name_edit.text().strip()
        gene_of_interest = self.colony_gene_edit.text().strip()
        background_strain = self.colony_strain_edit.text().strip()

        if not colony_name:
            QMessageBox.warning(self, "Validation Error", "Colony name is required.")
            return

        if not gene_of_interest:
            QMessageBox.warning(self, "Validation Error", "Gene of interest is required.")
            return

        if not background_strain:
            QMessageBox.warning(self, "Validation Error", "Background strain is required.")
            return

        colony_data = current_item.data(Qt.ItemDataRole.UserRole + 1)
        colony_id = colony_data['id']

        success = self.lab_service.update_colony(colony_id, colony_name, gene_of_interest, background_strain)

        if success:
            # Refresh colonies list
            self.load_colonies()

            # Clear form
            self.colony_name_edit.clear()
            self.colony_gene_edit.clear()
            self.colony_strain_edit.clear()

    # ---- Shared Projects Methods ----
    def load_shared_projects(self):
        """Load projects registered with the currently selected lab."""
        if not self.lab_service:
            self.shared_projects_list.clear()
            self.navigation_pane.add_log_message("Lab service not available", "error")
            return

        try:
            # Get the currently selected lab
            current_lab_item = self.labs_list.currentItem()
            if not current_lab_item:
                self.shared_projects_list.clear()
                self.navigation_pane.add_log_message("No lab selected - cannot load projects", "warning")
                return

            lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)

            # Get projects for this lab
            projects = self.lab_service.get_lab_projects(lab_id)

            self.shared_projects_list.clear()
            for project in projects:
                display_text = f"{project['name']} - {project['path']}"
                item = QListWidgetItem(display_text)
                # Store project data for operations
                item.setData(Qt.ItemDataRole.UserRole, project['id'])
                item.setData(Qt.ItemDataRole.UserRole + 1, project)
                self.shared_projects_list.addItem(item)

            self.navigation_pane.add_log_message(f"Loaded {len(projects)} lab projects", "info")

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading shared projects: {e}", "error")
            self.shared_projects_list.clear()

    def _browse_shared_project_path(self):
        """Browse for shared project path."""
        directory = QFileDialog.getExistingDirectory(self, "Select Shared Project Directory")
        if directory:
            self.shared_project_path_edit.setText(directory)

    def handle_add_shared_project(self):
        """Add a project to the lab."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        project_name = self.shared_project_name_edit.text().strip()
        project_path = self.shared_project_path_edit.text().strip()

        if not project_name:
            QMessageBox.warning(self, "Validation Error", "Project name is required")
            return

        if not project_path:
            QMessageBox.warning(self, "Validation Error", "Project path is required")
            return

        # Get the currently selected lab
        current_lab_item = self.labs_list.currentItem()
        if not current_lab_item:
            QMessageBox.warning(self, "No Selection", "Please select a lab first")
            return

        lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)

        success = self.lab_service.add_lab_project(lab_id, project_name, project_path)

        if success:
            # Refresh projects list
            self.load_shared_projects()

    # ---- Lab Library Methods ----
    def load_lab_library(self):
        """Load recordings and subjects for the selected lab using SetupService APIs."""
        if not self.lab_service:
            if hasattr(self, 'recordings_list'):
                self.recordings_list.clear()
            if hasattr(self, 'lab_subjects_list'):
                self.lab_subjects_list.clear()
            self.navigation_pane.add_log_message("Lab service not available", "error")
            return

        # Determine selected lab id
        current_lab_item = getattr(self, 'labs_list', None).currentItem() if hasattr(self, 'labs_list') else None
        if not current_lab_item:
            if hasattr(self, 'recordings_list'):
                self.recordings_list.clear()
            if hasattr(self, 'lab_subjects_list'):
                self.lab_subjects_list.clear()
            self.navigation_pane.add_log_message("No lab selected - cannot load lab library", "warning")
            return

        lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)

        # Recordings
        try:
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            rec = svc.list_lab_recordings(lab_id=lab_id)
            self.recordings_list.clear()
            for p in rec.get("recordings", []):
                self.recordings_list.addItem(p)
            self.navigation_pane.add_log_message(f"Loaded {self.recordings_list.count()} recordings from lab library", "info")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading lab recordings: {e}", "error")
            self.recordings_list.clear()

        # Subjects
        try:
            from ..core.setup_service import get_setup_service
            svc = get_setup_service()
            subj = svc.get_lab_subjects(lab_id)
            self.lab_subjects_list.clear()
            for s in subj.get("subjects", []):
                disp = f"{s.get('id')} (geno={s.get('genotype') or 'N/A'})"
                self.lab_subjects_list.addItem(disp)
            self.navigation_pane.add_log_message(f"Loaded {self.lab_subjects_list.count()} lab subjects", "info")
        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading lab subjects: {e}", "error")
            self.lab_subjects_list.clear()

    def add_selected_recordings_to_project(self):
        """Add selected lab recordings into the current project as videos (path references)."""
        main_window = self.window()
        if not main_window or not hasattr(main_window, 'project_manager') or not main_window.project_manager:
            QMessageBox.warning(self, "No Project", "Load a project first to add recordings.")
            return
        pm = main_window.project_manager
        selected = self.recordings_list.selectedItems() if hasattr(self, 'recordings_list') else []
        if not selected:
            QMessageBox.information(self, "Lab Library", "Select one or more recordings to add to the project.")
            return
        from ..core.metadata import VideoFile
        link_only = getattr(self, 'link_only_check', None)
        link_only_enabled = bool(link_only and link_only.isChecked())
        added = 0
        for it in selected:
            try:
                p = Path(it.text())
                if link_only_enabled:
                    vf = VideoFile(path=p, hash="")
                    pm.add_or_update_video_from_file(vf) if hasattr(pm, 'add_or_update_video_from_file') else pm.add_video(vf)
                else:
                    # Copy mode not implemented: fall back to linking
                    vf = VideoFile(path=p, hash="")
                    pm.add_or_update_video_from_file(vf) if hasattr(pm, 'add_or_update_video_from_file') else pm.add_video(vf)
                added += 1
            except Exception:
                continue
        self.navigation_pane.add_log_message(f"Added {added} recording(s) to current project", "success")

            # Clear form
            self.shared_project_name_edit.clear()
            self.shared_project_path_edit.clear()

    def handle_remove_shared_project(self):
        """Remove selected project from lab."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        current_item = self.shared_projects_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "Shared Projects", "Select a project to remove.")
            return

        # Get the currently selected lab
        current_lab_item = self.labs_list.currentItem()
        if not current_lab_item:
            QMessageBox.warning(self, "No Selection", "Please select a lab first")
            return

        lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)
        project_data = current_item.data(Qt.ItemDataRole.UserRole + 1)
        project_name = project_data['name']

        # Confirm removal
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove project '{project_name}' from this lab?\n\n"
            f"This will only remove the association - the project files will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success = self.lab_service.remove_lab_project(lab_id, project_name)

        if success:
            # Refresh projects list
            self.load_shared_projects()

    # ---- Lab Members Methods ----
    def load_lab_members(self):
        """Load lab members for the currently selected lab."""
        if not self.lab_service:
            self.lab_members_list.clear()
            self.navigation_pane.add_log_message("Lab service not available", "error")
            return

        try:
            # Get the currently selected lab
            current_lab_item = self.labs_list.currentItem()
            if not current_lab_item:
                self.lab_members_list.clear()
                self.navigation_pane.add_log_message("No lab selected - cannot load members", "warning")
                return

            lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)

            # Get members for this lab
            members = self.lab_service.get_lab_members(lab_id)

            self.lab_members_list.clear()
            for member in members:
                display_text = f"{member['email']} ({member['role']})"
                item = QListWidgetItem(display_text)
                # Store user_id and role for potential operations
                item.setData(Qt.ItemDataRole.UserRole, member['user_id'])
                item.setData(Qt.ItemDataRole.UserRole + 1, member['role'])
                self.lab_members_list.addItem(item)

            self.navigation_pane.add_log_message(f"Loaded {len(members)} lab members", "info")

        except Exception as e:
            self.navigation_pane.add_log_message(f"Error loading lab members: {e}", "error")
            self.lab_members_list.clear()

    def handle_add_lab_member(self):
        """Add a lab member."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        member_email = self.member_email_edit.text().strip()
        member_role = self.member_role_combo.currentText()

        if not member_email:
            QMessageBox.warning(self, "Validation Error", "Email is required")
            return

        # Get the currently selected lab
        current_lab_item = self.labs_list.currentItem()
        if not current_lab_item:
            QMessageBox.warning(self, "No Selection", "Please select a lab first")
            return

        lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)

        success = self.lab_service.add_lab_member(lab_id, member_email, member_role)

        if success:
            # Refresh the members list
            self.load_lab_members()
            # Clear form
            self.member_email_edit.clear()

    def handle_remove_lab_member(self):
        """Remove selected lab member."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        current_item = self.lab_members_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "Lab Members", "Select a member to remove.")
            return

        # Get the currently selected lab
        current_lab_item = self.labs_list.currentItem()
        if not current_lab_item:
            QMessageBox.warning(self, "No Selection", "Please select a lab first")
            return

        lab_id = current_lab_item.data(Qt.ItemDataRole.UserRole)
        user_id = current_item.data(Qt.ItemDataRole.UserRole)
        member_info = current_item.text()

        # Don't allow removing yourself if you're the creator
        lab_data = current_lab_item.data(Qt.ItemDataRole.UserRole + 1)
        from ..core.config_manager import get_config
        current_user_id = get_config("user.id", scope="user")
        if user_id == current_user_id and lab_data.get('creator_id') == current_user_id:
            QMessageBox.warning(self, "Cannot Remove", "You cannot remove yourself as the lab creator.")
            return

        # Confirm removal
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove {member_info} from this lab?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success = self.lab_service.remove_lab_member(lab_id, user_id)

        if success:
            # Refresh the members list
            self.load_lab_members()

    # ---- Lab Settings Methods (moved from Settings view) ----
    def load_labs(self):
        """Load user's labs."""
        self.navigation_pane.add_log_message("Loading labs...", "info")
        if not self.lab_service:
            self.navigation_pane.add_log_message("Lab service not available", "error")
            return

        try:
            labs = self.lab_service.get_labs()
            self.navigation_pane.add_log_message(f"Retrieved {len(labs)} labs from service", "info")

            self.labs_list.clear()
            for lab_data in labs:
                display_text = f"{lab_data['name']} ({lab_data.get('institution', 'Unknown')})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, lab_data['id'])
                item.setData(Qt.ItemDataRole.UserRole + 1, lab_data)
                self.labs_list.addItem(item)
            self.navigation_pane.add_log_message(f"Added {len(labs)} labs to list", "info")
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

        # Load members for this lab
        self.load_lab_members()

    def handle_create_lab(self):
        """Create a new lab."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

        lab_name = self.lab_name_edit.text().strip()
        if not lab_name:
            QMessageBox.warning(self, "Validation Error", "Lab name is required")
            return

        # Generate lab ID from name
        lab_id = lab_name.lower().replace(' ', '_').replace('-', '_')

        institution = self.lab_institution_edit.text().strip()
        pi_name = self.lab_pi_edit.text().strip()

        success = self.lab_service.create_lab(lab_id, lab_name, institution, pi_name)

        if success:
            self.load_labs()  # Refresh the list
            # Clear form
            self.lab_name_edit.clear()
            self.lab_institution_edit.clear()
            self.lab_pi_edit.clear()

    def handle_update_lab(self):
        """Update selected lab."""
        if not self.lab_service:
            QMessageBox.warning(self, "Error", "Lab service not available")
            return

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

        success = self.lab_service.update_lab(lab_id, lab_name, institution, pi_name)

        if success:
            self.load_labs()  # Refresh the list
            # Clear form
            self.lab_name_edit.clear()
            self.lab_institution_edit.clear()
            self.lab_pi_edit.clear()

    def refresh_lab_data(self):
        """Refresh all lab-related data."""
        self.navigation_pane.add_log_message("Refreshing lab data...", "info")
        self.load_labs()
        self.navigation_pane.add_log_message(f"Labs list now has {self.labs_list.count() if hasattr(self, 'labs_list') else 0} items", "info")
        # Lab-specific data will be loaded when a lab is selected
