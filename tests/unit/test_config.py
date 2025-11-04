"""
Unit tests for config module
"""

import os
import pytest
from src.config import (
    ReplicatorConfig,
    ConfigurationError,
    load_config_from_env,
    is_cross_account
)


class TestReplicatorConfig:
    """Tests for ReplicatorConfig dataclass"""

    def test_minimal_valid_config(self):
        """Test creating config with minimal required fields"""
        config = ReplicatorConfig(dest_region='us-west-2')
        assert config.dest_region == 'us-west-2'
        assert config.transform_mode == 'auto'  # Default (changed from 'sed')
        assert config.log_level == 'INFO'  # Default
        assert config.enable_metrics is True  # Default

    def test_config_with_all_fields(self):
        """Test creating config with all fields"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            dest_secret_name='override-name',
            dest_account_role_arn='arn:aws:iam::999:role/MyRole',
            transform_mode='json',
            log_level='DEBUG',
            enable_metrics=False,
            dlq_arn='arn:aws:sqs:us-east-1:123:dlq',
            timeout_seconds=10,
            max_secret_size=32768
        )

        assert config.dest_region == 'us-west-2'
        assert config.dest_secret_name == 'override-name'
        assert config.dest_account_role_arn == 'arn:aws:iam::999:role/MyRole'
        assert config.transform_mode == 'json'
        assert config.log_level == 'DEBUG'
        assert config.enable_metrics is False
        assert config.dlq_arn == 'arn:aws:sqs:us-east-1:123:dlq'
        assert config.timeout_seconds == 10
        assert config.max_secret_size == 32768

    def test_config_invalid_region(self):
        """Test that invalid region raises error"""
        with pytest.raises(ConfigurationError, match="Invalid dest_region format"):
            ReplicatorConfig(dest_region='invalid')

    def test_config_empty_region(self):
        """Test that empty region raises error"""
        with pytest.raises(ConfigurationError, match="dest_region is required"):
            ReplicatorConfig(dest_region='')

    def test_config_invalid_transform_mode(self):
        """Test that invalid transform mode raises error"""
        with pytest.raises(ConfigurationError, match="Invalid transform_mode"):
            ReplicatorConfig(dest_region='us-west-2', transform_mode='invalid')

    def test_config_invalid_log_level(self):
        """Test that invalid log level raises error"""
        with pytest.raises(ConfigurationError, match="Invalid log_level"):
            ReplicatorConfig(dest_region='us-west-2', log_level='TRACE')

    def test_config_log_level_normalization(self):
        """Test that log level is normalized to uppercase"""
        config = ReplicatorConfig(dest_region='us-west-2', log_level='debug')
        assert config.log_level == 'DEBUG'

    def test_config_warn_normalized_to_warning(self):
        """Test that WARN is normalized to WARNING"""
        config = ReplicatorConfig(dest_region='us-west-2', log_level='WARN')
        assert config.log_level == 'WARNING'

    def test_config_invalid_role_arn(self):
        """Test that invalid role ARN raises error"""
        with pytest.raises(ConfigurationError, match="Invalid dest_account_role_arn format"):
            ReplicatorConfig(
                dest_region='us-west-2',
                dest_account_role_arn='not-an-arn'
            )

    def test_config_invalid_dlq_arn(self):
        """Test that invalid DLQ ARN raises error"""
        with pytest.raises(ConfigurationError, match="Invalid dlq_arn format"):
            ReplicatorConfig(
                dest_region='us-west-2',
                dlq_arn='not-an-arn'
            )

    def test_config_invalid_timeout(self):
        """Test that invalid timeout raises error"""
        with pytest.raises(ConfigurationError, match="timeout_seconds must be between"):
            ReplicatorConfig(dest_region='us-west-2', timeout_seconds=0)

        with pytest.raises(ConfigurationError, match="timeout_seconds must be between"):
            ReplicatorConfig(dest_region='us-west-2', timeout_seconds=400)

    def test_config_invalid_max_secret_size(self):
        """Test that invalid max secret size raises error"""
        with pytest.raises(ConfigurationError, match="max_secret_size must be between"):
            ReplicatorConfig(dest_region='us-west-2', max_secret_size=0)

        with pytest.raises(ConfigurationError, match="max_secret_size must be between"):
            ReplicatorConfig(dest_region='us-west-2', max_secret_size=100000)

    def test_config_valid_regions(self):
        """Test various valid AWS region formats"""
        valid_regions = [
            'us-east-1',
            'us-west-2',
            'eu-west-1',
            'eu-central-1',
            'ap-southeast-1',
            'ap-northeast-1',
            'ca-central-1',
            'sa-east-1',
            'af-south-1',
            'me-south-1',
            'us-gov-east-1',
            'us-gov-west-1',
        ]

        for region in valid_regions:
            config = ReplicatorConfig(dest_region=region)
            assert config.dest_region == region


class TestLoadConfigFromEnv:
    """Tests for load_config_from_env function"""

    def test_load_minimal_config(self, monkeypatch):
        """Test loading minimal configuration from environment"""
        monkeypatch.setenv('DEST_REGION', 'us-west-2')

        config = load_config_from_env()
        assert config.dest_region == 'us-west-2'
        assert config.transform_mode == 'sed'
        assert config.log_level == 'INFO'
        assert config.enable_metrics is True

    def test_load_full_config(self, monkeypatch):
        """Test loading full configuration from environment"""
        monkeypatch.setenv('DEST_REGION', 'us-west-2')
        monkeypatch.setenv('DEST_SECRET_NAME', 'my-dest-secret')
        monkeypatch.setenv('DEST_ACCOUNT_ROLE_ARN', 'arn:aws:iam::999:role/MyRole')
        monkeypatch.setenv('TRANSFORM_MODE', 'json')
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
        monkeypatch.setenv('ENABLE_METRICS', 'false')
        monkeypatch.setenv('DLQ_ARN', 'arn:aws:sqs:us-east-1:123:dlq')
        monkeypatch.setenv('TIMEOUT_SECONDS', '10')
        monkeypatch.setenv('MAX_SECRET_SIZE', '32768')

        config = load_config_from_env()
        assert config.dest_region == 'us-west-2'
        assert config.dest_secret_name == 'my-dest-secret'
        assert config.dest_account_role_arn == 'arn:aws:iam::999:role/MyRole'
        assert config.transform_mode == 'json'
        assert config.log_level == 'DEBUG'
        assert config.enable_metrics is False
        assert config.dlq_arn == 'arn:aws:sqs:us-east-1:123:dlq'
        assert config.timeout_seconds == 10
        assert config.max_secret_size == 32768

    def test_load_missing_required_field(self, monkeypatch):
        """Test that missing required field raises error"""
        # Don't set DEST_REGION
        with pytest.raises(ConfigurationError, match="Missing required environment variable: DEST_REGION"):
            load_config_from_env()

    def test_load_empty_string_values_become_none(self, monkeypatch):
        """Test that empty string values become None for optional fields"""
        monkeypatch.setenv('DEST_REGION', 'us-west-2')
        monkeypatch.setenv('DEST_SECRET_NAME', '')  # Empty string
        monkeypatch.setenv('DEST_ACCOUNT_ROLE_ARN', '')

        config = load_config_from_env()
        assert config.dest_secret_name is None
        assert config.dest_account_role_arn is None

    def test_load_whitespace_values_become_none(self, monkeypatch):
        """Test that whitespace-only values become None"""
        monkeypatch.setenv('DEST_REGION', 'us-west-2')
        monkeypatch.setenv('DEST_SECRET_NAME', '   ')  # Whitespace

        config = load_config_from_env()
        assert config.dest_secret_name is None

    def test_load_enable_metrics_variants(self, monkeypatch):
        """Test various enable_metrics boolean values"""
        monkeypatch.setenv('DEST_REGION', 'us-west-2')

        # Test 'true' variants
        for value in ['true', 'True', 'TRUE', '1', 'yes', 'YES', 'on', 'ON']:
            monkeypatch.setenv('ENABLE_METRICS', value)
            config = load_config_from_env()
            assert config.enable_metrics is True, f"Failed for value: {value}"

        # Test 'false' variants
        for value in ['false', 'False', 'FALSE', '0', 'no', 'NO', 'off', 'OFF']:
            monkeypatch.setenv('ENABLE_METRICS', value)
            config = load_config_from_env()
            assert config.enable_metrics is False, f"Failed for value: {value}"

    def test_load_numeric_fields(self, monkeypatch):
        """Test loading numeric fields"""
        monkeypatch.setenv('DEST_REGION', 'us-west-2')
        monkeypatch.setenv('TIMEOUT_SECONDS', '15')
        monkeypatch.setenv('MAX_SECRET_SIZE', '10000')

        config = load_config_from_env()
        assert config.timeout_seconds == 15
        assert config.max_secret_size == 10000


class TestIsCrossAccount:
    """Tests for is_cross_account function"""

    def test_not_cross_account(self):
        """Test same-account replication"""
        config = ReplicatorConfig(dest_region='us-west-2')
        assert is_cross_account(config) is False

    def test_cross_account(self):
        """Test cross-account replication"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            dest_account_role_arn='arn:aws:iam::999:role/MyRole'
        )
        assert is_cross_account(config) is True


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_config_with_region_variations(self):
        """Test region validation with various formats"""
        # Valid regions
        valid = ['us-east-1', 'eu-west-2', 'ap-southeast-1', 'ca-central-1']
        for region in valid:
            config = ReplicatorConfig(dest_region=region)
            assert config.dest_region == region

        # Invalid regions
        invalid = ['invalid', 'us', 'us-1', '123']
        for region in invalid:
            with pytest.raises(ConfigurationError):
                ReplicatorConfig(dest_region=region)

    def test_config_log_level_case_insensitive(self):
        """Test log level accepts various cases"""
        for level in ['debug', 'DEBUG', 'Debug', 'INFO', 'info', 'ERROR', 'error']:
            config = ReplicatorConfig(dest_region='us-west-2', log_level=level)
            assert config.log_level == level.upper()

    def test_config_with_env_overrides(self, monkeypatch):
        """Test that environment variables can override defaults"""
        monkeypatch.setenv('DEST_REGION', 'eu-west-1')
        monkeypatch.setenv('TRANSFORM_MODE', 'json')

        config = load_config_from_env()
        assert config.dest_region == 'eu-west-1'
        assert config.transform_mode == 'json'

    def test_config_internal_fields_not_settable(self):
        """Test that internal fields are not set via init"""
        config = ReplicatorConfig(dest_region='us-west-2')
        assert config.source_region is None
        assert config.source_account_id is None

        # These can be set after initialization
        config.source_region = 'us-east-1'
        config.source_account_id = '123456789012'
        assert config.source_region == 'us-east-1'
        assert config.source_account_id == '123456789012'
