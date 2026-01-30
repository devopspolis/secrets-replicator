"""
Pytest fixtures for unit tests.

Provides moto AWS mocking for all unit tests.
"""

import json
import pytest
import boto3
from moto import mock_aws


@pytest.fixture(autouse=True)
def aws_mock():
    """
    Automatically mock all AWS services for every unit test.

    This fixture uses autouse=True to automatically apply mocking to all tests
    in the tests/unit directory without requiring explicit fixture usage.
    """
    with mock_aws():
        # Create default configuration secrets that handler tests expect
        _setup_default_secrets()
        yield


def _setup_default_secrets():
    """
    Set up default secrets in moto for handler tests.

    Creates the configuration secrets that the handler expects to find:
    - secrets-replicator/config/destinations: Destination configuration
    - secrets-replicator/filters/default: Default filter mapping
    - secrets-replicator/transformations/region-swap: Default transformation
    """
    sm = boto3.client("secretsmanager", region_name="us-east-1")

    # Default destinations configuration
    destinations_config = json.dumps(
        [{"region": "us-west-2", "filters": "secrets-replicator/filters/default"}]
    )
    sm.create_secret(
        Name="secrets-replicator/config/destinations", SecretString=destinations_config
    )

    # Default filters
    filters_config = json.dumps({"*": "region-swap"})  # Apply region-swap to all secrets
    sm.create_secret(Name="secrets-replicator/filters/default", SecretString=filters_config)

    # Default transformation
    sm.create_secret(
        Name="secrets-replicator/transformations/region-swap",
        SecretString="s/us-east-1/us-west-2/g",
    )
