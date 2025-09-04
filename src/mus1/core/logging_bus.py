from datetime import datetime
import logging
import os
from pathlib import Path
from typing import List, Callable, Protocol, Optional
# Import the handler for type checking if needed, though not strictly necessary here
from logging.handlers import RotatingFileHandler 

class LogObserver(Protocol):
    """Protocol defining what a log observer must implement."""
    def on_log_event(self, message: str, level: str, source: str, timestamp: datetime) -> None:
        """Handle a log event."""
        pass

class LoggingEventBus:
    """Central event bus plus helper to configure rotating file handler."""
    """Central event bus for distributing log messages throughout the application.
    Implemented as a singleton for easy access from anywhere in the application.
    Relies on standard library handlers (e.g., RotatingFileHandler) for file management.
    """
    # The singleton instance
    _instance = None
    
    # Removed MAX_LOG_LINES constant

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
        # Ensure we have at least a console handler for quick dev output
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            self.logger.addHandler(ch)
        
        # Get the log file path from logger's handlers (optional, might not be needed)
        self.log_file = self._get_log_file_path()
        
        # Removed check log file size on startup

    def configure_default_file_handler(self, project_root: Path, *, max_size: int = 1 * 1024 * 1024, backups: int = 3) -> None:
        """Attach/replace a RotatingFileHandler inside *project_root*.

        Called by CLI and GUI startup so both write to the same log file
        `<project>/mus1.log`.  When the file size exceeds *max_size* it
        rotates, keeping *backups* older logs.  This prevents megabyte-long log
        files during development without manual cleanup.
        """
        log_path = project_root / "mus1.log"
        # Remove existing RotatingFileHandler(s) that write elsewhere
        for h in list(self.logger.handlers):
            if isinstance(h, RotatingFileHandler):
                self.logger.removeHandler(h)
                h.close()
        rf_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_size,
            backupCount=backups,
            encoding="utf-8",
        )
        rf_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        rf_handler.setLevel(logging.INFO)
        self.logger.addHandler(rf_handler)
        self.logger.info("Rotating file handler configured at %s", log_path)

    def _get_log_file_path(self) -> Optional[str]:
        """Get the path to the log file from logger's handlers."""
        # This might need adjustment depending on how RotatingFileHandler is identified
        # but often works as it inherits from FileHandler.
        for handler in self.logger.handlers + logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler): # Includes RotatingFileHandler
                return handler.baseFilename
        # Only log warning if this is called after handlers should have been configured
        # During initialization, it's normal to not have file handlers yet
        return None
        
    # Removed _check_log_file_size method
    
    # Removed _rotate_log_file method
        
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
        # Ensure source is included for clarity in the main log file
        log_message = f"[{source}] {message}" if source else message
        self.logger.log(std_level, log_message)
        
        # Removed check log file size call
        
        # Create timestamp
        timestamp = datetime.now()
        
        # Notify all observers synchronously
        for observer in self._observers:
            # Pass the original message and source to observers
            observer.on_log_event(message, level, source, timestamp) 