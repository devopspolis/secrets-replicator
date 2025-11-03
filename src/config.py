"""
Configuration management for secrets replicator.

Loads configuration from environment variables with validation.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List


class ConfigurationError(Exception):
    """Raised when configuration is invalid"""
    pass


@dataclass
class ReplicatorConfig:
    """Configuration for the secrets replicator Lambda function"""

    # Required fields
    dest_region: str                        # Destination AWS region

    # Optional fields
    dest_secret_name: Optional[str] = None  # Override destination secret name
    dest_account_role_arn: Optional[str] = None  # Role ARN for cross-account
    transform_mode: str = 'sed'                   # Transformation mode (sed|json)
    log_level: str = 'INFO'                       # Log level
    enable_metrics: bool = True                   # Enable CloudWatch metrics
    kms_key_id: Optional[str] = None              # KMS key for destination encryption
    dlq_arn: Optional[str] = None                 # Dead Letter Queue ARN

    # Advanced options
    timeout_seconds: int = 5                      # Regex timeout
    max_secret_size: int = 65536                  # Max secret size (64KB)

    # Filtering options
    source_secret_pattern: Optional[str] = None   # Regex pattern for filtering source secrets
    source_secret_list: List[str] = field(default_factory=list)  # Explicit list of secret names
    source_include_tags: List[tuple[str, str]] = field(default_factory=list)  # Include tags (key, value)
    source_exclude_tags: List[tuple[str, str]] = field(default_factory=list)  # Exclude tags (key, value)
    transformation_secret_prefix: str = 'secrets-replicator/transformations/'  # Prefix for transformation secrets

    # Internal/computed fields
    source_region: Optional[str] = field(default=None, init=False)
    source_account_id: Optional[str] = field(default=None, init=False)

    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()

    def validate(self):
        """
        Validate configuration values.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate required fields
        if not self.dest_region:
            raise ConfigurationError("dest_region is required")

        # Validate region format (basic check)
        if not self._is_valid_region(self.dest_region):
            raise ConfigurationError(f"Invalid dest_region format: {self.dest_region}")

        # Validate transform mode
        valid_modes = ['sed', 'json']
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

        # Validate role ARN format (basic check)
        if self.dest_account_role_arn and not self.dest_account_role_arn.startswith('arn:'):
            raise ConfigurationError(
                f"Invalid dest_account_role_arn format: {self.dest_account_role_arn}"
            )

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

        # Validate transformation secret prefix
        if not self.transformation_secret_prefix:
            raise ConfigurationError("transformation_secret_prefix cannot be empty")

        # Validate regex pattern if provided
        if self.source_secret_pattern:
            try:
                import re
                re.compile(self.source_secret_pattern)
            except re.error as e:
                raise ConfigurationError(
                    f"Invalid source_secret_pattern regex: {e}"
                )

    @staticmethod
    def _is_valid_region(region: str) -> bool:
        """
        Basic validation for AWS region format.

        Args:
            region: AWS region string

        Returns:
            True if region looks valid, False otherwise
        """
        if not region:
            return False

        # Basic pattern: us-east-1, eu-west-2, ap-southeast-1, etc.
        parts = region.split('-')
        if len(parts) < 3:
            return False

        # Common region prefixes
        valid_prefixes = [
            'us', 'eu', 'ap', 'ca', 'sa', 'af', 'me', 'il', 'cn', 'us-gov'
        ]

        # Check if starts with valid prefix
        region_prefix = parts[0] if parts[0] != 'us' else f"{parts[0]}-{parts[1]}"
        if region_prefix == 'us-gov':
            return len(parts) >= 3  # us-gov-east-1, etc.

        return parts[0] in valid_prefixes or region_prefix in valid_prefixes


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
        DEST_REGION (required): Destination AWS region
        DEST_SECRET_NAME: Override destination secret name
        DEST_ACCOUNT_ROLE_ARN: IAM role ARN for cross-account access
        TRANSFORM_MODE: Transformation mode (default: 'sed')
        LOG_LEVEL: Log level (default: 'INFO')
        ENABLE_METRICS: Enable CloudWatch metrics (default: 'true')
        KMS_KEY_ID: KMS key ID for destination secret encryption
        DLQ_ARN: Dead Letter Queue ARN
        TIMEOUT_SECONDS: Regex timeout (default: 5)
        MAX_SECRET_SIZE: Maximum secret size (default: 65536)
        SOURCE_SECRET_PATTERN: Regex pattern for filtering source secrets
        SOURCE_SECRET_LIST: Comma-separated list of secret names to include
        SOURCE_INCLUDE_TAGS: Comma-separated tag filters to include (Key=Value,Key2=Value2)
        SOURCE_EXCLUDE_TAGS: Comma-separated tag filters to exclude (Key=Value,Key2=Value2)
        TRANSFORMATION_SECRET_PREFIX: Prefix for transformation secrets (default: 'transformations/')

    Returns:
        ReplicatorConfig object

    Raises:
        ConfigurationError: If required config is missing or invalid

    Examples:
        >>> import os
        >>> os.environ['DEST_REGION'] = 'us-west-2'
        >>> config = load_config_from_env()
        >>> config.dest_region
        'us-west-2'
    """
    # Required fields
    dest_region = os.environ.get('DEST_REGION', '').strip()
    if not dest_region:
        raise ConfigurationError("Missing required environment variable: DEST_REGION")

    # Optional fields
    dest_secret_name = os.environ.get('DEST_SECRET_NAME', '').strip() or None
    dest_account_role_arn = os.environ.get('DEST_ACCOUNT_ROLE_ARN', '').strip() or None
    transform_mode = os.environ.get('TRANSFORM_MODE', 'sed').strip()
    log_level = os.environ.get('LOG_LEVEL', 'INFO').strip()

    # Boolean field
    enable_metrics_str = os.environ.get('ENABLE_METRICS', 'true').strip().lower()
    enable_metrics = enable_metrics_str in ('true', '1', 'yes', 'on')

    # Optional ARNs
    kms_key_id = os.environ.get('KMS_KEY_ID', '').strip() or None
    dlq_arn = os.environ.get('DLQ_ARN', '').strip() or None

    # Numeric fields with defaults
    timeout_seconds = int(os.environ.get('TIMEOUT_SECONDS', '5'))
    max_secret_size = int(os.environ.get('MAX_SECRET_SIZE', '65536'))

    # Filtering options
    source_secret_pattern = os.environ.get('SOURCE_SECRET_PATTERN', '').strip() or None
    source_secret_list_str = os.environ.get('SOURCE_SECRET_LIST', '').strip()
    source_secret_list = [s.strip() for s in source_secret_list_str.split(',') if s.strip()] if source_secret_list_str else []

    source_include_tags_str = os.environ.get('SOURCE_INCLUDE_TAGS', '').strip()
    source_include_tags = parse_tag_filters(source_include_tags_str)

    source_exclude_tags_str = os.environ.get('SOURCE_EXCLUDE_TAGS', '').strip()
    source_exclude_tags = parse_tag_filters(source_exclude_tags_str)

    transformation_secret_prefix = os.environ.get('TRANSFORMATION_SECRET_PREFIX', 'secrets-replicator/transformations/').strip()

    return ReplicatorConfig(
        dest_region=dest_region,
        dest_secret_name=dest_secret_name,
        dest_account_role_arn=dest_account_role_arn,
        transform_mode=transform_mode,
        log_level=log_level,
        enable_metrics=enable_metrics,
        kms_key_id=kms_key_id,
        dlq_arn=dlq_arn,
        timeout_seconds=timeout_seconds,
        max_secret_size=max_secret_size,
        source_secret_pattern=source_secret_pattern,
        source_secret_list=source_secret_list,
        source_include_tags=source_include_tags,
        source_exclude_tags=source_exclude_tags,
        transformation_secret_prefix=transformation_secret_prefix
    )


def is_cross_account(config: ReplicatorConfig) -> bool:
    """
    Check if replication is cross-account.

    Args:
        config: ReplicatorConfig object

    Returns:
        True if cross-account replication is configured, False otherwise

    Examples:
        >>> config = ReplicatorConfig(dest_region='us-west-2')
        >>> is_cross_account(config)
        False
        >>> config = ReplicatorConfig(
        ...     dest_region='us-west-2',
        ...     dest_account_role_arn='arn:aws:iam::999:role/MyRole'
        ... )
        >>> is_cross_account(config)
        True
    """
    return bool(config.dest_account_role_arn)
