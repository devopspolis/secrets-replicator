# Transformations Guide

Comprehensive guide to secret value transformations in Secrets Replicator.

---

## Table of Contents

1. [Overview](#overview)
2. [Pass-Through Replication](#pass-through-replication)
3. [Auto-Detection](#auto-detection)
4. [Transformation Chains](#transformation-chains)
5. [Sed Transformations](#sed-transformations)
6. [JSON Transformations](#json-transformations)
7. [Transformation Patterns](#transformation-patterns)
8. [Best Practices](#best-practices)
9. [Testing Transformations](#testing-transformations)
10. [Common Pitfalls](#common-pitfalls)
11. [Advanced Techniques](#advanced-techniques)

---

## Overview

Secrets Replicator supports three replication modes:

1. **Pass-Through Mode**: Simple copy without transformation (no tag required)
2. **Sed Mode**: Regex-based find/replace transformations using GNU sed syntax
3. **JSON Mode**: JSONPath-based field mapping for structured JSON secrets

**New in Version 1.1**: Auto-detection and transformation chains allow automatic format detection and sequential application of multiple transformations.

**New in Version 1.2**: Pass-through replication allows simple secret copying without requiring transformation secrets.

### When to Use Each Mode

| Use Case | Pass-Through | Sed Mode | JSON Mode |
|----------|--------------|----------|-----------|
| Simple DR/backup | ✅ Recommended | ❌ Not needed | ❌ Not needed |
| Cross-account sharing (no changes) | ✅ Recommended | ❌ Not needed | ❌ Not needed |
| Simple find/replace | ❌ No transformation | ✅ Recommended | ❌ Overkill |
| Region swapping | ❌ No transformation | ✅ Recommended | ⚠️ Possible but verbose |
| Environment promotion | ❌ No transformation | ⚠️ Risky (broad patterns) | ✅ Recommended |
| Structured field mapping | ❌ No transformation | ❌ Complex | ✅ Recommended |
| Complex multi-line patterns | ❌ No transformation | ✅ Recommended | ❌ Not supported |
| Mixed content (JSON + text) | ✅ Exact copy | ✅ Works | ⚠️ JSON only |
| Non-JSON secrets | ✅ Exact copy | ✅ Only transform option | ❌ Won't work |

---

## Pass-Through Replication

Pass-through replication performs a simple copy of the secret value from source to destination **without any transformation**. This mode is activated automatically when a source secret does not have the `SecretsReplicator:TransformSecretName` tag.

### Use Cases

✅ **Disaster Recovery**: Maintain identical copies of secrets across regions for failover
✅ **Secret Backup**: Create backup copies in secondary regions
✅ **Cross-Account Sharing**: Share secrets across AWS accounts without modification
✅ **Testing**: Test replication setup before adding transformation complexity

### How It Works

1. Source secret update triggers EventBridge event
2. Lambda detects no `SecretsReplicator:TransformSecretName` tag
3. Lambda retrieves source secret value as-is
4. Lambda writes exact copy to destination (no transformation applied)
5. Returns HTTP 200 with `transformMode: "passthrough"`

### Setup

**No configuration required!** Simply deploy Secrets Replicator and it will automatically replicate any secrets that do not have a transformation tag.

```bash
# Deploy Lambda (one-time setup)
sam deploy --parameter-overrides DestinationRegion=us-west-2

# Create or update any secret - it will be automatically replicated
aws secretsmanager put-secret-value \
  --secret-id my-app-secret \
  --secret-string '{"username":"admin","password":"secret123"}'

# Verify replication (wait 2-5 seconds)
aws secretsmanager get-secret-value \
  --secret-id my-app-secret \
  --region us-west-2 \
  --query SecretString \
  --output text

# Output: {"username":"admin","password":"secret123"}  (exact copy)
```

### Example: Cross-Region Backup

**Scenario**: Maintain backup copies of all production secrets in `us-west-2` for disaster recovery.

```bash
# Deploy Lambda targeting backup region
sam deploy --parameter-overrides \
  DestinationRegion=us-west-2 \
  SourceSecretPattern='arn:aws:secretsmanager:us-east-1:*:secret:prod-*'

# All secrets matching pattern will be automatically replicated without transformation
# No tagging required!
```

### Example: Cross-Account Secret Sharing

**Scenario**: Share secrets from production account to DR account without modification.

```bash
# In DR account, create IAM role with trust policy
aws iam create-role \
  --role-name SecretsReplicatorDestinationRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/prod-secrets-replicator-role"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "my-external-id-12345"
        }
      }
    }]
  }'

# Deploy Lambda in production account with cross-account role
sam deploy --parameter-overrides \
  DestinationRegion=us-east-1 \
  DestinationAccountRoleArn=arn:aws:iam::444455556666:role/SecretsReplicatorDestinationRole
```

### Response Format

```json
{
  "statusCode": 200,
  "body": "Secret replicated successfully",
  "transformMode": "passthrough",
  "rulesCount": 0,
  "transformChainLength": 0,
  "sourceRegion": "us-east-1",
  "destRegion": "us-west-2",
  "secretId": "my-app-secret",
  "durationMs": 243.51
}
```

### Enabling Transformations Later

To add transformations to a pass-through secret, simply add the transformation tag:

```bash
# Secret is currently being replicated in pass-through mode

# Add transformation tag
aws secretsmanager tag-resource \
  --secret-id my-app-secret \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap

# Next update will use transformation
aws secretsmanager put-secret-value \
  --secret-id my-app-secret \
  --secret-string '{"host":"db.us-east-1.amazonaws.com"}'

# Destination will now contain transformed value
# {"host":"db.us-west-2.amazonaws.com"}
```

### Binary Secrets

**Note**: Binary secrets are not currently supported and will return HTTP 501. Pass-through mode does not change this behavior.

```bash
# Binary secret returns 501 (not implemented)
aws secretsmanager put-secret-value \
  --secret-id binary-secret \
  --secret-binary fileb://certificate.pfx

# Response: statusCode 501, body: "Binary secret replication not implemented"
```

---

## Auto-Detection

Auto-detection allows Secrets Replicator to automatically determine whether a transformation is sed-style or JSON-based by analyzing the content.

### How It Works

When `TRANSFORM_MODE=auto` (default), the system analyzes each transformation secret:

1. **Parse as JSON**: Attempt to parse transformation content as JSON
2. **Check for JSONPath**: If JSON object with keys starting with `$.`, use JSON mode
3. **Default to Sed**: Otherwise, treat as sed-style transformation

### Detection Logic

```python
# Sed transformation detected
s/us-east-1/us-west-2/g
# Comment lines are ignored
s/dev/prod/g

# JSON transformation detected (keys start with $.)
{
  "$.database.host": "prod-db.example.com",
  "$.environment": "production"
}

# Plain JSON object - detected as SED (no JSONPath keys)
{
  "foo": "bar",
  "baz": "qux"
}
```

### Benefits

✅ **Simpler Configuration**: No need to specify mode for each transformation
✅ **Flexible**: Mix sed and JSON transformations in chains without changing config
✅ **Backward Compatible**: Existing configurations work unchanged
✅ **Fail-Safe**: Falls back to sed mode (more permissive) when uncertain

### Examples

#### Example 1: Auto-Detected Sed Transformation

**Transformation Secret** (`secrets-replicator/transformations/region-swap`):
```bash
# This is auto-detected as sed mode
s/us-east-1/us-west-2/g
s/\.rds\.amazonaws\.com/\.rds.amazonaws.com/g
```

**Configuration**:
```bash
# TRANSFORM_MODE not specified - defaults to 'auto'
DEST_REGION=us-west-2
```

**Tag Source Secret**:
```bash
aws secretsmanager tag-resource \
  --secret-id app-db-config \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap
```

#### Example 2: Auto-Detected JSON Transformation

**Transformation Secret** (`secrets-replicator/transformations/env-promotion`):
```json
{
  "transformations": [
    {
      "path": "$.environment",
      "find": "dev",
      "replace": "prod"
    },
    {
      "path": "$.database.host",
      "find": "dev-db.example.com",
      "replace": "prod-db.example.com"
    }
  ]
}
```

**Configuration**:
```bash
# TRANSFORM_MODE=auto (default) detects JSON format automatically
DEST_REGION=us-east-1
```

**Tag Source Secret**:
```bash
aws secretsmanager tag-resource \
  --secret-id app-config \
  --tags Key=SecretsReplicator:TransformSecretName,Value=env-promotion
```

### When to Override Auto-Detection

Explicitly set `TRANSFORM_MODE` when:

1. **Performance**: Bypass detection overhead for high-volume replications
2. **Debugging**: Force specific mode to troubleshoot transformation issues
3. **Edge Cases**: Content matches wrong format (rare)

```bash
# Explicitly force sed mode
TRANSFORM_MODE=sed

# Explicitly force JSON mode
TRANSFORM_MODE=json
```

---

## Transformation Chains

Transformation chains allow sequential application of multiple transformations, where each transformation operates on the output of the previous one.

### How It Works

Instead of specifying a single transformation name in the tag, provide a **comma-separated list**:

```bash
aws secretsmanager tag-resource \
  --secret-id my-secret \
  --tags "Key=SecretsReplicator:TransformSecretName,Value=transform1,transform2,transform3"
```

**Execution Flow**:
```
Original Secret → Transform1 → Transform2 → Transform3 → Destination Secret
```

Each transformation:
1. Receives the output of the previous transformation as input
2. Auto-detects format (sed or JSON) independently
3. Applies its transformation rules
4. Passes result to next transformation

### Use Cases

#### Use Case 1: Region + Environment Transformation

**Scenario**: Replicate from `us-east-1` dev to `us-west-2` prod

**Transformation 1** - Region Swap (`secrets-replicator/transformations/region-east-to-west`):
```bash
s/us-east-1/us-west-2/g
s/\.rds\.us-east-1\./\.rds.us-west-2./g
```

**Transformation 2** - Environment Promotion (`secrets-replicator/transformations/dev-to-prod`):
```bash
s/dev/prod/g
s/development/production/g
s/"log_level": "DEBUG"/"log_level": "INFO"/g
```

**Setup**:
```bash
# Create both transformation secrets
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-east-to-west \
  --secret-string 's/us-east-1/us-west-2/g'

aws secretsmanager create-secret \
  --name secrets-replicator/transformations/dev-to-prod \
  --secret-string 's/dev/prod/g
s/"log_level": "DEBUG"/"log_level": "INFO"/g'

# Tag source secret with chain
aws secretsmanager tag-resource \
  --secret-id app-db-credentials \
  --tags "Key=SecretsReplicator:TransformSecretName,Value=region-east-to-west,dev-to-prod"
```

**Result**:
```
Original:  {"host": "dev-db.us-east-1.rds.amazonaws.com", "log_level": "DEBUG"}
After T1:  {"host": "dev-db.us-west-2.rds.amazonaws.com", "log_level": "DEBUG"}
After T2:  {"host": "prod-db.us-west-2.rds.amazonaws.com", "log_level": "INFO"}
```

#### Use Case 2: Mixed Sed + JSON Chain

**Scenario**: Apply broad regex changes, then precise JSON field updates

**Transformation 1** - Sed (`region-swap`):
```bash
s/us-east-1/us-west-2/g
```

**Transformation 2** - JSON (`config-overrides`):
```json
{
  "transformations": [
    {
      "path": "$.max_connections",
      "find": "100",
      "replace": "500"
    },
    {
      "path": "$.timeout_seconds",
      "find": "30",
      "replace": "60"
    }
  ]
}
```

**Setup**:
```bash
aws secretsmanager tag-resource \
  --secret-id app-config \
  --tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap,config-overrides"
```

**Auto-Detection**: Each transformation in the chain is auto-detected independently.

#### Use Case 3: Layered Configuration

**Scenario**: Base transformations + environment-specific overrides

**Chain**: `base-config,aws-resources,prod-overrides`

1. **base-config**: Common replacements (hostnames, protocols)
2. **aws-resources**: AWS-specific ARNs and regions
3. **prod-overrides**: Production-specific settings (timeouts, limits)

**Benefit**: Reusable transformation modules - mix and match for different environments.

### Chain Best Practices

1. **Always Quote Tag Values with Commas**: Required for AWS CLI parsing
   ```bash
   # ✅ Correct
   --tags "Key=SecretsReplicator:TransformSecretName,Value=t1,t2,t3"

   # ❌ Incorrect - CLI will misparse commas
   --tags Key=SecretsReplicator:TransformSecretName,Value=t1,t2,t3
   ```

2. **Order Matters**: Transformations apply sequentially - order affects outcome
   ```bash
   # Different results!
   Value=region-swap,env-promotion  # Region first, then environment
   Value=env-promotion,region-swap  # Environment first, then region
   ```

3. **Test Each Step**: Verify intermediate outputs to debug chain issues
   ```bash
   # Test transformation 1 alone
   Value=transform1

   # Then test chain
   Value=transform1,transform2
   ```

4. **Keep Chains Short**: 2-3 transformations recommended for maintainability

5. **Use Descriptive Names**: Makes chains self-documenting
   ```bash
   # Good
   Value=region-east-to-west,account-dev-to-prod,scale-up

   # Bad
   Value=transform1,transform2,transform3
   ```

6. **Version Transformations**: Use Secrets Manager versioning to track changes
   ```bash
   aws secretsmanager update-secret \
     --secret-id secrets-replicator/transformations/my-transform \
     --secret-string "$(cat updated-rules.sed)"

   # Rollback if needed
   aws secretsmanager update-secret-version-stage \
     --secret-id secrets-replicator/transformations/my-transform \
     --version-stage AWSCURRENT \
     --move-to-version-id <previous-version>
   ```

### Chain Monitoring

CloudWatch logs show detailed chain execution:

```json
{
  "message": "Transformation chain detected",
  "transform_count": 3,
  "transforms": ["region-swap", "env-promotion", "scale-up"]
}

{
  "message": "Applying transformation step",
  "step": 1,
  "name": "region-swap",
  "mode": "sed",
  "rules_count": 5
}

{
  "message": "Applying transformation step",
  "step": 2,
  "name": "env-promotion",
  "mode": "json",
  "rules_count": 8
}
```

CloudWatch metrics include chain metadata:
- `transformChainLength`: Number of transformations in chain
- `rulesCount`: Total rules across all transformations

### Error Handling in Chains

**Fail-Fast Behavior**: If any transformation in chain fails, entire replication fails.

**Example Error**:
```
ERROR: Transformation failed at step 2/3 (env-promotion): Invalid JSONPath expression '$.invalid..path'
```

**Recovery**:
1. Fix broken transformation secret
2. Re-trigger replication by updating source secret
3. Check CloudWatch logs for step-by-step execution

---

## Variable Expansion

**NEW FEATURE**: Transformation secrets now support variable references using `${VARIABLE}` syntax that are expanded dynamically for each destination.

### Overview

Variable expansion allows a single transformation secret to work across multiple destinations by substituting runtime values. Instead of creating separate transformation secrets for each region or environment, use variables to make transformations adaptive.

### Why Variable Expansion?

**Without Variables** (old approach):
```bash
# ❌ Need separate transformation secrets for each destination
secrets-replicator/transformations/us-east-1-to-us-west-2
secrets-replicator/transformations/us-east-1-to-eu-west-1
secrets-replicator/transformations/us-east-1-to-ap-south-1
```

**With Variables** (new approach):
```bash
# ✅ One transformation secret for all destinations
secrets-replicator/transformations/region-swap
# Content: s/us-east-1/${REGION}/g
```

### Available Variables

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `${REGION}` | Destination region | `us-west-2` |
| `${SOURCE_REGION}` | Source region | `us-east-1` |
| `${SECRET_NAME}` | Source secret name | `my-app/config` |
| `${DEST_SECRET_NAME}` | Destination secret name (after name mapping) | `my-app/config-west` |
| `${ACCOUNT_ID}` | Destination AWS account ID | `123456789012` |
| `${SOURCE_ACCOUNT_ID}` | Source AWS account ID | `999999999999` |

### Custom Variables

Define custom variables per-destination in the configuration secret:

```json
{
  "destinations": [
    {
      "region": "us-west-2",
      "variables": {
        "ENV": "production",
        "DB_INSTANCE": "prod-db-west",
        "API_DOMAIN": "api.prod.west.example.com"
      }
    },
    {
      "region": "eu-west-1",
      "variables": {
        "ENV": "production",
        "DB_INSTANCE": "prod-db-eu",
        "API_DOMAIN": "api.prod.eu.example.com"
      }
    }
  ]
}
```

### Sed Transformation Examples

#### Example: Adaptive Region Swapping

**Transformation Secret** (`secrets-replicator/transformations/region-swap`):
```bash
# AWS Region endpoints
s/${SOURCE_REGION}\.amazonaws\.com/${REGION}.amazonaws.com/g

# RDS endpoints
s/rds\.${SOURCE_REGION}/rds.${REGION}/g

# S3 bucket URLs
s/s3\.${SOURCE_REGION}\.amazonaws/s3.${REGION}.amazonaws/g

# SNS topic ARNs
s/arn:aws:sns:${SOURCE_REGION}/arn:aws:sns:${REGION}/g
```

**Configuration Secret** (`secrets-replicator/config/destinations`):
```json
[
  {"region": "us-west-2"},
  {"region": "eu-west-1"},
  {"region": "ap-south-1"}
]
```

**How It Works**:
- For `us-west-2`: `${REGION}` → `us-west-2`, `${SOURCE_REGION}` → `us-east-1`
- For `eu-west-1`: `${REGION}` → `eu-west-1`, `${SOURCE_REGION}` → `us-east-1`
- For `ap-south-1`: `${REGION}` → `ap-south-1`, `${SOURCE_REGION}` → `us-east-1`

#### Example: Custom Variables for Multi-Environment

**Transformation Secret**:
```bash
s/dev-${ENV}-/g
s/dev\./${ENV}./g
s/dev-db\./${DB_INSTANCE}./g
```

**Configuration**:
```json
[
  {
    "region": "us-west-2",
    "variables": {
      "ENV": "prod",
      "DB_INSTANCE": "prod-db-west"
    }
  },
  {
    "region": "eu-west-1",
    "variables": {
      "ENV": "prod",
      "DB_INSTANCE": "prod-db-eu"
    }
  }
]
```

### JSON Transformation Examples

#### Example: Region-Aware JSON Transformation

**Transformation Secret** (`secrets-replicator/transformations/json-region-swap`):
```json
{
  "transformations": [
    {
      "path": "$.database.region",
      "find": "us-east-1",
      "replace": "${REGION}"
    },
    {
      "path": "$.database.host",
      "find": "db.us-east-1.amazonaws.com",
      "replace": "db.${REGION}.amazonaws.com"
    },
    {
      "path": "$.metadata.source_region",
      "find": "unknown",
      "replace": "${SOURCE_REGION}"
    }
  ]
}
```

**Source Secret**:
```json
{
  "database": {
    "region": "us-east-1",
    "host": "db.us-east-1.amazonaws.com"
  },
  "metadata": {
    "source_region": "unknown"
  }
}
```

**Result in us-west-2**:
```json
{
  "database": {
    "region": "us-west-2",
    "host": "db.us-west-2.amazonaws.com"
  },
  "metadata": {
    "source_region": "us-east-1"
  }
}
```

### Syntax Rules

1. **Variable Format**: `${VARIABLE_NAME}` (uppercase letters, numbers, underscores only)
2. **Case Sensitive**: Variables are uppercase by convention
3. **Undefined Variables**: Fail with descriptive error message
4. **No Escaping**: Literal `${...}` not currently supported (use custom variables as workaround)
5. **Expansion Timing**: Variables expanded **per-destination** before transformation rules are parsed

### Variable Precedence

When the same variable is defined in multiple places:

1. **Custom variables** (in `destination.variables`) - highest priority
2. **Core variables** (REGION, SOURCE_REGION, etc.) - default values
3. **Undefined** - error

Custom variables can override core variables if needed (advanced use case).

### Testing Variable Expansion

#### Test Locally Before Deployment

```bash
# Manual variable substitution test
echo 's/${REGION}/us-west-2/g' | sed 's/\${REGION}/us-west-2/g'
# Output: s/us-west-2/us-west-2/g

# Test with actual secret value
aws secretsmanager get-secret-value \
  --secret-id my-secret \
  --query SecretString \
  --output text | sed 's/us-east-1/us-west-2/g'
```

#### Create Test Configuration

```bash
# Create test transformation with variables
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/test-variables \
  --secret-string 's/${SOURCE_REGION}/${REGION}/g' \
  --region us-east-1

# Create test destination config
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/config/destinations \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1

# Create test source secret
aws secretsmanager create-secret \
  --name test/variable-expansion \
  --secret-string '{"host":"db.us-east-1.amazonaws.com"}' \
  --region us-east-1

# Trigger replication
aws secretsmanager put-secret-value \
  --secret-id test/variable-expansion \
  --secret-string '{"host":"db.us-east-1.amazonaws.com"}' \
  --region us-east-1

# Wait 5 seconds for replication
sleep 5

# Verify result
aws secretsmanager get-secret-value \
  --secret-id test/variable-expansion \
  --region us-west-2 \
  --query SecretString \
  --output text
# Expected: {"host":"db.us-west-2.amazonaws.com"}
```

### Troubleshooting Variable Expansion

#### Error: Undefined Variable

**Symptom**: CloudWatch logs show `VariableExpansionError: Undefined variable: ${FOO}`

**Cause**: Transformation references a variable not available in the context

**Solution**:
1. Check available variables in error message
2. Add missing variable to `destination.variables` in configuration secret
3. Or use a different core variable (REGION, SOURCE_REGION, etc.)

**Example Fix**:
```json
{
  "destinations": [
    {
      "region": "us-west-2",
      "variables": {
        "FOO": "bar"  // Add missing variable
      }
    }
  ]
}
```

#### Error: Malformed Variable Syntax

**Symptom**: Variables not being expanded

**Cause**: Incorrect variable syntax (e.g., `{REGION}` instead of `${REGION}`)

**Solution**: Use correct syntax `${VARIABLE_NAME}` with dollar sign and braces

#### Debugging Variable Context

Check CloudWatch logs for variable expansion details:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/secrets-replicator \
  --filter-pattern "variable context" \
  --region us-west-2
```

Look for log entries showing available variables:
```json
{
  "message": "Building variable context",
  "destination_region": "us-west-2",
  "variables": {
    "REGION": "us-west-2",
    "SOURCE_REGION": "us-east-1",
    "SECRET_NAME": "my-app/config",
    "DEST_SECRET_NAME": "my-app/config",
    "ACCOUNT_ID": "123456789012",
    "SOURCE_ACCOUNT_ID": "123456789012"
  }
}
```

### Best Practices

1. **Use Descriptive Variable Names**: `${DB_ENDPOINT}` better than `${VAR1}`
2. **Document Custom Variables**: Add comments in configuration secrets
3. **Test Each Destination**: Verify variable expansion works for all destinations
4. **Keep Transformations Simple**: Complex variable logic is harder to debug
5. **Version Transformation Secrets**: Use Secrets Manager versioning for rollback
6. **Monitor CloudWatch Logs**: Check for variable expansion errors

### Example Files

See the following example files for complete working examples:
- `examples/sedfile-variables-region.sed` - Adaptive region swapping
- `examples/sedfile-variables-json.json` - JSON transformation with variables
- `examples/config-custom-variables.json` - Custom variables configuration

---

## Sed Transformations

### Basic Syntax

Sed transformations use standard GNU sed syntax.

#### Substitution Command

```bash
s/pattern/replacement/flags
```

**Flags**:
- `g` - Global replacement (all occurrences)
- `i` - Case-insensitive matching
- `1`, `2`, `3`, ... - Replace only nth occurrence

#### Delete Command

```bash
/pattern/d
```

Delete lines matching the pattern.

#### Examples

**Simple replacement** (first occurrence):
```bash
s/dev/prod/
```

**Global replacement** (all occurrences):
```bash
s/dev/prod/g
```

**Case-insensitive replacement**:
```bash
s/dev/prod/gi
```

**Delete lines containing "debug"**:
```bash
/debug/d
```

---

### Region Swapping

#### Example 1: Basic Region Swap

**Source Secret**:
```json
{
  "host": "db.us-east-1.rds.amazonaws.com",
  "port": "5432"
}
```

**Sed Script**:
```bash
s/us-east-1/us-west-2/g
```

**Result**:
```json
{
  "host": "db.us-west-2.rds.amazonaws.com",
  "port": "5432"
}
```

#### Example 2: Comprehensive AWS Region Swap

**Sedfile** (`region-swap.sed`):
```sed
# RDS endpoints
s/\.us-east-1\.rds\.amazonaws\.com/\.us-west-2.rds.amazonaws.com/g

# ElastiCache endpoints
s/\.us-east-1\.cache\.amazonaws\.com/\.us-west-2.cache.amazonaws.com/g

# S3 buckets (ARNs)
s/arn:aws:s3:::([^-]*)-us-east-1/arn:aws:s3:::\1-us-west-2/g

# DynamoDB tables (ARNs)
s/arn:aws:dynamodb:us-east-1:/arn:aws:dynamodb:us-west-2:/g

# SQS queues
s/sqs\.us-east-1\.amazonaws\.com/sqs.us-west-2.amazonaws.com/g

# SNS topics
s/arn:aws:sns:us-east-1:/arn:aws:sns:us-west-2:/g

# Lambda functions
s/arn:aws:lambda:us-east-1:/arn:aws:lambda:us-west-2:/g

# Secrets Manager
s/arn:aws:secretsmanager:us-east-1:/arn:aws:secretsmanager:us-west-2:/g

# Generic region swap (fallback)
s/us-east-1/us-west-2/g
```

**Setup**:
```bash
# Create transformation secret
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --secret-string "$(cat region-swap.sed)"

# Tag source secret to use this transformation
aws secretsmanager tag-resource \
  --secret-id app-db-credentials \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap
```

---

### Environment Transformations

#### Example 3: Dev to Prod

**Source Secret**:
```json
{
  "api_url": "https://api.dev.example.com",
  "db_host": "dev-postgres.example.com",
  "log_level": "DEBUG",
  "cache_enabled": "false"
}
```

**Sed Script**:
```sed
# Update API URL
s/api\.dev\.example\.com/api.prod.example.com/g

# Update database host
s/dev-postgres/prod-postgres/g

# Change log level
s/"log_level": "DEBUG"/"log_level": "INFO"/g

# Enable cache in production
s/"cache_enabled": "false"/"cache_enabled": "true"/g
```

**Result**:
```json
{
  "api_url": "https://api.prod.example.com",
  "db_host": "prod-postgres.example.com",
  "log_level": "INFO",
  "cache_enabled": "true"
}
```

---

### Protocol and Port Changes

#### Example 4: HTTP to HTTPS

**Sed Script**:
```bash
s/http:/https:/g
```

**Before**:
```
http://api.example.com:8080
```

**After**:
```
https://api.example.com:8080
```

#### Example 5: Port Change

**Sed Script**:
```bash
s/:3000/:8080/g
```

**Before**:
```json
{
  "api_endpoint": "http://localhost:3000",
  "websocket_endpoint": "ws://localhost:3000"
}
```

**After**:
```json
{
  "api_endpoint": "http://localhost:8080",
  "websocket_endpoint": "ws://localhost:8080"
}
```

---

### Account ID Transformations

#### Example 6: Cross-Account ARN Updates

**Sed Script**:
```sed
# Replace account ID in all ARNs
s/arn:aws:([^:]+):([^:]+):111111111111:/arn:aws:\1:\2:222222222222:/g

# Replace account ID in account-specific resources
s/111111111111/222222222222/g
```

**Before**:
```json
{
  "role_arn": "arn:aws:iam::111111111111:role/MyRole",
  "s3_bucket": "arn:aws:s3:::my-bucket-111111111111",
  "kms_key": "arn:aws:kms:us-east-1:111111111111:key/12345"
}
```

**After**:
```json
{
  "role_arn": "arn:aws:iam::222222222222:role/MyRole",
  "s3_bucket": "arn:aws:s3:::my-bucket-222222222222",
  "kms_key": "arn:aws:kms:us-east-1:222222222222:key/12345"
}
```

---

### Complex Multi-Pattern Transformations

#### Example 7: Comprehensive Production Promotion

**Sedfile** (`dev-to-prod.sed`):
```sed
# Environment name
s/dev/prod/g
s/development/production/g

# API endpoints
s/api\.dev\.example\.com/api.example.com/g
s/api-dev\./api./g

# Database hosts
s/dev-db\./prod-db./g
s/dev-postgres\./prod-postgres./g
s/dev-mysql\./prod-mysql./g

# Cache endpoints
s/dev-redis\./prod-redis./g
s/dev-memcached\./prod-memcached./g

# Storage buckets
s/-dev-/-prod-/g
s/bucket-dev/bucket-prod/g

# Ports (dev typically uses non-standard ports)
s/:3000/:443/g
s/:8080/:443/g

# Protocols (enforce HTTPS in prod)
s/http:/https:/g

# Log levels
s/"log_level": "DEBUG"/"log_level": "INFO"/g
s/"log_level": "TRACE"/"log_level": "WARN"/g

# Feature flags
s/"debug_mode": "true"/"debug_mode": "false"/g
s/"verbose": "true"/"verbose": "false"/g

# Timeouts (prod typically has stricter timeouts)
s/"timeout": "600"/"timeout": "30"/g
```

---

## JSON Transformations

### Basic Syntax

JSON transformations use JSONPath expressions to target specific fields.

```json
{
  "$.path.to.field": "new value",
  "$.another.field": "replacement"
}
```

### JSONPath Primer

| Expression | Description | Example |
|------------|-------------|---------|
| `$` | Root object | `$` |
| `.field` | Child field | `$.database` |
| `..field` | Recursive descent | `$..host` |
| `[n]` | Array index | `$.servers[0]` |
| `[*]` | All array elements | `$.servers[*]` |
| `[@.field]` | Filter | `$.servers[@.active]` |

---

### Simple Field Replacements

#### Example 8: Environment Promotion

**Source Secret**:
```json
{
  "environment": "development",
  "api_endpoint": "https://api.dev.example.com",
  "database": "dev-db"
}
```

**JSON Mapping**:
```json
{
  "$.environment": "production",
  "$.api_endpoint": "https://api.example.com",
  "$.database": "prod-db"
}
```

**Result**:
```json
{
  "environment": "production",
  "api_endpoint": "https://api.example.com",
  "database": "prod-db"
}
```

---

### Nested Field Replacements

#### Example 9: Nested Configuration

**Source Secret**:
```json
{
  "database": {
    "host": "dev-db.example.com",
    "port": "5432",
    "name": "dev_database"
  },
  "cache": {
    "redis": {
      "host": "dev-redis.example.com",
      "port": "6379"
    }
  }
}
```

**JSON Mapping**:
```json
{
  "$.database.host": "prod-db.example.com",
  "$.database.name": "prod_database",
  "$.cache.redis.host": "prod-redis.example.com"
}
```

**Result**:
```json
{
  "database": {
    "host": "prod-db.example.com",
    "port": "5432",
    "name": "prod_database"
  },
  "cache": {
    "redis": {
      "host": "prod-redis.example.com",
      "port": "6379"
    }
  }
}
```

---

### Array Transformations

#### Example 10: Array Element Updates

**Source Secret**:
```json
{
  "servers": [
    {"host": "server1.dev.example.com", "port": "8080"},
    {"host": "server2.dev.example.com", "port": "8080"},
    {"host": "server3.dev.example.com", "port": "8080"}
  ]
}
```

**JSON Mapping**:
```json
{
  "$.servers[0].host": "server1.prod.example.com",
  "$.servers[1].host": "server2.prod.example.com",
  "$.servers[2].host": "server3.prod.example.com"
}
```

**Result**:
```json
{
  "servers": [
    {"host": "server1.prod.example.com", "port": "8080"},
    {"host": "server2.prod.example.com", "port": "8080"},
    {"host": "server3.prod.example.com", "port": "8080"}
  ]
}
```

---

### Comprehensive JSON Transformation

#### Example 11: Full Environment Promotion

**Source Secret**:
```json
{
  "app": {
    "name": "MyApp",
    "environment": "development",
    "version": "1.0.0"
  },
  "database": {
    "primary": {
      "host": "dev-db-primary.example.com",
      "port": "5432",
      "database": "dev_myapp",
      "username": "dev_user",
      "ssl": false
    },
    "replica": {
      "host": "dev-db-replica.example.com",
      "port": "5432",
      "database": "dev_myapp",
      "username": "dev_user",
      "ssl": false
    }
  },
  "cache": {
    "host": "dev-redis.example.com",
    "port": "6379",
    "ttl": 60
  },
  "api": {
    "base_url": "https://api.dev.example.com",
    "timeout": 30,
    "retry_count": 3
  },
  "logging": {
    "level": "DEBUG",
    "verbose": true
  }
}
```

**JSON Mapping**:
```json
{
  "$.app.environment": "production",
  "$.database.primary.host": "prod-db-primary.example.com",
  "$.database.primary.database": "prod_myapp",
  "$.database.primary.username": "prod_user",
  "$.database.primary.ssl": true,
  "$.database.replica.host": "prod-db-replica.example.com",
  "$.database.replica.database": "prod_myapp",
  "$.database.replica.username": "prod_user",
  "$.database.replica.ssl": true,
  "$.cache.host": "prod-redis.example.com",
  "$.cache.ttl": 3600,
  "$.api.base_url": "https://api.example.com",
  "$.api.timeout": 10,
  "$.logging.level": "INFO",
  "$.logging.verbose": false
}
```

**Result**:
```json
{
  "app": {
    "name": "MyApp",
    "environment": "production",
    "version": "1.0.0"
  },
  "database": {
    "primary": {
      "host": "prod-db-primary.example.com",
      "port": "5432",
      "database": "prod_myapp",
      "username": "prod_user",
      "ssl": true
    },
    "replica": {
      "host": "prod-db-replica.example.com",
      "port": "5432",
      "database": "prod_myapp",
      "username": "prod_user",
      "ssl": true
    }
  },
  "cache": {
    "host": "prod-redis.example.com",
    "port": "6379",
    "ttl": 3600
  },
  "api": {
    "base_url": "https://api.example.com",
    "timeout": 10,
    "retry_count": 3
  },
  "logging": {
    "level": "INFO",
    "verbose": false
  }
}
```

---

## Transformation Patterns

### Pattern Library

Common transformation patterns for various scenarios.

#### Pattern 1: AWS Service Endpoints

```sed
# RDS
s/([a-zA-Z0-9-]+)\.([a-z0-9-]+)\.rds\.amazonaws\.com/\1.\2.rds.amazonaws.com/g

# ElastiCache
s/([a-zA-Z0-9-]+)\.([a-z0-9-]+)\.cache\.amazonaws\.com/\1.\2.cache.amazonaws.com/g

# OpenSearch
s/([a-zA-Z0-9-]+)\.([a-z0-9-]+)\.es\.amazonaws\.com/\1.\2.es.amazonaws.com/g
```

#### Pattern 2: Connection Strings

```sed
# PostgreSQL
s/postgres:\/\/([^@]+)@dev-([^:]+):(\d+)\/dev_(\w+)/postgres:\/\/\1@prod-\2:\3\/prod_\4/g

# MySQL
s/mysql:\/\/([^@]+)@dev-([^:]+):(\d+)\/dev_(\w+)/mysql:\/\/\1@prod-\2:\3\/prod_\4/g

# MongoDB
s/mongodb:\/\/([^@]+)@dev-([^:]+):(\d+)\/dev_(\w+)/mongodb:\/\/\1@prod-\2:\3\/prod_\4/g
```

#### Pattern 3: ARN Transformations

```sed
# S3 buckets
s/arn:aws:s3:::([^-]+)-dev-/arn:aws:s3:::\1-prod-/g

# IAM roles
s/arn:aws:iam::(\d+):role\/dev-/arn:aws:iam::\1:role\/prod-/g

# Lambda functions
s/arn:aws:lambda:([^:]+):(\d+):function:dev-/arn:aws:lambda:\1:\2:function:prod-/g
```

#### Pattern 4: API Keys and Tokens

```sed
# API key prefix change
s/ak_dev_/ak_prod_/g

# Token prefix change
s/tk_dev_/tk_prod_/g

# Client ID change
s/client_dev_/client_prod_/g
```

---

## Best Practices

### 1. Test Transformations Locally

Always test sed patterns before deploying:

```bash
# Test sed pattern
echo '{"host":"db.us-east-1.amazonaws.com"}' | sed 's/us-east-1/us-west-2/g'

# Test with actual secret value
aws secretsmanager get-secret-value \
  --secret-id my-secret \
  --query SecretString \
  --output text | sed 's/dev/prod/g'
```

### 2. Use Transformation Secrets for Complex Transformations

For sedfiles with >5 rules, store in transformation secrets:

```bash
# Create transformation secret with multi-line sed script
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/dev-to-prod \
  --secret-string "$(cat transform.sed)"

# Enable automatic rotation for transformation secrets (optional)
aws secretsmanager rotate-secret \
  --secret-id secrets-replicator/transformations/dev-to-prod \
  --rotation-lambda-arn arn:aws:lambda:region:account:function:rotator
```

**Benefits**:
- Automatic versioning (AWSCURRENT, AWSPREVIOUS)
- Easy rollback to previous versions
- Encryption at rest with KMS
- IAM-based access control
- No external dependencies
- CloudTrail audit logging

### 3. Be Specific with Patterns

**Bad** (too broad):
```bash
s/dev/prod/g
```
This would replace "development" → "prodevelopment"

**Good** (specific):
```bash
s/dev-/prod-/g
s/\.dev\./\.prod\./g
```

### 4. Escape Special Characters

Escape these characters in sed patterns: `. * [ ] ^ $ \ /`

```bash
# Wrong
s/example.com/newdomain.com/g

# Correct
s/example\.com/newdomain.com/g
```

### 5. Use Comments in Sedfiles

```sed
# Database transformations
s/dev-db/prod-db/g

# API endpoints
s/api\.dev\./api./g

# Log levels
s/"DEBUG"/"INFO"/g
```

### 6. Order Matters

Apply specific patterns before generic ones:

```sed
# Specific pattern first
s/dev-api-special/prod-api-special/g

# Generic pattern second
s/dev-api/prod-api/g
```

### 7. Validate JSON After Transformation

For JSON secrets, validate output:

```bash
# Test transformation and validate JSON
echo '{"host":"dev-db.example.com"}' | \
  sed 's/dev-/prod-/g' | \
  python3 -m json.tool
```

### 8. Document Transformation Intent

Include metadata in sedfiles:

```sed
# Sedfile: dev-to-prod.sed
# Purpose: Transform development secrets to production
# Author: DevOps Team
# Last Updated: 2025-11-01
# Version: 1.2.0

# Transformations
s/dev/prod/g
```

---

## Testing Transformations

### Local Testing

#### Test Sed Patterns

```bash
# Simple test
echo "dev-database" | sed 's/dev/prod/g'
# Output: prod-database

# Test with JSON
cat <<EOF | sed 's/us-east-1/us-west-2/g'
{
  "host": "db.us-east-1.amazonaws.com",
  "region": "us-east-1"
}
EOF

# Test complex sedfile
cat test-secret.json | sed -f transform.sed
```

#### Test JSON Mappings

```python
# test_json_transform.py
import json
from jsonpath_ng import parse

# Source secret
source = {
    "database": {
        "host": "dev-db.example.com"
    }
}

# Mapping
mapping = {
    "$.database.host": "prod-db.example.com"
}

# Apply transformation
for path_expr, new_value in mapping.items():
    path = parse(path_expr)
    path.update(source, new_value)

print(json.dumps(source, indent=2))
```

### Integration Testing

```bash
# Create test secret
aws secretsmanager create-secret \
  --name test-source-secret \
  --secret-string '{"host":"dev-db.example.com"}'

# Trigger replication
aws secretsmanager put-secret-value \
  --secret-id test-source-secret \
  --secret-string '{"host":"dev-db.example.com"}'

# Wait for replication (2-5 seconds)
sleep 5

# Verify transformation
aws secretsmanager get-secret-value \
  --secret-id test-dest-secret \
  --query SecretString \
  --output text

# Expected: {"host":"prod-db.example.com"}
```

---

## Common Pitfalls

### Pitfall 1: Greedy Matching

**Problem**:
```bash
s/.*dev.*/prod/g
```

This replaces the entire line if "dev" appears anywhere.

**Solution**:
```bash
s/dev/prod/g
```

### Pitfall 2: Unescaped Dots

**Problem**:
```bash
s/example.com/newdomain.com/g
```

The `.` matches any character, so "exampleXcom" would also match.

**Solution**:
```bash
s/example\.com/newdomain.com/g
```

### Pitfall 3: Case Sensitivity

**Problem**:
```bash
s/dev/prod/g
```

Won't match "Dev", "DEV", or "DeV".

**Solution**:
```bash
s/dev/prod/gi  # Case-insensitive
```

### Pitfall 4: JSON Field Order

**Problem**: Assuming fields are in a specific order.

**Bad**:
```sed
s/"host": "dev-db"/"host": "prod-db"/g
```

**Good** (use JSON mode):
```json
{
  "$.database.host": "prod-db"
}
```

### Pitfall 5: Partial Replacements

**Problem**:
```bash
s/dev/prod/g
```

Transforms "developer" → "prodeveloper"

**Solution**:
```bash
s/\bdev\b/prod/g  # Word boundaries
```

### Pitfall 6: Regex Catastrophic Backtracking (ReDoS)

**Problem**:
```bash
s/(a+)+b/replacement/g
```

This can cause exponential time complexity.

**Solution**: Use simpler patterns or test with long inputs.

Secrets Replicator validates patterns for ReDoS vulnerabilities.

---

## Advanced Techniques

### Technique 1: Conditional Replacements

Only replace in specific contexts:

```sed
# Replace "port" only in database context
s/"database":\s*{[^}]*"port":\s*"3306"/"database": {... "port": "3307"/g
```

### Technique 2: Backreferences

Capture and reuse parts of the match:

```sed
# Swap first two words
s/([a-z]+)\s+([a-z]+)/\2 \1/g

# Extract and reformat
s/postgres:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/(\w+)/Host:\3 Port:\4 DB:\5/g
```

### Technique 3: Multi-Pass Transformations

Apply transformations in stages:

```bash
# Pass 1: Environment name
s/dev/prod/g

# Pass 2: Region (after environment to avoid conflicts)
s/us-east-1/us-west-2/g

# Pass 3: Specific overrides
s/prod-special-case/custom-value/g
```

### Technique 4: Combining Sed and JSON Modes

Use both modes for different parts:

**Approach 1**: Use Sed for coarse-grained, JSON for fine-grained

1. Deploy with Sed mode to replace all "dev" with "prod"
2. Create second replicator with JSON mode for specific field overrides

**Approach 2**: Pre-transform with Sed, load into JSON mode

Not directly supported, but achievable with custom Lambda layer.

### Technique 5: Dynamic Transformations

Use multiple transformation secrets for different scenarios:

**Pattern**: Create environment-specific transformation secrets

```bash
# Create dev-to-qa transformation
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/dev-to-qa \
  --secret-string 's/dev/qa/g'

# Create qa-to-prod transformation
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/qa-to-prod \
  --secret-string 's/qa/prod/g'

# Tag secrets based on promotion path
aws secretsmanager tag-resource \
  --secret-id my-dev-secret \
  --tags Key=SecretsReplicator:TransformSecretName,Value=dev-to-qa

aws secretsmanager tag-resource \
  --secret-id my-qa-secret \
  --tags Key=SecretsReplicator:TransformSecretName,Value=qa-to-prod
```

This allows different replication flows with appropriate transformations.

---

## Examples Repository

### Example 1: Basic Dev to Prod

**File**: `examples/sedfile-basic.sed`

```sed
# Environment
s/dev/prod/g
s/development/production/g

# Hostnames
s/\.dev\././g

# Protocols
s/http:/https:/g
```

### Example 2: AWS Region Swap

**File**: `examples/sedfile-regions.sed`

```sed
# RDS
s/\.us-east-1\.rds\./\.us-west-2.rds./g

# S3
s/-us-east-1/-us-west-2/g

# DynamoDB
s/:dynamodb:us-east-1:/:dynamodb:us-west-2:/g
```

### Example 3: JSON Environment Promotion

**File**: `examples/sedfile-json.json`

```json
{
  "$.environment": "production",
  "$.api_endpoint": "https://api.example.com",
  "$.database.host": "prod-db.example.com",
  "$.logging.level": "INFO"
}
```

---

## Troubleshooting Transformations

### Problem: Transformation Not Applied

**Check 1**: Verify transformation mode
```bash
aws lambda get-function-configuration \
  --function-name secrets-replicator \
  --query 'Environment.Variables.TRANSFORM_MODE'
```

**Check 2**: Check CloudWatch logs for transformation details
```bash
aws logs tail /aws/lambda/secrets-replicator-replicator \
  --filter-pattern "transformation"
```

**Check 3**: Test pattern locally
```bash
echo "test-value" | sed 's/pattern/replacement/g'
```

### Problem: Sed Pattern Errors

**Check**: Validate sed syntax
```bash
echo "test" | sed 's/(/)/g'
# Error: unterminated `s' command

# Fix: Escape parentheses
echo "test" | sed 's/\(/\)/g'
```

### Problem: JSON Path Not Found

**Check**: Validate JSONPath
```python
from jsonpath_ng import parse
import json

secret = json.loads('{"database":{"host":"example.com"}}')
path = parse('$.database.port')
matches = path.find(secret)

if not matches:
    print("Path not found!")
```

---

## Further Reading

- [GNU Sed Manual](https://www.gnu.org/software/sed/manual/sed.html)
- [JSONPath Specification](https://goessner.net/articles/JsonPath/)
- [Regular Expressions Tutorial](https://www.regular-expressions.info/)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)

---

**Last Updated**: 2025-11-01
**Version**: 1.0.0
**Maintainer**: Devopspolis
