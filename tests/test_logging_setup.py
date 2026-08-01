"""Tests for logging setup."""

import logging

from radioplayer.logging_setup import setup_logging, enable_file_logging, disable_file_logging


class TestLoggingSetup:
    def test_setup_logging_returns_logger(self):
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "RadioPlayer"

    def test_setup_logging_idempotent(self):
        radio_logger = logging.getLogger("RadioPlayer")
        radio_logger.handlers.clear()
        setup_logging()
        count = len(radio_logger.handlers)
        setup_logging()
        assert len(radio_logger.handlers) == count

    def test_enable_disable_file_logging(self, tmp_path):
        log_file = tmp_path / "test.log"
        radio_logger = logging.getLogger("RadioPlayer")
        radio_logger.handlers.clear()
        logger = setup_logging(log_file=log_file)

        enable_file_logging(logger)
        disable_file_logging(logger)
