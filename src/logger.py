"""
Structured JSON logging for the secrets replicator.

Provides secure logging that never exposes secret values.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.utils import sanitize_log_message, mask_secret


class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format for easy parsing by CloudWatch Logs Insights
    and other log aggregation tools.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        # Base log entry
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
        }

        # Add context if available
        if hasattr(record, 'context'):
            log_entry['context'] = record.context

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName',
                          'relativeCreated', 'thread', 'threadName', 'exc_info',
                          'exc_text', 'stack_info', 'context']:
                log_entry[key] = value

        # Sanitize the entire log entry (convert to string, sanitize, parse back)
        log_json = json.dumps(log_entry, default=str)
        sanitized_json = sanitize_log_message(log_json)

        return sanitized_json


def setup_logger(name: str = 'secrets-replicator',
                 level: str = 'INFO',
                 use_json: bool = True) -> logging.Logger:
    """
    Setup a logger with JSON formatting.

    Args:
        name: Logger name (default: 'secrets-replicator')
        level: Log level (default: 'INFO')
        use_json: Whether to use JSON formatting (default: True)

    Returns:
        Configured logger instance

    Examples:
        >>> logger = setup_logger('my-lambda', 'DEBUG')
        >>> logger.info('Test message')
    """
    logger = logging.getLogger(name)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Set log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Set formatter
    if use_json:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


class LogContext:
    """
    Context manager for adding contextual information to logs.

    Usage:
        with LogContext(logger, request_id='abc-123', secret_arn='arn:...'):
            logger.info('Processing secret')  # Will include context
    """

    def __init__(self, logger: logging.Logger, **context):
        """
        Initialize log context.

        Args:
            logger: Logger to add context to
            **context: Contextual key-value pairs
        """
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        """Enter context manager"""
        # Save old factory
        self.old_factory = logging.getLogRecordFactory()

        # Create new factory that adds context
        context = self.context

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            record.context = context
            return record

        # Set new factory
        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager"""
        # Restore old factory
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)


def log_event(logger: logging.Logger,
              level: str,
              message: str,
              **context):
    """
    Log a message with context.

    Args:
        logger: Logger instance
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        message: Log message
        **context: Additional context fields

    Examples:
        >>> logger = setup_logger()
        >>> log_event(logger, 'INFO', 'Secret replicated',
        ...          secret_id='my-secret', region='us-west-2')
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create log record with context
    extra = {'context': context}
    logger.log(log_level, message, extra=extra)


def log_secret_operation(logger: logging.Logger,
                         operation: str,
                         secret_id: str,
                         secret_arn: Optional[str] = None,
                         version_id: Optional[str] = None,
                         **extra_context):
    """
    Log a secret operation with metadata (never logs secret value).

    Args:
        logger: Logger instance
        operation: Operation type ('read', 'write', 'transform', etc.)
        secret_id: Secret ID or name
        secret_arn: Secret ARN (optional)
        version_id: Secret version ID (optional)
        **extra_context: Additional context

    Examples:
        >>> logger = setup_logger()
        >>> log_secret_operation(logger, 'read', 'my-secret',
        ...                     secret_arn='arn:...', version_id='v1')
    """
    context = {
        'operation': operation,
        'secret_id': mask_secret(secret_id, show_chars=6) if len(secret_id) > 20 else secret_id,
        **extra_context
    }

    if secret_arn:
        context['secret_arn'] = secret_arn

    if version_id:
        context['version_id'] = version_id

    log_event(logger, 'INFO', f'Secret operation: {operation}', **context)


def log_transformation(logger: logging.Logger,
                      mode: str,
                      rules_count: int,
                      input_size: int,
                      output_size: int,
                      duration_ms: float):
    """
    Log transformation metrics.

    Args:
        logger: Logger instance
        mode: Transformation mode ('sed' or 'json')
        rules_count: Number of transformation rules applied
        input_size: Input secret size in bytes
        output_size: Output secret size in bytes
        duration_ms: Transformation duration in milliseconds

    Examples:
        >>> logger = setup_logger()
        >>> log_transformation(logger, 'sed', 3, 1024, 1024, 15.5)
    """
    context = {
        'mode': mode,
        'rules_count': rules_count,
        'input_size': input_size,
        'output_size': output_size,
        'duration_ms': round(duration_ms, 2),
        'size_change': output_size - input_size
    }

    log_event(logger, 'INFO', 'Transformation completed', **context)


def log_replication(logger: logging.Logger,
                   source_region: str,
                   dest_region: str,
                   secret_id: str,
                   success: bool,
                   duration_ms: float,
                   error: Optional[str] = None):
    """
    Log replication result.

    Args:
        logger: Logger instance
        source_region: Source AWS region
        dest_region: Destination AWS region
        secret_id: Secret identifier
        success: Whether replication succeeded
        duration_ms: Replication duration in milliseconds
        error: Error message if failed (optional)

    Examples:
        >>> logger = setup_logger()
        >>> log_replication(logger, 'us-east-1', 'us-west-2',
        ...                'my-secret', True, 234.5)
    """
    context = {
        'source_region': source_region,
        'dest_region': dest_region,
        'secret_id': secret_id,
        'success': success,
        'duration_ms': round(duration_ms, 2)
    }

    if error:
        context['error'] = error

    level = 'INFO' if success else 'ERROR'
    message = 'Replication succeeded' if success else 'Replication failed'

    log_event(logger, level, message, **context)


def log_error(logger: logging.Logger,
              error: Exception,
              context: Optional[Dict[str, Any]] = None):
    """
    Log an error with context.

    Args:
        logger: Logger instance
        error: Exception that occurred
        context: Additional context (optional)

    Examples:
        >>> logger = setup_logger()
        >>> try:
        ...     raise ValueError('Test error')
        ... except Exception as e:
        ...     log_error(logger, e, {'secret_id': 'my-secret'})
    """
    error_context = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        **(context or {})
    }

    log_event(logger, 'ERROR', f'Error occurred: {error}', **error_context)


# Global logger instance
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """
    Get or create the global logger instance.

    Returns:
        Global logger instance

    Examples:
        >>> logger = get_logger()
        >>> logger.info('Using global logger')
    """
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger
