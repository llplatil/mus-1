from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication
from pathlib import Path
import os
import re
import logging

logger = logging.getLogger("mus1.core.theme_manager")

class ThemeManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        # Color cache to reuse computed colors
        self.color_cache = {}

    def get_effective_theme(self):
        """Determine the effective theme based on the state_manager's theme preference."""
        theme_pref = self.state_manager.get_theme_preference()
        if not theme_pref:  # default to dark if no preference set
            theme_pref = "dark"
        if theme_pref == "os":
            app = QApplication.instance()
            palette = app.palette()
            window_color = palette.color(QPalette.Window)
            return "dark" if window_color.lightness() < 128 else "light"
        return theme_pref

    def apply_theme(self, app):
        """Apply the effective theme to the application, including plugin styling."""
        effective_theme = self.get_effective_theme()
        logger.info(f"Applying theme: {effective_theme}")

        # Set up the palette based on effective theme
        palette = QPalette()
        if effective_theme == "dark":
            palette.setColor(QPalette.Window, QColor("#121212"))
            palette.setColor(QPalette.WindowText, QColor("white"))
            palette.setColor(QPalette.Base, QColor("#1E1E1E"))
            palette.setColor(QPalette.Button, QColor("#1E1E1E"))
            palette.setColor(QPalette.ButtonText, QColor("white"))
            palette.setColor(QPalette.Highlight, QColor("#BB86FC"))
            palette.setColor(QPalette.HighlightedText, QColor("black"))
        else:
            palette = app.style().standardPalette()
        app.setPalette(palette)

        # Instead of trying to process the complex CSS file, just apply our known-compatible stylesheet directly
        stylesheet = self._generate_compatible_stylesheet(effective_theme)
        logger.info(f"Generated compatible stylesheet: {len(stylesheet)} characters")
        
        # For debugging - write the processed stylesheet to a file
        debug_path = Path(os.path.join(os.path.dirname(__file__), "..", "themes", "debug_processed.css"))
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(stylesheet)
        logger.info(f"Wrote debug CSS to: {debug_path}")

        # Apply the stylesheet
        try:
            app.setStyleSheet(stylesheet)
            logger.info("Successfully applied compatible stylesheet")
        except Exception as style_error:
            logger.error(f"Qt could not parse stylesheet: {str(style_error)}")
            self._apply_minimal_stylesheet(app, effective_theme)
            logger.info("Applied minimal stylesheet instead")

        return effective_theme

    def _generate_compatible_stylesheet(self, theme):
        """Generate a Qt-compatible stylesheet based on the theme."""
        if theme == "dark":
            # Dark theme colors
            bg_color = "#121212"
            text_color = "#FFFFFF"
            border_color = "#555555"
            input_bg = "#2a2a2a"
            input_text = "#e0e0e0"
            button_bg = "#BB86FC"
            button_text = "#121212"
            button_hover_bg = "#CBB6FC"
            nav_bg = "#2a2a2a"
            nav_text = "#e0e0e0"
            nav_selected_bg = "#BB86FC"
            nav_selected_text = "#121212"
            header_bg = "#3A3A3A"
            header_text = "#E0E0E0"
            content_bg = "#1E1E1E"
            content_text = "#E0E0E0"
            selection_bg = "#3a5f8c"
            selection_text = "#FFFFFF"
            scrollbar_bg = "#333333"
            scrollbar_handle = "#555555"
        else:
            # Light theme colors
            bg_color = "#f0f0f0"
            text_color = "#000000"
            border_color = "#CCCCCC"
            input_bg = "#FFFFFF"
            input_text = "#333333"
            button_bg = "#4A90E2"
            button_text = "#FFFFFF"
            button_hover_bg = "#5AA0F2"
            nav_bg = "#E0E0E0"
            nav_text = "#333333"
            nav_selected_bg = "#4A90E2"
            nav_selected_text = "#FFFFFF"
            header_bg = "#E0E0E0"
            header_text = "#333333"
            content_bg = "#FFFFFF"
            content_text = "#333333"
            selection_bg = "#ADD8E6"
            selection_text = "#000000"
            scrollbar_bg = "#D9D9D9"
            scrollbar_handle = "#BBBBBB"

        # Build the compatible stylesheet
        return f"""
        /* Qt-compatible {theme.capitalize()} Theme */
        QWidget {{
            background-color: {bg_color};
            color: {text_color};
            font-family: "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 12px;
        }}
        
        /* === MAIN WINDOW === */
        .mus1-main-window {{
            min-width: 800px;
            min-height: 600px;
            background-color: {bg_color};
            color: {text_color};
        }}

        /* === BUTTON STYLES === */
        QPushButton, .mus1-primary-button {{
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            background-color: {button_bg};
            color: {button_text};
            margin-top: 10px;
        }}
        
        QPushButton:hover, .mus1-primary-button:hover {{
            background-color: {button_hover_bg};
        }}
        
        QPushButton:pressed, .mus1-primary-button:pressed {{
            background-color: {button_bg};
        }}
        
        .mus1-secondary-button {{
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 8px 16px;
            background-color: {input_bg};
            color: {input_text};
        }}
        
        .mus1-secondary-button:hover {{
            background-color: {bg_color};
        }}
        
        /* === INPUT AND FORM ELEMENTS === */
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, .mus1-text-input, .mus1-combo-box {{
            border-radius: 4px;
            padding: 6px;
            border: 1px solid {border_color};
            background-color: {input_bg};
            color: {input_text};
        }}
        
        .mus1-input-group {{
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 10px;
            margin-bottom: 10px;
            background-color: {content_bg};
            color: {text_color};
        }}
        
        QLineEdit::selection, QTextEdit::selection, QPlainTextEdit::selection {{
            background-color: {selection_bg};
            color: {selection_text};
        }}
        
        .mus1-input-label {{
            color: {text_color};
            font-weight: normal;
            background-color: rgba(0,0,0,0);
            padding: 2px 0;
        }}
        
        .mus1-combo-box {{
            margin-bottom: 10px;
        }}
        
        /* === NOTES WIDGET === */
        .mus1-notes-edit {{
            border-radius: 4px;
            padding: 6px;
            border: 1px solid {border_color};
            background-color: {input_bg};
            color: {input_text};
        }}
        
        /* === LIST WIDGET STYLING === */
        QListWidget, .mus1-list-widget {{
            border: 1px solid {border_color};
            border-radius: 4px;
            background-color: {input_bg};
            color: {input_text};
            padding: 2px;
            margin-bottom: 8px;
            min-height: 100px;
        }}
        
        QListWidget::item, .mus1-list-widget::item {{
            padding: 4px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        }}
        
        QListWidget::item:selected, .mus1-list-widget::item:selected {{
            background-color: {selection_bg};
            color: {selection_text};
        }}
        
        QListWidget::item:hover, .mus1-list-widget::item:hover {{
            background-color: rgba(128, 128, 128, 0.1);
        }}
        
        /* === TABLE VIEWS === */
        QTableView, .mus1-table-view {{
            border: 1px solid {border_color};
            background-color: {input_bg};
            color: {input_text};
        }}
        
        QTableView QHeaderView::section, .mus1-table-view QHeaderView::section {{
            background-color: {header_bg};
            color: {header_text};
            padding: 8px;
            font-weight: bold;
        }}
        
        QTableView::item, .mus1-table-view::item {{
            padding: 4px;
        }}
        
        QTableView::item:selected, .mus1-table-view::item:selected {{
            background-color: {selection_bg};
            color: {selection_text};
        }}
        
        /* === NAVIGATION ELEMENTS === */
        .mus1-nav-pane {{
            background-color: {nav_bg};
            border-right: 1px solid {border_color};
        }}
        
        .mus1-nav-list-container {{
            padding: 0px;
            background-color: rgba(0,0,0,0);
            margin: 0px;
        }}
        
        .mus1-nav-button {{
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            margin: 4px;
            background-color: {nav_bg};
            color: {nav_text};
            text-align: left;
        }}
        
        .mus1-nav-button:hover {{
            background-color: rgba(128, 128, 128, 0.1);
        }}
        
        .mus1-nav-button:checked {{
            background-color: {nav_selected_bg};
            color: {nav_selected_text};
        }}
        
        /* === LOG DISPLAY === */
        .mus1-log-display {{
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 6px;
            background-color: {input_bg};
            color: {input_text};
            margin-top: 10px;
            font-family: Consolas, monospace;
            font-size: 11px;
        }}
        
        .mus1-log-container {{
            background-color: {input_bg};
            color: {input_text};
        }}
        
        .mus1-log-label {{
            color: {text_color};
            font-weight: bold;
            background-color: {header_bg};
            padding: 4px 8px;
            border-radius: 2px 2px 0 0;
            font-size: 11px;
            font-family: Consolas, monospace;
        }}
        
        /* === PANELS AND CONTAINERS === */
        .plugin-panel {{
            border: 1px solid {border_color};
            border-radius: 6px;
            background-color: {content_bg};
            color: {content_text};
            padding: 10px;
            margin: 5px;
        }}
        
        QScrollArea {{
            border: none;
            background-color: {bg_color};
        }}
        
        QScrollArea > QWidget > QWidget {{
            background-color: {bg_color};
        }}
        
        QScrollBar:vertical {{
            background-color: {scrollbar_bg};
            width: 12px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {scrollbar_handle};
            min-height: 20px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background-color: {button_bg};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            background-color: rgba(0,0,0,0);
        }}
        
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background-color: rgba(0,0,0,0);
        }}
        
        QSplitter::handle {{
            background-color: {border_color};
            width: 1px;
        }}
        
        /* === CONTENT AREAS === */
        .mus1-content-area {{
            background-color: {content_bg};
            color: {content_text};
            border-radius: 6px;
            padding: 10px;
        }}
        
        .mus1-page {{
            background-color: {content_bg};
            color: {content_text};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 15px;
            margin: 5px;
        }}
        
        /* === PROJECT ELEMENTS === */
        .mus1-project-selector {{
            background-color: {content_bg};
            color: {content_text};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 10px;
            margin-bottom: 15px;
        }}
        
        .mus1-section-label {{
            color: {text_color};
            font-weight: bold;
            font-size: 14px;
            margin-top: 15px;
            margin-bottom: 10px;
            padding-bottom: 5px;
            border-bottom: 1px solid {border_color};
        }}
        
        /* === PLUGIN STYLING === */
        .plugin-field {{
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 8px;
            margin: 4px 0;
        }}
        
        .plugin-field-required {{
            background-color: rgba(255, 0, 0, 0.1);
        }}
        
        .plugin-field-optional {{
            background-color: rgba(0, 0, 255, 0.1);
        }}
        
        .plugin-stage-preprocessing {{
            border-left: 3px solid blue;
        }}
        
        .plugin-stage-analysis {{
            border-left: 3px solid green;
        }}
        
        .plugin-stage-results {{
            border-left: 3px solid orange;
        }}
        
        .plugin-stage-unknown {{
            border-left: 3px solid gray;
        }}
        
        /* Add any additional styling needed for plugins */
        """

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

    def change_theme(self, theme_choice):
        """Change the theme; updates the state_manager and reapplies the theme.
        Returns the effective theme after change.
        """
        logger.info(f"Changing theme to: {theme_choice}")
        self.state_manager.set_theme_preference(theme_choice)
        app = QApplication.instance()
        effective_theme = self.apply_theme(app)
        return effective_theme
