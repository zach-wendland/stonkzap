import logging
import sys
from typing import Optional
from functools import lru_cache

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure application-wide logging."""

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    return root_logger

@lru_cache()
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance for a module."""
    if name is None:
        name = __name__
    return logging.getLogger(name)
