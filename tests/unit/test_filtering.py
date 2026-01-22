"""
Tests for filtering logic with SECRETS_FILTER support.

Tests the new centralized filter configuration system that replaces tag-based filtering.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.filters import (
    should_replicate_secret,
    load_filter_configuration,
    get_cached_filters,
    match_secret_pattern,
    find_matching_filter,
    clear_filter_cache,
    is_system_secret,
    get_destination_transformation
)
from src.config import parse_tag_filters, ReplicatorConfig, ConfigurationError, DestinationConfig


class TestParseTagFilters:
    """Test tag parsing helper function (still used for other purposes)"""

    def test_parse_empty_string(self):
        """Empty string returns empty list"""
        assert parse_tag_filters("") == []
        assert parse_tag_filters("   ") == []

    def test_parse_single_tag(self):
        """Parse single tag filter"""
        result = parse_tag_filters("Environment=production")
        assert result == [("Environment", "production")]

    def test_parse_multiple_tags(self):
        """Parse multiple tag filters"""
        result = parse_tag_filters("Env=prod,App=webapp,Team=backend")
        assert result == [
            ("Env", "prod"),
            ("App", "webapp"),
            ("Team", "backend")
        ]

    def test_parse_tags_with_whitespace(self):
        """Parse tags with extra whitespace"""
        result = parse_tag_filters("  Env = prod , App = webapp  ")
        assert result == [
            ("Env", "prod"),
            ("App", "webapp")
        ]

    def test_parse_tag_with_equals_in_value(self):
        """Parse tag where value contains equals sign"""
        result = parse_tag_filters("Query=SELECT * FROM users WHERE id=123")
        assert result == [("Query", "SELECT * FROM users WHERE id=123")]

    def test_parse_tag_without_equals_raises_error(self):
        """Tag without equals sign raises ConfigurationError"""
        with pytest.raises(ConfigurationError, match="Invalid tag filter format"):
            parse_tag_filters("InvalidTag")

    def test_parse_tag_with_empty_key_raises_error(self):
        """Tag with empty key raises ConfigurationError"""
        with pytest.raises(ConfigurationError, match="key and value cannot be empty"):
            parse_tag_filters("=value")

    def test_parse_tag_with_empty_value_raises_error(self):
        """Tag with empty value raises ConfigurationError"""
        with pytest.raises(ConfigurationError, match="key and value cannot be empty"):
            parse_tag_filters("key=")


class TestMatchSecretPattern:
    """Test glob pattern matching for secret names"""

    def test_exact_match(self):
        """Exact match (no wildcard)"""
        assert match_secret_pattern("my-secret", "my-secret") is True
        assert match_secret_pattern("my-secret", "other-secret") is False

    def test_prefix_wildcard(self):
        """Prefix wildcard pattern"""
        assert match_secret_pattern("app/prod/db", "app/*") is True
        assert match_secret_pattern("app/staging/db", "app/*") is True
        assert match_secret_pattern("other/prod/db", "app/*") is False

    def test_suffix_wildcard(self):
        """Suffix wildcard pattern"""
        assert match_secret_pattern("app/prod", "*/prod") is True
        assert match_secret_pattern("db/prod", "*/prod") is True
        assert match_secret_pattern("app/staging", "*/prod") is False

    def test_middle_wildcard(self):
        """Middle wildcard pattern"""
        assert match_secret_pattern("app/prod/db", "app/*/db") is True
        assert match_secret_pattern("app/staging/db", "app/*/db") is True
        assert match_secret_pattern("app/prod/cache", "app/*/db") is False

    def test_multiple_wildcards(self):
        """Multiple wildcards in pattern"""
        assert match_secret_pattern("app/team1/prod/db", "app/*/prod/*") is True
        assert match_secret_pattern("app/team2/prod/cache", "app/*/prod/*") is True
        assert match_secret_pattern("app/team1/dev/db", "app/*/prod/*") is False


class TestFindMatchingFilter:
    """Test filter pattern matching logic"""

    def test_exact_match_priority(self):
        """Exact match takes priority over wildcard"""
        filters = {
            "app/*": "default-transform",
            "app/prod/db": "specific-transform"
        }
        assert find_matching_filter("app/prod/db", filters) == "specific-transform"

    def test_wildcard_match(self):
        """Wildcard pattern matching"""
        filters = {
            "app/prod/*": "region-swap",
            "db/*": "connection-transform"
        }
        assert find_matching_filter("app/prod/api", filters) == "region-swap"
        assert find_matching_filter("db/mysql", filters) == "connection-transform"

    def test_no_match_returns_false(self):
        """No matching pattern returns False"""
        filters = {
            "app/*": "region-swap"
        }
        assert find_matching_filter("other-secret", filters) is False

    def test_empty_transformation(self):
        """Empty/null transformation value returns None"""
        filters = {
            "critical-secret": None,
            "app/*": ""
        }
        # Note: empty string is normalized to None during loading
        assert find_matching_filter("critical-secret", filters) is None

    def test_empty_filters(self):
        """Empty filters dict returns False for any secret"""
        assert find_matching_filter("any-secret", {}) is False


class TestLoadFilterConfiguration:
    """Test loading filter configuration from Secrets Manager"""

    def test_load_single_filter_secret(self):
        """Load filters from single secret"""
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/*": "region-swap", "db/*": "connection-transform"}'
        )

        filters = load_filter_configuration("secrets-replicator/filters/prod", mock_client)

        assert filters == {
            "app/*": "region-swap",
            "db/*": "connection-transform"
        }

    def test_load_multiple_filter_secrets(self):
        """Load and merge filters from multiple secrets"""
        mock_client = MagicMock()
        mock_client.get_secret.side_effect = [
            MagicMock(secret_string='{"app/*": "transform-a"}'),
            MagicMock(secret_string='{"db/*": "transform-b", "app/*": "transform-c"}')
        ]

        filters = load_filter_configuration(
            "secrets-replicator/filters/a,secrets-replicator/filters/b",
            mock_client
        )

        # Later filter overrides earlier one for app/*
        assert filters == {
            "app/*": "transform-c",
            "db/*": "transform-b"
        }

    def test_load_empty_filter_list(self):
        """Empty filter list returns empty dict"""
        mock_client = MagicMock()
        filters = load_filter_configuration("", mock_client)
        assert filters == {}

    def test_null_transformation_normalized(self):
        """Null and empty string values are normalized to None"""
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"secret-a": null, "secret-b": ""}'
        )

        filters = load_filter_configuration("secrets-replicator/filters/test", mock_client)

        assert filters == {
            "secret-a": None,
            "secret-b": None
        }


class TestGetCachedFilters:
    """Test filter caching behavior"""

    def setup_method(self):
        """Clear cache before each test"""
        clear_filter_cache()

    def test_cache_miss_loads_filters(self):
        """Cache miss triggers filter loading"""
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/*": "transform"}'
        )

        filters = get_cached_filters("secrets-replicator/filters/test", 300, mock_client)

        assert filters == {"app/*": "transform"}
        mock_client.get_secret.assert_called_once()

    def test_cache_hit_skips_loading(self):
        """Cache hit returns cached filters without loading"""
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/*": "transform"}'
        )

        # First call - cache miss
        get_cached_filters("secrets-replicator/filters/test", 300, mock_client)
        # Second call - cache hit
        filters = get_cached_filters("secrets-replicator/filters/test", 300, mock_client)

        assert filters == {"app/*": "transform"}
        # Should only be called once due to caching
        assert mock_client.get_secret.call_count == 1

    def test_cache_invalidated_on_filter_list_change(self):
        """Cache is invalidated when filter list changes"""
        mock_client = MagicMock()
        mock_client.get_secret.side_effect = [
            MagicMock(secret_string='{"app/*": "transform-a"}'),
            MagicMock(secret_string='{"db/*": "transform-b"}')
        ]

        # First call with filter-a
        filters_a = get_cached_filters("secrets-replicator/filters/a", 300, mock_client)
        # Second call with filter-b (different list)
        filters_b = get_cached_filters("secrets-replicator/filters/b", 300, mock_client)

        assert filters_a == {"app/*": "transform-a"}
        assert filters_b == {"db/*": "transform-b"}
        assert mock_client.get_secret.call_count == 2


class TestShouldReplicateHardcodedExclusions:
    """Test hardcoded exclusion for system secrets"""

    def setup_method(self):
        """Clear cache and create config before each test"""
        clear_filter_cache()
        self.config = ReplicatorConfig(destinations=[])
        self.mock_client = MagicMock()

    def test_transformation_secret_excluded(self):
        """Transformation secrets are always excluded"""
        result, transform = should_replicate_secret(
            'secrets-replicator/transformations/my-sed',
            self.config,
            self.mock_client
        )
        assert result is False
        assert transform is None

    def test_transformation_secret_nested_excluded(self):
        """Nested transformation secrets are excluded"""
        result, transform = should_replicate_secret(
            'secrets-replicator/transformations/databases/prod-db',
            self.config,
            self.mock_client
        )
        assert result is False
        assert transform is None

    def test_filter_secret_excluded(self):
        """Filter secrets are always excluded"""
        result, transform = should_replicate_secret(
            'secrets-replicator/filters/prod',
            self.config,
            self.mock_client
        )
        assert result is False
        assert transform is None

    def test_config_secret_excluded(self):
        """Config secrets are always excluded"""
        result, transform = should_replicate_secret(
            'secrets-replicator/config/destinations',
            self.config,
            self.mock_client
        )
        assert result is False
        assert transform is None

    def test_name_mapping_secret_excluded(self):
        """Name mapping secrets are always excluded"""
        result, transform = should_replicate_secret(
            'secrets-replicator/names/prod-mappings',
            self.config,
            self.mock_client
        )
        assert result is False
        assert transform is None


class TestShouldReplicateNoFilter:
    """Test behavior when SECRETS_FILTER is not configured"""

    def setup_method(self):
        """Clear cache and create config without SECRETS_FILTER"""
        clear_filter_cache()
        self.config = ReplicatorConfig(destinations=[], secrets_filter=None)
        self.mock_client = MagicMock()

    def test_no_filter_allows_all_secrets(self):
        """Without SECRETS_FILTER, all secrets are allowed"""
        result, transform = should_replicate_secret(
            'any-secret',
            self.config,
            self.mock_client
        )
        assert result is True
        assert transform is None

    def test_no_filter_no_transformation(self):
        """Without SECRETS_FILTER, no transformation is applied"""
        result, transform = should_replicate_secret(
            'prod-db',
            self.config,
            self.mock_client
        )
        assert result is True
        assert transform is None

    def test_no_filter_still_excludes_system_secrets(self):
        """Without SECRETS_FILTER, system secrets are still excluded"""
        result, transform = should_replicate_secret(
            'secrets-replicator/transformations/test',
            self.config,
            self.mock_client
        )
        assert result is False


class TestShouldReplicateWithFilter:
    """Test behavior when SECRETS_FILTER is configured"""

    def setup_method(self):
        """Clear cache and create config with SECRETS_FILTER"""
        clear_filter_cache()
        self.config = ReplicatorConfig(
            destinations=[],
            secrets_filter='secrets-replicator/filters/prod'
        )
        self.mock_client = MagicMock()

    def test_filter_match_with_transformation(self):
        """Filter match returns transformation name"""
        self.mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/prod/*": "region-swap"}'
        )

        result, transform = should_replicate_secret(
            'app/prod/db',
            self.config,
            self.mock_client
        )

        assert result is True
        assert transform == 'region-swap'

    def test_filter_match_without_transformation(self):
        """Filter match with null transformation replicates without transform"""
        self.mock_client.get_secret.return_value = MagicMock(
            secret_string='{"critical-secret": null}'
        )

        result, transform = should_replicate_secret(
            'critical-secret',
            self.config,
            self.mock_client
        )

        assert result is True
        assert transform is None

    def test_filter_no_match_denies_replication(self):
        """No filter match denies replication"""
        self.mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/prod/*": "region-swap"}'
        )

        result, transform = should_replicate_secret(
            'other-secret',
            self.config,
            self.mock_client
        )

        assert result is False
        assert transform is None

    def test_filter_load_failure_denies_replication(self):
        """Filter loading failure denies replication for safety"""
        self.mock_client.get_secret.side_effect = Exception("Access denied")

        result, transform = should_replicate_secret(
            'any-secret',
            self.config,
            self.mock_client
        )

        assert result is False
        assert transform is None

    def test_empty_filters_denies_replication(self):
        """Empty filters (all failed to load) denies replication"""
        self.mock_client.get_secret.return_value = MagicMock(
            secret_string='{}'
        )

        result, transform = should_replicate_secret(
            'any-secret',
            self.config,
            self.mock_client
        )

        assert result is False
        assert transform is None


class TestShouldReplicateComplexScenarios:
    """Test complex real-world scenarios"""

    def setup_method(self):
        """Clear cache before each test"""
        clear_filter_cache()

    def test_production_secrets_only(self):
        """Replicate only production secrets"""
        config = ReplicatorConfig(
            destinations=[],
            secrets_filter='secrets-replicator/filters/prod'
        )
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/prod/*": "region-swap", "db/prod/*": "connection-transform"}'
        )

        # Production secrets are replicated
        result, transform = should_replicate_secret('app/prod/api', config, mock_client)
        assert result is True
        assert transform == 'region-swap'

        # Non-production secrets are denied
        clear_filter_cache()  # Clear cache to reload filters
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/prod/*": "region-swap", "db/prod/*": "connection-transform"}'
        )
        result, transform = should_replicate_secret('app/dev/api', config, mock_client)
        assert result is False

    def test_transformation_chain(self):
        """Comma-separated transformation names in filter"""
        config = ReplicatorConfig(
            destinations=[],
            secrets_filter='secrets-replicator/filters/complex'
        )
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/prod/*": "region-swap,endpoint-update"}'
        )

        result, transform = should_replicate_secret('app/prod/api', config, mock_client)

        assert result is True
        assert transform == 'region-swap,endpoint-update'

    def test_multiple_filter_secrets(self):
        """Multiple filter secrets are merged correctly"""
        config = ReplicatorConfig(
            destinations=[],
            secrets_filter='secrets-replicator/filters/base,secrets-replicator/filters/override'
        )
        mock_client = MagicMock()
        mock_client.get_secret.side_effect = [
            MagicMock(secret_string='{"app/*": "base-transform"}'),
            MagicMock(secret_string='{"app/prod/*": "prod-transform"}')
        ]

        # Both patterns match, but app/* is checked first (dict iteration order)
        # The merged dict has both patterns, first wildcard match wins
        result, transform = should_replicate_secret('app/prod/db', config, mock_client)
        assert result is True
        # First wildcard match wins (app/* matches before app/prod/*)
        assert transform == 'base-transform'


class TestIsSystemSecret:
    """Test is_system_secret function for hardcoded exclusions"""

    def test_transformation_secret(self):
        """Transformation secrets are system secrets"""
        assert is_system_secret('secrets-replicator/transformations/my-sed') is True
        assert is_system_secret('secrets-replicator/transformations/nested/path') is True

    def test_filter_secret(self):
        """Filter secrets are system secrets"""
        assert is_system_secret('secrets-replicator/filters/prod') is True

    def test_config_secret(self):
        """Config secrets are system secrets"""
        assert is_system_secret('secrets-replicator/config/destinations') is True

    def test_names_secret(self):
        """Name mapping secrets are system secrets"""
        assert is_system_secret('secrets-replicator/names/prod-mappings') is True

    def test_normal_secret(self):
        """Normal secrets are not system secrets"""
        assert is_system_secret('app/prod/database') is False
        assert is_system_secret('my-secret') is False
        assert is_system_secret('transformations/old-style') is False


class TestGetDestinationTransformation:
    """Test per-destination filtering with get_destination_transformation"""

    def setup_method(self):
        """Clear cache before each test"""
        clear_filter_cache()

    def test_destination_with_filters(self):
        """Destination-level filters override global config"""
        destination = DestinationConfig(
            region='us-west-2',
            filters='secrets-replicator/filters/us-west-2'
        )
        global_config = ReplicatorConfig(
            destinations=[],
            secrets_filter='secrets-replicator/filters/global'
        )
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/*": "west-transform"}'
        )

        result, transform = get_destination_transformation(
            'app/prod/db', destination, global_config, mock_client
        )

        assert result is True
        assert transform == 'west-transform'
        # Should load destination filter, not global
        mock_client.get_secret.assert_called_with(
            secret_id='secrets-replicator/filters/us-west-2'
        )

    def test_destination_without_filters_uses_global(self):
        """Destination without filters uses global SECRETS_FILTER"""
        destination = DestinationConfig(region='us-west-2')  # No filters
        global_config = ReplicatorConfig(
            destinations=[],
            secrets_filter='secrets-replicator/filters/global'
        )
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/*": "global-transform"}'
        )

        result, transform = get_destination_transformation(
            'app/prod/db', destination, global_config, mock_client
        )

        assert result is True
        assert transform == 'global-transform'
        # Should load global filter
        mock_client.get_secret.assert_called_with(
            secret_id='secrets-replicator/filters/global'
        )

    def test_no_filters_anywhere(self):
        """No filters configured - allow all, no transformation"""
        destination = DestinationConfig(region='us-west-2')
        global_config = ReplicatorConfig(destinations=[], secrets_filter=None)
        mock_client = MagicMock()

        result, transform = get_destination_transformation(
            'any-secret', destination, global_config, mock_client
        )

        assert result is True
        assert transform is None
        # Should not call get_secret
        mock_client.get_secret.assert_not_called()

    def test_secret_not_matching_destination_filter(self):
        """Secret not matching destination filter is denied"""
        destination = DestinationConfig(
            region='us-west-2',
            filters='secrets-replicator/filters/us-west-2'
        )
        global_config = ReplicatorConfig(destinations=[], secrets_filter=None)
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(
            secret_string='{"app/prod/*": "transform"}'
        )

        result, transform = get_destination_transformation(
            'other-secret', destination, global_config, mock_client
        )

        assert result is False
        assert transform is None

    def test_different_destinations_different_transforms(self):
        """Different destinations can have different transformations"""
        clear_filter_cache()

        dest_west = DestinationConfig(
            region='us-west-2',
            filters='secrets-replicator/filters/us-west-2'
        )
        dest_east = DestinationConfig(
            region='us-east-1',
            filters='secrets-replicator/filters/us-east-1'
        )
        global_config = ReplicatorConfig(destinations=[], secrets_filter=None)

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = [
            MagicMock(secret_string='{"app/*": "west-transform"}'),
            MagicMock(secret_string='{"app/*": "east-transform"}')
        ]

        # Check west destination
        result_west, transform_west = get_destination_transformation(
            'app/db', dest_west, global_config, mock_client
        )

        # Clear cache to force reload for different destination
        clear_filter_cache()

        # Check east destination
        result_east, transform_east = get_destination_transformation(
            'app/db', dest_east, global_config, mock_client
        )

        assert result_west is True
        assert transform_west == 'west-transform'
        assert result_east is True
        assert transform_east == 'east-transform'
