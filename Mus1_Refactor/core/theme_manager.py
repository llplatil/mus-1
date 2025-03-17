from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication
from pathlib import Path
import os
import logging
import re

logger = logging.getLogger("mus1.core.theme_manager")

class ThemeManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self.base_dir = Path(os.path.dirname(__file__)).parent
        self.base_qss_path = self.base_dir / "themes" / "mus1.qss"
        
        # Cache for processed stylesheets
        self.processed_stylesheets = {}
        
        # New: Registry for plugin-specific style overrides
        self.plugin_style_registry = {}
        self.plugin_styles_dirty = True
        self.combined_stylesheet = {"dark": "", "light": ""}
        
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
                
                # Plugin colors
                "$PLUGIN_PREPROCESSING_BG": "rgba(0, 41, 82, 0.25)",
                "$PLUGIN_ANALYSIS_BG": "rgba(0, 82, 41, 0.25)",
                "$PLUGIN_RESULTS_BG": "rgba(82, 41, 0, 0.25)",
                "$PLUGIN_REQUIRED_COLOR": "#ff8787",
                "$PLUGIN_OPTIONAL_COLOR": "#4dabf7",
                "$PLUGIN_COMPONENT_ACCENT": "#BB86FC"
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
                
                # Plugin colors
                "$PLUGIN_PREPROCESSING_BG": "rgba(240, 248, 255, 0.6)",
                "$PLUGIN_ANALYSIS_BG": "rgba(240, 255, 240, 0.6)",
                "$PLUGIN_RESULTS_BG": "rgba(255, 248, 240, 0.6)",
                "$PLUGIN_REQUIRED_COLOR": "rgba(238, 141, 141, 0.57)",
                "$PLUGIN_OPTIONAL_COLOR": "rgba(116, 193, 252, 0.57)",
                "$PLUGIN_COMPONENT_ACCENT": "#4A90E2"
            }
        }

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
        """Apply the effective theme to the application."""
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
            
            # Set specific colors for text to ensure good contrast
            palette.setColor(QPalette.Text, QColor("white"))
        else:
            palette = app.style().standardPalette()
            
        app.setPalette(palette)
        
        # Process base stylesheet if not cached
        if effective_theme not in self.processed_stylesheets:
            try:
                if not self.base_qss_path.exists():
                    logger.error(f"Base QSS file not found: {self.base_qss_path}")
                    self._apply_minimal_stylesheet(app, effective_theme)
                    return effective_theme
                with open(self.base_qss_path, "r", encoding="utf-8") as f:
                    stylesheet = f.read()
                colors = self.theme_colors.get(effective_theme, self.theme_colors["dark"])
                for var, value in colors.items():
                    stylesheet = stylesheet.replace(var, value)
                # Clean up any erroneous appended suffixes in hex colors (e.g., "#555555_HOVER" -> "#555555")
                stylesheet = re.sub(r"(#[0-9a-fA-F]{6})_[A-Z]+", r"\1", stylesheet)
                self.processed_stylesheets[effective_theme] = stylesheet
            except Exception as e:
                logger.error(f"Error processing stylesheet: {e}")
                self._apply_minimal_stylesheet(app, effective_theme)
                return effective_theme
        
        # Combine base stylesheet with plugin-specific CSS
        if self.plugin_styles_dirty or not self.combined_stylesheet.get(effective_theme):
            base_stylesheet = self.processed_stylesheets[effective_theme]
            plugin_css = self._generate_plugin_css(effective_theme)
            combined_css = base_stylesheet
            if plugin_css:
                combined_css += "\n/* PLUGIN-SPECIFIC STYLES */\n" + plugin_css
            self.combined_stylesheet[effective_theme] = combined_css
            self.plugin_styles_dirty = False
        
        # Apply the combined stylesheet
        app.setStyleSheet(self.combined_stylesheet[effective_theme])
        logger.info("Successfully applied theme stylesheet with plugin overrides")
        
        return effective_theme

    def register_plugin_styles(self, plugin_id, style_overrides):
        """Register plugin-specific style overrides."""
        self.plugin_style_registry[plugin_id] = style_overrides
        self.plugin_styles_dirty = True
        logger.info(f"Registered style overrides for plugin: {plugin_id}")

    def unregister_plugin_styles(self, plugin_id):
        """Unregister plugin-specific style overrides."""
        if plugin_id in self.plugin_style_registry:
            del self.plugin_style_registry[plugin_id]
            self.plugin_styles_dirty = True
            logger.info(f"Unregistered style overrides for plugin: {plugin_id}")

    def refresh_plugin_styles(self):
        """Mark plugin styles as dirty to trigger reprocessing."""
        self.plugin_styles_dirty = True

    def merge_plugin_overrides(self):
        """Merge all registered plugin base overrides, applying first-registered wins if conflicts occur."""
        merged = {}
        for plugin_id, overrides in self.plugin_style_registry.items():
            base_overrides = overrides.get("base", {})
            for var, value in base_overrides.items():
                if var in merged:
                    if merged[var] != value:
                        logger.warning(f"Conflict for {var} from plugin {plugin_id}; using '{merged[var]}' (first registered wins).")
                else:
                    merged[var] = value
        return merged

    def _generate_plugin_css(self, theme):
        """Generate CSS for all registered plugin style overrides."""
        if not self.plugin_style_registry:
            return ""
        plugin_css = ""
        # Generate individual plugin CSS rules
        for plugin_id, overrides in self.plugin_style_registry.items():
            if "base" not in overrides:
                continue
            plugin_css += f"\n/* Plugin: {plugin_id} */\n"
            plugin_css += f'QWidget[pluginId="{plugin_id}"] {{'
            for var, value in overrides["base"].items():
                prop = self._map_variable_to_property(var)
                if prop:
                    if prop == "border-left":
                        plugin_css += f"\n    {prop}: 3px solid {value};"
                    else:
                        plugin_css += f"\n    {prop}: {value};"
            plugin_css += "\n}\n"
        
        # Merge overrides from all plugins for combined UI components
        merged_overrides = self.merge_plugin_overrides()
        if merged_overrides:
            plugin_css += "\n/* Combined Plugin Overrides */\n"
            plugin_css += ".plugin-combined-overrides {"
            for var, value in merged_overrides.items():
                prop = self._map_variable_to_property(var)
                if prop:
                    if prop == "border-left":
                        plugin_css += f"\n    {prop}: 3px solid {value};"
                    else:
                        plugin_css += f"\n    {prop}: {value};"
            plugin_css += "\n}\n"
        return plugin_css

    def _map_variable_to_property(self, variable):
        """Map a placeholder variable to its corresponding CSS property."""
        mapping = {
            "$BACKGROUND_COLOR": "background-color",
            "$TEXT_COLOR": "color",
            "$BORDER_COLOR": "border-color",
            "$PRIMARY_BUTTON_BG": "background-color",
            "$PRIMARY_BUTTON_TEXT": "color",
            "$PRIMARY_BUTTON_HOVER": "background-color",
            "$PRIMARY_BUTTON_PRESSED": "background-color",
            "$SECONDARY_BUTTON_BG": "background-color",
            "$SECONDARY_BUTTON_TEXT": "color",
            "$SECONDARY_BUTTON_HOVER": "background-color",
            "$NAV_BG": "background-color",
            "$NAV_BUTTON_BG": "background-color",
            "$NAV_BUTTON_TEXT": "color",
            "$NAV_BUTTON_HOVER": "background-color",
            "$NAV_BUTTON_SELECTED": "background-color",
            "$CONTENT_BG": "background-color",
            "$CONTENT_TEXT": "color",
            "$INPUT_BG": "background-color",
            "$INPUT_TEXT": "color",
            "$WIDGET_BOX_BG": "background-color",
            "$SELECTION_BG": "background-color",
            "$SELECTION_TEXT": "color",
            "$BORDER_LIGHT": "border-color",
            "$SCROLLBAR_BG": "background-color",
            "$SCROLLBAR_HANDLE": "background-color",
            "$SCROLLBAR_HANDLE_HOVER": "background-color",
            "$HEADER_BG": "background-color",
            "$HEADER_TEXT": "color",
            "$HOVER_BG": "background-color",
            "$PLUGIN_PREPROCESSING_BG": "background-color",
            "$PLUGIN_ANALYSIS_BG": "background-color",
            "$PLUGIN_RESULTS_BG": "background-color",
            "$PLUGIN_REQUIRED_COLOR": "border-left",
            "$PLUGIN_OPTIONAL_COLOR": "border-left",
            "$PLUGIN_COMPONENT_ACCENT": "border-left"
        }
        return mapping.get(variable)

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
        """Change the theme; updates the state_manager and reapplies the theme."""
        logger.info(f"Changing theme to: {theme_choice}")
        self.state_manager.set_theme_preference(theme_choice)
        app = QApplication.instance()
        effective_theme = self.apply_theme(app)
        return effective_theme
        
    def collect_plugin_styles_from_manager(self, plugin_manager):
        """
        Collect and register styles from all plugins in the plugin manager.
        
        Args:
            plugin_manager: The application's PluginManager instance
        """
        for plugin in plugin_manager.get_all_plugins():
            try:
                plugin_id = plugin.plugin_self_metadata().name
                styling_prefs = plugin.get_styling_preferences()
                
                # Convert plugin preferences to our style format
                style_data = {
                    "dark": {
                        "base": {},
                        "stages": {},
                        "importance": {}
                    },
                    "light": {
                        "base": {},
                        "stages": {},
                        "importance": {}
                    }
                }
                
                # Process plugin's styling preferences into our format
                # (This is a simplified example - expand as needed)
                for theme in ["dark", "light"]:
                    # Handle base styling
                    theme_colors = styling_prefs.get("colors", {}).get(theme, {})
                    for color_key, color_value in theme_colors.items():
                        if color_key == "primary":
                            style_data[theme]["base"]["background-color"] = color_value
                        elif color_key == "text":
                            style_data[theme]["base"]["color"] = color_value
                            
                    # Handle stage-specific styling
                    for stage in ["preprocessing", "analysis", "results"]:
                        stage_color = styling_prefs.get("stages", {}).get(stage, {}).get(theme)
                        if stage_color:
                            style_data[theme]["stages"][stage] = {
                                "background-color": stage_color
                            }
                            
                    # Handle importance levels
                    for level in ["required", "optional"]:
                        border_color = styling_prefs.get("importance", {}).get(level, {}).get(theme)
                        if border_color:
                            style_data[theme]["importance"][level] = {
                                "border-left": f"3px solid {border_color}"
                            }
                
                # Register the processed style data
                self.register_plugin_styles(plugin_id, style_data)
                
            except Exception as e:
                logger.warning(f"Error processing styles for plugin {plugin.plugin_self_metadata().name}: {e}")
