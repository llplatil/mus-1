"""Methods Explorer widget for parameter testing"""

from .base.base_widget import BaseWidget
from PyQt5.QtWidgets import QListWidget, QPushButton
from typing import List

class MethodsExplorer(BaseWidget):
    def __init__(self, state_manager, project_manager, data_manager):
        super().__init__(state_manager, project_manager, data_manager)
        
    def setup_ui(self):
        """Initialize methods explorer UI"""
        super().setup_ui()
        
        # Body parts management
        self.bodyparts_list = QListWidget()
        self.bodyparts_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        # Object management
        self.object_list = QListWidget()
        self.add_object_btn = QPushButton("Add Object")
        self.remove_object_btn = QPushButton("Remove Selected")
        
        # Connect signals
        self.state_manager.body_parts_updated.connect(self._update_bodyparts)
        self.state_manager.tracked_objects_updated.connect(self._update_objects)
        
    def _update_bodyparts(self, parts: List[str]):
        """Refresh available body parts"""
        self.bodyparts_list.clear()
        self.bodyparts_list.addItems(parts)
        
        # Preserve selections
        current_active = self.state_manager.get_settings().get('active_body_parts', [])
        for i in range(self.bodyparts_list.count()):
            item = self.bodyparts_list.item(i)
            item.setSelected(item.text() in current_active)

    def _update_objects(self, objects: List[str]):
        """Refresh tracked objects"""
        self.object_list.clear()
        self.object_list.addItems(objects)
        
    def get_selected_bodyparts(self) -> List[str]:
        """Get user-selected body parts"""
        return [item.text() for item in self.bodyparts_list.selectedItems()] 