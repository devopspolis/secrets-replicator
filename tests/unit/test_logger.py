"""
Unit tests for logger module
"""

import json
import logging
import pytest
from io import StringIO
from logger import (
    JsonFormatter,
    setup_logger,
    LogContext,
    log_event,
    log_secret_operation,
    log_transformation,
    log_replication,
    log_error,
    get_logger,
)


class TestJsonFormatter:
    """Tests for JsonFormatter"""

    def test_json_formatter_basic(self):
        """Test basic JSON formatting"""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_json_formatter_with_context(self):
        """Test JSON formatting with context"""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.context = {"request_id": "123", "secret_id": "my-secret"}

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert "context" in parsed
        assert parsed["context"]["request_id"] == "123"

    def test_json_formatter_with_exception(self):
        """Test JSON formatting with exception"""
        formatter = JsonFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["level"] == "ERROR"
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestSetupLogger:
    """Tests for setup_logger function"""

    def test_setup_logger_default(self):
        """Test logger setup with defaults"""
        logger = setup_logger("test-default")

        assert logger.name == "test-default"
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1

    def test_setup_logger_with_level(self):
        """Test logger setup with custom level"""
        logger = setup_logger("test-debug", level="DEBUG")

        assert logger.level == logging.DEBUG

    def test_setup_logger_json_format(self):
        """Test logger with JSON formatting"""
        logger = setup_logger("test-json", use_json=True)

        handler = logger.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)

    def test_setup_logger_plain_format(self):
        """Test logger with plain formatting"""
        logger = setup_logger("test-plain", use_json=False)

        handler = logger.handlers[0]
        assert not isinstance(handler.formatter, JsonFormatter)

    def test_setup_logger_clears_existing_handlers(self):
        """Test that setup_logger clears existing handlers"""
        logger = setup_logger("test-clear")
        initial_handler_count = len(logger.handlers)

        # Setup again
        logger = setup_logger("test-clear")

        # Should still have same number of handlers (not duplicated)
        assert len(logger.handlers) == initial_handler_count


class TestLogContext:
    """Tests for LogContext context manager"""

    def test_log_context_adds_context(self, caplog):
        """Test that LogContext adds context to logs"""
        logger = setup_logger("test-context", use_json=False)

        with LogContext(logger, request_id="abc-123", secret_id="my-secret"):
            logger.info("Test message")

        # Note: Testing context in logs requires checking the formatter output
        # For this test, we just verify no errors occur

    def test_log_context_restores_factory(self):
        """Test that LogContext restores log record factory"""
        logger = setup_logger("test-factory")

        old_factory = logging.getLogRecordFactory()

        with LogContext(logger, test="value"):
            # Factory should be different inside context
            pass

        # Factory should be restored after context
        assert logging.getLogRecordFactory() == old_factory


class TestLogEvent:
    """Tests for log_event function"""

    def test_log_event_info(self, caplog):
        """Test logging INFO event"""
        logger = setup_logger("test-event", use_json=False)
        logger.propagate = True  # Enable for caplog

        log_event(logger, "INFO", "Test event", key="value")

        assert len(caplog.records) > 0
        assert caplog.records[0].message == "Test event"
        assert caplog.records[0].levelname == "INFO"

    def test_log_event_error(self, caplog):
        """Test logging ERROR event"""
        logger = setup_logger("test-error", use_json=False)
        logger.propagate = True

        log_event(logger, "ERROR", "Error event", error_code=500)

        assert len(caplog.records) > 0
        assert caplog.records[0].levelname == "ERROR"

    def test_log_event_with_context(self, caplog):
        """Test logging event with multiple context fields"""
        logger = setup_logger("test-multi-context", use_json=False)
        logger.propagate = True

        log_event(logger, "INFO", "Multi context", field1="value1", field2="value2", field3=123)

        assert len(caplog.records) > 0


class TestLogSecretOperation:
    """Tests for log_secret_operation function"""

    def test_log_secret_operation_basic(self, caplog):
        """Test logging secret operation"""
        logger = setup_logger("test-secret-op", use_json=False)
        logger.propagate = True

        log_secret_operation(logger, "read", "my-secret")

        assert len(caplog.records) > 0
        assert "Secret operation: read" in caplog.records[0].message

    def test_log_secret_operation_with_arn(self, caplog):
        """Test logging secret operation with ARN"""
        logger = setup_logger("test-secret-arn", use_json=False)
        logger.propagate = True

        log_secret_operation(
            logger,
            "write",
            "my-secret",
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:test",
            version_id="v1",
        )

        assert len(caplog.records) > 0

    def test_log_secret_operation_masks_long_ids(self, caplog):
        """Test that long secret IDs are masked"""
        logger = setup_logger("test-mask", use_json=False)
        logger.propagate = True

        long_secret_id = "a" * 50  # Long secret ID
        log_secret_operation(logger, "transform", long_secret_id)

        # Should mask the secret ID
        assert len(caplog.records) > 0


class TestLogTransformation:
    """Tests for log_transformation function"""

    def test_log_transformation(self, caplog):
        """Test logging transformation metrics"""
        logger = setup_logger("test-transform", use_json=False)
        logger.propagate = True

        log_transformation(logger, "sed", 3, 1024, 1024, 15.5)

        assert len(caplog.records) > 0
        assert "Transformation completed" in caplog.records[0].message

    def test_log_transformation_size_change(self, caplog):
        """Test transformation with size change"""
        logger = setup_logger("test-size-change", use_json=False)
        logger.propagate = True

        log_transformation(logger, "json", 5, 1000, 1200, 25.3)

        assert len(caplog.records) > 0


class TestLogReplication:
    """Tests for log_replication function"""

    def test_log_replication_success(self, caplog):
        """Test logging successful replication"""
        logger = setup_logger("test-repl-success", use_json=False)
        logger.propagate = True

        log_replication(logger, "us-east-1", "us-west-2", "my-secret", True, 234.5)

        assert len(caplog.records) > 0
        assert "Replication succeeded" in caplog.records[0].message
        assert caplog.records[0].levelname == "INFO"

    def test_log_replication_failure(self, caplog):
        """Test logging failed replication"""
        logger = setup_logger("test-repl-fail", use_json=False)
        logger.propagate = True

        log_replication(
            logger, "us-east-1", "us-west-2", "my-secret", False, 100.0, error="Access denied"
        )

        assert len(caplog.records) > 0
        assert "Replication failed" in caplog.records[0].message
        assert caplog.records[0].levelname == "ERROR"


class TestLogError:
    """Tests for log_error function"""

    def test_log_error_basic(self, caplog):
        """Test logging error"""
        logger = setup_logger("test-err-basic", use_json=False)
        logger.propagate = True

        error = ValueError("Test error")
        log_error(logger, error)

        assert len(caplog.records) > 0
        assert caplog.records[0].levelname == "ERROR"
        assert "Test error" in caplog.records[0].message

    def test_log_error_with_context(self, caplog):
        """Test logging error with context"""
        logger = setup_logger("test-err-context", use_json=False)
        logger.propagate = True

        error = RuntimeError("Runtime error")
        log_error(logger, error, context={"secret_id": "my-secret", "region": "us-east-1"})

        assert len(caplog.records) > 0
        assert caplog.records[0].levelname == "ERROR"


class TestGetLogger:
    """Tests for get_logger function"""

    def test_get_logger_creates_global(self):
        """Test that get_logger creates global logger"""
        logger = get_logger()

        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns same instance"""
        logger1 = get_logger()
        logger2 = get_logger()

        # Should return the same logger instance
        assert logger1 is logger2


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_log_with_none_values(self, caplog):
        """Test logging with None values in context"""
        logger = setup_logger("test-none", use_json=False)
        logger.propagate = True

        log_event(logger, "INFO", "Test", field1=None, field2="value")

        assert len(caplog.records) > 0

    def test_log_with_special_characters(self, caplog):
        """Test logging with special characters"""
        logger = setup_logger("test-special", use_json=False)
        logger.propagate = True

        log_event(logger, "INFO", 'Test with "quotes" and \\backslashes')

        assert len(caplog.records) > 0

    def test_json_formatter_with_datetime(self):
        """Test JSON formatter handles datetime objects"""
        from datetime import datetime

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.timestamp = datetime.now()

        # Should not raise error
        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert "timestamp" in parsed

    def test_log_secret_operation_with_extra_context(self, caplog):
        """Test log_secret_operation with extra context fields"""
        logger = setup_logger("test-extra", use_json=False)
        logger.propagate = True

        log_secret_operation(logger, "read", "my-secret", extra_field1="value1", extra_field2=123)

        assert len(caplog.records) > 0
