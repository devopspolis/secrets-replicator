# Secrets Replicator

[![CI](https://github.com/devopspolis/secrets-replicator/workflows/CI/badge.svg)](https://github.com/devopspolis/secrets-replicator/actions)
[![Coverage](https://codecov.io/gh/devopspolis/secrets-replicator/branch/main/graph/badge.svg)](https://codecov.io/gh/devopspolis/secrets-replicator)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![AWS SAM](https://img.shields.io/badge/AWS-SAM-orange.svg)](https://aws.amazon.com/serverless/sam/)

**Event-driven AWS Secrets Manager replication with transformation across regions and accounts**

Fill the gap in AWS's native secret replication by transforming secret values during replication (e.g., changing `us-east-1` to `us-west-2` in connection strings).

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Use Cases](#use-cases)
- [Transformations](#transformations)
- [Monitoring](#monitoring)
- [Security](#security)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [FAQ](#faq)
- [Resources](#resources)

---

## Overview

**Secrets Replicator** is a production-ready AWS Lambda function that automatically replicates AWS Secrets Manager secrets across regions and accounts with configurable value transformations.

### Why Secrets Replicator?

AWS Secrets Manager supports [native replication](https://docs.aws.amazon.com/secretsmanager/latest/userguide/create-manage-multi-region-secrets.html), but **cannot modify secret values** during replication. This creates challenges for:

- **Disaster Recovery**: Connection strings need region-specific endpoints
- **Multi-Region Applications**: Database hosts differ by region
- **Environment Promotion**: Dev secrets need different values in prod
- **Cross-Account Deployments**: Account-specific ARNs and resource IDs

**Secrets Replicator solves this** by transforming secret values during replication using sed-style regex or JSON field mappings.

### Value Proposition

| Feature | AWS Native Replication | Secrets Replicator |
|---------|------------------------|-------------------|
| Cross-region replication | ✅ Yes | ✅ Yes |
| Cross-account replication | ❌ No | ✅ Yes |
| Transform values | ❌ No | ✅ Yes |
| Event-driven | ✅ Yes | ✅ Yes |
| KMS encryption | ✅ Yes | ✅ Yes |
| Cost | Free | ~$2.22/month |

---

## Features

### Core Capabilities

- ✅ **Event-Driven Replication**: Automatic replication triggered by Secrets Manager updates via EventBridge
- ✅ **Cross-Region**: Replicate to any AWS region with region-specific transformations
- ✅ **Cross-Account**: Replicate to different AWS accounts with proper IAM controls and External ID
- ✅ **Value Transformation**:
  - Sed-style regex replacements (e.g., `s/dev/prod/g`)
  - JSON field mappings with JSONPath
  - Region swapping (all AWS services)
  - Environment promotion (dev → staging → prod)
- ✅ **Binary Secret Detection**: Returns HTTP 501 for binary secrets (not currently supported)
- ✅ **Secret Size Validation**: Configurable max size (default 64KB)

### Monitoring & Resilience

- ✅ **CloudWatch Metrics**: Custom metrics for success, failure, duration, throttling
- ✅ **CloudWatch Alarms**: SNS notifications for failures, throttling, performance degradation
- ✅ **Automatic Retries**: Exponential backoff with jitter (up to 5 attempts)
- ✅ **Dead Letter Queue**: Failed events sent to SQS DLQ for investigation
- ✅ **Structured Logging**: JSON logs with context (no secret leakage)

### Security

- ✅ **No Secret Leakage**: Secrets never logged in plaintext (masked in all logs)
- ✅ **KMS Encryption**: Supports customer-managed KMS keys for encryption
- ✅ **IAM Least Privilege**: Minimal permissions with resource-scoped policies
- ✅ **External ID**: Cross-account trust policy with External ID for security
- ✅ **CloudTrail Integration**: Full audit trail of all operations

### Performance

- ✅ **Fast Execution**: 200-500ms warm execution, 2-3s cold start
- ✅ **Efficient Transformations**: 10-30ms transformation time
- ✅ **Transformation Secrets**: Cached in Lambda memory for fast access
- ✅ **Parallel Processing**: Handles concurrent secret updates

### Cost

- **Lambda**: ~$0.62/month (1000 replications)
- **EventBridge**: ~$1.00/month
- **CloudWatch**: ~$0.60/month (metrics + alarms)
- **Total**: ~**$2.22/month** (excludes Secrets Manager storage costs)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AWS Account A (Source)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐                                                  │
│  │ Secrets Manager  │ PutSecretValue                                   │
│  │  (Source Secret) │────────┐                                         │
│  └──────────────────┘        │                                         │
│                              ▼                                          │
│                   ┌─────────────────────┐                              │
│                   │    EventBridge      │                              │
│                   │  (Secret Changed)   │                              │
│                   └──────────┬──────────┘                              │
│                              │                                          │
│                              ▼                                          │
│         ┌──────────────────────────────────────────────────┐           │
│         │   Lambda Function                                │           │
│         │   (Secrets Replicator)                           │           │
│         ├──────────────────────────────────────────────────┤           │
│         │ 1. Parse EventBridge event                       │           │
│         │ 2. Get source secret tags & transformation name  │           │
│         │ 3. Load transformation rules (from secret)       │           │
│         │ 4. Get source secret value                       │           │
│         │ 5. Apply transformations                         │           │
│         │ 6. Assume destination role (if needed)           │           │
│         │ 7. Put transformed secret                        │           │
│         │ 8. Publish metrics & logs                        │           │
│         └────────┬────────────────────┬────────────────────┘           │
│                  │                    │                                 │
│                  ▼                    ▼                                 │
│        ┌──────────────┐    ┌──────────────────┐                        │
│        │  CloudWatch  │    │  SQS DLQ         │                        │
│        │  Metrics     │    │  (Failed Events) │                        │
│        └──────────────┘    └──────────────────┘                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ AssumeRole (with External ID)
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      AWS Account B (Destination)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                   ┌──────────────────────┐                             │
│                   │  IAM Role            │                             │
│                   │  (Trust Policy +     │                             │
│                   │   External ID)       │                             │
│                   └──────────┬───────────┘                             │
│                              │                                          │
│                              ▼                                          │
│                   ┌──────────────────────┐                             │
│                   │  Secrets Manager     │                             │
│                   │  (Destination Secret)│                             │
│                   │  [Transformed Value] │                             │
│                   └──────────────────────┘                             │
│                              │                                          │
│                              ▼                                          │
│                   ┌──────────────────────┐                             │
│                   │  KMS Key             │                             │
│                   │  (Customer Managed)  │                             │
│                   └──────────────────────┘                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Flow

1. **Secret Updated**: User updates a secret in AWS Secrets Manager (source)
2. **EventBridge Trigger**: Secrets Manager emits `PutSecretValue` event to EventBridge
3. **Lambda Invocation**: EventBridge rule triggers Lambda function
4. **Event Parsing**: Lambda parses event to extract secret ARN and metadata
5. **Secret Retrieval**: Lambda calls `GetSecretValue` to retrieve source secret
6. **Transformation**: Lambda applies sed or JSON transformations to secret value
7. **Cross-Account Access** (optional): Lambda assumes role in destination account via STS
8. **Secret Replication**: Lambda calls `PutSecretValue` (or `CreateSecret`) in destination
9. **Metrics & Logging**: Lambda publishes CloudWatch metrics and structured logs

---

## Quick Start

### Prerequisites

- AWS CLI configured with credentials
- SAM CLI installed ([Installation guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
- Python 3.12+
- Two secrets: source and destination (can be in different regions/accounts)

### 5-Minute Setup

```bash
# 1. Clone repository
git clone https://github.com/devopspolis/secrets-replicator.git
cd secrets-replicator

# 2. Deploy with SAM
sam build
sam deploy --guided

# 3. Create transformation secret:
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --secret-string 's/us-east-1/us-west-2/g'

# 4. Tag source secret to use transformation:
aws secretsmanager tag-resource \
  --secret-id my-source-secret \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap

# Note: You can chain multiple transformations with comma-separated values:
# --tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap,env-promotion"

# 5. Test by updating source secret
aws secretsmanager put-secret-value \
  --secret-id my-source-secret \
  --secret-string '{"host":"db.us-east-1.amazonaws.com","port":"5432"}'

# 5. Verify destination secret (after ~2-5 seconds)
aws secretsmanager get-secret-value \
  --secret-id my-destination-secret \
  --region us-west-2 \
  --query SecretString \
  --output text

# Expected output:
# {"host":"db.us-west-2.amazonaws.com","port":"5432"}
```

---

## Installation

### Option 1: AWS Serverless Application Repository (Recommended)

**Coming soon - Phase 8**

Deploy directly from SAR with one click:

1. Go to [AWS Serverless Application Repository](https://serverlessrepo.aws.amazon.com/)
2. Search for "secrets-replicator"
3. Click "Deploy"
4. Configure parameters
5. Click "Deploy" again

### Option 2: SAM CLI

```bash
# Build
sam build --cached

# Deploy (first time)
sam deploy --guided

# Deploy (subsequent)
sam deploy --config-env dev
```

### Option 3: Manual CloudFormation

```bash
# Package
sam package \
  --template-file template.yaml \
  --output-template-file packaged.yaml \
  --s3-bucket my-deployment-bucket

# Deploy
sam deploy \
  --template-file packaged.yaml \
  --stack-name secrets-replicator \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    SourceSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret \
    DestSecretName=my-destination-secret \
    DestRegion=us-west-2
```

---

## Configuration

### Environment Variables

Configure via SAM template parameters or directly in Lambda:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEST_REGION` | ✅ Yes | - | Destination AWS region |
| `DEST_SECRET_NAME` | No | *(same as source)* | Override destination secret name (leave empty to use source name) |
| `TRANSFORM_MODE` | No | `auto` | Transformation mode: `auto` (detect), `sed`, or `json` |
| `TRANSFORMATION_SECRET_PREFIX` | No | `secrets-replicator/transformations/` | Prefix for transformation secrets (excluded from replication) |
| `DEST_ACCOUNT_ROLE_ARN` | No | - | IAM role ARN in destination account (cross-account) |
| `KMS_KEY_ID` | No | - | KMS key ID for destination secret encryption |
| `MAX_SECRET_SIZE` | No | `65536` | Maximum secret size in bytes (64KB default) |
| `ENABLE_METRICS` | No | `true` | Enable CloudWatch custom metrics |
| `LOG_LEVEL` | No | `INFO` | Log level: DEBUG, INFO, WARN, ERROR |
| `TIMEOUT_SECONDS` | No | `5` | Regex timeout in seconds |

**Transformation Secrets**: Source secrets must be tagged with `SecretsReplicator:TransformSecretName` to specify which transformation secret contains the sed or JSON transformation rules.

### SAM Template Parameters

Configure when deploying with SAM:

```yaml
# samconfig.toml
[default.deploy.parameters]
parameter_overrides = [
  "DestinationRegion=us-west-2",
  # "TransformMode=auto",  # Optional - auto-detects by default
  "EnableMetrics=true"
]
```

**Note**: Transformation rules are stored in transformation secrets (see [Transformations](#transformations) section below), not in SAM parameters.

---

## Use Cases

### Use Case 1: Cross-Region Disaster Recovery

**Scenario**: Replicate production database secret from `us-east-1` to `us-west-2` with region-specific endpoints.

**Source Secret** (`us-east-1`):
```json
{
  "host": "prod-db.us-east-1.rds.amazonaws.com",
  "port": "5432",
  "username": "dbadmin",
  "password": "SuperSecretPassword123",
  "database": "production"
}
```

**Configuration**:

1. Create transformation secret:
```bash
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap-sed \
  --description "Sed transformation for region swapping" \
  --secret-string 's/us-east-1/us-west-2/g'
```

2. Tag source secret with transformation name:
```bash
aws secretsmanager tag-resource \
  --secret-id prod-db-credentials \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap-sed
```

3. Lambda environment variables:
```bash
DEST_REGION=us-west-2
# TRANSFORM_MODE=auto  # Optional - auto-detects sed format
```

**Destination Secret** (`us-west-2`):
```json
{
  "host": "prod-db.us-west-2.rds.amazonaws.com",
  "port": "5432",
  "username": "dbadmin",
  "password": "SuperSecretPassword123",
  "database": "production"
}
```

**Result**: Automatic failover to `us-west-2` with correct database endpoint.

---

### Use Case 2: Cross-Account Organizational Deployment

**Scenario**: Replicate secrets from central security account to application account.

**Source Account**: `111111111111` (Security Account)
**Destination Account**: `222222222222` (Application Account)

**IAM Setup** (Destination Account):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/secrets-replicator-LambdaExecutionRole"
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

**Setup**:
```bash
# 1. Create transformation secret for account ID swap
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/account-swap \
  --secret-string 's/111111111111/222222222222/g'

# 2. Tag source secret to use transformation
aws secretsmanager tag-resource \
  --secret-id app-credentials \
  --tags Key=SecretsReplicator:TransformSecretName,Value=account-swap
```

**Configuration**:
```bash
SOURCE_SECRET_ARN=arn:aws:secretsmanager:us-east-1:111111111111:secret:app-credentials
DEST_SECRET_NAME=app-credentials
DEST_REGION=us-east-1
DEST_ACCOUNT_ROLE_ARN=arn:aws:iam::222222222222:role/SecretsReplicatorDestRole
DEST_ROLE_EXTERNAL_ID=my-secure-external-id-12345
# TRANSFORM_MODE=auto  # Optional - auto-detects sed format
```

**Result**: Secrets replicated to application account with account-specific ARNs.

---

### Use Case 3: Environment Promotion (Dev → Prod)

**Scenario**: Promote secrets from development to production with environment-specific values.

**Source Secret** (Dev):
```json
{
  "api_endpoint": "https://api.dev.example.com",
  "database": "dev-database",
  "log_level": "DEBUG",
  "cache_ttl": "60"
}
```

**Transformation** (JSON mapping):
```json
{
  "$.api_endpoint": "https://api.prod.example.com",
  "$.database": "prod-database",
  "$.log_level": "INFO",
  "$.cache_ttl": "3600"
}
```

**Setup**:
```bash
# 1. Create transformation secret with JSON mapping
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/dev-to-prod \
  --secret-string '{"$.api_endpoint": "https://api.prod.example.com", "$.database": "prod-database", "$.log_level": "INFO", "$.cache_ttl": "3600"}'

# 2. Tag source secret to use transformation
aws secretsmanager tag-resource \
  --secret-id app-config-dev \
  --tags Key=SecretsReplicator:TransformSecretName,Value=dev-to-prod
```

**Configuration**:
```bash
SOURCE_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:app-config-dev
DEST_SECRET_NAME=app-config-prod
DEST_REGION=us-east-1
# TRANSFORM_MODE=auto  # Optional - can explicitly set to 'json' if needed
```

**Destination Secret** (Prod):
```json
{
  "api_endpoint": "https://api.prod.example.com",
  "database": "prod-database",
  "log_level": "INFO",
  "cache_ttl": "3600"
}
```

**Result**: Automated promotion with correct production values.

---

### Use Case 4: Multi-Region Application with Complex Transformations

**Scenario**: Replicate API keys and service endpoints for multi-region application deployment.

**Source Secret** (`us-east-1`):
```json
{
  "primary_db": "postgres://db.us-east-1.rds.amazonaws.com:5432/app",
  "redis_endpoint": "redis.us-east-1.cache.amazonaws.com:6379",
  "s3_bucket": "arn:aws:s3:::app-data-us-east-1",
  "sqs_queue": "https://sqs.us-east-1.amazonaws.com/123456789012/app-queue",
  "api_key": "ak_east_1234567890",
  "environment": "us-east-1"
}
```

**Configuration**:

1. Create transformation secret with comprehensive region swapping rules:
```bash
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap-comprehensive \
  --description "Comprehensive region swap transformations" \
  --secret-string '# Swap regions
s/us-east-1/us-west-2/g

# Update API key
s/ak_east_/ak_west_/g

# ARN transformations
s/arn:aws:s3:::app-data-us-east-1/arn:aws:s3:::app-data-us-west-2/g'
```

2. Tag source secret:
```bash
aws secretsmanager tag-resource \
  --secret-id app-config \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap-comprehensive
```

3. Lambda environment variables:
```bash
DEST_REGION=us-west-2
# TRANSFORM_MODE=auto  # Optional - auto-detects sed format
```

**Result**: Complete multi-region deployment with region-specific endpoints.

---

## Transformations

### Transformation Secrets

Transformation rules (sed scripts or JSON mappings) are stored in **transformation secrets** in AWS Secrets Manager with the prefix `secrets-replicator/transformations/`.

**Benefits**:
- ✅ Version control via Secrets Manager versioning
- ✅ Secure storage with encryption
- ✅ No deployment required to update transformations
- ✅ Audit trail via CloudTrail
- ✅ Namespace isolation (transformation secrets excluded from replication)

**Setup Process**:
1. Create transformation secret with prefix `secrets-replicator/transformations/`
2. Store sed script or JSON mapping in secret value
3. Tag source secrets with `SecretsReplicator:TransformSecretName` pointing to transformation secret name (without prefix)

### Sed Transformations

Use sed-style regex for find/replace transformations.

#### Basic Syntax

```bash
# Simple replacement (first occurrence)
s/old/new/

# Global replacement (all occurrences)
s/old/new/g

# Case-insensitive replacement
s/old/new/gi

# Delete lines matching pattern
/pattern/d
```

#### Examples

**Environment Change**:
```bash
# Create transformation secret
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/env-to-prod \
  --secret-string 's/dev/prod/g'

# Tag source secret
aws secretsmanager tag-resource \
  --secret-id my-app-config \
  --tags Key=SecretsReplicator:TransformSecretName,Value=env-to-prod
```

**Region Swap**:
```bash
# Create transformation secret
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --secret-string 's/us-east-1/us-west-2/g'

# Tag source secret
aws secretsmanager tag-resource \
  --secret-id db-credentials \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap
```

**Complex Multi-Line Transformations**:
```bash
# Create transformation secret with multi-line sed script
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/comprehensive-transform \
  --secret-string '# Change environment
s/dev/prod/g
s/staging/prod/g

# Update hostnames
s/dev-db\.example\.com/prod-db.example.com/g
s/dev-api\.example\.com/prod-api.example.com/g

# Change ports
s/:3000/:8080/g

# Case-insensitive domain swap
s/example\.local/example.com/gi'

# Tag source secret
aws secretsmanager tag-resource \
  --secret-id app-secret \
  --tags Key=SecretsReplicator:TransformSecretName,Value=comprehensive-transform
```

### JSON Transformations

Use JSONPath expressions to map specific fields.

#### Syntax

```json
{
  "$.path.to.field": "new value",
  "$.another.field": "replacement"
}
```

#### Examples

**Simple Field Replacement**:
```json
{
  "$.environment": "production",
  "$.api_endpoint": "https://api.prod.example.com"
}
```

**Nested Field Replacement**:
```json
{
  "$.database.host": "prod-db.example.com",
  "$.database.port": "5432",
  "$.cache.redis.endpoint": "redis.prod.example.com"
}
```

**Array Element Replacement**:
```json
{
  "$.servers[0].host": "server1.prod.example.com",
  "$.servers[1].host": "server2.prod.example.com"
}
```

### Transformation Chains

Apply multiple transformations sequentially by specifying a **comma-separated list** in the tag:

```bash
# Apply transformations in order: region-swap → env-promotion → scale-up
aws secretsmanager tag-resource \
  --secret-id my-app-config \
  --tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap,env-promotion,scale-up"
```

**Execution Flow**:
```text
Original Secret → region-swap → env-promotion → scale-up → Destination Secret
```

#### Chain Example 1: Region + Environment

**Scenario**: Replicate from us-east-1 dev to us-west-2 prod

```bash
# Create region transformation
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-east-to-west \
  --secret-string 's/us-east-1/us-west-2/g'

# Create environment transformation
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
```text
Original:  {"host": "dev-db.us-east-1.rds.amazonaws.com", "log_level": "DEBUG"}
Step 1:    {"host": "dev-db.us-west-2.rds.amazonaws.com", "log_level": "DEBUG"}
Final:     {"host": "prod-db.us-west-2.rds.amazonaws.com", "log_level": "INFO"}
```

#### Chain Example 2: Mixed Sed + JSON

**Scenario**: Apply broad regex changes, then precise JSON field updates

```bash
# Create sed transformation
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --secret-string 's/us-east-1/us-west-2/g'

# Create JSON transformation (auto-detected by format)
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/config-overrides \
  --secret-string '{
  "transformations": [
    {"path": "$.max_connections", "find": "100", "replace": "500"},
    {"path": "$.timeout_seconds", "find": "30", "replace": "60"}
  ]
}'

# Tag source secret with mixed chain
aws secretsmanager tag-resource \
  --secret-id app-config \
  --tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap,config-overrides"
```

**Auto-Detection**: Each transformation in the chain is automatically detected as sed or JSON based on content format.

#### Chain Example 3: Whitespace in Tag Value

Whitespace around commas is automatically trimmed:

```bash
# These are equivalent (quotes required for CLI):
--tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap,env-promotion,scale-up"
--tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap, env-promotion, scale-up"
--tags "Key=SecretsReplicator:TransformSecretName,Value=region-swap , env-promotion , scale-up"
```

#### Chain Best Practices

1. **Always quote tag values with commas**: Required for AWS CLI parsing
   ```bash
   # ✅ Correct
   --tags "Key=SecretsReplicator:TransformSecretName,Value=t1,t2,t3"

   # ❌ Incorrect - CLI will fail
   --tags Key=SecretsReplicator:TransformSecretName,Value=t1,t2,t3
   ```

2. **Order matters**: Transformations apply left-to-right
3. **Keep chains short**: 2-3 transformations recommended
4. **Test incrementally**: Test each transformation alone, then test the chain
5. **Use descriptive names**: `Value=region-east-west,env-dev-prod` is self-documenting

See [docs/transformations.md](docs/transformations.md) for comprehensive chain examples and use cases.

### Transformation Best Practices

1. **Test transformations locally** before deploying:
   ```bash
   # Test sed script
   echo '{"host":"db.us-east-1.amazonaws.com"}' | sed 's/us-east-1/us-west-2/g'
   ```

2. **Use descriptive transformation secret names**: Makes maintenance easier
   - Good: `secrets-replicator/transformations/db-region-swap-east-to-west`
   - Bad: `secrets-replicator/transformations/transform1`

3. **Version your transformations**: Use Secrets Manager versioning for rollback capability
   ```bash
   # Update transformation secret (creates new version)
   aws secretsmanager update-secret \
     --secret-id secrets-replicator/transformations/region-swap \
     --secret-string 's/us-east-1/eu-west-1/g'
   ```

4. **Avoid overly broad patterns**: Be specific to prevent unintended replacements

5. **Document transformations**: Include comments in sedfiles

---

## Monitoring

### CloudWatch Metrics

Custom metrics published to namespace `SecretsReplicator`:

| Metric | Unit | Description |
|--------|------|-------------|
| `ReplicationSuccess` | Count | Successful replications |
| `ReplicationFailure` | Count | Failed replications |
| `ReplicationDuration` | Milliseconds | Time to replicate (success) |
| `FailureDuration` | Milliseconds | Time to fail |
| `SecretSize` | Bytes | Size of secret replicated |
| `TransformationDuration` | Milliseconds | Time to transform secret |
| `TransformationInputSize` | Bytes | Input size before transformation |
| `TransformationOutputSize` | Bytes | Output size after transformation |
| `TransformationRulesCount` | Count | Number of transformation rules applied |
| `RetryAttempt` | Count | Retry attempts |
| `ThrottlingEvent` | Count | AWS API throttling events |

**Dimensions**:
- `SourceRegion`: Source AWS region
- `DestRegion`: Destination AWS region
- `TransformMode`: `sed` or `json`
- `ErrorType`: Error classification (failures only)

### CloudWatch Alarms

Three alarms configured by default:

**1. ReplicationFailureAlarm**
- **Condition**: ≥5 failures in 5 minutes
- **Action**: SNS notification
- **Use**: Detect replication issues

**2. ThrottlingAlarm**
- **Condition**: ≥10 throttling events in 5 minutes
- **Action**: SNS notification
- **Use**: Detect API rate limiting

**3. HighDurationAlarm**
- **Condition**: Average duration ≥5000ms
- **Action**: SNS notification
- **Use**: Detect performance degradation

### CloudWatch Logs

Structured JSON logs with context:

```json
{
  "timestamp": "2025-11-01T12:34:56.789Z",
  "level": "INFO",
  "message": "Secret replicated successfully",
  "source_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret",
  "dest_name": "my-destination-secret",
  "dest_region": "us-west-2",
  "transform_mode": "sed",
  "duration_ms": 234,
  "secret_size": 1024
}
```

**Secrets are NEVER logged in plaintext** - all secret values are masked.

### Monitoring Dashboard (Coming in Phase 8)

Create a CloudWatch dashboard to visualize:
- Success/failure rates
- Replication duration trends
- Throttling events
- Error types distribution

---

## Security

### IAM Permissions

**Minimum Lambda Execution Role** (same account, same region):

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
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:123456789012:secret:dest-secret-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:us-east-1:123456789012:key/source-key-id",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.us-east-1.amazonaws.com"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:us-west-2:123456789012:key/dest-key-id",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.us-west-2.amazonaws.com"
        }
      }
    }
  ]
}
```

**Cross-Account Destination Role**:

See [docs/iam-policies.md](docs/iam-policies.md) for complete IAM policy templates.

### Security Best Practices

1. **Use External ID**: Always configure External ID for cross-account access
2. **KMS Encryption**: Use customer-managed KMS keys for secrets
3. **Least Privilege**: Scope IAM permissions to specific secret ARNs
4. **Audit Trail**: Enable CloudTrail for all Secrets Manager operations
5. **Secrets Rotation**: Use AWS Secrets Manager rotation in source account
6. **No Hardcoded Secrets**: All secrets loaded from Secrets Manager or environment
7. **ReDoS Prevention**: Validate sed patterns for catastrophic backtracking

### Security Validations

All security validations are tested in Phase 6:
- ✅ No secret leakage in logs
- ✅ KMS encryption/decryption
- ✅ IAM permission enforcement
- ✅ External ID validation
- ✅ ReDoS pattern detection

---

## Performance

### Benchmarks

Tested with 290 unit tests and 15+ performance tests (92.39% coverage):

#### Execution Time

| Scenario | Cold Start | Warm Execution |
|----------|-----------|----------------|
| Same-region, small secret (1KB) | 2.0-2.5s | 200-300ms |
| Same-region, medium secret (10KB) | 2.2-2.8s | 250-400ms |
| Same-region, large secret (60KB) | 2.5-3.5s | 400-600ms |
| Cross-region, small secret | 2.5-3.5s | 500-800ms |
| Cross-region, medium secret | 3.0-4.0s | 700-1000ms |
| Cross-region, large secret | 3.5-5.0s | 900-1500ms |
| Cross-account, cross-region | 3.0-4.5s | 800-1200ms |

#### Transformation Performance

| Transform Type | Rules/Mappings | Time | Throughput |
|----------------|----------------|------|------------|
| Sed (simple) | 1 rule | 5-10ms | 100-200 ops/s |
| Sed (complex) | 10 rules | 15-25ms | 40-65 ops/s |
| JSON (simple) | 2 mappings | 8-12ms | 80-125 ops/s |
| JSON (complex) | 10 mappings | 20-30ms | 33-50 ops/s |

#### Retry Performance

With exponential backoff (transient errors):

| Attempt | Wait Time | Total Time |
|---------|-----------|------------|
| 1 | 0ms | 0ms |
| 2 | ~2s | ~2s |
| 3 | ~4s | ~6s |
| 4 | ~8s | ~14s |
| 5 | ~16s | ~30s |
| 6 (max) | ~32s | ~62s |

### Performance Optimization Tips

1. **Use warm containers**: Keep Lambda warm with CloudWatch Events (ping every 5 min)
2. **Reuse transformation secrets**: Transformation secrets are cached in Lambda memory across invocations
3. **Minimize secret size**: Smaller secrets replicate faster
4. **Use provisioned concurrency**: For high-frequency replications
5. **Batch updates**: Update multiple fields in a single secret update
6. **Share transformation secrets**: Multiple source secrets can reference the same transformation secret

---

## Troubleshooting

### Common Issues

#### Issue 1: Replication Fails with AccessDenied

**Symptoms**:
```
ERROR: AccessDenied - User is not authorized to perform secretsmanager:GetSecretValue
```

**Causes**:
- Lambda execution role lacks permissions
- KMS key policy doesn't allow Lambda role
- Cross-account role trust policy incorrect

**Solutions**:
1. Check Lambda execution role has `secretsmanager:GetSecretValue` permission
2. Verify KMS key policy allows Lambda role to decrypt
3. For cross-account, verify trust policy has correct External ID

**Related**: See [docs/iam-policies.md](docs/iam-policies.md)

---

#### Issue 2: Transformation Not Applied

**Symptoms**:
- Destination secret has same value as source
- No errors in logs

**Causes**:
- Incorrect sed pattern
- Wrong `TRANSFORM_MODE` (if explicitly set)
- Source secret missing `SecretsReplicator:TransformSecretName` tag
- Transformation secret not found
- Transformation secret name incorrect (includes prefix when it shouldn't)
- Auto-detection failed to detect correct format

**Solutions**:
1. Test sed pattern locally: `echo "value" | sed 's/old/new/g'`
2. Check CloudWatch logs for transformation details
3. Verify source secret has correct tag:
   ```bash
   aws secretsmanager describe-secret --secret-id my-secret --query 'Tags'
   ```
4. Verify transformation secret exists:
   ```bash
   aws secretsmanager get-secret-value --secret-id secrets-replicator/transformations/my-transform
   ```
5. Ensure tag value is just the name (NOT the full path):
   - ✅ Good: `Value=region-swap`
   - ❌ Bad: `Value=secrets-replicator/transformations/region-swap`

---

#### Issue 3: Secret Not Replicating

**Symptoms**:
- Source secret updated but destination unchanged
- No Lambda invocations in CloudWatch

**Causes**:
- EventBridge rule disabled
- EventBridge rule pattern incorrect
- Source secret ARN doesn't match

**Solutions**:
1. Check EventBridge rule is `ENABLED`:
   ```bash
   aws events describe-rule --name secrets-replicator-SecretChangeRule
   ```
2. Verify event pattern matches source secret ARN
3. Check Lambda has EventBridge trigger configured

---

#### Issue 4: High Duration / Timeouts

**Symptoms**:
- Lambda times out after 30 seconds
- HighDurationAlarm triggered

**Causes**:
- Large secret size
- Complex transformations
- Network latency to destination region
- Cold start overhead

**Solutions**:
1. Increase Lambda timeout (default: 30s, max: 15min)
2. Increase Lambda memory (more memory = more CPU)
3. Use provisioned concurrency for warm containers
4. Optimize sed patterns (reduce rules)

---

### Debugging

**Enable Debug Logging**:
```bash
# Set environment variable
LOG_LEVEL=DEBUG

# Check logs
aws logs tail /aws/lambda/secrets-replicator-prod-replicator --follow
```

**Check Metrics**:
```bash
# Get failure count
aws cloudwatch get-metric-statistics \
  --namespace SecretsReplicator \
  --metric-name ReplicationFailure \
  --start-time 2025-11-01T00:00:00Z \
  --end-time 2025-11-01T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

**Inspect DLQ**:
```bash
# Receive message from DLQ
aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/secrets-replicator-dlq
```

For more troubleshooting tips, see [docs/troubleshooting.md](docs/troubleshooting.md).

---

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone repository
git clone https://github.com/devopspolis/secrets-replicator.git
cd secrets-replicator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/unit/ -v --cov=src --cov-report=html

# Run code quality checks
black --check src/ tests/
pylint src/ --fail-under=8.0
mypy src/ --ignore-missing-imports
```

### Running Pre-Commit Hooks

```bash
# Run all hooks
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files
```

### Submitting Changes

1. Fork the repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Make changes and commit (pre-commit hooks will run)
4. Push to your fork: `git push origin feature/my-feature`
5. Create Pull Request

See [docs/cicd.md](docs/cicd.md) for CI/CD workflow details.

---

## FAQ

### Q: Does this support binary secrets?

**A**: Not currently. Binary secrets return HTTP 501. Use AWS native replication for binary secrets (no transformation needed).

### Q: What's the maximum secret size?

**A**: Default 64KB (configurable via `MAX_SECRET_SIZE`). AWS Secrets Manager limit is 64KB.

### Q: Can I replicate to multiple destinations?

**A**: Not in a single Lambda invocation. Deploy multiple stacks for multiple destinations.

### Q: Does this work with secret rotation?

**A**: Yes! Rotation triggers `PutSecretValue` events, which trigger replication.

### Q: Can I transform only specific fields in JSON?

**A**: Yes, use JSON transform mode with JSONPath mappings.

### Q: What happens if transformation fails?

**A**: Event is sent to Dead Letter Queue (DLQ) and failure metric is published.

### Q: Can I use this in GovCloud or China regions?

**A**: Yes, but update service endpoints in code for GovCloud/China partitions.

### Q: How do I rollback a bad transformation?

**A**: Update the transformation secret with corrected rules, or use `AWSPREVIOUS` version stage to rollback:
```bash
# Option 1: Update transformation secret
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/transformations/my-transform \
  --secret-string 's/corrected/pattern/g'

# Option 2: Rollback to previous version
aws secretsmanager update-secret-version-stage \
  --secret-id secrets-replicator/transformations/my-transform \
  --version-stage AWSCURRENT \
  --move-to-version-id <previous-version-id>
```
Then trigger replication by updating the source secret.

### Q: Is there a Terraform version?

**A**: Not yet. SAM template can be converted to Terraform using `sam2tf` or similar tools.

### Q: Can I get notified when replication fails?

**A**: Yes, CloudWatch alarms send SNS notifications on failures. Configure SNS topic ARN in SAM template.

---

## Resources

### Documentation

- [Architecture](ARCHITECTURE.md) - Technical architecture and design
- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Development roadmap
- [IAM Policies](docs/iam-policies.md) - IAM policy templates
- [Transformations](docs/transformations.md) - Transformation examples
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [CI/CD Guide](docs/cicd.md) - GitHub Actions workflows
- [Testing Guide](docs/testing.md) - Testing strategy and benchmarks
- [Phase Summaries](PHASE7_SUMMARY.md) - Implementation phase details

### AWS Resources

- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [AWS EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/what-is-amazon-eventbridge.html)
- [AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
- [AWS SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/overview.html)

### Related Projects

- [AWS Native Multi-Region Secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/create-manage-multi-region-secrets.html) - AWS native replication (no transformation)
- [Secrets Manager Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html) - Automatic secret rotation

### Support

- **Issues**: [GitHub Issues](https://github.com/devopspolis/secrets-replicator/issues)
- **Discussions**: [GitHub Discussions](https://github.com/devopspolis/secrets-replicator/discussions)
- **Email**: devopspolis@example.com

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

---

## Acknowledgments

- AWS Secrets Manager team for EventBridge integration
- AWS SAM team for serverless deployment framework
- Community contributors

---

**Made with ❤️ by Devopspolis**
