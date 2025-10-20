from .qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QFileDialog, QMessageBox, Qt, QProgressBar, QTextEdit, QSlider, QCheckBox
)
from .qt import Signal
from pathlib import Path
from .base_view import BaseView
from ..core.logging_bus import LoggingEventBus
from typing import Dict, Any
from ..core.plugin_manager_clean import PluginManagerClean
from ..core.scanners.remote import collect_from_targets
from .gui_services import GUIProjectService


class NotesBox(QGroupBox):
    """A reusable notes component that can be added to any view."""
    def __init__(self, parent=None, title="Notes", placeholder_text="Enter notes here..."):
        super().__init__(title, parent)

        # Find base_view for accessing layout constants
        self.base_view = self.find_base_view_parent(parent)

        # Use base view constants if available, otherwise use defaults
        form_margin = getattr(self.base_view, 'FORM_MARGIN', 10) if self.base_view else 10
        control_spacing = getattr(self.base_view, 'CONTROL_SPACING', 8) if self.base_view else 8

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(form_margin, form_margin + 5, form_margin, form_margin)
        self.layout.setSpacing(control_spacing)
        
        # Set up the QTextEdit for notes
        self.notes_edit = QTextEdit(self)
        self.notes_edit.setPlaceholderText(placeholder_text)
        self.notes_edit.setProperty("class", "mus1-notes-edit")
        self.layout.addWidget(self.notes_edit)
        
        # Add a save button
        self.save_button = QPushButton("Save", self)
        self.save_button.setProperty("class", "mus1-primary-button")
        
        # Button row layout - no specific margins set here
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.save_button)
        
        self.layout.addLayout(button_layout)
        
        # Find base_view for accessing log functionality
        self.base_view = self.find_base_view_parent(parent)
    
    def find_base_view_parent(self, parent):
        """Find the closest BaseView parent to access layout constants."""
        current = parent
        while current:
            if hasattr(current, 'FORM_MARGIN') and hasattr(current, 'CONTROL_SPACING'):
                return current
            if hasattr(current, 'parent'):
                current = current.parent()
            else:
                break
        return None
    
    def set_text(self, text):
        """Set the content of the notes editor."""
        self.notes_edit.setPlainText(text)
    
    def get_text(self):
        """Get the content of the notes editor."""
        return self.notes_edit.toPlainText()
    
    def connect_save_button(self, callback):
        """Connect the save button to a callback function."""
        self.save_button.clicked.connect(callback)


class ProjectView(BaseView):
    project_renamed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, view_name="project")

        # Initialize logging
        self.log_bus = LoggingEventBus.get_instance()

        # Initialize GUI services
        self.gui_services = None  # Will be set when project is loaded
        self.project_service = None  # Will be set when project is loaded
        self.plugin_manager = None  # Will be set when project is loaded
        self.importer_param_widgets: Dict[str, QWidget] = {} # Initialize the dictionary here
        self.setup_navigation(["Import Project", "Project Settings"])
        self.setup_import_project_page()
        self.setup_project_settings_page()
        self.setup_scan_ingest_page()
        self.setup_targets_page()
        # Add navigation buttons for newly added pages to keep nav and pages aligned
        self.add_navigation_button("Scan & Ingest")
        self.add_navigation_button("Targets")
        self.change_page(0)

    # --- Lifecycle hooks ---
    def on_services_ready(self, services):
        super().on_services_ready(services)
        # services may be a GUIServiceFactory (project-scoped) or GlobalServices (no project)
        self.gui_services = services
        try:
            if hasattr(services, 'create_project_service'):
                # Project is loaded; create the project-scoped service
                self.project_service = services.create_project_service()
            else:
                # No project yet; keep project_service unset and allow global-only operations
                self.project_service = None
        except Exception:
            # Be resilient during early startup before a project is loaded
            self.project_service = None
        try:
            main_window = self.window()
            if hasattr(main_window, 'service_factory') and main_window.service_factory and hasattr(main_window.service_factory, 'plugin_manager'):
                self.plugin_manager = main_window.service_factory.plugin_manager
                self.plugin_manager.discover_entry_points()
                self.populate_importer_plugins()
            else:
                self.log_bus.log("No project loaded - plugin manager not available", "info", "ProjectView")
        except Exception as e:
            self.log_bus.log(f"Plugin manager init failed: {e}", "warning", "ProjectView")
        # Subscribe to context changes to refresh lists when user/lab/project changes
        try:
            mw = self.window()
            if mw and hasattr(mw, 'contextChanged'):
                mw.contextChanged.connect(lambda _ctx: self.refresh_lists())
        except Exception:
            pass

    def format_item(self, item):
        """Utility to return the proper display string for an item."""
        return item.name if hasattr(item, "name") else str(item)

    def setup_import_project_page(self):
        """Setup the page for importing data from external projects."""
        self.import_project_page = QWidget()
        layout = self.setup_page_layout(self.import_project_page)

        # 1. Importer Plugin Selection Group
        importer_group, importer_layout = self.create_form_section("Select Importer", layout)
        importer_row = self.create_form_row(importer_layout)
        importer_label = self.create_form_label("Importer:")
        self.importer_plugin_combo = QComboBox()
        self.importer_plugin_combo.setProperty("class", "mus1-combo-box")
        self.importer_plugin_combo.currentIndexChanged.connect(self.on_importer_plugin_selected)
        importer_row.addWidget(importer_label)
        importer_row.addWidget(self.importer_plugin_combo, 1)

        # Action selector for project-level actions
        action_row = self.create_form_row(importer_layout)
        action_label = self.create_form_label("Action:")
        self.importer_action_combo = QComboBox()
        self.importer_action_combo.setProperty("class", "mus1-combo-box")
        action_row.addWidget(action_label)
        action_row.addWidget(self.importer_action_combo, 1)

        # 2. Dynamic Parameter Fields Group
        # Use a group box to visually contain the dynamic fields
        self.importer_params_group, self.importer_params_layout = self.create_form_section("Importer Parameters", layout)
        # Initially hide the group until a plugin is selected? Optional.
        # self.importer_params_group.setVisible(False)

        # Add stretch before the button
        layout.addStretch(1)

        # 3. Action Button
        button_row = self.create_button_row(layout)
        self.import_project_button = QPushButton("Run Import Action")
        self.import_project_button.setProperty("class", "mus1-primary-button")
        self.import_project_button.clicked.connect(self.handle_import_project)
        self.import_project_button.setEnabled(False) # Disable until a plugin is selected
        button_row.addWidget(self.import_project_button)

        self.add_page(self.import_project_page, "Import Project") # Add page to stacked widget
        self.populate_importer_plugins() # Populate the dropdown

    def populate_importer_plugins(self):
        """Populates the importer plugin selection dropdown using new architecture."""
        if not hasattr(self, 'importer_plugin_combo'):
            return

        self.importer_plugin_combo.blockSignals(True)
        self.importer_plugin_combo.clear()
        self.importer_plugin_combo.addItem("Select an importer...", None)

        try:
            if not self.plugin_manager:
                raise RuntimeError("Plugin manager not initialized")
            importer_plugins = self.plugin_manager.get_importer_plugins()
            if not importer_plugins:
                importer_plugins = self.plugin_manager.get_plugins_with_project_actions()
            for p in importer_plugins:
                name = p.plugin_self_metadata().name
                self.importer_plugin_combo.addItem(name, name)
        except Exception as e:
            self.log_bus.log(f"No importer plugins available: {e}", "info", "ProjectView")

        self.importer_plugin_combo.blockSignals(False)
        self.on_importer_plugin_selected(self.importer_plugin_combo.currentIndex())

    def on_importer_plugin_selected(self, index):
        """Handles selection changes in the importer plugin dropdown."""
        # Clear previous dynamic widgets and layout content
        self._clear_layout(self.importer_params_layout)
        self.importer_param_widgets.clear()
        self.importer_params_group.setVisible(False) # Hide group if no plugin selected
        self.import_project_button.setEnabled(False)

        plugin_name = self.importer_plugin_combo.itemData(index)
        if not plugin_name:
            return

        # Get plugin instance
        plugin = None
        try:
            plugin = self.plugin_manager.get_plugin_by_name(plugin_name) if self.plugin_manager else None
        except Exception:
            plugin = None
        if not plugin:
            self.log_bus.log(f"Importer plugin '{plugin_name}' not found.", "warning", "ProjectView")
            return

        # Populate actions
        self.importer_action_combo.clear()
        try:
            actions = self.plugin_manager.get_project_actions_for_plugin(plugin_name)
            for action in actions:
                self.importer_action_combo.addItem(action, action)
        except Exception:
            pass

        # Build parameter UI
        self.importer_params_group.setVisible(True)
        self.importer_params_group.setTitle(f"{plugin_name} Parameters") # Update title

        # Get fields from the selected plugin
        try:
            required_fields = plugin.required_fields() or []
            field_types = plugin.get_field_types() or {}
            field_descriptions = plugin.get_field_descriptions() or {}
        except Exception:
            required_fields = []
            field_types = {}
            field_descriptions = {}

        # TODO: Re-enable when plugin system is integrated
        # self.importer_params_group.setVisible(True) # Show the parameter group
        self.importer_params_group.setTitle(f"{plugin_name} Parameters") # Update title

        # Get fields from the selected plugin
        required_fields = plugin.required_fields()
        # optional_fields = plugin.optional_fields() # Add if needed later
        field_types = plugin.get_field_types()
        field_descriptions = plugin.get_field_descriptions()

        # Dynamically create widgets for required fields
        for field_name in required_fields:
             field_type = field_types.get(field_name, "string") # Default to string
             description = field_descriptions.get(field_name, "")

             row_layout = self.create_form_row(self.importer_params_layout)
             label_text = f"{field_name.replace('_', ' ').title()}:"
             label = self.create_form_label(label_text)
             label.setToolTip(description)
             row_layout.addWidget(label)

             widget = None
             if field_type == 'file':
                  widget = QLineEdit()
                  widget.setProperty("class", "mus1-text-input")
                  browse_button = QPushButton("Browse...")
                  browse_button.setProperty("class", "mus1-secondary-button")
                  # Use lambda to pass the line edit widget to the browse function
                  browse_button.clicked.connect(lambda checked=False, le=widget: self._browse_file_for_importer(le))
                  row_layout.addWidget(widget, 1) # Line edit takes stretch
                  row_layout.addWidget(browse_button)
             elif field_type == 'directory': # Example for directory
                 widget = QLineEdit()
                 widget.setProperty("class", "mus1-text-input")
                 browse_button = QPushButton("Browse...")
                 browse_button.setProperty("class", "mus1-secondary-button")
                 browse_button.clicked.connect(lambda checked=False, le=widget: self._browse_directory_for_importer(le))
                 row_layout.addWidget(widget, 1)
                 row_layout.addWidget(browse_button)
             # Add other types (string, int, float, enum -> QComboBox) as needed
             else: # Default to QLineEdit for string or unknown
                 widget = QLineEdit()
                 widget.setProperty("class", "mus1-text-input")
                 row_layout.addWidget(widget, 1)

             if widget:
                 # Store reference to the input widget (not the browse button)
                 self.importer_param_widgets[field_name] = widget

        # Enable the import button now that parameters are displayed
        self.import_project_button.setEnabled(True)

    def _clear_layout(self, layout):
        """Removes all widgets from a layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    # If it's a layout item, clear it recursively
                    layout_item = item.layout()
                    if layout_item is not None:
                        self._clear_layout(layout_item)

    def _browse_file_for_importer(self, line_edit_widget: QLineEdit):
        """Opens a file dialog and sets the path in the provided QLineEdit."""
        # Consider adding file type filters based on plugin requirements if possible
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            line_edit_widget.setText(file_path)

    def _browse_directory_for_importer(self, line_edit_widget: QLineEdit):
         """Opens a directory dialog and sets the path in the provided QLineEdit."""
         dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
         if dir_path:
              line_edit_widget.setText(dir_path)

    def handle_import_project(self):
        """Handles the 'Import Project Settings' button click."""
        selected_index = self.importer_plugin_combo.currentIndex()
        plugin_name = self.importer_plugin_combo.itemData(selected_index)

        if not plugin_name:
            QMessageBox.warning(self, "Import Error", "Please select an importer.")
            return

        plugin = self.plugin_manager.get_plugin_by_name(plugin_name) if self.plugin_manager else None
        if not plugin:
            self.log_bus.log(f"Could not find plugin: {plugin_name}", "error", "ProjectView")
            return

        # Selected action
        action = self.importer_action_combo.currentData() or self.importer_action_combo.currentText()
        if not action:
            QMessageBox.warning(self, "Import Error", "Please select an action.")
            return

        # Collect parameters from dynamically created widgets
        parameters: Dict[str, Any] = {}
        missing_required = []
        try:
            required_fields = plugin.required_fields()
            for field_name, widget in self.importer_param_widgets.items():
                value = ""
                if isinstance(widget, QLineEdit):
                    value = widget.text().strip()
                # Add elif for other widget types (QComboBox, QSpinBox, etc.) if used
                parameters[field_name] = value
                # Check if required field is empty
                if field_name in required_fields and not value:
                    missing_required.append(field_name)

            if missing_required:
                 QMessageBox.warning(self, "Missing Information",
                                     f"Please fill in the required fields: {', '.join(missing_required)}")
                 return

        except Exception as e:
             QMessageBox.critical(self, "Parameter Error", f"Error collecting parameters: {e}")
             return

        # Run the project-level action through the plugin instance
        self.log_bus.log(f"Starting import using {plugin_name}:{action}...", "info", "ProjectView")
        try:
            main_window = self.window()
            pm = getattr(main_window, 'project_manager', None)
            if not pm:
                QMessageBox.warning(self, "Import Error", "No project loaded.")
                return
            result = plugin.run_action(action, parameters, pm)
            status = result.get("status", "unknown")
            message = result.get("message") or result.get("error") or str(result)
            if status == "success":
                QMessageBox.information(self, "Import Successful", message)
                self.log_bus.log(message, "success", "ProjectView")
            else:
                QMessageBox.warning(self, "Import Failed", message)
                self.log_bus.log(f"Import failed: {message}", "error", "ProjectView")
        except Exception as e:
            error_msg = f"Import action error: {e}"
            QMessageBox.critical(self, "Import Error", error_msg)
            self.log_bus.log(error_msg, "error", "ProjectView")

    def set_initial_project(self, project_name: str):
        """
        Updates UI elements specific to ProjectView when a project is loaded or switched.
        Called by MainWindow after successful project load.
        """
        self.log_bus.log(f"Updating ProjectView for project: {project_name}", "info", "ProjectView")
        # Update the label showing the current project
        if hasattr(self, 'current_project_label'):
            self.current_project_label.setText("Current Project: " + project_name)
        # Pre-fill rename field
        if hasattr(self, 'rename_line_edit'):
            self.rename_line_edit.setText(project_name)

        # Load project notes (still relevant here)
        if hasattr(self, 'project_notes_box') and self.window() and self.window().project_manager:
            pm = self.window().project_manager
            notes = pm.config.settings.get("project_notes", "")
            self.log_bus.log(f"Loading project notes ({len(notes)} characters) for project: {project_name}", "info")
            self.project_notes_box.set_text(notes)
        else:
            has_window = bool(self.window())
            has_pm = has_window and bool(self.window().project_manager)
            self.log_bus.log(f"Cannot load project notes - project_notes_box exists: {hasattr(self, 'project_notes_box')}, window exists: {has_window}, project_manager exists: {has_pm}", "warning")

        # Update UI settings from the loaded project state
        # Note: General settings are now handled by SettingsView

        # Update the location selector based on whether current project is under shared
        try:
            if hasattr(self, 'switch_location_combo') and self.window().project_manager:
                pm = self.window().project_manager
                is_shared = False
                # Shared if project explicitly sets shared_root, or the project path is under the selected lab's storage root
                if getattr(pm.config, 'shared_root', None):
                    is_shared = True
                else:
                    try:
                        current_lab_id = getattr(self.window(), 'selected_lab_id', None)
                        if current_lab_id:
                            from ..core.config_manager import get_lab_storage_root as _glsr
                            lab_root = _glsr(current_lab_id)
                            if lab_root:
                                is_shared = str(pm.project_path.resolve()).startswith(str(lab_root.resolve()))
                    except Exception:
                        is_shared = False
                target_index = 1 if is_shared else 0  # 0=Local, 1=Shared
                if 0 <= target_index < self.switch_location_combo.count():
                    self.switch_location_combo.blockSignals(True)
                    self.switch_location_combo.setCurrentIndex(target_index)
                    self.switch_location_combo.blockSignals(False)
        except Exception:
            pass

        # Refresh the project list dropdown to ensure it's up-to-date
        self.populate_project_list()
        # Select the current project in the dropdown
        if hasattr(self, 'switch_project_combo'):
            index = self.switch_project_combo.findText(project_name)
            if index >= 0:
                self.switch_project_combo.setCurrentIndex(index)

        # Refresh importer plugin list as well (in case available plugins change based on project context, unlikely but good practice)
        self.populate_importer_plugins()

    def update_likelihood_filter_from_state(self):
        """Update likelihood filter settings from the current state."""
        pm = self.window().project_manager
        if not pm:
            return

        # Check if we have the likelihood filter components
        # These components might not exist yet in the current version
        # print("INFO: Likelihood filter update skipped - components not implemented yet") # Keep commented

    def populate_project_list(self):
        """Populate the project selection dropdown using discovery service.

        Displays entries as: <name> — Local | Shared (Lab Name). Stores full path in itemData.
        Filters by `switch_location_combo` (Local/Shared).
        """
        if not hasattr(self, 'switch_project_combo'):
            self.log_bus.log("Switch project combo box not found.", "warning", "ProjectView")
            return

        try:
            # Determine filter
            location_filter = "Local"
            if hasattr(self, 'switch_location_combo'):
                location_filter = self.switch_location_combo.currentText() or "Local"

            # Discover projects
            from ..core.project_discovery_service import get_project_discovery_service
            pds = get_project_discovery_service()
            project_paths = pds.discover_existing_projects() or []

            # Lab id -> label mapping
            lab_names = {}
            try:
                from ..core.setup_service import get_setup_service
                labs = get_setup_service().get_labs() or {}
                for lab_id, lab in labs.items():
                    nm = lab.get('name') or lab_id
                    inst = lab.get('institution')
                    lab_names[lab_id] = f"{nm} ({inst})" if inst else nm
            except Exception:
                pass

            # Remove deprecated global shared root usage
            shared_root = None

            from pathlib import Path as _Path
            items = []  # (display, path)
            for p in project_paths:
                try:
                    p = _Path(p)
                    name = p.name
                    lab_id = None
                    proj_shared = None
                    meta = p / 'project.json'
                    if meta.exists():
                        import json as _json
                        try:
                            with open(meta) as f:
                                data = _json.load(f)
                            lab_id = data.get('lab_id')
                            sr = data.get('shared_root')
                            if sr:
                                from pathlib import Path as __P
                                proj_shared = __P(sr)
                        except Exception:
                            pass

                    # Determine location
                    is_shared = bool(proj_shared)
                    if not is_shared and shared_root:
                        try:
                            is_shared = str(p.resolve()).startswith(str(shared_root.resolve()))
                        except Exception:
                            is_shared = False

                    # Apply filter
                    if location_filter.lower() == 'shared' and not is_shared:
                        continue
                    if location_filter.lower() == 'local' and is_shared:
                        continue

                    # Build explicit designation
                    designation = 'Local'
                    if proj_shared:
                        designation = 'Shared (Project)'
                    else:
                        # Check if under selected lab root only
                        try:
                            current_lab_id = getattr(self.window(), 'selected_lab_id', None)
                            if current_lab_id:
                                from ..core.config_manager import get_lab_storage_root as _glsr
                                lab_root = _glsr(current_lab_id)
                                if lab_root and str(p.resolve()).startswith(str(lab_root.resolve())):
                                    designation = 'Shared (Lab)'
                        except Exception:
                            pass

                    lab_txt = f" ({lab_names.get(lab_id)})" if lab_id and lab_id in lab_names else ""
                    display = f"{name} — {designation}{lab_txt}"
                    items.append((display, str(p)))
                except Exception:
                    continue

            # Fill combo
            self.switch_project_combo.blockSignals(True)
            self.switch_project_combo.clear()
            if items:
                for display, path_str in sorted(items, key=lambda x: x[0].lower()):
                    self.switch_project_combo.addItem(display, path_str)
            else:
                self.switch_project_combo.addItem("No projects available", None)
            self.switch_project_combo.blockSignals(False)
        except Exception as e:
            self.switch_project_combo.clear()
            self.switch_project_combo.addItem("Error loading projects", None)
            self.log_bus.log(f"Project list load error: {e}", "error", "ProjectView")

    def on_creation_location_changed(self, index):
        """Handle location type change for project creation."""
        is_shared = self.creation_location_combo.currentText().lower() == "shared"
        self.log_bus.log(f"Location changed to '{self.creation_location_combo.currentText()}', is_shared={is_shared}", "info", "ProjectView")
        self._set_lab_selection_visible(is_shared)
        if is_shared:
            self.populate_lab_combo()

    def _set_lab_selection_visible(self, visible):
        """Set visibility of lab selection row."""
        if hasattr(self, 'lab_selection_row'):
            # Hide/show the entire row by setting visibility on widgets
            for i in range(self.lab_selection_row.count()):
                widget = self.lab_selection_row.itemAt(i).widget()
                if widget:
                    widget.setVisible(visible)

    def populate_lab_combo(self):
        """Populate the lab selection combo for project creation."""
        if not hasattr(self, 'creation_lab_combo'):
            return

        self.creation_lab_combo.clear()
        try:
            # Prefer GUI LabService via global/project services
            lab_service = None
            if hasattr(self.gui_services, 'create_lab_service'):
                lab_service = self.gui_services.create_lab_service()
            elif hasattr(self.gui_services, 'lab_service'):
                lab_service = getattr(self.gui_services, 'lab_service')
            elif hasattr(self.window(), '_global_services') and hasattr(self.window()._global_services, 'lab_service'):
                lab_service = self.window()._global_services.lab_service

            labs = lab_service.get_labs() if lab_service else []
            self.log_bus.log(f"Found {len(labs)} labs for user", "info")
            if labs:
                for lab in labs:
                    lab_id = lab.get('id')
                    display_name = f"{lab.get('name', 'Unknown Lab')} ({lab.get('institution', 'Unknown Institution')})"
                    self.creation_lab_combo.addItem(display_name, lab_id)
                    self.log_bus.log(f"Added lab: {display_name}", "info", "ProjectView")
            else:
                self.creation_lab_combo.addItem("No labs available", None)
                self.log_bus.log("No labs available for user", "warning", "ProjectView")
        except Exception as e:
            self.log_bus.log(f"Error loading labs: {e}", "error", "ProjectView")
            self.creation_lab_combo.addItem("Error loading labs", None)

    def handle_create_project(self):
        """Handle creating a new project."""
        project_name = self.new_project_name_edit.text().strip()
        if not project_name:
            QMessageBox.warning(self, "Project Creation", "Please enter a project name.")
            return

        location_type = self.creation_location_combo.currentText().lower()
        lab_id = None

        if location_type == "shared":
            lab_id = self.creation_lab_combo.currentData()
            if not lab_id:
                QMessageBox.warning(self, "Project Creation", "Please select a lab for shared projects.")
                return

        try:
            from ..core.setup_service import get_setup_service
            from pathlib import Path

            setup_service = get_setup_service()

            # Determine base path
            if location_type == "shared":
                # Use per-lab storage root only
                try:
                    from ..core.config_manager import get_lab_storage_root
                    lab_root = get_lab_storage_root(lab_id) if lab_id else None
                except Exception:
                    lab_root = None
                if not lab_root:
                    QMessageBox.warning(self, "Project Creation", "Selected lab has no storage root configured. Set lab storage in Lab Settings.")
                    return
                base_path = Path(lab_root) / "Projects"
            else:
                # Use local projects directory
                user_profile = setup_service.get_user_profile()
                if user_profile and user_profile.default_projects_dir:
                    base_path = user_profile.default_projects_dir
                else:
                    base_path = Path.home() / "Documents" / "MUS1" / "Projects"

            # Check for global project name uniqueness
            from ..core.project_discovery_service import get_project_discovery_service
            discovery_service = get_project_discovery_service()
            existing_project_path = discovery_service.find_project_path(project_name)
            if existing_project_path:
                QMessageBox.warning(self, "Project Creation",
                    f"A project named '{project_name}' already exists at:\n{existing_project_path}\n\n"
                    "Please choose a different name or delete the existing project first.")
                return

            # Create project
            project_path = base_path / project_name

            if (project_path / "mus1.db").exists():
                QMessageBox.warning(self, "Project Creation", f"Project '{project_name}' already exists in target location.")
                return

            # Create directory and initialize project
            project_path.mkdir(parents=True, exist_ok=True)

            from ..core.project_manager_clean import ProjectManagerClean
            project_manager = ProjectManagerClean(project_path)

            # If created as Shared, persist lab root on project config (optional)
            if location_type == "shared":
                try:
                    if lab_root:
                        project_manager.set_shared_root(Path(lab_root))
                except Exception as e:
                    self.log_bus.log(f"Failed to persist lab shared root on project: {e}", "warning", "ProjectView")

            # Associate with lab if specified or requested for local
            if lab_id or (location_type == "local" and getattr(self, 'register_with_lab_check', None) and self.register_with_lab_check.isChecked()):
                if not lab_id:
                    # Try to use currently selected lab from the UI if available
                    if hasattr(self.window(), 'selected_lab_id'):
                        lab_id = self.window().selected_lab_id
                
                project_manager.set_lab_id(lab_id)
                # Register with lab using service layer
                lab_service = None
                try:
                    if hasattr(self.gui_services, 'create_lab_service'):
                        lab_service = self.gui_services.create_lab_service()
                    elif hasattr(self.gui_services, 'lab_service'):
                        lab_service = getattr(self.gui_services, 'lab_service')
                    elif hasattr(self.window(), '_global_services') and hasattr(self.window()._global_services, 'lab_service'):
                        lab_service = self.window()._global_services.lab_service
                except Exception:
                    lab_service = None

                if lab_service:
                    success = lab_service.associate_project_with_lab(
                        lab_id=lab_id,
                        project_name=project_name,
                        project_path=str(project_path)
                    )
                    if not success:
                        self.log_bus.log(f"Warning: Failed to associate project with lab '{lab_id}'", "warning", "ProjectView")
                else:
                    self.log_bus.log("Lab service unavailable; skipping lab association.", "warning", "ProjectView")

            # Switch to the newly created project
            self.window().load_project_path(project_path)
            try:
                if hasattr(self, 'switch_location_combo'):
                    self.switch_location_combo.setCurrentIndex(1 if location_type == 'shared' else 0)
            except Exception:
                pass
            self.log_bus.log(f"Project '{project_name}' created successfully", "success", "ProjectView")

            # Clear the form
            self.new_project_name_edit.clear()

            # Refresh project list and align filter to show the new project
            try:
                self.populate_project_list()
                if hasattr(self, 'switch_location_combo'):
                    self.switch_location_combo.setCurrentIndex(1 if location_type == 'shared' else 0)
                # Auto-select newly created project in dropdown
                if hasattr(self, 'switch_project_combo'):
                    idx = self.switch_project_combo.findText(project_name)
                    if idx >= 0:
                        self.switch_project_combo.setCurrentIndex(idx)
            except Exception:
                pass

        except Exception as e:
            self.log_bus.log(f"Error creating project: {e}", "error", "ProjectView")
            QMessageBox.critical(self, "Project Creation Error", f"Failed to create project: {e}")

    def handle_switch_project(self):
        """Handles the 'Switch' button click."""
        selected_project = self.switch_project_combo.currentText()
        if selected_project:
            current_project = self.window().selected_project_name
            if selected_project == current_project:
                self.log_bus.log(f"Already in project: {selected_project}", 'info', "ProjectView")
                return

            self.log_bus.log(f"Requesting switch to project: {selected_project}", 'info', "ProjectView")
            # Try to use stored full path if present
            try:
                path_str = self.switch_project_combo.currentData()
                if path_str:
                    from pathlib import Path as _Path
                    self.window().load_project_path(_Path(path_str))
                else:
                    self.window().load_project(selected_project)
            except Exception:
                self.window().load_project(selected_project)
            # MainWindow's load_project now handles logging success/failure,
            # title updates, and view refreshes (including calling set_initial_project).
        else:
            msg = "No project selected in the dropdown to switch to."
            # print(msg) # Keep commented
            self.log_bus.log(msg, 'warning', "ProjectView")

    def handle_rename_project(self):
        """Handles the 'Rename' button click."""
        new_name = self.rename_line_edit.text().strip()
        current_name = self.window().selected_project_name

        if not new_name:
            msg = "New project name cannot be empty."
            # print(msg) # Keep commented
            self.log_bus.log(msg, 'warning', "ProjectView")
            return

        if new_name == current_name:
             msg = "New name is the same as the current project name."
             self.log_bus.log(msg, 'info', "ProjectView")
             return

        if current_name is None:
             msg = "Cannot rename, no project is currently loaded."
             self.log_bus.log(msg, 'error', "ProjectView")
             return

        try:
            self.log_bus.log(f"Attempting to rename project '{current_name}' to: {new_name}", 'info', "ProjectView")
            # Perform rename using project_manager
            # Ensure project_manager exists
            if not self.window().project_manager:
                 self.log_bus.log("ProjectManager not available for rename.", "error", "ProjectView")
                 return

            self.window().project_manager.rename_project(new_name)

            # --- Rename Successful ---
            self.log_bus.log(f"Project successfully renamed to: {new_name}", 'success', "ProjectView")

            # Emit signal to notify MainWindow to update title etc.
            self.project_renamed.emit(new_name)

            # Update UI elements within this ProjectView
            if hasattr(self, 'current_project_label'):
                 self.current_project_label.setText("Current Project: " + new_name)
            # Keep rename_line_edit updated? Or clear it? Let's keep it updated.
            # self.rename_line_edit.setText(new_name) # Already set by user input

            # Refresh the project list dropdown
            self.populate_project_list()
            # Ensure the new name is selected in the dropdown
            if hasattr(self, 'switch_project_combo'):
                 index = self.switch_project_combo.findText(new_name)
                 if index >= 0:
                     self.switch_project_combo.setCurrentIndex(index)


        except Exception as e:
            error_msg = f"Error renaming project '{current_name}' to '{new_name}': {e}"
            # print(error_msg) # Keep commented
            self.log_bus.log(error_msg, 'error', "ProjectView")
            # Restore rename line edit to current name on failure?
            if hasattr(self, 'rename_line_edit'):
                 self.rename_line_edit.setText(current_name)

    def setup_project_settings_page(self):
        """Setup the Project Settings page with project info controls."""
        # Create the page widget without redundant styling
        self.project_settings_page = QWidget()

        # Create a scroll area to handle overflow content
        from .qt import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setProperty("class", "mus1-scroll-area")

        # Create a container widget for the scrollable content
        scroll_content = QWidget()
        layout = self.setup_page_layout(scroll_content)
        # Adjust margins for scroll content (less top margin since scroll area handles spacing)
        layout.setContentsMargins(self.FORM_MARGIN, self.PAGE_MARGIN // 2, self.FORM_MARGIN, self.FORM_MARGIN)

        # Set the scroll content as the widget for the scroll area
        scroll_area.setWidget(scroll_content)

        # Set up the page layout to contain just the scroll area
        page_layout = QVBoxLayout(self.project_settings_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)

        # Project creation group
        creation_group, creation_layout = self.create_form_section("Create New Project", layout)

        # Location type selection
        _, self.creation_location_combo = self.create_form_field("Location", "combo_box", parent_layout=creation_layout)
        self.creation_location_combo.addItems(["Local", "Shared"])

        # Project name
        _, self.new_project_name_edit = self.create_form_field("Project Name", "line_edit", "Enter project name", True, creation_layout)

        # Lab selection for shared projects
        self.lab_selection_row, self.creation_lab_combo = self.create_form_field("Lab", "combo_box", parent_layout=creation_layout)
        # Store references for visibility control
        self.lab_label = self.lab_selection_row.itemAt(0).widget()  # Get the label from the row
        self.lab_combo = self.creation_lab_combo

        # Create button
        button_row = self.create_form_actions_section("", [("Create Project", "mus1-primary-button")], creation_layout)
        self.create_project_button = button_row.itemAt(1).widget()  # Get the button from the centered layout
        if self.create_project_button:
            self.create_project_button.clicked.connect(self.handle_create_project)

        # Connect location combo to show/hide lab selection
        self.creation_location_combo.currentIndexChanged.connect(self.on_creation_location_changed)
        # Initially hide lab selection (for "Local")
        self._set_lab_selection_visible(False)
        self.creation_lab_combo.setVisible(False)

        layout.addWidget(creation_group)

        # Project selection group
        selection_group = QGroupBox("Project Selection")
        selection_group.setProperty("class", "mus1-input-group")
        selection_layout = QVBoxLayout(selection_group)
        
        # Current project display
        current_layout = QHBoxLayout()
        self.current_project_label = QLabel("Current Project: None")
        self.current_project_label.setProperty("formLabel", True)
        self.current_project_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        current_layout.addWidget(self.current_project_label)
        current_layout.addStretch(1)
        selection_layout.addLayout(current_layout)
        
        # Project selector
        selector_layout = self.create_form_row()
        switch_label = self.create_form_label("Switch to:")
        
        # Location chooser for listing projects (Local/Shared)
        self.switch_location_combo = QComboBox()
        self.switch_location_combo.setProperty("class", "mus1-combo-box")
        self.switch_location_combo.addItems(["Local", "Shared"])
        self.switch_location_combo.currentIndexChanged.connect(self.populate_project_list)

        self.switch_project_combo = QComboBox()
        self.switch_project_combo.setProperty("class", "mus1-combo-box")
        self.switch_project_button = QPushButton("Switch")
        self.switch_project_button.setProperty("class", "mus1-primary-button")
        self.switch_project_button.clicked.connect(self.handle_switch_project)

        # Registration preference
        register_group, register_layout_container = self.create_form_section("Registration", layout)
        reg_row = self.create_form_row(register_layout_container)
        self.register_with_lab_check = QCheckBox("Register newly created Local projects with selected lab")
        self.register_with_lab_check.setChecked(False)
        reg_row.addWidget(self.register_with_lab_check)
        layout.addWidget(register_group)

        # Quick actions
        quick_group, quick_layout_container = self.create_form_section("Quick Actions", layout)
        quick_row = self.create_form_row(quick_layout_container)
        browse_lab_btn = QPushButton("Browse Lab Library…")
        browse_lab_btn.setProperty("class", "mus1-secondary-button")
        browse_lab_btn.clicked.connect(self.handle_browse_lab_library)
        quick_row.addWidget(browse_lab_btn)
        layout.addWidget(quick_group)
        
        selector_layout.addWidget(switch_label)
        selector_layout.addWidget(self.switch_location_combo)
        selector_layout.addWidget(self.switch_project_combo, 1)
        selector_layout.addWidget(self.switch_project_button)
        selection_layout.addLayout(selector_layout)
        
        # Add the selection group to the main layout to preserve its children (including the combo box)
        layout.addWidget(selection_group)
        
        # Project renaming group
        rename_group, rename_layout_container = self.create_form_section("Rename Project", layout)
        rename_layout = self.create_form_row(rename_layout_container)
        
        rename_label = self.create_form_label("New Name:")
        self.rename_line_edit = QLineEdit()
        self.rename_line_edit.setProperty("class", "mus1-text-input")
        self.rename_button = QPushButton("Rename")
        self.rename_button.setProperty("class", "mus1-primary-button")
        self.rename_button.clicked.connect(self.handle_rename_project)
        
        rename_layout.addWidget(rename_label)
        rename_layout.addWidget(self.rename_line_edit, 1)
        rename_layout.addWidget(self.rename_button)
        
        # Add rename group to main layout
        layout.addWidget(rename_group)
        
        # Project notes - placed last as requested
        # Removed deprecated global/shared root UI group

        self.project_notes_box = NotesBox(
            title="Project Notes",
            placeholder_text="Enter project notes, details, and important information here..."
        )
        self.project_notes_box.connect_save_button(self.handle_save_project_notes)
        
        # Add notes to main layout (placed last as requested) with vertical stretch
        layout.addWidget(self.project_notes_box, 1)  # Give it a stretch factor of 1
        
        # Add the page to the stacked widget - BaseView will apply styling
        self.add_page(self.project_settings_page, "Project Settings")
        
        # Initialize the project list and lab combo
        self.populate_project_list()
        self.populate_lab_combo()
        
    def handle_save_project_notes(self):
        """Save the project notes to the current project state."""
        if not hasattr(self, 'window') or not self.window():
            self.log_bus.log("Cannot save notes: window reference not available.", 'error', "ProjectView")
            return

        if not hasattr(self, 'project_notes_box'):
            self.log_bus.log("Cannot save notes: project_notes_box not initialized.", 'error', "ProjectView")
            return

        notes = self.project_notes_box.get_text()
        self.log_bus.log(f"Saving project notes ({len(notes)} characters)...", 'info')

        try:
            # Ensure project_manager is available
            if not self.window().project_manager:
                 self.log_bus.log("Cannot save notes: Project manager not available.", 'error', "ProjectView")
                 return

            # Update notes in project config settings
            pm = self.window().project_manager
            pm.config.settings["project_notes"] = notes

            # Save the project to persist changes
            pm.save_project()

            self.log_bus.log("Project notes saved successfully.", 'success', "ProjectView")
        except Exception as e:
            error_msg = f"Error saving project notes: {e}"
            # print(error_msg) # Keep commented
            self.log_bus.log(error_msg, 'error', "ProjectView")

    # Removed deprecated shared-root handlers (global/shared UI)

    def update_theme(self, theme):
        """Update theme for this view and propagate any view-specific changes."""
        super().update_theme(theme)
        self.log_bus.log(f"Theme updated to {theme}.", "info", "ProjectView")

    def refresh_lists(self):
        """Refreshes lists managed by this view."""
        self.log_bus.log("Refreshing ProjectView lists...", "info", "ProjectView")
        self.populate_project_list()
        self.populate_lab_combo()  # Refresh lab combo too
        self.populate_importer_plugins() # Also refresh importer list
        # Note: General settings are now handled by SettingsView
        # Refresh new admin lists
        try:
            self.refresh_targets_admin_list()
            self.refresh_targets_list()
        except Exception:
            pass

    def setup_scan_ingest_page(self):
        """Setup a page to scan configured targets and ingest videos into the project."""
        self.scan_ingest_page = QWidget()
        layout = self.setup_page_layout(self.scan_ingest_page)

        # Targets selection
        self.targets_list = QListWidget()
        self.targets_list.setProperty("class", "mus1-list-widget")
        self.targets_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        targets_group, tg_layout = self.create_form_list_section("Scan Targets", self.targets_list, layout)

        # Options
        opt_group, opt_layout = self.create_form_section("Options", layout)

        # Extensions field
        _, self.extensions_line = self.create_form_field("Extensions", "line_edit", "Extensions (e.g., .mp4 .avi .mov)", parent_layout=opt_layout)

        # Excludes field
        _, self.exclude_line = self.create_form_field("Excludes", "line_edit", "Exclude dirs substrings (comma-separated)", parent_layout=opt_layout)

        # Non-recursive checkbox
        _, self.non_recursive_check = self.create_form_field("Non-recursive", "check_box", parent_layout=opt_layout)

        # Actions and progress
        self.create_form_actions_section("", [("Scan Selected Targets", "mus1-primary-button")], layout)
        # Get the scan button
        actions_layout = layout.itemAt(layout.count() - 1).layout()
        self.scan_button = actions_layout.itemAt(1).widget() if actions_layout.count() > 1 else None
        if self.scan_button:
            self.scan_button.clicked.connect(self.handle_scan_targets)

        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        layout.addWidget(self.scan_progress)

        # Summary and staging
        self.scan_summary_label = QLabel("")
        layout.addWidget(self.scan_summary_label)

        stage_group, stage_layout = self.create_form_section("Stage Off-Shared", layout)
        _, self.stage_subdir_line, self.stage_button = self.create_form_field_with_button(
            "Subdir", "line_edit", "Stage Off-Shared to Subdir",
            "Destination subdir under shared root (e.g., recordings/raw)",
            parent_layout=stage_layout
        )
        if self.stage_button:
            self.stage_button.clicked.connect(self.handle_stage_off_shared)

        self.create_form_actions_section("", [("Add Unique Under Shared", "mus1-primary-button")], layout)
        # Get the add button
        add_layout = layout.itemAt(layout.count() - 1).layout()
        self.add_shared_button = add_layout.itemAt(1).widget() if add_layout.count() > 1 else None
        if self.add_shared_button:
            self.add_shared_button.clicked.connect(self.handle_add_under_shared)

        layout.addStretch(1)
        self.add_page(self.scan_ingest_page, "Scan & Ingest")

        # Data holders
        self._dedup_results = []  # list of tuples (Path, hash, start_time)
        self._off_shared = []     # list of (Path, hash)
        self._in_shared = []      # list of (Path, hash, start_time)

        # Populate targets list initially
        self.refresh_targets_list()

    def refresh_targets_list(self):
        if not hasattr(self, 'targets_list'):
            return
        self.targets_list.clear()
        try:
            targets = list(self.window().project_manager.config.settings.get('scan_targets', []) or [])
        except Exception:
            targets = []
        for t in targets:
            item = QListWidgetItem(f"{t.get('name', '')}  ({t.get('kind', '')})")
            item.setData(Qt.ItemDataRole.UserRole, t.get('name', ''))
            item.setCheckState(Qt.CheckState.Unchecked)
            self.targets_list.addItem(item)

    def handle_scan_targets(self):
        try:
            # Check if project manager is available
            if not self.window().project_manager:
                QMessageBox.warning(self, "Scan", "No project is currently loaded. Please load a project first.")
                self.log_bus.log("Cannot scan targets: no project loaded.", "error", "ProjectView")
                return

            sr = self.window().project_manager.config.shared_root
            selected_names = []
            for i in range(self.targets_list.count()):
                it = self.targets_list.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    selected_names.append(it.data(Qt.ItemDataRole.UserRole))
            if not selected_names:
                QMessageBox.warning(self, "Scan", "Select at least one target to scan.")
                return

            # Build filters
            exts_text = self.extensions_line.text().strip()
            extensions = [e.strip() for e in exts_text.split() if e.strip()] if exts_text else None
            excl_text = self.exclude_line.text().strip()
            excludes = [e.strip() for e in excl_text.split(',') if e.strip()] if excl_text else None
            non_recursive = self.non_recursive_check.isChecked()

            # Resolve targets
            all_targets = list(self.window().project_manager.config.settings.get('scan_targets', []) or [])
            targets = [t for t in all_targets if t.get('name', '') in set(selected_names)]
            if not targets:
                QMessageBox.warning(self, "Scan", "No matching targets found.")
                return

            # Progress callback to update bar approximately
            self.scan_progress.setValue(0)
            def _cb(done: int, total: int):
                if total > 0:
                    val = max(0, min(100, int(done * 100 / total)))
                    self.scan_progress.setValue(val)

            # Collect and dedup - TODO: Integrate with clean architecture
            # items = collect_from_targets(self.state_manager, self.data_manager, targets, extensions=extensions, exclude_dirs=excludes, non_recursive=non_recursive)
            items = []  # Placeholder until integration is complete
            # dedup = list(self.data_manager.deduplicate_video_list(items, progress_cb=_cb))
            dedup = []  # Placeholder until integration is complete

            # Partition by shared root
            self._dedup_results = dedup
            self._in_shared = []
            self._off_shared = []
            for p, h, ts in dedup:
                try:
                    if sr and str(Path(p).resolve()).startswith(str(Path(sr).resolve())):
                        self._in_shared.append((p, h, ts))
                    else:
                        self._off_shared.append((p, h))
                except Exception:
                    self._off_shared.append((p, h))

            total = len(items)
            unique = len(dedup)
            off_shared = len(self._off_shared)
            self.scan_summary_label.setText(f"Scanned files: {total} | Unique: {unique} | Off-shared: {off_shared}")
        except Exception as e:
            self.log_bus.log(f"Scan failed: {e}", "error", "ProjectView")

    def handle_add_under_shared(self):
        try:
            # Check if project manager is available
            if not self.window().project_manager:
                QMessageBox.warning(self, "Add", "No project is currently loaded. Please load a project first.")
                self.log_bus.log("Cannot add videos: no project loaded.", "error", "ProjectView")
                return

            if not self._in_shared:
                self.log_bus.log("No items under shared root to add", "info", "ProjectView")
                return
            added = self.window().project_manager.register_unlinked_videos(iter(self._in_shared))
            self.log_bus.log(f"Added {added} videos under shared root", "success", "ProjectView")
        except Exception as e:
            self.log_bus.log(f"Add under shared failed: {e}", "error", "ProjectView")

    def handle_stage_off_shared(self):
        try:
            # Check if project manager is available
            if not self.window().project_manager:
                QMessageBox.warning(self, "Stage", "No project is currently loaded. Please load a project first.")
                self.log_bus.log("Cannot stage files: no project loaded.", "error", "ProjectView")
                return

            if not self._off_shared:
                QMessageBox.information(self, "Stage", "No off-shared items to stage.")
                return
            sr = self.window().project_manager.config.shared_root
            if not sr:
                QMessageBox.warning(self, "Stage", "Set shared root first in Project Settings.")
                return
            subdir = self.stage_subdir_line.text().strip()
            if not subdir:
                self.log_bus.log("Enter a destination subdirectory under shared root.", "warning", "ProjectView")
                return
            dest_base = Path(sr) / subdir

            # Convert to tuples for staging (Path, hash)
            src_with_hashes = list(self._off_shared)

            # Simple progress update
            self.scan_progress.setValue(0)
            def _cb(done: int, total: int):
                if total > 0:
                    self.scan_progress.setValue(max(0, min(100, int(done * 100 / total))))

            # staged_iter = self.data_manager.stage_files_to_shared(
            #     src_with_hashes,
            #     shared_root=Path(sr),
            #     dest_base=dest_base,
            #     overwrite=False,
            #     progress_cb=_cb,
            # )
            staged_iter = []  # Placeholder until integration is complete
            added = self.window().project_manager.register_unlinked_videos(staged_iter)
            QMessageBox.information(self, "Stage", f"Staged and added {added} videos.")
        except Exception as e:
            self.log_bus.log(f"Stage failed: {e}", "error", "ProjectView")

    def setup_targets_page(self):
        """Setup Targets management page (typed scan targets CRUD)."""
        self.targets_page = QWidget()
        layout = self.setup_page_layout(self.targets_page)

        list_group, list_layout = self.create_form_section("Scan Targets", layout)
        row = self.create_form_row(list_layout)
        self.targets_admin_list = QListWidget()
        self.targets_admin_list.setProperty("class", "mus1-list-widget")
        row.addWidget(self.targets_admin_list, 1)

        form_group, form_layout = self.create_form_section("Add Target", layout)
        r1 = self.create_form_row(form_layout)
        self.target_name_edit = QLineEdit()
        self.target_name_edit.setProperty("class", "mus1-text-input")
        self.target_kind_combo = QComboBox()
        self.target_kind_combo.setProperty("class", "mus1-combo-box")
        self.target_kind_combo.addItems(["local", "ssh", "wsl"])
        self.target_ssh_alias_edit = QLineEdit()
        self.target_ssh_alias_edit.setProperty("class", "mus1-text-input")
        r1.addWidget(self.create_form_label("Name:"))
        r1.addWidget(self.target_name_edit)
        r1.addWidget(self.create_form_label("Kind:"))
        r1.addWidget(self.target_kind_combo)
        r2 = self.create_form_row(form_layout)
        r2.addWidget(self.create_form_label("SSH Alias:"))
        r2.addWidget(self.target_ssh_alias_edit)
        r3 = self.create_form_row(form_layout)
        self.target_roots_edit = QLineEdit()
        self.target_roots_edit.setProperty("class", "mus1-text-input")
        self.target_roots_edit.setPlaceholderText("Roots (use ';' to separate multiple paths)")
        r3.addWidget(self.create_form_label("Roots:"))
        r3.addWidget(self.target_roots_edit, 1)

        btn_row = self.create_button_row(layout)
        add_btn = QPushButton("Add Target")
        add_btn.setProperty("class", "mus1-primary-button")
        add_btn.clicked.connect(self.handle_add_target)
        rem_btn = QPushButton("Remove Selected Target")
        rem_btn.setProperty("class", "mus1-secondary-button")
        rem_btn.clicked.connect(self.handle_remove_target)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)

        layout.addStretch(1)
        self.add_page(self.targets_page, "Targets")

        self.refresh_targets_admin_list()

    def refresh_targets_admin_list(self):
        if not hasattr(self, 'targets_admin_list'):
            return
        self.targets_admin_list.clear()
        try:
            targets = self.window().project_manager.config.settings.get('scan_targets', [])
        except Exception:
            targets = []
        for t in targets:
            roots_str = ", ".join(str(r) for r in t.get('roots', []))
            alias = t.get('ssh_alias', '') or ''
            item = QListWidgetItem(f"{t.get('name', '')}  kind={t.get('kind', '')}  alias={alias}  roots=[{roots_str}]")
            item.setData(Qt.ItemDataRole.UserRole, t.get('name', ''))
            self.targets_admin_list.addItem(item)

    def handle_add_target(self):
        try:
            # Check if project manager is available
            if not self.window().project_manager:
                QMessageBox.warning(self, "Targets", "No project is currently loaded. Please load a project first.")
                self.log_bus.log("Cannot add target: no project loaded.", "error", "ProjectView")
                return

            name = self.target_name_edit.text().strip()
            kind = self.target_kind_combo.currentText().strip()
            ssh_alias = self.target_ssh_alias_edit.text().strip() or None
            roots_raw = self.target_roots_edit.text().strip()
            if not name or not kind:
                QMessageBox.warning(self, "Targets", "Name and kind are required.")
                return
            if kind in ("ssh", "wsl") and not ssh_alias:
                QMessageBox.warning(self, "Targets", "SSH alias is required for ssh/wsl targets.")
                return
            roots: list[Path] = []
            if roots_raw:
                for part in roots_raw.split(';'):
                    p = part.strip()
                    if p:
                        roots.append(Path(p).expanduser())
            if not roots:
                QMessageBox.warning(self, "Targets", "At least one root path is required.")
                return
            targets = self.window().project_manager.config.settings.get('scan_targets', [])
            if any(t.get('name') == name for t in targets):
                QMessageBox.warning(self, "Targets", f"Target '{name}' already exists.")
                return
            target_dict = {
                'name': name,
                'kind': kind,
                'roots': roots,
                'ssh_alias': ssh_alias
            }
            targets.append(target_dict)
            self.window().project_manager.config.settings['scan_targets'] = targets
            self.window().project_manager.save_project()
            self.refresh_targets_admin_list()
            self.refresh_targets_list()
            self.log_bus.log(f"Added target {name}", "success", "ProjectView")
        except Exception as e:
            self.log_bus.log(f"Add target failed: {e}", "error", "ProjectView")

    def handle_remove_target(self):
        try:
            # Check if project manager is available
            if not self.window().project_manager:
                QMessageBox.warning(self, "Targets", "No project is currently loaded. Please load a project first.")
                self.log_bus.log("Cannot remove target: no project loaded.", "error", "ProjectView")
                return

            item = self.targets_admin_list.currentItem()
            if not item:
                self.log_bus.log("Select a target to remove", "info", "ProjectView")
                return
            name = item.data(Qt.ItemDataRole.UserRole)
            targets = self.window().project_manager.config.settings.get('scan_targets', [])
            before = len(targets)
            targets = [t for t in targets if t.get('name') != name]
            self.window().project_manager.config.settings['scan_targets'] = targets
            if len(targets) == before:
                self.log_bus.log(f"No target named '{name}' found", "info", "ProjectView")
                return
            self.window().project_manager.save_project()
            self.refresh_targets_admin_list()
            self.refresh_targets_list()
            self.log_bus.log(f"Removed target {name}", "success", "ProjectView")
        except Exception as e:
            self.log_bus.log(f"Remove target failed: {e}", "error", "ProjectView")

    def handle_browse_lab_library(self):
        try:
            main_window = self.window()
            if not main_window:
                return
            # Switch to Lab tab
            if hasattr(main_window, 'navigation_tabs'):
                # Find the Lab tab index by title
                for i in range(main_window.navigation_tabs.count()):
                    if main_window.navigation_tabs.tabText(i).lower().startswith("lab"):
                        main_window.navigation_tabs.setCurrentIndex(i)
                        break
            # Ensure LabView selects current lab and opens Lab Library page
            if hasattr(main_window, 'lab_view') and main_window.lab_view:
                # Trigger refresh and auto-select
                main_window.lab_view.refresh_lab_data()
                # Open Lab Library page if available
                if hasattr(main_window.lab_view, 'change_page'):
                    # Lab Library is page index 1 per setup
                    main_window.lab_view.change_page(1)
        except Exception:
            pass

        
   