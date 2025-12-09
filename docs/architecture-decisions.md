# Architecture Decision Records

This document records major architectural decisions made during the development of Secrets Replicator.

---

## Table of Contents

1. [ADR-001: Lambda-Side Filtering with Tag Support](#adr-001-lambda-side-filtering-with-tag-support)
2. [ADR-002: Transformation Secrets Architecture](#adr-002-transformation-secrets-architecture)
3. [ADR-003: Hardcoded Exclusion for Transformation Secrets](#adr-003-hardcoded-exclusion-for-transformation-secrets)

---

## ADR-001: Lambda-Side Filtering with Tag Support

**Date**: 2025-11-02
**Status**: Accepted
**Deciders**: Project Team
**Related**: Phase 8 Enhancement

### Context

The initial implementation triggers Lambda on ALL secret updates in an AWS account. For production environments with 100+ secrets where only a subset (e.g., 50-70) need replication, this results in:

1. **Wasted Lambda invocations**: Lambda invoked for secrets that shouldn't be replicated
2. **Unnecessary error logs**: AccessDenied errors for secrets without permissions
3. **Increased costs**: More invocations than needed (though negligible in absolute terms)
4. **Poor observability**: Harder to distinguish intentional vs unintentional invocations

### Decision

Implement **Lambda-side filtering** with the following capabilities:

#### Filtering Mechanisms (OR Logic for Includes)

1. **Secret Name Pattern** (Regex)
   - Environment variable: `SOURCE_SECRET_PATTERN`
   - Example: `^(prod-|app-).*$`
   - Matches secrets by name pattern

2. **Explicit Secret List** (Comma-separated)
   - Environment variable: `SOURCE_SECRET_LIST`
   - Example: `shared-redis,shared-cache,shared-db`
   - Matches exact secret names

3. **Tag-Based Include Filtering** (OR logic)
   - Environment variable: `SOURCE_INCLUDE_TAGS`
   - Example: `SecretsReplicator:Replicate=true,Environment=production`
   - Matches if secret has ANY of the specified tags

4. **Tag-Based Exclude Filtering** (Override includes)
   - Environment variable: `SOURCE_EXCLUDE_TAGS`
   - Example: `SecretsReplicator:SkipReplication=true,Environment=test`
   - Excludes if secret has ANY of the specified tags (highest priority)

#### Filtering Logic

```
For each secret update event:
  1. Check if secret matches transformation exclusion pattern (transformations/*)
     → If YES: Skip (never replicate transformation secrets)

  2. Check exclude filters (SOURCE_EXCLUDE_TAGS)
     → If ANY exclude tag matches: Skip

  3. Check include filters (OR logic):
     → If pattern matches: Include
     → OR if in explicit list: Include
     → OR if ANY include tag matches: Include

  4. If included and not excluded: Replicate
     Otherwise: Skip with log message
```

#### Tag Naming Convention

Use `SecretsReplicator:` prefix for all tags to avoid conflicts:
- `SecretsReplicator:Replicate` (include filter)
- `SecretsReplicator:SkipReplication` (exclude filter)
- `SecretsReplicator:TransformMode` (configuration)
- `SecretsReplicator:TransformSecretName` (configuration)
- `SecretsReplicator:DestRegion` (configuration)

### Rationale

#### Why Lambda-Side Instead of EventBridge Filtering?

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **EventBridge Pattern Filtering** | No wasted invocations | Limited to ~10-20 patterns, inflexible | ❌ Rejected |
| **IAM Policy Filtering** | Simple | Still invokes Lambda, only restricts permissions | ❌ Insufficient |
| **Lambda-Side Filtering** | Flexible, handles any number of secrets, tag-based | Lambda still invoked but exits early | ✅ **Selected** |

**Lambda-side filtering chosen because**:
1. Supports unlimited secrets (100+)
2. Flexible pattern matching (regex)
3. Tag-based filtering (dynamic)
4. Easy to update (just environment variables)
5. Cost difference negligible (early exit < 10ms)

#### Why OR Logic for Includes?

**OR logic** (match ANY condition) is more flexible:
- Pattern: `^prod-.*` catches prod secrets
- List: `shared-redis` catches specific shared secrets
- Tag: `Replicate=true` catches explicitly tagged secrets

**All three can work together** to cover different use cases in a single deployment.

#### Why Tags Over Other Metadata?

**Alternatives considered**:
1. Secret description field (not queryable)
2. Secret name conventions (inflexible)
3. Separate DynamoDB table (additional service)

**Tags chosen because**:
- Native Secrets Manager feature
- Queryable via DescribeSecret
- Support key-value pairs
- Commonly used pattern in AWS

### Consequences

#### Positive

- ✅ Flexible filtering supports diverse production scenarios
- ✅ Tag-based approach is intuitive for AWS users
- ✅ OR logic allows multiple inclusion methods
- ✅ Easy to add/remove secrets from replication (just update tags)
- ✅ Clear exclusion mechanism prevents accidents

#### Negative

- ⚠️ Lambda still invoked for all secrets (but exits early)
- ⚠️ Requires DescribeSecret API call for tag retrieval (+50ms latency)
- ⚠️ Tags must be maintained (additional operational overhead)

#### Mitigation

- Cache tags in Lambda global scope for warm containers (reduces API calls)
- Document tag naming conventions clearly
- Provide tag management scripts/examples

### Implementation Details

**Files to modify**:
- `src/handler.py`: Add filtering logic with early exit
- `src/config.py`: Add new configuration fields
- `template.yaml`: Add new parameters
- `tests/unit/test_handler.py`: Add filtering tests

**IAM Permissions Required**:
```json
{
  "Sid": "ReadSecretTags",
  "Effect": "Allow",
  "Action": [
    "secretsmanager:DescribeSecret"
  ],
  "Resource": "*"
}
```

**Estimated Effort**: 3-4 hours

---

## ADR-002: Transformation Secrets Architecture

**Date**: 2025-11-02
**Status**: Accepted
**Deciders**: Project Team
**Related**: ADR-001

### Context

Different secrets require different transformations:
- Production databases: Region swap (us-west-2 → us-east-1)
- Application configs: JSON field mapping
- Shared services: Custom sed scripts

**Initial approaches considered**:
1. **Inline tags**: Store transformation in tag value
2. **S3 objects**: Store transformation files in S3
3. **Transformation secrets**: Store transformations as Secrets Manager secrets

### Problem: Security vs Complexity

#### Inline Tags Approach

**Security Issue**: Anyone with `secretsmanager:TagResource` can inject code:
```bash
# Malicious injection
aws secretsmanager tag-resource --secret-id prod-db \
  --tags Key=TransformScript,Value='s/.*/HACKED/g'
```

**Attack Surface**:
- Tag values are considered "metadata" (less protected)
- `TagResource` permission often granted broadly
- No code review for tag changes
- Hard to audit malicious patterns

#### S3 Objects Approach

**Operational Complexity**:
- Additional service dependency (S3)
- Separate IAM permissions
- Bucket policies, KMS keys, versioning
- S3 outages affect replication
- Cross-service debugging complexity

### Decision

Use **Transformation Secrets** - store transformations as secrets in Secrets Manager.

#### Design

**Transformation Secret Naming**:
```
transformations/
├── databases/
│   ├── prod-db-region-swap
│   ├── prod-db-cross-account
│   └── qa-db-to-prod
├── applications/
│   ├── app-config-prod
│   ├── api-qa-to-prod
│   └── frontend-prod
└── shared/
    ├── region-us-west-2-to-us-east-1
    └── environment-dev-to-prod
```

**Reference in Data Secret Tags**:
```bash
# Data secret references transformation secret by name
aws secretsmanager tag-resource --secret-id prod-db-credentials \
  --tags \
    Key=SecretsReplicator:Replicate,Value=true \
    Key=SecretsReplicator:TransformMode,Value=sed \
    Key=SecretsReplicator:TransformSecretName,Value=transformations/databases/prod-db-region-swap
```

**Tags only contain names, not code** - prevents injection attacks.

### Rationale

#### Security Benefits

| Aspect | Inline Tags | S3 Objects | **Transformation Secrets** |
|--------|-------------|------------|---------------------------|
| **Code Injection** | ❌ Possible | ✅ Prevented | ✅ **Prevented** |
| **IAM Granularity** | ⚠️ Low | ✅ High | ✅ **Highest** |
| **Audit Trail** | ⚠️ Partial | ✅ Yes (CloudTrail) | ✅ **Yes (CloudTrail)** |
| **Encryption at Rest** | ❌ No | ⚠️ Optional | ✅ **Always (KMS)** |
| **Versioning** | ❌ No | ✅ Yes | ✅ **Yes (Built-in)** |
| **RBAC** | ⚠️ Limited | ✅ Yes | ✅ **Yes (IAM)** |

**Transformation secrets provide**:
1. **No code injection**: Tags only reference names
2. **Strict IAM control**: Separate permissions for read vs write
3. **Audit trail**: CloudTrail logs all access and modifications
4. **Encryption**: Transformations encrypted at rest with KMS
5. **Versioning**: Built-in version control and rollback

#### Operational Benefits

**vs S3 Objects**:
- ✅ Single service (Secrets Manager only)
- ✅ Same APIs (consistent interface)
- ✅ Same IAM patterns (familiar to team)
- ✅ Same SLA (99.99% availability)
- ✅ No cross-service dependencies

**Built-in Features**:
- ✅ Versioning (automatic)
- ✅ Encryption (KMS)
- ✅ Rotation (if needed)
- ✅ Replication (native, for transformations themselves if desired)

#### IAM Separation of Duties

```json
// Security team: Manage transformations
{
  "Sid": "ManageTransformations",
  "Effect": "Allow",
  "Action": ["secretsmanager:*"],
  "Resource": "arn:aws:secretsmanager:*:*:secret:transformations/*"
}

// Developers: Read-only transformations
{
  "Sid": "ReadTransformations",
  "Effect": "Allow",
  "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
  "Resource": "arn:aws:secretsmanager:*:*:secret:transformations/*"
}

// Lambda: Read transformations, cannot write
{
  "Sid": "ReadTransformationsOnly",
  "Effect": "Allow",
  "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
  "Resource": "arn:aws:secretsmanager:*:*:secret:transformations/*"
}
```

### Consequences

#### Positive

- ✅ **Secure**: No code injection via tags
- ✅ **Simple**: Single service (Secrets Manager)
- ✅ **Auditable**: CloudTrail logs all operations
- ✅ **Versioned**: Built-in version control
- ✅ **Encrypted**: KMS encryption at rest
- ✅ **Familiar**: Same service as data secrets
- ✅ **Reliable**: Same SLA as Secrets Manager

#### Negative

- ⚠️ **Cost**: ~$0.40/transformation/month (vs free for S3)
- ⚠️ **Size limit**: 64KB max (vs 5TB for S3)

#### Mitigation

- **Cost**: $4/month for 10 transformations is negligible for production security
- **Size limit**: 64KB is sufficient for transformation scripts (typical: 1-5KB)

### Implementation Details

**Transformation Secret Structure**:

**SED Transformation**:
```
Secret Name: transformations/databases/prod-db-region-swap
Secret Value (plaintext):
# Production database DR transformation
# Version: 1.0.0
# Owner: Security Team
s/db\.us-west-2\.rds\.amazonaws\.com/db.us-east-1.rds.amazonaws.com/g
s/cache\.us-west-2\.cache\.amazonaws\.com/cache.us-east-1.cache.amazonaws.com/g
```

**JSON Transformation**:
```
Secret Name: transformations/applications/app-config-prod
Secret Value (JSON string):
{
  "$.environment": "production",
  "$.api.host": "api.prod.example.com",
  "$.database.host": "prod-db.example.com"
}
```

**Loading Logic**:
```python
def get_transform_config(tags: dict) -> dict:
    transform_secret_name = tags.get('SecretsReplicator:TransformSecretName')

    if transform_secret_name:
        # Validate name pattern (prevent injection)
        if not is_valid_transformation_secret_name(transform_secret_name):
            raise TransformationError(f"Invalid transformation secret name")

        # Load from Secrets Manager
        transformation_value = get_secret_value(transform_secret_name)

        return {
            'mode': tags.get('SecretsReplicator:TransformMode', 'sed'),
            'script': transformation_value,
            'source': 'transformation-secret'
        }

    # Fall back to default
    return get_default_transform_config()
```

**Estimated Effort**: 3-4 hours

---

## ADR-003: Hardcoded Exclusion for Transformation Secrets

**Date**: 2025-11-02 (Updated: 2025-11-03)
**Status**: Accepted
**Deciders**: Project Team
**Related**: ADR-002

### Context

**Problem**: Transformation secrets could accidentally be replicated and transformed by themselves:

```bash
# Transformation secret contains
secrets-replicator/transformations/prod-db-region-swap: "s/us-west-2/us-east-1/g"

# If this secret is tagged for replication and transformed:
Source: "s/us-west-2/us-east-1/g"
Apply: s/us-west-2/us-east-1/g
Result: "s/us-east-1/us-east-1/g"  ← CORRUPTED!
```

**Security Risks**:
1. **Source corruption**: Using transformation secret AS replication source corrupts the rules
2. **Destination corruption**: Writing TO transformation secret overwrites the rules
3. **Cascading failures**: Corrupted transformations break all secrets using them
4. **Accidental misconfiguration**: User sets DEST_SECRET_NAME to transformation secret

**Key Distinction**:
- ✅ **ALLOWED**: Lambda reads transformation secrets to load transformation rules
- ❌ **BLOCKED**: Using transformation secrets as replication source
- ❌ **BLOCKED**: Writing to transformation secrets as replication destination

### Options Considered

#### Option 1: Hardcoded Exclusion (Selected)

```python
# Lambda code explicitly excludes secrets-replicator/transformations/* prefix

# SOURCE-SIDE: Prevent using as replication source
def should_replicate(secret_name: str, tags: dict) -> bool:
    if secret_name.startswith('secrets-replicator/transformations/'):
        return False  # Never replicate transformation secrets

# DESTINATION-SIDE: Prevent writing to transformation secrets
dest_secret_name = config.dest_secret_name or secret_event.secret_id
if dest_secret_name.startswith('secrets-replicator/transformations/'):
    return {'statusCode': 400, 'body': 'Cannot replicate to transformation secret'}
```

**Pros**:
- ✅ Foolproof (cannot be bypassed)
- ✅ Simple (clear, explicit code)
- ✅ Protects both source AND destination
- ✅ Secure (no way to accidentally replicate)
- ✅ Clear error messages (400 Bad Request)
- ✅ Namespace clarity (secrets-replicator/ prefix)
- ✅ Zero config (works by convention)

**Cons**:
- ⚠️ Convention-based (users must follow naming)
- ⚠️ Prefix is configurable but has safe default

#### Option 2: Reserved Exclude Tag

```bash
# Tag transformation secrets as non-replicable
Key=SecretsReplicator:SystemReserved,Value=true
```

**Pros**:
- ✅ Flexible naming (no hardcoded prefix)
- ✅ Explicit marking

**Cons**:
- ❌ User can remove tag (unsafe)
- ❌ Must remember to tag (error-prone)
- ❌ Not foolproof

#### Option 3: IAM Deny Policy

```json
{
  "Effect": "Deny",
  "Action": "secretsmanager:PutSecretValue",
  "Resource": "arn:aws:secretsmanager:*:*:secret:transformations/*"
}
```

**Pros**:
- ✅ IAM-enforced

**Cons**:
- ❌ Doesn't prevent Lambda from trying
- ❌ Legitimate use case: replicate transformations to DR account

#### Option 4: AWS Systems Manager Parameter Store

Store transformations in Parameter Store instead of Secrets Manager.

**Pros**:
- ✅ Complete separation (different service)
- ✅ No replication risk

**Cons**:
- ❌ Two services to manage
- ❌ Different APIs
- ❌ Additional complexity

### Decision

**Implement Option 1 (Hardcoded Exclusion) with defense in depth**:

1. **Primary Defense**: Hardcoded exclusion in Lambda code
2. **Secondary Defense**: IAM Deny policy (prevent writes even if code bypassed)
3. **Tertiary Defense**: CloudWatch monitoring + alerts

### Rationale

#### Why Hardcoded Exclusion?

**Security by Convention**:
- Naming convention (`transformations/*`) is clear and intuitive
- Hardcoded exclusion is foolproof (cannot be bypassed by tags)
- Similar to reserved namespaces in many systems (`system/*`, `aws:*`, etc.)

**Precedent**:
- AWS uses reserved prefixes: `aws:*` tags, `AWS::*` CloudFormation resources
- Kubernetes uses reserved namespaces: `kube-system`, `kube-public`
- Git ignores `.git/` directory by convention

**Risk Assessment**:
- Risk of corruption: HIGH (if not excluded)
- Risk of inflexibility: LOW (prefix can be made configurable)
- Security benefit: HIGH (prevents cascading failures)

#### Why Defense in Depth?

**Multiple Layers**:
1. Code prevents Lambda from attempting replication
2. IAM prevents Lambda from writing (even if code bug)
3. Monitoring alerts on any access attempt

**If primary defense fails** (code bug), secondary defense (IAM) prevents damage.

### Implementation

#### Protection Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Transformation Secrets                       │
│              secrets-replicator/transformations/*               │
└─────────────────────────────────────────────────────────────────┘
                     ↑                           ↑
                     │                           │
             SOURCE PROTECTION          DESTINATION PROTECTION
                     │                           │
         ┌───────────┴───────────┐   ┌───────────┴──────────┐
         │ should_replicate()    │   │ Destination Check    │
         │ Returns: False        │   │ Returns: 400 Error   │
         └───────────────────────┘   └──────────────────────┘
                     │                           │
         ┌───────────┴───────────┐   ┌───────────┴──────────┐
         │ IAM: Allow Read       │   │ IAM: Deny Write      │
         │ (for loading rules)   │   │ (prevent corruption) │
         └───────────────────────┘   └──────────────────────┘
                     │                           │
         ┌───────────┴───────────────────────────┴──────────┐
         │       CloudWatch Monitoring & Alarms             │
         └──────────────────────────────────────────────────┘
```

#### 1. Source-Side Protection (Primary)

```python
# src/config.py
TRANSFORMATION_SECRET_PREFIX = os.environ.get(
    'TRANSFORMATION_SECRET_PREFIX',
    'secrets-replicator/transformations/'  # Default
)

# src/handler.py - should_replicate()
def should_replicate(secret_name: str, tags: dict, config: ReplicatorConfig) -> bool:
    """
    Determine if secret should be replicated.

    SECURITY: Transformation secrets are ALWAYS excluded to prevent
    self-referential transformations that would corrupt rules.
    """
    # LAYER 1: Hardcoded exclusion for transformation secrets
    if secret_name.startswith(config.transformation_secret_prefix):
        return False  # Never use as replication source

    # ... rest of filtering logic
```

**Purpose**: Prevents transformation secrets from being used AS replication source.

#### 2. Destination-Side Protection (Primary)

```python
# src/handler.py - lambda_handler()
# Determine destination secret name
dest_secret_name = config.dest_secret_name or secret_event.secret_id

# Check if destination would be a transformation secret (defense-in-depth)
if dest_secret_name.startswith(config.transformation_secret_prefix):
    log_event(logger, 'ERROR', 'Cannot replicate to transformation secret',
             source_secret=secret_event.secret_id,
             dest_secret=dest_secret_name)
    return {
        'statusCode': 400,
        'body': f'Cannot replicate to transformation secret: {dest_secret_name}'
    }
```

**Purpose**: Prevents writing TO transformation secrets, even with custom DEST_SECRET_NAME.

**Benefits**:
- ✅ Fast fail (before AWS API calls)
- ✅ Clear error message (400 Bad Request)
- ✅ Protects against misconfiguration

#### 3. IAM Policies (Secondary)

```yaml
# template.yaml - Lambda execution role
Policies:
  - Version: '2012-10-17'
    Statement:
      # Allow READ for loading transformation rules
      - Sid: ReadTransformationSecrets
        Effect: Allow
        Action:
          - secretsmanager:GetSecretValue
          - secretsmanager:DescribeSecret
        Resource: !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:${TransformationSecretPrefix}*'

      # Deny WRITE to prevent corruption (even if code bug)
      - Sid: DenyWriteTransformationSecrets
        Effect: Deny
        Action:
          - secretsmanager:CreateSecret
          - secretsmanager:PutSecretValue
          - secretsmanager:UpdateSecret
          - secretsmanager:DeleteSecret
        Resource: 'arn:aws:secretsmanager:*:*:secret:${TransformationSecretPrefix}*'
```

**Purpose**:
- ✅ Allow Lambda to READ transformation secrets (load rules)
- ✅ Deny Lambda from WRITING to transformation secrets (prevent corruption)
- ✅ Even if code bug bypasses checks, IAM prevents damage

#### 3. CloudWatch Monitoring (Tertiary)

```yaml
# template.yaml - CloudWatch Alarm
TransformationSecretAccessAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub ${AWS::StackName}-transformation-secret-access
    AlarmDescription: Alert when transformation secret replication is attempted
    MetricName: TransformationSecretAccessAttempt
    Namespace: SecretsReplicator
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 1
    ComparisonOperator: GreaterThanOrEqualToThreshold
    TreatMissingData: notBreaching
    AlarmActions:
      - !Ref AlertTopic
```

**Purpose**: Alert on any attempt to replicate transformation secrets.

### Consequences

#### Positive

- ✅ **Foolproof**: Cannot corrupt transformation secrets
- ✅ **Simple**: Clear convention, easy to understand
- ✅ **Secure**: Multi-layered defense
- ✅ **Predictable**: Consistent behavior
- ✅ **Monitorable**: Alerts on violations

#### Negative

- ⚠️ **Convention-based**: Users must follow naming pattern
- ⚠️ **Hardcoded**: Changing prefix requires code update (but configurable)

#### Edge Cases

**What if users want to replicate transformation secrets?**

**Use Case**: Replicate transformations from primary to DR account.

**Solution**: Deploy separate replication stack with:
```bash
# Stack for transformation replication
sam deploy --stack-name transformation-replicator \
  --parameter-overrides \
    SourceSecretPattern='transformations/.*' \
    TransformationSecretPrefix='transformation-replicas/' \
    DestAccount=222222222222
```

**Different prefix** avoids infinite loop while allowing legitimate replication.

### Testing Strategy

**Unit Tests**:
```python
def test_transformation_secret_excluded():
    """Verify transformation secrets are never replicated."""
    assert not should_replicate('transformations/prod-db', {})
    assert not should_replicate('transformations/databases/test', {})

def test_transformation_secret_with_replicate_tag_still_excluded():
    """Verify tags cannot override hardcoded exclusion."""
    tags = {'SecretsReplicator:Replicate': 'true'}
    assert not should_replicate('transformations/prod-db', tags)

def test_regular_secret_not_affected():
    """Verify regular secrets are not excluded by transformation check."""
    tags = {'SecretsReplicator:Replicate': 'true'}
    assert should_replicate('prod-db-credentials', tags)

def test_transformation_prefix_boundary():
    """Verify only exact prefix matches are excluded."""
    assert not should_replicate('transformations/test', {})  # Excluded
    assert should_replicate('transformations-backup', {})     # NOT excluded
    assert should_replicate('my-transformations/test', {})    # NOT excluded
```

**Integration Tests**:
1. Create transformation secret
2. Tag it for replication
3. Update it (trigger EventBridge)
4. Verify Lambda skips it
5. Verify CloudWatch alarm triggered

**Estimated Testing Effort**: 2 hours

---

## Summary

### Decisions Made

1. **ADR-001**: Lambda-side filtering with tag support (OR logic)
2. **ADR-002**: Transformation secrets architecture (security over S3)
3. **ADR-003**: Hardcoded exclusion for `transformations/*` (defense in depth)

### Key Principles

- **Security First**: Prevent code injection, strict IAM control
- **Simplicity**: Single service (Secrets Manager), clear conventions
- **Defense in Depth**: Multiple security layers
- **Operational Excellence**: Built-in versioning, audit trail, monitoring

### Implementation Order

1. ✅ Document decisions (this file)
2. ⏭️ Implement filtering logic (ADR-001)
3. ⏭️ Implement transformation secrets (ADR-002)
4. ⏭️ Implement hardcoded exclusion (ADR-003)
5. ⏭️ Add unit tests
6. ⏭️ Update documentation
7. ⏭️ Test end-to-end

### Estimated Total Effort

- Documentation: 1 hour ✅
- Implementation: 8-10 hours
- Testing: 3-4 hours
- Documentation updates: 2 hours
- **Total**: ~14-17 hours

---

**Last Updated**: 2025-11-02
**Version**: 1.0.0
**Status**: Ready for Implementation
