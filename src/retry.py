"""
Retry logic with exponential backoff for AWS operations.

Provides decorators and utilities for retrying transient failures
with configurable backoff strategies.
"""

import random
import logging
from typing import Callable, Type
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
from src.logger import get_logger
from src.exceptions import ThrottlingError, InternalServiceError, AWSClientError

# Get logger for retry operations
logger = get_logger()


def should_retry_aws_error(exception: Exception) -> bool:
    """
    Determine if an AWS error should be retried.

    Args:
        exception: The exception to check

    Returns:
        True if the error is transient and should be retried

    Examples:
        >>> should_retry_aws_error(ThrottlingError("Rate exceeded"))
        True
        >>> should_retry_aws_error(SecretNotFoundError("Not found"))
        False
    """
    # Retry on throttling and internal service errors
    retriable_errors = (ThrottlingError, InternalServiceError)
    return isinstance(exception, retriable_errors)


def add_jitter(wait_time: float, jitter_factor: float = 0.1) -> float:
    """
    Add jitter to wait time to prevent thundering herd.

    Args:
        wait_time: Base wait time in seconds
        jitter_factor: Amount of randomness (0.0 to 1.0)

    Returns:
        Wait time with jitter applied

    Examples:
        >>> add_jitter(10.0, 0.1)  # Returns 9.0-11.0
        10.5
    """
    jitter = wait_time * jitter_factor * random.uniform(-1, 1)
    return max(0, wait_time + jitter)


class ExponentialBackoffWithJitter:
    """
    Custom wait strategy that adds jitter to exponential backoff.

    This prevents the "thundering herd" problem when multiple Lambda
    instances retry at the same time.

    Usage:
        @retry(wait=ExponentialBackoffWithJitter(multiplier=2, min=2, max=32))
        def my_function():
            ...
    """

    def __init__(self, multiplier: int = 1, min: float = 2, max: float = 32,
                 jitter_factor: float = 0.1):
        """
        Initialize backoff strategy.

        Args:
            multiplier: Multiplier for exponential backoff
            min: Minimum wait time in seconds
            max: Maximum wait time in seconds
            jitter_factor: Amount of jitter (0.0 to 1.0)
        """
        self.multiplier = multiplier
        self.min = min
        self.max = max
        self.jitter_factor = jitter_factor

    def __call__(self, retry_state):
        """Calculate wait time for retry attempt."""
        # Calculate exponential backoff: min * (multiplier ^ attempt)
        attempt = retry_state.attempt_number
        wait_time = min(self.min * (self.multiplier ** (attempt - 1)), self.max)

        # Add jitter
        return add_jitter(wait_time, self.jitter_factor)


def with_retries(
    max_attempts: int = 5,
    min_wait: float = 2,
    max_wait: float = 32,
    jitter_factor: float = 0.1
) -> Callable:
    """
    Decorator to add retry logic with exponential backoff and jitter.

    Retries on transient AWS errors (throttling, internal errors).

    Args:
        max_attempts: Maximum number of retry attempts (default: 5)
        min_wait: Minimum wait time in seconds (default: 2)
        max_wait: Maximum wait time in seconds (default: 32)
        jitter_factor: Jitter amount 0.0-1.0 (default: 0.1)

    Returns:
        Decorated function with retry logic

    Examples:
        @with_retries(max_attempts=3, min_wait=1, max_wait=10)
        def get_secret(client, secret_id):
            return client.get_secret(secret_id)

    Retry schedule (without jitter):
        - Attempt 1: Immediate
        - Attempt 2: Wait 2s
        - Attempt 3: Wait 4s
        - Attempt 4: Wait 8s
        - Attempt 5: Wait 16s
        - Attempt 6: Wait 32s (capped at max_wait)
    """
    return retry(
        # Stop after max attempts
        stop=stop_after_attempt(max_attempts),

        # Exponential backoff with jitter
        wait=ExponentialBackoffWithJitter(
            multiplier=2,
            min=min_wait,
            max=max_wait,
            jitter_factor=jitter_factor
        ),

        # Only retry on specific exceptions
        retry=retry_if_exception_type((ThrottlingError, InternalServiceError)),

        # Log before sleeping
        before_sleep=before_sleep_log(logger, logging.WARNING),

        # Log after retry
        after=after_log(logger, logging.INFO)
    )


def with_retries_custom(
    retry_on: tuple = (ThrottlingError, InternalServiceError),
    max_attempts: int = 5,
    min_wait: float = 2,
    max_wait: float = 32,
    jitter_factor: float = 0.1
) -> Callable:
    """
    Decorator with custom retry conditions.

    Args:
        retry_on: Tuple of exception types to retry on
        max_attempts: Maximum number of attempts
        min_wait: Minimum wait time in seconds
        max_wait: Maximum wait time in seconds
        jitter_factor: Jitter amount

    Returns:
        Decorated function with custom retry logic

    Examples:
        @with_retries_custom(
            retry_on=(ConnectionError, TimeoutError),
            max_attempts=3
        )
        def make_http_request():
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=ExponentialBackoffWithJitter(
            multiplier=2,
            min=min_wait,
            max=max_wait,
            jitter_factor=jitter_factor
        ),
        retry=retry_if_exception_type(retry_on),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO)
    )


# Convenience decorators for common scenarios

def retry_on_throttle(func: Callable) -> Callable:
    """
    Decorator that retries only on throttling errors.

    Uses default retry configuration (5 attempts, 2-32s wait).

    Examples:
        @retry_on_throttle
        def get_secret(client, secret_id):
            return client.get_secret(secret_id)
    """
    return with_retries_custom(
        retry_on=(ThrottlingError,),
        max_attempts=5
    )(func)


def retry_on_transient_errors(func: Callable) -> Callable:
    """
    Decorator that retries on all transient AWS errors.

    Retries on throttling and internal service errors.

    Examples:
        @retry_on_transient_errors
        def put_secret(client, secret_id, value):
            return client.put_secret(secret_id, value)
    """
    return with_retries()(func)


def get_retry_stats(retry_state) -> dict:
    """
    Get statistics about retry attempts.

    Args:
        retry_state: Tenacity retry state object

    Returns:
        Dictionary with retry statistics

    Examples:
        {
            'attempt_number': 3,
            'total_wait_time': 6.2,
            'outcome': 'success'
        }
    """
    return {
        'attempt_number': retry_state.attempt_number,
        'idle_for': getattr(retry_state, 'idle_for', 0),
        'next_action': str(getattr(retry_state, 'next_action', None))
    }
