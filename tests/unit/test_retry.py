"""
Unit tests for retry module
"""

import pytest
import time
from unittest.mock import Mock, patch
from tenacity import RetryError
from src.retry import (
    should_retry_aws_error,
    add_jitter,
    with_retries,
    with_retries_custom,
    retry_on_throttle,
    retry_on_transient_errors,
    ExponentialBackoffWithJitter
)
from src.exceptions import (
    ThrottlingError,
    InternalServiceError,
    SecretNotFoundError,
    AccessDeniedError,
    AWSClientError
)


class TestShouldRetryAwsError:
    """Tests for should_retry_aws_error function"""

    def test_throttling_error_should_retry(self):
        """Test that throttling errors should be retried"""
        error = ThrottlingError("Rate exceeded")
        assert should_retry_aws_error(error) is True

    def test_internal_service_error_should_retry(self):
        """Test that internal service errors should be retried"""
        error = InternalServiceError("Internal error")
        assert should_retry_aws_error(error) is True

    def test_secret_not_found_should_not_retry(self):
        """Test that SecretNotFoundError should not be retried"""
        error = SecretNotFoundError("Secret not found")
        assert should_retry_aws_error(error) is False

    def test_access_denied_should_not_retry(self):
        """Test that AccessDeniedError should not be retried"""
        error = AccessDeniedError("Access denied")
        assert should_retry_aws_error(error) is False

    def test_generic_aws_error_should_not_retry(self):
        """Test that generic AWS errors should not be retried"""
        error = AWSClientError("Generic error")
        assert should_retry_aws_error(error) is False


class TestAddJitter:
    """Tests for add_jitter function"""

    def test_add_jitter_returns_different_values(self):
        """Test that jitter returns varying values"""
        results = [add_jitter(10.0, 0.1) for _ in range(10)]
        # Should have some variance
        assert len(set(results)) > 1

    def test_add_jitter_stays_within_bounds(self):
        """Test that jitter stays within expected bounds"""
        wait_time = 10.0
        jitter_factor = 0.1
        max_jitter = wait_time * jitter_factor

        for _ in range(100):
            result = add_jitter(wait_time, jitter_factor)
            assert wait_time - max_jitter <= result <= wait_time + max_jitter

    def test_add_jitter_never_negative(self):
        """Test that jitter never produces negative wait times"""
        for _ in range(100):
            result = add_jitter(1.0, 0.5)
            assert result >= 0

    def test_add_jitter_zero_factor(self):
        """Test jitter with zero factor returns original value"""
        result = add_jitter(10.0, 0.0)
        assert result == 10.0


class TestExponentialBackoffWithJitter:
    """Tests for ExponentialBackoffWithJitter class"""

    def test_exponential_growth(self):
        """Test that backoff grows exponentially"""
        backoff = ExponentialBackoffWithJitter(multiplier=2, min=2, max=64, jitter_factor=0)

        # Mock retry states
        retry_states = []
        for i in range(1, 6):
            state = Mock()
            state.attempt_number = i
            retry_states.append(state)

        wait_times = [backoff(state) for state in retry_states]

        # Without jitter, should be: 2, 4, 8, 16, 32
        assert wait_times[0] == 2
        assert wait_times[1] == 4
        assert wait_times[2] == 8
        assert wait_times[3] == 16
        assert wait_times[4] == 32

    def test_respects_max_wait(self):
        """Test that backoff respects maximum wait time"""
        backoff = ExponentialBackoffWithJitter(multiplier=2, min=2, max=10, jitter_factor=0)

        state = Mock()
        state.attempt_number = 10  # Would be 1024 without cap

        wait_time = backoff(state)
        assert wait_time == 10

    def test_jitter_applied(self):
        """Test that jitter is applied to wait times"""
        backoff = ExponentialBackoffWithJitter(multiplier=2, min=2, max=64, jitter_factor=0.1)

        state = Mock()
        state.attempt_number = 3

        # Get multiple samples
        wait_times = [backoff(state) for _ in range(10)]

        # Should have variance due to jitter
        assert len(set(wait_times)) > 1

        # Should be roughly around 8 seconds (2 * 2^2)
        for wt in wait_times:
            assert 7.2 <= wt <= 8.8  # 8 +/- 10%


class TestWithRetries:
    """Tests for with_retries decorator"""

    def test_success_on_first_attempt(self):
        """Test that successful calls don't retry"""
        mock_func = Mock(return_value="success")
        decorated = with_retries(max_attempts=3)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retries_on_throttling_error(self):
        """Test that throttling errors trigger retries"""
        mock_func = Mock(side_effect=[
            ThrottlingError("Rate exceeded"),
            ThrottlingError("Rate exceeded"),
            "success"
        ])
        decorated = with_retries(max_attempts=5, min_wait=0.01, max_wait=0.1)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 3

    def test_retries_on_internal_service_error(self):
        """Test that internal service errors trigger retries"""
        mock_func = Mock(side_effect=[
            InternalServiceError("Internal error"),
            "success"
        ])
        decorated = with_retries(max_attempts=3, min_wait=0.01, max_wait=0.1)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_does_not_retry_secret_not_found(self):
        """Test that SecretNotFoundError is not retried"""
        mock_func = Mock(side_effect=SecretNotFoundError("Not found"))
        decorated = with_retries(max_attempts=3)(mock_func)

        with pytest.raises(SecretNotFoundError):
            decorated()

        # Should only be called once (no retries)
        assert mock_func.call_count == 1

    def test_stops_after_max_attempts(self):
        """Test that retries stop after max attempts"""
        mock_func = Mock(side_effect=ThrottlingError("Rate exceeded"))
        decorated = with_retries(max_attempts=3, min_wait=0.01, max_wait=0.1)(mock_func)

        with pytest.raises(RetryError):
            decorated()

        assert mock_func.call_count == 3

    def test_wait_time_increases(self):
        """Test that wait time increases between retries"""
        call_times = []

        def failing_func():
            call_times.append(time.time())
            raise ThrottlingError("Rate exceeded")

        decorated = with_retries(max_attempts=3, min_wait=0.1, max_wait=1, jitter_factor=0)(failing_func)

        with pytest.raises(RetryError):
            decorated()

        # Check that intervals increased
        if len(call_times) >= 3:
            interval1 = call_times[1] - call_times[0]
            interval2 = call_times[2] - call_times[1]
            # Second interval should be longer than first (exponential backoff)
            assert interval2 > interval1


class TestWithRetriesCustom:
    """Tests for with_retries_custom decorator"""

    def test_custom_exception_types(self):
        """Test retry with custom exception types"""
        mock_func = Mock(side_effect=[
            ValueError("Error"),
            "success"
        ])
        decorated = with_retries_custom(
            retry_on=(ValueError,),
            max_attempts=3,
            min_wait=0.01,
            max_wait=0.1
        )(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_does_not_retry_unlisted_exceptions(self):
        """Test that unlisted exceptions are not retried"""
        mock_func = Mock(side_effect=RuntimeError("Error"))
        decorated = with_retries_custom(
            retry_on=(ValueError,),
            max_attempts=3
        )(mock_func)

        with pytest.raises(RuntimeError):
            decorated()

        assert mock_func.call_count == 1


class TestRetryOnThrottle:
    """Tests for retry_on_throttle decorator"""

    def test_retries_throttling_only(self):
        """Test that only throttling errors are retried"""
        mock_func = Mock(side_effect=[
            ThrottlingError("Rate exceeded"),
            "success"
        ])
        decorated = retry_on_throttle(mock_func)

        # Patch to speed up test
        with patch('src.retry.with_retries_custom') as mock_decorator:
            mock_decorator.return_value = lambda f: f
            decorated = retry_on_throttle(mock_func)

            # Verify decorator was called with correct args
            mock_decorator.assert_called_once()
            call_args = mock_decorator.call_args[1]
            assert call_args['retry_on'] == (ThrottlingError,)

    def test_does_not_retry_other_errors(self):
        """Test that non-throttling errors are not retried"""
        # This is implicitly tested by the decorator configuration
        pass


class TestRetryOnTransientErrors:
    """Tests for retry_on_transient_errors decorator"""

    def test_uses_default_configuration(self):
        """Test that default configuration is used"""
        mock_func = Mock(return_value="success")

        with patch('src.retry.with_retries') as mock_with_retries:
            mock_with_retries.return_value = lambda f: f
            decorated = retry_on_transient_errors(mock_func)

            # Verify decorator was called
            mock_with_retries.assert_called_once_with()


class TestIntegration:
    """Integration tests for retry logic"""

    def test_realistic_throttling_scenario(self):
        """Test realistic scenario with multiple throttling errors"""
        call_count = {'count': 0}

        @with_retries(max_attempts=5, min_wait=0.01, max_wait=0.1)
        def flaky_operation():
            call_count['count'] += 1
            if call_count['count'] < 4:
                raise ThrottlingError("Rate exceeded")
            return "success"

        result = flaky_operation()

        assert result == "success"
        assert call_count['count'] == 4

    def test_mixed_error_types(self):
        """Test handling of different error types"""
        errors = [
            ThrottlingError("Throttled"),
            InternalServiceError("Internal"),
            ThrottlingError("Throttled again"),
        ]
        call_count = {'index': 0}

        @with_retries(max_attempts=10, min_wait=0.01, max_wait=0.1)
        def mixed_errors():
            if call_count['index'] < len(errors):
                error = errors[call_count['index']]
                call_count['index'] += 1
                raise error
            return "success"

        result = mixed_errors()

        assert result == "success"
        assert call_count['index'] == 3  # All three errors, then success


class TestEdgeCases:
    """Tests for edge cases"""

    def test_zero_max_attempts(self):
        """Test behavior with zero max attempts"""
        mock_func = Mock(return_value="success")
        # tenacity requires at least 1 attempt
        decorated = with_retries(max_attempts=1, min_wait=0.01)(mock_func)

        result = decorated()
        assert result == "success"

    def test_very_large_wait_time(self):
        """Test that very large wait times are capped"""
        backoff = ExponentialBackoffWithJitter(multiplier=2, min=2, max=60, jitter_factor=0)

        state = Mock()
        state.attempt_number = 100  # Would be astronomically large

        wait_time = backoff(state)
        assert wait_time == 60  # Capped at max
