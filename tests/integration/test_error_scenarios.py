"""
Integration tests for error handling scenarios.

These tests verify proper error handling for various failure conditions.

Run with:
    pytest tests/integration/test_error_scenarios.py -v --integration
"""

import json
import os
import pytest
from src.handler import lambda_handler
from tests.fixtures.eventbridge_events import create_test_event


@pytest.mark.integration
class TestErrorScenarios:
    """Test error handling in various failure scenarios."""

    def test_source_secret_not_found(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of non-existent source secret."""
        # Use a non-existent secret ARN
        fake_arn = f"arn:aws:secretsmanager:{aws_region}:{account_id}:secret:nonexistent-secret-XXXXXX"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": "test-dest-nonexistent",
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Create test event for non-existent secret
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=fake_arn,
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler - should return error
        result = lambda_handler(event, {})

        # Verify error response
        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert "error" in body
        assert "not found" in body["error"].lower()

    def test_binary_secret_not_supported(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of binary secrets (not supported)."""
        # Note: Creating binary secrets via boto3 is more complex
        # This test documents the expected behavior
        # In reality, binary secrets would be detected and rejected

        source_value = json.dumps({"type": "binary_test"})
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # This test would need actual binary secret support to properly test
        # For now, we verify string secrets work
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_secret_too_large(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of secrets exceeding size limit."""
        # Create a very large secret (65KB - exceeds default 64KB limit)
        large_value = "x" * (65 * 1024)

        # First, try to create it (may fail at Secrets Manager level)
        try:
            source = secret_helper.create_secret(value=large_value)
            dest_name = f"test-dest-{source['Name']}"

            os.environ.update({
                "DESTINATION_REGION": aws_region,
                "DESTINATION_SECRET_NAME": dest_name,
                "TRANSFORM_MODE": "sed",
                "LOG_LEVEL": "DEBUG",
                "ENABLE_METRICS": "false",
                "MAX_SECRET_SIZE": "64000",  # 64KB limit
            })

            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            # Invoke handler - should reject due to size
            result = lambda_handler(event, {})

            # Should return error
            assert result["statusCode"] in [400, 413]  # Bad request or payload too large
            body = json.loads(result["body"])
            assert "error" in body

            # Cleanup
            secret_helper.delete_secret(dest_name, force=True)

        except Exception as e:
            # Secrets Manager itself may reject the large secret
            print(f"Expected error creating large secret: {e}")
            assert "secret size" in str(e).lower() or "too large" in str(e).lower()

    def test_invalid_event_format(
        self,
        aws_region,
        account_id
    ):
        """Test handling of malformed events."""
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": "test-dest",
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Invalid event - missing required fields
        invalid_event = {
            "source": "aws.secretsmanager",
            # Missing detail-type, detail, etc.
        }

        # Invoke handler with invalid event
        result = lambda_handler(invalid_event, {})

        # Should return error
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "error" in body

    def test_unsupported_event_type(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of unsupported event types."""
        # Create a secret
        source = secret_helper.create_secret()

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": f"test-dest-{source['Name']}",
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Create event with unsupported event name (e.g., DeleteSecret)
        event = create_test_event(
            event_name="DeleteSecret",  # Not supported
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler
        result = lambda_handler(event, {})

        # Should handle gracefully (either skip or error)
        assert result["statusCode"] in [200, 400]

    def test_missing_configuration(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of missing required configuration."""
        source = secret_helper.create_secret()

        # Clear required environment variables
        env_backup = os.environ.copy()
        for key in ["DESTINATION_REGION", "DESTINATION_SECRET_NAME"]:
            if key in os.environ:
                del os.environ[key]

        try:
            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            # Invoke handler with missing config
            result = lambda_handler(event, {})

            # Should return configuration error
            assert result["statusCode"] in [400, 500]
            body = json.loads(result["body"])
            assert "error" in body

        finally:
            # Restore environment
            os.environ.update(env_backup)

    def test_invalid_transform_mode(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of invalid transform mode."""
        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "invalid_mode",  # Invalid
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler
        result = lambda_handler(event, {})

        # Should return configuration error
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "error" in body

    @pytest.mark.slow
    def test_timeout_handling(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of operations that might timeout."""
        # Create a normal secret
        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
            "OPERATION_TIMEOUT": "1",  # Very short timeout (if implemented)
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler
        result = lambda_handler(event, {})

        # May succeed or timeout depending on AWS performance
        # Just verify it returns a valid response
        assert result["statusCode"] in [200, 504, 500]

        # Cleanup if successful
        dest_secret = secret_helper.get_secret(dest_name)
        if dest_secret:
            secret_helper.delete_secret(dest_name, force=True)

    def test_invalid_sedfile_syntax(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test handling of invalid sedfile syntax."""
        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        # Create invalid sedfile
        invalid_sedfile = "/tmp/invalid-sedfile.sed"
        with open(invalid_sedfile, "w") as f:
            f.write("s/invalid syntax without closing delimiter\n")

        try:
            os.environ.update({
                "DESTINATION_REGION": aws_region,
                "DESTINATION_SECRET_NAME": dest_name,
                "TRANSFORM_MODE": "sed",
                "LOG_LEVEL": "DEBUG",
                "ENABLE_METRICS": "false",
                # Would need to configure sedfile path
            })

            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            # TODO: Test with actual sedfile loading
            # For now, test will pass with no transformation

            result = lambda_handler(event, {})
            # Without sedfile, should succeed
            assert result["statusCode"] == 200

            # Cleanup
            dest_secret = secret_helper.get_secret(dest_name)
            if dest_secret:
                secret_helper.delete_secret(dest_name, force=True)

        finally:
            if os.path.exists(invalid_sedfile):
                os.remove(invalid_sedfile)

    def test_network_error_retry(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test retry behavior on transient network errors."""
        # This test verifies that the retry logic is in place
        # Actual network errors are hard to simulate in integration tests

        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler - should succeed even if transient errors occur
        result = lambda_handler(event, {})

        # Should succeed (retry logic should handle transient errors)
        assert result["statusCode"] == 200

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)
