"""
Unit tests for aws_clients module
"""

import pytest
import boto3
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError
from aws_clients import SecretsManagerClient, SecretValue, create_secrets_manager_client
from exceptions import (
    AWSClientError,
    SecretNotFoundError,
    AccessDeniedError,
    InvalidRequestError,
    ThrottlingError,
    InternalServiceError,
)


class TestSecretsManagerClient:
    """Tests for SecretsManagerClient class"""

    def test_init_without_role(self):
        """Test client initialization without role assumption"""
        client = SecretsManagerClient(region="us-east-1")

        assert client.region == "us-east-1"
        assert client.role_arn is None
        assert client._client is not None

    def test_init_with_role(self):
        """Test client initialization with role assumption"""
        # Mock STS assume_role
        with patch("boto3.client") as mock_boto_client:
            mock_sts = MagicMock()
            mock_sm = MagicMock()

            # Configure mock to return different clients
            def client_factory(service, **kwargs):
                if service == "sts":
                    return mock_sts
                elif service == "secretsmanager":
                    return mock_sm

            mock_boto_client.side_effect = client_factory

            # Mock assume_role response
            mock_sts.assume_role.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "FwoGZXIvYXdzEBYaDJUaEXAMPLE",
                    "Expiration": "2024-01-01T00:00:00Z",
                }
            }

            client = SecretsManagerClient(
                region="us-west-2", role_arn="arn:aws:iam::123456789012:role/TestRole"
            )

            # Verify assume_role was called
            mock_sts.assume_role.assert_called_once()
            assert client.role_arn == "arn:aws:iam::123456789012:role/TestRole"

    def test_get_secret_string_success(self):
        """Test retrieving a string secret successfully"""
        # Create mock secret
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(
            Name="test-secret", SecretString='{"username":"admin","password":"secret123"}'
        )

        # Get secret using our client
        client = SecretsManagerClient(region="us-east-1")
        secret = client.get_secret("test-secret")

        assert isinstance(secret, SecretValue)
        assert secret.secret_string == '{"username":"admin","password":"secret123"}'
        assert secret.secret_binary is None
        assert secret.name == "test-secret"
        assert secret.arn is not None
        assert secret.version_id is not None
        assert "AWSCURRENT" in secret.version_stages

    def test_get_secret_with_version_id(self):
        """Test retrieving a specific version of a secret"""
        # Create mock secret
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        response = sm_client.create_secret(Name="versioned-secret", SecretString="value1")
        version_id = response["VersionId"]

        # Get secret with version ID
        client = SecretsManagerClient(region="us-east-1")
        secret = client.get_secret("versioned-secret", version_id=version_id)

        assert secret.secret_string == "value1"
        assert secret.version_id == version_id

    def test_get_secret_not_found(self):
        """Test getting a non-existent secret raises SecretNotFoundError"""
        client = SecretsManagerClient(region="us-east-1")

        with pytest.raises(SecretNotFoundError, match="failed"):
            client.get_secret("non-existent-secret")

    def test_put_secret_creates_new(self):
        """Test creating a new secret"""
        client = SecretsManagerClient(region="us-east-1")

        response = client.put_secret(
            secret_id="new-secret", secret_value='{"key":"value"}', description="Test secret"
        )

        assert response["Name"] == "new-secret"
        assert response["ARN"] is not None
        assert response["VersionId"] is not None

        # Verify secret was created
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        result = sm_client.get_secret_value(SecretId="new-secret")
        assert result["SecretString"] == '{"key":"value"}'

    def test_put_secret_updates_existing(self):
        """Test updating an existing secret"""
        # Create initial secret
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(Name="existing-secret", SecretString="old-value")

        # Update using our client
        client = SecretsManagerClient(region="us-east-1")
        response = client.put_secret(secret_id="existing-secret", secret_value="new-value")

        assert response["Name"] == "existing-secret"

        # Verify secret was updated
        result = sm_client.get_secret_value(SecretId="existing-secret")
        assert result["SecretString"] == "new-value"

    def test_put_secret_with_kms_key(self):
        """Test creating secret with KMS encryption"""
        client = SecretsManagerClient(region="us-east-1")

        response = client.put_secret(
            secret_id="encrypted-secret",
            secret_value="sensitive-data",
            kms_key_id="arn:aws:kms:us-east-1:123456789012:key/abc123",
        )

        assert response["Name"] == "encrypted-secret"

    def test_put_secret_with_tags(self):
        """Test creating secret with tags"""
        client = SecretsManagerClient(region="us-east-1")

        tags = {"Environment": "test", "Application": "secrets-replicator"}

        response = client.put_secret(secret_id="tagged-secret", secret_value="data", tags=tags)

        assert response["Name"] == "tagged-secret"

        # Verify tags were applied
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        result = sm_client.describe_secret(SecretId="tagged-secret")
        tag_dict = {tag["Key"]: tag["Value"] for tag in result.get("Tags", [])}
        assert tag_dict["Environment"] == "test"
        assert tag_dict["Application"] == "secrets-replicator"

    def test_secret_exists_true(self):
        """Test secret_exists returns True for existing secret"""
        # Create secret
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(Name="exists-secret", SecretString="value")

        # Check existence
        client = SecretsManagerClient(region="us-east-1")
        assert client.secret_exists("exists-secret") is True

    def test_secret_exists_false(self):
        """Test secret_exists returns False for non-existent secret"""
        client = SecretsManagerClient(region="us-east-1")
        assert client.secret_exists("non-existent") is False

    def test_get_secret_description_with_description(self):
        """Test get_secret_description returns description when set"""
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(
            Name="secret-with-desc", SecretString="value", Description="Test description for secret"
        )

        client = SecretsManagerClient(region="us-east-1")
        description = client.get_secret_description("secret-with-desc")

        assert description == "Test description for secret"

    def test_get_secret_description_without_description(self):
        """Test get_secret_description returns None when no description set"""
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(Name="secret-no-desc", SecretString="value")

        client = SecretsManagerClient(region="us-east-1")
        description = client.get_secret_description("secret-no-desc")

        assert description is None

    def test_get_secret_description_not_found(self):
        """Test get_secret_description raises error for non-existent secret"""
        client = SecretsManagerClient(region="us-east-1")

        with pytest.raises(SecretNotFoundError):
            client.get_secret_description("non-existent-secret")

    def test_put_secret_updates_description_on_existing(self):
        """Test put_secret updates description when secret already exists"""
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(
            Name="secret-to-update",
            SecretString="original-value",
            Description="Original description",
        )

        client = SecretsManagerClient(region="us-east-1")
        client.put_secret(
            secret_id="secret-to-update",
            secret_value="new-value",
            description="Updated description",
        )

        # Verify description was updated
        result = sm_client.describe_secret(SecretId="secret-to-update")
        assert result["Description"] == "Updated description"

    def test_put_secret_preserves_none_description(self):
        """Test put_secret does not update description when None is passed"""
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(
            Name="secret-keep-desc",
            SecretString="original-value",
            Description="Should remain unchanged",
        )

        client = SecretsManagerClient(region="us-east-1")
        client.put_secret(secret_id="secret-keep-desc", secret_value="new-value", description=None)

        # Verify description was NOT updated
        result = sm_client.describe_secret(SecretId="secret-keep-desc")
        assert result["Description"] == "Should remain unchanged"

    def test_handle_client_error_access_denied(self):
        """Test that AccessDenied errors are properly mapped"""
        client = SecretsManagerClient(region="us-east-1")

        # Mock a client error
        error_response = {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}
        client_error = ClientError(error_response, "GetSecretValue")

        with pytest.raises(AccessDeniedError, match="Access denied"):
            client._handle_client_error(client_error, "test_operation")

    def test_handle_client_error_invalid_request(self):
        """Test that InvalidRequest errors are properly mapped"""
        client = SecretsManagerClient(region="us-east-1")

        error_response = {
            "Error": {"Code": "InvalidRequestException", "Message": "Invalid request"}
        }
        client_error = ClientError(error_response, "GetSecretValue")

        with pytest.raises(InvalidRequestError, match="Invalid request"):
            client._handle_client_error(client_error, "test_operation")

    def test_handle_client_error_throttling(self):
        """Test that Throttling errors are properly mapped"""
        client = SecretsManagerClient(region="us-east-1")

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        client_error = ClientError(error_response, "GetSecretValue")

        with pytest.raises(ThrottlingError, match="Rate exceeded"):
            client._handle_client_error(client_error, "test_operation")

    def test_handle_client_error_internal_service(self):
        """Test that InternalService errors are properly mapped"""
        client = SecretsManagerClient(region="us-east-1")

        error_response = {"Error": {"Code": "InternalServiceError", "Message": "Internal error"}}
        client_error = ClientError(error_response, "GetSecretValue")

        with pytest.raises(InternalServiceError, match="Internal error"):
            client._handle_client_error(client_error, "test_operation")

    def test_handle_client_error_unknown(self):
        """Test that unknown errors are mapped to base AWSClientError"""
        client = SecretsManagerClient(region="us-east-1")

        error_response = {"Error": {"Code": "UnknownException", "Message": "Unknown error"}}
        client_error = ClientError(error_response, "GetSecretValue")

        with pytest.raises(AWSClientError, match="Unknown error"):
            client._handle_client_error(client_error, "test_operation")


class TestSecretValue:
    """Tests for SecretValue dataclass"""

    def test_secret_value_creation(self):
        """Test creating SecretValue object"""
        secret = SecretValue(
            secret_string="test-value",
            arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            name="test-secret",
            version_id="abc123",
            version_stages=["AWSCURRENT"],
        )

        assert secret.secret_string == "test-value"
        assert secret.secret_binary is None
        assert secret.arn == "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        assert secret.name == "test-secret"
        assert secret.version_id == "abc123"
        assert "AWSCURRENT" in secret.version_stages

    def test_secret_value_binary(self):
        """Test SecretValue with binary data"""
        binary_data = b"\x00\x01\x02\x03"
        secret = SecretValue(secret_binary=binary_data)

        assert secret.secret_binary == binary_data
        assert secret.secret_string is None


class TestFactoryFunction:
    """Tests for create_secrets_manager_client factory function"""

    def test_create_client_basic(self):
        """Test creating client with factory function"""
        client = create_secrets_manager_client(region="us-east-1")

        assert isinstance(client, SecretsManagerClient)
        assert client.region == "us-east-1"
        assert client.role_arn is None

    def test_create_client_with_role(self):
        """Test creating client with role ARN"""
        with patch("boto3.client") as mock_boto_client:
            mock_sts = MagicMock()
            mock_sm = MagicMock()

            def client_factory(service, **kwargs):
                if service == "sts":
                    return mock_sts
                elif service == "secretsmanager":
                    return mock_sm

            mock_boto_client.side_effect = client_factory

            mock_sts.assume_role.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "token",
                    "Expiration": "2024-01-01T00:00:00Z",
                }
            }

            client = create_secrets_manager_client(
                region="us-west-2",
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                external_id="test-external-id",
            )

            assert isinstance(client, SecretsManagerClient)
            assert client.region == "us-west-2"
            assert client.role_arn == "arn:aws:iam::123456789012:role/TestRole"
            assert client.external_id == "test-external-id"


class TestCrossAccountScenarios:
    """Tests for cross-account secret operations"""

    def test_assume_role_with_external_id(self):
        """Test role assumption with external ID"""
        with patch("boto3.client") as mock_boto_client:
            mock_sts = MagicMock()
            mock_sm = MagicMock()

            def client_factory(service, **kwargs):
                if service == "sts":
                    return mock_sts
                elif service == "secretsmanager":
                    return mock_sm

            mock_boto_client.side_effect = client_factory

            mock_sts.assume_role.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "token",
                    "Expiration": "2024-01-01T00:00:00Z",
                }
            }

            client = SecretsManagerClient(
                region="us-west-2",
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                external_id="my-external-id",
            )

            # Verify assume_role was called with external ID
            call_args = mock_sts.assume_role.call_args[1]
            assert call_args["ExternalId"] == "my-external-id"

    def test_assume_role_failure(self):
        """Test handling of role assumption failure"""
        with patch("boto3.client") as mock_boto_client:
            mock_sts = MagicMock()
            mock_boto_client.return_value = mock_sts

            # Mock access denied error
            error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
            mock_sts.assume_role.side_effect = ClientError(error_response, "AssumeRole")

            with pytest.raises(AccessDeniedError, match="Failed to assume role"):
                SecretsManagerClient(
                    region="us-west-2", role_arn="arn:aws:iam::123456789012:role/TestRole"
                )


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_get_secret_with_version_stage(self):
        """Test retrieving secret with specific version stage"""
        # Create secret and update it to have multiple versions
        sm_client = boto3.client("secretsmanager", region_name="us-east-1")
        sm_client.create_secret(Name="staged-secret", SecretString="v1")
        sm_client.put_secret_value(SecretId="staged-secret", SecretString="v2")

        # Get current version
        client = SecretsManagerClient(region="us-east-1")
        secret = client.get_secret("staged-secret", version_stage="AWSCURRENT")

        assert secret.secret_string == "v2"
        assert "AWSCURRENT" in secret.version_stages

    def test_put_secret_large_value(self):
        """Test creating secret with large value"""
        client = SecretsManagerClient(region="us-east-1")

        # Create a large secret (but under 64KB limit)
        large_value = "x" * (64 * 1024 - 100)  # Just under 64KB

        response = client.put_secret(secret_id="large-secret", secret_value=large_value)

        assert response["Name"] == "large-secret"

    def test_custom_session_name(self):
        """Test using custom session name for role assumption"""
        with patch("boto3.client") as mock_boto_client:
            mock_sts = MagicMock()
            mock_sm = MagicMock()

            def client_factory(service, **kwargs):
                if service == "sts":
                    return mock_sts
                elif service == "secretsmanager":
                    return mock_sm

            mock_boto_client.side_effect = client_factory

            mock_sts.assume_role.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "key",
                    "SessionToken": "token",
                    "Expiration": "2024-01-01T00:00:00Z",
                }
            }

            client = SecretsManagerClient(
                region="us-west-2",
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                session_name="custom-session",
            )

            # Verify session name was used
            call_args = mock_sts.assume_role.call_args[1]
            assert call_args["RoleSessionName"] == "custom-session"
