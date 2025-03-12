from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup, QListWidget, QListWidgetItem, QSizePolicy, QTextEdit, QLabel, QScrollArea, QFrame
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QTextCharFormat, QFont
from datetime import datetime

class NavigationPane(QWidget):
    """
    A standardized navigation pane component for MUS1.
    
    Features:
    - Fixed width (180px)
    - Vertical stacked navigation buttons
    - Log display at bottom
    - Consistent styling
    """
    button_clicked = Signal(int)  # Signal emitted when an item is clicked
    
    # Single source of truth for sizing parameters
    BUTTON_HEIGHT = 32          # Core button height without padding/margin
    BUTTON_SPACING = 2          # Space between buttons
    FIXED_WIDTH = 180           # Fixed width as per UI guidelines
    MIN_LOG_HEIGHT = 100        # Minimum height for log display
    LOG_LABEL_HEIGHT = 20       # Height for log label
    LAYOUT_MARGINS = 10         # Layout margin size
    LAYOUT_SPACING = 6          # Reduced spacing between widgets

    def __init__(self, parent=None, buttons=None):
        super().__init__(parent)
        # Apply class-based styling
        self.setObjectName("navigationPane")
        self.setProperty("class", "mus1-nav-pane")
        
        # Set fixed width for the navigation pane
        self.setFixedWidth(self.FIXED_WIDTH)

        # Main layout with consistent margins
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(self.LAYOUT_MARGINS, self.LAYOUT_MARGINS, 
                                        self.LAYOUT_MARGINS, self.LAYOUT_MARGINS)
        self.layout.setSpacing(self.LAYOUT_SPACING)  # reduced spacing between widgets

        # Create the button container directly (no scroll area)
        self.button_container = QWidget()
        self.button_container.setObjectName("buttonContainer")
        self.button_container.setProperty("class", "mus1-nav-list-container")
        
        # Set up the button container layout
        self.button_container_layout = QVBoxLayout(self.button_container)
        self.button_container_layout.setContentsMargins(0, 0, 0, 0)
        self.button_container_layout.setSpacing(self.BUTTON_SPACING)
        
        # Add the button container with no stretch to keep it at its natural size
        self.layout.addWidget(self.button_container, 0)
        
        # Create a container for the log section to group label and display
        self.log_container = QFrame()
        self.log_container.setFrameShape(QFrame.NoFrame)
        self.log_container.setObjectName("logContainer")
        self.log_container.setProperty("class", "mus1-log-container")
        
        # Container layout with minimal spacing
        log_container_layout = QVBoxLayout(self.log_container)
        log_container_layout.setContentsMargins(0, 0, 0, 0)
        log_container_layout.setSpacing(1)  # Reduced spacing between label and log
        
        # Create log display label inside the container
        self.log_label = QLabel("Log Messages")
        self.log_label.setAlignment(Qt.AlignLeft)
        self.log_label.setObjectName("logLabel")
        self.log_label.setProperty("class", "mus1-log-label")
        log_container_layout.addWidget(self.log_label)

        # Log display widget setup
        self.log_display = QTextEdit()
        self.log_display.setObjectName("logDisplay")
        self.log_display.setProperty("class", "mus1-log-display")
        self.log_display.setReadOnly(True)
        self.log_display.setFrameStyle(0)
        self.log_display.setMinimumHeight(self.MIN_LOG_HEIGHT)
        
        # Setup log display properties
        self.log_display.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.log_display.document().setMaximumBlockCount(100)  # Keep up to 100 log messages
        self.log_display.setLineWrapMode(QTextEdit.NoWrap)
        
        # Add the log display to the container layout
        log_container_layout.addWidget(self.log_display, 1)  # Give it stretch to fill the container
        
        # Add the log container to the main layout with stretch to take all remaining space
        self.layout.addWidget(self.log_container, 1)

        # Log message formats for different levels
        self.log_formats = {
            'info': self._create_format(QColor('#888888')),      # Gray
            'success': self._create_format(QColor('#6FCF97')),   # Green
            'warning': self._create_format(QColor('#F2C94C')),   # Yellow
            'error': self._create_format(QColor('#EB5757'))      # Red
        }
        
        # Store log entries for filtering/persistence
        self.max_log_entries = 100
        self.log_entries = []

        # Add buttons if provided
        self.buttons = []
        if buttons:
            for text in buttons:
                self.add_button(text)

    def _create_format(self, color):
        """Create a text format with the specified color"""
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        font = QFont()
        font.setWeight(QFont.Normal)
        fmt.setFont(font)
        return fmt

    def add_button(self, text: str):
        """Add a button to the navigation pane."""
        button = QPushButton(text)
        button.setObjectName(f"navButton_{len(self.buttons)}")
        button.setProperty("class", "mus1-nav-button")
        button.setCheckable(True)
        index = len(self.buttons)
        button.clicked.connect(lambda _, idx=index: self.button_clicked.emit(idx))
        
        # Set button size policy and fixed height for consistency
        button_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setSizePolicy(button_policy)
        button.setFixedHeight(self.BUTTON_HEIGHT)
        
        # Add to the button container layout
        self.button_container_layout.addWidget(button)
        self.buttons.append(button)
        
        # Recalculate button stack size and log space
        self.update_button_stack_size()
            
        return button

    def clear_buttons(self):
        """Clear all navigation buttons."""
        # Remove all buttons from layout
        for button in self.buttons:
            self.button_container_layout.removeWidget(button)
            button.deleteLater()
        
        self.buttons = []
        
        # Remove any stretches
        self._remove_all_stretches()
        
        # Update button stack size and log space
        self.update_button_stack_size()

    def _remove_all_stretches(self):
        """Remove all stretches from the button container layout."""
        # Find and remove all spacer items
        for i in range(self.button_container_layout.count() - 1, -1, -1):
            item = self.button_container_layout.itemAt(i)
            if item and item.spacerItem():
                self.button_container_layout.removeItem(item)

    def update_button_stack_size(self):
        """Calculate and set the proper size for the button stack based on buttons."""
        if not self.buttons:
            # No buttons, minimal height for container
            self.button_container.setFixedHeight(10)
            return
            
        # Calculate total height needed based on actual button count
        button_count = len(self.buttons)
        
        # Calculate exact height needed:
        # - Each button has fixed BUTTON_HEIGHT
        # - Space between buttons from layout spacing (not needed after last button)
        total_height = (button_count * self.BUTTON_HEIGHT) + (
            (button_count - 1) * self.BUTTON_SPACING)
        
        # Set fixed height to button container
        self.button_container.setFixedHeight(total_height)
        
        # Update layout to give remaining space to log display
        self._update_log_space()
        
    def _update_log_space(self):
        """Allocate remaining space to log display based on button stack size."""
        if not self.isVisible():
            return
            
        # Get current height of the navigation pane
        nav_height = self.height()
        
        # Calculate space needed for the button container
        button_stack_height = self.button_container.height()
        
        # Calculate available space for log display
        available_for_log = (
            nav_height 
            - button_stack_height 
            - self.LOG_LABEL_HEIGHT
            - (self.LAYOUT_MARGINS * 2)  # Top and bottom margins
            - (self.LAYOUT_SPACING * 2)  # Spacing between components
        )
        
        # Ensure log has at least minimum height
        log_height = max(available_for_log, self.MIN_LOG_HEIGHT)
        
        # Set minimum height for log display
        self.log_display.setMinimumHeight(log_height)
        
    def update_layout_sizes(self):
        """Update layout sizes based on the current button count and available space."""
        # Now just calls update_button_stack_size for backward compatibility
        self.update_button_stack_size()

    def set_button_checked(self, index: int):
        """Sets the currently selected button as checked and others unchecked."""
        if not self.buttons:
            return
            
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)

    def connect_button_group(self):
        """Setup button group if explicit control is needed."""
        self.button_group = QButtonGroup(self)
        for i, button in enumerate(self.buttons):
            self.button_group.addButton(button, i)
        self.button_group.buttonClicked[int].connect(self.button_clicked.emit)

    def add_log_message(self, message, level='info'):
        """
        Add a new log message to the log display area.
        
        Args:
            message: The message to log
            level: Log level ('info', 'success', 'warning', 'error')
        """
        # Get current timestamp
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Create the formatted log entry
        log_entry = f"[{timestamp}] {message}"
        
        # Add to our log entries list
        self.log_entries.append((log_entry, level))
        
        # Limit number of entries
        if len(self.log_entries) > self.max_log_entries:
            self.log_entries = self.log_entries[-self.max_log_entries:]
            
        # Update the display
        self._update_log_display()
            
    def _update_log_display(self):
        """Update the log display text with all current entries"""
        self.log_display.clear()
        cursor = self.log_display.textCursor()
        
        for entry, level in self.log_entries:
            cursor.insertText(entry + '\n', self.log_formats.get(level, self.log_formats['info']))
            
        # Scroll to the bottom to show the most recent messages
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())
        
    def clear_log(self):
        """Clear all log messages"""
        self.log_entries = []
        self.log_display.clear()

    def on_log_event(self, message: str, level: str, source: str, timestamp=None):
        """
        Receive log events from the LoggingEventBus.
        
        Args:
            message: The log message
            level: Log level ('info', 'success', 'warning', 'error')
            source: Source component that generated the log
            timestamp: When the log was generated
        """
        # Format message with source if provided
        formatted_message = f"{source}: {message}" if source else message
        
        # Use existing add_log_message method to display the log
        self.add_log_message(formatted_message, level) 

    def resizeEvent(self, event):
        """
        Handle resize events for the navigation pane.
        Maintains fixed width and updates log space.
        """
        super().resizeEvent(event)
        # Ensure pane maintains fixed width during resize
        self.setFixedWidth(self.FIXED_WIDTH)
        
        # Update log space when resized
        self._update_log_space()
        
    def showEvent(self, event):
        """
        Handle show events to ensure proper layout sizing.
        Updates button stack size and log space when shown.
        """
        super().showEvent(event)
        # Update button sizing and log space when shown
        self.update_button_stack_size()

    def add_widget(self, widget, stretch=0):
        """Add a custom widget to the button container."""
        self.button_container_layout.addWidget(widget, stretch)
        
        # Update sizing after adding widget
        self.update_button_stack_size()
    
    def update_theme(self, theme):
        """Update any theme-specific elements when the theme changes."""
        # Set the theme property so that stylesheets can react to it
        self.setProperty("theme", theme)
        # Reapply styling to update appearance
        self.style().unpolish(self)
        self.style().polish(self)
        # Recalculate button stack size when theme changes
        self.update_button_stack_size() 