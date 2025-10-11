"""
Defines a simple lifecycle interface for GUI views.

Views can implement these hooks to initialize once services are available
and react to activation/deactivation when their tab becomes active/inactive.
"""

from typing import Any


class ViewLifecycle:
    def on_services_ready(self, services: Any) -> None:
        """Called once when GUI services have been created and injected."""
        pass

    def on_activated(self) -> None:
        """Called when the view's tab becomes the active tab."""
        pass

    def on_deactivated(self) -> None:
        """Called when the view's tab stops being the active tab."""
        pass


