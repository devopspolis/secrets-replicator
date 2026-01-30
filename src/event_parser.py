"""
Event parser for AWS EventBridge events from Secrets Manager.

Handles parsing CloudTrail events for secret updates triggered via EventBridge,
as well as simplified manual trigger events for on-demand replication.
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


class EventParsingError(Exception):
    """Raised when event parsing fails"""

    pass


@dataclass
class SecretEvent:
    """Represents a parsed Secrets Manager event"""

    event_name: str  # PutSecretValue, UpdateSecret, etc.
    secret_id: str  # Secret ARN or name
    secret_arn: Optional[str]  # Full ARN if available
    version_id: Optional[str]  # Secret version ID
    region: str  # AWS region
    account_id: str  # AWS account ID
    event_time: datetime  # When the event occurred
    user_identity: Optional[str]  # Who triggered the event
    source_ip: Optional[str]  # Source IP address
    request_parameters: Dict[str, Any]  # Full request parameters
    response_elements: Dict[str, Any]  # Full response elements


def parse_eventbridge_event(event: Dict[str, Any]) -> SecretEvent:
    """
    Parse EventBridge event from Secrets Manager CloudTrail integration.

    Expected event structure:
    {
        "version": "0",
        "id": "...",
        "detail-type": "AWS API Call via CloudTrail",
        "source": "aws.secretsmanager",
        "account": "123456789012",
        "time": "2025-01-01T12:00:00Z",
        "region": "us-east-1",
        "detail": {
            "eventVersion": "1.08",
            "eventName": "PutSecretValue",
            "eventTime": "2025-01-01T12:00:00Z",
            "eventSource": "secretsmanager.amazonaws.com",
            "awsRegion": "us-east-1",
            "sourceIPAddress": "1.2.3.4",
            "userIdentity": {...},
            "requestParameters": {
                "secretId": "my-secret",
                ...
            },
            "responseElements": {
                "ARN": "arn:aws:secretsmanager:...",
                "versionId": "...",
                ...
            }
        }
    }

    Args:
        event: EventBridge event dictionary

    Returns:
        SecretEvent object with parsed event data

    Raises:
        EventParsingError: If event structure is invalid or missing required fields

    Examples:
        >>> event = {
        ...     "detail-type": "AWS API Call via CloudTrail",
        ...     "source": "aws.secretsmanager",
        ...     "region": "us-east-1",
        ...     "account": "123456789012",
        ...     "time": "2025-01-01T12:00:00Z",
        ...     "detail": {
        ...         "eventName": "PutSecretValue",
        ...         "requestParameters": {"secretId": "my-secret"},
        ...         "responseElements": {"ARN": "arn:..."}
        ...     }
        ... }
        >>> parsed = parse_eventbridge_event(event)
        >>> parsed.event_name
        'PutSecretValue'
    """
    # Validate top-level structure
    if not isinstance(event, dict):
        raise EventParsingError("Event must be a dictionary")

    # Check source
    source = event.get("source", "")
    if source != "aws.secretsmanager":
        raise EventParsingError(f"Invalid event source: '{source}' (expected 'aws.secretsmanager')")

    # Check detail-type
    detail_type = event.get("detail-type", "")
    valid_detail_types = ["AWS API Call via CloudTrail", "AWS Service Event"]
    if detail_type not in valid_detail_types:
        raise EventParsingError(
            f"Invalid detail-type: '{detail_type}' (expected one of {valid_detail_types})"
        )

    # Extract top-level fields
    region = event.get("region", "")
    if not region:
        raise EventParsingError("Missing required field: 'region'")

    account_id = event.get("account", "")
    if not account_id:
        raise EventParsingError("Missing required field: 'account'")

    event_time_str = event.get("time", "")
    try:
        event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise EventParsingError(f"Invalid event time format: '{event_time_str}'")

    # Extract detail
    detail = event.get("detail", {})
    if not isinstance(detail, dict):
        raise EventParsingError("Missing or invalid 'detail' field")

    # Extract event name
    event_name = detail.get("eventName", "")
    if not event_name:
        raise EventParsingError("Missing required field: 'detail.eventName'")

    # Validate event name
    valid_event_names = [
        "PutSecretValue",
        "UpdateSecret",
        "ReplicateSecretToRegions",
        "ReplicateSecretVersion",
        "CreateSecret",
    ]
    if event_name not in valid_event_names:
        raise EventParsingError(
            f"Unsupported event name: '{event_name}' (expected one of {valid_event_names})"
        )

    # Extract request parameters
    request_parameters = detail.get("requestParameters", {})
    if not isinstance(request_parameters, dict):
        request_parameters = {}

    # Extract response elements
    response_elements = detail.get("responseElements", {})
    if not isinstance(response_elements, dict):
        response_elements = {}

    # Extract secret ID (can be in multiple places)
    # Priority: requestParameters.secretId, requestParameters.name, responseElements.ARN
    secret_id = (
        request_parameters.get("secretId")
        or request_parameters.get("name")
        or response_elements.get("ARN")
        or response_elements.get("aRN")  # CloudTrail quirk
    )

    if not secret_id:
        raise EventParsingError(
            "Could not extract secret ID from requestParameters or responseElements"
        )

    # Extract secret ARN (may be in response)
    secret_arn = (
        response_elements.get("ARN")
        or response_elements.get("aRN")  # CloudTrail quirk
        or (secret_id if secret_id.startswith("arn:") else None)
    )

    # Extract version ID
    version_id = (
        response_elements.get("versionId")
        or response_elements.get("VersionId")
        or request_parameters.get("versionId")
    )

    # Extract user identity
    user_identity_dict = detail.get("userIdentity", {})
    if isinstance(user_identity_dict, dict):
        user_identity = (
            user_identity_dict.get("principalId")
            or user_identity_dict.get("arn")
            or user_identity_dict.get("type")
        )
    else:
        user_identity = None

    # Extract source IP
    source_ip = detail.get("sourceIPAddress")

    return SecretEvent(
        event_name=event_name,
        secret_id=secret_id,
        secret_arn=secret_arn,
        version_id=version_id,
        region=region,
        account_id=account_id,
        event_time=event_time,
        user_identity=user_identity,
        source_ip=source_ip,
        request_parameters=request_parameters,
        response_elements=response_elements,
    )


def validate_event_for_replication(event: SecretEvent) -> bool:
    """
    Validate that an event should trigger replication.

    Checks:
    - Event name is a supported trigger
    - Secret ID is available
    - Region and account are present

    Args:
        event: Parsed SecretEvent

    Returns:
        True if event should trigger replication, False otherwise

    Examples:
        >>> event = SecretEvent(
        ...     event_name='PutSecretValue',
        ...     secret_id='my-secret',
        ...     secret_arn=None,
        ...     version_id='v1',
        ...     region='us-east-1',
        ...     account_id='123',
        ...     event_time=datetime.now(),
        ...     user_identity=None,
        ...     source_ip=None,
        ...     request_parameters={},
        ...     response_elements={}
        ... )
        >>> validate_event_for_replication(event)
        True
    """
    # Check event name
    replication_trigger_events = ["PutSecretValue", "UpdateSecret", "CreateSecret"]

    if event.event_name not in replication_trigger_events:
        return False

    # Check required fields
    if not event.secret_id:
        return False

    if not event.region or not event.account_id:
        return False

    return True


def extract_secret_name_from_arn(arn: str) -> Optional[str]:
    """
    Extract secret name from ARN.

    ARN format: arn:aws:secretsmanager:region:account:secret:name-suffix

    Args:
        arn: Secret ARN

    Returns:
        Secret name (without suffix), or None if invalid

    Examples:
        >>> extract_secret_name_from_arn('arn:aws:secretsmanager:us-east-1:123:secret:my-secret-AbCdEf')
        'my-secret'
        >>> extract_secret_name_from_arn('invalid')
        None
    """
    if not arn or not arn.startswith("arn:"):
        return None

    try:
        parts = arn.split(":")
        if len(parts) < 7:
            return None

        # Secret name is in parts[6] and onwards
        secret_part = ":".join(parts[6:])

        # Remove the 6-character suffix that AWS adds
        # Format: secret-name-XXXXXX where X is alphanumeric
        if "-" in secret_part:
            # Split and check if last part is 6 characters (likely suffix)
            name_parts = secret_part.rsplit("-", 1)
            if len(name_parts) == 2 and len(name_parts[1]) == 6:
                return name_parts[0]

        return secret_part

    except (IndexError, AttributeError):
        return None


# =============================================================================
# Manual Trigger Event Support
# =============================================================================


def is_manual_trigger(event: Dict[str, Any]) -> bool:
    """
    Check if an event is a manual trigger for on-demand replication.

    Manual trigger events have a simplified format for easy invocation
    via AWS CLI, SDK, or Console.

    Supported formats:
    1. Single secret:
       {"source": "manual", "secretId": "my-secret"}

    2. Multiple secrets:
       {"source": "manual", "secretIds": ["secret1", "secret2"]}

    3. With explicit region:
       {"source": "manual", "secretIds": ["secret1"], "region": "us-west-2"}

    Args:
        event: Event dictionary

    Returns:
        True if this is a manual trigger event, False otherwise

    Examples:
        >>> is_manual_trigger({"source": "manual", "secretId": "test"})
        True
        >>> is_manual_trigger({"source": "aws.secretsmanager", "detail": {}})
        False
    """
    if not isinstance(event, dict):
        return False

    return event.get("source") == "manual"


def parse_manual_event(event: Dict[str, Any], account_id: str = "") -> List[SecretEvent]:
    """
    Parse a manual trigger event into a list of SecretEvent objects.

    This allows on-demand replication of pre-existing secrets without
    having to construct complex CloudTrail event structures.

    Args:
        event: Manual trigger event dictionary
        account_id: AWS account ID (from STS if not in event)

    Returns:
        List of SecretEvent objects, one per secret

    Raises:
        EventParsingError: If event is invalid or missing required fields

    Examples:
        >>> event = {"source": "manual", "secretId": "my-secret", "region": "us-east-1"}
        >>> events = parse_manual_event(event, "123456789012")
        >>> len(events)
        1
        >>> events[0].secret_id
        'my-secret'
        >>> events[0].event_name
        'ManualSync'
    """
    if not is_manual_trigger(event):
        raise EventParsingError("Event is not a manual trigger (source != 'manual')")

    # Extract secret IDs - support both singular and plural forms
    secret_ids = []

    if "secretId" in event:
        # Single secret
        secret_id = event["secretId"]
        if isinstance(secret_id, str) and secret_id.strip():
            secret_ids.append(secret_id.strip())
        else:
            raise EventParsingError("'secretId' must be a non-empty string")

    if "secretIds" in event:
        # Multiple secrets
        ids = event["secretIds"]
        if isinstance(ids, list):
            for sid in ids:
                if isinstance(sid, str) and sid.strip():
                    secret_ids.append(sid.strip())
                else:
                    raise EventParsingError("Each item in 'secretIds' must be a non-empty string")
        else:
            raise EventParsingError("'secretIds' must be a list of strings")

    if not secret_ids:
        raise EventParsingError("Manual trigger requires 'secretId' or 'secretIds'")

    # Remove duplicates while preserving order
    seen = set()
    unique_secret_ids = []
    for sid in secret_ids:
        if sid not in seen:
            seen.add(sid)
            unique_secret_ids.append(sid)

    # Extract region - use event value, env var, or default
    region = event.get("region", "")
    if not region:
        region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", ""))
    if not region:
        raise EventParsingError(
            "Region required: provide 'region' in event or set AWS_REGION environment variable"
        )

    # Extract account ID - use event value or passed parameter
    event_account_id = event.get("accountId", "") or account_id
    # Account ID is optional for manual events - will be populated later if needed

    # Current time for event
    now = datetime.now(timezone.utc)

    # Create SecretEvent for each secret
    events = []
    for secret_id in unique_secret_ids:
        # Determine if secret_id is an ARN
        secret_arn = secret_id if secret_id.startswith("arn:") else None

        events.append(
            SecretEvent(
                event_name="ManualSync",
                secret_id=secret_id,
                secret_arn=secret_arn,
                version_id=None,
                region=region,
                account_id=event_account_id,
                event_time=now,
                user_identity="manual-trigger",
                source_ip=None,
                request_parameters={"secretId": secret_id, "manual": True},
                response_elements={},
            )
        )

    return events


def validate_manual_event_for_replication(event: SecretEvent) -> bool:
    """
    Validate that a manual trigger event should trigger replication.

    For manual events, we only check that required fields are present.
    The event_name check is relaxed since 'ManualSync' is synthetic.

    Args:
        event: Parsed SecretEvent from manual trigger

    Returns:
        True if event should trigger replication, False otherwise

    Examples:
        >>> event = SecretEvent(
        ...     event_name='ManualSync',
        ...     secret_id='my-secret',
        ...     secret_arn=None,
        ...     version_id=None,
        ...     region='us-east-1',
        ...     account_id='123',
        ...     event_time=datetime.now(),
        ...     user_identity='manual-trigger',
        ...     source_ip=None,
        ...     request_parameters={'manual': True},
        ...     response_elements={}
        ... )
        >>> validate_manual_event_for_replication(event)
        True
    """
    # Check it's actually a manual event
    if event.event_name != "ManualSync":
        return False

    # Check required fields
    if not event.secret_id:
        return False

    if not event.region:
        return False

    return True
