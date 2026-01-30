"""
Filter configuration management for secrets replicator.

Filters serve a dual purpose:
1. Filtering: Determine which secrets are replicated (only matching patterns)
2. Transformation Mapping: Specify which transformation to apply to each secret

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
    "data": None,  # Dict[str, Optional[str]] - merged filters
    "loaded_at": 0,  # float - timestamp
    "ttl": 300,  # int - cache TTL in seconds
    "source_list": None,  # str - comma-separated filter secret names
}


def load_filter_configuration(filter_list: str, client) -> Dict[str, Optional[str]]:
    """
    Load filter configuration from comma-separated list of secret names.

    Filter secrets serve a dual purpose:
    - Filtering: Only secrets matching a pattern key are replicated
    - Transformation mapping: The value specifies which transformation to apply

    Args:
        filter_list: Comma-separated list of Secrets Manager secret names
        client: Boto3 Secrets Manager client

    Returns:
        Dict mapping secret patterns to transformation names (dual purpose):
        - Keys are patterns for filtering (which secrets to replicate)
        - Values are transformation names (which transformation to apply)

    Example:
        Input: "secrets-replicator/filters/prod,secrets-replicator/filters/db"
        Output: {
            "app/prod/*": "region-swap",      # Replicate app/prod/* with region-swap
            "db/prod/*": "db-transform",      # Replicate db/prod/* with db-transform
            "critical-secret-1": None         # Replicate as-is (no transformation)
            # Secrets not matching any pattern are NOT replicated
        }

    Raises:
        ValueError: If filter secret contains invalid JSON
        ClientError: If filter secret cannot be loaded
    """
    if not filter_list or not filter_list.strip():
        logger.info("No filter list provided, returning empty filters")
        return {}

    merged_filters = {}
    filter_secrets = [s.strip() for s in filter_list.split(",") if s.strip()]

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
                logger.error(
                    f"Filter secret {secret_name} must be a JSON object, got {type(filter_data)}"
                )
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
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"Failed to load filter secret {secret_name}: {error_code} - {e}")
            # Continue with other filters rather than failing completely
            continue
        except Exception as e:
            logger.error(
                f"Unexpected error loading filter secret {secret_name}: {e}", exc_info=True
            )
            # Continue with other filters
            continue

    logger.info(
        f"Loaded {len(merged_filters)} filter patterns from {len(filter_secrets)} filter secrets"
    )
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
        _filter_cache["data"] is not None
        and _filter_cache["source_list"] == filter_list
        and (now - _filter_cache["loaded_at"]) < _filter_cache["ttl"]
    )

    if cache_valid:
        logger.debug("Using cached filter configuration")
        return _filter_cache["data"]

    # Load fresh configuration
    logger.info(f"Loading fresh filter configuration from: {filter_list}")
    filters = load_filter_configuration(filter_list, client)

    # Update cache
    _filter_cache["data"] = filters
    _filter_cache["loaded_at"] = now
    _filter_cache["ttl"] = ttl
    _filter_cache["source_list"] = filter_list

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
    if "*" not in pattern:
        return secret_name == pattern

    # Convert glob pattern to regex
    # Escape special regex characters except *
    escaped_pattern = re.escape(pattern)

    # Replace escaped \* with regex .*
    regex_pattern = escaped_pattern.replace(r"\*", ".*")

    # Anchor the pattern
    regex_pattern = f"^{regex_pattern}$"

    # Compile and match
    try:
        compiled_pattern = re.compile(regex_pattern)
        return bool(compiled_pattern.match(secret_name))
    except re.error as e:
        logger.error(f"Invalid regex pattern generated from '{pattern}': {e}")
        return False


def find_matching_filter(
    secret_name: str, filters: Dict[str, Optional[str]]
) -> Union[Optional[str], bool]:
    """
    Find transformation for a secret based on filter patterns.

    This function implements the dual-purpose filter behavior:
    - Filtering: Returns False if no pattern matches (secret not replicated)
    - Transformation mapping: Returns the transformation name if pattern matches

    Args:
        secret_name: Name of the secret to replicate
        filters: Dict of pattern -> transformation_name mappings (dual purpose)

    Returns:
        - Transformation name (str): Pattern matched, replicate with this transformation
        - None: Pattern matched, replicate without transformation (pass-through)
        - False: No pattern matched, do NOT replicate (filtered out)

    Pattern matching:
        - Exact match has highest priority
        - Wildcard patterns checked in order
        - First match wins

    Examples:
        >>> filters = {"app/prod/*": "region-swap", "critical-secret-1": None}
        >>> find_matching_filter("app/prod/db", filters)
        'region-swap'  # Replicate with region-swap transformation
        >>> find_matching_filter("critical-secret-1", filters)
        None  # Replicate without transformation (pass-through)
        >>> find_matching_filter("other-secret", filters)
        False  # Do NOT replicate (no matching pattern)
    """
    # Check exact match first (highest priority)
    if secret_name in filters:
        logger.debug(f"Exact match found for '{secret_name}'")
        return filters[secret_name]

    # Check wildcard patterns
    for pattern, transform_name in filters.items():
        if "*" in pattern:
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
    1. Hardcoded exclusions (transformation secrets, filter secrets, config secrets)
    2. If SECRETS_FILTER not configured: allow all secrets, no transformation
    3. If SECRETS_FILTER configured: load filters and find matching pattern
    4. Return replication decision and transformation name

    Args:
        secret_name: Name of the secret to check
        config: ReplicatorConfig object (must have secrets_filter and secrets_filter_cache_ttl)
        client: Boto3 Secrets Manager client

    Returns:
        Tuple of (should_replicate: bool, transformation_name: Optional[str])

    Examples:
        # Match with transformation (SECRETS_FILTER configured)
        >>> should_replicate_secret("app/prod/db", config, client)
        (True, "region-swap")

        # Match without transformation (pattern maps to empty/null)
        >>> should_replicate_secret("critical-secret-1", config, client)
        (True, None)

        # No match in filters (deny replication)
        >>> should_replicate_secret("other-secret", config, client)
        (False, None)

        # No SECRETS_FILTER configured (allow all, no transformation)
        >>> should_replicate_secret("any-secret", config_without_filter, client)
        (True, None)

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
    if secret_name.startswith("secrets-replicator/config/"):
        logger.debug(f"Excluded: config secret (prefix: secrets-replicator/config/)")
        return (False, None)

    if secret_name.startswith("secrets-replicator/names/"):
        logger.debug(f"Excluded: name mapping secret (prefix: secrets-replicator/names/)")
        return (False, None)

    # LAYER 2: Check SECRETS_FILTER configuration
    secrets_filter = getattr(config, "secrets_filter", None)
    secrets_filter_cache_ttl = getattr(config, "secrets_filter_cache_ttl", 300)

    # If SECRETS_FILTER not configured, allow all secrets with no transformation
    if not secrets_filter:
        logger.info(
            f"SECRETS_FILTER not configured - allowing '{secret_name}' without transformation"
        )
        return (True, None)

    # LAYER 3: Load filters and find matching pattern
    try:
        filters = get_cached_filters(secrets_filter, secrets_filter_cache_ttl, client)
    except Exception as e:
        logger.error(f"Failed to load filters from SECRETS_FILTER: {e}")
        # On filter load failure, deny replication for safety
        return (False, None)

    # If no filters loaded (empty or all failed), deny replication
    if not filters:
        logger.warning(f"No filters loaded from SECRETS_FILTER - denying '{secret_name}'")
        return (False, None)

    # Find matching filter pattern
    match_result = find_matching_filter(secret_name, filters)

    if match_result is False:
        # No match found - deny replication
        logger.info(
            f"Secret '{secret_name}' does not match any filter pattern - denying replication"
        )
        return (False, None)

    # Match found - match_result is either a transformation name (str) or None
    if match_result is None:
        logger.info(f"Secret '{secret_name}' matched filter - replicating without transformation")
        return (True, None)
    else:
        logger.info(
            f"Secret '{secret_name}' matched filter - using transformation '{match_result}'"
        )
        return (True, match_result)


def is_system_secret(secret_name: str) -> bool:
    """
    Check if a secret is a system secret that should never be replicated.

    System secrets include transformation secrets, filter secrets, config secrets,
    and name mapping secrets.

    Args:
        secret_name: Name of the secret to check

    Returns:
        True if this is a system secret that should be excluded, False otherwise

    Examples:
        >>> is_system_secret("secrets-replicator/transformations/my-sed")
        True
        >>> is_system_secret("app/prod/database")
        False
    """
    system_prefixes = [
        TRANSFORMATION_SECRET_PREFIX,
        FILTER_SECRET_PREFIX,
        "secrets-replicator/config/",
        "secrets-replicator/names/",
    ]

    for prefix in system_prefixes:
        if secret_name.startswith(prefix):
            logger.debug(f"Secret '{secret_name}' is a system secret (prefix: {prefix})")
            return True

    return False


def get_destination_transformation(
    secret_name: str, destination, global_config, client
) -> Tuple[bool, Optional[str]]:
    """
    Determine if secret should replicate to destination and which transformation to use.

    This function implements the dual-purpose filter behavior per-destination:
    - Filtering: Should this secret be replicated to this destination?
    - Transformation mapping: Which transformation should be applied?

    Uses destination-level filters if configured, otherwise falls back to
    global SECRETS_FILTER. This allows different destinations to have
    different filter/transformation rules.

    Args:
        secret_name: Name of the secret being replicated
        destination: DestinationConfig object (may have 'filters' field)
        global_config: ReplicatorConfig object (has 'secrets_filter' field)
        client: Boto3 Secrets Manager client

    Returns:
        Tuple of (should_replicate: bool, transformation_name: Optional[str]):
        - (True, "name"): Replicate with named transformation
        - (True, None): Replicate without transformation (pass-through)
        - (False, None): Do NOT replicate to this destination

    Examples:
        # Secret matches filter with transformation
        >>> get_destination_transformation("app/prod/db", dest_with_filters, config, client)
        (True, "region-swap-west")  # Replicate with transformation

        # Secret matches filter without transformation
        >>> get_destination_transformation("critical/secret", dest_with_filters, config, client)
        (True, None)  # Replicate as-is

        # Secret doesn't match any filter pattern
        >>> get_destination_transformation("other/secret", dest_with_filters, config, client)
        (False, None)  # Do NOT replicate
    """
    # Get destination-specific filter or fall back to global
    dest_filters = getattr(destination, "filters", None)
    global_filters = getattr(global_config, "secrets_filter", None)
    cache_ttl = getattr(global_config, "secrets_filter_cache_ttl", 300)

    # Determine which filter to use
    filter_secret = dest_filters or global_filters

    if not filter_secret:
        # No filters configured at all - allow secret, no transformation
        logger.info(
            f"No filters configured for destination {destination.region} - allowing '{secret_name}'"
        )
        return (True, None)

    # Load and check the filter
    try:
        filters = get_cached_filters(filter_secret, cache_ttl, client)
    except Exception as e:
        logger.error(f"Failed to load filters for destination {destination.region}: {e}")
        return (False, None)

    if not filters:
        logger.warning(
            f"No filters loaded for destination {destination.region} - denying '{secret_name}'"
        )
        return (False, None)

    # Find matching filter pattern
    match_result = find_matching_filter(secret_name, filters)

    if match_result is False:
        logger.info(f"Secret '{secret_name}' doesn't match filters for {destination.region}")
        return (False, None)

    if match_result is None:
        logger.info(
            f"Secret '{secret_name}' matches filter for {destination.region} - no transformation"
        )
        return (True, None)

    logger.info(
        f"Secret '{secret_name}' matches filter for {destination.region} - transform: '{match_result}'"
    )
    return (True, match_result)


def clear_filter_cache():
    """
    Clear the filter cache.

    Useful for testing and forcing a cache refresh.
    """
    global _filter_cache
    _filter_cache = {"data": None, "loaded_at": 0, "ttl": 300, "source_list": None}
    logger.info("Filter cache cleared")
