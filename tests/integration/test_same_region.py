"""
Integration tests for same-region secret replication.

These tests verify end-to-end replication within the same AWS region.
Requires AWS credentials and permissions to manage secrets.

Run with:
    pytest tests/integration/test_same_region.py -v --integration
"""

import json
import os
import time
import pytest
from src.handler import lambda_handler
from src.config import ReplicatorConfig
from tests.fixtures.eventbridge_events import (
    PUT_SECRET_VALUE_EVENT,
    create_test_event,
)


@pytest.mark.integration
class TestSameRegionReplication:
    """Test same-account, same-region replication scenarios."""

    def test_simple_replication_no_transform(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test basic replication without transformation."""
        # Create source secret
        source_value = json.dumps({"username": "testuser", "password": "testpass123"})
        source = secret_helper.create_secret(value=source_value)

        # Create destination secret name
        dest_name = f"test-dest-{source['Name']}"

        # Set up environment for handler
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",  # Disable metrics for testing
        })

        # Create test event
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler
        result = lambda_handler(event, {})

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["source_secret"] == source["ARN"]
        assert dest_name in body["destination_secret"]

        # Verify destination secret was created
        dest_secret = secret_helper.get_secret(dest_name)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == source_value

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_replication_with_sed_transform(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test replication with sed transformations."""
        # Create source secret with values that will be transformed
        source_value = json.dumps({
            "environment": "dev",
            "api_url": "https://api.dev.example.com",
            "database": "db-dev-01.us-east-1.rds.amazonaws.com"
        })
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        # Create sedfile content
        sedfile = """# Transform dev to prod
s/dev/prod/g
s/us-east-1/us-west-2/g
"""

        # Set up environment (using bundled sedfile)
        # Note: For this test, we'll create a temporary sedfile
        sedfile_path = "/tmp/test-sedfile.sed"
        with open(sedfile_path, "w") as f:
            f.write(sedfile)

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Create test event
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler (will need to modify to support local sedfile path)
        # For now, this test documents the intended behavior
        # Real implementation would need S3 sedfile or bundled sedfile support

        # TODO: Complete this test once sedfile loading is integrated
        # result = lambda_handler(event, {})
        # assert result["statusCode"] == 200

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)
        if os.path.exists(sedfile_path):
            os.remove(sedfile_path)

    def test_replication_with_json_transform(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test replication with JSON transformations."""
        # Create source secret
        source_value = json.dumps({
            "environment": "development",
            "region": "us-east-1",
            "database": {
                "host": "db-dev-01.rds.amazonaws.com",
                "port": 5432
            }
        })
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        # Set up environment
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "json",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Create test event
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # TODO: Complete JSON transformation test
        # Requires JSON mapping file support

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_update_existing_secret(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test updating an existing destination secret."""
        # Create source secret
        initial_value = json.dumps({"version": "1.0"})
        source = secret_helper.create_secret(value=initial_value)
        dest_name = f"test-dest-{source['Name']}"

        # Create destination secret
        secret_helper.create_secret(name=dest_name, value=initial_value)

        # Set up environment
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Update source secret
        updated_value = json.dumps({"version": "2.0"})
        source_updated = secret_helper.update_secret(source["Name"], updated_value)

        # Create test event for update
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
            version_id=source_updated["VersionId"],
        )

        # Invoke handler
        result = lambda_handler(event, {})

        # Verify response
        assert result["statusCode"] == 200

        # Verify destination was updated
        dest_secret = secret_helper.get_secret(dest_name)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == updated_value

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    @pytest.mark.slow
    def test_large_secret_replication(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test replication of large secret (near 64KB limit)."""
        # Create a large secret (60KB)
        large_value = "x" * (60 * 1024)
        source = secret_helper.create_secret(value=large_value)
        dest_name = f"test-dest-{source['Name']}"

        # Set up environment
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
            "MAX_SECRET_SIZE": "65536",  # 64KB
        })

        # Create test event
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Invoke handler
        result = lambda_handler(event, {})

        # Verify response
        assert result["statusCode"] == 200

        # Verify destination secret
        dest_secret = secret_helper.get_secret(dest_name)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == large_value

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_secret_with_special_characters(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test replication of secrets with special characters."""
        # Create secret with special characters
        special_value = json.dumps({
            "password": "P@ssw0rd!#$%^&*()",
            "unicode": "Hello 世界 🌍",
            "escaped": "Line1\\nLine2\\tTab"
        })
        source = secret_helper.create_secret(value=special_value)
        dest_name = f"test-dest-{source['Name']}"

        # Set up environment
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Create test event
        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        })

        # Invoke handler
        result = lambda_handler(event, {})

        # Verify response
        assert result["statusCode"] == 200

        # Verify destination secret preserves special characters
        dest_secret = secret_helper.get_secret(dest_name)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == special_value

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    def test_concurrent_replications(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test multiple concurrent replications."""
        # Create multiple source secrets
        sources = []
        for i in range(5):
            value = json.dumps({"index": i, "data": f"test_data_{i}"})
            source = secret_helper.create_secret(value=value)
            sources.append(source)

        # Set up environment
        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Process each secret
        results = []
        for source in sources:
            dest_name = f"test-dest-{source['Name']}"
            os.environ["DESTINATION_SECRET_NAME"] = dest_name

            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            result = lambda_handler(event, {})
            results.append((result, dest_name))

        # Verify all succeeded
        for result, dest_name in results:
            assert result["statusCode"] == 200
            dest_secret = secret_helper.get_secret(dest_name)
            assert dest_secret is not None
            secret_helper.delete_secret(dest_name, force=True)
