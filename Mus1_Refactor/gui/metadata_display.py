from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, 
    QLabel, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSizePolicy, QHBoxLayout,
    QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from datetime import datetime
from typing import Any, Union

class SortableTableWidgetItem(QTableWidgetItem):
    """A QTableWidgetItem subclass that sorts based on underlying data, not just text."""
    def __init__(self, text: str, sort_key_data: Any):
        super().__init__(text)
        self.sort_key_data = sort_key_data

    def __lt__(self, other: 'SortableTableWidgetItem') -> bool:
        """Compare based on the sort_key_data."""
        try:
            # Handle None values (e.g., place them at the beginning or end)
            if self.sort_key_data is None and other.sort_key_data is None:
                return False # Equal
            if self.sort_key_data is None:
                return True # None is considered "less than" anything else
            if other.sort_key_data is None:
                return False # Anything else is "greater than" None

            # Attempt direct comparison (works for numbers, dates, etc.)
            return self.sort_key_data < other.sort_key_data
        except TypeError:
            # Fallback to string comparison if direct comparison fails
            return self.text() < other.text()
        except Exception as e:
            # Log unexpected errors during comparison
            # In a real app, use a proper logging mechanism
            print(f"Error comparing table items: {e}")
            return super().__lt__(other) # Fallback to default comparison

class SubjectTreeWidgetItem(QTreeWidgetItem):
    """Custom tree item that enables numeric-aware sorting for the overview tree."""
    def __lt__(self, other: 'SubjectTreeWidgetItem') -> bool:
        # Obtain column currently being sorted
        tree = self.treeWidget()
        if tree is None:
            return super().__lt__(other)
        column = tree.sortColumn()
        # Columns: 0 Subject ID, 1 Sex, 2 Genotype, 3 Experiments
        # For numeric columns (0, 3, 4) attempt int comparison (4 = Recordings)
        if column in (0, 3, 4):
            try:
                return int(self.text(column)) < int(other.text(column))
            except ValueError:
                # Fallback to standard string compare
                return self.text(column) < other.text(column)
        # For lexical columns compare case-insensitive
        else:
            return self.text(column).lower() < other.text(column).lower()

class MetadataTreeView(QTreeWidget):
    """
    Standardized tree view for hierarchical metadata display.
    
    Features:
    - Consistent styling with MUS1 design guidelines
    - Theme awareness with update_theme method 
    - Multiple hierarchical display modes for different data types
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Apply class-based styling
        self.setObjectName("metadataTree")
        self.setProperty("class", "mus1-tree-view")
        
        # Set up tree view appearance
        self.setHeaderHidden(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setSelectionBehavior(QTreeWidget.SelectRows)
        # Disable inline editing by default – SubjectView toggles this
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Configure sizing
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Enable clickable header sorting
        header = self.header()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        self.setSortingEnabled(True)
        
    def populate_subjects_with_experiments(self, subjects_dict, experiments_dict, state_manager=None):
        """
        Populate tree with subjects as parents and experiments as children.
        Adds a Genotype column when available so users can quickly see subject genotypes.
        """
        self.clear()
        # New header includes Genotype column
        self.setHeaderLabels(["Subject ID", "Sex", "Genotype", "Experiments", "Recordings"])
        
        for subject_id, subject in subjects_dict.items():
            item = SubjectTreeWidgetItem(self)
            # Allow editing (SubjectView guards commit handling)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setText(0, subject_id)
            item.setText(1, subject.sex.value if hasattr(subject.sex, 'value') else str(subject.sex))
            # Safely handle missing genotype values
            genotype_str = getattr(subject, 'genotype', None) or "N/A"
            item.setText(2, str(genotype_str))
            
            # Count experiments
            subject_experiments = [exp for exp in experiments_dict.values() if exp.subject_id == subject_id]
            item.setText(3, str(len(subject_experiments)))
            # Recording count per subject
            rec_count = 0
            if state_manager is not None:
                try:
                    rec_count = state_manager.get_recording_count_for_subject(subject_id)
                except Exception:
                    pass
            item.setText(4, str(rec_count))
            
            # Add experiment children
            for experiment in subject_experiments:
                exp_item = SubjectTreeWidgetItem(item)
                exp_item.setText(0, experiment.id)
                exp_item.setText(1, "")  # Sex column blank for experiments
                exp_item.setText(2, "")  # Genotype column blank for experiments
                exp_item.setText(3, experiment.type)
                # Column 4 – recordings per experiment
                rec_exp = 0
                if state_manager is not None:
                    try:
                        rec_exp = state_manager.get_recording_count_for_experiment(experiment.id)
                    except Exception:
                        pass
                exp_item.setText(4, str(rec_exp))
        
        # Expand all items for better visibility
        self.expandAll()
        
        # Resize columns to content
        for i in range(self.columnCount()):
            self.resizeColumnToContents(i)
        
    def populate_experiments_by_type(self, experiments_dict):
        """
        Group experiments by type in a hierarchical view.
        
        Args:
            experiments_dict: Dictionary of experiment ID to ExperimentMetadata
        """
        self.clear()
        self.setHeaderLabels(["Type/ID", "Subject", "Date"])
        
        # Group experiments by type
        exp_by_type = {}
        for exp_id, exp in experiments_dict.items():
            if exp.type not in exp_by_type:
                exp_by_type[exp.type] = []
            exp_by_type[exp.type].append(exp)
        
        # Add to tree
        for exp_type, exps in exp_by_type.items():
            type_item = SubjectTreeWidgetItem(self)
            type_item.setText(0, exp_type)
            type_item.setText(1, f"{len(exps)} experiments")
            type_item.setText(2, "")
            
            # Add individual experiments
            for exp in exps:
                exp_item = SubjectTreeWidgetItem(type_item)
                exp_item.setText(0, exp.id)
                exp_item.setText(1, exp.subject_id)
                
                # Format date if available
                date_str = "N/A"
                if hasattr(exp, 'date_recorded') and exp.date_recorded:
                    date_str = exp.date_recorded.strftime("%Y-%m-%d") if isinstance(exp.date_recorded, datetime) else str(exp.date_recorded)
                elif hasattr(exp, 'recorded_date') and exp.recorded_date:
                    date_str = exp.recorded_date.strftime("%Y-%m-%d") if isinstance(exp.recorded_date, datetime) else str(exp.recorded_date)
                
                exp_item.setText(2, date_str)
        
        # Expand all items for better visibility
        self.expandAll()
        
        # Resize columns to content
        for i in range(self.columnCount()):
            self.resizeColumnToContents(i)
        
    def populate_experiments_by_phase(self, experiments_dict):
        """
        Group experiments by their phase in the workflow.
        
        Args:
            experiments_dict: Dictionary of experiment ID to ExperimentMetadata
        """
        self.clear()
        self.setHeaderLabels(["Phase", "ID", "Type"])
        
        # Group experiments by phase/processing stage
        exp_by_phase = {}
        for exp_id, exp in experiments_dict.items():
            # Get phase from processing_stage or phase attribute
            phase = getattr(exp, 'processing_stage', None)
            if not phase:
                phase = getattr(exp, 'phase', 'Unknown')
            
            if phase not in exp_by_phase:
                exp_by_phase[phase] = []
            exp_by_phase[phase].append(exp)
        
        # Add to tree
        for phase, exps in exp_by_phase.items():
            phase_item = SubjectTreeWidgetItem(self)
            phase_item.setText(0, str(phase))
            phase_item.setText(1, f"{len(exps)} experiments")
            phase_item.setText(2, "")
            
            # Add individual experiments
            for exp in exps:
                exp_item = SubjectTreeWidgetItem(phase_item)
                exp_item.setText(0, "")
                exp_item.setText(1, exp.id)
                exp_item.setText(2, exp.type)
        
        # Expand all items for better visibility
        self.expandAll()
        
        # Resize columns to content
        for i in range(self.columnCount()):
            self.resizeColumnToContents(i)
    
    def update_theme(self):
        """Update the component to reflect theme changes."""
        # Refresh styles when theme changes
        self.style().unpolish(self)
        self.style().polish(self)


class MetadataGridDisplay(QWidget):
    """
    A standardized grid display for subjects/experiments with sorting capability.
    
    Features:
    - Consistent styling with MUS1 design guidelines
    - Theme awareness with update_theme method
    - Selection capability with checkboxes
    - Sorting functionality
    
    Signals:
        selection_changed: Emitted when an item is selected/deselected (experiment_id, is_selected)
    """
    
    # Signal emitted when an item is selected/deselected
    selection_changed = Signal(str, bool)  # experiment_id, is_selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Apply class-based styling
        self.setObjectName("metadataGrid")
        self.setProperty("class", "mus1-data-grid")
        
        # Create layout with minimal margins
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Table to display metadata
        self.table = QTableWidget(self)
        self.table.setObjectName("metadataTable")
        self.table.setProperty("class", "mus1-table-view")
        
        # Configure table appearance
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSortingEnabled(True)
        
        # Configure header
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setProperty("class", "mus1-table-header")

        # Add table to layout
        layout.addWidget(self.table)
        
        # Track checkboxes for selectable mode
        self.checkboxes = {}
        self.selectable = False
        self.checkbox_column = None
        
        # Configure sizing
        self.setMinimumHeight(200)
        
    def set_columns(self, columns):
        """
        Set the column headers for the table.
        
        Args:
            columns: List of column names
        """
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        
    def populate_data(self, items, columns, selectable=False, checkbox_column=None):
        """
        Populate table using a list of dicts where keys match the column names.
        Uses SortableTableWidgetItem for specific columns like Date and Stage.
        
        Args:
            items: List of dicts containing data for each row.
                   Expected keys should match column names.
                   For sortable columns (Date, Stage), the dict should contain
                   both the display string (e.g., "Date") and the raw data
                   (e.g., "raw_date" containing a datetime object).
            columns: List of column names to display.
            selectable: Whether to add checkboxes for selection.
            checkbox_column: Name of the column to display checkboxes in.
        """
        # Clear checkbox tracking
        self.checkboxes = {}
        self.selectable = selectable
        self.checkbox_column = checkbox_column
        
        # Define a mapping for stage sorting order
        stage_order = {"planned": 0, "recorded": 1, "tracked": 2, "interpreted": 3}
        
        if self.table.columnCount() != len(columns):
            self.set_columns(columns)
            
        self.table.setSortingEnabled(False) # Disable sorting during population
        self.table.setRowCount(0)
        self.table.setRowCount(len(items))
        
        for row, item_data in enumerate(items):
            # Assuming 'ID' key exists and is unique for checkbox mapping
            item_id = item_data.get("ID", "")
            if not item_id:
                 # Fallback or log warning if ID is missing
                 item_id = f"row_{row}"

            for col, key in enumerate(columns):
                display_value = str(item_data.get(key, ''))
                
                # Handle checkbox column
                if selectable and key == checkbox_column:
                    checkbox = QCheckBox()
                    checkbox.setProperty("class", "mus1-checkbox")
                    # Use the boolean value directly from the data dict for initial state
                    checkbox.setChecked(bool(item_data.get(key, False)))
                    self.checkboxes[item_id] = checkbox
                    # Connect signal using the unique item_id
                    checkbox.stateChanged.connect(lambda state, id=item_id:
                        self.selection_changed.emit(id, state == Qt.CheckState.Checked))
                    
                    # Center the checkbox in the cell
                    cell_widget = QWidget()
                    layout = QHBoxLayout(cell_widget)
                    layout.addWidget(checkbox)
                    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    layout.setContentsMargins(0,0,0,0)
                    self.table.setCellWidget(row, col, cell_widget)

                # Handle specific columns for custom sorting
                elif key == "Date":
                     # Expect raw_date in item_data
                     raw_date = item_data.get("raw_date", None)
                     table_item = SortableTableWidgetItem(display_value, raw_date)
                     self.table.setItem(row, col, table_item)
                elif key == "Stage":
                     # Expect raw_stage (the string) in item_data
                     raw_stage = item_data.get("raw_stage", None)
                     # Map stage string to its sort order number
                     sort_key = stage_order.get(raw_stage.lower() if raw_stage else None, 99) # Default to last if unknown
                     table_item = SortableTableWidgetItem(display_value, sort_key)
                     self.table.setItem(row, col, table_item)

                elif key == "Recordings":
                     sort_key = int(item_data.get("Recordings", 0))
                     table_item = SortableTableWidgetItem(display_value, sort_key)
                     self.table.setItem(row, col, table_item)

                # Default handling for other columns
                else:
                    # Use standard QTableWidgetItem if no special sorting needed
                    # Pass the display value itself as the sort key for basic text sorting
                    table_item = SortableTableWidgetItem(display_value, display_value.lower())
                    self.table.setItem(row, col, table_item)

                # Common alignment for non-checkbox cells
                if not (selectable and key == checkbox_column):
                    self.table.item(row, col).setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                
        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(True) # Re-enable sorting
        
    def populate_subjects(self, subjects_dict):
        """
        Populate the grid with subject data. Needs update if sorting is desired.
        """
        # TODO: Update this method if enhanced sorting is needed for subjects
        # Currently uses standard populate_data which relies on text sorting
        # Might need to pass raw dates etc. similarly to experiments
        columns = ["id", "sex", "genotype", "birth_date", "treatment"]
        items = []
        
        for subj_id, subject in subjects_dict.items():
            # Extract birth date string if available
            birth_date_obj = getattr(subject, 'birth_date', None)
            birth_date_str = "N/A"
            if birth_date_obj and isinstance(birth_date_obj, datetime):
                birth_date_str = birth_date_obj.strftime("%Y-%m-%d")
            
            item = {
                "id": subject.id,
                "sex": subject.sex.value if hasattr(subject.sex, 'value') else str(subject.sex),
                "genotype": subject.genotype or "N/A",
                "birth_date": birth_date_str, # Display string
                # "raw_birth_date": birth_date_obj, # Pass raw date for sorting if needed
                "treatment": subject.treatment or "N/A"
            }
            items.append(item)
            
        self.populate_data(items, columns) # Standard text sorting for now
        
    def populate_experiments(self, experiments_dict, selectable=False):
        """
        Populate the grid with experiment data. Passes raw data for sorting.
        
        Args:
            experiments_dict: Dictionary of experiment ID to ExperimentMetadata
            selectable: Whether to add checkboxes for selection
        """
        # Define the columns we want to display
        columns = ["Select", "ID", "Type", "Subject", "Date", "Stage", "Recordings"]
        items = []
        
        for exp_id, exp in experiments_dict.items():
            # Get raw data for sorting
            raw_date = getattr(exp, 'date_recorded', None)
            raw_stage = getattr(exp, 'processing_stage', None)
            
            # Format date string for display
            date_str = "N/A"
            if raw_date and isinstance(raw_date, datetime):
                 date_str = raw_date.strftime("%Y-%m-%d")
            elif raw_date: # If it's not a datetime, try converting (basic)
                 try:
                     date_str = datetime.fromisoformat(str(raw_date)).strftime("%Y-%m-%d")
                 except (ValueError, TypeError): pass # Keep N/A on error
            
            item = {
                # Data for Grid
                "Select": False,  # Default checkbox state
                "ID": getattr(exp, 'id', 'N/A'),
                "Type": getattr(exp, 'type', 'N/A'),
                "Subject": getattr(exp, 'subject_id', 'N/A'),
                "Date": date_str, # Display string
                "Stage": raw_stage or 'N/A', # Display string (use raw stage directly)
                "Recordings": 0,
                # Raw data for sorting keys used in populate_data
                "raw_date": raw_date,
                "raw_stage": raw_stage
            }
            # Determine recording count if a state manager reference is available via parent widget chain
            try:
                root_window = self.window()
                if hasattr(root_window, 'state_manager'):
                    item["Recordings"] = root_window.state_manager.get_recording_count_for_experiment(exp.id)
            except Exception:
                pass
            items.append(item)
            
        # Call populate_data which now uses SortableTableWidgetItem
        self.populate_data(items, columns, selectable=selectable, checkbox_column="Select" if selectable else None)
        
    def get_selected_items(self):
        """
        Return a list of selected item IDs.
        
        Returns:
            List of IDs for checked items
        """
        return [item_id for item_id, checkbox in self.checkboxes.items() 
                if checkbox.isChecked()]
    
    def update_theme(self):
        """Update the component to reflect theme changes."""
        # Refresh styles when theme changes
        self.style().unpolish(self)
        self.style().polish(self)
        self.table.style().unpolish(self.table)
        self.table.style().polish(self.table) 