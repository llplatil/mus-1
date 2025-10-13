# Qt imports - unified PyQt6 facade
from .qt import (
    Qt,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QLabel,
    QGroupBox,
)

from .navigation_pane import NavigationPane
from .view_lifecycle import ViewLifecycle
import logging

logger = logging.getLogger(__name__)

class BaseView(QWidget, ViewLifecycle):
    """
    Base view class that implements the standardized layout structure for MUS1.
    All main tab views (ProjectView, SubjectsView, etc.) should inherit from this class.
    
    Features:
    - Consistent layout with QSplitter
    - Navigation pane on the left
    - Content area on the right with QStackedWidget for pages
    - Consistent styling and proportions
    """
    
    # Standardized layout constants for consistent UI
    PAGE_MARGIN = 10          # Margin around page content (compensates for QGroupBox title positioning)
    SECTION_SPACING = 15       # Spacing between major sections
    CONTROL_SPACING = 10       # Spacing between controls within a section
    LABEL_SPACING = 5          # Spacing between labels and their controls
    FORM_MARGIN = 10           # Margin inside form groups
    GROUP_TITLE_HEIGHT = 20    # Space reserved for QGroupBox titles (accounts for CSS positioning)
    LABEL_MIN_WIDTH = 65       # Minimum width for form labels
    
    def __init__(self, parent=None, view_name=None):
        """
        Initialize the base view with standard layout structure.
        
        Args:
            parent: Parent widget
            view_name: Name of the view for logging and object names
        """
        super().__init__(parent)
        
        # Set object name and class for styling
        self.setObjectName(f"{view_name or 'base'}View")
        self.setProperty("class", "mus1-view")
        
        # Store navigation button texts for this view
        self.navigation_button_texts = []
        
        # Initialize the outer layout with zero margins for full component coverage
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Create a horizontal splitter (standard layout pattern)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setChildrenCollapsible(False)
        # Removed inline style for splitter handle; now using stylesheet version
        # self.splitter.setStyleSheet("QSplitter::handle { background-color: $BORDER_COLOR; }")
        
        # Create the navigation pane (left panel)
        self.navigation_pane = NavigationPane(self)
        self.splitter.addWidget(self.navigation_pane)
        
        # Create the content area (right panel)
        self.content_area = QWidget()
        self.content_area.setProperty("class", "mus1-content-area")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN)
        self.content_layout.setSpacing(self.SECTION_SPACING)
        
        # Create the stacked widget for pages
        self.pages = QStackedWidget()
        self.content_layout.addWidget(self.pages)
        
        # Add content area to splitter
        self.splitter.addWidget(self.content_area)
        
        # Set initial splitter ratio based on navigation pane width
        nav_width = self.navigation_pane.FIXED_WIDTH
        content_width = max(800, self.width()) - nav_width  # Ensure reasonable initial size
        self.splitter.setSizes([nav_width, content_width])
        
        # Add splitter to main layout
        self.layout.addWidget(self.splitter)
        
        # Connect navigation buttons to page changes
        self.navigation_pane.button_clicked.connect(self.change_page)

        # Lifecycle storage
        self._services = None

    # --- Lifecycle hooks (no-op defaults) ---
    def on_services_ready(self, services):
        self._services = services

    def on_activated(self):
        pass

    def on_deactivated(self):
        pass
    
    def create_form_section(self, title, parent_layout=None, is_subgroup=False):
        """
        Create a standardized form section with consistent styling.
        
        Args:
            title: Title for the form section
            parent_layout: Optional parent layout to add the section to
            is_subgroup: Whether this is a subgroup within another form section
            
        Returns:
            tuple: (group_box, layout) - The group box and its internal layout
        """
        group = QGroupBox(title)
        group.setProperty("class", "mus1-subgroup" if is_subgroup else "mus1-input-group")
        layout = QVBoxLayout(group)
        
        # Tighter margins for better spacing of form elements
        layout.setContentsMargins(self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        
        # Use slightly tighter spacing between controls
        layout.setSpacing(8)
        
        if parent_layout:
            parent_layout.addWidget(group)
            
        return group, layout
        
    def create_form_row(self, parent_layout=None):
        """
        Create a standardized form row with consistent spacing.
        Adds the row to the parent_layout if provided.

        Args:
            parent_layout: Optional parent layout to add the row to

        Returns:
            QHBoxLayout: The row layout
        """
        row = QHBoxLayout()
        row.setSpacing(self.CONTROL_SPACING)
        row.setContentsMargins(0, 0, 0, 0)
        row.setProperty("class", "form-row")
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        if parent_layout: # Add the layout back here
            parent_layout.addLayout(row)
        return row

    def create_form_label(self, text, parent=None, fixed_width=True):
        """Create a standard label with proper styling for forms.

        Args:
            text (str): The label text
            parent (QWidget, optional): Parent widget. Defaults to None.
            fixed_width (bool): Whether to use fixed width for alignment. Defaults to True.

        Returns:
            QLabel: The styled label
        """
        from .qt import QLabel
        label = QLabel(text, parent)
        label.setProperty("formLabel", True)
        if fixed_width:
            label.setFixedWidth(120)  # Fixed width for perfect alignment
        else:
            label.setMinimumWidth(65)  # Minimum width for legacy compatibility
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label
    
    def setup_navigation(self, button_texts):
        """Setup navigation buttons specific to this tab/view.
        
        Args:
            button_texts: List of button text labels for this view
        """
        self.navigation_button_texts = button_texts
        
        # Clear any existing buttons
        self.navigation_pane.clear_buttons()
        
        # Add new buttons
        for text in button_texts:
            self.navigation_pane.add_button(text)
        
        # Update button stack sizing and log space
        self.navigation_pane.update_button_stack_size()
        
        # Set a fixed width for the navigation pane to match the constant
        self.navigation_pane.setFixedWidth(self.navigation_pane.FIXED_WIDTH)
    
    def add_navigation_button(self, text):
        """Add a button to the navigation pane and return its index.
        
        Note: This method should be used for individual button additions.
        For setting up the complete navigation, use setup_navigation().
        """
        self.navigation_button_texts.append(text)
        return self.navigation_pane.add_button(text)
    
    def add_page(self, widget, title=None):
        """
        Add a page to the stacked widget.
        
        Args:
            widget: The widget to add as a page
            title: Optional title for the page
            
        Returns:
            The index of the added page
        """
        if title:
            widget.setWindowTitle(title)
        
        # Set consistent styling for the page
        widget.setProperty("class", "mus1-page")
        
        # Add the page to the stacked widget
        index = self.pages.addWidget(widget)
        return index
    
    def change_page(self, index):
        """
        Change to the specified page and update navigation button selection.
        
        Args:
            index: The index of the page to display
        """
        logger.debug(f"[{self.objectName()}] BaseView.change_page received click for index: {index}") # Log which view received click
        if 0 <= index < self.pages.count():
            logger.debug(f"  Setting stacked widget current index to: {index}")
            self.pages.setCurrentIndex(index)
            # Call the navigation pane's method to update the button visually
            self.navigation_pane.set_button_checked(index)
        else:
             logger.warning(f"[{self.objectName()}] Attempted to change to invalid page index: {index} (Page count: {self.pages.count()})")
    
    def add_log_message(self, message, level='info'):
        """Add a message to the navigation pane's log display."""
        self.navigation_pane.add_log_message(message, level)
    
    def update_theme(self, theme):
        """Update theme-specific elements when the theme changes."""
        # Propagate the theme to the navigation pane
        if hasattr(self, 'navigation_pane'):
            self.navigation_pane.update_theme(theme)
        
        # Set the theme property and update styling
        self.setProperty("theme", theme)
        self.style().unpolish(self)
        self.style().polish(self)
    
    def resizeEvent(self, event):
        """
        Handle resize events for the base view.
        Ensures navigation pane is properly sized and maintains proper splitter proportions.
        """
        super().resizeEvent(event)
        
        # This is the centralized place to update navigation pane sizing
        if hasattr(self, 'navigation_pane'):
            # Ensure navigation pane has correct fixed width
            self.navigation_pane.setFixedWidth(self.navigation_pane.FIXED_WIDTH)
            
            # Update button stack sizing within navigation pane
            self.navigation_pane.update_button_stack_size()
            
            # Maintain proper splitter proportions
            current_sizes = self.splitter.sizes()
            if len(current_sizes) >= 2:
                if current_sizes[0] != self.navigation_pane.FIXED_WIDTH:
                    nav_width = self.navigation_pane.FIXED_WIDTH
                    content_width = self.width() - nav_width
                    self.splitter.setSizes([nav_width, content_width])
    
    def showEvent(self, event):
        """
        Handle show events to ensure proper layout sizing.
        Triggers a resize event to ensure everything is properly sized.
        """
        super().showEvent(event)
        # Trigger a resize event to ensure proper sizing
        self.resizeEvent(None)
    
    def create_button_row(self, parent_layout=None, add_stretch=True):
        """
        Create a standardized row for buttons with consistent styling and stretch.

        Args:
            parent_layout: Optional parent layout to add the row to
            add_stretch: Whether to add a stretch at the end of the row

        Returns:
            QHBoxLayout: The row layout configured for buttons
        """
        # Call the original create_form_row which adds the layout to parent_layout
        row = self.create_form_row(parent_layout)

        # Add stretch if requested
        if add_stretch:
            row.addStretch(1)

        return row

    def setup_page_layout(self, page_widget, spacing=None):
        """
        Set up a standardized layout for a page widget.

        Args:
            page_widget: The QWidget to set up with a layout
            spacing: Optional spacing override, defaults to SECTION_SPACING

        Returns:
            QVBoxLayout: The configured layout
        """
        from .qt import QVBoxLayout
        layout = QVBoxLayout(page_widget)
        layout.setSpacing(spacing if spacing is not None else self.SECTION_SPACING)
        # Use PAGE_MARGIN for top to account for QGroupBox title positioning
        layout.setContentsMargins(self.FORM_MARGIN, self.PAGE_MARGIN, self.FORM_MARGIN, self.FORM_MARGIN)
        return layout

    def create_labeled_input_row(self, label_text, input_widget, parent_layout):
        """
        Create a standardized row with a label and input widget.
        Uses fixed-width labels for perfect alignment.

        Args:
            label_text: Text for the label (without colon)
            input_widget: The input widget (QLineEdit, QComboBox, etc.)
            parent_layout: Layout to add the row to

        Returns:
            QHBoxLayout: The created row layout
        """
        from .qt import QHBoxLayout

        # Create the row with consistent label width and field alignment
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.LABEL_SPACING)

        # Fixed-width label column for perfect alignment
        label = QLabel(f"{label_text}:")
        label.setProperty("formLabel", True)
        label.setFixedWidth(120)  # Fixed width for consistent alignment
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)

        # Add the input widget with stretch
        row.addWidget(input_widget, 1)

        if parent_layout:
            parent_layout.addLayout(row)

        return row

    def create_form_with_list(self, title, list_widget, parent_layout):
        """
        Create a standardized form section containing a list widget.

        Args:
            title: Title for the form section
            list_widget: The QListWidget to include
            parent_layout: Parent layout to add the section to

        Returns:
            tuple: (group_box, layout) - The group box and its layout
        """
        group, layout = self.create_form_section(title, parent_layout)
        layout.addWidget(list_widget)
        return group, layout

    def create_button_row_centered(self, buttons, parent_layout):
        """
        Create a standardized button row with centered buttons.

        Args:
            buttons: List of QPushButton widgets
            parent_layout: Parent layout to add the row to

        Returns:
            QHBoxLayout: The created button row layout
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.CONTROL_SPACING)
        row.addStretch(1)  # Left stretch

        for button in buttons:
            row.addWidget(button)

        row.addStretch(1)  # Right stretch
        parent_layout.addLayout(row)
        return row

    def create_two_column_form(self, left_inputs, right_inputs, parent_layout):
        """
        Create a two-column form layout with labeled inputs.

        Args:
            left_inputs: List of (label_text, input_widget) tuples for left column
            right_inputs: List of (label_text, input_widget) tuples for right column
            parent_layout: Parent layout to add the form to

        Returns:
            QHBoxLayout: The main form layout
        """
        main_row = QHBoxLayout()
        main_row.setSpacing(self.SECTION_SPACING)

        # Left column
        left_layout = QVBoxLayout()
        left_layout.setSpacing(self.LABEL_SPACING)
        for label_text, input_widget in left_inputs:
            row = QHBoxLayout()
            row.setSpacing(self.LABEL_SPACING)
            label = self.create_form_label(label_text)
            row.addWidget(label)
            row.addWidget(input_widget)
            left_layout.addLayout(row)

        # Right column
        right_layout = QVBoxLayout()
        right_layout.setSpacing(self.LABEL_SPACING)
        for label_text, input_widget in right_inputs:
            row = QHBoxLayout()
            row.setSpacing(self.LABEL_SPACING)
            label = self.create_form_label(label_text)
            row.addWidget(label)
            row.addWidget(input_widget)
            right_layout.addLayout(row)

        main_row.addLayout(left_layout)
        main_row.addLayout(right_layout)
        parent_layout.addLayout(main_row)
        return main_row

    def create_form_field(self, label_text, widget_type="line_edit", placeholder="", required=False, parent_layout=None):
        """
        Create a standardized form field with label and input widget.
        Uses a two-column grid approach for perfect alignment.

        Args:
            label_text: Text for the label (without colon, will be added)
            widget_type: Type of widget - "line_edit", "combo_box", "text_edit", "spin_box", "double_spin_box", "check_box", "date_time_edit"
            placeholder: Placeholder text for input widgets
            required: Whether this field is required (adds * to label)
            parent_layout: Layout to add the field to

        Returns:
            tuple: (row_layout, widget) - The row layout and the created widget
        """
        from .qt import QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QDateTimeEdit, QHBoxLayout

        # Format label text
        display_label = f"{label_text}:" + ("*" if required else "")

        # Create the row with consistent label width and field alignment
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.LABEL_SPACING)

        # Fixed-width label column for perfect alignment
        label = QLabel(display_label)
        label.setProperty("formLabel", True)
        label.setFixedWidth(120)  # Fixed width for consistent alignment
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)

        # Create the appropriate widget
        widget = None
        if widget_type == "line_edit":
            widget = QLineEdit()
            widget.setProperty("class", "mus1-text-input")
            if placeholder:
                widget.setPlaceholderText(placeholder)
        elif widget_type == "combo_box":
            widget = QComboBox()
            widget.setProperty("class", "mus1-combo-box")
        elif widget_type == "text_edit":
            widget = QTextEdit()
            widget.setProperty("class", "mus1-notes-edit")
            if placeholder:
                widget.setPlaceholderText(placeholder)
        elif widget_type == "spin_box":
            widget = QSpinBox()
            widget.setProperty("class", "mus1-spin-box")
        elif widget_type == "double_spin_box":
            widget = QDoubleSpinBox()
            widget.setProperty("class", "mus1-double-spin-box")
        elif widget_type == "check_box":
            widget = QCheckBox(label_text)
            widget.setProperty("class", "mus1-check-box")
            # For checkboxes, replace the label with the checkbox
            row.removeWidget(label)
            label.deleteLater()
            row.addWidget(widget)
            if parent_layout:
                parent_layout.addLayout(row)
            return row, widget
        elif widget_type == "date_time_edit":
            widget = QDateTimeEdit()
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd hh:mm:ss")

        if widget:
            row.addWidget(widget, 1)  # Give widget stretch

        if parent_layout:
            parent_layout.addLayout(row)

        return row, widget

    def create_form_field_with_button(self, label_text, widget_type="line_edit", button_text="Browse…", placeholder="", required=False, parent_layout=None):
        """
        Create a form field with an inline button (like file/directory selection).
        Uses fixed-width labels for perfect alignment.

        Args:
            label_text: Text for the label
            widget_type: Type of input widget
            button_text: Text for the button
            placeholder: Placeholder text for input widget
            required: Whether this field is required
            parent_layout: Layout to add the field to

        Returns:
            tuple: (row_layout, widget, button) - The row layout, input widget, and button
        """
        from .qt import QPushButton, QHBoxLayout, QLineEdit, QComboBox, QTextEdit

        # Format label text
        display_label = f"{label_text}:" + ("*" if required else "")

        # Create the row with consistent label width and field alignment
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.LABEL_SPACING)

        # Fixed-width label column for perfect alignment
        label = QLabel(display_label)
        label.setProperty("formLabel", True)
        label.setFixedWidth(120)  # Fixed width for consistent alignment
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)

        # Create the input widget
        widget = None
        if widget_type == "line_edit":
            widget = QLineEdit()
            widget.setProperty("class", "mus1-text-input")
            if placeholder:
                widget.setPlaceholderText(placeholder)
        elif widget_type == "combo_box":
            widget = QComboBox()
            widget.setProperty("class", "mus1-combo-box")
        elif widget_type == "text_edit":
            widget = QTextEdit()
            widget.setProperty("class", "mus1-notes-edit")
            if placeholder:
                widget.setPlaceholderText(placeholder)

        if widget:
            row.addWidget(widget, 1)  # Give widget stretch

        # Add button to the row
        button = QPushButton(button_text)
        button.setProperty("class", "mus1-secondary-button")
        row.addWidget(button)

        if parent_layout:
            parent_layout.addLayout(row)

        return row, widget, button

    def create_form_display_field(self, label_text, display_widget, parent_layout=None):
        """
        Create a form field for display-only content (like computed values).

        Args:
            label_text: Text for the label
            display_widget: The widget to display (usually a QLabel)
            parent_layout: Layout to add the field to

        Returns:
            QHBoxLayout: The row layout
        """
        from .qt import QHBoxLayout, QLabel

        # Create the row with consistent label width and field alignment
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.LABEL_SPACING)

        # Fixed-width label column for perfect alignment
        label = QLabel(f"{label_text}:")
        label.setProperty("formLabel", True)
        label.setFixedWidth(120)  # Fixed width for consistent alignment
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)

        # Add the display widget with stretch
        row.addWidget(display_widget, 1)

        if parent_layout:
            parent_layout.addLayout(row)

        return row

    def create_form_list_section(self, title, list_widget, parent_layout):
        """
        Create a standardized form section with a list widget and optional controls.

        Args:
            title: Title for the section
            list_widget: The QListWidget to include
            parent_layout: Parent layout to add the section to

        Returns:
            tuple: (group_box, layout) - The group box and its layout
        """
        return self.create_form_with_list(title, list_widget, parent_layout)

    def create_form_actions_section(self, title, actions, parent_layout):
        """
        Create a standardized actions section with buttons.

        Args:
            title: Title for the section (can be empty string)
            actions: List of button widgets or (text, style_class) tuples
            parent_layout: Parent layout to add the section to

        Returns:
            QHBoxLayout: The actions row layout
        """
        from .qt import QPushButton

        # Create buttons from tuples if needed
        buttons = []
        for action in actions:
            if isinstance(action, tuple):
                text, style_class = action
                button = QPushButton(text)
                button.setProperty("class", style_class)
                buttons.append(button)
            else:
                buttons.append(action)

        return self.create_button_row_centered(buttons, parent_layout)