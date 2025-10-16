from .qt import QPalette, QColor, QApplication
QT_BACKEND = "PyQt6"

# PyQt6 uses enum values
PALETTE_WINDOW = QPalette.ColorRole.Window
PALETTE_WINDOW_TEXT = QPalette.ColorRole.WindowText
PALETTE_BASE = QPalette.ColorRole.Base
PALETTE_ALTERNATE_BASE = QPalette.ColorRole.AlternateBase
PALETTE_TOOLTIP_BASE = QPalette.ColorRole.ToolTipBase
PALETTE_TOOLTIP_TEXT = QPalette.ColorRole.ToolTipText
PALETTE_TEXT = QPalette.ColorRole.Text
PALETTE_BUTTON = QPalette.ColorRole.Button
PALETTE_BUTTON_TEXT = QPalette.ColorRole.ButtonText
PALETTE_BRIGHT_TEXT = QPalette.ColorRole.BrightText
PALETTE_HIGHLIGHT = QPalette.ColorRole.Highlight
PALETTE_HIGHLIGHTED_TEXT = QPalette.ColorRole.HighlightedText
from pathlib import Path
import os
import logging
import re
from typing import Optional
from ..core.config_manager import ConfigManager

logger = logging.getLogger("mus1.gui.theme_manager")

class ThemeManager:
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.base_dir = Path(os.path.dirname(__file__)).parent
        self.base_qss_path = self.base_dir / "themes" / "mus1.qss"

        # Cache for processed stylesheets
        self.processed_stylesheets = {}

        # Define theme color palettes
        self.theme_colors = {
            "dark": {
                # Base colors
                "$BACKGROUND_COLOR": "#121212",
                "$TEXT_COLOR": "#FFFFFF",
                "$BORDER_COLOR": "#555555",

                # Input elements
                "$INPUT_BG": "#2a2a2a",
                "$INPUT_TEXT": "#e0e0e0",

                # Buttons
                "$PRIMARY_BUTTON_BG": "#BB86FC",
                "$PRIMARY_BUTTON_TEXT": "#121212",
                "$PRIMARY_BUTTON_HOVER": "#CBB6FC",
                "$PRIMARY_BUTTON_PRESSED": "#9966CC",

                "$SECONDARY_BUTTON_BG": "#333333",
                "$SECONDARY_BUTTON_TEXT": "#E0E0E0",
                "$SECONDARY_BUTTON_HOVER": "#444444",

                # Navigation
                "$NAV_BG": "#2A2A2A",
                "$NAV_BUTTON_BG": "#3A3A3A",
                "$NAV_BUTTON_TEXT": "#E0E0E0",
                "$NAV_BUTTON_HOVER": "#444444",
                "$NAV_BUTTON_SELECTED": "#BB86FC",

                # Content
                "$CONTENT_BG": "#1E1E1E",
                "$CONTENT_TEXT": "#E0E0E0",

                # Selection
                "$SELECTION_BG": "#BB86FC",
                "$SELECTION_TEXT": "#121212",

                # Lists and tables
                "$HEADER_BG": "#333333",
                "$HEADER_TEXT": "#E0E0E0",
                "$HOVER_BG": "#3A3A3A",
                "$BORDER_LIGHT": "#444444",

                # Scrollbar
                "$SCROLLBAR_BG": "#1A1A1A",
                "$SCROLLBAR_HANDLE": "#555555",
                "$SCROLLBAR_HANDLE_HOVER": "#777777",

                # Widget containers
                "$WIDGET_BOX_BG": "#2A2A2A",

                # Logs
                "$LOG_BG": "#1A1A1A",
                "$LOG_TEXT": "#E0E0E0",
                "$LOG_LABEL_COLOR": "#BB86FC",

                # Plugin/Field colors (Simplified)
                "$PLUGIN_REQUIRED_COLOR": "#ff8787", # Red for required fields
                "$PLUGIN_OPTIONAL_COLOR": "#4dabf7", # Blue for optional (if needed)
                "$PLUGIN_COMPONENT_ACCENT": "#BB86FC", # Accent border (if needed)

                # Experiment Stage Colors
                "$STAGE_PLANNED_COLOR": "#888888",  # Grey
                "$STAGE_RECORDED_COLOR": "#4dabf7", # Blue
                "$STAGE_LABELED_COLOR": "#fcc419",  # Yellow
                "$STAGE_TRACKED_COLOR": "#74b816",  # Green
                "$STAGE_INTERPRETED_COLOR": "#e03131", # Red
                "$STAGE_UNKNOWN_COLOR": "#cccccc",   # Light Grey for unknown/default

                # ---> ADD MISSING PLUGIN VARIABLES (Dark Theme) <---
                "$PLUGIN_PREPROCESSING_BG": "#2c3e50", # Dark blue-grey example
                "$PLUGIN_ANALYSIS_BG": "#34495e",      # Slightly lighter blue-grey example
                "$PLUGIN_RESULTS_BG": "#273746",        # Darker blue-grey example
            },
            "light": {
                # Base colors
                "$BACKGROUND_COLOR": "#f0f0f0",
                "$TEXT_COLOR": "#000000",
                "$BORDER_COLOR": "#CCCCCC",

                # Input elements
                "$INPUT_BG": "#FFFFFF",
                "$INPUT_TEXT": "#333333",

                # Buttons
                "$PRIMARY_BUTTON_BG": "#4A90E2",
                "$PRIMARY_BUTTON_TEXT": "#FFFFFF",
                "$PRIMARY_BUTTON_HOVER": "#5AA0F2",
                "$PRIMARY_BUTTON_PRESSED": "#3A80D2",

                "$SECONDARY_BUTTON_BG": "#EEEEEE",
                "$SECONDARY_BUTTON_TEXT": "#333333",
                "$SECONDARY_BUTTON_HOVER": "#DFDFDF",

                # Navigation
                "$NAV_BG": "#E6E6E6",
                "$NAV_BUTTON_BG": "#F0F0F0",
                "$NAV_BUTTON_TEXT": "#333333",
                "$NAV_BUTTON_HOVER": "#E0E0E0",
                "$NAV_BUTTON_SELECTED": "#4A90E2",

                # Content
                "$CONTENT_BG": "#FFFFFF",
                "$CONTENT_TEXT": "#333333",

                # Selection
                "$SELECTION_BG": "#4A90E2",
                "$SELECTION_TEXT": "#FFFFFF",

                # Lists and tables
                "$HEADER_BG": "#E6E6E6",
                "$HEADER_TEXT": "#333333",
                "$HOVER_BG": "#F5F5F5",
                "$BORDER_LIGHT": "#E0E0E0",

                # Scrollbar
                "$SCROLLBAR_BG": "#F0F0F0",
                "$SCROLLBAR_HANDLE": "#CCCCCC",
                "$SCROLLBAR_HANDLE_HOVER": "#AAAAAA",

                # Widget containers
                "$WIDGET_BOX_BG": "#FFFFFF",

                # Logs
                "$LOG_BG": "#F5F5F5",
                "$LOG_TEXT": "#333333",
                "$LOG_LABEL_COLOR": "#4A90E2",

                # Plugin/Field colors (Simplified)
                "$PLUGIN_REQUIRED_COLOR": "#e03131", # Red for required fields
                "$PLUGIN_OPTIONAL_COLOR": "#4A90E2", # Blue for optional (if needed)
                "$PLUGIN_COMPONENT_ACCENT": "#4A90E2", # Accent border (if needed)

                # Experiment Stage Colors
                "$STAGE_PLANNED_COLOR": "#888888",  # Grey
                "$STAGE_RECORDED_COLOR": "#4A90E2", # Blue
                "$STAGE_LABELED_COLOR": "#f59f00",  # Orange/Yellow
                "$STAGE_TRACKED_COLOR": "#40c057",  # Green
                "$STAGE_INTERPRETED_COLOR": "#c92a2a", # Red
                "$STAGE_UNKNOWN_COLOR": "#555555",   # Dark Grey for unknown/default

                # ---> ADD MISSING PLUGIN VARIABLES (Light Theme) <---
                "$PLUGIN_PREPROCESSING_BG": "#ecf0f1", # Light grey example
                "$PLUGIN_ANALYSIS_BG": "#e0e6e8",      # Slightly darker grey example
                "$PLUGIN_RESULTS_BG": "#d3dade",        # Medium grey example
            }
        }

    def get_effective_theme(self):
        """Determine the effective theme based on the config_manager's theme preference."""
        theme_pref = self.config_manager.get("ui.theme", "dark")
        if not theme_pref:  # default to dark if no preference set
            theme_pref = "dark"
        if theme_pref == "os":
            app = QApplication.instance()
            palette = app.palette()
            window_color = palette.color(PALETTE_WINDOW)
            return "dark" if window_color.lightness() < 128 else "light"
        return theme_pref

    def apply_theme(self, app):
        """Apply the effective theme to the application."""
        effective_theme = self.get_effective_theme()
        logger.info(f"Applying theme: {effective_theme}")

        # Get the color dictionary for the effective theme
        colors = self.theme_colors.get(effective_theme, self.theme_colors["dark"]) # Fallback to dark

        # Set up the palette based on effective theme using theme variables
        palette = QPalette()
        try:
            # Use variables from the 'colors' dictionary - THESE ARE HEX CODES
            palette.setColor(PALETTE_WINDOW, QColor(colors.get("$BACKGROUND_COLOR", "#FFFFFF")))
            palette.setColor(PALETTE_WINDOW_TEXT, QColor(colors.get("$TEXT_COLOR", "#000000")))
            palette.setColor(PALETTE_BASE, QColor(colors.get("$CONTENT_BG", "#FFFFFF")))
            palette.setColor(PALETTE_ALTERNATE_BASE, QColor(colors.get("$INPUT_BG", "#F0F0F0")))
            palette.setColor(PALETTE_TOOLTIP_BASE, QColor(colors.get("$WIDGET_BOX_BG", "#FFFFE0")))
            palette.setColor(PALETTE_TOOLTIP_TEXT, QColor(colors.get("$TEXT_COLOR", "#000000")))
            palette.setColor(PALETTE_TEXT, QColor(colors.get("$TEXT_COLOR", "#000000")))
            palette.setColor(PALETTE_BUTTON, QColor(colors.get("$SECONDARY_BUTTON_BG", "#F0F0F0")))
            palette.setColor(PALETTE_BUTTON_TEXT, QColor(colors.get("$SECONDARY_BUTTON_TEXT", "#000000")))
            palette.setColor(PALETTE_BRIGHT_TEXT, QColor(colors.get("$PRIMARY_BUTTON_TEXT", "#FFFFFF")))
            palette.setColor(PALETTE_HIGHLIGHT, QColor(colors.get("$SELECTION_BG", "#0078D7")))
            palette.setColor(PALETTE_HIGHLIGHTED_TEXT, QColor(colors.get("$SELECTION_TEXT", "#FFFFFF")))

            # Handle disabled state colors (can derive or use defaults)
            if QT_BACKEND == "PyQt6":
                # PyQt6 syntax for disabled colors
                palette.setColor(QPalette.ColorGroup.Disabled, PALETTE_TEXT, QColor(colors.get("$BORDER_COLOR", "#A0A0A0")))
                palette.setColor(QPalette.ColorGroup.Disabled, PALETTE_BUTTON_TEXT, QColor(colors.get("$BORDER_COLOR", "#A0A0A0")))
            else:
                # PySide6 syntax
                palette.setColor(QPalette.Disabled, PALETTE_TEXT, QColor(colors.get("$BORDER_COLOR", "#A0A0A0")))
                palette.setColor(QPalette.Disabled, PALETTE_BUTTON_TEXT, QColor(colors.get("$BORDER_COLOR", "#A0A0A0")))

        except KeyError as e:
             logger.error(f"Missing color variable for QPalette setup: {e}. Using fallback defaults.")
             # Apply very basic defaults if a key is missing
             if effective_theme == "dark":
                 palette.setColor(PALETTE_WINDOW, QColor("#121212"))
                 palette.setColor(PALETTE_WINDOW_TEXT, QColor("#FFFFFF")) # Use hex code instead of "white"
             else:
                 palette = app.style().standardPalette() # Fallback to system style standard palette

        app.setPalette(palette)

        # Initialize processed_stylesheet to None BEFORE checking cache or processing
        processed_stylesheet = None

        # Check cache first
        if effective_theme in self.processed_stylesheets:
            processed_stylesheet = self.processed_stylesheets[effective_theme]
            logger.debug(f"Using cached stylesheet for theme: {effective_theme}")
        else:
            # Not in cache, try processing
            try:
                if not self.base_qss_path.exists():
                    logger.error(f"Base QSS file not found: {self.base_qss_path}")
                    self._apply_minimal_stylesheet(app, effective_theme)
                    return effective_theme # Return early after applying minimal

                with open(self.base_qss_path, "r", encoding="utf-8") as f:
                    stylesheet = f.read()

                # Substitute theme variables
                # logger.debug(f"Starting variable substitution for theme: {effective_theme}") # Commented out
                for var, value in colors.items():
                    # Original pattern: pattern = r'\b' + re.escape(var) + r'\b'
                    # Revised pattern: Remove the leading \b because $ is not a word character
                    pattern = re.escape(var) + r'\b'
                    # logger.debug(f"Substituting pattern '{pattern}' with '{value}'") # Commented out
                    stylesheet = re.sub(pattern, value, stylesheet)

                # Check if any variables remain
                remaining_vars = re.findall(r'\$[\w_]+', stylesheet)
                if remaining_vars:
                    logger.warning(f"Unsubstituted variables remaining in stylesheet: {set(remaining_vars)}")

                # Rewrite relative asset URLs (e.g., down_arrow.svg) to absolute paths in themes dir
                themes_dir = self.base_dir / "themes"
                def _rewrite_url(match):
                    raw = match.group(1)
                    # Keep absolute and special schemes as-is
                    if raw.startswith(("qrc:", "file:", "/", "http:", "https:")):
                        return f'url("{raw}")'
                    # Otherwise, treat as an asset in themes dir
                    abs_path = (themes_dir / raw).resolve()
                    return f'url("{abs_path}")'
                stylesheet = re.sub(r'url\("([^")]+)"\)', _rewrite_url, stylesheet)

                # logger.info(f"Processed Stylesheet content sample:\n{stylesheet[:1000]}...") # Commented out

                self.processed_stylesheets[effective_theme] = stylesheet
                processed_stylesheet = stylesheet # Assign the newly processed stylesheet

            except Exception as e:
                logger.error(f"Error processing stylesheet: {e}", exc_info=True)
                self._apply_minimal_stylesheet(app, effective_theme)
                # Return early after applying minimal in case of error
                return effective_theme

        # Apply the processed stylesheet (now processed_stylesheet is guaranteed to be assigned or None)
        if processed_stylesheet:
            logger.info("Attempting to apply the processed stylesheet...")
            try:
                app.setStyleSheet(processed_stylesheet)
                logger.info("Stylesheet applied via app.setStyleSheet.")
            except Exception as apply_error: # Catch potential errors during Qt's application
                 logger.error(f"Qt failed to apply stylesheet: {apply_error}", exc_info=True)
                 logger.warning("Applying minimal fallback stylesheet due to Qt application error.")
                 self._apply_minimal_stylesheet(app, effective_theme)
        else:
             # This case means cache miss AND processing failed AND error handling didn't return early
             logger.error("No processed stylesheet was available and minimal wasn't applied in error handler. Applying minimal now.")
             self._apply_minimal_stylesheet(app, effective_theme)

        return effective_theme

    def _apply_minimal_stylesheet(self, app, theme):
        """Apply an absolutely minimal stylesheet when all else fails."""
        if theme == "dark":
            minimal_css = """
            QWidget { background-color: #121212; color: white; }
            QPushButton { background-color: #BB86FC; color: black; border-radius: 4px; padding: 6px; }
            QLineEdit, QTextEdit { background-color: #2a2a2a; color: white; border: 1px solid #555; }
            """
        else:
            minimal_css = """
            QWidget { background-color: white; color: black; }
            QPushButton { background-color: #4A90E2; color: white; border-radius: 4px; padding: 6px; }
            QLineEdit, QTextEdit { background-color: white; color: black; border: 1px solid #ccc; }
            """

        app.setStyleSheet(minimal_css)
        logger.info("Applied minimal fallback stylesheet")

    def change_theme(self, theme_choice):
        """Change the theme; updates the config_manager and reapplies the theme."""
        logger.info(f"Changing theme to: {theme_choice}")
        self.config_manager.set("ui.theme", theme_choice)
        app = QApplication.instance()
        # Force reprocessing of stylesheet by clearing cache for the new theme
        effective_theme_to_apply = self.get_effective_theme()
        if effective_theme_to_apply in self.processed_stylesheets:
             del self.processed_stylesheets[effective_theme_to_apply]

        effective_theme = self.apply_theme(app)
        return effective_theme
