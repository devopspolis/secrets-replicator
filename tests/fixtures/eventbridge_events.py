"""
Sample EventBridge event fixtures for testing.

These are examples of real EventBridge events from AWS Secrets Manager
via CloudTrail integration.
"""

# Valid PutSecretValue event
PUT_SECRET_VALUE_EVENT = {
    "version": "0",
    "id": "12345678-1234-1234-1234-123456789012",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T12:00:00Z",
    "region": "us-east-1",
    "resources": [],
    "detail": {
        "eventVersion": "1.08",
        "userIdentity": {
            "type": "IAMUser",
            "principalId": "AIDAI23HXX2LMQ6EXAMPLE",
            "arn": "arn:aws:iam::123456789012:user/alice",
            "accountId": "123456789012",
            "accessKeyId": "AKIAI44QH8DHBEXAMPLE",
            "userName": "alice"
        },
        "eventTime": "2025-01-01T12:00:00Z",
        "eventSource": "secretsmanager.amazonaws.com",
        "eventName": "PutSecretValue",
        "awsRegion": "us-east-1",
        "sourceIPAddress": "192.0.2.1",
        "userAgent": "aws-cli/2.0.0",
        "requestParameters": {
            "secretId": "my-secret",
            "secretString": "HIDDEN_DUE_TO_SECURITY_REASONS"
        },
        "responseElements": {
            "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-AbCdEf",
            "name": "my-secret",
            "versionId": "a1b2c3d4-5678-90ab-cdef-EXAMPLE11111"
        },
        "requestID": "example-request-id",
        "eventID": "example-event-id",
        "readOnly": False,
        "eventType": "AwsApiCall",
        "managementEvent": True,
        "recipientAccountId": "123456789012"
    }
}

# UpdateSecret event
UPDATE_SECRET_EVENT = {
    "version": "0",
    "id": "87654321-4321-4321-4321-210987654321",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T13:00:00Z",
    "region": "us-east-1",
    "resources": [],
    "detail": {
        "eventVersion": "1.08",
        "userIdentity": {
            "type": "AssumedRole",
            "principalId": "AROAI23HXX2LMQ6EXAMPLE:session-name",
            "arn": "arn:aws:sts::123456789012:assumed-role/MyRole/session-name",
            "accountId": "123456789012",
            "accessKeyId": "ASIAXAMPLE",
            "sessionContext": {
                "sessionIssuer": {
                    "type": "Role",
                    "principalId": "AROAI23HXX2LMQ6EXAMPLE",
                    "arn": "arn:aws:iam::123456789012:role/MyRole",
                    "accountId": "123456789012",
                    "userName": "MyRole"
                }
            }
        },
        "eventTime": "2025-01-01T13:00:00Z",
        "eventSource": "secretsmanager.amazonaws.com",
        "eventName": "UpdateSecret",
        "awsRegion": "us-east-1",
        "sourceIPAddress": "192.0.2.2",
        "userAgent": "aws-sdk-python/1.0.0",
        "requestParameters": {
            "secretId": "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-db-password-XyZ123",
            "description": "Updated production database password"
        },
        "responseElements": {
            "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-db-password-XyZ123",
            "name": "prod-db-password",
            "versionId": "b2c3d4e5-6789-01bc-defg-EXAMPLE22222"
        },
        "requestID": "example-request-id-2",
        "eventID": "example-event-id-2",
        "readOnly": False,
        "eventType": "AwsApiCall",
        "managementEvent": True,
        "recipientAccountId": "123456789012"
    }
}

# CreateSecret event
CREATE_SECRET_EVENT = {
    "version": "0",
    "id": "abcdef12-3456-7890-abcd-ef1234567890",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T14:00:00Z",
    "region": "us-west-2",
    "resources": [],
    "detail": {
        "eventVersion": "1.08",
        "userIdentity": {
            "type": "IAMUser",
            "principalId": "AIDAI23HXX2LMQ6EXAMPLE",
            "arn": "arn:aws:iam::123456789012:user/bob",
            "accountId": "123456789012",
            "accessKeyId": "AKIAI44QH8DHBEXAMPLE",
            "userName": "bob"
        },
        "eventTime": "2025-01-01T14:00:00Z",
        "eventSource": "secretsmanager.amazonaws.com",
        "eventName": "CreateSecret",
        "awsRegion": "us-west-2",
        "sourceIPAddress": "192.0.2.3",
        "userAgent": "console.amazonaws.com",
        "requestParameters": {
            "name": "new-secret",
            "secretString": "HIDDEN_DUE_TO_SECURITY_REASONS"
        },
        "responseElements": {
            "ARN": "arn:aws:secretsmanager:us-west-2:123456789012:secret:new-secret-MnOpQr",
            "name": "new-secret",
            "versionId": "c3d4e5f6-7890-12cd-efgh-EXAMPLE33333"
        },
        "requestID": "example-request-id-3",
        "eventID": "example-event-id-3",
        "readOnly": False,
        "eventType": "AwsApiCall",
        "managementEvent": True,
        "recipientAccountId": "123456789012"
    }
}

# ReplicateSecretToRegions event (AWS Service Event, not CloudTrail)
REPLICATE_SECRET_EVENT = {
    "version": "0",
    "id": "fedcba98-7654-3210-fedc-ba9876543210",
    "detail-type": "AWS Service Event",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T15:00:00Z",
    "region": "us-east-1",
    "resources": [],
    "detail": {
        "eventVersion": "1.08",
        "eventTime": "2025-01-01T15:00:00Z",
        "eventSource": "secretsmanager.amazonaws.com",
        "eventName": "ReplicateSecretToRegions",
        "awsRegion": "us-east-1",
        "requestParameters": {
            "secretId": "replicated-secret",
            "addReplicaRegions": [
                {
                    "region": "us-west-2"
                }
            ]
        },
        "responseElements": {
            "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:replicated-secret-StUvWx",
            "replicationStatus": [
                {
                    "region": "us-west-2",
                    "status": "InProgress"
                }
            ]
        },
        "requestID": "example-request-id-4",
        "eventID": "example-event-id-4",
        "eventType": "AwsServiceEvent",
        "recipientAccountId": "123456789012"
    }
}

# Event with CloudTrail ARN quirk (lowercase 'aRN' instead of 'ARN')
EVENT_WITH_ARN_QUIRK = {
    "version": "0",
    "id": "quirk-1234-5678-90ab-cdef12345678",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T16:00:00Z",
    "region": "eu-west-1",
    "resources": [],
    "detail": {
        "eventVersion": "1.08",
        "userIdentity": {
            "type": "IAMUser",
            "principalId": "AIDAI23HXX2LMQ6EXAMPLE",
            "arn": "arn:aws:iam::123456789012:user/charlie",
            "accountId": "123456789012",
            "userName": "charlie"
        },
        "eventTime": "2025-01-01T16:00:00Z",
        "eventSource": "secretsmanager.amazonaws.com",
        "eventName": "PutSecretValue",
        "awsRegion": "eu-west-1",
        "sourceIPAddress": "192.0.2.4",
        "requestParameters": {
            "secretId": "quirky-secret"
        },
        "responseElements": {
            # Note: lowercase 'aRN' instead of 'ARN' (CloudTrail quirk)
            "aRN": "arn:aws:secretsmanager:eu-west-1:123456789012:secret:quirky-secret-YzAbCd",
            "name": "quirky-secret",
            "versionId": "d4e5f6g7-8901-23de-fghi-EXAMPLE44444"
        },
        "requestID": "example-request-id-5",
        "eventID": "example-event-id-5",
        "readOnly": False,
        "eventType": "AwsApiCall",
        "managementEvent": True,
        "recipientAccountId": "123456789012"
    }
}

# Invalid event - wrong source
INVALID_EVENT_WRONG_SOURCE = {
    "version": "0",
    "id": "invalid-1234",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.s3",  # Wrong source
    "account": "123456789012",
    "time": "2025-01-01T17:00:00Z",
    "region": "us-east-1",
    "detail": {
        "eventName": "PutObject"
    }
}

# Invalid event - missing detail
INVALID_EVENT_MISSING_DETAIL = {
    "version": "0",
    "id": "invalid-5678",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T18:00:00Z",
    "region": "us-east-1"
    # Missing 'detail' field
}

# Invalid event - missing secret ID
INVALID_EVENT_MISSING_SECRET_ID = {
    "version": "0",
    "id": "invalid-9012",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T19:00:00Z",
    "region": "us-east-1",
    "detail": {
        "eventName": "PutSecretValue",
        "requestParameters": {},  # Missing secretId
        "responseElements": {}    # Missing ARN
    }
}

# Invalid event - unsupported event name
INVALID_EVENT_UNSUPPORTED_NAME = {
    "version": "0",
    "id": "invalid-3456",
    "detail-type": "AWS API Call via CloudTrail",
    "source": "aws.secretsmanager",
    "account": "123456789012",
    "time": "2025-01-01T20:00:00Z",
    "region": "us-east-1",
    "detail": {
        "eventName": "DeleteSecret",  # Not a replication trigger
        "requestParameters": {
            "secretId": "to-be-deleted"
        }
    }
}

# Minimal valid event (bare minimum fields)
MINIMAL_VALID_EVENT = {
    "source": "aws.secretsmanager",
    "detail-type": "AWS API Call via CloudTrail",
    "region": "us-east-1",
    "account": "123456789012",
    "time": "2025-01-01T21:00:00Z",
    "detail": {
        "eventName": "PutSecretValue",
        "requestParameters": {
            "secretId": "minimal-secret"
        }
    }
}
