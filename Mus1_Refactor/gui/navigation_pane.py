from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup, QListWidget, QListWidgetItem, QSizePolicy, QTextEdit, QLabel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QTextCharFormat, QFont
from datetime import datetime

class NavigationPane(QWidget):
    """
    A navigation pane using a QListWidget for selection.
    """
    button_clicked = Signal(int)  # Signal emitted when an item is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)  # No space between items
        self.layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #9acced; /* blue gray */
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #d5e2eb; /* Light gray border */
                color: black;
                font-size: 14px;
            }
            QListWidget::item:selected {
                background-color: #6b889c; /* Darker on selection */
                font-weight: bold;
            }
            QListWidget::item:hover {
                background-color: #7ba1b8;
            }

        """)
        self.layout.addWidget(self.list_widget)
        self.list_widget.currentRowChanged.connect(self.button_clicked)
        self._item_counter = 0

        # Corrected alignment and size policy
        self.layout.setAlignment(Qt.AlignTop)  # Keep it aligned to the top
        self.list_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)  # Use Maximum
        self.list_widget.setMaximumWidth(180)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff) #Added

        # Add a spacer to push everything up
        self.layout.addStretch()
        
        # Remove log section header and update log display area
        self.log_display = QTextEdit(self)
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumHeight(120)  # Make it more compact
        self.log_display.setMinimumHeight(80)   # Ensure it's always visible
        self.log_display.setStyleSheet("""
            QTextEdit {
                border: none;
                background-color: transparent;  /* transparent background */
                color: #cccccc;             /* default text color: light gray */
                font-size: 11px;
                font-weight: normal;
                padding: 4px;
            }
        """)
        self.layout.addWidget(self.log_display)
        
        # Update log message formats for different levels - using grayscale colors
        self.log_formats = {
            'info': self._create_format(QColor('#d3d3d3')),      # Light gray
            'success': self._create_format(QColor('#a9a9a9')),   # Medium gray
            'warning': self._create_format(QColor('#808080')),   # Gray
            'error': self._create_format(QColor('#505050'))      # Dark gray
        }
        
        # Maximum number of log entries to keep
        self.max_log_entries = 3
        self.log_entries = []

    def _create_format(self, color):
        """Create a text format with the specified color"""
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        # Create a lighter font (normal weight)
        font = QFont()
        font.setWeight(QFont.Normal)
        fmt.setFont(font)
        return fmt

    def add_button(self, text: str) -> QListWidgetItem:
        """
        Adds an item to the navigation pane.

        Args:
            text: The text to display on the item.

        Returns:
            The newly created QListWidgetItem.
        """
        item = QListWidgetItem(text, self.list_widget)
        self._item_counter += 1
        self.adjust_height()  # Call adjust_height after adding an item
        return item

    def set_button_checked(self, index: int):
        """Sets the currently selected item."""
        self.list_widget.setCurrentRow(index)

    def connect_button_group(self):
        """
        Not needed with QListWidget.
        """
        pass

    def adjust_height(self):
        """Adjusts the height of the list widget based on content."""
        size = self.list_widget.sizeHintForRow(0) * self.list_widget.count()
        margins = self.list_widget.contentsMargins()
        size += margins.top() + margins.bottom()
        self.list_widget.setFixedHeight(size) 
        
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
        formatted_message = message
        if source:
            formatted_message = f"{message} [{source}]"
            
        # Use existing add_log_message method to display the log
        self.add_log_message(formatted_message, level) 