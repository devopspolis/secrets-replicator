"""
Unit tests for sedfile_loader module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError
from src.sedfile_loader import (
    load_sedfile_from_s3,
    load_sedfile_from_bundle,
    load_sedfile,
    clear_cache,
    get_cache_keys,
    SedfileLoadError
)


class TestLoadSedfileFromS3:
    """Tests for load_sedfile_from_s3 function"""

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_success(self, mock_boto_client):
        """Test successful sedfile load from S3"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/us-east-1/us-west-2/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Clear cache before test
        clear_cache()

        # Load sedfile
        content = load_sedfile_from_s3('my-bucket', 'sedfiles/test.sed', use_cache=False)

        assert content == 's/us-east-1/us-west-2/g'
        mock_s3.get_object.assert_called_once_with(Bucket='my-bucket', Key='sedfiles/test.sed')

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_with_cache(self, mock_boto_client):
        """Test that caching works for S3 loads"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/test/TEST/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Clear cache before test
        clear_cache()

        # Load sedfile twice
        content1 = load_sedfile_from_s3('my-bucket', 'cached.sed', use_cache=True)
        content2 = load_sedfile_from_s3('my-bucket', 'cached.sed', use_cache=True)

        assert content1 == content2
        # S3 should only be called once (second call uses cache)
        assert mock_s3.get_object.call_count == 1

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_no_cache(self, mock_boto_client):
        """Test loading without cache"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/test/TEST/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Load sedfile twice without cache
        content1 = load_sedfile_from_s3('my-bucket', 'nocache.sed', use_cache=False)
        content2 = load_sedfile_from_s3('my-bucket', 'nocache.sed', use_cache=False)

        assert content1 == content2
        # S3 should be called twice (no caching)
        assert mock_s3.get_object.call_count == 2

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_no_such_key(self, mock_boto_client):
        """Test error when S3 key doesn't exist"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock NoSuchKey error
        error_response = {'Error': {'Code': 'NoSuchKey'}}
        mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')

        # Should raise SedfileLoadError
        with pytest.raises(SedfileLoadError, match="Sedfile not found in S3"):
            load_sedfile_from_s3('my-bucket', 'missing.sed', use_cache=False)

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_no_such_bucket(self, mock_boto_client):
        """Test error when S3 bucket doesn't exist"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock NoSuchBucket error
        error_response = {'Error': {'Code': 'NoSuchBucket'}}
        mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')

        # Should raise SedfileLoadError
        with pytest.raises(SedfileLoadError, match="S3 bucket not found"):
            load_sedfile_from_s3('missing-bucket', 'test.sed', use_cache=False)

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_access_denied(self, mock_boto_client):
        """Test error when access is denied"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock AccessDenied error
        error_response = {'Error': {'Code': 'AccessDenied'}}
        mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')

        # Should raise SedfileLoadError
        with pytest.raises(SedfileLoadError, match="Access denied to S3 sedfile"):
            load_sedfile_from_s3('my-bucket', 'test.sed', use_cache=False)

    @patch('src.sedfile_loader.boto3.client')
    def test_load_from_s3_unexpected_error(self, mock_boto_client):
        """Test handling of unexpected errors"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock unexpected error
        mock_s3.get_object.side_effect = Exception("Unexpected error")

        # Should raise SedfileLoadError
        with pytest.raises(SedfileLoadError, match="Unexpected error loading sedfile"):
            load_sedfile_from_s3('my-bucket', 'test.sed', use_cache=False)


class TestLoadSedfileFromBundle:
    """Tests for load_sedfile_from_bundle function"""

    def test_load_bundled_default_sedfile(self):
        """Test loading default bundled sedfile"""
        # Should be able to load default.sed from sedfiles/ directory
        content = load_sedfile_from_bundle('default.sed')

        assert isinstance(content, str)
        assert len(content) > 0
        # Default sedfile should contain region replacement
        assert 'us-east-1' in content or 'us-west-2' in content

    def test_load_bundled_example_sedfile(self):
        """Test loading example bundled sedfile"""
        content = load_sedfile_from_bundle('example.sed')

        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_bundled_missing_sedfile(self):
        """Test error when bundled sedfile doesn't exist"""
        with pytest.raises(SedfileLoadError, match="Bundled sedfile not found"):
            load_sedfile_from_bundle('nonexistent.sed')

    def test_load_bundled_custom_directory(self):
        """Test loading from custom sedfiles directory"""
        # This should work with default directory
        content = load_sedfile_from_bundle('default.sed', sedfiles_dir='sedfiles')
        assert isinstance(content, str)


class TestLoadSedfile:
    """Tests for load_sedfile convenience function"""

    @patch('src.sedfile_loader.boto3.client')
    def test_load_sedfile_from_s3(self, mock_boto_client):
        """Test load_sedfile chooses S3 when bucket/key provided"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/test/TEST/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Load from S3
        content = load_sedfile(bucket='my-bucket', key='test.sed', use_cache=False)

        assert content == 's/test/TEST/g'
        mock_s3.get_object.assert_called_once()

    def test_load_sedfile_from_bundle(self):
        """Test load_sedfile chooses bundled when no bucket/key"""
        # Load from bundle
        content = load_sedfile(bundled_filename='default.sed')

        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_sedfile_bundle_when_bucket_empty(self):
        """Test load_sedfile uses bundle when bucket is None"""
        content = load_sedfile(bucket=None, key=None, bundled_filename='default.sed')

        assert isinstance(content, str)


class TestCacheFunctions:
    """Tests for cache management functions"""

    @patch('src.sedfile_loader.boto3.client')
    def test_clear_cache(self, mock_boto_client):
        """Test cache clearing"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/test/TEST/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Load sedfile to populate cache
        clear_cache()
        load_sedfile_from_s3('my-bucket', 'test.sed', use_cache=True)

        # Check cache has content
        cache_keys = get_cache_keys()
        assert len(cache_keys) > 0

        # Clear cache
        clear_cache()

        # Check cache is empty
        cache_keys = get_cache_keys()
        assert len(cache_keys) == 0

    @patch('src.sedfile_loader.boto3.client')
    def test_get_cache_keys(self, mock_boto_client):
        """Test getting cache keys"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b's/test/TEST/g'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Clear cache first
        clear_cache()

        # Load multiple sedfiles
        load_sedfile_from_s3('bucket1', 'file1.sed', use_cache=True)
        load_sedfile_from_s3('bucket2', 'file2.sed', use_cache=True)

        # Check cache keys
        cache_keys = get_cache_keys()
        assert 's3://bucket1/file1.sed' in cache_keys
        assert 's3://bucket2/file2.sed' in cache_keys


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    @patch('src.sedfile_loader.boto3.client')
    def test_load_sedfile_with_unicode(self, mock_boto_client):
        """Test loading sedfile with Unicode characters"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response with Unicode
        unicode_content = 's/café/coffee/g'
        mock_body = MagicMock()
        mock_body.read.return_value = unicode_content.encode('utf-8')
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Load sedfile
        content = load_sedfile_from_s3('my-bucket', 'unicode.sed', use_cache=False)

        assert content == unicode_content
        assert 'café' in content

    @patch('src.sedfile_loader.boto3.client')
    def test_load_empty_sedfile(self, mock_boto_client):
        """Test loading empty sedfile"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock empty response
        mock_body = MagicMock()
        mock_body.read.return_value = b''
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Load sedfile
        content = load_sedfile_from_s3('my-bucket', 'empty.sed', use_cache=False)

        assert content == ''

    @patch('src.sedfile_loader.boto3.client')
    def test_cache_key_format(self, mock_boto_client):
        """Test that cache keys follow expected format"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_body = MagicMock()
        mock_body.read.return_value = b'test'
        mock_s3.get_object.return_value = {'Body': mock_body}

        # Clear cache
        clear_cache()

        # Load sedfile
        load_sedfile_from_s3('my-bucket', 'path/to/file.sed', use_cache=True)

        # Check cache key format
        cache_keys = get_cache_keys()
        assert len(cache_keys) == 1
        assert cache_keys[0] == 's3://my-bucket/path/to/file.sed'
