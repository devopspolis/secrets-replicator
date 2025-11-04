# Architecture Documentation - Secrets Replicator

## System Overview

The Secrets Replicator is an event-driven AWS Lambda function that replicates AWS Secrets Manager secrets across regions and accounts while applying configurable transformations to the secret values.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Source Account/Region                     │
│                                                                   │
│  ┌──────────────┐         ┌─────────────────┐                   │
│  │   Secrets    │ update  │   CloudTrail    │                   │
│  │   Manager    │────────▶│                 │                   │
│  │  (Source)    │         └────────┬────────┘                   │
│  └──────────────┘                  │                            │
│                                     │ event                      │
│                          ┌──────────▼────────┐                  │
│                          │   EventBridge     │                  │
│                          │      Rule         │                  │
│                          └──────────┬────────┘                  │
│                                     │ trigger                    │
│                          ┌──────────▼────────┐                  │
│                          │  Lambda Function  │                  │
│                          │  (Replicator)     │                  │
│                          └──────────┬────────┘                  │
│                                     │                            │
│                    ┌────────────────┼────────────────┐          │
│                    │                │                │          │
│         ┌──────────▼────┐   ┌──────▼──────────┐  ┌─▼─────┐    │
│         │   Secrets     │   │    Secrets      │  │  STS  │    │
│         │   Manager     │   │    Manager      │  │Assume │    │
│         │   (Source)    │   │(Transformations)│  │ Role  │    │
│         └───────────────┘   └─────────────────┘  └───┬───┘    │
│                                                     │          │
└─────────────────────────────────────────────────────┼──────────┘
                                                      │
                                                      │ assume
                                                      │
┌─────────────────────────────────────────────────────▼──────────┐
│                   Destination Account/Region                    │
│                                                                  │
│                          ┌──────────────┐                       │
│                          │   Secrets    │                       │
│                          │   Manager    │                       │
│                          │ (Destination)│                       │
│                          └──────────────┘                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. EventBridge Rule

**Purpose**: Detects secret updates and triggers the Lambda function

**Event Pattern**:
```json
{
  "source": ["aws.secretsmanager"],
  "detail-type": [
    "AWS API Call via CloudTrail",
    "AWS Service Event"
  ],
  "detail": {
    "eventName": [
      "PutSecretValue",
      "UpdateSecret",
      "ReplicateSecretToRegions",
      "ReplicateSecretVersion"
    ]
  }
}
```

**Optional Filtering**:
- Filter by specific secret ARN patterns
- Filter by tags
- Filter by source IP/identity

**Considerations**:
- CloudTrail must be enabled for Secrets Manager events
- EventBridge rule may need to handle both `arn` and `aRN` fields (CloudTrail quirk)
- Rule should prevent triggering on destination writes to avoid loops

### 2. Lambda Function

**Runtime**: Python 3.12 (recommended)

**Memory**: 256 MB (adjustable based on secret size and transformation complexity)

**Timeout**: 60 seconds (adjustable for large secrets or slow transformations)

**Environment Variables**:
```
DEST_REGION                    # Required: Destination region (or comma-separated list)
DEST_SECRET_NAME               # Optional: Override destination secret name
DEST_ACCOUNT_ROLE_ARN          # Optional: Role ARN to assume for cross-account
TRANSFORMATION_SECRET_PREFIX   # Optional: Prefix for transformation secrets (default: "secrets-replicator/transformations/")
TRANSFORM_MODE                 # Optional: "auto", "sed" or "json" (default: "auto")
LOG_LEVEL                      # Optional: DEBUG, INFO, WARN, ERROR (default: INFO)
DLQ_ARN                        # Optional: DLQ for failed events
ENABLE_METRICS                 # Optional: Enable CloudWatch custom metrics (default: true)
```

#### Handler Flow

```python
def lambda_handler(event, context):
    1. Parse EventBridge event
       - Extract secret ARN/name from detail.requestParameters or detail.responseElements
       - Validate event structure

    2. Load configuration
       - Determine destination(s) from environment or config
       - Load transformation rules (sedfile)

    3. Retrieve source secret
       - Call secretsmanager:GetSecretValue
       - Handle SecretString vs SecretBinary

    4. Apply transformations
       - Execute sed-style regex replacements OR
       - Apply JSON field mappings
       - Validate transformed output

    5. Write to destination(s)
       - For each destination:
         a. Assume role if cross-account (STS)
         b. Create Secrets Manager client for destination region
         c. Check if secret exists
         d. CreateSecret (if new) or PutSecretValue (if exists)
         e. Optionally verify idempotency

    6. Emit metrics and logs
       - CloudWatch custom metrics (success/failure counts)
       - Structured logs (metadata only, no plaintext)

    7. Error handling
       - Catch and classify errors (transient vs permanent)
       - Retry transient errors with exponential backoff
       - Send permanent failures to DLQ
       - Return appropriate status
```

### 3. Transformation Engine

**Module**: `transformer.py`

#### Sed-Style Transformation

**Input Format** (sedfile):
```
s/us-east-1/us-west-2/g
s/prod-db-1.example.com/prod-db-2.example.com/g
s/tcp:5432/tcp:5433/
```

**Implementation**:
```python
def apply_sed_transforms(secret_value: str, rules: List[SedRule]) -> str:
    """
    Apply sed-style regex replacements to secret value

    Args:
        secret_value: Original secret value (string)
        rules: List of (pattern, replacement, flags) tuples

    Returns:
        Transformed secret value

    Raises:
        TransformationError: If regex is invalid or times out
    """
    transformed = secret_value
    for pattern, replacement, flags in rules:
        try:
            # Compile with timeout protection
            regex = re.compile(pattern, flags)
            transformed = regex.sub(replacement, transformed)
        except re.error as e:
            raise TransformationError(f"Invalid regex: {pattern}") from e

    return transformed
```

**Security Considerations**:
- Validate regex patterns to prevent ReDoS (Regular Expression Denial of Service)
- Set timeout limits for regex execution
- Limit maximum number of replacements per rule

#### JSON Field Transformation

**Input Format** (JSON mapping):
```json
{
  "transformations": [
    {
      "path": "$.database.host",
      "find": "db1.us-east-1.example.com",
      "replace": "db1.us-west-2.example.com"
    },
    {
      "path": "$.database.region",
      "find": "us-east-1",
      "replace": "us-west-2"
    }
  ]
}
```

**Implementation**:
```python
def apply_json_transforms(secret_value: str, mappings: List[JsonMapping]) -> str:
    """
    Apply JSON path-based transformations

    Args:
        secret_value: Original secret value (JSON string)
        mappings: List of JSON path transformations

    Returns:
        Transformed secret value (JSON string)

    Raises:
        TransformationError: If JSON is invalid or path not found
    """
    try:
        secret_obj = json.loads(secret_value)
    except json.JSONDecodeError as e:
        raise TransformationError("Invalid JSON in secret") from e

    for mapping in mappings:
        # Use JSONPath library to locate and update fields
        jsonpath_expr = parse(mapping['path'])
        jsonpath_expr.find(secret_obj)
        jsonpath_expr.update(secret_obj, mapping['replace'])

    return json.dumps(secret_obj, separators=(',', ':'))
```

### 4. AWS Clients Module

**Module**: `aws_clients.py`

**Purpose**: Manage boto3 clients with proper credential handling

```python
class SecretsManagerClient:
    """Wrapper for Secrets Manager operations"""

    def __init__(self, region: str, role_arn: Optional[str] = None):
        """
        Initialize Secrets Manager client

        Args:
            region: AWS region
            role_arn: Optional role ARN to assume for cross-account access
        """
        if role_arn:
            credentials = self._assume_role(role_arn)
            self.client = boto3.client(
                'secretsmanager',
                region_name=region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            self.client = boto3.client('secretsmanager', region_name=region)

    def _assume_role(self, role_arn: str) -> Dict:
        """Assume IAM role and return temporary credentials"""
        sts = boto3.client('sts')
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SecretReplicatorSession',
            DurationSeconds=3600  # 1 hour
        )
        return response['Credentials']

    def get_secret(self, secret_id: str) -> Dict:
        """Retrieve secret value"""
        return self.client.get_secret_value(SecretId=secret_id)

    def put_secret(self, secret_id: str, value: str, is_binary: bool = False) -> Dict:
        """Create or update secret value"""
        try:
            # Try to update existing secret
            if is_binary:
                return self.client.put_secret_value(
                    SecretId=secret_id,
                    SecretBinary=value
                )
            else:
                return self.client.put_secret_value(
                    SecretId=secret_id,
                    SecretString=value
                )
        except self.client.exceptions.ResourceNotFoundException:
            # Secret doesn't exist, create it
            if is_binary:
                return self.client.create_secret(
                    Name=secret_id,
                    SecretBinary=value
                )
            else:
                return self.client.create_secret(
                    Name=secret_id,
                    SecretString=value
                )
```

### 5. Transformation Secrets Storage

**Location**: AWS Secrets Manager with prefix `secrets-replicator/transformations/`

**Advantages**:
- Update transformation rules without redeploying Lambda
- Automatic version control (AWSCURRENT, AWSPREVIOUS)
- Encryption at rest with KMS by default
- IAM-based access control
- CloudTrail audit logging
- No external dependencies (no S3 required)
- Easy rollback to previous versions

**Setup**:
```bash
# Create transformation secret with sed script
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --secret-string 's/us-east-1/us-west-2/g'

# Tag source secret to use this transformation
aws secretsmanager tag-resource \
  --secret-id my-source-secret \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap
```

**Lambda IAM Permission**:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:DescribeSecret"
  ],
  "Resource": "arn:aws:secretsmanager:*:*:secret:secrets-replicator/transformations/*"
}
```

**Key Features**:
- **Tag-based routing**: Source secrets specify which transformation to use via tags
- **Automatic exclusion**: Transformation secrets are never replicated (both source and destination filtering)
- **Version rollback**: Use `AWSPREVIOUS` version stage to rollback transformations
- **Multi-environment**: Different transformation secrets for dev→staging, staging→prod, etc.

## IAM Permissions

### Lambda Execution Role (Source Account)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSourceSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:123456789012:secret:source-*"
      ]
    },
    {
      "Sid": "DecryptSourceSecrets",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": [
        "arn:aws:kms:us-east-1:123456789012:key/source-key-id"
      ]
    },
    {
      "Sid": "ReadTransformationSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:123456789012:secret:secrets-replicator/transformations/*"
      ]
    },
    {
      "Sid": "AssumeDestinationRole",
      "Effect": "Allow",
      "Action": ["sts:AssumeRole"],
      "Resource": [
        "arn:aws:iam::987654321098:role/SecretReplicatorDestinationRole"
      ]
    },
    {
      "Sid": "WriteLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:*:123456789012:log-group:/aws/lambda/secret-replicator:*"
      ]
    },
    {
      "Sid": "PublishMetrics",
      "Effect": "Allow",
      "Action": ["cloudwatch:PutMetricData"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "SecretReplicator"
        }
      }
    }
  ]
}
```

### Destination Account Role (Cross-Account)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteDestinationSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:UpdateSecretVersionStage",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-west-2:987654321098:secret:dest-*"
      ]
    },
    {
      "Sid": "EncryptDestinationSecrets",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:GenerateDataKey",
        "kms:DescribeKey"
      ],
      "Resource": [
        "arn:aws:kms:us-west-2:987654321098:key/dest-key-id"
      ]
    }
  ]
}
```

**Trust Policy** (Destination Role):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/SecretReplicatorExecutionRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "unique-external-id-12345"
        }
      }
    }
  ]
}
```

## Error Handling

### Error Classification

| Error Type | Category | Action |
|------------|----------|--------|
| `ResourceNotFoundException` | Permanent | Create secret, or fail if source not found |
| `AccessDeniedException` | Permanent | Log error, send to DLQ |
| `InvalidRequestException` | Permanent | Log error, send to DLQ |
| `ThrottlingException` | Transient | Retry with exponential backoff |
| `InternalServiceError` | Transient | Retry with exponential backoff |
| Regex timeout | Permanent | Log error, send to DLQ |
| JSON parsing error | Permanent | Log error, send to DLQ |

### Retry Strategy

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((ThrottlingException, InternalServiceError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60)
)
def write_secret_with_retry(client, secret_id, value):
    """Write secret with automatic retry for transient errors"""
    return client.put_secret(secret_id, value)
```

### Dead Letter Queue

**Purpose**: Capture events that fail permanently after retries

**Setup**:
```yaml
DeadLetterQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: !Sub ${AWS::StackName}-dlq
    KmsMasterKeyId: alias/aws/sqs
    MessageRetentionPeriod: 1209600  # 14 days

DeadLetterAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub ${AWS::StackName}-dlq-alarm
    MetricName: ApproximateNumberOfMessagesVisible
    Namespace: AWS/SQS
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 1
    ComparisonOperator: GreaterThanOrEqualToThreshold
    Dimensions:
      - Name: QueueName
        Value: !GetAtt DeadLetterQueue.QueueName
```

## Monitoring & Observability

### CloudWatch Logs

**Log Structure** (JSON):
```json
{
  "timestamp": "2025-10-31T20:00:00Z",
  "level": "INFO",
  "message": "Secret replicated successfully",
  "context": {
    "source_secret_arn": "arn:aws:secretsmanager:us-east-1:123:secret:source-abc123",
    "source_version_id": "v1",
    "dest_secret_arn": "arn:aws:secretsmanager:us-west-2:456:secret:dest-xyz789",
    "dest_version_id": "v2",
    "transformation_applied": true,
    "duration_ms": 234
  }
}
```

**Important**: NEVER log secret values (plaintext or encrypted)

### CloudWatch Metrics

**Custom Namespace**: `SecretReplicator`

**Metrics**:
- `ReplicationSuccess` (Count) - Successful replications
- `ReplicationFailure` (Count) - Failed replications
- `TransformationDuration` (Milliseconds) - Time to transform
- `ReplicationDuration` (Milliseconds) - Total end-to-end time
- `AssumeRoleSuccess` (Count) - Successful role assumptions
- `AssumeRoleFailure` (Count) - Failed role assumptions

**Dimensions**:
- `SourceRegion`
- `DestinationRegion`
- `TransformationType` (sed/json)

### CloudWatch Alarms

```yaml
ReplicationFailureAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub ${AWS::StackName}-replication-failures
    MetricName: ReplicationFailure
    Namespace: SecretReplicator
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 1
    ComparisonOperator: GreaterThanOrEqualToThreshold
    AlarmActions:
      - !Ref AlertTopic
```

## Security Architecture

### Encryption in Transit
- All AWS API calls use TLS 1.2+
- Secrets never transmitted in plaintext

### Encryption at Rest
- Source secrets encrypted with KMS CMK
- Destination secrets encrypted with KMS CMK (may be different key)
- Transformation secrets encrypted with KMS (default aws/secretsmanager or CMK)
- CloudWatch Logs encrypted with KMS (optional)

### Least Privilege
- Lambda execution role has minimal permissions
- Destination role limited to specific secret patterns
- KMS key policies enforce encryption/decryption boundaries

### Audit Trail
- All API calls logged to CloudTrail
- Lambda invocations logged to CloudWatch Logs
- Secret access tracked via Secrets Manager logging

### Preventing Replication Loops

**Problem**: Destination secret update could trigger another replication

**Solutions**:
1. **EventBridge Filtering** (Preferred):
   ```json
   {
     "detail": {
       "requestParameters": {
         "secretId": [{
           "prefix": "source-"
         }]
       }
     }
   }
   ```

2. **Tag-based Filtering**:
   - Tag source secrets with `replication:enabled=true`
   - Filter EventBridge rule by tag
   - Don't tag destination secrets

3. **Version Comparison**:
   - Store source version ID in destination secret metadata
   - Skip replication if already at same version

## Performance Considerations

### Lambda Optimization
- **Cold Start**: ~500-800ms (Python 3.12)
- **Warm Execution**: ~50-200ms (depends on secret size)
- **Memory**: 256 MB sufficient for most secrets (<1MB)
- **Concurrent Executions**: Set reserved concurrency to avoid throttling

### Secrets Manager Limits
- Max secret size: 65,536 bytes
- API rate limits: 5,000 TPS (GetSecretValue), 3,000 TPS (PutSecretValue)
- Use exponential backoff for throttling

### Cost Optimization
- Use Lambda reserved concurrency to control costs
- Cache transformation secrets in memory (Lambda execution context)
- Minimize cross-region data transfer
- Use VPC endpoints for Secrets Manager (avoid NAT gateway costs)

## Disaster Recovery

### Lambda Function Recovery
- Deploy Lambda across multiple regions (active-active)
- Use global DynamoDB table for coordination (if needed)
- Store configuration in Parameter Store or Secrets Manager

### Data Recovery
- Secrets Manager provides point-in-time recovery (version history)
- Transformation secrets have automatic versioning (AWSCURRENT, AWSPREVIOUS)
- CloudWatch Logs retained for 30+ days

### Backup Strategy
- Regular snapshots of transformation secret configurations
- Export CloudWatch metrics to S3
- Maintain runbooks for common failure scenarios

## Scalability

### Horizontal Scaling
- Lambda automatically scales to handle increased load
- EventBridge can handle millions of events per second
- Secrets Manager API has high throughput limits

### Vertical Scaling
- Increase Lambda memory for large secrets (>10KB)
- Increase Lambda timeout for complex transformations

### Multi-Region Deployment
- Deploy Lambda in each source region
- Use regional EventBridge rules
- Create transformation secrets in each region (or use cross-region secret replication)

## Future Enhancements

### Potential Features
1. **Bi-directional replication** - Sync secrets in both directions
2. **Multi-destination support** - Replicate to multiple targets
3. **Scheduled replication** - Periodic sync independent of events
4. **Transformation templates** - Reusable transformation libraries
5. **Web UI** - Console for managing replication rules
6. **Terraform/CDK support** - Infrastructure as code examples
7. **Secret rotation integration** - Trigger rotation on destination

### Performance Improvements
1. **Batch processing** - Handle multiple events in single invocation
2. **Caching layer** - Cache sedfile and transformations
3. **Async replication** - Use Step Functions for orchestration

### Security Enhancements
1. **Secret scanning** - Detect exposed credentials in transformations
2. **Compliance reporting** - Audit trail for compliance requirements
3. **Encryption key rotation** - Automate KMS key rotation
