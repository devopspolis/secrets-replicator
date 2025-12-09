"""
Tests for filtering logic (Lambda-side filtering with tag support).

Tests ADR-001 (Lambda-Side Filtering) and ADR-003 (Hardcoded Exclusion).
"""

import pytest
from src.handler import should_replicate
from src.config import parse_tag_filters, ReplicatorConfig, ConfigurationError


class TestParseTagFilters:
    """Test tag parsing helper function"""

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


class TestShouldReplicateTransformationSecrets:
    """Test hardcoded exclusion for transformation secrets (ADR-003)"""

    def test_transformation_secret_excluded(self):
        """Transformation secrets are always excluded"""
        config = ReplicatorConfig(dest_region='us-west-2')

        assert should_replicate('secrets-replicator/transformations/my-sed', {}, config) is False
        assert should_replicate('secrets-replicator/transformations/databases/prod-db', {}, config) is False
        assert should_replicate('secrets-replicator/transformations/', {}, config) is False

    def test_transformation_secret_excluded_even_with_include_tag(self):
        """Transformation secrets excluded even if they have include tags"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_include_tags=[('Replicate', 'true')]
        )
        tags = {'Replicate': 'true'}

        assert should_replicate('secrets-replicator/transformations/my-sed', tags, config) is False

    def test_transformation_secret_custom_prefix(self):
        """Custom transformation secret prefix is respected"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            transformation_secret_prefix='my-transforms/'
        )

        assert should_replicate('my-transforms/sed-file', {}, config) is False
        assert should_replicate('secrets-replicator/transformations/sed-file', {}, config) is True

    def test_transformation_secret_old_prefix_not_excluded(self):
        """Old prefix 'transformations/' is NOT excluded with new default"""
        config = ReplicatorConfig(dest_region='us-west-2')

        # Old prefix should now be treated as normal secret
        assert should_replicate('transformations/my-sed', {}, config) is True

        # New prefix should be excluded
        assert should_replicate('secrets-replicator/transformations/my-sed', {}, config) is False


class TestShouldReplicateExcludeTags:
    """Test exclude tag filtering (Layer 2)"""

    def test_exclude_tag_skips_replication(self):
        """Secret with exclude tag is not replicated"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_exclude_tags=[('SkipReplication', 'true')]
        )
        tags = {'SkipReplication': 'true'}

        assert should_replicate('prod-db', tags, config) is False

    def test_exclude_tag_multiple_filters(self):
        """Multiple exclude tag filters work correctly"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_exclude_tags=[
                ('SkipReplication', 'true'),
                ('Environment', 'test')
            ]
        )

        assert should_replicate('prod-db', {'SkipReplication': 'true'}, config) is False
        assert should_replicate('test-db', {'Environment': 'test'}, config) is False
        assert should_replicate('prod-db', {'Environment': 'production'}, config) is True

    def test_exclude_tag_takes_precedence_over_include(self):
        """Exclude tags override include filters"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_list=['prod-db'],
            source_exclude_tags=[('SkipReplication', 'true')]
        )
        tags = {'SkipReplication': 'true'}

        # Even though it's in the include list, exclude tag wins
        assert should_replicate('prod-db', tags, config) is False


class TestShouldReplicateIncludePattern:
    """Test include pattern filtering (Layer 3)"""

    def test_pattern_match_simple(self):
        """Simple regex pattern matching"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_pattern=r'^prod-.*'
        )

        assert should_replicate('prod-db', {}, config) is True
        assert should_replicate('prod-api-key', {}, config) is True
        assert should_replicate('dev-db', {}, config) is False

    def test_pattern_match_complex(self):
        """Complex regex pattern matching"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_pattern=r'^(prod|qa)-(db|api|cache)$'
        )

        assert should_replicate('prod-db', {}, config) is True
        assert should_replicate('qa-api', {}, config) is True
        assert should_replicate('dev-db', {}, config) is False
        assert should_replicate('prod-unknown', {}, config) is False


class TestShouldReplicateIncludeList:
    """Test include list filtering (Layer 3)"""

    def test_list_match(self):
        """Explicit list matching"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_list=['shared-redis', 'shared-cache', 'prod-db']
        )

        assert should_replicate('shared-redis', {}, config) is True
        assert should_replicate('prod-db', {}, config) is True
        assert should_replicate('other-secret', {}, config) is False

    def test_empty_list(self):
        """Empty list with no other filters replicates all"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_list=[]
        )

        assert should_replicate('any-secret', {}, config) is True


class TestShouldReplicateIncludeTags:
    """Test include tag filtering (Layer 3)"""

    def test_include_tag_match(self):
        """Secret with include tag is replicated"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_include_tags=[('Replicate', 'true')]
        )

        assert should_replicate('any-secret', {'Replicate': 'true'}, config) is True
        assert should_replicate('any-secret', {'Replicate': 'false'}, config) is False
        assert should_replicate('any-secret', {}, config) is False

    def test_include_tag_multiple_filters(self):
        """Multiple include tag filters use OR logic"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_include_tags=[
                ('Replicate', 'true'),
                ('Environment', 'production')
            ]
        )

        # Match first tag
        assert should_replicate('db1', {'Replicate': 'true'}, config) is True

        # Match second tag
        assert should_replicate('db2', {'Environment': 'production'}, config) is True

        # Match both tags
        assert should_replicate('db3', {'Replicate': 'true', 'Environment': 'production'}, config) is True

        # Match neither tag
        assert should_replicate('db4', {'Environment': 'dev'}, config) is False


class TestShouldReplicateOrLogic:
    """Test OR logic across different include filter types"""

    def test_or_logic_pattern_and_list(self):
        """Pattern OR list matching"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_pattern=r'^prod-.*',
            source_secret_list=['shared-cache']
        )

        # Matches pattern
        assert should_replicate('prod-db', {}, config) is True

        # In list
        assert should_replicate('shared-cache', {}, config) is True

        # Matches neither
        assert should_replicate('dev-db', {}, config) is False

    def test_or_logic_all_filters(self):
        """Pattern OR list OR tags matching"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_pattern=r'^prod-.*',
            source_secret_list=['shared-cache'],
            source_include_tags=[('Replicate', 'true')]
        )

        # Matches pattern only
        assert should_replicate('prod-db', {}, config) is True

        # In list only
        assert should_replicate('shared-cache', {}, config) is True

        # Has include tag only
        assert should_replicate('custom-secret', {'Replicate': 'true'}, config) is True

        # Matches multiple conditions
        assert should_replicate('prod-db', {'Replicate': 'true'}, config) is True

        # Matches none
        assert should_replicate('dev-db', {}, config) is False


class TestShouldReplicateDefaultBehavior:
    """Test default behavior when no filters are configured"""

    def test_no_filters_replicates_all(self):
        """No filters means replicate everything (except transformation secrets)"""
        config = ReplicatorConfig(dest_region='us-west-2')

        assert should_replicate('any-secret', {}, config) is True
        assert should_replicate('prod-db', {}, config) is True
        assert should_replicate('dev-api-key', {}, config) is True

        # Except transformation secrets (new prefix)
        assert should_replicate('secrets-replicator/transformations/my-sed', {}, config) is False

        # Old prefix is treated as normal secret now
        assert should_replicate('transformations/my-sed', {}, config) is True


class TestShouldReplicateComplexScenarios:
    """Test complex real-world scenarios"""

    def test_scenario_production_secrets_only(self):
        """Replicate only production secrets, skip test environments"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_include_tags=[('Environment', 'production')],
            source_exclude_tags=[('SkipReplication', 'true')]
        )

        # Production secret without skip tag
        assert should_replicate('prod-db', {'Environment': 'production'}, config) is True

        # Production secret with skip tag (skip wins)
        assert should_replicate('prod-temp', {'Environment': 'production', 'SkipReplication': 'true'}, config) is False

        # Non-production secret
        assert should_replicate('dev-db', {'Environment': 'development'}, config) is False

    def test_scenario_mixed_filters(self):
        """Complex scenario with all filter types"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_pattern=r'^app-.*',
            source_secret_list=['shared-redis', 'shared-postgres'],
            source_include_tags=[('CriticalService', 'true')],
            source_exclude_tags=[('Deprecated', 'true'), ('Testing', 'true')]
        )

        # Matches pattern
        assert should_replicate('app-api-key', {}, config) is True

        # In shared list
        assert should_replicate('shared-redis', {}, config) is True

        # Has critical service tag
        assert should_replicate('payment-processor', {'CriticalService': 'true'}, config) is True

        # Matches pattern but deprecated (exclude wins)
        assert should_replicate('app-old-service', {'Deprecated': 'true'}, config) is False

        # Matches nothing
        assert should_replicate('random-secret', {}, config) is False

    def test_scenario_transformation_secret_with_all_includes(self):
        """Transformation secret excluded even with all include criteria"""
        config = ReplicatorConfig(
            dest_region='us-west-2',
            source_secret_pattern=r'secrets-replicator/transformations/.*',
            source_secret_list=['secrets-replicator/transformations/my-sed'],
            source_include_tags=[('Include', 'true')]
        )

        # Even though it matches pattern, list, and tags - still excluded
        tags = {'Include': 'true'}
        assert should_replicate('secrets-replicator/transformations/my-sed', tags, config) is False
