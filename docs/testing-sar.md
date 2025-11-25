# SAR Testing Guide

## Overview

This guide walks you through testing Secrets Replicator after publishing to AWS Serverless Application Repository (SAR).

## Prerequisites

- AWS CLI configured with credentials
- SAM CLI installed
- Application published to SAR (see [SAR Publishing Guide](sar-publishing.md))

## Quick Start

### 1. Create Test Secrets

**Minimal setup (2 secrets = $0.80/month)**:

```bash
# Create test secrets in us-west-2 (default)
./scripts/setup-test-secrets.sh

# Custom regions
./scripts/setup-test-secrets.sh --region us-west-2 --dest-region us-east-1

# Custom prefix
./scripts/setup-test-secrets.sh --prefix my-test
```

This creates:
- **Source secret**: `sar-test-source` with realistic multi-field test data
- **Transformation secret**: `secrets-replicator/transformations/sar-test` with sed + JSON rules

### 2. Deploy from SAR

#### Option A: Console (Recommended for Testing)

1. Go to [AWS SAR Console](https://console.aws.amazon.com/serverlessrepo)
2. Click "Available applications" → "Private applications"
3. Find "secrets-replicator"
4. Click "Deploy"
5. Configure parameters (use values from setup script output):
   - **SourceSecretPattern**: `arn:aws:secretsmanager:us-west-2:ACCOUNT:secret:sar-test-source*`
   - **DestinationRegion**: `us-east-1`
   - **DestinationSecretName**: (leave empty - uses source name)
   - **TransformationSecretPrefix**: `secrets-replicator/transformations/`
   - **TransformMode**: `auto`
6. Check "I acknowledge that this app creates custom IAM roles"
7. Click "Deploy"

#### Option B: CLI

```bash
sam deploy \
  --stack-name secrets-replicator-test \
  --capabilities CAPABILITY_IAM \
  --region us-west-2 \
  --parameter-overrides \
    SourceSecretPattern="arn:aws:secretsmanager:us-west-2:*:secret:sar-test-source*" \
    DestinationRegion=us-east-1 \
    TransformationSecretPrefix="secrets-replicator/transformations/" \
    TransformMode=auto
```

### 3. Test Scenarios

#### Scenario 1: Pass-Through (No Transformation)

Test that basic replication works without transformation.

```bash
# Update source secret (triggers replication)
aws secretsmanager put-secret-value \
  --secret-id sar-test-source \
  --secret-string '{"test": "pass-through", "timestamp": "'$(date +%s)'"}' \
  --region us-west-2

# Wait 5-10 seconds for replication

# Check destination (should match source exactly)
aws secretsmanager get-secret-value \
  --secret-id sar-test-source \
  --region us-east-1 \
  --query SecretString \
  --output text
```

**Expected**: Destination secret value matches source exactly.

#### Scenario 2: Sed Transformation

Test sed-based regex transformation.

```bash
# Tag source secret with transformation reference
aws secretsmanager tag-resource \
  --secret-id sar-test-source \
  --tags "Key=secrets-replicator/transformation,Value=secrets-replicator/transformations/sar-test" \
  --region us-west-2

# Update source secret with us-west-2 references
aws secretsmanager put-secret-value \
  --secret-id sar-test-source \
  --secret-string '{"endpoint": "https://api.us-west-2.example.com", "bucket": "data-us-west-2"}' \
  --region us-west-2

# Wait 5-10 seconds for replication

# Check destination (should have us-east-1)
aws secretsmanager get-secret-value \
  --secret-id sar-test-source \
  --region us-east-1 \
  --query SecretString \
  --output text
```

**Expected**: All `us-west-2` replaced with `us-east-1`.

#### Scenario 3: JSON Transformation

Test structured JSON field transformation.

```bash
# Same tagging as Scenario 2 (already done if following order)

# Update with structured data
aws secretsmanager put-secret-value \
  --secret-id sar-test-source \
  --secret-string '{
    "database": {
      "host": "db1.us-west-2.rds.amazonaws.com",
      "region": "us-west-2"
    },
    "redis": {
      "endpoint": "redis.us-west-2.cache.amazonaws.com:6379",
      "region": "us-west-2"
    }
  }' \
  --region us-west-2

# Wait 5-10 seconds

# Check destination
aws secretsmanager get-secret-value \
  --secret-id sar-test-source \
  --region us-east-1 \
  --query SecretString \
  --output text | jq .
```

**Expected**: All nested fields transformed (database.host, redis.endpoint, etc.).

#### Scenario 4: Failure Handling

Test that failures are handled gracefully.

```bash
# Temporarily break replication (invalid transformation secret)
aws secretsmanager tag-resource \
  --secret-id sar-test-source \
  --tags "Key=secrets-replicator/transformation,Value=invalid-secret-name" \
  --region us-west-2

# Update source
aws secretsmanager put-secret-value \
  --secret-id sar-test-source \
  --secret-string '{"test": "failure"}' \
  --region us-west-2

# Check CloudWatch Logs for error
aws logs tail /aws/lambda/secrets-replicator-SecretsReplicatorFunction-* \
  --follow \
  --region us-west-2
```

**Expected**: See error in logs, message sent to DLQ, CloudWatch alarm triggered.

### 4. Monitor Replication

#### CloudWatch Logs

```bash
# Tail logs in real-time
aws logs tail /aws/lambda/secrets-replicator-SecretsReplicatorFunction-* \
  --follow \
  --region us-west-2

# Filter for errors
aws logs filter-events \
  --log-group-name /aws/lambda/secrets-replicator-SecretsReplicatorFunction-* \
  --filter-pattern "ERROR" \
  --region us-west-2
```

#### CloudWatch Metrics

```bash
# View custom metrics
aws cloudwatch get-metric-statistics \
  --namespace SecretsReplicator \
  --metric-name ReplicationSuccess \
  --dimensions Name=FunctionName,Value=secrets-replicator-SecretsReplicatorFunction-* \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-west-2
```

#### Dead Letter Queue

```bash
# Check DLQ for failed messages
aws sqs receive-message \
  --queue-url $(aws cloudformation describe-stacks \
    --stack-name secrets-replicator-test \
    --query "Stacks[0].Outputs[?OutputKey=='DeadLetterQueueURL'].OutputValue" \
    --output text \
    --region us-west-2) \
  --region us-west-2
```

### 5. Cleanup

When done testing:

```bash
# Delete test secrets (saves ~$0.80/month)
./scripts/cleanup-test-secrets.sh --region us-west-2 --dest-region us-east-1

# Auto-approve deletion (skip confirmation)
./scripts/cleanup-test-secrets.sh --yes

# Delete CloudFormation stack
aws cloudformation delete-stack \
  --stack-name secrets-replicator-test \
  --region us-west-2
```

## Troubleshooting

### Issue: Destination Secret Not Created

**Symptoms**: Source secret updated, but no destination secret appears.

**Diagnosis**:
1. Check CloudWatch Logs for errors
2. Verify EventBridge rule is enabled
3. Check Lambda IAM permissions
4. Verify SourceSecretPattern matches source ARN

**Solution**:
```bash
# Check EventBridge rule status
aws events describe-rule \
  --name secrets-replicator-SecretUpdateRule-* \
  --region us-west-2

# Enable if disabled
aws events enable-rule \
  --name secrets-replicator-SecretUpdateRule-* \
  --region us-west-2
```

### Issue: Transformation Not Applied

**Symptoms**: Destination secret created but values not transformed.

**Diagnosis**:
1. Verify source secret has transformation tag
2. Check transformation secret exists and is readable
3. Verify transformation secret format (JSON with "sed" or "json" keys)

**Solution**:
```bash
# Verify tag
aws secretsmanager describe-secret \
  --secret-id sar-test-source \
  --region us-west-2 \
  --query Tags

# Verify transformation secret
aws secretsmanager get-secret-value \
  --secret-id secrets-replicator/transformations/sar-test \
  --region us-west-2 \
  --query SecretString \
  --output text | jq .
```

### Issue: AccessDenied Errors

**Symptoms**: Replication fails with "AccessDenied" in logs.

**Diagnosis**: Check IAM permissions for Lambda execution role.

**Solution**:
```bash
# Check Lambda role permissions
aws iam get-role-policy \
  --role-name secrets-replicator-SecretsReplicatorRole-* \
  --policy-name SecretsReplicatorPolicy

# Add missing permissions via CloudFormation update
```

## Cost Tracking

### Expected Costs for Testing

| Duration | Replications | Secrets | Total Cost |
|----------|--------------|---------|------------|
| 1 day    | 10           | 2       | $0.03      |
| 1 week   | 50           | 2       | $0.10      |
| 1 month  | 100          | 2       | $0.60      |

**Breakdown**:
- Secrets storage: $0.40/month (2 secrets)
- Lambda + services: ~$0.03-$0.20 depending on activity

### Cost Optimization for Testing

1. **Delete secrets after each test session** (saves $0.80/month)
2. **Disable custom metrics** (`EnableMetrics: false`)
3. **Disable CloudWatch alarms** (comment out in template)
4. **Use 1-day log retention**:
   ```bash
   aws logs put-retention-policy \
     --log-group-name /aws/lambda/secrets-replicator-* \
     --retention-in-days 1 \
     --region us-west-2
   ```

## Next Steps

After successful testing:
1. Update to version 1.0.0 in template.yaml
2. Make SAR application public
3. Publish to additional regions (us-east-1, eu-west-1)
4. Create GitHub release
5. Announce on AWS forums/reddit

## Resources

- [SAR Publishing Guide](sar-publishing.md)
- [Cost Calculator](../scripts/cost-calculator.py)
- [Main README](../README.md)
- [Troubleshooting Guide](../README.md#troubleshooting)
