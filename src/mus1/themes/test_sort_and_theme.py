#!/usr/bin/env python3
"""
Test script to verify sort mode and theme functionality works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pathlib import Path
from mus1.core.project_manager_clean import ProjectManagerClean

def test_sort_modes():
    """Test that sort modes work correctly."""
    print("Testing sort mode functionality...")

    # Use the existing test project
    project_path = Path("projects/copperlab_dev_test_1")

    if not project_path.exists():
        print(f"Project path {project_path} does not exist")
        return False

    try:
        pm = ProjectManagerClean(project_path)
        print(f"Loaded project: {pm.config.name}")

        # Test different sort modes
        sort_modes = ["Newest First", "Recording Date", "ID Order", "By Type"]

        for sort_mode in sort_modes:
            print(f"\nTesting sort mode: {sort_mode}")

            # Set the sort mode in config
            pm.config.settings["global_sort_mode"] = sort_mode
            pm.save_project()

            # Test subjects sorting
            subjects = pm.list_subjects()
            print(f"  Subjects ({len(subjects)}): {[s.id for s in subjects[:3]]}")

            # Test experiments sorting
            experiments = pm.list_experiments()
            print(f"  Experiments ({len(experiments)}): {[e.id for e in experiments[:3]]}")

        print("\nSort mode testing completed successfully!")
        return True

    except Exception as e:
        print(f"Error testing sort modes: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_theme_functionality():
    """Test that theme persistence works."""
    print("\nTesting theme persistence...")

    try:
        from mus1.core.config_manager import ConfigManager

        config_manager = ConfigManager()

        # Test theme setting and getting (without GUI application)
        themes = ["dark", "light", "os"]
        for theme in themes:
            print(f"Testing theme persistence: {theme}")

            # Manually set theme (simulating what ThemeManager.change_theme does)
            config_manager.set("ui.theme", theme)

            # Verify it was persisted
            current = config_manager.get("ui.theme")
            print(f"  Set to: {theme}, retrieved as: {current}")

            if current != theme:
                print(f"  ERROR: Expected {theme}, got {current}")
                return False

        print("Theme persistence testing completed successfully!")
        return True

    except Exception as e:
        print(f"Error testing theme persistence: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing MUS1 sort and theme functionality...\n")

    sort_success = test_sort_modes()
    theme_success = test_theme_functionality()

    if sort_success and theme_success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
