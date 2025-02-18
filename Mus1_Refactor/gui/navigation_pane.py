from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup
from PySide6.QtCore import Signal

class NavigationPane(QWidget):
    """
    A navigation pane with stacked buttons for switching between views.
    """
    button_clicked = Signal(int)  # Signal emitted when a button is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)  # Only one button can be checked at a time
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)  # No space between buttons
        self.layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        self._button_counter = 0 # add an internal counter
        self.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: #f0f0f0; /* Light gray */
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #ccc; /* Light gray border */
                font-size: 14px;
            }
            QPushButton:checked {
                background-color: #d0d0d0; /* Slightly darker gray */
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)

    def add_button(self, text: str) -> QPushButton:
        """
        Adds a button to the navigation pane.

        Args:
            text: The text to display on the button.

        Returns:
            The newly created QPushButton.
        """
        button = QPushButton(text, self)
        button.setCheckable(True)  # Make the button checkable
        self.button_group.addButton(button, self._button_counter)  # Add to button group with an ID
        self.layout.addWidget(button)
        self._button_counter += 1
        return button
    
    def set_button_checked(self, index: int):
        button = self.button_group.button(index)
        if button:
            button.setChecked(True)

    def connect_button_group(self):
        """
        This method should be called after all buttons are added.  It connects
        the buttonClicked signal of the button group to a slot that emits
        the button_clicked signal of this NavigationPane.  This simplifies
        connections for users of this class.
        """
        self.button_group.idClicked.connect(self.button_clicked.emit) 