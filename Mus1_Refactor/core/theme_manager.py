import os
from PySide6 import QtWidgets
from qt_material import apply_stylesheet


class ThemeManager:
    """Manages application themes using qt-material with a minimalist approach."""

    @staticmethod
    def apply_theme(app, config=None):
        """Apply theme to application with custom configuration."""
        # Default theme and customizations
        theme_name = "dark_teal.xml"
        custom_css = "custom.css"
        
        # Default theme variables
        extra = {
            # Font configuration
            'font_family': 'Roboto',
            'font_size': '12px',
            'line_height': '20px',
            
            # Density for compact UI
            'density_scale': '-1',
            
            # Button colors
            'danger': '#dc3545',
            'warning': '#ffc107',
            'success': '#17a2b8'
        }
        
        # Override defaults if configuration provided
        if config:
            if 'theme_name' in config:
                theme_name = config['theme_name']
            if 'extra' in config:
                extra.update(config['extra'])
        
        # Determine paths to theme files relative to this file
        theme_path = os.path.join(os.path.dirname(__file__), theme_name)
        css_path = os.path.join(os.path.dirname(__file__), custom_css)
        
        # Fallback: if custom theme does not exist, use the theme name directly
        if not os.path.exists(theme_path):
            theme_path = theme_name
        
        # Apply the theme using qt-material
        return apply_stylesheet(app, theme=theme_path, css_file=css_path, extra=extra) 