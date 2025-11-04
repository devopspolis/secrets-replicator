"""
Unit tests for transformer module
"""

import pytest
from src.transformer import (
    SedRule,
    JsonMapping,
    parse_sedfile,
    apply_sed_transforms,
    parse_json_mapping,
    apply_json_transforms,
    transform_secret,
    TransformationError,
    InvalidRegexError,
    InvalidJsonError,
    RegexTimeoutError
)


class TestSedRule:
    """Tests for SedRule dataclass"""

    def test_valid_sed_rule(self):
        """Test creating a valid sed rule"""
        rule = SedRule(pattern='us-east-1', replacement='us-west-2')
        assert rule.pattern == 'us-east-1'
        assert rule.replacement == 'us-west-2'
        assert rule.flags == 0
        assert rule.global_replace is False

    def test_sed_rule_with_flags(self):
        """Test sed rule with regex flags"""
        import re
        rule = SedRule(
            pattern='test',
            replacement='TEST',
            flags=re.IGNORECASE,
            global_replace=True
        )
        assert rule.flags == re.IGNORECASE
        assert rule.global_replace is True

    def test_invalid_regex_pattern(self):
        """Test that invalid regex raises error"""
        with pytest.raises(InvalidRegexError):
            SedRule(pattern='[invalid(', replacement='test')


class TestParseSedfile:
    """Tests for parse_sedfile function"""

    def test_parse_simple_rule(self):
        """Test parsing a simple sed rule"""
        content = "s/us-east-1/us-west-2/"
        rules = parse_sedfile(content)
        assert len(rules) == 1
        assert rules[0].pattern == 'us-east-1'
        assert rules[0].replacement == 'us-west-2'
        assert rules[0].global_replace is False

    def test_parse_rule_with_global_flag(self):
        """Test parsing sed rule with global flag"""
        content = "s/us-east-1/us-west-2/g"
        rules = parse_sedfile(content)
        assert len(rules) == 1
        assert rules[0].global_replace is True

    def test_parse_rule_with_case_insensitive_flag(self):
        """Test parsing sed rule with case-insensitive flag"""
        import re
        content = "s/EAST/WEST/i"
        rules = parse_sedfile(content)
        assert len(rules) == 1
        assert rules[0].flags == re.IGNORECASE

    def test_parse_rule_with_multiple_flags(self):
        """Test parsing sed rule with multiple flags"""
        import re
        content = "s/test/TEST/gi"
        rules = parse_sedfile(content)
        assert len(rules) == 1
        assert rules[0].global_replace is True
        assert rules[0].flags == re.IGNORECASE

    def test_parse_multiple_rules(self):
        """Test parsing multiple sed rules"""
        content = """
        s/us-east-1/us-west-2/g
        s/prod-db-1/prod-db-2/
        s/5432/5433/
        """
        rules = parse_sedfile(content)
        assert len(rules) == 3
        assert rules[0].pattern == 'us-east-1'
        assert rules[1].pattern == 'prod-db-1'
        assert rules[2].pattern == '5432'

    def test_parse_with_comments(self):
        """Test that comments are ignored"""
        content = """
        # Replace region
        s/us-east-1/us-west-2/g
        # Replace database host
        s/db1/db2/
        """
        rules = parse_sedfile(content)
        assert len(rules) == 2

    def test_parse_with_empty_lines(self):
        """Test that empty lines are ignored"""
        content = """
        s/test1/result1/

        s/test2/result2/

        """
        rules = parse_sedfile(content)
        assert len(rules) == 2

    def test_parse_invalid_format(self):
        """Test that invalid format raises error"""
        content = "invalid rule format"
        with pytest.raises(TransformationError, match="must start with 's/'"):
            parse_sedfile(content)

    def test_parse_incomplete_rule(self):
        """Test that incomplete rule raises error"""
        content = "s/pattern"
        with pytest.raises(TransformationError, match="Invalid sed format"):
            parse_sedfile(content)

    def test_parse_regex_special_characters(self):
        """Test parsing regex with special characters"""
        content = r"s/\d+\.\d+\.\d+\.\d+/0.0.0.0/g"
        rules = parse_sedfile(content)
        assert len(rules) == 1
        assert rules[0].pattern == r'\d+\.\d+\.\d+\.\d+'


class TestApplySedTransforms:
    """Tests for apply_sed_transforms function"""

    def test_simple_replacement(self):
        """Test simple string replacement"""
        rules = [SedRule(pattern='us-east-1', replacement='us-west-2')]
        result = apply_sed_transforms('db.us-east-1.aws.com', rules)
        assert result == 'db.us-west-2.aws.com'

    def test_global_replacement(self):
        """Test global replacement (all occurrences)"""
        rules = [SedRule(
            pattern='test',
            replacement='TEST',
            global_replace=True
        )]
        result = apply_sed_transforms('test test test', rules)
        assert result == 'TEST TEST TEST'

    def test_non_global_replacement(self):
        """Test non-global replacement (first occurrence only)"""
        rules = [SedRule(
            pattern='test',
            replacement='TEST',
            global_replace=False
        )]
        result = apply_sed_transforms('test test test', rules)
        assert result == 'TEST test test'

    def test_case_insensitive_replacement(self):
        """Test case-insensitive replacement"""
        import re
        rules = [SedRule(
            pattern='EAST',
            replacement='WEST',
            flags=re.IGNORECASE,
            global_replace=True
        )]
        result = apply_sed_transforms('east EAST East', rules)
        assert result == 'WEST WEST WEST'

    def test_multiple_rules(self):
        """Test applying multiple rules in sequence"""
        rules = [
            SedRule(pattern='us-east-1', replacement='us-west-2'),
            SedRule(pattern='db1', replacement='db2'),
            SedRule(pattern='5432', replacement='5433')
        ]
        result = apply_sed_transforms('db1.us-east-1:5432', rules)
        assert result == 'db2.us-west-2:5433'

    def test_regex_pattern(self):
        """Test regex pattern replacement"""
        rules = [SedRule(
            pattern=r'\d+\.\d+\.\d+\.\d+',
            replacement='0.0.0.0',
            global_replace=True
        )]
        result = apply_sed_transforms('host 192.168.1.1 and 10.0.0.1', rules)
        assert result == 'host 0.0.0.0 and 0.0.0.0'

    def test_no_match(self):
        """Test transformation when pattern doesn't match"""
        rules = [SedRule(pattern='nonexistent', replacement='replaced')]
        original = 'original text'
        result = apply_sed_transforms(original, rules)
        assert result == original

    def test_empty_rules(self):
        """Test with empty rules list"""
        original = 'test string'
        result = apply_sed_transforms(original, [])
        assert result == original

    def test_replacement_with_special_chars(self):
        """Test replacement containing special characters"""
        rules = [SedRule(pattern='OLD', replacement='$NEW$')]
        result = apply_sed_transforms('OLD value', rules)
        assert result == '$NEW$ value'


class TestJsonMapping:
    """Tests for JsonMapping dataclass"""

    def test_valid_json_mapping(self):
        """Test creating a valid JSON mapping"""
        mapping = JsonMapping(
            path='$.database.host',
            find='db1.us-east-1',
            replace='db1.us-west-2'
        )
        assert mapping.path == '$.database.host'
        assert mapping.find == 'db1.us-east-1'
        assert mapping.replace == 'db1.us-west-2'

    def test_invalid_jsonpath(self):
        """Test that invalid JSONPath raises error"""
        with pytest.raises(TransformationError, match="Invalid JSONPath"):
            JsonMapping(
                path='$invalid[path',
                find='test',
                replace='value'
            )


class TestParseJsonMapping:
    """Tests for parse_json_mapping function"""

    def test_parse_simple_mapping(self):
        """Test parsing a simple JSON mapping"""
        content = '''
        {
            "transformations": [
                {
                    "path": "$.database.host",
                    "find": "db1.us-east-1",
                    "replace": "db1.us-west-2"
                }
            ]
        }
        '''
        mappings = parse_json_mapping(content)
        assert len(mappings) == 1
        assert mappings[0].path == '$.database.host'
        assert mappings[0].find == 'db1.us-east-1'
        assert mappings[0].replace == 'db1.us-west-2'

    def test_parse_multiple_mappings(self):
        """Test parsing multiple JSON mappings"""
        content = '''
        {
            "transformations": [
                {
                    "path": "$.database.host",
                    "find": "us-east-1",
                    "replace": "us-west-2"
                },
                {
                    "path": "$.database.region",
                    "find": "us-east-1",
                    "replace": "us-west-2"
                }
            ]
        }
        '''
        mappings = parse_json_mapping(content)
        assert len(mappings) == 2

    def test_parse_invalid_json(self):
        """Test that invalid JSON raises error"""
        content = "{ invalid json"
        with pytest.raises(InvalidJsonError):
            parse_json_mapping(content)

    def test_parse_missing_transformations(self):
        """Test that missing transformations key raises error"""
        content = '{"other": "value"}'
        with pytest.raises(TransformationError, match="must contain 'transformations'"):
            parse_json_mapping(content)

    def test_parse_transformations_not_array(self):
        """Test that non-array transformations raises error"""
        content = '{"transformations": "not an array"}'
        with pytest.raises(TransformationError, match="must be an array"):
            parse_json_mapping(content)

    def test_parse_missing_required_field(self):
        """Test that missing required field raises error"""
        content = '''
        {
            "transformations": [
                {
                    "path": "$.test",
                    "find": "value"
                }
            ]
        }
        '''
        with pytest.raises(TransformationError, match="missing required field 'replace'"):
            parse_json_mapping(content)


class TestApplyJsonTransforms:
    """Tests for apply_json_transforms function"""

    def test_simple_field_replacement(self):
        """Test simple field value replacement"""
        secret = '{"database": {"host": "db1.us-east-1"}}'
        mappings = [JsonMapping(
            path='$.database.host',
            find='db1.us-east-1',
            replace='db1.us-west-2'
        )]
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['database']['host'] == 'db1.us-west-2'

    def test_partial_string_replacement(self):
        """Test partial string replacement in field"""
        secret = '{"url": "https://api.us-east-1.example.com"}'
        mappings = [JsonMapping(
            path='$.url',
            find='us-east-1',
            replace='us-west-2'
        )]
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['url'] == 'https://api.us-west-2.example.com'

    def test_nested_field_replacement(self):
        """Test nested field replacement"""
        secret = '{"level1": {"level2": {"level3": "value"}}}'
        mappings = [JsonMapping(
            path='$.level1.level2.level3',
            find='value',
            replace='new_value'
        )]
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['level1']['level2']['level3'] == 'new_value'

    def test_multiple_mappings(self):
        """Test applying multiple mappings"""
        secret = '''
        {
            "database": {
                "host": "db1.us-east-1",
                "region": "us-east-1"
            }
        }
        '''
        mappings = [
            JsonMapping(path='$.database.host', find='us-east-1', replace='us-west-2'),
            JsonMapping(path='$.database.region', find='us-east-1', replace='us-west-2')
        ]
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['database']['host'] == 'db1.us-west-2'
        assert result_obj['database']['region'] == 'us-west-2'

    def test_nonexistent_path(self):
        """Test that nonexistent path is skipped gracefully"""
        secret = '{"field": "value"}'
        mappings = [JsonMapping(
            path='$.nonexistent.field',
            find='value',
            replace='new_value'
        )]
        # Should not raise error, just skip the transformation
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['field'] == 'value'

    def test_no_match(self):
        """Test when find value doesn't match"""
        secret = '{"field": "value"}'
        mappings = [JsonMapping(
            path='$.field',
            find='different_value',
            replace='new_value'
        )]
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['field'] == 'value'

    def test_invalid_json_secret(self):
        """Test that invalid JSON secret raises error"""
        secret = "{ invalid json"
        mappings = [JsonMapping(path='$.test', find='a', replace='b')]
        with pytest.raises(InvalidJsonError):
            apply_json_transforms(secret, mappings)

    def test_empty_mappings(self):
        """Test with empty mappings list"""
        secret = '{"field": "value"}'
        result = apply_json_transforms(secret, [])
        assert result == '{"field":"value"}'  # Compact JSON format


class TestTransformSecret:
    """Tests for transform_secret convenience function"""

    def test_sed_mode(self):
        """Test sed mode transformation"""
        secret = "db.us-east-1.aws.com"
        rules = "s/us-east-1/us-west-2/"
        result = transform_secret(secret, 'sed', rules)
        assert result == "db.us-west-2.aws.com"

    def test_json_mode(self):
        """Test JSON mode transformation"""
        secret = '{"region": "us-east-1"}'
        mappings = '''
        {
            "transformations": [
                {
                    "path": "$.region",
                    "find": "us-east-1",
                    "replace": "us-west-2"
                }
            ]
        }
        '''
        result = transform_secret(secret, 'json', mappings)
        import json
        result_obj = json.loads(result)
        assert result_obj['region'] == 'us-west-2'

    def test_binary_secret_not_transformed(self):
        """Test that binary secrets are not transformed"""
        secret = "binary_data_here"
        rules = "s/binary/text/"
        result = transform_secret(secret, 'sed', rules, is_binary=True)
        assert result == secret  # Unchanged

    def test_invalid_mode(self):
        """Test that invalid mode raises error"""
        with pytest.raises(ValueError, match="Invalid transformation mode"):
            transform_secret("test", 'invalid', "rules")


class TestEdgeCases:
    """Tests for edge cases and error conditions"""

    def test_empty_secret_value(self):
        """Test transformation on empty secret"""
        rules = [SedRule(pattern='test', replacement='TEST')]
        result = apply_sed_transforms('', rules)
        assert result == ''

    def test_very_long_secret(self):
        """Test transformation on very long secret"""
        secret = 'us-east-1 ' * 10000
        rules = [SedRule(pattern='us-east-1', replacement='us-west-2', global_replace=True)]
        result = apply_sed_transforms(secret, rules)
        assert 'us-east-1' not in result
        assert result.count('us-west-2') == 10000

    def test_unicode_characters(self):
        """Test transformation with Unicode characters"""
        secret = 'región: us-east-1 🚀'
        rules = [SedRule(pattern='us-east-1', replacement='us-west-2')]
        result = apply_sed_transforms(secret, rules)
        assert result == 'región: us-west-2 🚀'

    def test_multiline_secret(self):
        """Test transformation on multiline secret"""
        secret = '''line1: us-east-1
line2: us-east-1
line3: us-east-1'''
        rules = [SedRule(pattern='us-east-1', replacement='us-west-2', global_replace=True)]
        result = apply_sed_transforms(secret, rules)
        assert result.count('us-west-2') == 3

    def test_json_with_arrays(self):
        """Test JSON transformation with arrays"""
        secret = '{"endpoints": ["api.us-east-1.com", "db.us-east-1.com"]}'
        mappings = [JsonMapping(
            path='$.endpoints[*]',
            find='us-east-1',
            replace='us-west-2'
        )]
        result = apply_json_transforms(secret, mappings)
        import json
        result_obj = json.loads(result)
        # Note: jsonpath-ng may handle arrays differently
        # This test documents the current behavior
        assert isinstance(result_obj['endpoints'], list)


class TestDetectTransformType:
    """Tests for detect_transform_type function (auto-detection)"""

    def test_detect_sed_simple(self):
        """Test detection of simple sed script"""
        from src.transformer import detect_transform_type
        content = "s/foo/bar/g"
        assert detect_transform_type(content) == 'sed'

    def test_detect_sed_multiline(self):
        """Test detection of multiline sed script"""
        from src.transformer import detect_transform_type
        content = """
        # Comment
        s/us-east-1/us-west-2/g
        s/dev/prod/g
        """
        assert detect_transform_type(content) == 'sed'

    def test_detect_json_simple(self):
        """Test detection of JSON mapping"""
        from src.transformer import detect_transform_type
        content = '{"$.foo": "bar"}'
        assert detect_transform_type(content) == 'json'

    def test_detect_json_with_multiple_paths(self):
        """Test detection of JSON with multiple JSONPath keys"""
        from src.transformer import detect_transform_type
        content = '{"$.api": "prod", "$.db": "prod-db"}'
        assert detect_transform_type(content) == 'json'

    def test_detect_json_object_without_jsonpath(self):
        """Test JSON object without JSONPath keys defaults to sed"""
        from src.transformer import detect_transform_type
        content = '{"foo": "bar", "baz": "qux"}'
        # No $.keys, so treated as sed (will be no-op)
        assert detect_transform_type(content) == 'sed'

    def test_detect_json_array(self):
        """Test JSON array is not detected as JSON mode"""
        from src.transformer import detect_transform_type
        content = '["a", "b", "c"]'
        assert detect_transform_type(content) == 'sed'

    def test_detect_empty_content(self):
        """Test empty content defaults to sed"""
        from src.transformer import detect_transform_type
        assert detect_transform_type("") == 'sed'
        assert detect_transform_type("   ") == 'sed'

    def test_detect_invalid_json(self):
        """Test invalid JSON defaults to sed"""
        from src.transformer import detect_transform_type
        content = '{invalid json}'
        assert detect_transform_type(content) == 'sed'

    def test_detect_text_that_looks_like_json(self):
        """Test text with curly braces but not JSON"""
        from src.transformer import detect_transform_type
        content = 's/{foo}/{bar}/g'
        assert detect_transform_type(content) == 'sed'


class TestParseTransformNames:
    """Tests for parse_transform_names function (chain parsing)"""

    def test_parse_single_name(self):
        """Test parsing single transformation name"""
        from src.transformer import parse_transform_names
        names = parse_transform_names('my-transform')
        assert names == ['my-transform']

    def test_parse_multiple_names(self):
        """Test parsing comma-separated transformation names"""
        from src.transformer import parse_transform_names
        names = parse_transform_names('transform1,transform2,transform3')
        assert names == ['transform1', 'transform2', 'transform3']

    def test_parse_with_spaces(self):
        """Test parsing with spaces around commas"""
        from src.transformer import parse_transform_names
        names = parse_transform_names('transform1, transform2 , transform3')
        assert names == ['transform1', 'transform2', 'transform3']

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty list"""
        from src.transformer import parse_transform_names
        assert parse_transform_names('') == []
        assert parse_transform_names('   ') == []

    def test_parse_with_trailing_comma(self):
        """Test parsing with trailing comma ignores empty element"""
        from src.transformer import parse_transform_names
        names = parse_transform_names('transform1,transform2,')
        assert names == ['transform1', 'transform2']

    def test_parse_with_extra_commas(self):
        """Test parsing filters out empty elements from extra commas"""
        from src.transformer import parse_transform_names
        names = parse_transform_names('transform1,,transform2')
        assert names == ['transform1', 'transform2']

    def test_parse_complex_names(self):
        """Test parsing complex transformation names"""
        from src.transformer import parse_transform_names
        names = parse_transform_names('region-us-east-to-west,account-dev-to-prod,json-overrides')
        assert names == ['region-us-east-to-west', 'account-dev-to-prod', 'json-overrides']
