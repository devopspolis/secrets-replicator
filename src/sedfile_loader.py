"""
Sedfile loader for transformation rules.

Supports loading sedfiles from:
- S3 buckets (with caching)
- Bundled files in the Lambda package
"""

import os
import boto3
from typing import Optional, Dict
from pathlib import Path
from botocore.exceptions import ClientError


class SedfileLoadError(Exception):
    """Raised when sedfile loading fails"""
    pass


class SedfileCache:
    """Simple in-memory cache for sedfiles"""

    def __init__(self):
        self._cache: Dict[str, str] = {}

    def get(self, key: str) -> Optional[str]:
        """Get cached sedfile content"""
        return self._cache.get(key)

    def set(self, key: str, content: str) -> None:
        """Cache sedfile content"""
        self._cache[key] = content

    def clear(self) -> None:
        """Clear all cached sedfiles"""
        self._cache.clear()


# Global cache instance (persists across Lambda invocations in same container)
_sedfile_cache = SedfileCache()


def load_sedfile_from_s3(bucket: str, key: str, use_cache: bool = True) -> str:
    """
    Load sedfile from S3 bucket.

    Uses in-memory caching to avoid repeated S3 calls within the same
    Lambda container (warm start optimization).

    Args:
        bucket: S3 bucket name
        key: S3 object key
        use_cache: Whether to use cache (default: True)

    Returns:
        Sedfile content as string

    Raises:
        SedfileLoadError: If sedfile cannot be loaded from S3

    Examples:
        >>> content = load_sedfile_from_s3('my-bucket', 'sedfiles/default.sed')
        >>> 's/us-east-1/us-west-2/' in content
        True
    """
    # Check cache first
    cache_key = f"s3://{bucket}/{key}"
    if use_cache:
        cached = _sedfile_cache.get(cache_key)
        if cached is not None:
            return cached

    # Load from S3
    try:
        s3_client = boto3.client('s3')
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')

        # Cache for next time
        if use_cache:
            _sedfile_cache.set(cache_key, content)

        return content

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'NoSuchKey':
            raise SedfileLoadError(
                f"Sedfile not found in S3: s3://{bucket}/{key}"
            ) from e
        elif error_code == 'NoSuchBucket':
            raise SedfileLoadError(
                f"S3 bucket not found: {bucket}"
            ) from e
        elif error_code in ('AccessDenied', 'Forbidden'):
            raise SedfileLoadError(
                f"Access denied to S3 sedfile: s3://{bucket}/{key}"
            ) from e
        else:
            raise SedfileLoadError(
                f"Failed to load sedfile from S3: {error_code}"
            ) from e
    except Exception as e:
        raise SedfileLoadError(
            f"Unexpected error loading sedfile from S3: {e}"
        ) from e


def load_sedfile_from_bundle(filename: str = 'default.sed',
                             sedfiles_dir: str = 'sedfiles') -> str:
    """
    Load sedfile from bundled Lambda package.

    Looks for sedfile in the Lambda package under sedfiles/ directory.

    Args:
        filename: Sedfile filename (default: 'default.sed')
        sedfiles_dir: Directory containing sedfiles (default: 'sedfiles')

    Returns:
        Sedfile content as string

    Raises:
        SedfileLoadError: If sedfile cannot be found or read

    Examples:
        >>> content = load_sedfile_from_bundle('default.sed')
        >>> isinstance(content, str)
        True
    """
    # Determine base path (Lambda or local development)
    # In Lambda, files are in /var/task/
    # In local dev, files are relative to project root
    possible_base_paths = [
        Path('/var/task'),           # Lambda runtime
        Path(__file__).parent.parent,  # Development (from src/ to project root)
        Path.cwd(),                  # Current working directory
    ]

    sedfile_path = None
    for base_path in possible_base_paths:
        candidate = base_path / sedfiles_dir / filename
        if candidate.exists() and candidate.is_file():
            sedfile_path = candidate
            break

    if sedfile_path is None:
        # Build error message with search paths
        search_paths = [str(base / sedfiles_dir / filename) for base in possible_base_paths]
        raise SedfileLoadError(
            f"Bundled sedfile not found: {filename}\n"
            f"Searched paths: {', '.join(search_paths)}"
        )

    try:
        return sedfile_path.read_text(encoding='utf-8')
    except Exception as e:
        raise SedfileLoadError(
            f"Failed to read bundled sedfile {sedfile_path}: {e}"
        ) from e


def load_sedfile(bucket: Optional[str] = None,
                 key: Optional[str] = None,
                 bundled_filename: str = 'default.sed',
                 use_cache: bool = True) -> str:
    """
    Load sedfile from S3 or bundled package.

    If bucket and key are provided, loads from S3.
    Otherwise, loads from bundled package.

    Args:
        bucket: S3 bucket name (optional)
        key: S3 object key (optional)
        bundled_filename: Bundled sedfile filename (default: 'default.sed')
        use_cache: Whether to use cache for S3 (default: True)

    Returns:
        Sedfile content as string

    Raises:
        SedfileLoadError: If sedfile cannot be loaded

    Examples:
        >>> # Load from S3
        >>> content = load_sedfile(bucket='my-bucket', key='sedfiles/prod.sed')

        >>> # Load from bundled package
        >>> content = load_sedfile(bundled_filename='default.sed')
    """
    if bucket and key:
        # Load from S3
        return load_sedfile_from_s3(bucket, key, use_cache=use_cache)
    else:
        # Load from bundled package
        return load_sedfile_from_bundle(bundled_filename)


def clear_cache() -> None:
    """
    Clear the sedfile cache.

    Useful for testing or when sedfiles are updated during runtime.

    Examples:
        >>> clear_cache()  # Cache is now empty
    """
    _sedfile_cache.clear()


def get_cache_keys() -> list:
    """
    Get all cached sedfile keys (for debugging/testing).

    Returns:
        List of cache keys

    Examples:
        >>> keys = get_cache_keys()
        >>> isinstance(keys, list)
        True
    """
    return list(_sedfile_cache._cache.keys())
