"""Test configuration and fixtures"""

import pytest
from mus1.core import StateManager

@pytest.fixture
def state_manager():
    """Provide clean StateManager instance"""
    return StateManager() 