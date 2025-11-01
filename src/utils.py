"""
Utility functions for the secrets replicator
"""

import re
from typing import Dict, Any, Optional


def mask_secret(secret: str, show_chars: int = 4) -> str:
    """
    Mask a secret value for logging purposes.

    Shows only the first and last N characters, replacing the middle with asterisks.
    This allows for debugging without exposing the full secret.

    Args:
        secret: Secret value to mask
        show_chars: Number of characters to show at start and end

    Returns:
        Masked secret string

    Examples:
        >>> mask_secret('my_secret_password', 4)
        'my_s***word'
        >>> mask_secret('short', 4)
        'sh**t'
        >>> mask_secret('a', 4)
        '*'
    """
    if not secret:
        return ''

    secret_len = len(secret)

    # If secret is very short, just show asterisks
    if secret_len <= 2:
        return '*' * secret_len

    # If secret is shorter than show_chars * 2, adjust
    if secret_len <= show_chars * 2:
        show_chars = max(1, secret_len // 3)

    # Show first N and last N characters
    start = secret[:show_chars]
    end = secret[-show_chars:]
    masked_len = secret_len - (show_chars * 2)

    return f"{start}{'*' * masked_len}{end}"


def validate_regex(pattern: str, max_length: int = 1000) -> bool:
    """
    Validate that a regex pattern is safe to use.

    Checks for:
    - Valid regex syntax
    - Not excessively long (potential ReDoS)
    - No obvious ReDoS patterns (nested quantifiers)

    Args:
        pattern: Regex pattern to validate
        max_length: Maximum allowed pattern length

    Returns:
        True if pattern is safe, False otherwise

    Examples:
        >>> validate_regex(r'\\d+')
        True
        >>> validate_regex('a' * 2000)
        False
    """
    # Check length
    if len(pattern) > max_length:
        return False

    # Check if it's a valid regex
    try:
        re.compile(pattern)
    except re.error:
        return False

    # Check for potentially dangerous patterns
    # Nested quantifiers like (a+)+ or (a*)*
    dangerous_patterns = [
        r'\([^)]*[*+]\)[*+]',  # (x+)+ or (x*)*
        r'\([^)]*[*+]\)\{',    # (x+){n,m}
    ]

    for dangerous in dangerous_patterns:
        if re.search(dangerous, pattern):
            return False

    return True


def get_secret_metadata(secret_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from Secrets Manager GetSecretValue response.

    Extracts only non-sensitive fields like ARN, version, creation date, etc.
    NEVER includes the actual secret value.

    Args:
        secret_response: Response from secretsmanager.get_secret_value()

    Returns:
        Dictionary containing only metadata fields

    Examples:
        >>> response = {
        ...     'ARN': 'arn:aws:secretsmanager:us-east-1:123:secret:test',
        ...     'Name': 'test-secret',
        ...     'VersionId': 'v1',
        ...     'SecretString': 'sensitive_value',
        ...     'CreatedDate': '2025-01-01'
        ... }
        >>> metadata = get_secret_metadata(response)
        >>> 'SecretString' in metadata
        False
        >>> metadata['Name']
        'test-secret'
    """
    # Fields to extract (non-sensitive only)
    metadata_fields = [
        'ARN',
        'Name',
        'VersionId',
        'VersionStages',
        'CreatedDate',
        'ResponseMetadata'
    ]

    metadata = {}
    for field in metadata_fields:
        if field in secret_response:
            metadata[field] = secret_response[field]

    # Add indication of secret type without the value
    if 'SecretString' in secret_response:
        metadata['SecretType'] = 'string'
        metadata['SecretSize'] = len(secret_response['SecretString'])
    elif 'SecretBinary' in secret_response:
        metadata['SecretType'] = 'binary'
        metadata['SecretSize'] = len(secret_response['SecretBinary'])

    return metadata


def format_arn(
    service: str,
    region: str,
    account_id: str,
    resource_type: str,
    resource_id: str
) -> str:
    """
    Format an AWS ARN string.

    Args:
        service: AWS service name (e.g., 'secretsmanager')
        region: AWS region (e.g., 'us-east-1')
        account_id: AWS account ID
        resource_type: Resource type (e.g., 'secret')
        resource_id: Resource identifier

    Returns:
        Formatted ARN string

    Examples:
        >>> format_arn('secretsmanager', 'us-east-1', '123456789012', 'secret', 'my-secret')
        'arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret'
    """
    return f"arn:aws:{service}:{region}:{account_id}:{resource_type}:{resource_id}"


def parse_arn(arn: str) -> Optional[Dict[str, str]]:
    """
    Parse an AWS ARN into its components.

    Args:
        arn: AWS ARN string

    Returns:
        Dictionary with ARN components, or None if invalid

    Examples:
        >>> arn = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret'
        >>> components = parse_arn(arn)
        >>> components['service']
        'secretsmanager'
        >>> components['region']
        'us-east-1'
        >>> components['resource_id']
        'my-secret'
    """
    # ARN format: arn:partition:service:region:account-id:resource-type:resource-id
    # or: arn:partition:service:region:account-id:resource-type/resource-id

    arn_pattern = r'^arn:([^:]+):([^:]+):([^:]*):([^:]*):(.+)$'
    match = re.match(arn_pattern, arn)

    if not match:
        return None

    partition, service, region, account_id, resource = match.groups()

    # Parse resource (can be "type:id" or "type/id")
    resource_parts = resource.split(':', 1)
    if len(resource_parts) == 2:
        resource_type, resource_id = resource_parts
    else:
        # Try slash separator
        resource_parts = resource.split('/', 1)
        if len(resource_parts) == 2:
            resource_type, resource_id = resource_parts
        else:
            # No separator - entire thing is resource
            resource_type = ''
            resource_id = resource

    return {
        'partition': partition,
        'service': service,
        'region': region,
        'account_id': account_id,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'resource': resource
    }


def sanitize_log_message(message: str, patterns: list = None) -> str:
    """
    Sanitize log message by removing potential secret values.

    Removes common patterns that might contain secrets:
    - Long base64 strings
    - JWT tokens
    - API keys
    - Passwords in URLs

    Args:
        message: Log message to sanitize
        patterns: Additional regex patterns to remove (optional)

    Returns:
        Sanitized log message

    Examples:
        >>> sanitize_log_message('password=secret123 other text')
        'password=*** other text'
    """
    if patterns is None:
        patterns = []

    # Default patterns to remove
    default_patterns = [
        (r'password\s*=\s*[^\s]+', r'password=***'),
        (r'api[_-]?key\s*=\s*[^\s]+', r'api_key=***'),
        (r'secret\s*=\s*[^\s]+', r'secret=***'),
        (r'token\s*=\s*[^\s]+', r'token=***'),
        # Base64 strings longer than 50 chars
        (r'[A-Za-z0-9+/]{50,}={0,2}', r'[BASE64_REDACTED]'),
        # JWT tokens
        (r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*', r'[JWT_REDACTED]'),
    ]

    sanitized = message

    # Apply default patterns
    for pattern, replacement in default_patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # Apply custom patterns
    for pattern in patterns:
        if isinstance(pattern, tuple) and len(pattern) == 2:
            sanitized = re.sub(pattern[0], pattern[1], sanitized, flags=re.IGNORECASE)

    return sanitized


def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    Truncate a string to a maximum length.

    Args:
        text: String to truncate
        max_length: Maximum length (including suffix)
        suffix: Suffix to add when truncated

    Returns:
        Truncated string

    Examples:
        >>> truncate_string('a' * 200, 50)
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa...'
        >>> truncate_string('short', 50)
        'short'
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def is_binary_data(data: bytes) -> bool:
    """
    Check if data appears to be binary (not text).

    Uses a heuristic: if data contains null bytes or high percentage of
    non-printable characters, it's likely binary.

    Args:
        data: Bytes to check

    Returns:
        True if data appears binary, False if it appears to be text

    Examples:
        >>> is_binary_data(b'Hello World')
        False
        >>> is_binary_data(b'\\x00\\x01\\x02\\x03')
        True
    """
    if not data:
        return False

    # Check for null bytes (strong indicator of binary)
    if b'\x00' in data:
        return True

    # Count non-printable characters
    printable_chars = set(range(32, 127)) | {9, 10, 13}  # Include tab, newline, carriage return
    non_printable_count = sum(1 for byte in data if byte not in printable_chars)

    # If more than 30% non-printable, consider it binary
    threshold = 0.3
    return (non_printable_count / len(data)) > threshold


def get_region_from_arn(arn: str) -> Optional[str]:
    """
    Extract AWS region from an ARN.

    Args:
        arn: AWS ARN string

    Returns:
        Region string, or None if not found

    Examples:
        >>> get_region_from_arn('arn:aws:secretsmanager:us-east-1:123:secret:test')
        'us-east-1'
        >>> get_region_from_arn('invalid')
        None
    """
    components = parse_arn(arn)
    if components:
        return components['region']
    return None


def get_account_from_arn(arn: str) -> Optional[str]:
    """
    Extract AWS account ID from an ARN.

    Args:
        arn: AWS ARN string

    Returns:
        Account ID string, or None if not found

    Examples:
        >>> get_account_from_arn('arn:aws:secretsmanager:us-east-1:123456789012:secret:test')
        '123456789012'
    """
    components = parse_arn(arn)
    if components:
        return components['account_id']
    return None
