# Troubleshooting Guide

Comprehensive troubleshooting guide for Secrets Replicator.

---

## Table of Contents

1. [Overview](#overview)
2. [Common Issues](#common-issues)
3. [IAM and Permissions](#iam-and-permissions)
4. [Transformation Issues](#transformation-issues)
5. [EventBridge and Triggers](#eventbridge-and-triggers)
6. [Performance and Timeouts](#performance-and-timeouts)
7. [Cross-Account Issues](#cross-account-issues)
8. [KMS and Encryption](#kms-and-encryption)
9. [Debugging Tools](#debugging-tools)
10. [Error Reference](#error-reference)

---

## Overview

This guide helps diagnose and resolve common issues with Secrets Replicator.

### Quick Diagnostic Checklist

Before diving deep, check these basics:

- [ ] Lambda function exists and is active
- [ ] EventBridge rule is enabled
- [ ] Source secret exists and has correct ARN
- [ ] Destination region is valid
- [ ] IAM permissions are configured
- [ ] CloudWatch logs are accessible
- [ ] No typos in environment variables

---

## Common Issues

### Issue 1: Secret Not Replicating

**Symptoms**:
- Source secret updated, but destination unchanged
- No Lambda invocations in CloudWatch Logs
- No errors visible

**Diagnosis**:

```bash
# Step 1: Check EventBridge rule status
aws events describe-rule \
  --name secrets-replicator-prod-SecretChangeRule

# Look for: "State": "ENABLED"

# Step 2: Check EventBridge rule targets
aws events list-targets-by-rule \
  --rule secrets-replicator-prod-SecretChangeRule

# Verify Lambda ARN is correct

# Step 3: Check Lambda function exists
aws lambda get-function \
  --function-name secrets-replicator-prod-replicator

# Step 4: Check recent Lambda invocations
aws logs tail /aws/lambda/secrets-replicator-prod-replicator \
  --since 10m
```

**Solutions**:

**Solution A**: Enable EventBridge Rule
```bash
aws events enable-rule \
  --name secrets-replicator-prod-SecretChangeRule
```

**Solution B**: Fix EventBridge Rule Pattern

Check the event pattern matches your source secret:

```bash
# Get current pattern
aws events describe-rule \
  --name secrets-replicator-prod-SecretChangeRule \
  --query EventPattern

# Expected pattern:
{
  "source": ["aws.secretsmanager"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventName": ["PutSecretValue"]
  }
}
```

**Solution C**: Verify Source Secret ARN

```bash
# Check Lambda environment variable
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.SOURCE_SECRET_ARN'

# Compare with actual secret ARN
aws secretsmanager describe-secret \
  --secret-id my-source-secret \
  --query ARN
```

---

### Issue 2: AccessDenied Errors

**Symptoms**:
```
ERROR: AccessDenied - User is not authorized to perform: secretsmanager:GetSecretValue on resource: arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret
```

**Diagnosis**:

```bash
# Step 1: Get Lambda execution role
ROLE_ARN=$(aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Role' --output text)

echo "Lambda Role: $ROLE_ARN"

# Step 2: Get role policies
ROLE_NAME=$(echo $ROLE_ARN | cut -d'/' -f2)

aws iam list-attached-role-policies \
  --role-name $ROLE_NAME

aws iam list-role-policies \
  --role-name $ROLE_NAME

# Step 3: Get policy details
POLICY_ARN=$(aws iam list-attached-role-policies \
  --role-name $ROLE_NAME \
  --query 'AttachedPolicies[0].PolicyArn' --output text)

aws iam get-policy-version \
  --policy-arn $POLICY_ARN \
  --version-id $(aws iam get-policy --policy-arn $POLICY_ARN --query 'Policy.DefaultVersionId' --output text)
```

**Solutions**:

**Solution A**: Fix IAM Policy

Add missing permissions to Lambda execution role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:123456789012:secret:source-secret-*"
    }
  ]
}
```

**Solution B**: Check Secret Resource ARN

Ensure the IAM policy's `Resource` matches the actual secret ARN:

```bash
# Get secret ARN
aws secretsmanager describe-secret \
  --secret-id my-secret \
  --query ARN

# Compare with IAM policy Resource field
```

**Solution C**: Verify KMS Permissions

If secret is encrypted with KMS:

```bash
# Get KMS key ID
aws secretsmanager describe-secret \
  --secret-id my-secret \
  --query KmsKeyId

# Check key policy allows Lambda role to decrypt
aws kms get-key-policy \
  --key-id <key-id> \
  --policy-name default
```

Add KMS decrypt permission:

```json
{
  "Effect": "Allow",
  "Action": [
    "kms:Decrypt"
  ],
  "Resource": "arn:aws:kms:us-east-1:123456789012:key/<key-id>",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "secretsmanager.us-east-1.amazonaws.com"
    }
  }
}
```

---

### Issue 3: Transformation Not Applied

**Symptoms**:
- Destination secret has same value as source
- No transformation errors in logs
- Replication succeeds but values are identical

**Diagnosis**:

```bash
# Step 1: Check transformation mode
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.TRANSFORM_MODE'

# Step 2: Check transformation configuration
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.{SED_SCRIPT:SED_SCRIPT,JSON_MAPPING:JSON_MAPPING,SED_S3_BUCKET:SED_SCRIPT_S3_BUCKET,SED_S3_KEY:SED_SCRIPT_S3_KEY}'

# Step 3: Check CloudWatch logs for transformation
aws logs filter-log-events \
  --log-group-name /aws/lambda/secrets-replicator-prod-replicator \
  --filter-pattern "transformation" \
  --start-time $(date -u -d '10 minutes ago' +%s)000
```

**Solutions**:

**Solution A**: Verify Sed Pattern Syntax

Test the sed pattern locally:

```bash
# Get source secret value
SOURCE_VALUE=$(aws secretsmanager get-secret-value \
  --secret-id source-secret \
  --query SecretString --output text)

# Test transformation
echo "$SOURCE_VALUE" | sed 's/us-east-1/us-west-2/g'
```

**Solution B**: Check S3 Sedfile Access

If using S3 sedfile:

```bash
# Verify sedfile exists
aws s3 ls s3://my-bucket/sedfiles/transform.sed

# Download and inspect
aws s3 cp s3://my-bucket/sedfiles/transform.sed - | cat

# Check Lambda has S3 read permission
# Lambda role needs: s3:GetObject, s3:GetObjectVersion
```

**Solution C**: Validate JSON Mapping

Test JSONPath expressions:

```python
import json
from jsonpath_ng import parse

# Load secret
secret = json.loads('{"host":"dev-db.example.com"}')

# Test path
path = parse('$.host')
matches = path.find(secret)

if matches:
    print(f"Found: {matches[0].value}")
else:
    print("Path not found!")
```

**Solution D**: Check Transform Mode

Ensure `TRANSFORM_MODE` is set correctly:

```bash
# Should be "sed" or "json"
aws lambda update-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --environment Variables={TRANSFORM_MODE=sed,...}
```

---

### Issue 4: Destination Secret Not Created

**Symptoms**:
- Source secret replicates successfully (logs show success)
- Destination secret doesn't exist
- No errors in Lambda logs

**Diagnosis**:

```bash
# Step 1: Check destination secret exists
aws secretsmanager describe-secret \
  --secret-id destination-secret \
  --region us-west-2

# If not found, check Lambda permissions

# Step 2: Check Lambda can write to destination
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.{DEST_SECRET_NAME:DEST_SECRET_NAME,DEST_REGION:DEST_REGION}'

# Step 3: Check CloudWatch logs for destination writes
aws logs filter-log-events \
  --log-group-name /aws/lambda/secrets-replicator-prod-replicator \
  --filter-pattern "destination" \
  --start-time $(date -u -d '10 minutes ago' +%s)000
```

**Solutions**:

**Solution A**: Add CreateSecret Permission

Lambda role needs `secretsmanager:CreateSecret`:

```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:CreateSecret",
    "secretsmanager:PutSecretValue",
    "secretsmanager:DescribeSecret"
  ],
  "Resource": "arn:aws:secretsmanager:us-west-2:123456789012:secret:destination-secret-*"
}
```

**Solution B**: Check Destination Region Configuration

```bash
# Verify correct region
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.DEST_REGION'

# Should match intended region (e.g., us-west-2)
```

**Solution C**: Pre-Create Destination Secret

Manually create the destination secret:

```bash
aws secretsmanager create-secret \
  --name destination-secret \
  --region us-west-2 \
  --secret-string '{"placeholder":"value"}'
```

---

## IAM and Permissions

### Debugging IAM Issues

#### Tool 1: IAM Policy Simulator

```bash
# Simulate GetSecretValue
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:role/SecretsReplicatorRole \
  --action-names secretsmanager:GetSecretValue \
  --resource-arns arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-abc123

# Look for: "EvalDecision": "allowed"
```

#### Tool 2: CloudTrail Event History

```bash
# Find recent access denied events
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue \
  --max-results 10 \
  --query 'Events[?contains(CloudTrailEvent, `AccessDenied`)]'
```

#### Tool 3: IAM Access Analyzer

```bash
# Check for overly permissive policies
aws accessanalyzer list-findings \
  --analyzer-arn arn:aws:access-analyzer:us-east-1:123456789012:analyzer/my-analyzer
```

### Common Permission Issues

#### Issue: Cross-Region Permissions

**Problem**: Lambda in `us-east-1` can't write to secret in `us-west-2`

**Solution**: IAM is global, but ensure resource ARNs specify correct region:

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:PutSecretValue",
  "Resource": "arn:aws:secretsmanager:us-west-2:123456789012:secret:my-secret-*"
}
```

#### Issue: KMS Key in Different Region

**Problem**: KMS key in `us-west-2` can't be used from Lambda in `us-east-1`

**Solution**: KMS keys are regional. Use a KMS key in the **destination region**:

```bash
# Create KMS key in destination region
aws kms create-key --region us-west-2

# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --environment Variables={KMS_KEY_ID=<key-id-in-us-west-2>,...}
```

---

## Transformation Issues

### Sed Pattern Debugging

#### Issue: Pattern Not Matching

**Test Pattern**:

```bash
# Test with sample input
echo "db.us-east-1.rds.amazonaws.com" | sed 's/us-east-1/us-west-2/g'

# Expected: db.us-west-2.rds.amazonaws.com

# Test with actual secret
aws secretsmanager get-secret-value \
  --secret-id source-secret \
  --query SecretString --output text | \
  sed 's/us-east-1/us-west-2/g'
```

#### Issue: Special Characters Not Escaped

**Problem**:
```bash
s/example.com/newdomain.com/g  # WRONG - matches any character
```

**Solution**:
```bash
s/example\.com/newdomain.com/g  # CORRECT - matches literal dot
```

#### Issue: Sed Syntax Error

**Test Syntax**:

```bash
# This will fail
echo "test" | sed 's/(/)/g'
# sed: -e expression #1, char 7: unterminated `s' command

# Escape special characters
echo "test" | sed 's/\(/\)/g'
```

### JSON Transformation Debugging

#### Issue: JSONPath Not Found

**Test JSONPath**:

```python
from jsonpath_ng import parse
import json

secret = json.loads('{"database":{"host":"example.com"}}')

# Test path exists
path = parse('$.database.host')
matches = path.find(secret)

if matches:
    print(f"Found: {matches[0].value}")
else:
    print("ERROR: Path not found")

# Test update
path.update(secret, "newhost.com")
print(json.dumps(secret, indent=2))
```

#### Issue: JSON Structure Mismatch

**Problem**: Mapping assumes nested structure, but secret is flat

```json
# Secret:
{"host": "example.com"}

# Mapping (WRONG):
{"$.database.host": "newhost.com"}  # $.database doesn't exist
```

**Solution**: Match actual structure

```json
{"$.host": "newhost.com"}
```

---

## EventBridge and Triggers

### EventBridge Rule Not Triggering

#### Check 1: EventBridge Rule Exists and Enabled

```bash
aws events describe-rule \
  --name secrets-replicator-prod-SecretChangeRule

# Look for:
# "State": "ENABLED"
# "EventPattern": {...}
```

#### Check 2: Event Pattern Matches

**Default Pattern**:
```json
{
  "source": ["aws.secretsmanager"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventName": ["PutSecretValue"]
  }
}
```

**Note**: This pattern matches **all** `PutSecretValue` events. Lambda function filters by source ARN.

#### Check 3: CloudTrail Enabled

EventBridge rules for API calls require CloudTrail:

```bash
# Check trails
aws cloudtrail describe-trails

# Verify trail is logging management events
aws cloudtrail get-event-selectors \
  --trail-name my-trail

# Should include:
# "IncludeManagementEvents": true
# "ReadWriteType": "All" or "WriteOnly"
```

#### Check 4: Test EventBridge Rule

Send a test event:

```bash
aws events put-events \
  --entries '[
    {
      "Source": "aws.secretsmanager",
      "DetailType": "AWS API Call via CloudTrail",
      "Detail": "{\"eventName\":\"PutSecretValue\",\"responseElements\":{\"ARN\":\"arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret\"}}"
    }
  ]'

# Check Lambda logs
aws logs tail /aws/lambda/secrets-replicator-prod-replicator --follow
```

---

## Performance and Timeouts

### Lambda Timeout

**Symptoms**:
```
Task timed out after 30.00 seconds
```

**Diagnosis**:

```bash
# Check current timeout
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query Timeout

# Check average duration
aws cloudwatch get-metric-statistics \
  --namespace SecretsReplicator \
  --metric-name ReplicationDuration \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 300 \
  --statistics Average,Maximum
```

**Solutions**:

**Solution A**: Increase Timeout

```bash
# Increase to 60 seconds (or more, up to 900s/15min)
aws lambda update-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --timeout 60
```

**Solution B**: Increase Memory (More CPU)

More memory = more CPU power:

```bash
# Increase to 512 MB (from default 256 MB)
aws lambda update-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --memory-size 512
```

**Solution C**: Optimize Transformation

- Reduce number of sed rules
- Use simpler regex patterns
- Avoid recursive JSONPath expressions

### Cold Start Issues

**Symptoms**:
- First invocation takes 2-3 seconds
- Subsequent invocations are faster (200-500ms)

**Solutions**:

**Solution A**: Provisioned Concurrency

```bash
# Configure provisioned concurrency (keeps 1 instance warm)
aws lambda put-provisioned-concurrency-config \
  --function-name secrets-replicator-prod-replicator \
  --provisioned-concurrent-executions 1 \
  --qualifier $LATEST

# Note: This increases cost (~$6/month per instance)
```

**Solution B**: Scheduled Warming

Create a CloudWatch Event to ping Lambda every 5 minutes:

```yaml
# In template.yaml
WarmingRule:
  Type: AWS::Events::Rule
  Properties:
    ScheduleExpression: rate(5 minutes)
    Targets:
      - Arn: !GetAtt ReplicatorFunction.Arn
        Id: WarmingTarget
        Input: '{"warming": true}'
```

Update Lambda to handle warming events:

```python
# In handler.py
def lambda_handler(event, context):
    if event.get('warming'):
        return {'statusCode': 200, 'body': 'Warmed'}
    # ... rest of handler
```

### High Duration

**Symptoms**:
- HighDurationAlarm triggered
- Average duration > 5 seconds

**Diagnosis**:

```bash
# Get duration statistics
aws cloudwatch get-metric-statistics \
  --namespace SecretsReplicator \
  --metric-name ReplicationDuration \
  --dimensions Name=SourceRegion,Value=us-east-1 Name=DestRegion,Value=us-west-2 \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 300 \
  --statistics Average,Maximum,Minimum
```

**Solutions**:

1. Check secret size (large secrets take longer):
   ```bash
   aws secretsmanager get-secret-value \
     --secret-id source-secret \
     --query 'length(SecretString)'
   ```

2. Check transformation complexity (more rules = slower)

3. Check network latency (cross-region is slower than same-region)

4. Check for retries (exponential backoff adds time)

---

## Cross-Account Issues

### AssumeRole Failures

**Symptoms**:
```
ERROR: AccessDenied - User: arn:aws:sts::111111111111:assumed-role/LambdaRole is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::222222222222:role/DestRole
```

**Diagnosis**:

```bash
# Step 1: Check destination role exists
aws iam get-role \
  --role-name DestRole \
  --profile destination-account

# Step 2: Check trust policy
aws iam get-role \
  --role-name DestRole \
  --query 'Role.AssumeRolePolicyDocument' \
  --profile destination-account
```

**Solutions**:

**Solution A**: Fix Trust Policy

Destination account role trust policy must allow Lambda role to assume it:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/secrets-replicator-LambdaRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "my-secure-external-id-12345"
        }
      }
    }
  ]
}
```

**Solution B**: Add AssumeRole Permission to Lambda Role

Source account Lambda role needs permission to assume destination role:

```json
{
  "Effect": "Allow",
  "Action": "sts:AssumeRole",
  "Resource": "arn:aws:iam::222222222222:role/DestRole"
}
```

**Solution C**: Verify External ID Matches

```bash
# Check Lambda environment variable
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.DEST_ROLE_EXTERNAL_ID'

# Must match External ID in trust policy
```

### Cross-Account KMS Issues

**Symptoms**:
```
ERROR: AccessDenied - The ciphertext refers to a customer master key that does not exist, does not exist in this region, or you are not allowed to access.
```

**Solution**:

Grant cross-account access to destination KMS key:

```json
{
  "Sid": "Allow use of the key from source account",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111111111111:role/secrets-replicator-LambdaRole"
  },
  "Action": [
    "kms:Encrypt",
    "kms:Decrypt",
    "kms:GenerateDataKey"
  ],
  "Resource": "*"
}
```

---

## KMS and Encryption

### KMS Decrypt Errors

**Symptoms**:
```
ERROR: KMSAccessDeniedException - User: arn:aws:iam::123456789012:role/LambdaRole is not authorized to perform: kms:Decrypt on resource
```

**Solutions**:

**Solution A**: Add KMS Decrypt Permission

```json
{
  "Effect": "Allow",
  "Action": [
    "kms:Decrypt"
  ],
  "Resource": "arn:aws:kms:us-east-1:123456789012:key/<source-key-id>",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "secretsmanager.us-east-1.amazonaws.com"
    }
  }
}
```

**Solution B**: Update KMS Key Policy

Add Lambda role to key policy:

```bash
aws kms put-key-policy \
  --key-id <key-id> \
  --policy-name default \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::123456789012:role/secrets-replicator-LambdaRole"
        },
        "Action": [
          "kms:Decrypt"
        ],
        "Resource": "*",
        "Condition": {
          "StringEquals": {
            "kms:ViaService": "secretsmanager.us-east-1.amazonaws.com"
          }
        }
      }
    ]
  }'
```

### KMS Encrypt Errors

**Symptoms**:
```
ERROR: KMSAccessDeniedException - User is not authorized to perform: kms:Encrypt
```

**Solution**: Add KMS Encrypt Permission

```json
{
  "Effect": "Allow",
  "Action": [
    "kms:Encrypt",
    "kms:GenerateDataKey"
  ],
  "Resource": "arn:aws:kms:us-west-2:123456789012:key/<dest-key-id>",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "secretsmanager.us-west-2.amazonaws.com"
    }
  }
}
```

---

## Debugging Tools

### Tool 1: CloudWatch Logs Insights

Query Lambda logs for errors:

```sql
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 20
```

Query transformation details:

```sql
fields @timestamp, transform_mode, transformation_duration, secret_size
| filter transformation_duration > 100
| sort transformation_duration desc
| limit 10
```

### Tool 2: CloudWatch Metrics

Get replication failure count:

```bash
aws cloudwatch get-metric-statistics \
  --namespace SecretsReplicator \
  --metric-name ReplicationFailure \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 300 \
  --statistics Sum
```

### Tool 3: X-Ray Tracing (Advanced)

Enable X-Ray for Lambda:

```bash
aws lambda update-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --tracing-config Mode=Active
```

View traces in X-Ray console to see:
- AWS SDK calls (GetSecretValue, PutSecretValue)
- Duration breakdown
- Errors and exceptions

### Tool 4: Dead Letter Queue

Check DLQ for failed events:

```bash
# Get DLQ URL
DLQ_URL=$(aws sqs get-queue-url \
  --queue-name secrets-replicator-prod-dlq \
  --query QueueUrl --output text)

# Receive messages
aws sqs receive-message \
  --queue-url $DLQ_URL \
  --max-number-of-messages 10

# Purge DLQ (after investigation)
aws sqs purge-queue --queue-url $DLQ_URL
```

---

## Error Reference

### Error: SecretNotFoundError

**Message**: `Secret not found: arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret`

**Cause**: Source secret doesn't exist or ARN is incorrect

**Solution**: Verify secret ARN:
```bash
aws secretsmanager describe-secret --secret-id my-secret
```

### Error: BinarySecretNotSupportedError

**Message**: `Binary secrets are not supported (HTTP 501)`

**Cause**: Source secret contains binary data

**Solution**: Use AWS native replication for binary secrets

### Error: SecretTooLargeError

**Message**: `Secret size exceeds maximum: 65536 bytes`

**Cause**: Secret is larger than configured max size (default 64KB)

**Solution**: Increase `MAX_SECRET_SIZE` or reduce secret size

### Error: TransformationError

**Message**: `Transformation failed: invalid sed pattern`

**Cause**: Sed pattern has syntax error

**Solution**: Test pattern locally:
```bash
echo "test" | sed 's/pattern/replacement/g'
```

### Error: ThrottlingException

**Message**: `Rate exceeded`

**Cause**: Too many AWS API calls

**Solution**:
1. Wait and retry (automatic with exponential backoff)
2. Reduce replication frequency
3. Request quota increase

### Error: InternalServiceError

**Message**: `An internal error occurred`

**Cause**: AWS service issue

**Solution**:
1. Automatic retry (up to 5 attempts)
2. Check AWS Service Health Dashboard
3. Contact AWS Support if persists

---

## Getting Help

### Before Requesting Support

1. **Check CloudWatch Logs**: Most issues are visible in logs
2. **Test Locally**: Test transformations on your machine
3. **Review IAM Policies**: 90% of issues are permissions-related
4. **Search GitHub Issues**: Common problems already solved

### Creating a Bug Report

Include:

1. **Lambda function configuration**:
   ```bash
   aws lambda get-function-configuration \
     --function-name secrets-replicator-prod-replicator
   ```

2. **Recent CloudWatch logs** (with secrets redacted):
   ```bash
   aws logs tail /aws/lambda/secrets-replicator-prod-replicator \
     --since 1h
   ```

3. **EventBridge rule configuration**:
   ```bash
   aws events describe-rule \
     --name secrets-replicator-prod-SecretChangeRule
   ```

4. **Source secret metadata** (NOT the value):
   ```bash
   aws secretsmanager describe-secret \
     --secret-id source-secret
   ```

5. **Steps to reproduce**

### Support Channels

- **GitHub Issues**: https://github.com/devopspolis/secrets-replicator/issues
- **GitHub Discussions**: https://github.com/devopspolis/secrets-replicator/discussions
- **Email**: devopspolis@example.com

---

**Last Updated**: 2025-11-01
**Version**: 1.0.0
**Maintainer**: Devopspolis
