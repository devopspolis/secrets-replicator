"""
Configuration management for secrets replicator.

Loads configuration from environment variables with validation.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# Hardcoded prefixes for security and consistency
TRANSFORMATION_SECRET_PREFIX = 'secrets-replicator/transformations/'
FILTER_SECRET_PREFIX = 'secrets-replicator/filters/'
NAME_MAPPING_PREFIX = 'secrets-replicator/names/'
DEFAULT_DESTINATIONS_SECRET = 'secrets-replicator/config/destinations'


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
    variables: Optional[Dict[str, str]] = None   # Custom variables for transformation expansion

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

    # SECRETS_FILTER configuration
    secrets_filter: Optional[str] = None          # Comma-separated list of filter secret names
    secrets_filter_cache_ttl: int = 300           # Cache TTL in seconds (5 minutes)

    # Advanced options
    timeout_seconds: int = 5                      # Regex timeout
    max_secret_size: int = 65536                  # Max secret size (64KB)

    # Default values for destination configurations (can be overridden per-destination)
    default_secret_names: Optional[str] = None    # Default name mapping secret
    default_region: Optional[str] = None          # Default destination region
    default_role_arn: Optional[str] = None        # Default cross-account role ARN
    secret_names_cache_ttl: int = 300             # Cache TTL for name mappings (seconds)
    default_kms_key_id: Optional[str] = None      # Default KMS key ID for encryption

    # Internal/computed fields
    source_region: Optional[str] = field(default=None, init=False)
    source_account_id: Optional[str] = field(default=None, init=False)

    # Configuration secret name
    config_secret: str = DEFAULT_DESTINATIONS_SECRET

    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()

    def validate(self):
        """
        Validate configuration values.

        Note: Destinations list validation is skipped if empty, as destinations
        are loaded later via load_destinations().

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate destinations list (if loaded)
        if self.destinations:
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

    Note: destinations list is initially empty and must be loaded via
    load_destinations() after creating a Secrets Manager client.

    Environment variables:
        CONFIG_SECRET: Name of Secrets Manager secret containing configuration
            (default: 'secrets-replicator/config/destinations')
        SECRETS_FILTER: Comma-separated list of filter secret names that map
            secret patterns to transformation names. If not set, all secrets
            pass through without transformation.
        SECRETS_FILTER_CACHE_TTL: Cache TTL for filter config in seconds (default: 300)
        DEFAULT_SECRET_NAMES: Default name mapping secret for destinations
        DEFAULT_REGION: Default destination region
        DEFAULT_ROLE_ARN: Default cross-account IAM role ARN
        SECRET_NAMES_CACHE_TTL: Cache TTL for name mappings in seconds (default: 300)
        KMS_KEY_ID: Default KMS key ID for destination encryption
        TRANSFORM_MODE: Transformation mode (default: 'auto')
        LOG_LEVEL: Log level (default: 'INFO')
        ENABLE_METRICS: Enable CloudWatch metrics (default: 'true')
        DLQ_ARN: Dead Letter Queue ARN
        TIMEOUT_SECONDS: Regex timeout (default: 5)
        MAX_SECRET_SIZE: Maximum secret size (default: 65536)

    Returns:
        ReplicatorConfig object with empty destinations list

    Raises:
        ConfigurationError: If configuration is invalid

    Examples:
        >>> import os
        >>> os.environ['CONFIG_SECRET'] = 'my-app/config/destinations'
        >>> config = load_config_from_env()
        >>> config.config_secret
        'my-app/config/destinations'
    """
    # Get configuration secret name (defaults to hardcoded value)
    config_secret = os.environ.get('CONFIG_SECRET', '').strip() or DEFAULT_DESTINATIONS_SECRET

    # Default values for destination configurations
    default_secret_names = os.environ.get('DEFAULT_SECRET_NAMES', '').strip() or None
    default_region = os.environ.get('DEFAULT_REGION', '').strip() or None
    default_role_arn = os.environ.get('DEFAULT_ROLE_ARN', '').strip() or None
    secret_names_cache_ttl = int(os.environ.get('SECRET_NAMES_CACHE_TTL', '300'))
    default_kms_key_id = os.environ.get('KMS_KEY_ID', '').strip() or None

    # SECRETS_FILTER configuration
    secrets_filter = os.environ.get('SECRETS_FILTER', '').strip() or None
    secrets_filter_cache_ttl = int(os.environ.get('SECRETS_FILTER_CACHE_TTL', '300'))

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

    config = ReplicatorConfig(
        destinations=[],  # Empty - must be loaded via load_destinations()
        transform_mode=transform_mode,
        log_level=log_level,
        enable_metrics=enable_metrics,
        dlq_arn=dlq_arn,
        secrets_filter=secrets_filter,
        secrets_filter_cache_ttl=secrets_filter_cache_ttl,
        timeout_seconds=timeout_seconds,
        max_secret_size=max_secret_size,
        default_secret_names=default_secret_names,
        default_region=default_region,
        default_role_arn=default_role_arn,
        secret_names_cache_ttl=secret_names_cache_ttl,
        default_kms_key_id=default_kms_key_id,
        config_secret=config_secret
    )

    return config


def load_destinations(config: ReplicatorConfig, secrets_manager_client) -> None:
    """
    Load destination configurations from Secrets Manager secret.

    Updates config.destinations in-place by loading from the configured
    destinations secret.

    Args:
        config: ReplicatorConfig object to update
        secrets_manager_client: Boto3 Secrets Manager client for source region

    Raises:
        ConfigurationError: If destinations secret doesn't exist, is invalid,
            or contains no destinations

    Examples:
        >>> config = load_config_from_env()
        >>> load_destinations(config, sm_client)
        >>> len(config.destinations)
        2
    """
    try:
        response = secrets_manager_client.get_secret(secret_id=config.config_secret)
        destinations_json = response.secret_string
    except Exception as e:
        error_msg = str(e)
        if 'ResourceNotFoundException' in error_msg or 'not found' in error_msg.lower():
            raise ConfigurationError(
                f"Configuration secret not found: {config.config_secret}. "
                f"Please create this secret with a JSON array of destination configurations. "
                f"Example: '[{{\"region\":\"us-east-1\"}}]'"
            )
        raise ConfigurationError(f"Failed to load configuration secret '{config.config_secret}': {e}")

    # Parse JSON
    try:
        destinations_data = json.loads(destinations_json)
    except json.JSONDecodeError as e:
        raise ConfigurationError(
            f"Invalid JSON in configuration secret '{config.config_secret}': {e}"
        )

    if not isinstance(destinations_data, list):
        raise ConfigurationError(
            f"Configuration secret '{config.config_secret}' must contain a JSON array, got {type(destinations_data).__name__}"
        )

    if len(destinations_data) == 0:
        raise ConfigurationError(
            f"Configuration secret '{config.config_secret}' must contain at least one destination"
        )

    # Parse each destination
    destinations = []
    for i, dest_data in enumerate(destinations_data):
        if not isinstance(dest_data, dict):
            raise ConfigurationError(
                f"Destination {i} in secret '{config.config_secret}' must be a JSON object, got {type(dest_data).__name__}"
            )

        try:
            # Parse variables (can be dict or None)
            variables = dest_data.get('variables')
            if variables is not None and not isinstance(variables, dict):
                raise ConfigurationError(
                    f"Destination {i}: 'variables' must be a JSON object (dict), got {type(variables).__name__}"
                )

            dest = DestinationConfig(
                region=dest_data.get('region', ''),
                account_role_arn=dest_data.get('account_role_arn') or dest_data.get('accountRoleArn'),
                secret_names=dest_data.get('secret_names') or dest_data.get('secretNames'),
                secret_names_cache_ttl=dest_data.get('secret_names_cache_ttl') or
                                      dest_data.get('secretNamesCacheTTL') or 300,
                kms_key_id=dest_data.get('kms_key_id') or dest_data.get('kmsKeyId'),
                variables=variables
            )
            destinations.append(dest)
        except (TypeError, ConfigurationError) as e:
            raise ConfigurationError(f"Invalid destination {i} in secret '{config.config_secret}': {e}")

    # Update config in-place
    config.destinations = destinations


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
