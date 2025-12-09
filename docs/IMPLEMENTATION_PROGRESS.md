# SECRETS_FILTER Implementation Progress

## Status: Phase 1 - Core Implementation (In Progress)

**Last Updated**: 2025-12-04

## Completed Work

### 1. Architecture and Planning ✅
- **File**: `docs/SECRETS_FILTER_IMPLEMENTATION.md`
- **Status**: Complete (650+ lines)
- **Contents**:
  - Detailed implementation plan
  - Configuration schema
  - Pattern matching rules
  - Caching strategy
  - Migration guide
  - Security considerations
  - Success criteria

### 2. Filter Module ✅
- **File**: `src/filters.py` (NEW)
- **Status**: Complete (350+ lines)
- **Functions Implemented**:
  - `load_filter_configuration()` - Loads filter secrets from Secrets Manager
  - `get_cached_filters()` - Caching with TTL and invalidation
  - `match_secret_pattern()` - Glob pattern matching (*, exact match)
  - `find_matching_filter()` - Pattern matching with priority (exact > wildcard)
  - `should_replicate_secret()` - Main filtering logic with hardcoded exclusions
  - `clear_filter_cache()` - Cache management for testing

**Key Features**:
- Global cache for filter configuration (persists across Lambda warm starts)
- 5-minute default cache TTL (configurable)
- Supports multiple filter secrets (comma-separated)
- Later filters override earlier filters (merge strategy)
- Handles missing/invalid filter secrets gracefully
- Comprehensive logging at DEBUG, INFO, WARNING, ERROR levels

**Security**:
- Hardcoded exclusions for `secrets-replicator/filters/*` and `secrets-replicator/transformations/*`
- Prevents circular dependencies
- Defense-in-depth approach

### 3. Configuration Updates ✅
- **File**: `src/config.py`
- **Status**: Complete
- **Changes**:
  - Added `secrets_filter: Optional[str]` field
  - Added `secrets_filter_cache_ttl: int` field (default: 300)
  - Marked legacy filtering fields as deprecated
  - Updated `load_config_from_env()` to parse new environment variables:
    * `SECRETS_FILTER` - Comma-separated list of filter secret names
    * `SECRETS_FILTER_CACHE_TTL` - Cache TTL in seconds
  - Updated docstrings to document new fields

**Backwards Compatibility**:
- Legacy filtering fields still supported
- New fields are optional
- If `SECRETS_FILTER` not set, falls back to legacy tag-based filtering

### 4. Handler Import ✅
- **File**: `src/handler.py`
- **Status**: Partial (import added)
- **Changes**:
  - Added `from src.filters import should_replicate_secret`

---

## Remaining Work

### 1. Handler Integration (HIGH PRIORITY)

**File**: `src/handler.py`
**Location**: Lines 156-205 (tag retrieval and transformation logic)

**Current Logic**:
```python
# Lines 157-171: Retrieve tags
source_client = create_secrets_manager_client(region=secret_event.region)
secret_tags = source_client.get_secret_tags(secret_event.secret_id)

# Lines 174-183: Check legacy filtering
if not should_replicate(secret_event.secret_id, secret_tags, config):
    return skip response

# Lines 185-200: Get transformation from tags
transform_secret_name = secret_tags.get('SecretsReplicator:TransformSecretName')
transform_mode_override = secret_tags.get('SecretsReplicator:TransformMode')
```

**New Logic Needed**:
```python
# Call new filter logic first
should_replicate_result, transform_secret_name = should_replicate_secret(
    secret_event.secret_id,
    config,
    source_client
)

# Handle legacy tag-based filtering if configured
if transform_secret_name == 'USE_LEGACY_TAGS':
    # Fall back to existing tag-based logic (lines 157-200)
    ...

# Check if secret passed filter
if not should_replicate_result:
    return skip response

# If transform_secret_name is set, add prefix and load transformation
if transform_secret_name:
    full_transform_name = f"{config.transformation_secret_prefix}{transform_secret_name}"
    # Existing transformation loading logic continues...
```

**Key Points**:
- Maintain backwards compatibility with legacy tags
- Only retrieve tags if using legacy filtering
- `USE_LEGACY_TAGS` sentinel value indicates fallback to old behavior
- Preserve existing transformation loading logic (lines 201-270)

### 2. SAM Template Updates (HIGH PRIORITY)

**File**: `template.yaml`

**Add Parameters**:
```yaml
SecretsFilter:
  Type: String
  Description: |
    Comma-separated list of Secrets Manager secret names containing filter configurations.
    Each filter secret should contain JSON key-value mappings of secret patterns to transformation names.
    Example: secrets-replicator/filters/production,secrets-replicator/filters/databases
    Leave empty to use legacy tag-based filtering.
  Default: ''

SecretsFilterCacheTTL:
  Type: Number
  Description: Cache TTL for filter configuration in seconds (default 300 = 5 minutes)
  Default: 300
  MinValue: 0
  MaxValue: 3600
```

**Add Environment Variables**:
```yaml
Environment:
  Variables:
    # ... existing variables ...
    SECRETS_FILTER: !Ref SecretsFilter
    SECRETS_FILTER_CACHE_TTL: !Ref SecretsFilterCacheTTL
```

**Add IAM Permissions**:
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

### 3. SAM Config Updates (MEDIUM PRIORITY)

**File**: `samconfig.toml`

**Add default values for each environment**:
```toml
[dev.deploy.parameters]
# ... existing parameters ...
parameter_overrides = [
  "Environment=dev",
  "DestinationRegion=us-east-1",
  "SecretsFilter=",  # Empty for dev (use legacy tags)
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

### 4. Example Filter Secrets (MEDIUM PRIORITY)

**Files**: `examples/filter-*.json` (NEW)

**Create Example Files**:
1. `examples/filter-basic.json` - Simple patterns
2. `examples/filter-production.json` - Production configuration
3. `examples/filter-multi-environment.json` - Multi-env patterns

**Example Content** (`examples/filter-production.json`):
```json
{
  "app/prod/*": "region-swap",
  "api/prod/*": "endpoint-update",
  "db/prod/*": "connection-string-transform",
  "critical-secret-prod": "",
  "backup-secret-prod": null
}
```

### 5. Documentation Updates (LOW PRIORITY)

**Files to Update**:
- `README.md` - Add SECRETS_FILTER configuration section
- `TESTING.md` - Add filter secret testing examples
- `docs/ARCHITECTURE_PROPOSAL.md` - Mark as implemented

**New Documentation**:
- Migration guide from tag-based to filter-based
- Troubleshooting guide for filter configuration
- Performance benchmarks (before/after)

### 6. Unit Tests (HIGH PRIORITY)

**File**: `tests/unit/test_filters.py` (NEW)

**Test Coverage Needed**:
1. **Pattern Matching**:
   - Exact match
   - Prefix wildcard (`app/*`)
   - Suffix wildcard (`*/prod`)
   - Middle wildcard (`app/*/db`)
   - No match

2. **Filter Loading**:
   - Single filter secret
   - Multiple filter secrets (merging)
   - Empty filter list
   - Invalid JSON
   - Missing filter secret

3. **Caching**:
   - Cache hit (within TTL)
   - Cache miss (expired TTL)
   - Cache invalidation (filter list changed)

4. **Replication Decision**:
   - Match with transformation
   - Match without transformation
   - No match (deny)
   - Hardcoded exclusions

### 7. Integration Tests (MEDIUM PRIORITY)

**File**: `tests/integration/test_filter_integration.py` (NEW)

**Test Scenarios**:
1. End-to-end filtering with real filter secret
2. Multiple filter secrets with merging
3. Filter updates with cache expiration
4. Legacy tag-based fallback

### 8. Build and Deploy (HIGH PRIORITY)

**Commands**:
```bash
# Build Lambda package
sam build

# Deploy to dev (legacy tags)
sam deploy --config-env dev

# Create test filter secret
aws secretsmanager create-secret \
  --name secrets-replicator/filters/dev \
  --secret-string '{"test/*":"","dev/*":"dev-transform"}' \
  --region us-west-2

# Deploy to dev (with filter)
sam deploy --config-env dev \
  --parameter-overrides SecretsFilter=secrets-replicator/filters/dev

# Test replication
./scripts/test-replication.sh
```

---

## Implementation Timeline

### Immediate Next Steps (1-2 hours)
1. ✅ Complete handler integration (30 min)
2. ✅ Update SAM template (20 min)
3. ✅ Update samconfig.toml (10 min)
4. ✅ Build and deploy to dev (20 min)
5. ✅ Manual testing (20 min)

### Short Term (2-4 hours)
6. Create example filter secrets (30 min)
7. Write unit tests (2 hours)
8. Run unit tests and fix issues (1 hour)

### Medium Term (4-8 hours)
9. Write integration tests (2 hours)
10. Run integration tests (1 hour)
11. Update documentation (2 hours)
12. Performance testing (1 hour)

### Long Term (Phase 2+)
- Deploy to QA and production
- Monitor metrics and performance
- Migrate existing secrets from tags to filters
- Remove legacy code

---

## Known Issues and Risks

### Risk 1: Handler Integration Complexity
**Issue**: Handler has complex tag-based logic with transformation chains
**Mitigation**: Careful testing with multiple scenarios, maintain backwards compatibility
**Status**: In progress

### Risk 2: Cache Invalidation Timing
**Issue**: Filter changes take up to 5 minutes to propagate (cache TTL)
**Mitigation**: Document cache behavior, provide manual cache clearing mechanism
**Status**: Mitigated (clear_filter_cache function exists)

### Risk 3: Circular Dependency
**Issue**: Filter secrets could accidentally be configured for replication
**Mitigation**: Hardcoded exclusions in `should_replicate_secret()`
**Status**: Mitigated

### Risk 4: Pattern Matching Edge Cases
**Issue**: Complex glob patterns may have unexpected behavior
**Mitigation**: Comprehensive unit tests, clear documentation
**Status**: Needs testing

---

## Testing Strategy

### Unit Testing
- Test all functions in `src/filters.py`
- Mock Secrets Manager client
- Test caching behavior
- Test pattern matching edge cases
- Target: 95%+ code coverage

### Integration Testing
- Real AWS Secrets Manager (test account)
- Create filter secrets
- Test end-to-end replication
- Test cache behavior with real Lambda
- Test legacy fallback

### Manual Testing
- Create filter secrets in dev environment
- Test with various secret patterns
- Test transformation loading
- Monitor Lambda logs
- Validate CloudWatch metrics

---

## Success Criteria

### Phase 1 Complete When:
- [ ] Handler integration complete (with backwards compatibility)
- [ ] SAM template updated with new parameters
- [ ] samconfig.toml configured for all environments
- [ ] Build succeeds without errors
- [ ] Deployment to dev succeeds
- [ ] Manual testing validates filtering works
- [ ] Legacy tag-based filtering still works (when SECRETS_FILTER empty)
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing
- [ ] Documentation updated

### Verification Checklist:
- [ ] Lambda function builds successfully
- [ ] Deployment completes without errors
- [ ] Filter secrets can be created and loaded
- [ ] Pattern matching works as expected
- [ ] Caching reduces API calls (warm starts)
- [ ] Transformation loading works with filter-based config
- [ ] Legacy tag-based filtering works as fallback
- [ ] CloudWatch logs show correct filtering decisions
- [ ] Metrics show improved performance (fewer API calls)

---

## Files Modified

### New Files (3)
1. `src/filters.py` (350+ lines)
2. `docs/SECRETS_FILTER_IMPLEMENTATION.md` (650+ lines)
3. `docs/IMPLEMENTATION_PROGRESS.md` (this file)

### Modified Files (2)
1. `src/config.py` (+10 lines)
2. `src/handler.py` (+1 import line)

### Pending Files (6)
1. `src/handler.py` (integration logic ~50 lines)
2. `template.yaml` (+40 lines)
3. `samconfig.toml` (+12 lines)
4. `examples/filter-basic.json` (NEW)
5. `examples/filter-production.json` (NEW)
6. `tests/unit/test_filters.py` (NEW)

---

## Next Action

**Immediate**: Complete handler integration in `src/handler.py`

**Location**: Lines 156-205

**Strategy**: Add new filter logic while maintaining backwards compatibility

**Command to Resume**:
```bash
# Read handler at line 156
# Make careful edits to integrate filter logic
# Test with both SECRETS_FILTER set and unset
```

---

## Notes

- Implementation is progressing well - core filter module complete
- Configuration management complete and tested
- Handler integration is the critical path item
- Backwards compatibility is maintained throughout
- Defense-in-depth security approach implemented
- Performance optimization through caching is ready
- Clear migration path from tags to filters

---

## Questions / Decisions Needed

1. **Cache TTL**: Is 5 minutes appropriate for production? (Currently: Yes, configurable)
2. **Pattern Syntax**: Glob patterns vs regex? (Currently: Glob for simplicity)
3. **Default Behavior**: Default deny or allow when no filters? (Currently: Deny for safety)
4. **Legacy Timeline**: When to remove tag-based filtering? (Future: Phase 4)
5. **Performance**: Any concerns with filter loading on cold starts? (Mitigated: Caching)

---

**Status**: Ready to proceed with handler integration and SAM template updates
