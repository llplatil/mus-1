"""Novel Object Recognition (NOR) plugin for MUS1"""

from .nor_analysis import NORPlugin
from ...core.metadata import PluginMetadata

# Define plugin metadata
metadata = PluginMetadata(
    name="nor",
    version="0.1.0", 
    description="Novel Object Recognition Analysis",
    author="MUS1 Team"
)

# Attach metadata to plugin
NORPlugin.metadata = metadata

__all__ = ['NORPlugin'] 