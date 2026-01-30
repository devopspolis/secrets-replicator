"""
Unit tests for utils module
"""

import pytest
from utils import (
    mask_secret,
    validate_regex,
    get_secret_metadata,
    format_arn,
    parse_arn,
    sanitize_log_message,
    truncate_string,
    is_binary_data,
    get_region_from_arn,
    get_account_from_arn,
)


class TestMaskSecret:
    """Tests for mask_secret function"""

    def test_mask_normal_secret(self):
        """Test masking a normal-length secret"""
        result = mask_secret("my_secret_password", 4)
        assert result == "my_s**********word"  # 18 chars total: 4 + 10 + 4
        assert "secret" not in result

    def test_mask_short_secret(self):
        """Test masking a short secret"""
        result = mask_secret("short", 4)
        assert result == "s***t"

    def test_mask_very_short_secret(self):
        """Test masking a very short secret"""
        result = mask_secret("ab", 4)
        assert result == "**"

    def test_mask_single_char(self):
        """Test masking a single character"""
        result = mask_secret("a", 4)
        assert result == "*"

    def test_mask_empty_string(self):
        """Test masking empty string"""
        result = mask_secret("", 4)
        assert result == ""

    def test_mask_custom_show_chars(self):
        """Test masking with custom show_chars"""
        result = mask_secret("my_secret_password", 2)
        assert result == "my**************rd"  # 18 chars total: 2 + 14 + 2

    def test_mask_preserves_length_info(self):
        """Test that masked secret gives length indication"""
        original = "a" * 50
        result = mask_secret(original, 4)
        # Result should be roughly same length (4 + asterisks + 4)
        assert len(result) == len(original)


class TestValidateRegex:
    """Tests for validate_regex function"""

    def test_valid_simple_regex(self):
        """Test valid simple regex"""
        assert validate_regex(r"\d+") is True
        assert validate_regex(r"[a-z]+") is True
        assert validate_regex(r"test.*pattern") is True

    def test_invalid_regex(self):
        """Test invalid regex syntax"""
        assert validate_regex(r"[invalid(") is False
        assert validate_regex(r"(?P<incomplete") is False

    def test_too_long_regex(self):
        """Test regex that exceeds max length"""
        long_pattern = "a" * 2000
        assert validate_regex(long_pattern, max_length=1000) is False

    def test_dangerous_nested_quantifiers(self):
        """Test that dangerous nested quantifiers are rejected"""
        assert validate_regex(r"(a+)+") is False
        assert validate_regex(r"(a*)*") is False
        assert validate_regex(r"(a+){2,5}") is False

    def test_safe_quantifiers(self):
        """Test that safe quantifiers are accepted"""
        assert validate_regex(r"a+") is True
        assert validate_regex(r"a*") is True
        assert validate_regex(r"a{2,5}") is True


class TestGetSecretMetadata:
    """Tests for get_secret_metadata function"""

    def test_extract_metadata_string_secret(self):
        """Test extracting metadata from string secret response"""
        response = {
            "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:test",
            "Name": "test-secret",
            "VersionId": "v1",
            "SecretString": "sensitive_value",
            "CreatedDate": "2025-01-01",
        }
        metadata = get_secret_metadata(response)

        assert "ARN" in metadata
        assert "Name" in metadata
        assert "VersionId" in metadata
        assert "SecretString" not in metadata  # Should be excluded
        assert metadata["SecretType"] == "string"
        assert metadata["SecretSize"] == len("sensitive_value")

    def test_extract_metadata_binary_secret(self):
        """Test extracting metadata from binary secret response"""
        binary_data = b"\x00\x01\x02\x03"
        response = {
            "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:test",
            "Name": "test-secret",
            "VersionId": "v1",
            "SecretBinary": binary_data,
        }
        metadata = get_secret_metadata(response)

        assert "SecretBinary" not in metadata  # Should be excluded
        assert metadata["SecretType"] == "binary"
        assert metadata["SecretSize"] == len(binary_data)

    def test_metadata_includes_version_stages(self):
        """Test that version stages are included"""
        response = {
            "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:test",
            "Name": "test-secret",
            "VersionId": "v1",
            "VersionStages": ["AWSCURRENT"],
            "SecretString": "value",
        }
        metadata = get_secret_metadata(response)

        assert "VersionStages" in metadata
        assert metadata["VersionStages"] == ["AWSCURRENT"]


class TestFormatArn:
    """Tests for format_arn function"""

    def test_format_secrets_manager_arn(self):
        """Test formatting Secrets Manager ARN"""
        arn = format_arn("secretsmanager", "us-east-1", "123456789012", "secret", "my-secret")
        assert arn == "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret"

    def test_format_s3_arn(self):
        """Test formatting S3 ARN"""
        arn = format_arn("s3", "", "", "bucket", "my-bucket")
        assert arn == "arn:aws:s3:::bucket:my-bucket"  # S3 has empty region/account


class TestParseArn:
    """Tests for parse_arn function"""

    def test_parse_secrets_manager_arn(self):
        """Test parsing Secrets Manager ARN"""
        arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret"
        components = parse_arn(arn)

        assert components is not None
        assert components["partition"] == "aws"
        assert components["service"] == "secretsmanager"
        assert components["region"] == "us-east-1"
        assert components["account_id"] == "123456789012"
        assert components["resource_type"] == "secret"
        assert components["resource_id"] == "my-secret"

    def test_parse_arn_with_slash(self):
        """Test parsing ARN with slash separator"""
        arn = "arn:aws:s3:::bucket/key"
        components = parse_arn(arn)

        assert components is not None
        assert components["service"] == "s3"
        assert components["resource_type"] == "bucket"
        assert components["resource_id"] == "key"

    def test_parse_arn_with_suffix(self):
        """Test parsing ARN with version suffix"""
        arn = "arn:aws:secretsmanager:us-east-1:123:secret:my-secret-AbCdEf"
        components = parse_arn(arn)

        assert components is not None
        assert components["resource_id"] == "my-secret-AbCdEf"

    def test_parse_invalid_arn(self):
        """Test parsing invalid ARN"""
        result = parse_arn("not-an-arn")
        assert result is None

        result = parse_arn("arn:aws")
        assert result is None


class TestSanitizeLogMessage:
    """Tests for sanitize_log_message function"""

    def test_sanitize_password(self):
        """Test sanitizing password in log message"""
        message = "Connecting with password=secret123 to server"
        result = sanitize_log_message(message)
        assert "secret123" not in result
        assert "password=***" in result

    def test_sanitize_api_key(self):
        """Test sanitizing API key in log message"""
        message = "Using api_key=abcd1234 for request"
        result = sanitize_log_message(message)
        assert "abcd1234" not in result
        assert "api_key=***" in result

    def test_sanitize_base64(self):
        """Test sanitizing long base64 strings"""
        long_base64 = "A" * 60 + "=="
        message = f"Token: {long_base64}"
        result = sanitize_log_message(message)
        assert long_base64 not in result
        assert "[BASE64_REDACTED]" in result

    def test_sanitize_jwt(self):
        """Test sanitizing JWT tokens"""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        message = f"JWT: {jwt}"
        result = sanitize_log_message(message)
        assert jwt not in result
        assert "[JWT_REDACTED]" in result

    def test_sanitize_preserves_safe_content(self):
        """Test that safe content is preserved"""
        message = "Processing request for user john_doe in region us-east-1"
        result = sanitize_log_message(message)
        assert result == message

    def test_sanitize_custom_patterns(self):
        """Test sanitizing with custom patterns"""
        message = "custom_field=sensitive_data other text"
        patterns = [(r"custom_field=[^\s]+", r"custom_field=***")]
        result = sanitize_log_message(message, patterns)
        assert "sensitive_data" not in result
        assert "custom_field=***" in result


class TestTruncateString:
    """Tests for truncate_string function"""

    def test_truncate_long_string(self):
        """Test truncating a long string"""
        text = "a" * 200
        result = truncate_string(text, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_truncate_short_string(self):
        """Test that short strings are not truncated"""
        text = "short"
        result = truncate_string(text, 50)
        assert result == text

    def test_truncate_exact_length(self):
        """Test string at exact max length"""
        text = "a" * 50
        result = truncate_string(text, 50)
        assert result == text

    def test_truncate_custom_suffix(self):
        """Test truncating with custom suffix"""
        text = "a" * 200
        result = truncate_string(text, 50, suffix="[...]")
        assert len(result) == 50
        assert result.endswith("[...]")


class TestIsBinaryData:
    """Tests for is_binary_data function"""

    def test_text_data(self):
        """Test that text data is recognized"""
        assert is_binary_data(b"Hello World") is False
        assert is_binary_data(b'{"key": "value"}') is False

    def test_binary_with_null_bytes(self):
        """Test that null bytes indicate binary"""
        assert is_binary_data(b"\x00\x01\x02\x03") is True
        assert is_binary_data(b"text\x00data") is True

    def test_binary_with_non_printable(self):
        """Test that high percentage of non-printable indicates binary"""
        non_printable = bytes(range(0, 255))
        assert is_binary_data(non_printable) is True

    def test_empty_data(self):
        """Test empty data"""
        assert is_binary_data(b"") is False

    def test_text_with_newlines(self):
        """Test text with newlines and tabs"""
        text = b"line1\nline2\tcolumn"
        assert is_binary_data(text) is False


class TestGetRegionFromArn:
    """Tests for get_region_from_arn function"""

    def test_extract_region(self):
        """Test extracting region from ARN"""
        arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        assert get_region_from_arn(arn) == "us-east-1"

    def test_extract_region_different_regions(self):
        """Test extracting various regions"""
        arns = [
            ("arn:aws:secretsmanager:us-west-2:123:secret:test", "us-west-2"),
            ("arn:aws:secretsmanager:eu-west-1:123:secret:test", "eu-west-1"),
            ("arn:aws:secretsmanager:ap-northeast-1:123:secret:test", "ap-northeast-1"),
        ]
        for arn, expected_region in arns:
            assert get_region_from_arn(arn) == expected_region

    def test_invalid_arn(self):
        """Test with invalid ARN"""
        assert get_region_from_arn("invalid-arn") is None


class TestGetAccountFromArn:
    """Tests for get_account_from_arn function"""

    def test_extract_account_id(self):
        """Test extracting account ID from ARN"""
        arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        assert get_account_from_arn(arn) == "123456789012"

    def test_different_account_ids(self):
        """Test extracting various account IDs"""
        arns = [
            ("arn:aws:secretsmanager:us-east-1:111111111111:secret:test", "111111111111"),
            ("arn:aws:secretsmanager:us-east-1:999999999999:secret:test", "999999999999"),
        ]
        for arn, expected_account in arns:
            assert get_account_from_arn(arn) == expected_account

    def test_invalid_arn(self):
        """Test with invalid ARN"""
        assert get_account_from_arn("invalid-arn") is None


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_mask_unicode_secret(self):
        """Test masking secret with Unicode characters"""
        result = mask_secret("pássw🔒rd", 2)
        assert result.startswith("pá")
        assert result.endswith("rd")

    def test_parse_arn_with_complex_resource_id(self):
        """Test parsing ARN with complex resource ID"""
        arn = "arn:aws:secretsmanager:us-east-1:123:secret:my/secret/path-AbCdEf"
        components = parse_arn(arn)
        assert components is not None
        assert "my/secret/path-AbCdEf" in components["resource_id"]

    def test_sanitize_multiple_secrets_in_message(self):
        """Test sanitizing message with multiple secrets"""
        message = "password=pass1 api_key=key1 secret=secret1"
        result = sanitize_log_message(message)
        assert "pass1" not in result
        assert "key1" not in result
        assert "secret1" not in result
        assert result.count("***") >= 3
