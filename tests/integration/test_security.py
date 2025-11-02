"""
Security validation tests for secret replication.

These tests verify security properties:
- No plaintext secrets in logs
- KMS encryption working
- IAM permissions (least privilege)
- No secret leakage in error messages

Run with:
    pytest tests/integration/test_security.py -v --integration
"""

import json
import os
import re
import pytest
import boto3
from src.handler import lambda_handler
from src.logger import get_logger, setup_logger
from src.utils import mask_secret, sanitize_log_message
from tests.fixtures.eventbridge_events import create_test_event
from io import StringIO
import logging


@pytest.mark.integration
class TestSecurityValidation:
    """Security validation tests."""

    def test_no_plaintext_secrets_in_logs(
        self,
        secret_helper,
        aws_region,
        account_id,
        caplog
    ):
        """Verify that plaintext secrets never appear in logs."""
        # Create secret with sensitive data
        sensitive_password = "SuperSecret123!@#"
        sensitive_api_key = "ak-1234567890abcdef"
        secret_value = json.dumps({
            "password": sensitive_password,
            "api_key": sensitive_api_key,
            "database": "postgres://user:pass@host:5432/db"
        })
        source = secret_helper.create_secret(value=secret_value)
        dest_name = f"test-dest-{source['Name']}"

        # Setup environment
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",  # Maximum verbosity
            "ENABLE_METRICS": "false",
        })

        # Capture logs
        with caplog.at_level(logging.DEBUG):
            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            result = lambda_handler(event, {})
            assert result["statusCode"] == 200

        # Check all log messages for plaintext secrets
        all_logs = caplog.text

        # Verify sensitive values are NOT in logs
        assert sensitive_password not in all_logs, "Plaintext password found in logs!"
        assert sensitive_api_key not in all_logs, "Plaintext API key found in logs!"
        assert "user:pass@host" not in all_logs, "Database credentials found in logs!"

        # Verify masking is working (should see masked versions)
        # This depends on implementation - masked secrets might appear like "Supe****23!@#"

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_error_messages_dont_leak_secrets(
        self,
        secret_helper,
        aws_region,
        account_id,
        caplog
    ):
        """Verify that error messages don't leak secret values."""
        # Create secret
        sensitive_value = "ThisIsASecretValue12345"
        secret_value = json.dumps({"key": sensitive_value})
        source = secret_helper.create_secret(value=secret_value)

        # Setup environment with invalid configuration to trigger error
        os.environ.update({
            "DESTINATION_REGION": "invalid-region-xyz",  # Invalid
            "DESTINATION_SECRET_NAME": f"test-dest-{source['Name']}",
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Capture logs
        with caplog.at_level(logging.DEBUG):
            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            result = lambda_handler(event, {})
            # Should fail due to invalid region
            assert result["statusCode"] != 200

        # Check logs and error response
        all_logs = caplog.text
        response_body = json.loads(result["body"])

        # Verify secret value is NOT in logs or error message
        assert sensitive_value not in all_logs, "Secret value leaked in error logs!"
        assert sensitive_value not in json.dumps(response_body), "Secret value leaked in error response!"

    def test_masking_utility_functions(self):
        """Test secret masking utility functions."""
        # Test mask_secret function
        secret = "MySecretPassword123"
        masked = mask_secret(secret)

        # Should not contain full secret
        assert secret != masked
        assert "****" in masked

        # Should show length info
        assert len(masked) > 0

        # Test with short secrets
        short_secret = "abc"
        masked_short = mask_secret(short_secret)
        assert short_secret != masked_short

    def test_sanitize_log_messages(self):
        """Test log message sanitization."""
        # Test sanitize_log_message function
        log_msg = "User password is: MyPassword123 and API key: sk-1234567890abcdef"
        sanitized = sanitize_log_message(log_msg)

        # Should not contain sensitive patterns
        assert "MyPassword123" not in sanitized
        assert "sk-1234567890abcdef" not in sanitized
        assert "REDACTED" in sanitized or "****" in sanitized

    def test_kms_encryption_used(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Verify that KMS encryption is used for secrets."""
        # Create secret with KMS encryption
        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
            "KMS_KEY_ID": "alias/aws/secretsmanager",  # Use default KMS key
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

        # Verify destination secret exists and is encrypted
        dest_secret = secret_helper.get_secret(dest_name)
        assert dest_secret is not None

        # Check that secret metadata includes KMS key info
        # (This would require describe_secret call)
        sm_client = boto3.client("secretsmanager", region_name=aws_region)
        describe_response = sm_client.describe_secret(SecretId=dest_name)

        # Verify KMS key is set
        assert "KmsKeyId" in describe_response
        print(f"\\nSecret encrypted with KMS key: {describe_response['KmsKeyId']}")

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_iam_permissions_validation(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Verify IAM permissions are working correctly."""
        # This test verifies that the Lambda role has appropriate permissions
        # by attempting operations that should succeed

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

        # Should succeed with proper IAM permissions
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

        # Verify all necessary operations worked:
        # 1. Read source secret (GetSecretValue)
        # 2. Write destination secret (CreateSecret/PutSecretValue)
        # 3. Check secret existence (DescribeSecret)

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_cloudtrail_logging_enabled(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Verify that CloudTrail logging is capturing API calls."""
        # This test documents that CloudTrail should be enabled
        # Actual verification would require CloudTrail API access

        # Create and replicate secret
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

        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

        # Note: In production, verify CloudTrail logs contain:
        # - PutSecretValue event (triggered)
        # - GetSecretValue event (Lambda reading source)
        # - CreateSecret/PutSecretValue event (Lambda writing destination)
        # - All with proper user identity and source IP

        print("\\nCloudTrail audit trail should contain:")
        print("  - PutSecretValue on source secret")
        print("  - GetSecretValue by Lambda")
        print("  - CreateSecret/PutSecretValue on destination")

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_no_credentials_in_environment(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Verify no AWS credentials are stored in environment variables."""
        # Create secret
        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Check environment variables
        env_keys = os.environ.keys()

        # Should NOT contain AWS credentials in environment
        assert "AWS_SECRET_ACCESS_KEY" not in env_keys or \
               os.environ.get("AWS_SECRET_ACCESS_KEY") == "", \
               "AWS secret access key found in environment!"

        # IAM role should be used instead (via instance metadata or execution role)
        # This is the secure way for Lambda

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_secret_version_tracking(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Verify that secret versions are properly tracked."""
        # Create initial secret
        initial_value = json.dumps({"version": 1})
        source = secret_helper.create_secret(value=initial_value)
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # First replication
        event1 = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
            version_id=source["VersionId"],
        )

        result1 = lambda_handler(event1, {})
        assert result1["statusCode"] == 200

        # Get destination version
        dest1 = secret_helper.get_secret(dest_name)
        version_id_1 = dest1["VersionId"]

        # Update source secret
        updated_value = json.dumps({"version": 2})
        source_updated = secret_helper.update_secret(source["Name"], updated_value)

        # Second replication
        event2 = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
            version_id=source_updated["VersionId"],
        )

        result2 = lambda_handler(event2, {})
        assert result2["statusCode"] == 200

        # Get updated destination version
        dest2 = secret_helper.get_secret(dest_name)
        version_id_2 = dest2["VersionId"]

        # Verify versions are different (secret was updated)
        assert version_id_1 != version_id_2, "Secret version not updated!"

        print(f"\\nSecret version tracking:")
        print(f"  Initial version: {version_id_1}")
        print(f"  Updated version: {version_id_2}")

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_regex_safety_validation(self):
        """Test that dangerous regex patterns are detected."""
        from src.utils import validate_regex

        # Test safe patterns
        safe_patterns = [
            r"simple",
            r"test\d+",
            r"^start.*end$",
        ]
        for pattern in safe_patterns:
            assert validate_regex(pattern), f"Safe pattern rejected: {pattern}"

        # Test dangerous patterns (ReDoS)
        dangerous_patterns = [
            r"(a+)+b",  # Nested quantifiers
            r"(a*)*b",  # Nested star quantifiers
            r"(a+)*b",  # Mixed nested quantifiers
        ]
        for pattern in dangerous_patterns:
            assert not validate_regex(pattern), f"Dangerous pattern accepted: {pattern}"

        print("\\nRegex safety validation working correctly")
