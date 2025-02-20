from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup, QListWidget, QListWidgetItem, QSizePolicy
from PySide6.QtCore import Signal, Qt

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