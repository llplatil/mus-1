"""Plugin system for MUS1"""

from .base_plugin import BasePlugin
from typing import Dict, Type

# Plugin registry
plugins: Dict[str, Type[BasePlugin]] = {}

def register_plugin(plugin_class: Type[BasePlugin]) -> None:
    """Register a plugin class"""
    plugins[plugin_class.name] = plugin_class

def get_plugin(name: str) -> Type[BasePlugin]:
    """Get a plugin by name"""
    return plugins.get(name)

# Register built-in plugins
# register_plugin(NORPlugin)

__all__ = ['BasePlugin', 'register_plugin', 'get_plugin', 'plugins'] 