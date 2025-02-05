"""Plugin system for MUS1"""

from .base_plugin import BasePlugin, PluginMetadata
from .nor import NORPlugin

__all__ = [
    'BasePlugin',
    'PluginMetadata',
    'NORPlugin'
]