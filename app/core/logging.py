"""
Logging configuration for PII Anonymizer.
"""

import logging
import sys
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    name: Optional[str] = None
) -> logging.Logger:
    """
    Set up structured logging.
    
    Args:
        level: Logging level (default: INFO)
        name: Logger name (default: root logger)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    return logger


# Default logger for the application
logger = setup_logging(name="anonymizer")


def get_logger(name: str) -> logging.Logger:
    """Get a child logger with the given name."""
    return logging.getLogger(f"anonymizer.{name}")

