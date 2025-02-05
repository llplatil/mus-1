"""Test configuration for MUS1"""

import pytest
from pathlib import Path

@pytest.fixture
def test_data_dir():
    """Get test data directory"""
    return Path(__file__).parent / "test_data"

@pytest.fixture
def tmp_project_dir(tmp_path):
    """Get temporary project directory"""
    return tmp_path

@pytest.fixture
def headless_app(tmp_project_dir):
    """Provide headless app instance"""
    app = HeadlessApp(project_path=tmp_project_dir)
    return app

@pytest.fixture
def managers(headless_app):
    """Provide initialized core managers"""
    return headless_app.get_managers()

@pytest.fixture
def test_dir():
    """Get test directory path"""
    return Path(__file__).parent

@pytest.fixture
def project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent

@pytest.fixture(autouse=True)
def clean_logs():
    """Clean log files before each test"""
    log_file = Path("mus1.log")
    if log_file.exists():
        log_file.unlink()
    yield 