"""
Unit tests for config module
"""

import os
import pytest
from src.config import (
    ReplicatorConfig,
    DestinationConfig,
    ConfigurationError,
    load_config_from_env
)


class TestDestinationConfig:
    """Tests for DestinationConfig dataclass"""

    def test_minimal_valid_destination(self):
        """Test creating destination config with minimal required fields"""
        dest = DestinationConfig(region='us-west-2')
        assert dest.region == 'us-west-2'
        assert dest.account_role_arn is None
        assert dest.secret_names is None
        assert dest.secret_names_cache_ttl == 300  # Default
        assert dest.kms_key_id is None
        assert dest.variables is None

    def test_destination_with_all_fields(self):
        """Test creating destination config with all fields"""
        dest = DestinationConfig(
            region='us-west-2',
            account_role_arn='arn:aws:iam::999:role/MyRole',
            secret_names='secrets-replicator/names/us-west-2',
            secret_names_cache_ttl=600,
            kms_key_id='alias/my-key',
            variables={'ENV': 'prod', 'REGION': 'us-west-2'}
        )

        assert dest.region == 'us-west-2'
        assert dest.account_role_arn == 'arn:aws:iam::999:role/MyRole'
        assert dest.secret_names == 'secrets-replicator/names/us-west-2'
        assert dest.secret_names_cache_ttl == 600
        assert dest.kms_key_id == 'alias/my-key'
        assert dest.variables == {'ENV': 'prod', 'REGION': 'us-west-2'}

    def test_destination_invalid_region(self):
        """Test that invalid region raises error"""
        with pytest.raises(ConfigurationError, match="Invalid destination region format"):
            DestinationConfig(region='invalid')

    def test_destination_empty_region(self):
        """Test that empty region raises error"""
        with pytest.raises(ConfigurationError, match="Destination region is required"):
            DestinationConfig(region='')

    def test_destination_invalid_role_arn(self):
        """Test that invalid role ARN raises error"""
        with pytest.raises(ConfigurationError, match="Invalid account_role_arn format"):
            DestinationConfig(
                region='us-west-2',
                account_role_arn='not-an-arn'
            )

    def test_destination_valid_regions(self):
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
            dest = DestinationConfig(region=region)
            assert dest.region == region


class TestReplicatorConfig:
    """Tests for ReplicatorConfig dataclass"""

    def test_minimal_valid_config(self):
        """Test creating config with minimal required fields"""
        dest = DestinationConfig(region='us-west-2')
        config = ReplicatorConfig(destinations=[dest])

        assert len(config.destinations) == 1
        assert config.destinations[0].region == 'us-west-2'
        assert config.transform_mode == 'auto'  # Default
        assert config.log_level == 'INFO'  # Default
        assert config.enable_metrics is True  # Default

    def test_config_with_multiple_destinations(self):
        """Test creating config with multiple destinations"""
        dest1 = DestinationConfig(region='us-west-2')
        dest2 = DestinationConfig(region='eu-west-1')
        dest3 = DestinationConfig(
            region='ap-south-1',
            account_role_arn='arn:aws:iam::999:role/MyRole'
        )

        config = ReplicatorConfig(destinations=[dest1, dest2, dest3])

        assert len(config.destinations) == 3
        assert config.destinations[0].region == 'us-west-2'
        assert config.destinations[1].region == 'eu-west-1'
        assert config.destinations[2].region == 'ap-south-1'
        assert config.destinations[2].account_role_arn == 'arn:aws:iam::999:role/MyRole'

    def test_config_with_all_fields(self):
        """Test creating config with all fields"""
        dest = DestinationConfig(region='us-west-2')
        config = ReplicatorConfig(
            destinations=[dest],
            transform_mode='json',
            log_level='DEBUG',
            enable_metrics=False,
            dlq_arn='arn:aws:sqs:us-east-1:123:dlq',
            timeout_seconds=10,
            max_secret_size=32768,
            default_secret_names='secrets-replicator/names/default',
            default_region='us-east-1',
            default_role_arn='arn:aws:iam::888:role/DefaultRole'
        )

        assert config.transform_mode == 'json'
        assert config.log_level == 'DEBUG'
        assert config.enable_metrics is False
        assert config.dlq_arn == 'arn:aws:sqs:us-east-1:123:dlq'
        assert config.timeout_seconds == 10
        assert config.max_secret_size == 32768
        assert config.default_secret_names == 'secrets-replicator/names/default'
        assert config.default_region == 'us-east-1'
        assert config.default_role_arn == 'arn:aws:iam::888:role/DefaultRole'

    def test_config_empty_destinations_allowed(self):
        """Test that empty destinations list is allowed (will be loaded later)"""
        config = ReplicatorConfig(destinations=[])
        assert len(config.destinations) == 0

    def test_config_invalid_transform_mode(self):
        """Test that invalid transform mode raises error"""
        dest = DestinationConfig(region='us-west-2')
        with pytest.raises(ConfigurationError, match="Invalid transform_mode"):
            ReplicatorConfig(destinations=[dest], transform_mode='invalid')

    def test_config_invalid_log_level(self):
        """Test that invalid log level raises error"""
        dest = DestinationConfig(region='us-west-2')
        with pytest.raises(ConfigurationError, match="Invalid log_level"):
            ReplicatorConfig(destinations=[dest], log_level='TRACE')

    def test_config_log_level_normalization(self):
        """Test that log level is normalized to uppercase"""
        dest = DestinationConfig(region='us-west-2')
        config = ReplicatorConfig(destinations=[dest], log_level='debug')
        assert config.log_level == 'DEBUG'

    def test_config_warn_normalized_to_warning(self):
        """Test that WARN is normalized to WARNING"""
        dest = DestinationConfig(region='us-west-2')
        config = ReplicatorConfig(destinations=[dest], log_level='WARN')
        assert config.log_level == 'WARNING'

    def test_config_invalid_dlq_arn(self):
        """Test that invalid DLQ ARN raises error"""
        dest = DestinationConfig(region='us-west-2')
        with pytest.raises(ConfigurationError, match="Invalid dlq_arn format"):
            ReplicatorConfig(
                destinations=[dest],
                dlq_arn='not-an-arn'
            )

    def test_config_invalid_timeout(self):
        """Test that invalid timeout raises error"""
        dest = DestinationConfig(region='us-west-2')
        with pytest.raises(ConfigurationError, match="timeout_seconds must be between"):
            ReplicatorConfig(destinations=[dest], timeout_seconds=0)

        with pytest.raises(ConfigurationError, match="timeout_seconds must be between"):
            ReplicatorConfig(destinations=[dest], timeout_seconds=400)

    def test_config_invalid_max_secret_size(self):
        """Test that invalid max secret size raises error"""
        dest = DestinationConfig(region='us-west-2')
        with pytest.raises(ConfigurationError, match="max_secret_size must be between"):
            ReplicatorConfig(destinations=[dest], max_secret_size=0)

        with pytest.raises(ConfigurationError, match="max_secret_size must be between"):
            ReplicatorConfig(destinations=[dest], max_secret_size=100000)

    def test_config_internal_fields_not_settable(self):
        """Test that internal fields are not set via init"""
        dest = DestinationConfig(region='us-west-2')
        config = ReplicatorConfig(destinations=[dest])
        assert config.source_region is None
        assert config.source_account_id is None

        # These can be set after initialization
        config.source_region = 'us-east-1'
        config.source_account_id = '123456789012'
        assert config.source_region == 'us-east-1'
        assert config.source_account_id == '123456789012'


class TestLoadConfigFromEnv:
    """Tests for load_config_from_env function"""

    def test_load_minimal_config(self, monkeypatch):
        """Test loading minimal configuration from environment"""
        # Set minimal environment variables for runtime config
        monkeypatch.setenv('LOG_LEVEL', 'INFO')
        monkeypatch.setenv('TRANSFORM_MODE', 'auto')

        config = load_config_from_env()
        assert config.destinations == []  # Empty until loaded from secret
        assert config.transform_mode == 'auto'
        assert config.log_level == 'INFO'
        assert config.enable_metrics is True

    def test_load_full_config(self, monkeypatch):
        """Test loading full configuration from environment"""
        monkeypatch.setenv('TRANSFORM_MODE', 'json')
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
        monkeypatch.setenv('ENABLE_METRICS', 'false')
        monkeypatch.setenv('DLQ_ARN', 'arn:aws:sqs:us-east-1:123:dlq')
        monkeypatch.setenv('TIMEOUT_SECONDS', '10')
        monkeypatch.setenv('MAX_SECRET_SIZE', '32768')
        monkeypatch.setenv('CONFIG_SECRET', 'secrets-replicator/config/custom')
        monkeypatch.setenv('DEFAULT_SECRET_NAMES', 'secrets-replicator/names/default')
        monkeypatch.setenv('DEFAULT_REGION', 'us-east-1')
        monkeypatch.setenv('DEFAULT_ROLE_ARN', 'arn:aws:iam::888:role/DefaultRole')

        config = load_config_from_env()
        assert config.transform_mode == 'json'
        assert config.log_level == 'DEBUG'
        assert config.enable_metrics is False
        assert config.dlq_arn == 'arn:aws:sqs:us-east-1:123:dlq'
        assert config.timeout_seconds == 10
        assert config.max_secret_size == 32768
        assert config.config_secret == 'secrets-replicator/config/custom'
        assert config.default_secret_names == 'secrets-replicator/names/default'
        assert config.default_region == 'us-east-1'
        assert config.default_role_arn == 'arn:aws:iam::888:role/DefaultRole'

    def test_load_empty_string_values_become_none(self, monkeypatch):
        """Test that empty string values become None for optional fields"""
        monkeypatch.setenv('DEFAULT_SECRET_NAMES', '')  # Empty string
        monkeypatch.setenv('DEFAULT_ROLE_ARN', '')

        config = load_config_from_env()
        assert config.default_secret_names is None
        assert config.default_role_arn is None

    def test_load_whitespace_values_become_none(self, monkeypatch):
        """Test that whitespace-only values become None"""
        monkeypatch.setenv('DEFAULT_SECRET_NAMES', '   ')  # Whitespace

        config = load_config_from_env()
        assert config.default_secret_names is None

    def test_load_enable_metrics_variants(self, monkeypatch):
        """Test various enable_metrics boolean values"""
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
        monkeypatch.setenv('TIMEOUT_SECONDS', '15')
        monkeypatch.setenv('MAX_SECRET_SIZE', '10000')
        monkeypatch.setenv('SECRET_NAMES_CACHE_TTL', '600')

        config = load_config_from_env()
        assert config.timeout_seconds == 15
        assert config.max_secret_size == 10000
        assert config.secret_names_cache_ttl == 600


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_config_log_level_case_insensitive(self):
        """Test log level accepts various cases"""
        dest = DestinationConfig(region='us-west-2')
        for level in ['debug', 'DEBUG', 'Debug', 'INFO', 'info', 'ERROR', 'error']:
            config = ReplicatorConfig(destinations=[dest], log_level=level)
            assert config.log_level == level.upper()

    def test_config_with_env_overrides(self, monkeypatch):
        """Test that environment variables can override defaults"""
        monkeypatch.setenv('DEFAULT_REGION', 'eu-west-1')
        monkeypatch.setenv('TRANSFORM_MODE', 'json')

        config = load_config_from_env()
        assert config.default_region == 'eu-west-1'
        assert config.transform_mode == 'json'

    def test_destination_with_custom_variables(self):
        """Test destination with custom transformation variables"""
        dest = DestinationConfig(
            region='us-west-2',
            variables={
                'ENV': 'production',
                'DB_INSTANCE': 'prod-db-west',
                'API_DOMAIN': 'api.prod.west.example.com'
            }
        )

        assert dest.variables['ENV'] == 'production'
        assert dest.variables['DB_INSTANCE'] == 'prod-db-west'
        assert dest.variables['API_DOMAIN'] == 'api.prod.west.example.com'

    def test_cross_account_destination(self):
        """Test cross-account destination configuration"""
        dest = DestinationConfig(
            region='us-west-2',
            account_role_arn='arn:aws:iam::999888777666:role/SecretsReplicatorRole'
        )

        assert dest.account_role_arn == 'arn:aws:iam::999888777666:role/SecretsReplicatorRole'
