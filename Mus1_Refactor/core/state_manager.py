import logging
from typing import Optional
from .metadata import ProjectState, MouseMetadata, ExperimentMetadata

logger = logging.getLogger("mus1.core.state_manager")

class StateManager:
    """
    Manages the in-memory ProjectState, providing methods for CRUD operations.
    """

    def __init__(self, project_state: Optional[ProjectState] = None):
        self._project_state = project_state or ProjectState()

    @property
    def project_state(self) -> ProjectState:
        return self._project_state

