"""Test MUS1 application flows"""

from datetime import datetime
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from ...utils.logging_config import get_class_logger, get_logger, setup_logging
from mus1.core import MouseMetadata
from mus1.__main__ import create_app  # Import app creation from main

def setup_test_logging():
    """Setup logging for tests with clear section markers"""
    logger = get_logger("test")
    logger.info("=" * 80)
    logger.info("TEST SECTION: Starting new test run")
    logger.info("=" * 80)
    return logger

def test_app_flow(test_data_dir, qtbot):
    """Test basic app usage flow"""
    logger = setup_test_logging()
    
    # Step 1: Start app using main's create_app
    logger.info("Step 1: Starting app")
    app, main_window = create_app()
    qtbot.addWidget(main_window)
    
    # Get managers from main window
    state_manager = main_window.state_manager
    project_manager = main_window.project_manager
    
    # Create project through startup dialog
    project_name = f"test_project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    project_path = project_manager.mus1_root / project_name
    
    # Simulate startup dialog
    dialog = main_window.show_startup_dialog()
    qtbot.addWidget(dialog)
    dialog.selected_path = project_path
    dialog.create_new_project()
    
    # Verify project structure created by manager
    assert project_path.exists()
    assert (project_path / "subjects").exists()
    assert (project_path / "experiments").exists()
    assert (project_path / "config").exists()
    
    # Load DLC config
    logger.info("Step 2: Loading DLC config")
    dlc_config_path = test_data_dir / "dlc_examples" / "config.yaml"
    project_manager.load_dlc_config(dlc_config_path)
    assert (project_path / "config" / "dlc_config.yaml").exists()
    
    # Step 3: Add mouse
    logger.info("Step 3: Adding mouse")
    mouse_id = "123F"
    mouse_metadata = MouseMetadata(
        id=mouse_id,
        birth_date=datetime(2023, 1, 1),
        sex='F'
    )
    mouse_id = state_manager.add_mouse(mouse_metadata)
    assert (project_path / "subjects" / mouse_id).exists()
    
    # Step 4: Add experiment
    logger.info("Step 4: Adding experiment")
    exp_id = project_manager.add_experiment(
        mouse_id=mouse_id,
        tracking_csv=test_data_dir / "dlc_examples" / "tracking.csv",
        arena_image=test_data_dir / "dlc_examples" / "arena_images" / "arena_image.png",
        exp_type="NOR",
        phase="Novel",
        date=datetime(2023, 2, 1)
    )
    
    exp_dir = project_path / "experiments" / exp_id
    assert exp_dir.exists()
    assert (exp_dir / "tracking.csv").exists()
    assert (exp_dir / "arena_image.png").exists() 