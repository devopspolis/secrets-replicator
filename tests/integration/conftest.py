"""
Pytest configuration and fixtures for integration tests.

Integration tests require:
- AWS credentials configured (AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)
- Permissions to create/delete secrets in Secrets Manager
- Permissions to create/delete S3 objects (for sedfile tests)
- Optional: Cross-account role for cross-account tests

To run integration tests:
    pytest tests/integration/ -v --integration

To skip integration tests (default):
    pytest tests/unit/ -v
"""

import os
import uuid
import json
import time
from typing import Dict, Any, Optional, List
import pytest
import boto3
from botocore.exceptions import ClientError


def pytest_addoption(parser):
    """Add custom command-line options for integration tests."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires AWS credentials)"
    )
    parser.addoption(
        "--aws-region",
        action="store",
        default="us-east-1",
        help="AWS region for integration tests"
    )
    parser.addoption(
        "--dest-region",
        action="store",
        default="us-west-2",
        help="Destination AWS region for cross-region tests"
    )


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires AWS)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (>5 seconds)"
    )
    config.addinivalue_line(
        "markers", "cross_region: mark test as cross-region (requires two regions)"
    )
    config.addinivalue_line(
        "markers", "cross_account: mark test as cross-account (requires second account)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration flag is provided."""
    if config.getoption("--integration"):
        # Running integration tests - verify AWS credentials
        try:
            sts = boto3.client("sts")
            sts.get_caller_identity()
        except Exception as e:
            pytest.exit(f"AWS credentials not configured: {e}")
        return

    # Skip integration tests
    skip_integration = pytest.mark.skip(reason="need --integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


class SecretHelper:
    """Helper class for managing test secrets."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.client = boto3.client("secretsmanager", region_name=region)
        self.created_secrets: List[str] = []

    def create_secret(
        self,
        name: Optional[str] = None,
        value: str = None,
        description: str = "Test secret for integration tests",
        kms_key_id: Optional[str] = None,
        tags: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Create a test secret.

        Returns:
            Dict with ARN, Name, and VersionId
        """
        if name is None:
            name = f"test-secret-{uuid.uuid4().hex[:8]}"

        if value is None:
            value = json.dumps({"test_key": "test_value", "created_at": time.time()})

        kwargs = {
            "Name": name,
            "Description": description,
            "SecretString": value,
        }

        if kms_key_id:
            kwargs["KmsKeyId"] = kms_key_id

        if tags:
            kwargs["Tags"] = tags

        try:
            response = self.client.create_secret(**kwargs)
            self.created_secrets.append(name)
            return {
                "ARN": response["ARN"],
                "Name": response["Name"],
                "VersionId": response["VersionId"],
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceExistsException":
                # Secret exists - update it instead
                response = self.client.put_secret_value(
                    SecretId=name,
                    SecretString=value
                )
                self.created_secrets.append(name)
                return {
                    "ARN": response["ARN"],
                    "Name": response["Name"],
                    "VersionId": response["VersionId"],
                }
            raise

    def get_secret(self, secret_id: str) -> Optional[Dict[str, Any]]:
        """Get secret value."""
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            return {
                "ARN": response["ARN"],
                "Name": response["Name"],
                "VersionId": response["VersionId"],
                "SecretString": response.get("SecretString"),
                "SecretBinary": response.get("SecretBinary"),
                "CreatedDate": response.get("CreatedDate"),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return None
            raise

    def update_secret(self, secret_id: str, value: str) -> Dict[str, Any]:
        """Update secret value."""
        response = self.client.put_secret_value(
            SecretId=secret_id,
            SecretString=value
        )
        return {
            "ARN": response["ARN"],
            "Name": response["Name"],
            "VersionId": response["VersionId"],
        }

    def delete_secret(self, secret_id: str, force: bool = True):
        """Delete secret (immediately if force=True)."""
        try:
            kwargs = {"SecretId": secret_id}
            if force:
                kwargs["ForceDeleteWithoutRecovery"] = True
            else:
                kwargs["RecoveryWindowInDays"] = 7

            self.client.delete_secret(**kwargs)
            if secret_id in self.created_secrets:
                self.created_secrets.remove(secret_id)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                # Ignore if secret doesn't exist
                raise

    def cleanup(self):
        """Delete all created secrets."""
        for secret_id in list(self.created_secrets):
            self.delete_secret(secret_id, force=True)
        self.created_secrets.clear()


class S3Helper:
    """Helper class for managing test S3 objects (sedfiles)."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.client = boto3.client("s3", region_name=region)
        self.created_objects: List[tuple] = []

    def upload_sedfile(
        self,
        bucket: str,
        key: str,
        content: str
    ):
        """Upload sedfile to S3."""
        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/plain"
        )
        self.created_objects.append((bucket, key))

    def cleanup(self):
        """Delete all created objects."""
        for bucket, key in list(self.created_objects):
            try:
                self.client.delete_object(Bucket=bucket, Key=key)
            except ClientError:
                # Ignore errors during cleanup
                pass
        self.created_objects.clear()


@pytest.fixture
def aws_region(request):
    """AWS region for tests."""
    return request.config.getoption("--aws-region")


@pytest.fixture
def dest_region(request):
    """Destination AWS region for cross-region tests."""
    return request.config.getoption("--dest-region")


@pytest.fixture
def account_id():
    """Get current AWS account ID."""
    sts = boto3.client("sts")
    return sts.get_caller_identity()["Account"]


@pytest.fixture
def secret_helper(aws_region):
    """Fixture for managing test secrets in source region."""
    helper = SecretHelper(region=aws_region)
    yield helper
    helper.cleanup()


@pytest.fixture
def dest_secret_helper(dest_region):
    """Fixture for managing test secrets in destination region."""
    helper = SecretHelper(region=dest_region)
    yield helper
    helper.cleanup()


@pytest.fixture
def s3_helper(aws_region):
    """Fixture for managing test S3 objects."""
    helper = S3Helper(region=aws_region)
    yield helper
    helper.cleanup()


@pytest.fixture
def lambda_client(aws_region):
    """Lambda client for invoking functions."""
    return boto3.client("lambda", region_name=aws_region)


@pytest.fixture
def eventbridge_client(aws_region):
    """EventBridge client for testing event triggers."""
    return boto3.client("events", region_name=aws_region)


@pytest.fixture
def cloudwatch_client(aws_region):
    """CloudWatch client for checking metrics."""
    return boto3.client("cloudwatch", region_name=aws_region)


@pytest.fixture
def sample_sedfile():
    """Sample sedfile content for testing."""
    return """# Test sedfile
s/dev/prod/g
s/test/production/g
s/us-east-1/us-west-2/g
"""


@pytest.fixture
def sample_json_mapping():
    """Sample JSON mapping for testing."""
    return {
        "transformations": [
            {
                "path": "$.environment",
                "find": "development",
                "replace": "production"
            },
            {
                "path": "$.region",
                "find": "us-east-1",
                "replace": "us-west-2"
            }
        ]
    }


def wait_for_secret(
    helper: SecretHelper,
    secret_id: str,
    max_wait: int = 30,
    interval: float = 1.0
) -> Optional[Dict[str, Any]]:
    """
    Wait for secret to exist (useful after async operations).

    Args:
        helper: SecretHelper instance
        secret_id: Secret ID to wait for
        max_wait: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        Secret data if found, None if timeout
    """
    start = time.time()
    while time.time() - start < max_wait:
        secret = helper.get_secret(secret_id)
        if secret:
            return secret
        time.sleep(interval)
    return None


def wait_for_secret_value(
    helper: SecretHelper,
    secret_id: str,
    expected_value: Optional[str] = None,
    max_wait: int = 30,
    interval: float = 1.0
) -> bool:
    """
    Wait for secret value to match expected value.

    Args:
        helper: SecretHelper instance
        secret_id: Secret ID to check
        expected_value: Expected secret value (None = any value)
        max_wait: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if value matches, False if timeout
    """
    start = time.time()
    while time.time() - start < max_wait:
        secret = helper.get_secret(secret_id)
        if secret:
            if expected_value is None:
                return True
            if secret.get("SecretString") == expected_value:
                return True
        time.sleep(interval)
    return False
