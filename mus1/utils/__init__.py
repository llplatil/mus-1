"""Utility modules for MUS1

Development Notes:
- logging_config.py: Global logging for both app and test sessions
"""

from .logging_config import setup_logging, get_logger, shutdown_logging

def init_logging() -> bool:
    """Initialize logging system"""
    return setup_logging()

__all__ = ['init_logging', 'get_logger', 'shutdown_logging'] 