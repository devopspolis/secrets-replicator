"""
Unit tests for event_parser module
"""

import pytest
from datetime import datetime
from event_parser import (
    SecretEvent,
    parse_eventbridge_event,
    validate_event_for_replication,
    extract_secret_name_from_arn,
    EventParsingError
)
from tests.fixtures.eventbridge_events import (
    PUT_SECRET_VALUE_EVENT,
    UPDATE_SECRET_EVENT,
    CREATE_SECRET_EVENT,
    REPLICATE_SECRET_EVENT,
    EVENT_WITH_ARN_QUIRK,
    INVALID_EVENT_WRONG_SOURCE,
    INVALID_EVENT_MISSING_DETAIL,
    INVALID_EVENT_MISSING_SECRET_ID,
    INVALID_EVENT_UNSUPPORTED_NAME,
    MINIMAL_VALID_EVENT
)


class TestParseEventBridgeEvent:
    """Tests for parse_eventbridge_event function"""

    def test_parse_put_secret_value_event(self):
        """Test parsing PutSecretValue event"""
        event = parse_eventbridge_event(PUT_SECRET_VALUE_EVENT)

        assert isinstance(event, SecretEvent)
        assert event.event_name == 'PutSecretValue'
        assert event.secret_id == 'my-secret'
        assert event.secret_arn == 'arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf'
        assert event.version_id == 'a1b2c3d4-5678-90ab-cdef-EXAMPLE11111'
        assert event.region == 'us-east-1'
        assert event.account_id == '123456789012'
        assert isinstance(event.event_time, datetime)
        assert event.user_identity == 'AIDAI23HXX2LMQ6EXAMPLE'
        assert event.source_ip == '192.0.2.1'

    def test_parse_update_secret_event(self):
        """Test parsing UpdateSecret event"""
        event = parse_eventbridge_event(UPDATE_SECRET_EVENT)

        assert event.event_name == 'UpdateSecret'
        assert event.secret_id == 'arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-db-password-XyZ123'
        assert event.secret_arn == 'arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-db-password-XyZ123'
        assert event.region == 'us-east-1'
        assert 'AROAI23HXX2LMQ6EXAMPLE' in event.user_identity

    def test_parse_create_secret_event(self):
        """Test parsing CreateSecret event"""
        event = parse_eventbridge_event(CREATE_SECRET_EVENT)

        assert event.event_name == 'CreateSecret'
        assert event.secret_id == 'new-secret'
        assert event.secret_arn == 'arn:aws:secretsmanager:us-west-2:123456789012:secret:new-secret-MnOpQr'
        assert event.region == 'us-west-2'
        assert event.account_id == '123456789012'

    def test_parse_replicate_secret_event(self):
        """Test parsing ReplicateSecretToRegions event"""
        event = parse_eventbridge_event(REPLICATE_SECRET_EVENT)

        assert event.event_name == 'ReplicateSecretToRegions'
        assert event.secret_id == 'replicated-secret'
        assert event.region == 'us-east-1'

    def test_parse_event_with_arn_quirk(self):
        """Test parsing event with CloudTrail ARN quirk (lowercase 'aRN')"""
        event = parse_eventbridge_event(EVENT_WITH_ARN_QUIRK)

        assert event.event_name == 'PutSecretValue'
        assert event.secret_id == 'quirky-secret'
        # Should still parse ARN even with lowercase 'aRN'
        assert event.secret_arn == 'arn:aws:secretsmanager:eu-west-1:123456789012:secret:quirky-secret-YzAbCd'
        assert event.region == 'eu-west-1'

    def test_parse_minimal_valid_event(self):
        """Test parsing event with minimal fields"""
        event = parse_eventbridge_event(MINIMAL_VALID_EVENT)

        assert event.event_name == 'PutSecretValue'
        assert event.secret_id == 'minimal-secret'
        assert event.region == 'us-east-1'
        assert event.account_id == '123456789012'
        # Optional fields may be None
        assert event.source_ip is None
        assert event.user_identity is None

    def test_parse_event_with_service_event_type(self):
        """Test parsing AWS Service Event (not CloudTrail)"""
        event = parse_eventbridge_event(REPLICATE_SECRET_EVENT)

        # Should parse successfully even with different detail-type
        assert event.event_name == 'ReplicateSecretToRegions'

    def test_parse_invalid_event_wrong_source(self):
        """Test that wrong source raises error"""
        with pytest.raises(EventParsingError, match="Invalid event source"):
            parse_eventbridge_event(INVALID_EVENT_WRONG_SOURCE)

    def test_parse_invalid_event_missing_detail(self):
        """Test that missing detail raises error"""
        with pytest.raises(EventParsingError):  # Will fail at missing eventName
            parse_eventbridge_event(INVALID_EVENT_MISSING_DETAIL)

    def test_parse_invalid_event_missing_secret_id(self):
        """Test that missing secret ID raises error"""
        with pytest.raises(EventParsingError, match="Could not extract secret ID"):
            parse_eventbridge_event(INVALID_EVENT_MISSING_SECRET_ID)

    def test_parse_invalid_event_unsupported_name(self):
        """Test that unsupported event name raises error"""
        with pytest.raises(EventParsingError, match="Unsupported event name"):
            parse_eventbridge_event(INVALID_EVENT_UNSUPPORTED_NAME)

    def test_parse_invalid_event_missing_region(self):
        """Test that missing region raises error"""
        invalid_event = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "account": "123",
            "time": "2025-01-01T12:00:00Z",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {"secretId": "test"}
            }
        }
        with pytest.raises(EventParsingError, match="Missing required field: 'region'"):
            parse_eventbridge_event(invalid_event)

    def test_parse_invalid_event_missing_account(self):
        """Test that missing account raises error"""
        invalid_event = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "region": "us-east-1",
            "time": "2025-01-01T12:00:00Z",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {"secretId": "test"}
            }
        }
        with pytest.raises(EventParsingError, match="Missing required field: 'account'"):
            parse_eventbridge_event(invalid_event)

    def test_parse_invalid_event_time(self):
        """Test that invalid event time raises error"""
        invalid_event = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "region": "us-east-1",
            "account": "123",
            "time": "invalid-time-format",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {"secretId": "test"}
            }
        }
        with pytest.raises(EventParsingError, match="Invalid event time format"):
            parse_eventbridge_event(invalid_event)

    def test_parse_event_not_dict(self):
        """Test that non-dict event raises error"""
        with pytest.raises(EventParsingError, match="Event must be a dictionary"):
            parse_eventbridge_event("not a dict")

    def test_parse_event_invalid_detail_type(self):
        """Test that invalid detail-type raises error"""
        invalid_event = {
            "source": "aws.secretsmanager",
            "detail-type": "Some Other Event Type",
            "region": "us-east-1",
            "account": "123",
            "time": "2025-01-01T12:00:00Z",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {"secretId": "test"}
            }
        }
        with pytest.raises(EventParsingError, match="Invalid detail-type"):
            parse_eventbridge_event(invalid_event)

    def test_parse_event_extracts_version_id_from_request(self):
        """Test version ID extraction from requestParameters"""
        event_dict = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "region": "us-east-1",
            "account": "123",
            "time": "2025-01-01T12:00:00Z",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {
                    "secretId": "test",
                    "versionId": "version-from-request"
                },
                "responseElements": {}
            }
        }
        event = parse_eventbridge_event(event_dict)
        assert event.version_id == "version-from-request"


class TestValidateEventForReplication:
    """Tests for validate_event_for_replication function"""

    def test_validate_put_secret_value_event(self):
        """Test PutSecretValue event is valid for replication"""
        event = parse_eventbridge_event(PUT_SECRET_VALUE_EVENT)
        assert validate_event_for_replication(event) is True

    def test_validate_update_secret_event(self):
        """Test UpdateSecret event is valid for replication"""
        event = parse_eventbridge_event(UPDATE_SECRET_EVENT)
        assert validate_event_for_replication(event) is True

    def test_validate_create_secret_event(self):
        """Test CreateSecret event is valid for replication"""
        event = parse_eventbridge_event(CREATE_SECRET_EVENT)
        assert validate_event_for_replication(event) is True

    def test_validate_replicate_event_not_valid(self):
        """Test ReplicateSecretToRegions event is NOT valid for replication"""
        event = parse_eventbridge_event(REPLICATE_SECRET_EVENT)
        # Replication events should not trigger another replication (avoid loops)
        assert validate_event_for_replication(event) is False

    def test_validate_event_missing_secret_id(self):
        """Test event with missing secret ID is not valid"""
        event = SecretEvent(
            event_name='PutSecretValue',
            secret_id='',  # Empty secret ID
            secret_arn=None,
            version_id=None,
            region='us-east-1',
            account_id='123',
            event_time=datetime.now(),
            user_identity=None,
            source_ip=None,
            request_parameters={},
            response_elements={}
        )
        assert validate_event_for_replication(event) is False

    def test_validate_event_missing_region(self):
        """Test event with missing region is not valid"""
        event = SecretEvent(
            event_name='PutSecretValue',
            secret_id='test',
            secret_arn=None,
            version_id=None,
            region='',  # Empty region
            account_id='123',
            event_time=datetime.now(),
            user_identity=None,
            source_ip=None,
            request_parameters={},
            response_elements={}
        )
        assert validate_event_for_replication(event) is False

    def test_validate_event_missing_account(self):
        """Test event with missing account is not valid"""
        event = SecretEvent(
            event_name='PutSecretValue',
            secret_id='test',
            secret_arn=None,
            version_id=None,
            region='us-east-1',
            account_id='',  # Empty account
            event_time=datetime.now(),
            user_identity=None,
            source_ip=None,
            request_parameters={},
            response_elements={}
        )
        assert validate_event_for_replication(event) is False


class TestExtractSecretNameFromArn:
    """Tests for extract_secret_name_from_arn function"""

    def test_extract_name_from_standard_arn(self):
        """Test extracting name from standard ARN with suffix"""
        arn = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf'
        name = extract_secret_name_from_arn(arn)
        assert name == 'my-secret'

    def test_extract_name_from_arn_with_dashes(self):
        """Test extracting name from ARN with multiple dashes"""
        arn = 'arn:aws:secretsmanager:us-east-1:123:secret:prod-db-password-XyZ123'
        name = extract_secret_name_from_arn(arn)
        assert name == 'prod-db-password'

    def test_extract_name_from_arn_without_suffix(self):
        """Test extracting name from ARN without 6-char suffix"""
        arn = 'arn:aws:secretsmanager:us-east-1:123:secret:simplesecret'
        name = extract_secret_name_from_arn(arn)
        # If no 6-char suffix, returns full name
        assert name == 'simplesecret'

    def test_extract_name_from_arn_with_path(self):
        """Test extracting name from ARN with path-like structure"""
        arn = 'arn:aws:secretsmanager:us-east-1:123:secret:path/to/secret-Abc123'
        name = extract_secret_name_from_arn(arn)
        assert name == 'path/to/secret'

    def test_extract_name_from_invalid_arn(self):
        """Test extracting name from invalid ARN"""
        assert extract_secret_name_from_arn('invalid') is None
        assert extract_secret_name_from_arn('') is None
        assert extract_secret_name_from_arn(None) is None

    def test_extract_name_from_short_arn(self):
        """Test extracting name from ARN with too few parts"""
        arn = 'arn:aws:secretsmanager:us-east-1:123'
        name = extract_secret_name_from_arn(arn)
        assert name is None


class TestSecretEvent:
    """Tests for SecretEvent dataclass"""

    def test_secret_event_creation(self):
        """Test creating a SecretEvent"""
        event = SecretEvent(
            event_name='PutSecretValue',
            secret_id='my-secret',
            secret_arn='arn:aws:secretsmanager:us-east-1:123:secret:my-secret-AbCdEf',
            version_id='v1',
            region='us-east-1',
            account_id='123456789012',
            event_time=datetime.now(),
            user_identity='user123',
            source_ip='192.0.2.1',
            request_parameters={'test': 'value'},
            response_elements={'result': 'ok'}
        )

        assert event.event_name == 'PutSecretValue'
        assert event.secret_id == 'my-secret'
        assert event.secret_arn.startswith('arn:')
        assert event.region == 'us-east-1'

    def test_secret_event_with_optional_none(self):
        """Test SecretEvent with optional fields as None"""
        event = SecretEvent(
            event_name='UpdateSecret',
            secret_id='test',
            secret_arn=None,
            version_id=None,
            region='us-west-2',
            account_id='999',
            event_time=datetime.now(),
            user_identity=None,
            source_ip=None,
            request_parameters={},
            response_elements={}
        )

        assert event.secret_arn is None
        assert event.version_id is None
        assert event.user_identity is None


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_parse_event_with_empty_response_elements(self):
        """Test event with empty responseElements"""
        event_dict = PUT_SECRET_VALUE_EVENT.copy()
        event_dict['detail']['responseElements'] = {}
        # Should still parse if requestParameters has secretId
        event = parse_eventbridge_event(event_dict)
        assert event.secret_id == 'my-secret'

    def test_parse_event_with_empty_request_parameters(self):
        """Test event with empty requestParameters but ARN in response"""
        # Create event dict with empty requestParameters but valid responseElements
        event_dict = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "region": "us-east-1",
            "account": "123456789012",
            "time": "2025-01-01T12:00:00Z",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {},  # Empty
                "responseElements": {
                    "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf",
                    "versionId": "v1"
                }
            }
        }
        # Should parse ARN from responseElements (secret_id will be the ARN)
        event = parse_eventbridge_event(event_dict)
        # secret_id should be extracted from responseElements.ARN
        assert event.secret_id == 'arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf'
        assert event.secret_arn == 'arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf'

    def test_parse_event_with_arn_as_secret_id(self):
        """Test event where secretId is already an ARN"""
        event_dict = {
            "source": "aws.secretsmanager",
            "detail-type": "AWS API Call via CloudTrail",
            "region": "us-east-1",
            "account": "123",
            "time": "2025-01-01T12:00:00Z",
            "detail": {
                "eventName": "PutSecretValue",
                "requestParameters": {
                    "secretId": "arn:aws:secretsmanager:us-east-1:123:secret:test-AbCdEf"
                }
            }
        }
        event = parse_eventbridge_event(event_dict)
        assert event.secret_id.startswith('arn:')
        assert event.secret_arn.startswith('arn:')

    def test_extract_name_handles_colons_in_secret_name(self):
        """Test extracting name when secret name contains colons"""
        arn = 'arn:aws:secretsmanager:us-east-1:123:secret:path:to:secret-AbCdEf'
        name = extract_secret_name_from_arn(arn)
        assert name == 'path:to:secret'
