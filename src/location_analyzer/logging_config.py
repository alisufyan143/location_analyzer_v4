"""
Structured logging configuration.

Replaces all print() debug statements with proper logging.
Supports both console and file output with configurable levels.
"""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: str = "logs/location_analyzer.log") -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to the log file
    """
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # File handler — detailed output
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # Console handler — cleaner output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(console_formatter)

    # Root logger
    root_logger = logging.getLogger("location_analyzer")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    for noisy_logger in ["urllib3", "selenium", "playwright", "httpx", "httpcore"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    root_logger.info("Logging configured — level=%s, file=%s", level, log_file)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger under the location_analyzer namespace.

    Usage:
        from location_analyzer.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Processing postcode %s", postcode)

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"location_analyzer.{name}")
