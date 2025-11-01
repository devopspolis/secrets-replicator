# Claude Code Context - Secrets Replicator

## Project Overview

**Repository**: secrets-replicator
**Purpose**: AWS Lambda function for cross-region/cross-account AWS Secrets Manager replication with value transformation
**Target**: AWS Serverless Application Repository (SAR) publication

## Problem Statement

AWS Secrets Manager provides native secret replication across regions, but it does NOT support modification of the destination secret values. This project fills that gap by:

1. Replicating secrets to different regions/accounts
2. Applying string transformations to destination values (e.g., replacing `us-east-1` with `us-west-2` in connection strings)
3. Supporting disaster recovery and business continuity use cases

## ChatGPT Conversation Summary

This project originated from a detailed ChatGPT conversation (https://chatgpt.com/share/69057ae0-4644-8004-a022-5d8ee665cc83) where comprehensive recommendations were provided for:
- Architecture design
- Security considerations
- Implementation approach
- SAR publishing guidance

## Key Requirements

### Functional Requirements
- Trigger on AWS Secrets Manager secret updates via EventBridge
- Copy secrets from source to destination (cross-region and/or cross-account)
- Apply configurable string transformations using sed-style replacements
- Support both text (SecretString) and binary (SecretBinary) secrets
- Handle JSON-structured secrets with field-level transformations

### Non-Functional Requirements
- **Security**: Never log plaintext secret values
- **Encryption**: Use KMS CMKs for all encryption operations
- **Least Privilege**: Minimal IAM permissions for all operations
- **Resilience**: Retry logic, DLQ for failures, CloudWatch metrics
- **Idempotency**: Avoid creating duplicate secret versions unnecessarily
- **Auditing**: CloudTrail integration, structured audit events

## Naming Conventions

### Repository Name (Selected)
`secrets-replicator` ✓ (current)

### Alternative Names Considered
- secrets-replica-sed
- secret-copy-sed
- secrets-sync-modifier
- multiregion-secret-mirror
- secret-dr-replicator

### Lambda/SAR Application Name (Recommended)
- SecretMirror-Sed
- SecretsReplicator
- secrets-replicator-sed

## High-Level Architecture

```
EventBridge Rule → Lambda Function → Secrets Manager (Destination)
       ↑                  ↓
   CloudTrail         S3 (sedfile)
                         ↓
                    STS AssumeRole (cross-account)
```

### Components

1. **EventBridge Rule**
   - Matches CloudTrail events from Secrets Manager
   - Event types: `PutSecretValue`, `UpdateSecret`, `ReplicateSecretToRegions`, `ReplicateSecretVersion`
   - Filters by source secret ARN or pattern

2. **Lambda Function**
   - Validates event and extracts secret metadata
   - Retrieves source secret value (`GetSecretValue`)
   - Loads transformation rules (sedfile)
   - Applies transformations to secret value
   - Writes to destination secret (`CreateSecret` or `PutSecretValue`)
   - Handles cross-account via STS AssumeRole

3. **Transformation Rules (Sedfile)**
   - Storage options:
     - Bundled in Lambda deployment package (simple, versioned)
     - S3 object with SSE-KMS encryption (updateable without redeployment)
     - Secrets Manager config secret (encrypted, but risk of circular dependency)
   - **Recommended**: S3 with KMS encryption

4. **IAM Roles & Policies**
   - Lambda execution role (source account)
   - Destination account role (for cross-account writes)
   - Least-privilege permissions for each operation

## Transformation Engine

### Two Modes Supported

1. **sed-style replacements** (line-by-line regex)
   ```
   s/us-east-1/us-west-2/g
   s/prod-db-1/prod-db-2/g
   ```

2. **JSON field mapping** (structured secrets)
   ```json
   {
     "$.database.host": {"from": "db1.us-east-1", "to": "db1.us-west-2"},
     "$.database.region": {"from": "us-east-1", "to": "us-west-2"}
   }
   ```

### Implementation Notes
- All transformations operate on in-memory values only
- Never write plaintext to disk or logs
- Support for binary secrets (copy without transformation)
- Validate regex patterns to prevent ReDoS attacks
- Limit transformation execution time

## Security Considerations

### Critical Security Rules
1. **NEVER log plaintext secret values** - only log metadata (ARN, version ID, size)
2. Use KMS CMKs for encryption at rest
3. Least-privilege IAM policies (no wildcards unless necessary)
4. Validate all transformation rules before application
5. Prevent replication loops (filter EventBridge by source ARN only)

### IAM Permissions Required

**Lambda Execution Role (Source Account)**
```
secretsmanager:GetSecretValue (source secrets)
secretsmanager:DescribeSecret (source secrets)
kms:Decrypt (source CMK)
sts:AssumeRole (if cross-account)
s3:GetObject (if sedfile in S3)
logs:CreateLogStream, logs:PutLogEvents
```

**Destination Account Role (if cross-account)**
```
secretsmanager:CreateSecret
secretsmanager:PutSecretValue
secretsmanager:UpdateSecretVersionStage
kms:Encrypt, kms:Decrypt (destination CMK)
```

### KMS Considerations
- Source CMK must allow Lambda role to decrypt
- Destination CMK must allow Lambda/assumed role to encrypt
- Document key policies and grants in README

## Error Handling & Resilience

1. **Retry Logic**: Exponential backoff for transient errors
2. **Dead Letter Queue**: SQS or SNS for persistent failures
3. **CloudWatch Alarms**: Alert on repeated failures
4. **Idempotency**: Compare version/checksum before writing
5. **Graceful Degradation**: Continue on non-critical errors

## Cross-Region & Cross-Account Support

### Scenarios to Support
1. Same account, cross-region
2. Same region, cross-account
3. Cross-account AND cross-region
4. Same account, same region (for testing/transformations only)

### Implementation
- Use `boto3.client('secretsmanager', region_name=dest_region)`
- For cross-account: STS AssumeRole with session name `SecretMirrorSession`
- Pass temporary credentials to destination client
- Document trust policies and permission boundaries

## EventBridge Integration

### Example Event Pattern
```json
{
  "source": ["aws.secretsmanager"],
  "detail-type": ["AWS API Call via CloudTrail", "AWS Service Event"],
  "detail": {
    "eventName": ["PutSecretValue", "UpdateSecret", "ReplicateSecretToRegions", "ReplicateSecretVersion"]
  }
}
```

### Event Filtering
- Match specific secret ARNs or patterns
- Handle both `arn` and `aRN` fields (CloudTrail quirk)
- Optional: filter by tags or secret name patterns

## Testing Strategy

### Unit Tests
- Transformation logic (regex, JSON path updates)
- Edge cases: empty values, binary secrets, malformed JSON
- Error handling and retry logic
- IAM policy validation

### Integration Tests
- End-to-end secret replication
- Cross-region operations
- Cross-account operations (with test accounts)
- KMS encryption/decryption
- EventBridge trigger simulation

### Test Environment
- Use ephemeral test secrets
- Dedicated test AWS account/region
- Automated cleanup of test resources
- CI/CD integration (GitHub Actions)

## SAR Publishing Requirements

### SAM Template Components
```yaml
Parameters:
  - DestinationRegion
  - DestinationSecretName
  - SourceSecretPattern
  - SedFileS3Bucket (optional)
  - SedFileS3Key (optional)
  - AssumeRoleArn (optional for cross-account)
  - EventPatternSecretArn (optional)

Resources:
  - SecretReplicatorFunction (Lambda)
  - SecretReplicatorRole (IAM)
  - SecretUpdateRule (EventBridge, optional)
  - SecretUpdatePermission (Lambda permission)
```

### Metadata for SAR
- Application name and description
- Semantic version
- License (MIT recommended)
- README link
- Source code URL
- Required capabilities: CAPABILITY_IAM, CAPABILITY_NAMED_IAM

### Documentation Required
- Installation guide
- Configuration examples for all scenarios
- IAM policy templates
- KMS setup instructions
- Troubleshooting guide
- Example sedfiles

## Project Structure (Recommended)

```
secrets-replicator/
├── src/
│   ├── handler.py              # Main Lambda handler
│   ├── transformer.py          # Transformation engine
│   ├── aws_clients.py          # Boto3 client management
│   └── utils.py                # Helpers and validators
├── tests/
│   ├── unit/
│   │   ├── test_transformer.py
│   │   └── test_handler.py
│   └── integration/
│       └── test_e2e.py
├── examples/
│   ├── sedfile-basic.txt       # Simple sed rules
│   ├── sedfile-json.json       # JSON field mappings
│   ├── same-region.yaml        # SAM parameter example
│   ├── cross-region.yaml       # SAM parameter example
│   └── cross-account.yaml      # SAM parameter example
├── iam/
│   ├── lambda-role.json        # Source account role
│   └── destination-role.json   # Destination account role
├── template.yaml               # AWS SAM template
├── samconfig.toml              # SAM CLI config
├── requirements.txt            # Python dependencies
├── README.md                   # User-facing documentation
├── ARCHITECTURE.md             # Technical architecture
├── IMPLEMENTATION_PLAN.md      # Development roadmap
├── CONTRIBUTING.md             # Contribution guidelines
├── CODE_OF_CONDUCT.md          # Community guidelines
└── LICENSE                     # MIT License
```

## Implementation Roadmap

### Phase 1: Core Functionality
1. Implement transformation engine with unit tests
2. Create Lambda handler with EventBridge event parsing
3. Add source secret retrieval logic
4. Implement destination secret write logic
5. Basic error handling and logging

### Phase 2: Cross-Account Support
1. STS AssumeRole implementation
2. Destination account role templates
3. Cross-account integration tests

### Phase 3: Production Hardening
1. Retry logic with exponential backoff
2. DLQ integration
3. CloudWatch metrics and alarms
4. Idempotency checks
5. Security audit (no plaintext logging)

### Phase 4: SAM Template & Examples
1. Complete SAM template with all parameters
2. Example configurations for all scenarios
3. IAM policy documentation
4. KMS setup guide

### Phase 5: Testing & CI/CD
1. Comprehensive test suite
2. GitHub Actions workflow
3. Automated SAM packaging
4. Integration test automation

### Phase 6: Documentation & Publishing
1. README with installation guide
2. Architecture documentation
3. API documentation
4. Troubleshooting guide
5. SAR publication

## References

### AWS Documentation
- [Secrets Manager EventBridge Integration](https://docs.aws.amazon.com/secretsmanager/latest/userguide/monitoring-eventbridge.html)
- [Secrets Manager Replication](https://docs.aws.amazon.com/secretsmanager/latest/userguide/replicate-secrets.html)
- [EventBridge Event Reference for Secrets Manager](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-secretsmanager.html)
- [Publishing to AWS Serverless Application Repository](https://docs.aws.amazon.com/serverlessrepo/latest/devguide/serverlessrepo-how-to-publish.html)

### Design Decisions to Document
1. Why S3 over bundled sedfile? (flexibility vs simplicity trade-off)
2. Why not use Secrets Manager native replication? (no transformation support)
3. Why EventBridge over Lambda polling? (efficiency, event-driven)
4. Why Python over other runtimes? (boto3 integration, AWS familiarity)

## Next Steps

When ready to implement, start with:
1. Create project structure (Phase 1)
2. Implement and test transformation engine in isolation
3. Build Lambda handler with mock events
4. Add EventBridge integration
5. Iterate on features and hardening

## Notes for Future Developers

- This project originated from a ChatGPT conversation with detailed architectural recommendations
- The core value proposition is transformation during replication (not available in AWS native replication)
- Security is paramount: never log plaintext secrets
- Test thoroughly with cross-account scenarios before SAR publication
- Keep the SAM template simple with sensible defaults but allow customization
