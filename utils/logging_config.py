"""Logging configuration for MUS1"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import re

def verify_log_access(log_file: Path) -> bool:
    """Verify log file is accessible"""
    try:
        # Check if we can write
        if log_file.exists():
            with open(log_file, 'a') as f:
                f.write('')
        else:
            with open(log_file, 'w') as f:
                f.write('')
        # Check if we can read
        with open(log_file, 'r') as f:
            f.read()
        return True
    except (IOError, PermissionError):
        return False

def setup_logging(log_dir: Optional[Path] = None, level=logging.INFO) -> bool:
    """Setup application logging
    
    Args:
        log_dir: Directory for log files. If None, uses cwd/logs
        level: Logging level
        
    Returns:
        bool: True if logging setup succeeded
    """
    try:
        # Create root logger
        root_logger = logging.getLogger("mus1")
        root_logger.setLevel(level)
        
        # Setup log directory
        if log_dir is None:
            log_dir = Path.cwd() / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "mus1.log"
        
        # Verify we can access log file
        if not verify_log_access(log_file):
            print(f"ERROR: Cannot access log file: {log_file}")
            return False
            
        # Create formatters
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Setup file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        
        # Remove any existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
            
        root_logger.addHandler(file_handler)
        
        # Log startup
        root_logger.info("\n" + "="*80)
        root_logger.info(f"Starting new session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        root_logger.info("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to setup logging: {e}")
        return False

def get_class_logger(cls) -> logging.Logger:
    """Get logger using class name"""
    root_logger = logging.getLogger("mus1")
    if not root_logger.handlers:  # If logging not initialized
        initialize_logging()  # Use initialize_logging instead of setup_logging
    # Convert CamelCase to dot.separated.lowercase
    name = re.sub('([a-z0-9])([A-Z])', r'\1.\2', cls.__name__).lower()
    return logging.getLogger(f"mus1.{name}")

def get_logger(name: str) -> logging.Logger:
    """Get logger with proper namespace"""
    root_logger = logging.getLogger("mus1")
    if not root_logger.handlers:
        initialize_logging()  # Use initialize_logging instead of setup_logging
    return logging.getLogger(f"mus1.{name}")

def initialize_logging(
    log_file: str = "mus1.log",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    force: bool = False
) -> None:
    """Initialize logging system"""
    root_logger = logging.getLogger("mus1")
    
    if root_logger.handlers and not force:
        return
        
    if force:
        shutdown_logging()
    
    try:
        # Configure root logger
        root_logger.setLevel(logging.DEBUG)
        root_logger.propagate = False
        
        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(console_level)
        console.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        root_logger.addHandler(console)
        
        # File handler with context info
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        root_logger.addHandler(file_handler)
        
        # Log initialization context
        root_logger.info("Logging initialized - Context: %s", 
                        "TEST" if "pytest" in sys.modules else "APP")
        
    except Exception as e:
        print(f"Failed to initialize logging: {e}")

def shutdown_logging() -> None:
    """Clean up logging handlers"""
    root_logger = logging.getLogger("mus1")
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close() 