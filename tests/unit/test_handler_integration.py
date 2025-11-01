"""
Integration tests for handler with AWS clients
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from src.handler import lambda_handler
from src.aws_clients import SecretValue, SecretNotFoundError, AccessDeniedError, ThrottlingError
from tests.fixtures.eventbridge_events import (
    PUT_SECRET_VALUE_EVENT,
    UPDATE_SECRET_EVENT,
    REPLICATE_SECRET_EVENT
)


def create_mock_source_client(secret_value='{"key":"value"}'):
    """Helper to create mocked source client"""
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
        mock_source = create_mock_source_client('db.us-east-1.example.com')
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-123'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert 'replicated successfully' in response['body']
        assert mock_source.get_secret.called
        assert mock_dest.put_secret.called

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_source_secret_not_found(self, mock_create_client):
        """Test handling when source secret doesn't exist"""
        mock_source = MagicMock()
        mock_source.get_secret.side_effect = SecretNotFoundError('Secret not found')
        mock_create_client.return_value = mock_source

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
        mock_source = MagicMock()
        mock_source.get_secret.side_effect = AccessDeniedError('Access denied')
        mock_create_client.return_value = mock_source

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
        mock_source = create_mock_source_client()
        mock_dest = MagicMock()
        mock_dest.put_secret.side_effect = AccessDeniedError('Access denied to destination')
        mock_create_client.side_effect = [mock_source, mock_dest]

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
        mock_source = create_mock_source_client(large_secret)
        mock_create_client.return_value = mock_source

        context = Mock()
        context.request_id = 'test-size'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 500
        assert 'exceeds maximum' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'json'
    })
    @patch('src.handler.load_sedfile')
    @patch('src.handler.create_secrets_manager_client')
    def test_json_transformation(self, mock_create_client, mock_load_sedfile):
        """Test JSON transformation mode"""
        # Mock JSON transformation rules
        json_rules = '{"transformations": [{"path": "$.region", "find": "us-east-1", "replace": "us-west-2"}]}'
        mock_load_sedfile.return_value = json_rules

        mock_source = create_mock_source_client('{"region":"us-east-1"}')
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_source, mock_dest]

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
        mock_source = create_mock_source_client()
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_source, mock_dest]

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
        mock_source = create_mock_source_client()
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_source, mock_dest]

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
        mock_source = create_mock_source_client()
        mock_dest = create_mock_dest_client()
        mock_create_client.side_effect = [mock_source, mock_dest]

        context = Mock()
        context.request_id = 'test-cross-account'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        # Verify dest client was created with role ARN
        dest_call = mock_create_client.call_args_list[1]
        assert dest_call[1]['role_arn'] == 'arn:aws:iam::999999999999:role/SecretReplicator'

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.create_secrets_manager_client')
    def test_binary_secret_handling(self, mock_create_client):
        """Test that binary secrets are detected and handled appropriately"""
        mock_source = MagicMock()
        mock_source.get_secret.return_value = SecretValue(
            secret_binary=b'\x00\x01\x02\x03',
            arn='arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-abc123',
            name='my-secret',
            version_id='v1'
        )
        mock_create_client.return_value = mock_source

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
        mock_source = MagicMock()
        mock_source.get_secret.side_effect = ThrottlingError('Rate exceeded')
        mock_create_client.return_value = mock_source

        context = Mock()
        context.request_id = 'test-throttle'

        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 500
        assert 'Error retrieving source secret' in response['body']
