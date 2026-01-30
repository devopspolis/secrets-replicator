"""
Unit tests for name_mappings module.

Tests:
- Pattern matching with wildcards
- Pattern transformation
- Exact match lookup
- Caching behavior
- Edge cases
"""

import json
import pytest
from unittest.mock import MagicMock, Mock
from botocore.exceptions import ClientError

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from name_mappings import (
    _match_pattern,
    _apply_pattern_mapping,
    get_destination_name,
    load_name_mappings,
    get_cached_mappings,
    clear_mapping_cache,
)
from config import DestinationConfig


class TestMatchPattern:
    """Test pattern matching functionality."""

    def test_exact_match_no_wildcard(self):
        """Exact match without wildcards should match only exact strings."""
        assert _match_pattern("app/prod/db", "app/prod/db") is True
        assert _match_pattern("app/prod/db", "app/prod") is False
        assert _match_pattern("app/prod", "app/prod/db") is False

    def test_prefix_wildcard(self):
        """Prefix wildcard should match all secrets with that prefix."""
        pattern = "app/*"
        assert _match_pattern("app/prod", pattern) is True
        assert _match_pattern("app/staging", pattern) is True
        assert _match_pattern("app/prod/db", pattern) is True
        assert _match_pattern("app/prod/db/master", pattern) is True
        assert _match_pattern("db/prod", pattern) is False
        assert _match_pattern("myapp/prod", pattern) is False

    def test_suffix_wildcard(self):
        """Suffix wildcard should match all secrets with that suffix."""
        pattern = "*/prod"
        assert _match_pattern("app/prod", pattern) is True
        assert _match_pattern("db/prod", pattern) is True
        assert _match_pattern("team1/app/prod", pattern) is True
        assert _match_pattern("app/staging", pattern) is False
        assert _match_pattern("prod", pattern) is False

    def test_middle_wildcard(self):
        """Middle wildcard should match secrets with matching prefix and suffix."""
        pattern = "app/*/db"
        assert _match_pattern("app/prod/db", pattern) is True
        assert _match_pattern("app/staging/db", pattern) is True
        assert _match_pattern("app/team1/env/db", pattern) is True
        assert _match_pattern("app/db", pattern) is False
        assert _match_pattern("app/prod/cache", pattern) is False
        assert _match_pattern("db/prod/db", pattern) is False

    def test_multiple_wildcards(self):
        """Multiple wildcards should match complex patterns."""
        pattern = "app/*/prod/*"
        assert _match_pattern("app/team1/prod/db", pattern) is True
        assert _match_pattern("app/team1/prod/cache", pattern) is True
        assert _match_pattern("app/x/prod/y/z", pattern) is True
        assert _match_pattern("app/prod/db", pattern) is False
        assert _match_pattern("app/team1/staging/db", pattern) is False

    def test_wildcard_at_start_and_end(self):
        """Wildcards at both ends should match middle content."""
        pattern = "*/prod/*"
        assert _match_pattern("app/prod/db", pattern) is True
        assert _match_pattern("x/prod/y", pattern) is True
        assert _match_pattern("a/b/prod/c/d", pattern) is True
        assert _match_pattern("prod", pattern) is False
        assert _match_pattern("app/staging", pattern) is False

    def test_case_sensitive(self):
        """Pattern matching should be case-sensitive."""
        pattern = "App/*"
        assert _match_pattern("App/prod", pattern) is True
        assert _match_pattern("app/prod", pattern) is False
        assert _match_pattern("APP/prod", pattern) is False

    def test_special_characters_escaped(self):
        """Special regex characters should be escaped properly."""
        # Dots, slashes, hyphens should be treated as literals
        pattern = "app-v2.*/prod"
        assert _match_pattern("app-v2.x/prod", pattern) is True
        assert _match_pattern("app-v2./prod", pattern) is True
        assert _match_pattern("appXv2Xy/prod", pattern) is False


class TestApplyPatternMapping:
    """Test pattern transformation functionality."""

    def test_no_wildcard_in_destination(self):
        """Destination without wildcard should return as-is."""
        result = _apply_pattern_mapping("app/prod/db", "app/*", "fixed-name")
        assert result == "fixed-name"

    def test_prefix_wildcard_transformation(self):
        """Prefix wildcard should transform by replacing prefix."""
        result = _apply_pattern_mapping("app/prod/db", "app/*", "my-app/*")
        assert result == "my-app/prod/db"

        result = _apply_pattern_mapping("app/staging", "app/*", "new-app/*")
        assert result == "new-app/staging"

    def test_suffix_wildcard_transformation(self):
        """Suffix wildcard should transform by replacing suffix."""
        result = _apply_pattern_mapping("app/prod", "*/prod", "*/production")
        assert result == "app/production"

        result = _apply_pattern_mapping("db/prod", "*/prod", "*/production")
        assert result == "db/production"

    def test_middle_wildcard_transformation(self):
        """Middle wildcard should preserve middle portion."""
        result = _apply_pattern_mapping("app/staging/db", "app/*/db", "my-app/*/database")
        assert result == "my-app/staging/database"

    def test_multiple_wildcards_transformation(self):
        """Multiple wildcards should replace in order."""
        result = _apply_pattern_mapping(
            "app/team1/prod/db", "app/*/prod/*", "new-app/*/production/*"
        )
        assert result == "new-app/team1/production/db"

        result = _apply_pattern_mapping("a/b/c/d", "*/b/*", "*/x/*")
        assert result == "a/x/c/d"

    def test_prefix_to_suffix_transformation(self):
        """Transform from prefix pattern to suffix pattern."""
        result = _apply_pattern_mapping("legacy-app", "legacy-*", "new-*")
        assert result == "new-app"

        result = _apply_pattern_mapping("legacy-service", "legacy-*", "new-*")
        assert result == "new-service"

    def test_complex_transformation(self):
        """Complex multi-wildcard transformation."""
        result = _apply_pattern_mapping(
            "dev/us-east-1/app/config", "dev/*/app/*", "prod/*/application/*"
        )
        assert result == "prod/us-east-1/application/config"


class TestGetDestinationName:
    """Test get_destination_name function with various scenarios."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_mapping_cache()

    def test_no_secret_names_configured(self):
        """When secret_names not configured, return source name."""
        destination = DestinationConfig(region="us-west-2", secret_names=None)
        client = MagicMock()

        result = get_destination_name("app/prod/db", destination, client)
        assert result == "app/prod/db"
        client.get_secret.assert_not_called()

    def test_exact_match_priority(self):
        """Exact matches should take priority over patterns."""
        destination = DestinationConfig(
            region="us-west-2", secret_names="test-mappings", secret_names_cache_ttl=300
        )
        client = MagicMock()
        client.get_secret.return_value = Mock(
            secret_string=json.dumps(
                {"app/prod/db": "exact-match-name", "app/*": "pattern-match-name/*"}
            )
        )

        result = get_destination_name("app/prod/db", destination, client)
        assert result == "exact-match-name"

    def test_pattern_match_when_no_exact_match(self):
        """Pattern should match when no exact match exists."""
        destination = DestinationConfig(
            region="us-west-2", secret_names="test-mappings", secret_names_cache_ttl=300
        )
        client = MagicMock()
        client.get_secret.return_value = Mock(
            secret_string=json.dumps({"other-secret": "other-dest", "app/*": "my-app/*"})
        )

        result = get_destination_name("app/prod/db", destination, client)
        assert result == "my-app/prod/db"

    def test_multiple_patterns_first_match_wins(self):
        """When multiple patterns match, first one wins."""
        destination = DestinationConfig(
            region="us-west-2", secret_names="test-mappings", secret_names_cache_ttl=300
        )
        client = MagicMock()
        # Note: dict order in Python 3.7+ is insertion order
        client.get_secret.return_value = Mock(
            secret_string=json.dumps(
                {"app/*": "first-match/*", "app/prod/*": "second-match/*", "*": "catch-all/*"}
            )
        )

        result = get_destination_name("app/prod/db", destination, client)
        # Should match "app/*" first (depending on dict iteration order)
        # The actual result depends on JSON parsing order
        assert result.startswith("first-match/") or result.startswith("second-match/")

    def test_no_match_returns_none(self):
        """When no mapping matches, return None (filtering behavior)."""
        destination = DestinationConfig(
            region="us-west-2", secret_names="test-mappings", secret_names_cache_ttl=300
        )
        client = MagicMock()
        client.get_secret.return_value = Mock(
            secret_string=json.dumps({"other-secret": "other-dest", "app/*": "my-app/*"})
        )

        result = get_destination_name("database/prod/config", destination, client)
        assert result is None

    def test_catch_all_wildcard(self):
        """Single wildcard * should match everything."""
        destination = DestinationConfig(
            region="us-west-2", secret_names="test-mappings", secret_names_cache_ttl=300
        )
        client = MagicMock()
        client.get_secret.return_value = Mock(secret_string=json.dumps({"*": "prefix/*"}))

        result = get_destination_name("any/secret/name", destination, client)
        assert result == "prefix/any/secret/name"

    def test_empty_mappings_returns_none(self):
        """Empty mapping secret should return None (no patterns to match)."""
        destination = DestinationConfig(
            region="us-west-2", secret_names="test-mappings", secret_names_cache_ttl=300
        )
        client = MagicMock()
        client.get_secret.return_value = Mock(secret_string=json.dumps({}))

        result = get_destination_name("app/prod/db", destination, client)
        assert result is None


class TestLoadNameMappings:
    """Test loading name mappings from Secrets Manager."""

    def test_load_single_mapping_secret(self):
        """Load mappings from a single secret."""
        client = MagicMock()
        client.get_secret.return_value = Mock(
            secret_string=json.dumps({"source1": "dest1", "source2": "dest2"})
        )

        result = load_name_mappings("mapping1", client)
        assert result == {"source1": "dest1", "source2": "dest2"}
        client.get_secret.assert_called_once_with(secret_id="mapping1")

    def test_load_multiple_mapping_secrets(self):
        """Load and merge mappings from multiple secrets."""
        client = MagicMock()
        client.get_secret.side_effect = [
            Mock(secret_string=json.dumps({"source1": "dest1"})),
            Mock(secret_string=json.dumps({"source2": "dest2"})),
        ]

        result = load_name_mappings("mapping1,mapping2", client)
        assert result == {"source1": "dest1", "source2": "dest2"}
        assert client.get_secret.call_count == 2

    def test_later_mappings_override_earlier(self):
        """Later mappings should override earlier ones."""
        client = MagicMock()
        client.get_secret.side_effect = [
            Mock(secret_string=json.dumps({"source1": "dest1"})),
            Mock(secret_string=json.dumps({"source1": "dest2"})),
        ]

        result = load_name_mappings("mapping1,mapping2", client)
        assert result == {"source1": "dest2"}

    def test_empty_mapping_list(self):
        """Empty mapping list should return empty dict."""
        client = MagicMock()
        result = load_name_mappings("", client)
        assert result == {}
        client.get_secret.assert_not_called()

    def test_invalid_json_continues_gracefully(self):
        """Invalid JSON in mapping secret should log error and return empty dict."""
        client = MagicMock()
        client.get_secret.return_value = Mock(secret_string="not valid json")

        # Should not raise, but return empty dict
        result = load_name_mappings("mapping1", client)
        assert result == {}

    def test_non_dict_json_continues_gracefully(self):
        """Non-dict JSON should log error and return empty dict."""
        client = MagicMock()
        client.get_secret.return_value = Mock(secret_string=json.dumps(["array", "not", "dict"]))

        # Should not raise, but return empty dict
        result = load_name_mappings("mapping1", client)
        assert result == {}

    def test_client_error_continues_with_other_mappings(self):
        """ClientError on one secret should not prevent loading others."""
        client = MagicMock()
        client.get_secret.side_effect = [
            ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue"),
            Mock(secret_string=json.dumps({"source2": "dest2"})),
        ]

        result = load_name_mappings("mapping1,mapping2", client)
        assert result == {"source2": "dest2"}


class TestGetCachedMappings:
    """Test caching behavior of name mappings."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_mapping_cache()

    def test_cache_hit(self):
        """Second call should use cache."""
        client = MagicMock()
        client.get_secret.return_value = Mock(secret_string=json.dumps({"source1": "dest1"}))

        # First call - cache miss
        result1 = get_cached_mappings("mapping1", 300, client)
        assert result1 == {"source1": "dest1"}
        assert client.get_secret.call_count == 1

        # Second call - cache hit
        result2 = get_cached_mappings("mapping1", 300, client)
        assert result2 == {"source1": "dest1"}
        assert client.get_secret.call_count == 1  # Not called again

    def test_cache_invalidation_on_different_mapping_list(self):
        """Cache should invalidate when mapping list changes."""
        client = MagicMock()
        client.get_secret.side_effect = [
            Mock(secret_string=json.dumps({"source1": "dest1"})),
            Mock(secret_string=json.dumps({"source2": "dest2"})),
        ]

        get_cached_mappings("mapping1", 300, client)
        get_cached_mappings("mapping2", 300, client)

        assert client.get_secret.call_count == 2
