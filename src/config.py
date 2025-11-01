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
    sedfile_s3_bucket: Optional[str] = None      # S3 bucket for sedfile
    sedfile_s3_key: Optional[str] = None         # S3 key for sedfile
    transform_mode: str = 'sed'                   # Transformation mode (sed|json)
    log_level: str = 'INFO'                       # Log level
    enable_metrics: bool = True                   # Enable CloudWatch metrics
    dlq_arn: Optional[str] = None                 # Dead Letter Queue ARN

    # Advanced options
    timeout_seconds: int = 5                      # Regex timeout
    max_secret_size: int = 65536                  # Max secret size (64KB)

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

        # Validate S3 configuration (if one is set, both should be set)
        if bool(self.sedfile_s3_bucket) != bool(self.sedfile_s3_key):
            raise ConfigurationError(
                "Both sedfile_s3_bucket and sedfile_s3_key must be set together, or both empty"
            )

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


def load_config_from_env() -> ReplicatorConfig:
    """
    Load configuration from environment variables.

    Environment variables:
        DEST_REGION (required): Destination AWS region
        DEST_SECRET_NAME: Override destination secret name
        DEST_ACCOUNT_ROLE_ARN: IAM role ARN for cross-account access
        SEDFILE_S3_BUCKET: S3 bucket containing sedfile
        SEDFILE_S3_KEY: S3 key for sedfile
        TRANSFORM_MODE: Transformation mode (default: 'sed')
        LOG_LEVEL: Log level (default: 'INFO')
        ENABLE_METRICS: Enable CloudWatch metrics (default: 'true')
        DLQ_ARN: Dead Letter Queue ARN
        TIMEOUT_SECONDS: Regex timeout (default: 5)
        MAX_SECRET_SIZE: Maximum secret size (default: 65536)

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
    sedfile_s3_bucket = os.environ.get('SEDFILE_S3_BUCKET', '').strip() or None
    sedfile_s3_key = os.environ.get('SEDFILE_S3_KEY', '').strip() or None
    transform_mode = os.environ.get('TRANSFORM_MODE', 'sed').strip()
    log_level = os.environ.get('LOG_LEVEL', 'INFO').strip()

    # Boolean field
    enable_metrics_str = os.environ.get('ENABLE_METRICS', 'true').strip().lower()
    enable_metrics = enable_metrics_str in ('true', '1', 'yes', 'on')

    # Optional ARNs
    dlq_arn = os.environ.get('DLQ_ARN', '').strip() or None

    # Numeric fields with defaults
    timeout_seconds = int(os.environ.get('TIMEOUT_SECONDS', '5'))
    max_secret_size = int(os.environ.get('MAX_SECRET_SIZE', '65536'))

    return ReplicatorConfig(
        dest_region=dest_region,
        dest_secret_name=dest_secret_name,
        dest_account_role_arn=dest_account_role_arn,
        sedfile_s3_bucket=sedfile_s3_bucket,
        sedfile_s3_key=sedfile_s3_key,
        transform_mode=transform_mode,
        log_level=log_level,
        enable_metrics=enable_metrics,
        dlq_arn=dlq_arn,
        timeout_seconds=timeout_seconds,
        max_secret_size=max_secret_size
    )


def get_sedfile_location(config: ReplicatorConfig) -> tuple[str, Optional[str]]:
    """
    Determine sedfile location based on configuration.

    Returns:
        Tuple of (location_type, location_value)
        - ('s3', 's3://bucket/key') if S3 is configured
        - ('bundled', None) if using bundled sedfile

    Args:
        config: ReplicatorConfig object

    Returns:
        Tuple of location type and value

    Examples:
        >>> config = ReplicatorConfig(dest_region='us-west-2')
        >>> get_sedfile_location(config)
        ('bundled', None)
        >>> config = ReplicatorConfig(
        ...     dest_region='us-west-2',
        ...     sedfile_s3_bucket='my-bucket',
        ...     sedfile_s3_key='sedfiles/default.sed'
        ... )
        >>> get_sedfile_location(config)
        ('s3', 's3://my-bucket/sedfiles/default.sed')
    """
    if config.sedfile_s3_bucket and config.sedfile_s3_key:
        s3_path = f"s3://{config.sedfile_s3_bucket}/{config.sedfile_s3_key}"
        return ('s3', s3_path)
    else:
        return ('bundled', None)


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
