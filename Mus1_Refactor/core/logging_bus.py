from datetime import datetime
import logging
import os
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
    
    # Maximum number of lines in the log file
    MAX_LOG_LINES = 500
    
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
        
        # Get the log file path from logger's handlers
        self.log_file = self._get_log_file_path()
        
        # Check log file size on startup and rotate if needed
        if self.log_file and os.path.exists(self.log_file):
            self._check_log_file_size()
        
    def _get_log_file_path(self) -> Optional[str]:
        """Get the path to the log file from logger's handlers."""
        for handler in self.logger.handlers + logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                return handler.baseFilename
        return None
        
    def _check_log_file_size(self) -> None:
        """Check log file size and rotate if it exceeds MAX_LOG_LINES."""
        if not self.log_file or not os.path.exists(self.log_file):
            return
            
        # Count lines in the log file
        line_count = 0
        try:
            with open(self.log_file, 'r') as f:
                for _ in f:
                    line_count += 1
                    
            # Rotate if line count exceeds limit
            if line_count > self.MAX_LOG_LINES:
                self._rotate_log_file()
        except Exception as e:
            print(f"Error checking log file size: {e}")
    
    def _rotate_log_file(self) -> None:
        """Rotate the log file by removing oldest lines and keeping recent ones."""
        try:
            # Read all lines from the log file
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
            
            # Instead of keeping just the most recent MAX_LOG_LINES,
            # we'll delete half of the oldest lines when we reach the limit
            num_lines = len(lines)
            if num_lines > self.MAX_LOG_LINES:
                # Delete oldest half of excess lines
                lines_to_delete = (num_lines - self.MAX_LOG_LINES) // 2
                lines_to_keep = lines[lines_to_delete:]
                
                # Write back the kept lines
                with open(self.log_file, 'w') as f:
                    for line in lines_to_keep:
                        f.write(line)
                    
                # Log rotation completed message
                self.logger.info(f"Log file rotated, deleted {lines_to_delete} oldest lines")
            else:
                self.logger.info(f"Log rotation not needed, {num_lines} lines in log file")
        except Exception as e:
            print(f"Error rotating log file: {e}")
        
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
        
        # Check log file size each time we log to potentially trigger rotation
        if self.log_file:
            self._check_log_file_size()
        
        # Create timestamp
        timestamp = datetime.now()
        
        # Notify all observers synchronously
        for observer in self._observers:
            observer.on_log_event(message, level, source, timestamp) 