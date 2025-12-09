"""
Configuration management for secrets replicator.

Loads configuration from environment variables with validation.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional, List


# Hardcoded prefixes for security and consistency
TRANSFORMATION_SECRET_PREFIX = 'secrets-replicator/transformations/'
FILTER_SECRET_PREFIX = 'secrets-replicator/filters/'
NAME_MAPPING_PREFIX = 'secrets-replicator/names/'


class ConfigurationError(Exception):
    """Raised when configuration is invalid"""
    pass


@dataclass
class DestinationConfig:
    """Configuration for a single replication destination"""

    region: str                                   # Destination AWS region
    account_role_arn: Optional[str] = None       # Role ARN for cross-account (if different account)
    secret_names: Optional[str] = None           # Comma-separated list of name mapping secret names
    secret_names_cache_ttl: int = 300            # Cache TTL for name mappings (seconds)
    kms_key_id: Optional[str] = None             # KMS key ID for encryption (optional)

    def __post_init__(self):
        """Validate destination configuration"""
        if not self.region:
            raise ConfigurationError("Destination region is required")

        if not self._is_valid_region(self.region):
            raise ConfigurationError(f"Invalid destination region format: {self.region}")

        if self.account_role_arn and not self.account_role_arn.startswith('arn:'):
            raise ConfigurationError(f"Invalid account_role_arn format: {self.account_role_arn}")

    @staticmethod
    def _is_valid_region(region: str) -> bool:
        """Basic validation for AWS region format"""
        if not region:
            return False

        parts = region.split('-')
        if len(parts) < 3:
            return False

        valid_prefixes = [
            'us', 'eu', 'ap', 'ca', 'sa', 'af', 'me', 'il', 'cn', 'us-gov'
        ]

        region_prefix = parts[0] if parts[0] != 'us' else f"{parts[0]}-{parts[1]}"
        if region_prefix == 'us-gov':
            return len(parts) >= 3

        return parts[0] in valid_prefixes or region_prefix in valid_prefixes


@dataclass
class ReplicatorConfig:
    """Configuration for the secrets replicator Lambda function"""

    # Destination configuration - supports multiple destinations
    destinations: List[DestinationConfig]         # List of replication destinations

    # Optional fields
    transform_mode: str = 'auto'                  # Transformation mode (auto|sed|json)
    log_level: str = 'INFO'                       # Log level
    enable_metrics: bool = True                   # Enable CloudWatch metrics
    dlq_arn: Optional[str] = None                 # Dead Letter Queue ARN

    # Advanced options
    timeout_seconds: int = 5                      # Regex timeout
    max_secret_size: int = 65536                  # Max secret size (64KB)

    # Centralized filtering (SECRETS_FILTER)
    secrets_filter: Optional[str] = None  # Comma-separated list of filter secret names
    secrets_filter_cache_ttl: int = 300   # Cache TTL in seconds (5 minutes)

    # Internal/computed fields
    source_region: Optional[str] = field(default=None, init=False)
    source_account_id: Optional[str] = field(default=None, init=False)

    # Legacy compatibility fields (deprecated, for backward compatibility only)
    dest_region: Optional[str] = field(default=None, init=False)
    dest_account_role_arn: Optional[str] = field(default=None, init=False)
    dest_secret_names: Optional[str] = field(default=None, init=False)
    dest_secret_names_cache_ttl: Optional[int] = field(default=None, init=False)
    kms_key_id: Optional[str] = field(default=None, init=False)

    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()

    def validate(self):
        """
        Validate configuration values.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate destinations list
        if not self.destinations or len(self.destinations) == 0:
            raise ConfigurationError("At least one destination is required")

        # Validate each destination (already validated in DestinationConfig.__post_init__)
        for i, dest in enumerate(self.destinations):
            if not isinstance(dest, DestinationConfig):
                raise ConfigurationError(f"Destination {i} must be a DestinationConfig instance")

        # Validate transform mode
        valid_modes = ['auto', 'sed', 'json']
        if self.transform_mode not in valid_modes:
            raise ConfigurationError(
                f"Invalid transform_mode: {self.transform_mode} (must be one of {valid_modes})"
            )

        # Validate log level
        valid_log_levels = ['DEBUG', 'INFO', 'WARN', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_log_levels:
            raise ConfigurationError(
                f"Invalid log_level: {self.log_level} (must be one of {valid_log_levels})"
            )

        # Normalize log level to uppercase
        self.log_level = self.log_level.upper()
        if self.log_level == 'WARN':
            self.log_level = 'WARNING'  # Normalize to Python logging standard

        # Validate DLQ ARN format (basic check)
        if self.dlq_arn and not self.dlq_arn.startswith('arn:'):
            raise ConfigurationError(f"Invalid dlq_arn format: {self.dlq_arn}")

        # Validate timeout
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ConfigurationError(
                f"timeout_seconds must be between 1 and 300 (got {self.timeout_seconds})"
            )

        # Validate max secret size
        if self.max_secret_size <= 0 or self.max_secret_size > 65536:
            raise ConfigurationError(
                f"max_secret_size must be between 1 and 65536 (got {self.max_secret_size})"
            )


def parse_tag_filters(tag_string: str) -> List[tuple[str, str]]:
    """
    Parse comma-separated tag filters into list of (key, value) tuples.

    Args:
        tag_string: Comma-separated tag filters (e.g., "Key1=Value1,Key2=Value2")

    Returns:
        List of (key, value) tuples

    Examples:
        >>> parse_tag_filters("Replicate=true,Environment=prod")
        [('Replicate', 'true'), ('Environment', 'prod')]
        >>> parse_tag_filters("")
        []
    """
    if not tag_string or not tag_string.strip():
        return []

    tags = []
    for tag in tag_string.split(','):
        tag = tag.strip()
        if not tag:
            continue

        if '=' not in tag:
            raise ConfigurationError(f"Invalid tag filter format: '{tag}' (expected Key=Value)")

        key, value = tag.split('=', 1)
        key = key.strip()
        value = value.strip()

        if not key or not value:
            raise ConfigurationError(f"Invalid tag filter: '{tag}' (key and value cannot be empty)")

        tags.append((key, value))

    return tags


def load_config_from_env() -> ReplicatorConfig:
    """
    Load configuration from environment variables.

    Environment variables:
        DESTINATIONS (required): JSON-encoded list of destination configurations
            Example: '[{"region":"us-east-1","secret_names":"secrets-replicator/names/us-east-1"}]'

        Alternative (legacy, deprecated):
            DEST_REGION: Single destination region (for backward compatibility)
            DEST_ACCOUNT_ROLE_ARN: IAM role ARN for cross-account access
            DEST_SECRET_NAMES: Name mapping secret names
            DEST_SECRET_NAMES_CACHE_TTL: Cache TTL for name mappings
            KMS_KEY_ID: KMS key ID for encryption

        Common parameters:
            TRANSFORM_MODE: Transformation mode (default: 'auto')
            LOG_LEVEL: Log level (default: 'INFO')
            ENABLE_METRICS: Enable CloudWatch metrics (default: 'true')
            DLQ_ARN: Dead Letter Queue ARN
            TIMEOUT_SECONDS: Regex timeout (default: 5)
            MAX_SECRET_SIZE: Maximum secret size (default: 65536)
            SECRETS_FILTER: Comma-separated list of filter secret names
            SECRETS_FILTER_CACHE_TTL: Cache TTL for filter configuration in seconds (default: 300)

    Returns:
        ReplicatorConfig object

    Raises:
        ConfigurationError: If required config is missing or invalid

    Examples:
        >>> import os
        >>> os.environ['DESTINATIONS'] = '[{"region":"us-west-2"}]'
        >>> config = load_config_from_env()
        >>> config.destinations[0].region
        'us-west-2'
    """
    # Parse destinations (new multi-destination format)
    destinations_json = os.environ.get('DESTINATIONS', '').strip()

    if destinations_json:
        # New format: JSON-encoded list of destinations
        try:
            destinations_data = json.loads(destinations_json)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in DESTINATIONS: {e}")

        if not isinstance(destinations_data, list):
            raise ConfigurationError("DESTINATIONS must be a JSON array")

        if len(destinations_data) == 0:
            raise ConfigurationError("DESTINATIONS must contain at least one destination")

        destinations = []
        for i, dest_data in enumerate(destinations_data):
            if not isinstance(dest_data, dict):
                raise ConfigurationError(f"Destination {i} must be a JSON object")

            try:
                dest = DestinationConfig(
                    region=dest_data.get('region', ''),
                    account_role_arn=dest_data.get('account_role_arn') or dest_data.get('accountRoleArn'),
                    secret_names=dest_data.get('secret_names') or dest_data.get('secretNames'),
                    secret_names_cache_ttl=dest_data.get('secret_names_cache_ttl') or
                                          dest_data.get('secretNamesCacheTTL') or 300,
                    kms_key_id=dest_data.get('kms_key_id') or dest_data.get('kmsKeyId')
                )
                destinations.append(dest)
            except (TypeError, ConfigurationError) as e:
                raise ConfigurationError(f"Invalid destination {i}: {e}")

    else:
        # Legacy format: Single destination from separate env vars (backward compatibility)
        dest_region = os.environ.get('DEST_REGION', '').strip()
        if not dest_region:
            raise ConfigurationError(
                "Missing required configuration: Either DESTINATIONS or DEST_REGION must be set"
            )

        dest_account_role_arn = os.environ.get('DEST_ACCOUNT_ROLE_ARN', '').strip() or None
        dest_secret_names = os.environ.get('DEST_SECRET_NAMES', '').strip() or None
        dest_secret_names_cache_ttl = int(os.environ.get('DEST_SECRET_NAMES_CACHE_TTL', '300'))
        kms_key_id = os.environ.get('KMS_KEY_ID', '').strip() or None

        destinations = [
            DestinationConfig(
                region=dest_region,
                account_role_arn=dest_account_role_arn,
                secret_names=dest_secret_names,
                secret_names_cache_ttl=dest_secret_names_cache_ttl,
                kms_key_id=kms_key_id
            )
        ]

    # Common parameters
    transform_mode = os.environ.get('TRANSFORM_MODE', 'auto').strip()
    log_level = os.environ.get('LOG_LEVEL', 'INFO').strip()

    # Boolean field
    enable_metrics_str = os.environ.get('ENABLE_METRICS', 'true').strip().lower()
    enable_metrics = enable_metrics_str in ('true', '1', 'yes', 'on')

    # Optional ARNs
    dlq_arn = os.environ.get('DLQ_ARN', '').strip() or None

    # Numeric fields with defaults
    timeout_seconds = int(os.environ.get('TIMEOUT_SECONDS', '5'))
    max_secret_size = int(os.environ.get('MAX_SECRET_SIZE', '65536'))

    # Centralized filtering (SECRETS_FILTER)
    secrets_filter = os.environ.get('SECRETS_FILTER', '').strip() or None
    secrets_filter_cache_ttl = int(os.environ.get('SECRETS_FILTER_CACHE_TTL', '300'))

    config = ReplicatorConfig(
        destinations=destinations,
        transform_mode=transform_mode,
        log_level=log_level,
        enable_metrics=enable_metrics,
        dlq_arn=dlq_arn,
        timeout_seconds=timeout_seconds,
        max_secret_size=max_secret_size,
        secrets_filter=secrets_filter,
        secrets_filter_cache_ttl=secrets_filter_cache_ttl
    )

    # Set legacy compatibility fields for backward compatibility with existing code
    if len(destinations) > 0:
        config.dest_region = destinations[0].region
        config.dest_account_role_arn = destinations[0].account_role_arn
        config.dest_secret_names = destinations[0].secret_names
        config.dest_secret_names_cache_ttl = destinations[0].secret_names_cache_ttl
        config.kms_key_id = destinations[0].kms_key_id

    return config


def is_cross_account(destination: DestinationConfig) -> bool:
    """
    Check if a destination requires cross-account replication.

    Args:
        destination: DestinationConfig object

    Returns:
        True if cross-account replication is configured, False otherwise

    Examples:
        >>> dest = DestinationConfig(region='us-west-2')
        >>> is_cross_account(dest)
        False
        >>> dest = DestinationConfig(
        ...     region='us-west-2',
        ...     account_role_arn='arn:aws:iam::999:role/MyRole'
        ... )
        >>> is_cross_account(dest)
        True
    """
    return bool(destination.account_role_arn)
