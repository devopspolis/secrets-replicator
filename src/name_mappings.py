"""
Name mapping configuration management for secrets replicator.

Handles loading, caching, and lookup for DEST_SECRET_NAMES configuration.
Maps source secret names to destination secret names.
"""

import json
import logging
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


def get_destination_name(source_secret_name: str, config, client) -> str:
    """
    Get destination secret name for a given source secret name.

    Lookup logic:
    1. If DEST_SECRET_NAMES not configured, return source name (standard DR pattern)
    2. Load name mappings from DEST_SECRET_NAMES
    3. Look up source name in mappings (exact match only)
    4. If found, return mapped destination name
    5. If not found, return source name (default behavior)

    Args:
        source_secret_name: Name of the source secret
        config: ReplicatorConfig object
        client: Boto3 Secrets Manager client

    Returns:
        Destination secret name (either mapped or source name)

    Examples:
        # No mappings configured
        >>> get_destination_name("app/prod/db", config, client)
        'app/prod/db'

        # Mapping found
        >>> get_destination_name("legacy-name", config, client)
        'new-name'

        # No mapping found (use source name)
        >>> get_destination_name("unmapped-secret", config, client)
        'unmapped-secret'
    """
    # LAYER 1: Check if DEST_SECRET_NAMES is configured
    if not config.dest_secret_names:
        # No mapping configured - use source name (standard DR/HA pattern)
        logger.debug(f"No DEST_SECRET_NAMES configured, using source name: {source_secret_name}")
        return source_secret_name

    # LAYER 2: Load and check mappings
    mappings = get_cached_mappings(
        config.dest_secret_names,
        config.dest_secret_names_cache_ttl,
        client
    )

    if not mappings:
        # Mapping list specified but no mappings loaded - use source name
        logger.debug(f"DEST_SECRET_NAMES specified but no mappings loaded, using source name: {source_secret_name}")
        return source_secret_name

    # LAYER 3: Look up mapping (exact match only)
    if source_secret_name in mappings:
        dest_name = mappings[source_secret_name]
        logger.info(f"Name mapping found: '{source_secret_name}' -> '{dest_name}'")
        return dest_name

    # LAYER 4: No mapping found - use source name (default)
    logger.debug(f"No name mapping for '{source_secret_name}', using source name")
    return source_secret_name


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
