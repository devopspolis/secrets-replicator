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
- [Cost](#cost)
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
  - Pass-through mode (no transformation - simple copy)
  - Sed-style regex replacements (e.g., `s/dev/prod/g`)
  - JSON field mappings with JSONPath
  - Region swapping (all AWS services)
  - Environment promotion (dev → qa → prod)
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
┌────────────────────────────────────────────────────────────────────────┐
│                         AWS Account A (Source)                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────┐                                                  │
│  │ Secrets Manager  │ PutSecretValue                                   │
│  │  (Source Secret) │────────┐                                         │
│  └──────────────────┘        │                                         │
│                              ▼                                         │
│                   ┌─────────────────────┐                              │
│                   │    EventBridge      │                              │
│                   │  (Secret Changed)   │                              │
│                   └──────────┬──────────┘                              │
│                              │                                         │
│                              ▼                                         │
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
│                  │                    │                                │
│                  ▼                    ▼                                │
│        ┌──────────────┐    ┌──────────────────┐                        │
│        │  CloudWatch  │    │  SQS DLQ         │                        │
│        │  Metrics     │    │  (Failed Events) │                        │
│        └──────────────┘    └──────────────────┘                        │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ AssumeRole (with External ID)
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      AWS Account B (Destination)                       │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                   ┌──────────────────────┐                             │
│                   │  IAM Role            │                             │
│                   │  (Trust Policy +     │                             │
│                   │   External ID)       │                             │
│                   └──────────┬───────────┘                             │
│                              │                                         │
│                              ▼                                         │
│                   ┌──────────────────────┐                             │
│                   │  Secrets Manager     │                             │
│                   │  (Destination Secret)│                             │
│                   │  [Transformed Value] │                             │
│                   └──────────────────────┘                             │
│                              │                                         │
│                              ▼                                         │
│                   ┌──────────────────────┐                             │
│                   │  KMS Key             │                             │
│                   │  (Customer Managed)  │                             │
│                   └──────────────────────┘                             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
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

- AWS Account with appropriate IAM permissions
- AWS CLI configured (for post-deployment configuration)

### 3-Minute Setup via AWS Serverless Application Repository

```bash
# 1. Deploy from AWS Serverless Application Repository
# Go to: https://serverlessrepo.aws.amazon.com/applications
# Search for: "secrets-replicator"
# Click "Deploy" (accepts default parameters)

# 2. Create configuration secret (defines replication destinations)
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1

# That's it! Secrets will now be replicated to us-west-2 (pass-through mode).

# 3. Test by creating/updating a source secret
aws secretsmanager create-secret \
  --name my-app-secret \
  --description "Test secret for replication" \
  --secret-string '{"api_key":"test-12345","region":"us-east-1"}' \
  --region us-east-1

# 4. Verify replication (after ~2-5 seconds)
aws secretsmanager get-secret-value \
  --secret-id my-app-secret \
  --region us-west-2 \
  --query SecretString \
  --output text

# Expected output:
# {"api_key":"test-12345","region":"us-east-1"}

# For transformations and advanced configuration, see Use Cases section below.
```

---

## Installation

### Option 1: AWS Serverless Application Repository (Recommended)

Deploy directly from SAR - no build tools required:

1. Go to [AWS Serverless Application Repository](https://serverlessrepo.aws.amazon.com/)
2. Search for "secrets-replicator"
3. Click "Deploy"
4. Accept default parameters (only Environment selection needed)
5. Click "Deploy" again
6. **Post-deployment**: Create configuration secret to define replication destinations

```bash
# After SAR deployment, create configuration secret
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1
```

See [Configuration](#configuration) section for multi-destination and cross-account setup.

### Option 2: SAM CLI (For Development)

For local development and testing:

```bash
# Build
sam build --cached

# Deploy (first time)
sam deploy --guided

# Deploy (subsequent deployments)
sam deploy

# Post-deployment: Create CONFIG_SECRET
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1
```

**Note**: All configuration is runtime-based via Secrets Manager. No deployment parameters needed except `Environment` (dev/qa/prod).

### Option 3: CloudFormation Template

Deploy using pre-packaged template:

```bash
# Download latest template from GitHub releases
wget https://github.com/devopspolis/secrets-replicator/releases/latest/download/packaged.yaml

# Deploy
aws cloudformation deploy \
  --template-file packaged.yaml \
  --stack-name secrets-replicator \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev

# Post-deployment: Create CONFIG_SECRET
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1
```

---

## Configuration

All configuration is stored in AWS Secrets Manager and loaded at runtime. This allows you to update replication destinations, name mappings, and transformations without redeploying the Lambda function.

### Configuration Secret (Required)

The `CONFIG_SECRET` defines all replication destinations. By default, the Lambda function loads configuration from:

```
secrets-replicator/config/destinations
```

**Create configuration secret**:

```bash
# Single destination (same region)
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1

# Multiple destinations (multi-region)
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[
    {"region":"us-west-2"},
    {"region":"eu-west-1"},
    {"region":"ap-southeast-1"}
  ]' \
  --region us-east-1

# Cross-account destination
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Secrets Replicator destination configurations" \
  --secret-string '[{
    "region":"us-west-2",
    "account_role_arn":"arn:aws:iam::999999999999:role/SecretsReplicatorDestRole"
  }]' \
  --region us-east-1
```

### Destination Configuration Attributes

Each destination in the JSON array supports these attributes:

| Attribute | Required | Default Value | Description |
|-----------|----------|---------------|-------------|
| `region` | ✅ Yes | (none) | Target AWS region (e.g., `us-west-2`) |
| `account_role_arn` | No | `DEFAULT_ROLE_ARN` env var, or (none) | IAM role ARN for cross-account replication |
| `secret_names` | No | `DEFAULT_SECRET_NAMES` env var, or (none) | Name mapping secret (e.g., `secrets-replicator/names/us-west-2`) |
| `secret_names_cache_ttl` | No | `SECRET_NAMES_CACHE_TTL` env var, or `300` | Cache TTL for name mappings (seconds) |
| `kms_key_id` | No | `KMS_KEY_ID` env var, or (none) | KMS key ID/ARN for destination encryption |
| `filters` | No | `SECRETS_FILTER` env var, or (none) | Filter secret for filtering AND transformation mapping - determines which secrets replicate and which transformation to apply (e.g., `secrets-replicator/filters/dr`) |
| `variables` | No | (none) | Custom variables for transformation expansion (JSON object) |

**Default Resolution Order**:
1. **Per-destination value** (specified in configuration secret) - highest priority
2. **Lambda environment variable** (e.g., `DEFAULT_SECRET_NAMES`, `DEFAULT_ROLE_ARN`)
3. **Hardcoded default** (e.g., `300` for `secret_names_cache_ttl`) - lowest priority

**Example - Full configuration**:
```json
[
  {
    "region": "us-west-2",
    "secret_names": "secrets-replicator/names/us-west-2",
    "filters": "secrets-replicator/filters/us-west-2",
    "kms_key_id": "arn:aws:kms:us-west-2:111111111111:key/..."
  },
  {
    "region": "eu-west-1",
    "account_role_arn": "arn:aws:iam::999999999999:role/SecretsReplicatorDestRole",
    "secret_names": "secrets-replicator/names/eu-west-1",
    "filters": "secrets-replicator/filters/eu-west-1"
  }
]
```

### Filter Configuration

Filters serve a **dual purpose**:
1. **Filtering**: Determine which secrets are replicated (only secrets matching a pattern are replicated)
2. **Transformation Mapping**: Specify which transformation to apply to matching secrets

Each destination can have its own filter configuration, allowing different filtering and transformation rules for different regions.

**Filter Secret Format**:

A filter secret is a JSON object mapping secret name patterns to transformation names:

```json
{
  "app/*": "region-swap",
  "database/prod/*": "db-transform",
  "critical-secret-1": null,
  "other-secrets/*": ""
}
```

**Pattern Matching Rules**:
- **Exact match**: `"mysecret"` matches only `"mysecret"`
- **Prefix wildcard**: `"app/*"` matches `"app/prod"`, `"app/staging/db"`, etc.
- **Suffix wildcard**: `"*/prod"` matches `"app/prod"`, `"db/prod"`, etc.
- **Middle wildcard**: `"app/*/db"` matches `"app/prod/db"`, `"app/staging/db"`, etc.
- Exact matches have highest priority, then wildcard patterns are checked in order

**Transformation Values** (the value in the pattern → value mapping):
- **String value** (e.g., `"region-swap"`): Replicate AND apply the named transformation from `secrets-replicator/transformations/{name}`
- **`null` or `""`**: Replicate without transformation (pass-through copy)
- **No match**: Secret is NOT replicated to that destination (filtered out)

**Example: Per-Destination Filters**

Different destinations can have different filtering/transformation rules:

```bash
# Filter for us-west-2: All app/* secrets get region swap
aws secretsmanager create-secret \
  --name secrets-replicator/filters/us-west-2 \
  --secret-string '{"app/*": "region-swap-west", "critical/*": null}' \
  --region us-east-1

# Filter for eu-west-1: Only database secrets
aws secretsmanager create-secret \
  --name secrets-replicator/filters/eu-west-1 \
  --secret-string '{"database/*": "region-swap-eu"}' \
  --region us-east-1

# Destinations configuration
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --secret-string '[
    {"region": "us-west-2", "filters": "secrets-replicator/filters/us-west-2"},
    {"region": "eu-west-1", "filters": "secrets-replicator/filters/eu-west-1"}
  ]' \
  --region us-east-1
```

With this configuration:
- `app/myapp` → Replicated to `us-west-2` with `region-swap-west` transformation, NOT replicated to `eu-west-1`
- `database/prod` → Replicated to `eu-west-1` with `region-swap-eu` transformation, NOT replicated to `us-west-2`
- `critical/secret1` → Replicated to `us-west-2` without transformation, NOT replicated to `eu-west-1`
- `other/secret` → NOT replicated to either destination (no pattern match)

### Default Configuration Values

The Lambda function uses these hardcoded defaults (no environment variables required):

| Setting | Default | Override Via |
|---------|---------|--------------|
| Configuration secret name | `secrets-replicator/config/destinations` | Env var: `CONFIG_SECRET` |
| Transformation mode | `auto` | Env var: `TRANSFORM_MODE` |
| Log level | `INFO` | Env var: `LOG_LEVEL` |
| CloudWatch metrics | `true` | Env var: `ENABLE_METRICS` |
| Name mapping cache TTL | `300` seconds | Per-destination config |
| Regex timeout | `5` seconds | Env var: `TIMEOUT_SECONDS` |
| Max secret size | `65536` bytes | Env var: `MAX_SECRET_SIZE` |

**Example - Override defaults via environment variables** (optional):

```bash
# Update Lambda environment (optional - for advanced use cases)
aws lambda update-function-configuration \
  --function-name secrets-replicator \
  --environment Variables='{
    "CONFIG_SECRET":"my-custom-config/destinations",
    "LOG_LEVEL":"DEBUG",
    "ENABLE_METRICS":"false"
  }' \
  --region us-east-1
```

### Benefits of Runtime Configuration

- ✅ **No Redeployment**: Update destinations without rebuilding Lambda
- ✅ **Zero Downtime**: Change configuration on-the-fly
- ✅ **Encrypted at Rest**: All config stored in Secrets Manager with KMS
- ✅ **Audit Trail**: CloudTrail logs all configuration changes
- ✅ **Multi-Destination Support**: 1 invocation for N destinations (70% cost reduction for 3+ regions)
- ✅ **Partial Failure Handling**: Per-destination success/failure tracking

---

## Secret Filtering and Name Mapping

**IMPORTANT**: The `secret_names` configuration serves a **dual purpose** - it acts as BOTH a filter (which secrets to replicate) AND a name mapper (what names to use).

### How secret_names Works

When you configure `secret_names` for a destination:

1. **Filtering**: Only secrets matching a pattern in the mapping will be replicated to that destination
2. **Name Mapping**: Matched secrets will be replicated with the transformed name from the mapping

**Key Behavior**:
- **If `secret_names` is configured**: Only secrets matching a pattern are replicated
- **If `secret_names` is NOT configured**: All secrets are replicated with the same name (standard DR pattern)

### Example: Filter and Map Secrets

**Name Mapping Secret** (`secrets-replicator/names/us-west-2`):

**Option 1: Using matching wildcards** (clearer intent):
```json
{
  "app/*": "app/*",
  "database/prod/*": "database/prod/*",
  "critical-secret-1": "critical-secret-1"
}
```

**Option 2: Using empty strings** (when keeping same name):
```json
{
  "app/*": "",
  "database/prod/*": "",
  "critical-secret-1": ""
}
```

Both options produce the same result - secrets keep their original names. The wildcard in the destination value (`"app/*"`) tells the system to preserve the matched portion.

**Destination Configuration**:
```json
[
  {
    "region": "us-west-2",
    "secret_names": "secrets-replicator/names/us-west-2"
  }
]
```

**Replication Behavior**:
- `app/myapp` → ✅ Replicated to us-west-2 as `app/myapp` (matches `app/*`, wildcard preserved)
- `database/prod/master` → ✅ Replicated to us-west-2 as `database/prod/master` (matches `database/prod/*`)
- `critical-secret-1` → ✅ Replicated to us-west-2 as `critical-secret-1` (exact match)
- `test/myapp` → ❌ NOT replicated (doesn't match any pattern - **filtering behavior**)
- `staging/config` → ❌ NOT replicated (doesn't match any pattern - **filtering behavior**)

**System Secrets Always Excluded**:
The Lambda function automatically excludes these prefixes (hardcoded):
- `secrets-replicator/transformations/`
- `secrets-replicator/filters/`
- `secrets-replicator/config/`
- `secrets-replicator/names/`

---

## Secret Name Mapping

Secret name mapping allows you to replicate secrets with different names in the destination. This is useful for:

- **Environment Promotion**: Map `app-config-dev` → `app-config-prod`
- **Naming Conventions**: Match different naming standards across accounts/regions
- **Multi-Tenancy**: Replicate one secret to multiple destination names
- **Namespace Isolation**: Add region/environment prefixes (e.g., `config` → `us-west-2/config`)

### How It Works

1. Create a name mapping secret containing a JSON object mapping source → destination names
2. Reference the mapping secret in your destination configuration using `secret_names`
3. When replicating, the Lambda function checks the mapping and uses the destination name if found

**Mapping Priority**:
1. **Name mapping secret** (if `secret_names` is configured) - highest priority
2. **Same name** (default behavior) - source name = destination name

### Name Mapping Secret Format

The name mapping secret must contain a JSON object with source-to-destination mappings:

```json
{
  "source-secret-name-1": "destination-secret-name-1",
  "source-secret-name-2": "destination-secret-name-2",
  "app/dev/database": "app/prod/database",
  "shared-secret": "us-west-2/shared-secret",
  "app/*": "my-app/*",
  "keep-same-name": ""
}
```

**Rules**:
- **Keys**: Source secret names or patterns (case-sensitive)
- **Values**: Destination secret names or patterns
- **Empty string value (`""`)**: Uses source name (useful for filtering while keeping same name)
- **Wildcards in destination**: Matched portions from source are preserved (e.g., `"app/*"` → `"my-app/*"`)
- **Missing mappings**: If `secret_names` is configured and source not in mapping, secret is NOT replicated (filtering behavior)
- **Matching Order**: Exact matches are checked first, then patterns in order

**Pattern Matching (Source Patterns)**:
- **Exact match**: `"mysecret"` matches only `"mysecret"`
- **Prefix wildcard**: `"app/*"` matches `"app/prod"`, `"app/staging/db"`, etc.
- **Suffix wildcard**: `"*/prod"` matches `"app/prod"`, `"db/prod"`, etc.
- **Middle wildcard**: `"app/*/db"` matches `"app/prod/db"`, `"app/staging/db"`, etc.
- **Multiple wildcards**: `"app/*/prod/*"` matches `"app/team1/prod/db"`, etc.

**Destination Pattern Transformation**:
When the destination pattern contains wildcards, the matched portions from the source are substituted:
- Source: `"app/prod/db"` matching pattern `"app/*"` with destination `"my-app/*"` → Result: `"my-app/prod/db"`
- Source: `"app/prod"` matching pattern `"*/prod"` with destination `"*/production"` → Result: `"app/production"`
- Source: `"legacy-app"` matching pattern `"legacy-*"` with destination `"new-*"` → Result: `"new-app"`
- Source: `"app/prod/db"` matching pattern `"app/*"` with destination `"app/*"` → Result: `"app/prod/db"` (keeps same name)

### Example 1: Environment Promotion

**Scenario**: Promote secrets from `dev` to `prod` with different naming.

**Name Mapping Secret** (`secrets-replicator/names/prod-mappings`):
```json
{
  "app-config-dev": "app-config-prod",
  "db-credentials-dev": "db-credentials-prod",
  "api-keys-dev": "api-keys-prod"
}
```

**Destination Configuration**:
```json
[
  {
    "region": "us-east-1",
    "secret_names": "secrets-replicator/names/prod-mappings"
  }
]
```

**Setup**:
```bash
# 1. Create name mapping secret
aws secretsmanager create-secret \
  --name secrets-replicator/names/prod-mappings \
  --description "Dev to Prod name mappings" \
  --secret-string '{
    "app-config-dev":"app-config-prod",
    "db-credentials-dev":"db-credentials-prod",
    "api-keys-dev":"api-keys-prod"
  }' \
  --region us-east-1

# 2. Create/update destination configuration
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/config/destinations \
  --secret-string '[{
    "region":"us-east-1",
    "secret_names":"secrets-replicator/names/prod-mappings"
  }]' \
  --region us-east-1

# 3. Update source secret (triggers replication)
aws secretsmanager put-secret-value \
  --secret-id app-config-dev \
  --secret-string '{"api":"https://api.dev.example.com"}' \
  --region us-east-1

# 4. Verify destination secret has mapped name
aws secretsmanager get-secret-value \
  --secret-id app-config-prod \
  --query SecretString \
  --output text \
  --region us-east-1
```

**Result**: `app-config-dev` is replicated to `app-config-prod` in `us-east-1`.

### Example 2: Multi-Region with Region-Specific Names

**Scenario**: Replicate secrets to multiple regions with region prefixes.

**Name Mapping Secret for us-west-2** (`secrets-replicator/names/us-west-2`):
```json
{
  "shared/database-config": "us-west-2/database-config",
  "shared/api-keys": "us-west-2/api-keys"
}
```

**Name Mapping Secret for eu-west-1** (`secrets-replicator/names/eu-west-1`):
```json
{
  "shared/database-config": "eu-west-1/database-config",
  "shared/api-keys": "eu-west-1/api-keys"
}
```

**Destination Configuration**:
```json
[
  {
    "region": "us-west-2",
    "secret_names": "secrets-replicator/names/us-west-2"
  },
  {
    "region": "eu-west-1",
    "secret_names": "secrets-replicator/names/eu-west-1"
  }
]
```

**Result**:
- Source `shared/database-config` (us-east-1) → `us-west-2/database-config` (us-west-2)
- Source `shared/database-config` (us-east-1) → `eu-west-1/database-config` (eu-west-1)

### Example 3: Cross-Account with Account-Specific Names

**Scenario**: Replicate secrets to DR account with account-specific naming.

**Name Mapping Secret** (`secrets-replicator/names/dr-account`):
```json
{
  "prod/app-config": "dr-prod/app-config",
  "prod/database": "dr-prod/database"
}
```

**Destination Configuration**:
```json
[
  {
    "region": "us-east-1",
    "account_role_arn": "arn:aws:iam::999888777666:role/SecretsReplicatorDestRole",
    "secret_names": "secrets-replicator/names/dr-account"
  }
]
```

**Setup**:
```bash
# In source account (123456789012)
aws secretsmanager create-secret \
  --name secrets-replicator/names/dr-account \
  --secret-string '{
    "prod/app-config":"dr-prod/app-config",
    "prod/database":"dr-prod/database"
  }' \
  --region us-east-1
```

**Result**: `prod/app-config` in account 123456789012 → `dr-prod/app-config` in account 999888777666.

### Example 4: Partial Mappings (Mixed Behavior)

**Name Mapping Secret**:
```json
{
  "app-config": "app-config-v2",
  "database-credentials": "db-creds"
}
```

**Behavior**:
- ✅ `app-config` → `app-config-v2` (mapped)
- ✅ `database-credentials` → `db-creds` (mapped)
- ✅ `other-secret` → `other-secret` (not in mapping, uses same name)

### Example 5: Wildcard Pattern Mappings

**Scenario**: Map all secrets matching patterns without explicit enumeration.

**Name Mapping Secret** (`secrets-replicator/names/wildcard-mappings`):
```json
{
  "app/*": "my-app/*",
  "*/prod": "*/production",
  "legacy-*": "new-*",
  "team/*/db": "database/*/config"
}
```

**Behavior Examples**:

| Source Secret | Pattern Matched | Destination Secret |
|---------------|----------------|-------------------|
| `app/config` | `app/*` | `my-app/config` |
| `app/team1/settings` | `app/*` | `my-app/team1/settings` |
| `services/prod` | `*/prod` | `services/production` |
| `legacy-service` | `legacy-*` | `new-service` |
| `team/alpha/db` | `team/*/db` | `database/alpha/config` |
| `other/secret` | (no match) | `other/secret` (unchanged) |

**Pattern Matching Rules**:
- Patterns checked in order (exact matches first, then patterns)
- First matching pattern wins
- `*` matches any sequence of characters (including `/`)
- Wildcards in destination are replaced with matched content from source

**Example with Multiple Wildcards**:
```json
{
  "app/*/prod/*": "my-app/*/production/*"
}
```
- `app/team1/prod/db` → `my-app/team1/production/db`
- `app/x/prod/y/z` → `my-app/x/production/y/z`

**Combining Exact and Pattern Matches**:
```json
{
  "critical-secret": "prod-critical-secret",
  "app/*": "my-app/*",
  "*": "archived/*"
}
```
- `critical-secret` → `prod-critical-secret` (exact match priority)
- `app/config` → `my-app/config` (pattern match)
- `other/secret` → `archived/other/secret` (catch-all pattern)

**Setup**:
```bash
# Create wildcard mapping secret
aws secretsmanager create-secret \
  --name secrets-replicator/names/wildcard-mappings \
  --description "Wildcard pattern name mappings" \
  --secret-string '{
    "app/*":"my-app/*",
    "*/prod":"*/production",
    "legacy-*":"new-*"
  }' \
  --region us-east-1

# Use in destination configuration
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/config/destinations \
  --secret-string '[{
    "region":"us-west-2",
    "secret_names":"secrets-replicator/names/wildcard-mappings"
  }]' \
  --region us-east-1
```

**When to Use Wildcards**:
- ✅ **Many secrets with predictable naming**: `app/team1/*`, `app/team2/*`, etc.
- ✅ **Environment/region prefixing**: Map `dev/*` → `prod/*`
- ✅ **Legacy migration**: Rename all `old-*` → `new-*`
- ❌ **Few secrets**: Use exact matches (simpler, faster)
- ❌ **Complex conditional logic**: Consider transformation secrets instead

### Caching

Name mapping secrets are cached in Lambda memory with configurable TTL:

**Default TTL**: 300 seconds (5 minutes)

**Per-Destination Override**:
```json
[
  {
    "region": "us-west-2",
    "secret_names": "secrets-replicator/names/us-west-2",
    "secret_names_cache_ttl": 600
  }
]
```

**Cache Behavior**:
- First access: Load from Secrets Manager (~100ms)
- Subsequent accesses: Serve from memory cache (~1ms)
- After TTL expires: Reload from Secrets Manager
- Cache per mapping secret (different secrets = different cache entries)

**When to Adjust TTL**:
- ✅ **Increase TTL (600-3600s)**: Rarely-changing mappings, reduce API calls
- ✅ **Decrease TTL (60-120s)**: Frequently-changing mappings, faster updates
- ✅ **Keep default (300s)**: Most use cases

### Updating Name Mappings

```bash
# Update name mapping secret
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/names/prod-mappings \
  --secret-string '{
    "app-config-dev":"app-config-prod",
    "new-secret-dev":"new-secret-prod"
  }' \
  --region us-east-1

# Changes take effect after cache TTL expires (default 300 seconds)
# Or force immediate refresh by restarting Lambda (cold start clears cache)
```

### Best Practices

1. **Use Descriptive Mapping Secret Names**: `secrets-replicator/names/{destination}` pattern recommended
2. **Version Mappings**: Use Secrets Manager versioning to track changes
3. **Test Before Production**: Verify mappings with test secrets first
4. **Document Mappings**: Add description field when creating mapping secrets
5. **Consistent Naming**: Establish naming convention across environments
6. **Avoid Circular Mappings**: Don't map `A` → `B` and `B` → `A` (undefined behavior)

### Troubleshooting

#### Problem: Secret not replicated with expected name

**Check**: Verify mapping secret content
```bash
aws secretsmanager get-secret-value \
  --secret-id secrets-replicator/names/prod-mappings \
  --query SecretString \
  --output text | jq .
```

**Check**: Look for source secret name in mapping (case-sensitive!)
```bash
# If source is "App-Config" but mapping has "app-config", no match!
```

#### Problem: Mapping changes not taking effect

**Cause**: Mapping cached in Lambda memory

**Solution**: Wait for cache TTL to expire, or update destination config to force Lambda restart

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

1. Create configuration secret (destination: us-west-2):
```bash
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Replication destinations" \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1
```

2. (Optional) Create transformation secret for region swapping:
```bash
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap-sed \
  --description "Sed transformation for region swapping" \
  --secret-string 's/us-east-1/us-west-2/g' \
  --region us-east-1
```

**Note**: Transformations are configured per-destination in the configuration secret or via destination-specific settings. See the Transformations section for details on applying transformations.

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

#### Complete Example: Replicate `app/*` Secrets with Region Transformation

This example shows how to replicate all secrets matching `app/*` from `us-east-1` to `us-west-2`, replacing all occurrences of `us-east-1` with `us-west-2` in the secret values.

**Step 1: Create the transformation secret**

This defines the sed transformation rule:

```bash
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --description "Replace us-east-1 with us-west-2" \
  --secret-string 's/us-east-1/us-west-2/g' \
  --region us-east-1
```

**Step 2: Create the filter secret**

This maps secret patterns to transformation names. Secrets matching `app/*` will use the `region-swap` transformation:

```bash
aws secretsmanager create-secret \
  --name secrets-replicator/filters/dr \
  --description "DR filter - replicate app secrets with region swap" \
  --secret-string '{"app/*": "region-swap"}' \
  --region us-east-1
```

**Step 3: Create the destinations secret with filters**

This configures the destination region and links to the filter secret:

```bash
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Replication destinations" \
  --secret-string '[{
    "region": "us-west-2",
    "filters": "secrets-replicator/filters/dr"
  }]' \
  --region us-east-1
```

**Step 4: Test by creating/updating a source secret**

```bash
aws secretsmanager create-secret \
  --name app/database \
  --description "Application database config" \
  --secret-string '{"host":"db.us-east-1.rds.amazonaws.com","port":"5432"}' \
  --region us-east-1
```

**Step 5: Verify replication (after ~2-5 seconds)**

```bash
aws secretsmanager get-secret-value \
  --secret-id app/database \
  --region us-west-2 \
  --query SecretString \
  --output text
```

**Expected output**:
```json
{"host":"db.us-west-2.rds.amazonaws.com","port":"5432"}
```

**How It Works**:
1. When `app/database` is created/updated in `us-east-1`, EventBridge triggers the Lambda
2. Lambda loads the filter from `secrets-replicator/filters/dr`
3. The filter matches `app/database` against pattern `app/*` and finds transformation `region-swap`
4. Lambda loads the transformation from `secrets-replicator/transformations/region-swap`
5. The sed rule `s/us-east-1/us-west-2/g` is applied to the secret value
6. The transformed secret is written to `us-west-2`

**Filtering Behavior**:
- Secrets matching `app/*` are replicated with the `region-swap` transformation
- Secrets NOT matching any pattern in the filter are NOT replicated
- System secrets (prefixed with `secrets-replicator/`) are automatically excluded

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
# 1. Create configuration secret with cross-account destination
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Cross-account replication destinations" \
  --secret-string '[{
    "region":"us-east-1",
    "account_role_arn":"arn:aws:iam::222222222222:role/SecretsReplicatorDestRole"
  }]' \
  --region us-east-1

# 2. (Optional) Create transformation secret for account ID swap
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/account-swap \
  --secret-string 's/111111111111/222222222222/g' \
  --region us-east-1
```

**Note**: Transformations are configured per-destination. See the Transformations section for applying transformations.

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
# 1. Create configuration secret (same region replication)
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Environment promotion destinations" \
  --secret-string '[{"region":"us-east-1"}]' \
  --region us-east-1

# 2. Create name mapping secret (dev → prod secret name)
aws secretsmanager create-secret \
  --name secrets-replicator/names/us-east-1 \
  --description "Dev to Prod name mappings" \
  --secret-string '{"app-config-dev":"app-config-prod"}' \
  --region us-east-1

# 3. Update configuration to use name mapping
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/config/destinations \
  --secret-string '[{"region":"us-east-1","secret_names":"secrets-replicator/names/us-east-1"}]' \
  --region us-east-1

# 4. (Optional) Create transformation secret with JSON mapping
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/dev-to-prod \
  --secret-string '{"$.api_endpoint": "https://api.prod.example.com", "$.database": "prod-database", "$.log_level": "INFO", "$.cache_ttl": "3600"}' \
  --region us-east-1
```

**Note**: Transformations are configured per-destination. See the Transformations section for applying transformations.
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

### Use Case 4: Multi-Region Replication (Global Application)

**Scenario**: Replicate database credentials to 3 regions simultaneously with region-specific transformations.

**Source Secret** (`us-west-2`):
```json
{
  "host": "prod-db.us-west-2.rds.amazonaws.com",
  "port": "5432",
  "username": "dbadmin",
  "password": "SuperSecretPassword123",
  "read_replica": "prod-db-read.us-west-2.rds.amazonaws.com",
  "region": "us-west-2"
}
```

**Setup**:

1. Create configuration secret with multiple destinations:
```bash
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --description "Multi-region replication destinations" \
  --secret-string '[
    {"region":"us-east-1"},
    {"region":"eu-west-1"},
    {"region":"ap-southeast-1"}
  ]' \
  --region us-west-2
```

2. Create region-specific transformation secrets:
```bash
# us-east-1 transformations
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/to-us-east-1 \
  --secret-string 's/us-west-2/us-east-1/g' \
  --region us-west-2

# eu-west-1 transformations
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/to-eu-west-1 \
  --secret-string 's/us-west-2/eu-west-1/g' \
  --region us-west-2

# ap-southeast-1 transformations
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/to-ap-southeast-1 \
  --secret-string 's/us-west-2/ap-southeast-1/g' \
  --region us-west-2
```

**Note**: This example uses the same transformation for all destinations. For destination-specific transformations, use per-destination tags or name mappings.

**Result**: Single Lambda invocation replicates to all 3 regions with region-specific values.

**Destination Secrets**:
- `us-east-1`: All `us-west-2` values replaced with `us-east-1`
- `eu-west-1`: All `us-west-2` values replaced with `eu-west-1`
- `ap-southeast-1`: All `us-west-2` values replaced with `ap-southeast-1`

**Response** (HTTP 200 - All succeeded):
```json
{
  "statusCode": 200,
  "body": "Secret replicated successfully to all destinations",
  "sourceSecretId": "app/prod/db",
  "totalDurationMs": 1234.56,
  "destinations": [
    {
      "region": "us-east-1",
      "secret_name": "app/prod/db",
      "success": true,
      "arn": "arn:aws:secretsmanager:us-east-1:...",
      "version_id": "...",
      "duration_ms": 412.34
    },
    {
      "region": "eu-west-1",
      "secret_name": "app/prod/db",
      "success": true,
      "arn": "arn:aws:secretsmanager:eu-west-1:...",
      "version_id": "...",
      "duration_ms": 398.21
    },
    {
      "region": "ap-southeast-1",
      "secret_name": "app/prod/db",
      "success": true,
      "arn": "arn:aws:secretsmanager:ap-southeast-1:...",
      "version_id": "...",
      "duration_ms": 424.01
    }
  ]
}
```

**Cost**: 1 Lambda invocation (vs 3 separate deployments) = **70% cost reduction**

---

### Use Case 5: Multi-Region Application with Complex Transformations

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

**Note**: Transformations are configured per-destination. See the Transformations section for applying transformations.

2. Lambda environment variables:
```bash
DEST_REGION=us-west-2
# TRANSFORM_MODE=auto  # Optional - auto-detects sed format
```

**Result**: Complete multi-region deployment with region-specific endpoints.

---

## Transformations

Secrets Replicator supports two replication modes:

1. **Pass-Through Replication** - Simple copy without transformation
2. **Transformation Replication** - Apply sed or JSON transformations during replication

### Pass-Through Replication

By default, Secrets Replicator performs **pass-through replication** - copying the secret value exactly as-is to the destination without any modifications.

**When to use pass-through**:
- ✅ Simple disaster recovery (identical copies across regions)
- ✅ Secret backup to another region
- ✅ Cross-account secret sharing (no transformation needed)
- ✅ Testing replication setup before adding transformations

**Setup**:

```bash
# No transformation secret needed!
# Simply deploy Secrets Replicator and configure destinations via CONFIG_SECRET

# Example: Create configuration secret
aws secretsmanager create-secret \
  --name secrets-replicator/config/destinations \
  --secret-string '[{"region":"us-west-2"}]' \
  --region us-east-1

# Update source secret - it will be replicated as-is
aws secretsmanager put-secret-value \
  --secret-id my-secret \
  --secret-string '{"username":"admin","password":"secret123"}'

# Verify destination (after 2-5 seconds)
aws secretsmanager get-secret-value \
  --secret-id my-secret \
  --region us-west-2 \
  --query SecretString \
  --output text

# Output: {"username":"admin","password":"secret123"}  (exact copy)
```

**Response**:
```json
{
  "statusCode": 200,
  "transformMode": "passthrough",
  "rulesCount": 0,
  "transformChainLength": 0,
  "sourceRegion": "us-east-1",
  "destRegion": "us-west-2"
}
```

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
3. Configure transformations per-destination in the configuration secret or via destination-specific settings

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
```

**Note**: Configure transformations per-destination. See Configuration section for details.

**Region Swap**:
```bash
# Create transformation secret
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/region-swap \
  --secret-string 's/us-east-1/us-west-2/g'
```

**Complex Multi-Line Transformations**:
```bash
# Create transformation secret with multi-line sed script
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/comprehensive-transform \
  --secret-string '# Change environment
s/dev/prod/g
s/qa/prod/g

# Update hostnames
s/dev-db\.example\.com/prod-db.example.com/g
s/dev-api\.example\.com/prod-api.example.com/g

# Change ports
s/:3000/:8080/g

# Case-insensitive domain swap
s/example\.local/example.com/gi'
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

### Variable Expansion

**NEW**: Transform secrets can now include variable references that are expanded dynamically for each destination using the `${VARIABLE}` syntax.

#### Why Variable Expansion?

Without variables, you need separate transformation secrets for each destination region:
```bash
# ❌ Old approach: One transformation secret per destination
secrets-replicator/transformations/us-east-1-to-us-west-2
secrets-replicator/transformations/us-east-1-to-eu-west-1
secrets-replicator/transformations/us-east-1-to-ap-south-1
```

With variables, one transformation secret works for all destinations:
```bash
# ✅ New approach: One transformation secret for all destinations
secrets-replicator/transformations/region-swap
# Content: s/us-east-1/${REGION}/g
```

#### Available Variables

**Core Variables** (automatically provided for all transformations):

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `${REGION}` | Destination region | `us-west-2` |
| `${SOURCE_REGION}` | Source region | `us-east-1` |
| `${SECRET_NAME}` | Source secret name | `my-app/db-config` |
| `${DEST_SECRET_NAME}` | Destination secret name (after name mapping) | `my-app/db-config-west` |
| `${ACCOUNT_ID}` | Destination AWS account ID | `123456789012` |
| `${SOURCE_ACCOUNT_ID}` | Source AWS account ID | `999999999999` |

**Custom Variables**: Define per-destination variables in the destinations configuration (see Configuration section).

#### Variable Expansion Examples

**Example 1: Region-Aware Transformations**

Create a single transformation secret that adapts to each destination region:

```bash
# Create transformation secret with variable
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/adaptive-region-swap \
  --secret-string 's/us-east-1/${REGION}/g' \
  --region us-east-1
```

When this transformation is applied:
- For destination `us-west-2`: Expands to `s/us-east-1/us-west-2/g`
- For destination `eu-west-1`: Expands to `s/us-east-1/eu-west-1/g`
- For destination `ap-south-1`: Expands to `s/us-east-1/ap-south-1/g`

**Example 2: Multi-Variable Sed Transformation**

Replace multiple patterns using different variables:

```bash
# Create transformation with multiple variables
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/comprehensive-swap \
  --secret-string '# Swap regions
s/${SOURCE_REGION}/${REGION}/g

# Update RDS endpoints with destination region
s/rds\.${SOURCE_REGION}\.amazonaws\.com/rds.${REGION}.amazonaws.com/g

# Update S3 bucket references
s/my-bucket-${SOURCE_REGION}/my-bucket-${REGION}/g' \
  --region us-east-1
```

**Example 3: JSON Transformation with Variables**

Use variables in JSON field mappings:

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
    },
    {
      "path": "$.metadata.dest_account",
      "find": "000000000000",
      "replace": "${ACCOUNT_ID}"
    }
  ]
}
```

```bash
# Create JSON transformation secret
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/json-with-variables \
  --secret-string "$(cat <<'EOF'
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
    }
  ]
}
EOF
)" \
  --region us-east-1
```

**Example 4: Custom Variables**

Define custom variables per destination for application-specific transformations:

```bash
# Create configuration with custom variables
aws secretsmanager put-secret-value \
  --secret-id secrets-replicator/config/destinations \
  --secret-string '[
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
]' \
  --region us-east-1

# Create transformation using custom variables
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/custom-var-transform \
  --secret-string '# Update environment
s/dev/${ENV}/g

# Update database instance
s/dev-db-1/${DB_INSTANCE}/g

# Update API domain
s/api\.dev\.example\.com/${API_DOMAIN}/g' \
  --region us-east-1
```

#### Variable Syntax Rules

1. **Pattern**: Variables must match `${VARIABLE_NAME}`
2. **Naming**: Variable names must:
   - Start with a letter or underscore
   - Contain only uppercase letters, numbers, and underscores
   - Example: `${REGION}`, `${DB_HOST_1}`, `${_CUSTOM_VAR}`
3. **Case-Sensitive**: Variable names are case-sensitive (must be uppercase)
4. **Error Handling**: Undefined variables raise an error with a helpful message listing all available variables

**Invalid Examples**:
- `${region}` - ❌ Lowercase (not matched)
- `${1INVALID}` - ❌ Starts with number (not matched)
- `${Region}` - ❌ Mixed case (not matched)
- `$REGION` - ❌ Missing braces (not expanded)
- `{REGION}` - ❌ Missing dollar sign (not expanded)

#### Testing Variable Expansion

Test variable expansion locally before deployment:

```bash
# Test sed transformation with variable substitution
echo '{"host":"db.us-east-1.amazonaws.com"}' | \
  sed 's/us-east-1/us-west-2/g'
# Output: {"host":"db.us-west-2.amazonaws.com"}

# Test multiple variable substitution
REGION="eu-west-1"
SOURCE_REGION="us-east-1"
echo "s/${SOURCE_REGION}/${REGION}/g" | \
  sed "s/\${SOURCE_REGION}/$SOURCE_REGION/g; s/\${REGION}/$REGION/g"
# Output: s/us-east-1/eu-west-1/g
```

#### Variable Expansion Troubleshooting

**Error: "Undefined variable"**
```
VariableExpansionError: Undefined variable: ${DB_HOST}. Available variables: REGION, SOURCE_REGION, SECRET_NAME, DEST_SECRET_NAME, ACCOUNT_ID, SOURCE_ACCOUNT_ID
```

**Solution**: Either:
1. Use one of the core variables listed in the error message
2. Define the custom variable in the destination configuration:
   ```json
   {
     "region": "us-west-2",
     "variables": {
       "DB_HOST": "prod-db.example.com"
     }
   }
   ```

**Variable not expanding (passes through unchanged)**

If you see `${REGION}` in your replicated secret instead of the actual region value:
1. Check variable name is uppercase: `${REGION}` not `${region}`
2. Check syntax: `${VARIABLE}` not `$VARIABLE` or `{VARIABLE}`
3. Check the transformation secret was loaded correctly
4. Review CloudWatch logs for variable expansion errors

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

## Cost

### Monthly Cost Breakdown

The cost of running Secrets Replicator depends on two factors:

1. **Replication activity** (Lambda, EventBridge, CloudWatch, etc.) - Very low cost
2. **Secrets Manager storage** (destination secrets) - Primary cost driver

#### Typical Scenarios

| Scenario | Replications/Month | Secrets Stored | Services Cost | Secrets Storage | **Total/Month** |
|----------|-------------------|----------------|---------------|-----------------|-----------------|
| **Testing** | 50 | 1 | $0.03 | $0.40 | **$0.43** |
| **Light Production** | 100 | 5 | $0.15 | $2.00 | **$2.15** |
| **Moderate Production** | 1,000 | 10 | $0.79 | $4.00 | **$4.79** |
| **Heavy Production** | 10,000 | 50 | $6.50 | $20.00 | **$26.50** |

#### Detailed Cost Components

**Per 1,000 Replications:**
- Lambda invocations + duration: ~$0.11
- Secrets Manager API calls: ~$0.01
- EventBridge events: ~$0.001
- CloudWatch (logs + metrics): ~$0.35
- X-Ray traces: ~$0.005
- SQS/SNS: ~$0.01
- **Subtotal: ~$0.48**

**Fixed Monthly Costs:**
- S3 storage (SAR packages): ~$0.02
- CloudWatch Alarms (3 alarms): ~$0.30 (if enabled)
- **Subtotal: ~$0.32**

**Secrets Manager Storage:**
- $0.40 per secret per month (same as AWS native replication)
- This is the largest cost component for most users

#### Cost Calculator

Use the included cost calculator script for precise estimates:

```bash
# Light production (100 replications, 5 secrets)
./scripts/cost-calculator.py --replications 100 --secrets 5

# Moderate production (1000 replications, 10 secrets)
./scripts/cost-calculator.py --replications 1000 --secrets 10

# Heavy production (10000 replications, 50 secrets)
./scripts/cost-calculator.py --replications 10000 --secrets 50

# Disable metrics and alarms to reduce costs
./scripts/cost-calculator.py --replications 1000 --secrets 10 --no-metrics --no-alarms
```

Example output:
```
======================================================================
AWS Secrets Replicator - Monthly Cost Estimate
======================================================================

Usage Parameters:
  Replications per month:     1,000
  Destination secrets:        10
  Lambda memory:              512 MB
  Avg Lambda duration:        3.0 seconds
  Custom metrics enabled:     True
  CloudWatch alarms enabled:  True

----------------------------------------------------------------------
Cost Breakdown:
----------------------------------------------------------------------

Lambda:
  Invocations:                $0.0002
  Duration:                   $0.0750
  Subtotal:                   $0.0752

Secrets Manager:
  API calls (Get/Put):        $0.0100
  Secret storage:             $4.00
  Subtotal:                   $4.01

CloudWatch:
  Logs ingestion:             $0.0010
  Logs storage:               $0.0001
  Custom metrics:             $1.20
  Alarms:                     $0.30
  Subtotal:                   $1.50

======================================================================
Services Total (excl. secrets storage):   $0.79
Secrets Storage (10 secrets):             $4.00
MONTHLY TOTAL:                             $4.79
======================================================================
```

### Cost Optimization Tips

#### 1. Disable Custom Metrics (Save ~$0.30 per 1,000 replications)

Set `EnableMetrics: 'false'` when deploying:

```bash
sam deploy \
  --parameter-overrides EnableMetrics=false \
  --guided
```

You'll still have CloudWatch Logs for troubleshooting, but no custom metrics.

#### 2. Disable CloudWatch Alarms (Save ~$0.30/month)

Remove or comment out the alarm resources in `template.yaml` before deployment.

#### 3. Reduce Log Retention

Set CloudWatch Logs retention to 1 day for testing, 7 days for production:

```bash
aws logs put-retention-policy \
  --log-group-name /aws/lambda/secrets-replicator \
  --retention-in-days 7
```

#### 4. Delete Test Secrets

Each destination secret costs $0.40/month. Delete test secrets after validation:

```bash
aws secretsmanager delete-secret \
  --secret-id test-secret \
  --force-delete-without-recovery
```

#### 5. Use AWS Free Tier

If your account is eligible for AWS Free Tier:
- Lambda: 1M free requests/month + 400,000 GB-seconds
- CloudWatch Logs: 5GB ingestion
- X-Ray: 100,000 traces/month
- SNS: 1,000 notifications/month
- SQS: 1M requests/month

This can reduce your costs significantly for light usage.

### Cost Comparison

| Solution | Setup Cost | Monthly Cost (10 secrets) | Value Transformation | Cross-Account |
|----------|-----------|---------------------------|---------------------|---------------|
| **AWS Native Replication** | Free | $4.00 | ❌ No | ❌ No |
| **Secrets Replicator** | Free | $4.79 | ✅ Yes | ✅ Yes |
| **Custom Solution** | High | Varies | ✅ Yes | ✅ Yes |

**Key Insight**: The incremental cost for transformation and cross-account support is only ~$0.79/month for moderate usage.

### Publishing to SAR Costs

Publishing your application to AWS Serverless Application Repository:

- **SAR Publishing**: FREE (no charge to publish)
- **S3 Storage** (packaged artifacts): ~$0.02/month
- **S3 Requests** (package uploads): ~$0.01 one-time
- **Total**: ~$0.03 one-time + minimal monthly

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
- Transformation not configured for destination
- Transformation secret not found
- Transformation secret name incorrect in configuration
- Auto-detection failed to detect correct format

**Solutions**:
1. Test sed pattern locally: `echo "value" | sed 's/old/new/g'`
2. Check CloudWatch logs for transformation details
3. Verify transformation is configured per-destination in CONFIG_SECRET
4. Verify transformation secret exists:
   ```bash
   aws secretsmanager get-secret-value --secret-id secrets-replicator/transformations/my-transform
   ```
5. Check configuration secret has correct transformation reference:
   ```bash
   aws secretsmanager get-secret-value --secret-id secrets-replicator/config/destinations
   ```

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

**A**: Yes! Use the `Destinations` parameter to replicate to multiple regions in a single Lambda invocation. This provides 70% cost reduction for 3+ regions and simplified management with HTTP 207 Multi-Status responses for partial failures. See the [Multi-Destination Configuration](#multi-destination-configuration-recommended) section and [Use Case 4](#use-case-4-multi-region-replication-global-application) for details.

For backward compatibility, you can also deploy multiple stacks (one per destination), but the multi-destination approach is now recommended.

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
