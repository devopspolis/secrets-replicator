# SECRETS_FILTER Implementation Plan

## Overview

This document outlines the implementation plan for the refined SECRETS_FILTER approach, which replaces tag-based filtering with a centralized, composable filter configuration system.

## Implementation Summary

**Goal**: Replace tag-based filtering (`SecretsReplicator:TransformSecretName` tags) with centralized filter configuration stored in Secrets Manager.

**Key Change**: Environment variable `SECRETS_FILTER` contains comma-separated list of filter secret names. Each filter secret contains key-value mappings of secret patterns to transformation names.

## Architecture

### Configuration Model

```
Environment Variable (Lambda):
  SECRETS_FILTER = "secrets-replicator/filters/prod,secrets-replicator/filters/db"

Filter Secret 1 (secrets-replicator/filters/prod):
  {
    "app/prod/*": "region-swap",
    "api/prod/*": "endpoint-update",
    "critical-secret-1": ""
  }

Filter Secret 2 (secrets-replicator/filters/db):
  {
    "db/prod/*": "connection-string-transform",
    "db/staging/*": ""
  }

Transformation Secrets (existing):
  secrets-replicator/transformations/region-swap
  secrets-replicator/transformations/endpoint-update
  secrets-replicator/transformations/connection-string-transform
```

### Pattern Matching Rules

1. **Exact Match** (highest priority): `"mysecret"` matches only `"mysecret"`
2. **Glob Pattern**: `"app/*"` matches `"app/prod"`, `"app/staging/db"`, etc.
3. **No Match**: Secret is not replicated (default deny)

### Transformation Mapping

- **Non-empty value**: Name of transformation secret (prefix auto-prepended)
  - `"region-swap"` → `secrets-replicator/transformations/region-swap`
- **Empty string or null**: Replicate without transformation
  - `""` or `null` → No transformation applied

## Implementation Phases

### Phase 1: Core Implementation (Backwards Compatible)

**Goal**: Add SECRETS_FILTER support while maintaining tag-based filtering as fallback

**Files to Modify**:
1. `src/config.py` - Add `secrets_filter` configuration field
2. `src/filters.py` (NEW) - Filter loading, caching, and pattern matching logic
3. `src/handler.py` - Update filtering logic to use new system
4. `template.yaml` - Add `SecretsFilter` parameter
5. `samconfig.toml` - Add default values for dev/qa/prod

**Backwards Compatibility**:
- If `SECRETS_FILTER` is not set → use legacy tag-based filtering
- If `SECRETS_FILTER` is set → use new filter-based filtering
- Both systems can coexist during migration

### Phase 2: Testing & Validation

**Goal**: Comprehensive testing of new filtering system

**Test Coverage**:
1. Unit tests for pattern matching (exact, glob, no match)
2. Unit tests for filter loading and caching
3. Integration tests with mock Secrets Manager
4. End-to-end tests with real AWS resources
5. Performance tests (cold start, warm start, caching)

### Phase 3: Documentation & Examples

**Goal**: Complete documentation for users

**Deliverables**:
1. Updated README with SECRETS_FILTER configuration
2. Example filter secrets for common scenarios
3. Migration guide from tag-based to filter-based
4. Troubleshooting guide

### Phase 4: Migration & Cleanup

**Goal**: Remove legacy tag-based filtering code

**Steps**:
1. Migrate all existing deployments to SECRETS_FILTER
2. Make `SECRETS_FILTER` required (remove default)
3. Remove tag-based filtering code
4. Remove unused environment variables
5. Update IAM policies (no longer need `describe_secret` for tags)

## Detailed Implementation

### 1. Configuration (src/config.py)

**Changes**:
- Add `secrets_filter: Optional[str]` field to `ReplicatorConfig`
- Add `secrets_filter_cache_ttl: int` field (default: 300 seconds)
- Parse `SECRETS_FILTER` environment variable
- Parse `SECRETS_FILTER_CACHE_TTL` environment variable

**Example**:
```python
@dataclass
class ReplicatorConfig:
    # ... existing fields ...

    # New fields for SECRETS_FILTER
    secrets_filter: Optional[str] = None  # Comma-separated list of filter secret names
    secrets_filter_cache_ttl: int = 300   # Cache TTL in seconds (5 minutes)

    # Deprecated fields (will be removed in Phase 4)
    source_secret_pattern: Optional[str] = None
    source_secret_list: List[str] = field(default_factory=list)
    source_include_tags: List[tuple[str, str]] = field(default_factory=list)
    source_exclude_tags: List[tuple[str, str]] = field(default_factory=list)
```

### 2. Filter Logic (src/filters.py - NEW FILE)

**Purpose**: Centralize filter loading, caching, and pattern matching

**Functions**:

#### `load_filter_configuration(filter_list: str, client) -> Dict[str, Optional[str]]`
- Parse comma-separated list of filter secret names
- Load each filter secret from Secrets Manager
- Merge filter dictionaries (later overrides earlier)
- Return merged filter mapping

#### `get_cached_filters(filter_list: str, ttl: int, client) -> Dict[str, Optional[str]]`
- Check cache validity (TTL, filter list match)
- Return cached filters if valid
- Load fresh filters if cache invalid
- Update cache with new data

#### `match_secret_pattern(secret_name: str, pattern: str) -> bool`
- Implement glob pattern matching
- Handle exact match (no wildcard)
- Handle prefix wildcard (`app/*`)
- Handle suffix wildcard (`*/prod`)
- Handle middle wildcard (`app/*/db`)

#### `find_matching_filter(secret_name: str, filters: Dict[str, Optional[str]]) -> Union[Optional[str], bool]`
- Check exact match first (highest priority)
- Check glob patterns in order
- Return transformation name (or None for no transform)
- Return False if no match found

#### `should_replicate_secret(secret_name: str, config: ReplicatorConfig, client) -> Tuple[bool, Optional[str]]`
- Hardcoded exclusions (transformation secrets, filter secrets)
- Load and check filters
- Find matching pattern
- Return (should_replicate: bool, transformation_name: Optional[str])

**Global Cache**:
```python
_filter_cache = {
    'data': None,           # Dict[str, Optional[str]] - merged filters
    'loaded_at': 0,         # float - timestamp
    'ttl': 300,            # int - cache TTL in seconds
    'source_list': None    # str - comma-separated filter secret names
}
```

### 3. Handler Updates (src/handler.py)

**Changes**:

#### Import new filter module
```python
from filters import should_replicate_secret
```

#### Replace existing filtering logic
```python
# OLD (tag-based):
should_replicate, tags = check_tags_and_filters(secret_name, config)
transform_secret_name = tags.get('SecretsReplicator:TransformSecretName')

# NEW (filter-based):
should_replicate, transform_secret_name = should_replicate_secret(
    secret_name,
    config,
    source_client
)
```

#### Update transformation loading
```python
if transform_secret_name:
    # Add prefix if not already present
    if not transform_secret_name.startswith(config.transformation_secret_prefix):
        transform_secret_name = f"{config.transformation_secret_prefix}{transform_secret_name}"

    logger.info(f"Loading transformation: {transform_secret_name}")
    # ... existing transformation loading logic ...
else:
    logger.info(f"Replicating without transformation")
    # ... replicate without transformation ...
```

### 4. SAM Template (template.yaml)

**New Parameter**:
```yaml
Parameters:
  SecretsFilter:
    Type: String
    Description: |
      Comma-separated list of Secrets Manager secret names containing filter configurations.
      Each filter secret should contain JSON key-value mappings of secret patterns to transformation names.
      Example: secrets-replicator/filters/production,secrets-replicator/filters/databases
      Leave empty to disable filtering (allow all secrets).
    Default: ''

  SecretsFilterCacheTTL:
    Type: Number
    Description: Cache TTL for filter configuration in seconds (default 300 = 5 minutes)
    Default: 300
    MinValue: 0
    MaxValue: 3600
```

**Environment Variables**:
```yaml
Environment:
  Variables:
    # ... existing variables ...
    SECRETS_FILTER: !Ref SecretsFilter
    SECRETS_FILTER_CACHE_TTL: !Ref SecretsFilterCacheTTL
```

**IAM Permissions** (add to Lambda execution role):
```yaml
- Sid: ReadFilterSecrets
  Effect: Allow
  Action:
    - secretsmanager:GetSecretValue
  Resource:
    - !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:secrets-replicator/filters/*'

- Sid: DenyWriteFilterSecrets
  Effect: Deny
  Action:
    - secretsmanager:CreateSecret
    - secretsmanager:PutSecretValue
    - secretsmanager:UpdateSecret
    - secretsmanager:DeleteSecret
  Resource:
    - !Sub 'arn:aws:secretsmanager:*:*:secret:secrets-replicator/filters/*'
```

### 5. SAM Config (samconfig.toml)

**Add default values**:
```toml
[dev.deploy.parameters]
# ... existing parameters ...
parameter_overrides = [
  "Environment=dev",
  "DestinationRegion=us-east-1",
  "SecretsFilter=secrets-replicator/filters/dev",
  "SecretsFilterCacheTTL=300"
]

[qa.deploy.parameters]
# ... existing parameters ...
parameter_overrides = [
  "Environment=qa",
  "DestinationRegion=us-east-1",
  "SecretsFilter=secrets-replicator/filters/qa",
  "SecretsFilterCacheTTL=300"
]

[prod.deploy.parameters]
# ... existing parameters ...
parameter_overrides = [
  "Environment=prod",
  "DestinationRegion=us-east-1",
  "SecretsFilter=secrets-replicator/filters/prod",
  "SecretsFilterCacheTTL=300"
]
```

## Example Filter Secrets

### Example 1: Production Application Secrets

**Secret Name**: `secrets-replicator/filters/prod`

**Content**:
```json
{
  "app/prod/*": "region-swap",
  "api/prod/*": "endpoint-update",
  "auth/prod/*": "auth-transform",
  "critical-secret-prod": "",
  "backup-secret-prod": null
}
```

**Usage**:
- `app/prod/myapp` → Matches `app/prod/*`, uses `region-swap` transformation
- `api/prod/gateway` → Matches `api/prod/*`, uses `endpoint-update` transformation
- `critical-secret-prod` → Matches exactly, no transformation
- `db/prod/main` → No match, not replicated

### Example 2: Database Secrets

**Secret Name**: `secrets-replicator/filters/databases`

**Content**:
```json
{
  "db/prod/postgres": "postgres-connection-transform",
  "db/prod/mysql": "mysql-connection-transform",
  "db/staging/*": "",
  "rds/*": "rds-endpoint-swap"
}
```

### Example 3: Multi-Environment

**Secret Name**: `secrets-replicator/filters/multi-env`

**Content**:
```json
{
  "app/*/api-key": "api-key-transform",
  "app/*/database": "db-connection-transform",
  "*/prod": "prod-transform",
  "*/staging": "staging-transform"
}
```

**Pattern Matching**:
- `app/prod/api-key` → Matches `app/*/api-key` (first match wins)
- `app/staging/api-key` → Matches `app/*/api-key`
- `service/prod` → Matches `*/prod`

## Testing Plan

### Unit Tests (tests/unit/test_filters.py - NEW)

**Test Cases**:

1. **Pattern Matching**
   - Exact match
   - Prefix wildcard (`app/*`)
   - Suffix wildcard (`*/prod`)
   - Middle wildcard (`app/*/db`)
   - Multiple wildcards (`app/*/prod/*`)
   - No match

2. **Filter Loading**
   - Single filter secret
   - Multiple filter secrets (merging)
   - Empty filter list
   - Invalid JSON in filter secret
   - Missing filter secret (error handling)
   - Later filters override earlier filters

3. **Caching**
   - Cache hit (within TTL)
   - Cache miss (expired TTL)
   - Cache invalidation (filter list changed)
   - Multiple Lambda invocations (warm starts)

4. **Replication Decision**
   - Match with transformation
   - Match without transformation (empty string)
   - Match without transformation (null)
   - No match (deny)
   - Hardcoded exclusions (transformation secrets, filter secrets)

### Integration Tests (tests/integration/test_filter_integration.py - NEW)

**Test Cases**:

1. **End-to-End Filtering**
   - Create test filter secret
   - Create test source secret (matching pattern)
   - Trigger Lambda
   - Verify replication occurred
   - Verify transformation applied

2. **Multiple Filter Secrets**
   - Create multiple filter secrets
   - Create source secrets matching different filters
   - Trigger Lambda
   - Verify correct transformations applied

3. **Filter Updates**
   - Create filter secret
   - Create source secret
   - Update filter secret (change transformation)
   - Wait for cache expiration
   - Trigger Lambda
   - Verify new transformation applied

### Performance Tests

**Metrics to Measure**:
- Cold start latency (with filter loading)
- Warm start latency (with cached filters)
- Cache hit rate
- API call count (GetSecretValue)
- Memory usage

**Test Scenarios**:
1. Single filter secret, 10 patterns
2. Multiple filter secrets (3), 30 patterns total
3. 100 concurrent Lambda invocations (cache effectiveness)

## Migration Guide

### Step 1: Create Filter Secrets

For each environment, create a filter secret:

```bash
# Development
aws secretsmanager create-secret \
  --name secrets-replicator/filters/dev \
  --description "Development environment filter configuration" \
  --secret-string '{
    "test/*": "",
    "dev/*": "dev-transform"
  }' \
  --region us-west-2

# Production
aws secretsmanager create-secret \
  --name secrets-replicator/filters/prod \
  --description "Production environment filter configuration" \
  --secret-string '{
    "app/prod/*": "region-swap",
    "db/prod/*": "db-transform",
    "critical-secret-prod": ""
  }' \
  --region us-west-2
```

### Step 2: Document Current Tag-Based Configuration

List all secrets with `SecretsReplicator:TransformSecretName` tags:

```bash
# List all secrets with replication tags
aws secretsmanager list-secrets --region us-west-2 \
  --query 'SecretList[?Tags[?Key==`SecretsReplicator:TransformSecretName`]].[Name,Tags]' \
  --output table
```

### Step 3: Convert Tags to Filter Configuration

For each tagged secret, add an entry to the appropriate filter secret:

**Tag-Based (OLD)**:
```
Secret: app/prod/myapp
Tag: SecretsReplicator:TransformSecretName = region-swap
```

**Filter-Based (NEW)**:
```json
{
  "app/prod/myapp": "region-swap"
}
```

Or use patterns for multiple secrets:
```json
{
  "app/prod/*": "region-swap"
}
```

### Step 4: Deploy with SECRETS_FILTER

Update deployment to use new configuration:

```bash
sam deploy \
  --stack-name secrets-replicator-dev \
  --parameter-overrides \
    Environment=dev \
    DestinationRegion=us-east-1 \
    SecretsFilter=secrets-replicator/filters/dev \
  --no-confirm-changeset
```

### Step 5: Validate Replication

Test replication with new filtering:

```bash
# Create or update a test secret
aws secretsmanager put-secret-value \
  --secret-id dev/test-secret \
  --secret-string '{"test":"value"}' \
  --region us-west-2

# Check Lambda logs
aws logs tail /aws/lambda/secrets-replicator-dev-replicator \
  --region us-west-2 \
  --follow

# Verify destination secret
aws secretsmanager get-secret-value \
  --secret-id dev/test-secret \
  --region us-east-1
```

### Step 6: Remove Tags (Optional)

Once filter-based replication is validated, remove old tags:

```bash
aws secretsmanager untag-resource \
  --secret-id app/prod/myapp \
  --tag-keys SecretsReplicator:TransformSecretName SecretsReplicator:TransformMode \
  --region us-west-2
```

## Security Considerations

### Defense-in-Depth

**Layer 1**: Hardcoded exclusions
- Filter secrets: `secrets-replicator/filters/*`
- Transformation secrets: `secrets-replicator/transformations/*`

**Layer 2**: IAM Deny policy
- Deny write operations to filter and transformation secrets
- Prevent accidental replication of configuration

**Layer 3**: Filter-based allow list
- Default deny (no filter match = no replication)
- Explicit patterns required for replication

### IAM Permissions

**Required Permissions**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadFilterSecrets",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:us-west-2:*:secret:secrets-replicator/filters/*"
    },
    {
      "Sid": "DenyWriteFilterSecrets",
      "Effect": "Deny",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:UpdateSecret",
        "secretsmanager:DeleteSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:secrets-replicator/filters/*"
    }
  ]
}
```

### Circular Dependency Prevention

**Problem**: If filter secrets are replicated, infinite loop could occur

**Solution**: Hardcoded exclusion in `should_replicate_secret()`:
```python
# Hardcoded exclusions
if secret_name.startswith('secrets-replicator/filters/'):
    return (False, None)
if secret_name.startswith(config.transformation_secret_prefix):
    return (False, None)
```

### Cache Poisoning Mitigation

**Risk**: Compromised filter secret could affect all replications

**Mitigations**:
1. **Short Cache TTL**: 5-minute default (configurable)
2. **CloudTrail Monitoring**: Alert on filter secret changes
3. **Least-Privilege IAM**: Restrict who can modify filter secrets
4. **Audit Trail**: CloudTrail tracks all filter secret access
5. **Version History**: Secrets Manager maintains version history

## Performance Optimization

### Caching Strategy

**Cache Key**: Comma-separated list of filter secret names
**Cache Value**: Merged filter dictionary
**Cache TTL**: 300 seconds (5 minutes) default
**Cache Invalidation**: TTL expiration or filter list change

### API Call Reduction

**Current (Tag-Based)**:
- Every invocation: 1× `describe_secret` (get tags)

**New (Filter-Based)**:
- Cold start: M× `get_secret_value` (M = number of filter secrets)
- Warm start: 0× API calls (cached)

**Improvement**:
- Cold start: Slightly slower if M > 1
- Warm start: 50-100ms faster (no describe_secret call)
- Steady state: Significant improvement due to caching

### Memory Usage

**Filter Storage**:
- Average filter secret: 1-5 KB
- 3 filter secrets: ~15 KB
- Negligible impact on Lambda memory (256 MB)

**Cache Storage**:
- Merged filter dict: ~5-10 KB
- Stored in global variable (persists across invocations)
- Minimal memory footprint

## Rollback Plan

If issues arise during deployment:

### Rollback Step 1: Disable SECRETS_FILTER

Remove `SecretsFilter` parameter from deployment:

```bash
sam deploy \
  --stack-name secrets-replicator-dev \
  --parameter-overrides \
    Environment=dev \
    DestinationRegion=us-east-1 \
    SecretsFilter='' \
  --no-confirm-changeset
```

With empty `SECRETS_FILTER`, Lambda falls back to tag-based filtering.

### Rollback Step 2: Restore Tags

If tags were removed, restore them:

```bash
aws secretsmanager tag-resource \
  --secret-id app/prod/myapp \
  --tags Key=SecretsReplicator:TransformSecretName,Value=region-swap \
  --region us-west-2
```

### Rollback Step 3: Monitor

Monitor Lambda logs and metrics to ensure replication resumes:

```bash
aws logs tail /aws/lambda/secrets-replicator-dev-replicator \
  --region us-west-2 \
  --follow
```

## Success Criteria

### Phase 1 Complete When:
- [ ] `src/filters.py` created with all filter logic
- [ ] `src/config.py` updated with `secrets_filter` fields
- [ ] `src/handler.py` updated to use new filtering
- [ ] `template.yaml` updated with new parameters and IAM permissions
- [ ] `samconfig.toml` updated with default values
- [ ] Unit tests pass with 100% coverage of filter logic
- [ ] Integration tests pass for basic filtering scenarios
- [ ] Deployment succeeds to dev environment
- [ ] Manual testing validates filtering works correctly
- [ ] Performance metrics show improved warm start latency
- [ ] Backwards compatibility verified (empty SECRETS_FILTER uses tag-based)

### Phase 2 Complete When:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Performance tests show expected improvements
- [ ] Edge cases handled (invalid JSON, missing secrets, etc.)
- [ ] Error handling validated
- [ ] Retry logic tested

### Phase 3 Complete When:
- [ ] README updated with SECRETS_FILTER documentation
- [ ] Example filter secrets created
- [ ] Migration guide complete
- [ ] Troubleshooting guide updated
- [ ] Architecture diagram updated

### Phase 4 Complete When:
- [ ] All deployments migrated to SECRETS_FILTER
- [ ] Tag-based code removed
- [ ] Unused environment variables removed
- [ ] IAM policies updated (removed describe_secret for tags)
- [ ] Documentation updated (removed tag-based references)
- [ ] Version bumped to 1.0.0 (breaking change)

## Timeline Estimate

- **Phase 1**: 4-6 hours (core implementation)
- **Phase 2**: 2-3 hours (testing)
- **Phase 3**: 2-3 hours (documentation)
- **Phase 4**: 1-2 hours (cleanup)

**Total**: 9-14 hours

## Notes

- Implementation focuses on simplicity and maintainability
- Glob pattern matching preferred over regex (simpler, safer)
- Caching is critical for performance (warm start optimization)
- Backwards compatibility ensures safe migration
- Defense-in-depth prevents circular dependencies
- Composable filter sets enable team collaboration
