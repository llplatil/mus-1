from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QStackedWidget, QLabel, QGroupBox
from PySide6.QtCore import Qt
from .navigation_pane import NavigationPane
import logging

logger = logging.getLogger(__name__)

class BaseView(QWidget):
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
    SECTION_SPACING = 15      # Spacing between major sections
    CONTROL_SPACING = 10      # Spacing between controls within a section
    LABEL_SPACING = 5         # Spacing between labels and their controls
    FORM_MARGIN = 10          # Margin inside form groups
    LABEL_MIN_WIDTH = 65      # Minimum width for form labels
    
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
        self.splitter = QSplitter(Qt.Horizontal)
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
        self.content_layout.setContentsMargins(15, 15, 15, 15)
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
        row.setAlignment(Qt.AlignVCenter)
        if parent_layout: # Add the layout back here
            parent_layout.addLayout(row)
        return row

    def create_form_label(self, text, parent=None):
        """Create a standard label with proper styling for forms.
        
        Args:
            text (str): The label text
            parent (QWidget, optional): Parent widget. Defaults to None.
            
        Returns:
            QLabel: The styled label
        """
        label = QLabel(text, parent)
        label.setProperty("formLabel", True)
        label.setMinimumWidth(65)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
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