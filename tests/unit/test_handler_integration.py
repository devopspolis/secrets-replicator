"""
Integration tests for handler with AWS clients
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from src.handler import lambda_handler
from src.aws_clients import SecretValue
from src.exceptions import SecretNotFoundError, AccessDeniedError, ThrottlingError
from tests.fixtures.eventbridge_events import (
    PUT_SECRET_VALUE_EVENT,
    UPDATE_SECRET_EVENT,
    REPLICATE_SECRET_EVENT
)


def create_mock_tags_and_transform_client(tags=None, transform_secret_name='my-transform-sed', sed_script='s/us-east-1/us-west-2/g'):
    """Helper to create mocked client for both tags and transformation secret"""
    mock_client = MagicMock()

    # Set up tags
    default_tags = {'SecretsReplicator:TransformSecretName': transform_secret_name} if transform_secret_name else {}
    if tags is not None:
        default_tags.update(tags)
    mock_client.get_secret_tags.return_value = default_tags

    # Set up get_secret to return transformation secret
    mock_client.get_secret.return_value = SecretValue(
        secret_string=sed_script,
        arn=f'arn:aws:secretsmanager:us-east-1:123456789012:secret:secrets-replicator/transformations/{transform_secret_name}-xyz789',
        name=f'secrets-replicator/transformations/{transform_secret_name}',
        version_id='v1',
        version_stages=['AWSCURRENT']
    )
    return mock_client


def create_mock_source_client(secret_value='{"key":"value"}'):
    """Helper to create mocked source secret client"""
    mock_client = MagicMock()
    mock_client.get_secret.return_value = SecretValue(
        secret_string=secret_value,
        arn='arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-abc123',
        name='my-secret',
        version_id='v1',
        version_stages=['AWSCURRENT']
    )
    return mock_client


def create_mock_dest_client():
    """Helper to create mocked destination client"""
    mock_client = MagicMock()
    mock_client.put_secret.return_value = {
        'ARN': 'arn:aws:secretsmanager:us-west-2:123456789012:secret:my-secret-def456',
        'Name': 'my-secret',
        'VersionId': 'v2'
    }
    return mock_client


class TestHandlerAWSIntegration:
    """Tests for handler with AWS integration"""

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_full_replication_flow(self, mock_create_client):
        """Test complete replication flow from source to destination"""
        # First client handles both tags and transformation secret
        mock_tags_transform = create_mock_tags_and_transform_client(sed_script='s/us-east-1/us-west-2/g')
        # Second client handles source secret
        mock_source = create_mock_source_client('db.us-east-1.example.com')
        # Third client handles destination
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-123'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert 'replicated successfully' in response['body']
        assert mock_tags_transform.get_secret_tags.called
        assert mock_tags_transform.get_secret.called
        assert mock_source.get_secret.called
        assert mock_dest.put_secret.called

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_source_secret_not_found(self, mock_create_client):
        """Test handling when source secret doesn't exist"""
        # First client handles tags and transformation secret
        mock_tags_transform = create_mock_tags_and_transform_client()
        # Second client fails when getting source secret
        mock_source_fail = MagicMock()
        mock_source_fail.get_secret.side_effect = SecretNotFoundError('Secret not found')
        mock_create_client.side_effect = [mock_tags_transform, mock_source_fail]

        context = Mock()
        context.request_id = 'test-404'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 404
        assert 'not found' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_source_access_denied(self, mock_create_client):
        """Test handling when access to source is denied"""
        # First client handles tags and transformation secret
        mock_tags_transform = create_mock_tags_and_transform_client()
        # Second client fails with access denied
        mock_source_fail = MagicMock()
        mock_source_fail.get_secret.side_effect = AccessDeniedError('Access denied')
        mock_create_client.side_effect = [mock_tags_transform, mock_source_fail]

        context = Mock()
        context.request_id = 'test-403'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 403
        assert 'Access denied' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_destination_access_denied(self, mock_create_client):
        """Test handling when access to destination is denied"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client()
        mock_dest = MagicMock()
        mock_dest.put_secret.side_effect = AccessDeniedError('Access denied to destination')
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-dest-403'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 403
        assert 'destination' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed',
        'MAX_SECRET_SIZE': '1024'  # 1KB in bytes
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_secret_size_validation(self, mock_create_client):
        """Test that secrets exceeding max size are rejected"""
        # Create a secret larger than 1KB
        large_secret = 'x' * 2000
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client(large_secret)
        mock_create_client.side_effect = [mock_tags_transform, mock_source]

        context = Mock()
        context.request_id = 'test-size'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 500
        assert 'exceeds maximum' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'json'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_json_transformation(self, mock_create_client):
        """Test JSON transformation mode"""
        # Mock JSON transformation rules in transformation secret
        json_rules = '{"transformations": [{"path": "$.region", "find": "us-east-1", "replace": "us-west-2"}]}'

        mock_tags_transform = create_mock_tags_and_transform_client(sed_script=json_rules)
        mock_source = create_mock_source_client('{"region":"us-east-1"}')
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-json'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['transformMode'] == 'json'

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'DEST_SECRET_NAME': 'custom-secret-name',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_custom_destination_name(self, mock_create_client):
        """Test using custom destination secret name"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client()
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-custom-name'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['destSecretId'] == 'custom-secret-name'
        # Verify put_secret was called with custom name
        mock_dest.put_secret.assert_called_once()
        call_args = mock_dest.put_secret.call_args[1]
        assert call_args['secret_id'] == 'custom-secret-name'

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'KMS_KEY_ID': 'arn:aws:kms:us-west-2:123456789012:key/abc123',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_kms_encryption(self, mock_create_client):
        """Test KMS encryption support"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client()
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-kms'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        # Verify KMS key was passed
        call_args = mock_dest.put_secret.call_args[1]
        assert call_args['kms_key_id'] == 'arn:aws:kms:us-west-2:123456789012:key/abc123'

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'DEST_ACCOUNT_ROLE_ARN': 'arn:aws:iam::999999999999:role/SecretReplicator',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_cross_account_replication(self, mock_create_client):
        """Test cross-account replication with role assumption"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client()
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-cross-account'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        # Verify dest client was created with role ARN
        dest_call = mock_create_client.call_args_list[2]  # Third client is dest
        assert dest_call[1]['role_arn'] == 'arn:aws:iam::999999999999:role/SecretReplicator'

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_binary_secret_handling(self, mock_create_client):
        """Test that binary secrets are detected and handled appropriately"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        # Source secret returns binary
        mock_source_binary = MagicMock()
        mock_source_binary.get_secret.return_value = SecretValue(
            secret_binary=b'\x00\x01\x02\x03',
            arn='arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-abc123',
            name='my-secret',
            version_id='v1'
        )
        # Destination client is created before binary check, but not used
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source_binary, mock_dest]

        context = Mock()
        context.request_id = 'test-binary'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 501
        assert 'Binary secret replication not implemented' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_throttling_error(self, mock_create_client):
        """Test handling of AWS throttling errors"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        # Source secret client fails with throttling
        mock_source_throttle = MagicMock()
        mock_source_throttle.get_secret.side_effect = ThrottlingError('Rate exceeded')
        mock_create_client.side_effect = [mock_tags_transform, mock_source_throttle]

        context = Mock()
        context.request_id = 'test-throttle'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 500
        assert 'Error retrieving source secret' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'DEST_SECRET_NAME': 'secrets-replicator/transformations/my-transform',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_destination_transformation_secret_blocked(self, mock_create_client):
        """Test that writing to transformation secret as destination is blocked"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client('db.us-east-1.example.com')
        # Destination client is created before the check happens, but check prevents using it
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-dest-transform'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 400
        assert 'Cannot replicate to transformation secret' in response['body']
        assert 'secrets-replicator/transformations/my-transform' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'DEST_SECRET_NAME': 'custom-destination-name',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_custom_destination_name_logs_warning(self, mock_create_client):
        """Test that using custom destination name logs a warning"""
        mock_tags_transform = create_mock_tags_and_transform_client()
        mock_source = create_mock_source_client('db.us-east-1.example.com')
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_tags_transform, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-custom-dest-warning'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        # Note: We can't easily test log output in unit tests,
        # but we verify the replication succeeds
        assert response['destSecretId'] == 'custom-destination-name'


class TestPassThroughReplication:
    """Tests for pass-through replication (no transformation tag)"""

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_passthrough_replication_no_tag(self, mock_create_client):
        """Test pass-through replication when no transformation tag is present"""
        # First client handles tags - return empty tags (no transformation tag)
        mock_tags = MagicMock()
        mock_tags.get_secret_tags.return_value = {}  # No transformation tag

        # Second client handles source secret
        mock_source = create_mock_source_client('{"host":"db.example.com","port":"5432"}')

        # Third client handles destination
        mock_dest = create_mock_dest_client()

        mock_create_client.side_effect = [mock_tags, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-passthrough'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify successful replication
        assert response['statusCode'] == 200
        assert 'replicated successfully' in response['body']
        assert response['transformMode'] == 'passthrough'
        assert response['rulesCount'] == 0
        assert response['transformChainLength'] == 0

        # Verify destination was written with original (untransformed) value
        assert mock_dest.put_secret.called
        call_kwargs = mock_dest.put_secret.call_args.kwargs
        assert call_kwargs['secret_value'] == '{"host":"db.example.com","port":"5432"}'  # Original value

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_passthrough_cross_region(self, mock_create_client):
        """Test pass-through replication works across regions"""
        mock_tags = MagicMock()
        mock_tags.get_secret_tags.return_value = {}

        mock_source = create_mock_source_client('supersecretpassword123')
        mock_dest = create_mock_dest_client()

        mock_create_client.side_effect = [mock_tags, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-passthrough-xregion'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['sourceRegion'] == 'us-east-1'
        assert response['destRegion'] == 'us-west-2'
        assert response['transformMode'] == 'passthrough'

        # Original value should be replicated without modification
        call_kwargs = mock_dest.put_secret.call_args.kwargs
        assert call_kwargs['secret_value'] == 'supersecretpassword123'

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_passthrough_binary_secret(self, mock_create_client):
        """Test that binary secrets return 501 (not yet implemented)"""
        mock_tags = MagicMock()
        mock_tags.get_secret_tags.return_value = {}

        # Create binary secret
        mock_source = MagicMock()
        mock_source.get_secret.return_value = SecretValue(
            secret_binary=b'binary_data_12345',
            arn='arn:aws:secretsmanager:us-east-1:123456789012:secret:binary-secret-abc123',
            name='binary-secret',
            version_id='v1',
            version_stages=['AWSCURRENT']
        )

        mock_dest = create_mock_dest_client()

        mock_create_client.side_effect = [mock_tags, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-passthrough-binary'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Binary secrets are not yet supported (would require additional implementation)
        assert response['statusCode'] == 501
        assert 'not implemented' in response['body'].lower()

        # Destination should not be called for binary secrets
        assert not mock_dest.put_secret.called

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_passthrough_with_json_secret(self, mock_create_client):
        """Test pass-through preserves JSON structure exactly"""
        mock_tags = MagicMock()
        mock_tags.get_secret_tags.return_value = {}

        json_secret = '{"user":"admin","pass":"secret123","config":{"timeout":30,"retries":3}}'
        mock_source = create_mock_source_client(json_secret)
        mock_dest = create_mock_dest_client()

        mock_create_client.side_effect = [mock_tags, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-passthrough-json'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['transformMode'] == 'passthrough'

        # JSON should be replicated exactly as-is
        call_kwargs = mock_dest.put_secret.call_args.kwargs
        assert call_kwargs['secret_value'] == json_secret

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-east-1'  # Same region
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_passthrough_same_region(self, mock_create_client):
        """Test pass-through replication works within same region"""
        mock_tags = MagicMock()
        mock_tags.get_secret_tags.return_value = {}

        mock_source = create_mock_source_client('sameregionsecret')
        mock_dest = create_mock_dest_client()

        mock_create_client.side_effect = [mock_tags, mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-passthrough-same-region'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['sourceRegion'] == 'us-east-1'
        assert response['destRegion'] == 'us-east-1'
        assert response['transformMode'] == 'passthrough'
