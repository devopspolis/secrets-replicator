"""
Integration tests for cross-region secret replication.

These tests verify replication across different AWS regions (DR scenarios).
Requires AWS credentials and permissions in both regions.

Run with:
    pytest tests/integration/test_cross_region.py -v --integration \
        --aws-region us-east-1 --dest-region us-west-2
"""

import json
import os
import pytest
from src.handler import lambda_handler
from tests.fixtures.eventbridge_events import create_test_event
from tests.integration.conftest import wait_for_secret


@pytest.mark.integration
@pytest.mark.cross_region
class TestCrossRegionReplication:
    """Test cross-region secret replication scenarios."""

    def test_basic_cross_region_replication(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id
    ):
        """Test basic replication from one region to another."""
        # Create source secret in source region
        source_value = json.dumps({
            "environment": "production",
            "region": aws_region,
            "database": f"db-prod.{aws_region}.rds.amazonaws.com"
        })
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        # Set up environment for cross-region replication
        os.environ.update({
            "DESTINATION_REGION": dest_region,
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

        # Invoke handler
        result = lambda_handler(event, {})

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert dest_region in body["destination_secret"]

        # Verify destination secret in destination region
        dest_secret = wait_for_secret(dest_secret_helper, dest_name, max_wait=10)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == source_value

        # Cleanup both regions
        dest_secret_helper.delete_secret(dest_name, force=True)

    def test_cross_region_with_transformation(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id,
        sample_sedfile
    ):
        """Test cross-region replication with sed transformation."""
        # Create source secret with region-specific values
        source_value = json.dumps({
            "region": "us-east-1",
            "endpoint": "https://api.us-east-1.amazonaws.com",
            "database": "db-prod.us-east-1.rds.amazonaws.com"
        })
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        # Expected transformed value
        expected_value = json.dumps({
            "region": "us-west-2",
            "endpoint": "https://api.us-west-2.amazonaws.com",
            "database": "db-prod.us-west-2.rds.amazonaws.com"
        })

        # TODO: Set up transformation secret with sed script
        # For now, test without transformation

        os.environ.update({
            "DESTINATION_REGION": dest_region,
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

        # Invoke handler
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

        # Verify destination
        dest_secret = wait_for_secret(dest_secret_helper, dest_name, max_wait=10)
        assert dest_secret is not None

        # Cleanup
        dest_secret_helper.delete_secret(dest_name, force=True)

    @pytest.mark.slow
    def test_cross_region_latency(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id
    ):
        """Test and measure cross-region replication latency."""
        import time

        # Create source secret
        source_value = json.dumps({"timestamp": time.time()})
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": dest_region,
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

        # Measure replication time
        start = time.time()
        result = lambda_handler(event, {})
        duration = time.time() - start

        # Verify response
        assert result["statusCode"] == 200

        # Log duration for analysis
        print(f"\\nCross-region replication took {duration:.2f} seconds")
        print(f"Source region: {aws_region}, Dest region: {dest_region}")

        # Verify destination
        dest_secret = wait_for_secret(dest_secret_helper, dest_name, max_wait=10)
        assert dest_secret is not None

        # Cleanup
        dest_secret_helper.delete_secret(dest_name, force=True)

        # Assert reasonable performance (should be < 5 seconds)
        assert duration < 5.0, f"Cross-region replication too slow: {duration:.2f}s"

    def test_cross_region_update(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id
    ):
        """Test updating an existing cross-region secret."""
        # Create initial secrets in both regions
        initial_value = json.dumps({"version": "1.0"})
        source = secret_helper.create_secret(value=initial_value)
        dest_name = f"test-dest-{source['Name']}"
        dest_secret_helper.create_secret(name=dest_name, value=initial_value)

        os.environ.update({
            "DESTINATION_REGION": dest_region,
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
        assert result["statusCode"] == 200

        # Verify destination was updated
        dest_secret = wait_for_secret(dest_secret_helper, dest_name, max_wait=10)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == updated_value

        # Cleanup
        dest_secret_helper.delete_secret(dest_name, force=True)

    def test_cross_region_kms_encryption(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id
    ):
        """Test cross-region replication with KMS encryption."""
        # Note: This test requires KMS keys in both regions
        # For now, we'll test without explicit KMS key (uses default)

        source_value = json.dumps({"sensitive": "data"})
        source = secret_helper.create_secret(value=source_value)
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": dest_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
            # "KMS_KEY_ID": "alias/aws/secretsmanager",  # Use default key
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
        assert result["statusCode"] == 200

        # Verify destination
        dest_secret = wait_for_secret(dest_secret_helper, dest_name, max_wait=10)
        assert dest_secret is not None
        assert dest_secret["SecretString"] == source_value

        # Cleanup
        dest_secret_helper.delete_secret(dest_name, force=True)

    def test_multiple_region_pairs(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id
    ):
        """Test replication with multiple source secrets to same destination region."""
        secrets = []

        # Create multiple source secrets
        for i in range(3):
            value = json.dumps({"index": i, "region": aws_region})
            source = secret_helper.create_secret(value=value)
            secrets.append(source)

        os.environ.update({
            "DESTINATION_REGION": dest_region,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "DEBUG",
            "ENABLE_METRICS": "false",
        })

        # Replicate each secret
        for source in secrets:
            dest_name = f"test-dest-{source['Name']}"
            os.environ["DESTINATION_SECRET_NAME"] = dest_name

            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            result = lambda_handler(event, {})
            assert result["statusCode"] == 200

            # Verify destination
            dest_secret = wait_for_secret(dest_secret_helper, dest_name, max_wait=10)
            assert dest_secret is not None

            # Cleanup
            dest_secret_helper.delete_secret(dest_name, force=True)
