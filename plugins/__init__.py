"""Plugin system for MUS1"""

from ..utils import get_logger
from ..core.metadata import PluginMetadata

logger = get_logger("plugins")

_plugin_registry = {}  # Store plugin classes

def init_plugins() -> bool:
    """Initialize plugin system"""
    try:
        logger.info("Initializing plugin system")
        
        # Import and register plugins
        from .base_plugin import BasePlugin
        from .nor import NORPlugin
        
        # Register built-in plugins
        _plugin_registry.update({
            'nor': NORPlugin
        })
        
        # Verify plugins
        for name, plugin_cls in _plugin_registry.items():
            if not hasattr(plugin_cls, 'metadata'):
                logger.error(f"Plugin {name} missing metadata")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize plugin system: {e}")
        return False

def get_plugin(plugin_type: str):
    """Get plugin class by type"""
    return _plugin_registry.get(plugin_type)

def connect_plugins(state_manager, data_manager):
    """Connect core managers to registered plugins"""
    for plugin_cls in _plugin_registry.values():
        plugin_cls._state_manager = state_manager
        plugin_cls._data_manager = data_manager

__all__ = [
    'init_plugins',
    'BasePlugin',
    'NORPlugin'
]