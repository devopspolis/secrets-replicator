"""
Unit tests for handler module
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.handler import lambda_handler
from src.config import ConfigurationError
from src.event_parser import EventParsingError
from src.sedfile_loader import SedfileLoadError
from src.transformer import TransformationError
from tests.fixtures.eventbridge_events import (
    PUT_SECRET_VALUE_EVENT,
    UPDATE_SECRET_EVENT,
    REPLICATE_SECRET_EVENT,
    INVALID_EVENT_MISSING_DETAIL
)


class TestLambdaHandler:
    """Tests for lambda_handler function"""

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed',
        'LOG_LEVEL': 'INFO'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_success_sed_mode(self, mock_load_sedfile):
        """Test successful handler execution with sed mode"""
        # Mock sedfile content
        mock_load_sedfile.return_value = 's/us-east-1/us-west-2/g'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-request-123'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify response
        assert response['statusCode'] == 200
        assert 'Success' in response['body']
        assert response['secretId'] == 'my-secret'
        assert response['sourceRegion'] == 'us-east-1'
        assert response['destRegion'] == 'us-west-2'
        assert response['transformMode'] == 'sed'
        assert response['rulesCount'] == 1

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'json',
        'LOG_LEVEL': 'INFO'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_success_json_mode(self, mock_load_sedfile):
        """Test successful handler execution with JSON mode"""
        # Mock JSON mapping content
        json_mapping = '''
        {
            "transformations": [
                {"path": "$.region", "find": "us-east-1", "replace": "us-west-2"}
            ]
        }
        '''
        mock_load_sedfile.return_value = json_mapping

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-request-456'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify response
        assert response['statusCode'] == 200
        assert response['transformMode'] == 'json'
        assert response['rulesCount'] == 1

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'SEDFILE_S3_BUCKET': 'my-bucket',
        'SEDFILE_S3_KEY': 'test.sed',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.sedfile_loader.boto3.client')
    def test_lambda_handler_with_s3_sedfile(self, mock_boto_client):
        """Test handler loading sedfile from S3"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock S3 response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/test/TEST/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-request-s3'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify S3 was called
        mock_s3.get_object.assert_called()
        assert response['statusCode'] == 200

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_skips_replicate_event(self, mock_load_sedfile):
        """Test that ReplicateSecretToRegions events are skipped"""
        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-skip'

        # Execute handler with replicate event
        response = lambda_handler(REPLICATE_SECRET_EVENT, context)

        # Verify event was skipped
        assert response['statusCode'] == 200
        assert 'skipped' in response['body']
        # Sedfile should not be loaded for skipped events
        mock_load_sedfile.assert_not_called()

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_with_update_secret_event(self, mock_load_sedfile):
        """Test handler with UpdateSecret event"""
        # Mock sedfile
        mock_load_sedfile.return_value = 's/old/new/g'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-update'

        # Execute handler
        response = lambda_handler(UPDATE_SECRET_EVENT, context)

        # Verify success
        assert response['statusCode'] == 200
        assert 'Success' in response['body']

    @patch.dict(os.environ, {})
    def test_lambda_handler_config_error(self):
        """Test handler with missing configuration"""
        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-config-error'

        # Execute handler (should fail due to missing DEST_REGION)
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify error response
        assert response['statusCode'] == 500
        assert 'Configuration error' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_event_parsing_error(self, mock_load_sedfile):
        """Test handler with invalid event"""
        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-parse-error'

        # Execute handler with invalid event
        response = lambda_handler(INVALID_EVENT_MISSING_DETAIL, context)

        # Verify error response
        assert response['statusCode'] == 400
        assert 'Event parsing error' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'SEDFILE_S3_BUCKET': 'my-bucket',
        'SEDFILE_S3_KEY': 'missing.sed',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.sedfile_loader.boto3.client')
    def test_lambda_handler_sedfile_load_error(self, mock_boto_client):
        """Test handler with sedfile loading error"""
        from botocore.exceptions import ClientError

        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock S3 error
        error_response = {'Error': {'Code': 'NoSuchKey'}}
        mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-sedfile-error'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify error response
        assert response['statusCode'] == 500
        assert 'Sedfile load error' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_invalid_sed_syntax(self, mock_load_sedfile):
        """Test handler with invalid sed syntax"""
        # Mock invalid sedfile content
        mock_load_sedfile.return_value = 's/invalid'  # Missing closing delimiter

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-invalid-sed'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify error response
        assert response['statusCode'] == 500
        assert 'Rule parsing error' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'json'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_invalid_json_mapping(self, mock_load_sedfile):
        """Test handler with invalid JSON mapping"""
        # Mock invalid JSON content
        mock_load_sedfile.return_value = '{invalid json'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-invalid-json'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify error response
        assert response['statusCode'] == 500
        assert 'Rule parsing error' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_without_request_id(self, mock_load_sedfile):
        """Test handler with context missing request_id"""
        # Mock sedfile
        mock_load_sedfile.return_value = 's/test/TEST/g'

        # Mock Lambda context without request_id
        context = Mock(spec=[])  # Empty spec means no attributes

        # Execute handler (should handle missing request_id gracefully)
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify success
        assert response['statusCode'] == 200

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed',
        'LOG_LEVEL': 'DEBUG'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_with_debug_logging(self, mock_load_sedfile):
        """Test handler with DEBUG log level"""
        # Mock sedfile
        mock_load_sedfile.return_value = 's/test/TEST/g'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-debug'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify success
        assert response['statusCode'] == 200

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_lambda_handler_response_format(self, mock_load_sedfile):
        """Test that handler response has correct format"""
        # Mock sedfile
        mock_load_sedfile.return_value = 's/a/b/g\ns/c/d/g'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-response'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify response structure
        assert 'statusCode' in response
        assert 'body' in response
        assert 'secretId' in response
        assert 'sourceRegion' in response
        assert 'destRegion' in response
        assert 'transformMode' in response
        assert 'rulesCount' in response

        # Verify values
        assert response['rulesCount'] == 2
        assert response['secretId'] == 'my-secret'
        assert response['sourceRegion'] == 'us-east-1'
        assert response['destRegion'] == 'us-west-2'


class TestHandlerIntegration:
    """Integration tests for handler with real components"""

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    def test_handler_with_bundled_sedfile(self):
        """Test handler using bundled sedfile (no mocking)"""
        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-bundled'

        # Execute handler (should use default.sed from bundle)
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify success
        assert response['statusCode'] == 200
        assert response['transformMode'] == 'sed'
        assert response['rulesCount'] > 0

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'DEST_SECRET_NAME': 'custom-secret-name',
        'DEST_ACCOUNT_ROLE_ARN': 'arn:aws:iam::123456789012:role/SecretReplicatorRole',
        'TRANSFORM_MODE': 'sed',
        'KMS_KEY_ID': 'arn:aws:kms:us-west-2:123456789012:key/abc123',
        'LOG_LEVEL': 'INFO'
    })
    def test_handler_with_full_config(self):
        """Test handler with all configuration options"""
        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-full-config'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify success
        assert response['statusCode'] == 200


class TestHandlerErrorHandling:
    """Tests for error handling in handler"""

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.parse_eventbridge_event')
    def test_handler_unexpected_exception(self, mock_parse):
        """Test handler handles unexpected exceptions"""
        # Mock unexpected error
        mock_parse.side_effect = RuntimeError('Unexpected error')

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-unexpected'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify error response
        assert response['statusCode'] == 500
        assert 'Unexpected error' in response['body']

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.setup_logger')
    @patch('src.handler.load_sedfile')
    def test_handler_logs_errors(self, mock_load_sedfile, mock_setup_logger):
        """Test that handler properly logs errors"""
        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock sedfile load error
        mock_load_sedfile.side_effect = SedfileLoadError('Test error')

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-log-error'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        # Verify error was logged
        assert response['statusCode'] == 500
        # Logger should have been called (checking it was created)
        mock_setup_logger.assert_called()


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_handler_with_empty_sedfile(self, mock_load_sedfile):
        """Test handler with empty sedfile"""
        # Mock empty sedfile
        mock_load_sedfile.return_value = ''

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-empty'

        # Execute handler (should succeed with 0 rules)
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['rulesCount'] == 0

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'sed'
    })
    @patch('src.handler.load_sedfile')
    def test_handler_with_commented_sedfile(self, mock_load_sedfile):
        """Test handler with sedfile containing only comments"""
        # Mock sedfile with comments
        mock_load_sedfile.return_value = '# Just a comment\n# Another comment'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-comments'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['rulesCount'] == 0

    @patch.dict(os.environ, {
        'DEST_REGION': 'us-west-2',
        'TRANSFORM_MODE': 'json'
    })
    @patch('src.handler.load_sedfile')
    def test_handler_with_empty_json_mappings(self, mock_load_sedfile):
        """Test handler with empty JSON transformations"""
        # Mock JSON with no transformations
        mock_load_sedfile.return_value = '{"transformations": []}'

        # Mock Lambda context
        context = Mock()
        context.request_id = 'test-empty-json'

        # Execute handler
        response = lambda_handler(PUT_SECRET_VALUE_EVENT, context)

        assert response['statusCode'] == 200
        assert response['rulesCount'] == 0
