"""
Name mapping configuration management for secrets replicator.

Handles loading, caching, and lookup for DEST_SECRET_NAMES configuration.
Maps source secret names to destination secret names.
Supports wildcard patterns like app/*, */prod, etc.
"""

import json
import logging
import re
import time
from typing import Dict, Optional

from botocore.exceptions import ClientError

from config import NAME_MAPPING_PREFIX


logger = logging.getLogger(__name__)


# Global cache for name mappings (persists across Lambda invocations)
_mapping_cache = {
    'data': None,           # Dict[str, str] - merged mappings
    'loaded_at': 0,         # float - timestamp
    'ttl': 300,            # int - cache TTL in seconds
    'source_list': None    # str - comma-separated mapping secret names
}


def load_name_mappings(mapping_list: str, client) -> Dict[str, str]:
    """
    Load name mappings from comma-separated list of secret names.

    Args:
        mapping_list: Comma-separated list of Secrets Manager secret names
        client: Boto3 Secrets Manager client

    Returns:
        Dict mapping source secret names to destination secret names

    Example:
        Input: "secrets-replicator/names/prod,secrets-replicator/names/special"
        Output: {
            "app/prod/database": "app/prod-dr/database",
            "legacy-name": "new-name"
        }

    Raises:
        ValueError: If mapping secret contains invalid JSON
        ClientError: If mapping secret cannot be loaded
    """
    if not mapping_list or not mapping_list.strip():
        logger.info("No mapping list provided, returning empty mappings")
        return {}

    merged_mappings = {}
    mapping_secrets = [s.strip() for s in mapping_list.split(',') if s.strip()]

    logger.info(f"Loading {len(mapping_secrets)} name mapping secrets")

    for secret_name in mapping_secrets:
        try:
            logger.debug(f"Loading name mapping secret: {secret_name}")
            response = client.get_secret(secret_id=secret_name)

            # Parse JSON
            try:
                mapping_data = json.loads(response.secret_string)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in mapping secret {secret_name}: {e}")
                raise ValueError(f"Mapping secret {secret_name} contains invalid JSON: {e}")

            # Validate mapping data is a dict
            if not isinstance(mapping_data, dict):
                logger.error(f"Mapping secret {secret_name} must be a JSON object, got {type(mapping_data)}")
                raise ValueError(f"Mapping secret {secret_name} must be a JSON object")

            # Merge mappings (later mappings override earlier ones)
            for source_name, dest_name in mapping_data.items():
                # Validate both are strings
                if not isinstance(source_name, str) or not isinstance(dest_name, str):
                    logger.warning(f"Skipping invalid mapping in {secret_name}: {source_name} -> {dest_name}")
                    continue

                # Normalize empty string to None (will use source name)
                if dest_name == "":
                    merged_mappings[source_name] = source_name
                    logger.debug(f"Name mapping '{source_name}' -> '{source_name}' (empty value, using source)")
                else:
                    merged_mappings[source_name] = dest_name
                    logger.debug(f"Name mapping '{source_name}' -> '{dest_name}'")

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"Failed to load mapping secret {secret_name}: {error_code} - {e}")
            # Continue with other mappings rather than failing completely
            continue
        except Exception as e:
            logger.error(f"Unexpected error loading mapping secret {secret_name}: {e}", exc_info=True)
            # Continue with other mappings
            continue

    logger.info(f"Loaded {len(merged_mappings)} name mappings from {len(mapping_secrets)} mapping secrets")
    return merged_mappings


def get_cached_mappings(mapping_list: str, ttl: int, client) -> Dict[str, str]:
    """
    Load name mappings with caching.

    Cache invalidation:
    - TTL expires (default 5 minutes)
    - Mapping list changes (different secrets)

    Args:
        mapping_list: Comma-separated list of mapping secret names
        ttl: Cache TTL in seconds
        client: Boto3 Secrets Manager client

    Returns:
        Dict mapping source secret names to destination secret names
    """
    now = time.time()

    # Check if cache is valid
    cache_valid = (
        _mapping_cache['data'] is not None and
        _mapping_cache['source_list'] == mapping_list and
        (now - _mapping_cache['loaded_at']) < _mapping_cache['ttl']
    )

    if cache_valid:
        logger.debug("Using cached name mappings")
        return _mapping_cache['data']

    # Load fresh configuration
    logger.info(f"Loading fresh name mappings from: {mapping_list}")
    mappings = load_name_mappings(mapping_list, client)

    # Update cache
    _mapping_cache['data'] = mappings
    _mapping_cache['loaded_at'] = now
    _mapping_cache['ttl'] = ttl
    _mapping_cache['source_list'] = mapping_list

    logger.info(f"Name mappings cached (TTL: {ttl}s)")
    return mappings


def _match_pattern(secret_name: str, pattern: str) -> bool:
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
        >>> _match_pattern("app/prod/db", "app/*")
        True
        >>> _match_pattern("app/prod/db", "app/prod/*")
        True
        >>> _match_pattern("app/prod/db", "db/*")
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


def _apply_pattern_mapping(secret_name: str, pattern: str, dest_pattern: str) -> str:
    """
    Apply a pattern-based name mapping to transform secret name.

    If the destination pattern contains wildcards, they are replaced with
    the corresponding matched portions from the source secret name.

    Args:
        secret_name: Source secret name
        pattern: Source pattern that matched
        dest_pattern: Destination pattern to apply

    Returns:
        Transformed destination name

    Examples:
        >>> _apply_pattern_mapping("app/prod/db", "app/*", "my-app/*")
        'my-app/prod/db'
        >>> _apply_pattern_mapping("app/prod", "*/prod", "*/production")
        'app/production'
        >>> _apply_pattern_mapping("legacy-app", "legacy-*", "new-*")
        'new-app'
    """
    # If destination has no wildcards, return it as-is
    if '*' not in dest_pattern:
        return dest_pattern

    # Build regex to extract wildcard portions
    escaped_pattern = re.escape(pattern)
    regex_pattern = escaped_pattern.replace(r'\*', '(.*?)')
    regex_pattern = f'^{regex_pattern}$'

    try:
        match = re.match(regex_pattern, secret_name)
        if not match:
            # Should not happen if _match_pattern was called first
            logger.warning(f"Pattern '{pattern}' matched but regex extraction failed for '{secret_name}'")
            return dest_pattern

        # Replace wildcards in destination with captured groups
        result = dest_pattern
        for i, captured in enumerate(match.groups(), 1):
            # Replace first * with captured value
            result = result.replace('*', captured, 1)

        logger.debug(f"Pattern mapping: '{secret_name}' ({pattern}) -> '{result}' ({dest_pattern})")
        return result

    except re.error as e:
        logger.error(f"Regex error applying pattern mapping: {e}")
        return dest_pattern


def get_destination_name(source_secret_name: str, destination, client) -> Optional[str]:
    """
    Get destination secret name for a given source secret name.

    IMPORTANT: When secret_names is configured, it acts as BOTH a filter and a name mapper.
    Only secrets matching a pattern in the mapping will be replicated.

    Lookup logic:
    1. If destination.secret_names not configured, return source name (replicate all with same name)
    2. Load name mappings from destination.secret_names
    3. Try exact match lookup first
    4. If no exact match, try pattern matching (in order)
    5. If found, apply pattern transformation to destination name
    6. If not found, return None (DO NOT replicate - filtering behavior)

    Args:
        source_secret_name: Name of the source secret
        destination: DestinationConfig object with secret_names and secret_names_cache_ttl
        client: Boto3 Secrets Manager client

    Returns:
        Destination secret name if matched, None if secret should not be replicated

    Examples:
        # No mappings configured - replicate all with same name
        >>> get_destination_name("app/prod/db", destination, client)
        'app/prod/db'

        # Exact match
        >>> get_destination_name("legacy-name", destination, client)
        'new-name'

        # Pattern match
        >>> get_destination_name("app/prod/db", destination, client)  # pattern: app/* -> my-app/*
        'my-app/prod/db'

        # No mapping found - do NOT replicate (filtering behavior)
        >>> get_destination_name("unmapped-secret", destination, client)
        None
    """
    # LAYER 1: Check if secret_names is configured
    if not destination.secret_names:
        # No mapping configured - replicate ALL secrets with same name (standard DR/HA pattern)
        logger.debug(f"No secret_names configured for destination, using source name: {source_secret_name}")
        return source_secret_name

    # LAYER 2: Load and check mappings
    mappings = get_cached_mappings(
        destination.secret_names,
        destination.secret_names_cache_ttl,
        client
    )

    if not mappings:
        # Mapping list specified but no mappings loaded - DO NOT replicate (fail-safe)
        logger.warning(f"secret_names specified but no mappings loaded - not replicating '{source_secret_name}'")
        return None

    # LAYER 3: Try exact match first (most common case, fastest)
    if source_secret_name in mappings:
        dest_name = mappings[source_secret_name]
        logger.info(f"Exact name mapping found: '{source_secret_name}' -> '{dest_name}'")
        return dest_name

    # LAYER 4: Try pattern matching (check all patterns in order)
    for pattern, dest_pattern in mappings.items():
        # Skip patterns without wildcards (already checked in exact match)
        if '*' not in pattern:
            continue

        if _match_pattern(source_secret_name, pattern):
            # Apply pattern transformation
            dest_name = _apply_pattern_mapping(source_secret_name, pattern, dest_pattern)
            logger.info(f"Pattern name mapping found: '{source_secret_name}' matched '{pattern}' -> '{dest_name}'")
            return dest_name

    # LAYER 5: No mapping found - DO NOT replicate (filtering behavior)
    logger.info(f"Secret '{source_secret_name}' does not match any pattern in secret_names - skipping replication to this destination")
    return None


def clear_mapping_cache():
    """
    Clear the name mapping cache.

    Useful for testing and forcing a cache refresh.
    """
    global _mapping_cache
    _mapping_cache = {
        'data': None,
        'loaded_at': 0,
        'ttl': 300,
        'source_list': None
    }
    logger.info("Name mapping cache cleared")
