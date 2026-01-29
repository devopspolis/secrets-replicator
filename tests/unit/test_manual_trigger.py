"""
Unit tests for manual trigger functionality.

Tests the on-demand secret replication feature that allows replicating
pre-existing secrets via direct Lambda invocation.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from event_parser import (
    is_manual_trigger,
    parse_manual_event,
    validate_manual_event_for_replication,
    EventParsingError,
    SecretEvent
)


class TestIsManualTrigger:
    """Tests for is_manual_trigger function."""

    def test_manual_trigger_with_source_manual(self):
        """Detects manual trigger event with source='manual'."""
        event = {"source": "manual", "secretId": "test-secret"}
        assert is_manual_trigger(event) is True

    def test_not_manual_trigger_eventbridge_event(self):
        """Returns False for EventBridge events."""
        event = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "detail": {"eventName": "PutSecretValue"}
        }
        assert is_manual_trigger(event) is False

    def test_not_manual_trigger_empty_event(self):
        """Returns False for empty event."""
        assert is_manual_trigger({}) is False

    def test_not_manual_trigger_none_event(self):
        """Returns False for non-dict event."""
        assert is_manual_trigger(None) is False
        assert is_manual_trigger("string") is False
        assert is_manual_trigger([]) is False

    def test_not_manual_trigger_different_source(self):
        """Returns False for other source values."""
        event = {"source": "aws.s3", "secretId": "test"}
        assert is_manual_trigger(event) is False


class TestParseManualEvent:
    """Tests for parse_manual_event function."""

    def test_parse_single_secret_id(self):
        """Parses event with single secretId."""
        event = {
            "source": "manual",
            "secretId": "my-secret",
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert len(events) == 1
        assert events[0].secret_id == "my-secret"
        assert events[0].region == "us-east-1"
        assert events[0].account_id == "123456789012"
        assert events[0].event_name == "ManualSync"

    def test_parse_multiple_secret_ids(self):
        """Parses event with multiple secretIds."""
        event = {
            "source": "manual",
            "secretIds": ["secret-1", "secret-2", "secret-3"],
            "region": "us-west-2"
        }
        events = parse_manual_event(event, "123456789012")

        assert len(events) == 3
        assert events[0].secret_id == "secret-1"
        assert events[1].secret_id == "secret-2"
        assert events[2].secret_id == "secret-3"
        for e in events:
            assert e.region == "us-west-2"
            assert e.event_name == "ManualSync"

    def test_parse_combined_secret_id_and_secret_ids(self):
        """Parses event with both secretId and secretIds."""
        event = {
            "source": "manual",
            "secretId": "single-secret",
            "secretIds": ["list-secret-1", "list-secret-2"],
            "region": "eu-west-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert len(events) == 3
        secret_ids = [e.secret_id for e in events]
        assert "single-secret" in secret_ids
        assert "list-secret-1" in secret_ids
        assert "list-secret-2" in secret_ids

    def test_parse_removes_duplicates(self):
        """Removes duplicate secret IDs while preserving order."""
        event = {
            "source": "manual",
            "secretId": "secret-a",
            "secretIds": ["secret-a", "secret-b", "secret-a"],
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert len(events) == 2
        assert events[0].secret_id == "secret-a"
        assert events[1].secret_id == "secret-b"

    def test_parse_with_region_from_env(self):
        """Uses AWS_REGION environment variable when region not in event."""
        event = {
            "source": "manual",
            "secretId": "my-secret"
        }

        with patch.dict(os.environ, {"AWS_REGION": "ap-southeast-1"}, clear=False):
            events = parse_manual_event(event, "123456789012")

        assert len(events) == 1
        assert events[0].region == "ap-southeast-1"

    def test_parse_with_region_from_default_env(self):
        """Uses AWS_DEFAULT_REGION when AWS_REGION not set."""
        event = {
            "source": "manual",
            "secretId": "my-secret"
        }

        # Remove AWS_REGION if it exists and set AWS_DEFAULT_REGION
        env_updates = {"AWS_DEFAULT_REGION": "sa-east-1"}
        with patch.dict(os.environ, env_updates, clear=False):
            # Temporarily unset AWS_REGION
            original_region = os.environ.pop("AWS_REGION", None)
            try:
                events = parse_manual_event(event, "123456789012")
            finally:
                if original_region:
                    os.environ["AWS_REGION"] = original_region

        assert events[0].region == "sa-east-1"

    def test_parse_with_account_id_in_event(self):
        """Uses accountId from event when provided."""
        event = {
            "source": "manual",
            "secretId": "my-secret",
            "region": "us-east-1",
            "accountId": "987654321098"
        }
        events = parse_manual_event(event, "123456789012")

        assert events[0].account_id == "987654321098"

    def test_parse_secret_arn_as_id(self):
        """Handles secret ARN as secretId."""
        arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf"
        event = {
            "source": "manual",
            "secretId": arn,
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert len(events) == 1
        assert events[0].secret_id == arn
        assert events[0].secret_arn == arn

    def test_parse_strips_whitespace(self):
        """Strips whitespace from secret IDs."""
        event = {
            "source": "manual",
            "secretIds": ["  secret-1  ", "secret-2  "],
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert events[0].secret_id == "secret-1"
        assert events[1].secret_id == "secret-2"

    def test_parse_sets_manual_flag_in_request_parameters(self):
        """Sets manual=True in request_parameters."""
        event = {
            "source": "manual",
            "secretId": "my-secret",
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert events[0].request_parameters.get("manual") is True

    def test_parse_sets_user_identity_to_manual_trigger(self):
        """Sets user_identity to 'manual-trigger'."""
        event = {
            "source": "manual",
            "secretId": "my-secret",
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert events[0].user_identity == "manual-trigger"

    def test_parse_error_not_manual_event(self):
        """Raises error for non-manual events."""
        event = {"source": "aws.secretsmanager", "secretId": "test"}

        with pytest.raises(EventParsingError) as exc_info:
            parse_manual_event(event, "123456789012")

        assert "not a manual trigger" in str(exc_info.value)

    def test_parse_error_missing_secret_id(self):
        """Raises error when no secretId or secretIds provided."""
        event = {"source": "manual", "region": "us-east-1"}

        with pytest.raises(EventParsingError) as exc_info:
            parse_manual_event(event, "123456789012")

        assert "secretId" in str(exc_info.value) or "secretIds" in str(exc_info.value)

    def test_parse_error_empty_secret_id(self):
        """Raises error for empty secretId string."""
        event = {"source": "manual", "secretId": "", "region": "us-east-1"}

        with pytest.raises(EventParsingError) as exc_info:
            parse_manual_event(event, "123456789012")

        assert "non-empty string" in str(exc_info.value)

    def test_parse_error_invalid_secret_id_type(self):
        """Raises error for non-string secretId."""
        event = {"source": "manual", "secretId": 123, "region": "us-east-1"}

        with pytest.raises(EventParsingError) as exc_info:
            parse_manual_event(event, "123456789012")

        assert "non-empty string" in str(exc_info.value)

    def test_parse_error_invalid_secret_ids_type(self):
        """Raises error for non-list secretIds."""
        event = {"source": "manual", "secretIds": "not-a-list", "region": "us-east-1"}

        with pytest.raises(EventParsingError) as exc_info:
            parse_manual_event(event, "123456789012")

        assert "list" in str(exc_info.value)

    def test_parse_error_invalid_item_in_secret_ids(self):
        """Raises error for non-string items in secretIds."""
        event = {
            "source": "manual",
            "secretIds": ["valid", 123, "also-valid"],
            "region": "us-east-1"
        }

        with pytest.raises(EventParsingError) as exc_info:
            parse_manual_event(event, "123456789012")

        assert "non-empty string" in str(exc_info.value)

    def test_parse_error_missing_region(self):
        """Raises error when region not provided and not in env."""
        event = {"source": "manual", "secretId": "my-secret"}

        # Remove region environment variables
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EventParsingError) as exc_info:
                parse_manual_event(event, "123456789012")

        assert "Region required" in str(exc_info.value)


class TestValidateManualEventForReplication:
    """Tests for validate_manual_event_for_replication function."""

    def test_valid_manual_event(self):
        """Validates a properly formed manual event."""
        event = SecretEvent(
            event_name="ManualSync",
            secret_id="my-secret",
            secret_arn=None,
            version_id=None,
            region="us-east-1",
            account_id="123456789012",
            event_time=datetime.now(timezone.utc),
            user_identity="manual-trigger",
            source_ip=None,
            request_parameters={"manual": True},
            response_elements={}
        )

        assert validate_manual_event_for_replication(event) is True

    def test_invalid_event_wrong_event_name(self):
        """Rejects events with non-ManualSync event name."""
        event = SecretEvent(
            event_name="PutSecretValue",  # Not ManualSync
            secret_id="my-secret",
            secret_arn=None,
            version_id=None,
            region="us-east-1",
            account_id="123456789012",
            event_time=datetime.now(timezone.utc),
            user_identity="manual-trigger",
            source_ip=None,
            request_parameters={},
            response_elements={}
        )

        assert validate_manual_event_for_replication(event) is False

    def test_invalid_event_missing_secret_id(self):
        """Rejects events without secret_id."""
        event = SecretEvent(
            event_name="ManualSync",
            secret_id="",  # Empty
            secret_arn=None,
            version_id=None,
            region="us-east-1",
            account_id="123456789012",
            event_time=datetime.now(timezone.utc),
            user_identity="manual-trigger",
            source_ip=None,
            request_parameters={},
            response_elements={}
        )

        assert validate_manual_event_for_replication(event) is False

    def test_invalid_event_missing_region(self):
        """Rejects events without region."""
        event = SecretEvent(
            event_name="ManualSync",
            secret_id="my-secret",
            secret_arn=None,
            version_id=None,
            region="",  # Empty
            account_id="123456789012",
            event_time=datetime.now(timezone.utc),
            user_identity="manual-trigger",
            source_ip=None,
            request_parameters={},
            response_elements={}
        )

        assert validate_manual_event_for_replication(event) is False

    def test_valid_event_without_account_id(self):
        """Accepts event without account_id (optional)."""
        event = SecretEvent(
            event_name="ManualSync",
            secret_id="my-secret",
            secret_arn=None,
            version_id=None,
            region="us-east-1",
            account_id="",  # Empty but allowed
            event_time=datetime.now(timezone.utc),
            user_identity="manual-trigger",
            source_ip=None,
            request_parameters={},
            response_elements={}
        )

        assert validate_manual_event_for_replication(event) is True


class TestManualTriggerIntegration:
    """Integration tests for manual trigger with handler."""

    def test_manual_event_structure_for_handler(self):
        """Verifies manual event structure matches handler expectations."""
        event = {
            "source": "manual",
            "secretId": "app/database/credentials",
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")
        parsed = events[0]

        # Verify all required SecretEvent fields are present
        assert parsed.event_name == "ManualSync"
        assert parsed.secret_id == "app/database/credentials"
        assert parsed.region == "us-east-1"
        assert isinstance(parsed.event_time, datetime)
        assert isinstance(parsed.request_parameters, dict)
        assert isinstance(parsed.response_elements, dict)

    def test_manual_event_with_path_separators(self):
        """Handles secret names with path separators."""
        event = {
            "source": "manual",
            "secretIds": [
                "myapp/prod/database",
                "myapp/prod/api-keys",
                "shared/certificates/tls"
            ],
            "region": "us-east-1"
        }
        events = parse_manual_event(event, "123456789012")

        assert len(events) == 3
        assert events[0].secret_id == "myapp/prod/database"
        assert events[1].secret_id == "myapp/prod/api-keys"
        assert events[2].secret_id == "shared/certificates/tls"
