"""
Filter configuration management for secrets replicator.

Handles loading, caching, and pattern matching for SECRETS_FILTER configuration.
"""

import json
import logging
import re
import time
from typing import Dict, Optional, Tuple, Union

from botocore.exceptions import ClientError

from config import TRANSFORMATION_SECRET_PREFIX, FILTER_SECRET_PREFIX


logger = logging.getLogger(__name__)


# Global cache for filter configuration (persists across Lambda invocations)
_filter_cache = {
    'data': None,           # Dict[str, Optional[str]] - merged filters
    'loaded_at': 0,         # float - timestamp
    'ttl': 300,            # int - cache TTL in seconds
    'source_list': None    # str - comma-separated filter secret names
}


def load_filter_configuration(filter_list: str, client) -> Dict[str, Optional[str]]:
    """
    Load filter configuration from comma-separated list of secret names.

    Args:
        filter_list: Comma-separated list of Secrets Manager secret names
        client: Boto3 Secrets Manager client

    Returns:
        Dict mapping secret patterns to transformation names

    Example:
        Input: "secrets-replicator/filters/prod,secrets-replicator/filters/db"
        Output: {
            "app/prod/*": "region-swap",
            "db/prod/*": "connection-string-transform",
            "critical-secret-1": None  # No transformation
        }

    Raises:
        ValueError: If filter secret contains invalid JSON
        ClientError: If filter secret cannot be loaded
    """
    if not filter_list or not filter_list.strip():
        logger.info("No filter list provided, returning empty filters")
        return {}

    merged_filters = {}
    filter_secrets = [s.strip() for s in filter_list.split(',') if s.strip()]

    logger.info(f"Loading {len(filter_secrets)} filter secrets")

    for secret_name in filter_secrets:
        try:
            logger.debug(f"Loading filter secret: {secret_name}")
            response = client.get_secret(secret_id=secret_name)

            # Parse JSON
            try:
                filter_data = json.loads(response.secret_string)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in filter secret {secret_name}: {e}")
                raise ValueError(f"Filter secret {secret_name} contains invalid JSON: {e}")

            # Validate filter data is a dict
            if not isinstance(filter_data, dict):
                logger.error(f"Filter secret {secret_name} must be a JSON object, got {type(filter_data)}")
                raise ValueError(f"Filter secret {secret_name} must be a JSON object")

            # Merge filters (later filters override earlier ones)
            for pattern, transform_name in filter_data.items():
                # Normalize empty string and None to None
                if transform_name == "" or transform_name is None:
                    merged_filters[pattern] = None
                    logger.debug(f"Filter pattern '{pattern}' -> no transformation")
                else:
                    merged_filters[pattern] = transform_name
                    logger.debug(f"Filter pattern '{pattern}' -> transformation '{transform_name}'")

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"Failed to load filter secret {secret_name}: {error_code} - {e}")
            # Continue with other filters rather than failing completely
            continue
        except Exception as e:
            logger.error(f"Unexpected error loading filter secret {secret_name}: {e}", exc_info=True)
            # Continue with other filters
            continue

    logger.info(f"Loaded {len(merged_filters)} filter patterns from {len(filter_secrets)} filter secrets")
    return merged_filters


def get_cached_filters(filter_list: str, ttl: int, client) -> Dict[str, Optional[str]]:
    """
    Load filter configuration with caching.

    Cache invalidation:
    - TTL expires (default 5 minutes)
    - Filter list changes (different secrets)

    Args:
        filter_list: Comma-separated list of filter secret names
        ttl: Cache TTL in seconds
        client: Boto3 Secrets Manager client

    Returns:
        Dict mapping secret patterns to transformation names
    """
    now = time.time()

    # Check if cache is valid
    cache_valid = (
        _filter_cache['data'] is not None and
        _filter_cache['source_list'] == filter_list and
        (now - _filter_cache['loaded_at']) < _filter_cache['ttl']
    )

    if cache_valid:
        logger.debug("Using cached filter configuration")
        return _filter_cache['data']

    # Load fresh configuration
    logger.info(f"Loading fresh filter configuration from: {filter_list}")
    filters = load_filter_configuration(filter_list, client)

    # Update cache
    _filter_cache['data'] = filters
    _filter_cache['loaded_at'] = now
    _filter_cache['ttl'] = ttl
    _filter_cache['source_list'] = filter_list

    logger.info(f"Filter configuration cached (TTL: {ttl}s)")
    return filters


def match_secret_pattern(secret_name: str, pattern: str) -> bool:
    """
    Match a secret name against a glob pattern.

    Pattern matching rules:
    - Exact match: "mysecret" matches only "mysecret"
    - Prefix wildcard: "app/*" matches "app/prod", "app/staging/db", etc.
    - Suffix wildcard: "*/prod" matches "app/prod", "db/prod", etc.
    - Middle wildcard: "app/*/db" matches "app/prod/db", "app/staging/db", etc.
    - Multiple wildcards: "app/*/prod/*" matches "app/team1/prod/db", etc.

    Args:
        secret_name: Name of the secret to match
        pattern: Glob pattern (may contain *)

    Returns:
        True if pattern matches, False otherwise

    Examples:
        >>> match_secret_pattern("app/prod/db", "app/*")
        True
        >>> match_secret_pattern("app/prod/db", "app/prod/*")
        True
        >>> match_secret_pattern("app/prod/db", "db/*")
        False
        >>> match_secret_pattern("app/prod", "*/prod")
        True
        >>> match_secret_pattern("app/staging", "*/prod")
        False
    """
    # Exact match (no wildcard)
    if '*' not in pattern:
        return secret_name == pattern

    # Convert glob pattern to regex
    # Escape special regex characters except *
    escaped_pattern = re.escape(pattern)

    # Replace escaped \* with regex .*
    regex_pattern = escaped_pattern.replace(r'\*', '.*')

    # Anchor the pattern
    regex_pattern = f'^{regex_pattern}$'

    # Compile and match
    try:
        compiled_pattern = re.compile(regex_pattern)
        return bool(compiled_pattern.match(secret_name))
    except re.error as e:
        logger.error(f"Invalid regex pattern generated from '{pattern}': {e}")
        return False


def find_matching_filter(secret_name: str, filters: Dict[str, Optional[str]]) -> Union[Optional[str], bool]:
    """
    Find transformation for a secret based on filter patterns.

    Args:
        secret_name: Name of the secret to replicate
        filters: Dict of pattern -> transformation_name mappings

    Returns:
        - Transformation name (str) if match found with transformation
        - None if match found without transformation (replicate as-is)
        - False if no match found (do not replicate)

    Pattern matching:
        - Exact match has highest priority
        - Wildcard patterns checked in order
        - First match wins

    Examples:
        >>> filters = {"app/prod/*": "region-swap", "critical-secret-1": None}
        >>> find_matching_filter("app/prod/db", filters)
        'region-swap'
        >>> find_matching_filter("critical-secret-1", filters)
        None
        >>> find_matching_filter("other-secret", filters)
        False
    """
    # Check exact match first (highest priority)
    if secret_name in filters:
        logger.debug(f"Exact match found for '{secret_name}'")
        return filters[secret_name]

    # Check wildcard patterns
    for pattern, transform_name in filters.items():
        if '*' in pattern:
            if match_secret_pattern(secret_name, pattern):
                logger.debug(f"Pattern match: '{secret_name}' matches '{pattern}'")
                return transform_name

    # No match found
    logger.debug(f"No filter match for '{secret_name}'")
    return False


def should_replicate_secret(secret_name: str, config, client) -> Tuple[bool, Optional[str]]:
    """
    Determine if secret should be replicated and which transformation to use.

    Filtering logic:
    1. Hardcoded exclusions (transformation secrets, filter secrets)
    2. Load and check filters from SECRETS_FILTER
    3. Find matching pattern
    4. Return replication decision and transformation name

    Args:
        secret_name: Name of the secret to check
        config: ReplicatorConfig object
        client: Boto3 Secrets Manager client

    Returns:
        Tuple of (should_replicate: bool, transformation_name: Optional[str])

    Examples:
        # Match with transformation
        >>> should_replicate_secret("app/prod/db", config, client)
        (True, "region-swap")

        # Match without transformation
        >>> should_replicate_secret("critical-secret-1", config, client)
        (True, None)

        # No match (deny)
        >>> should_replicate_secret("other-secret", config, client)
        (False, None)

        # Hardcoded exclusion
        >>> should_replicate_secret("secrets-replicator/transformations/test", config, client)
        (False, None)
    """
    # LAYER 1: Hardcoded exclusions for transformation and filter secrets
    # This prevents circular dependencies and accidental replication of configuration
    if secret_name.startswith(TRANSFORMATION_SECRET_PREFIX):
        logger.debug(f"Excluded: transformation secret (prefix: {TRANSFORMATION_SECRET_PREFIX})")
        return (False, None)

    if secret_name.startswith(FILTER_SECRET_PREFIX):
        logger.debug(f"Excluded: filter secret (prefix: {FILTER_SECRET_PREFIX})")
        return (False, None)

    # Hardcoded exclusion for config secrets
    if secret_name.startswith('secrets-replicator/config/'):
        logger.debug(f"Excluded: config secret (prefix: secrets-replicator/config/)")
        return (False, None)

    if secret_name.startswith('secrets-replicator/names/'):
        logger.debug(f"Excluded: name mapping secret (prefix: secrets-replicator/names/)")
        return (False, None)

    # LAYER 2: All other secrets are allowed for replication
    # Filtering is now event-driven via EventBridge rule configuration
    # No transformation applied by default (transformations loaded per-destination)
    logger.info(f"Secret '{secret_name}' allowed for replication")
    return (True, None)


def clear_filter_cache():
    """
    Clear the filter cache.

    Useful for testing and forcing a cache refresh.
    """
    global _filter_cache
    _filter_cache = {
        'data': None,
        'loaded_at': 0,
        'ttl': 300,
        'source_list': None
    }
    logger.info("Filter cache cleared")
