from datetime import datetime
import logging
from typing import List, Callable, Protocol, Optional

class LogObserver(Protocol):
    """Protocol defining what a log observer must implement."""
    def on_log_event(self, message: str, level: str, source: str, timestamp: datetime) -> None:
        """Handle a log event."""
        pass

class LoggingEventBus:
    """Central event bus for distributing log messages throughout the application.
    Implemented as a singleton for easy access from anywhere in the application.
    """
    # The singleton instance
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = LoggingEventBus()
        return cls._instance
    
    def __init__(self):
        """Initialize the logging event bus."""
        # Only allow initialization if no instance exists
        if LoggingEventBus._instance is not None:
            raise RuntimeError("LoggingEventBus is a singleton! Use LoggingEventBus.get_instance() instead.")
        
        self._observers: List[LogObserver] = []
        self.logger = logging.getLogger("mus1")
        
    def add_observer(self, observer: LogObserver) -> None:
        """Add an observer to receive log events."""
        if observer not in self._observers:
            self._observers.append(observer)
        
    def remove_observer(self, observer: LogObserver) -> None:
        """Remove an observer from receiving log events."""
        if observer in self._observers:
            self._observers.remove(observer)
            
    def log(self, message: str, level: str = 'info', source: str = '') -> None:
        """
        Log a message to all observers and the standard logging system.
        
        Args:
            message: The log message
            level: Log level ('info', 'success', 'warning', 'error')
            source: Source component generating the log
        """
        # Map UI log levels to standard logging levels
        log_level_map = {
            'info': logging.INFO,
            'success': logging.INFO,  # Success is a UI concept, map to INFO
            'warning': logging.WARNING,
            'error': logging.ERROR
        }
        
        # Log to standard logger
        std_level = log_level_map.get(level.lower(), logging.INFO)
        self.logger.log(std_level, f"[{source}] {message}")
        
        # Create timestamp
        timestamp = datetime.now()
        
        # Notify all observers synchronously
        for observer in self._observers:
            observer.on_log_event(message, level, source, timestamp) 