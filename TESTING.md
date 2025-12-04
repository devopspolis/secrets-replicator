# Testing Guide for Secrets Replicator

This guide covers how to test the secrets-replicator functionality in the dev environment.

## Overview

The secrets-replicator Lambda function:
- **Source**: us-west-2 (where Lambda runs)
- **Destination**: us-east-1 (cross-region replication)
- **Trigger**: EventBridge rule listening for Secrets Manager CloudTrail events
- **Events**: PutSecretValue, UpdateSecret, ReplicateSecretToRegions, ReplicateSecretVersion

## Testing Methods

### Method 1: Automated Test Script (Recommended)

The automated test script creates a test secret, waits for replication, and validates the result.

```bash
# Run the automated test
./scripts/test-replication.sh
```

**What it does:**
1. Creates a test secret in us-west-2 with a timestamp-based name
2. Waits up to 60 seconds for the secret to appear in us-east-1
3. Verifies the secret value matches (no transformation in basic test)
4. Cleans up both secrets automatically

**Important Notes:**
- CloudTrail events can take 5-15 minutes to appear in EventBridge
- The test script waits up to 60 seconds, then provides troubleshooting steps
- Test secrets are automatically deleted on completion or failure

### Method 2: Manual Testing

#### Step 1: Create a Test Secret in Source Region (us-west-2)

```bash
# Create a simple test secret
aws secretsmanager create-secret \
  --name test-replication-manual \
  --description "Manual test secret" \
  --secret-string '{"database":"prod-db","host":"db.us-west-2.example.com"}' \
  --region us-west-2
```

#### Step 2: Monitor Lambda Execution

Watch the Lambda logs for execution:

```bash
# Tail Lambda logs (will show new invocations)
aws logs tail /aws/lambda/secrets-replicator \
  --region us-west-2 \
  --follow \
  --format short
```

#### Step 3: Check Destination Secret (us-east-1)

After the Lambda executes (check logs), verify the destination secret:

```bash
# Check if secret exists in destination
aws secretsmanager describe-secret \
  --secret-id test-replication-manual \
  --region us-east-1

# Get the secret value
aws secretsmanager get-secret-value \
  --secret-id test-replication-manual \
  --region us-east-1 \
  --query 'SecretString' \
  --output text | jq .
```

#### Step 4: Cleanup

```bash
# Delete from source
aws secretsmanager delete-secret \
  --secret-id test-replication-manual \
  --region us-west-2 \
  --force-delete-without-recovery

# Delete from destination
aws secretsmanager delete-secret \
  --secret-id test-replication-manual \
  --region us-east-1 \
  --force-delete-without-recovery
```

### Method 3: Direct Lambda Invocation (Testing Without EventBridge)

Test the Lambda directly with a sample event payload:

```bash
# Create test event payload
cat > test-event.json << 'EOF'
{
  "version": "0",
  "id": "test-event-id",
  "detail-type": "AWS API Call via CloudTrail",
  "source": "aws.secretsmanager",
  "account": "737549531315",
  "time": "2025-12-04T10:00:00Z",
  "region": "us-west-2",
  "resources": [],
  "detail": {
    "eventVersion": "1.08",
    "userIdentity": {
      "type": "AssumedRole",
      "principalId": "AIDAI1234567890",
      "arn": "arn:aws:sts::737549531315:assumed-role/test-role/test-session",
      "accountId": "737549531315",
      "sessionContext": {
        "sessionIssuer": {
          "type": "Role",
          "principalId": "AIDAI1234567890",
          "arn": "arn:aws:iam::737549531315:role/test-role",
          "accountId": "737549531315",
          "userName": "test-role"
        }
      }
    },
    "eventTime": "2025-12-04T10:00:00Z",
    "eventSource": "secretsmanager.amazonaws.com",
    "eventName": "PutSecretValue",
    "awsRegion": "us-west-2",
    "sourceIPAddress": "10.0.0.1",
    "userAgent": "aws-cli/2.0.0",
    "requestParameters": {
      "secretId": "test-direct-invoke",
      "versionStages": ["AWSCURRENT"]
    },
    "responseElements": {
      "ARN": "arn:aws:secretsmanager:us-west-2:737549531315:secret:test-direct-invoke-AbCdEf",
      "name": "test-direct-invoke",
      "versionId": "test-version-id"
    },
    "requestID": "test-request-id",
    "eventID": "test-event-id",
    "readOnly": false,
    "eventType": "AwsApiCall",
    "recipientAccountId": "737549531315"
  }
}
EOF

# Create the test secret first
aws secretsmanager create-secret \
  --name test-direct-invoke \
  --secret-string '{"test":"value"}' \
  --region us-west-2

# Invoke Lambda directly
aws lambda invoke \
  --function-name secrets-replicator:dev \
  --payload file://test-event.json \
  --region us-west-2 \
  response.json

# Check response
cat response.json | jq .

# Verify destination
aws secretsmanager get-secret-value \
  --secret-id test-direct-invoke \
  --region us-east-1 \
  --query 'SecretString' \
  --output text

# Cleanup
aws secretsmanager delete-secret --secret-id test-direct-invoke --region us-west-2 --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id test-direct-invoke --region us-east-1 --force-delete-without-recovery
rm test-event.json response.json
```

## Monitoring and Troubleshooting

### 1. Check Lambda Logs

```bash
# View recent logs
aws logs tail /aws/lambda/secrets-replicator \
  --region us-west-2 \
  --since 30m

# Follow logs in real-time
aws logs tail /aws/lambda/secrets-replicator \
  --region us-west-2 \
  --follow
```

### 2. Check CloudWatch Metrics

```bash
# Replication success count
aws cloudwatch get-metric-statistics \
  --region us-west-2 \
  --namespace SecretsReplicator \
  --metric-name ReplicationSuccess \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Replication failures
aws cloudwatch get-metric-statistics \
  --region us-west-2 \
  --namespace SecretsReplicator \
  --metric-name ReplicationFailure \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Replication duration
aws cloudwatch get-metric-statistics \
  --region us-west-2 \
  --namespace SecretsReplicator \
  --metric-name ReplicationDuration \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

### 3. Check EventBridge Rule Status

```bash
# Get rule name
RULE_NAME=$(aws events list-rules --region us-west-2 \
  --name-prefix secrets-replicator-dev | jq -r '.Rules[0].Name')

# Check rule details
aws events describe-rule \
  --name "$RULE_NAME" \
  --region us-west-2

# Check rule targets
aws events list-targets-by-rule \
  --rule "$RULE_NAME" \
  --region us-west-2
```

### 4. Check Dead Letter Queue

```bash
# Get DLQ URL from stack outputs
DLQ_URL=$(aws cloudformation describe-stacks \
  --stack-name secrets-replicator-dev \
  --region us-west-2 \
  --query 'Stacks[0].Outputs[?OutputKey==`DeadLetterQueueUrl`].OutputValue' \
  --output text)

# Check for messages in DLQ
aws sqs receive-message \
  --queue-url "$DLQ_URL" \
  --region us-west-2 \
  --max-number-of-messages 10
```

### 5. Check CloudWatch Alarms

```bash
# List all alarms for the stack
aws cloudwatch describe-alarms \
  --region us-west-2 \
  --alarm-name-prefix secrets-replicator-dev
```

## Common Issues

### Issue 1: Replication Not Triggered

**Symptoms:**
- Secret created in source, but not appearing in destination
- No Lambda invocations in CloudWatch Logs

**Possible Causes:**
1. **CloudTrail delay**: CloudTrail events can take 5-15 minutes
2. **EventBridge rule disabled**: Check rule state
3. **IAM permissions**: Lambda role may lack permissions

**Resolution:**
```bash
# Check EventBridge rule is enabled
RULE_NAME=$(aws events list-rules --region us-west-2 \
  --name-prefix secrets-replicator-dev | jq -r '.Rules[0].Name')
aws events describe-rule --name "$RULE_NAME" --region us-west-2 | jq '.State'

# If disabled, enable it
aws events enable-rule --name "$RULE_NAME" --region us-west-2
```

### Issue 2: Lambda Execution Errors

**Symptoms:**
- Lambda logs show errors
- CloudWatch metric `ReplicationFailure` is increasing

**Possible Causes:**
1. **IAM permissions**: Missing secretsmanager:CreateSecret or PutSecretValue in destination
2. **KMS permissions**: Unable to decrypt source or encrypt destination
3. **Network issues**: Cannot reach destination region

**Resolution:**
```bash
# Check Lambda logs for specific error
aws logs tail /aws/lambda/secrets-replicator --region us-west-2 --since 1h

# Check Lambda role permissions
aws iam get-role-policy \
  --role-name secrets-replicator-dev-SecretReplicatorFunctionRole-* \
  --policy-name secrets-replicator-dev-SecretReplicatorFunctionRoleDefaultPolicy-*
```

### Issue 3: Secret Exists But Value Wrong

**Symptoms:**
- Secret created in destination
- Value doesn't match expected (transformation issue)

**Possible Causes:**
1. **Transformation configuration**: Check TRANSFORM_MODE and transformation rules
2. **JSON parsing**: Secret value may not be valid JSON
3. **Sedfile syntax**: If using sed transformations, check pattern syntax

**Resolution:**
```bash
# Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name secrets-replicator \
  --region us-west-2 | jq '.Environment.Variables'

# For transformations, check the transformation secret
aws secretsmanager get-secret-value \
  --secret-id secrets-replicator/transformations/test-replication-manual \
  --region us-west-2 \
  --query 'SecretString' \
  --output text
```

## Performance Testing

To test performance with multiple secrets:

```bash
# Create multiple test secrets
for i in {1..10}; do
  aws secretsmanager create-secret \
    --name "perf-test-$i" \
    --secret-string "{\"test\":\"value-$i\"}" \
    --region us-west-2 &
done

# Wait for all creates to complete
wait

# Monitor CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --region us-west-2 \
  --namespace SecretsReplicator \
  --metric-name ReplicationDuration \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average,Maximum,Minimum

# Cleanup
for i in {1..10}; do
  aws secretsmanager delete-secret --secret-id "perf-test-$i" --region us-west-2 --force-delete-without-recovery
  aws secretsmanager delete-secret --secret-id "perf-test-$i" --region us-east-1 --force-delete-without-recovery
done
```

## Best Practices for Testing

1. **Use Test Prefixes**: Always prefix test secrets with `test-` or similar for easy identification
2. **Tag Test Secrets**: Add tags like `Purpose=Testing` and `AutoDelete=true`
3. **Clean Up**: Always delete test secrets after testing
4. **Monitor Costs**: Each secret costs $0.40/month, so clean up promptly
5. **Use Automation**: Prefer the automated test script over manual testing
6. **Check Logs First**: Always check Lambda logs before troubleshooting elsewhere
7. **Wait for CloudTrail**: Remember that CloudTrail events can take 5-15 minutes

## Advanced Testing Scenarios

### Testing with Transformations

Coming soon: Documentation for testing with sed and JSON transformations.

### Testing Cross-Account Replication

Coming soon: Documentation for testing cross-account replication with AssumeRole.

### Testing Failure Scenarios

Coming soon: Documentation for testing error handling and retry logic.
