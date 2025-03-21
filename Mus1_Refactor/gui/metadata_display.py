from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, 
    QLabel, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from datetime import datetime

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
        
        # Configure sizing
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
    def populate_subjects_with_experiments(self, subjects_dict, experiments_dict):
        """
        Populate tree with subjects as parents and experiments as children.
        
        Args:
            subjects_dict: Dictionary of subject ID to SubjectMetadata
            experiments_dict: Dictionary of experiment ID to ExperimentMetadata
        """
        self.clear()
        self.setHeaderLabels(["Subject ID", "Sex", "Experiments"])
        
        for subject_id, subject in subjects_dict.items():
            item = QTreeWidgetItem(self)
            item.setText(0, subject_id)
            item.setText(1, subject.sex.value if hasattr(subject.sex, 'value') else str(subject.sex))
            
            # Count experiments
            subject_experiments = [exp for exp_id, exp in experiments_dict.items() 
                                if exp.subject_id == subject_id]
            item.setText(2, str(len(subject_experiments)))
            
            # Add experiment children
            for experiment in subject_experiments:
                exp_item = QTreeWidgetItem(item)
                exp_item.setText(0, experiment.id)
                exp_item.setText(1, "")
                exp_item.setText(2, experiment.type)
                
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
            type_item = QTreeWidgetItem(self)
            type_item.setText(0, exp_type)
            type_item.setText(1, f"{len(exps)} experiments")
            type_item.setText(2, "")
            
            # Add individual experiments
            for exp in exps:
                exp_item = QTreeWidgetItem(type_item)
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
            phase_item = QTreeWidgetItem(self)
            phase_item.setText(0, str(phase))
            phase_item.setText(1, f"{len(exps)} experiments")
            phase_item.setText(2, "")
            
            # Add individual experiments
            for exp in exps:
                exp_item = QTreeWidgetItem(phase_item)
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
        
        Args:
            items: List of dicts containing data for each row
            columns: List of column names
            selectable: Whether to add checkboxes for selection
            checkbox_column: Name of the column to display checkboxes in
        """
        # Clear checkbox tracking
        self.checkboxes = {}
        self.selectable = selectable
        self.checkbox_column = checkbox_column
        
        # Set columns if they haven't been set
        if self.table.columnCount() != len(columns):
            self.set_columns(columns)
            
        # Clear existing rows
        self.table.setRowCount(0)
        
        # Add new rows
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, key in enumerate(columns):
                value = item.get(key, '')
                
                # Handle checkbox column
                if selectable and key == checkbox_column:
                    checkbox = QCheckBox()
                    checkbox.setProperty("class", "mus1-checkbox")
                    checkbox.setChecked(bool(value))
                    
                    # Store item ID for tracking
                    item_id = item.get("id", "")
                    self.checkboxes[item_id] = checkbox
                    
                    # Connect checkbox state change
                    checkbox.stateChanged.connect(lambda state, id=item_id: 
                        self.selection_changed.emit(id, state == Qt.Checked))
                    
                    self.table.setCellWidget(row, col, checkbox)
                else:
                    # Regular cell
                    if value is None:
                        value = ""
                    else:
                        value = str(value)
                    table_item = QTableWidgetItem(value)
                    table_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    self.table.setItem(row, col, table_item)
                
        # Resize rows and columns to content
        self.table.resizeRowsToContents()
        for i in range(self.table.columnCount()):
            self.table.resizeColumnToContents(i)
        
    def populate_subjects(self, subjects_dict):
        """
        Populate the grid with subject data.
        
        Args:
            subjects_dict: Dictionary of subject ID to SubjectMetadata
        """
        columns = ["id", "sex", "genotype", "birth_date", "treatment"]
        items = []
        
        for subj_id, subject in subjects_dict.items():
            # Extract birth date string if available
            birth_date_str = "N/A"
            if hasattr(subject, 'birth_date') and subject.birth_date:
                birth_date_str = subject.birth_date.strftime("%Y-%m-%d") if isinstance(subject.birth_date, datetime) else str(subject.birth_date)
            
            item = {
                "id": subject.id,
                "sex": subject.sex.value if hasattr(subject.sex, 'value') else str(subject.sex),
                "genotype": subject.genotype or "N/A",
                "birth_date": birth_date_str,
                "treatment": subject.treatment or "N/A"
            }
            items.append(item)
            
        self.populate_data(items, columns)
        
    def populate_experiments(self, experiments_dict, selectable=False):
        """
        Populate the grid with experiment data.
        
        Args:
            experiments_dict: Dictionary of experiment ID to ExperimentMetadata
            selectable: Whether to add checkboxes for selection
        """
        columns = ["select", "id", "type", "subject_id", "date_recorded", "processing_stage", "data_source"]
        items = []
        
        for exp_id, exp in experiments_dict.items():
            # Extract date string if available
            date_str = "N/A"
            if hasattr(exp, 'date_recorded') and exp.date_recorded:
                date_str = exp.date_recorded.strftime("%Y-%m-%d") if isinstance(exp.date_recorded, datetime) else str(exp.date_recorded)
            elif hasattr(exp, 'recorded_date') and exp.recorded_date:
                date_str = exp.recorded_date.strftime("%Y-%m-%d") if isinstance(exp.recorded_date, datetime) else str(exp.recorded_date)
            
            item = {
                "select": False,  # Default checkbox state
                "id": exp.id,
                "type": exp.type,
                "subject_id": exp.subject_id,
                "date_recorded": date_str,
                "processing_stage": getattr(exp, 'processing_stage', 'N/A'),
                "data_source": getattr(exp, 'data_source', 'N/A')
            }
            items.append(item)
            
        self.populate_data(items, columns, selectable=selectable, checkbox_column="select" if selectable else None)
        
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