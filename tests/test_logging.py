"""
Tests for the logging configuration module.
"""

import logging

import pytest

from location_analyzer.logging_config import setup_logging, get_logger


@pytest.fixture(autouse=True)
def cleanup_logger():
    """Remove all handlers from the location_analyzer logger after each test."""
    yield
    logger = logging.getLogger("location_analyzer")
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


class TestSetupLogging:
    """Tests for logging setup."""

    def test_setup_creates_logger(self, tmp_path):
        """setup_logging should create a configured logger."""
        log_file = str(tmp_path / "test.log")
        setup_logging(level="DEBUG", log_file=log_file)
        
        logger = logging.getLogger("location_analyzer")
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) >= 2  # file + console

    def test_setup_creates_log_file_directory(self, tmp_path):
        """setup_logging should create the log file directory if missing."""
        log_file = str(tmp_path / "subdir" / "test.log")
        setup_logging(level="INFO", log_file=log_file)
        
        assert (tmp_path / "subdir").exists()

    def test_log_message_written_to_file(self, tmp_path):
        """Messages should be written to the log file."""
        log_file = str(tmp_path / "test.log")
        setup_logging(level="DEBUG", log_file=log_file)
        
        logger = logging.getLogger("location_analyzer")
        logger.info("Test message for file")
        
        # Flush handlers
        for handler in logger.handlers:
            handler.flush()
        
        with open(log_file) as f:
            content = f.read()
        assert "Test message for file" in content


class TestGetLogger:
    """Tests for the get_logger helper."""

    def test_returns_namespaced_logger(self):
        """get_logger should return a logger under location_analyzer namespace."""
        logger = get_logger("test_module")
        assert logger.name == "location_analyzer.test_module"

    def test_different_modules_get_different_loggers(self):
        """Each module should get its own logger instance."""
        logger1 = get_logger("module_a")
        logger2 = get_logger("module_b")
        assert logger1.name != logger2.name
