"""
Logging Configuration
====================
SOLID: Single Responsibility - Centralized logging setup

All Lambda functions use this configuration for consistent logging.
"""

import logging
import os


# ============================================================================
# Logging Configuration
# ============================================================================

def setup_logger(name=None, level=None):
    """
    Configure and return a logger instance

    Args:
        name: Logger name (default: root logger)
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               If None, uses LOG_LEVEL environment variable or defaults to INFO

    Returns:
        Configured logger instance
    """
    # Get or create logger
    logger = logging.getLogger(name) if name else logging.getLogger()

    # Determine log level
    if level is None:
        level = os.environ.get('LOG_LEVEL', 'INFO')

    # Convert string to logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Return configured logger
    return logger


def get_default_logger():
    """
    Get default root logger with INFO level

    Returns:
        Root logger configured with INFO level
    """
    return setup_logger()


# ============================================================================
# Default Logger Instance
# ============================================================================

# Pre-configured default logger for Lambda functions
logger = get_default_logger()
