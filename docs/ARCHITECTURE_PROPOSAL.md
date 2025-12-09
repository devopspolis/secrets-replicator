# Architecture Proposal: Centralized Configuration for Filtering and Transformations

## Executive Summary

**Recommendation: Option 3 - Hybrid Approach (Configuration Secret with Environment Variable Override)**

This proposal analyzes replacing the current tag-based filtering and transformation configuration with a centralized, declarative configuration approach using environment variables and/or Secrets Manager.

---

## Current Architecture Analysis

### Current Implementation

**Filtering Mechanism** (`handler.py:30-90`):
```python
def should_replicate(secret_name: str, tags: Dict[str, str], config: ReplicatorConfig) -> bool:
    # Layer 1: Hardcoded exclusion (transformation secrets)
    # Layer 2: Exclude tags
    # Layer 3: Include filters (pattern, list, tags) with OR logic
```

**Configuration Sources**:
1. **Environment Variables** (`config.py`):
   - `SOURCE_SECRET_PATTERN` - Regex pattern
   - `SOURCE_SECRET_LIST` - Comma-separated list
   - `SOURCE_INCLUDE_TAGS` - Tag-based inclusion
   - `SOURCE_EXCLUDE_TAGS` - Tag-based exclusion

2. **Secret Tags** (`handler.py:184-210`):
   - `SecretsReplicator:TransformSecretName` - Which transform to apply
   - `SecretsReplicator:TransformMode` - Mode override (sed/json)

### Current Workflow
```
EventBridge → Lambda
  ↓
1. Load config from environment variables
2. Fetch secret tags from Secrets Manager API
3. Apply filtering logic (should_replicate)
4. If match: read transform secret name from tag
5. Load transformation secret(s)
6. Apply transformation chain
7. Replicate to destination
```

### Current Security Posture

**Strengths**:
- ✅ Defense-in-depth with IAM Deny policy for transformation secrets
- ✅ Hardcoded exclusion for transformation prefix
- ✅ Tags stored encrypted in Secrets Manager
- ✅ No secrets in environment variables

**Weaknesses**:
- ⚠️ **Extra API call**: `describe_secret` to fetch tags for every invocation
- ⚠️ **Tag management complexity**: Tags must be updated on every source secret
- ⚠️ **Distributed configuration**: Each secret carries its own configuration
- ⚠️ **No centralized view**: Cannot see which secrets replicate without querying all
- ⚠️ **Tag limits**: AWS Secrets Manager allows max 50 tags per secret
- ⚠️ **Error-prone**: Easy to forget tags on new secrets

---

## Proposed Architecture Options

### Option 1: JSON in Environment Variable

**Configuration**: `REPLICATION_CONFIG`
```json
{
  "rules": [
    {
      "source_pattern": "app/prod/*",
      "transformations": ["region-swap", "endpoint-update"],
      "enabled": true
    },
    {
      "source_pattern": "db/*",
      "transformations": ["connection-string-transform"],
      "enabled": true
    },
    {
      "source_list": ["critical-secret-1", "critical-secret-2"],
      "transformations": [],
      "enabled": true
    }
  ],
  "default_action": "deny"
}
```

**Pros**:
- ✅ No additional Secrets Manager API calls
- ✅ Fast - configuration loaded once at Lambda cold start
- ✅ Centralized configuration
- ✅ Version controlled via SAM template
- ✅ Easy to audit and review

**Cons**:
- ❌ Environment variable size limit (4KB)
- ❌ Configuration visible in Lambda console
- ❌ Requires redeployment to change configuration
- ❌ Not ideal for frequently changing rules

**Security Assessment**: ⭐⭐⭐⭐ (Good)
- Configuration not sensitive (just patterns/names)
- Visible in console but acceptable for non-secrets
- IAM required to modify Lambda

---

### Option 2: Configuration in Secrets Manager

**Configuration**: Secret named `secrets-replicator/config`
```json
{
  "version": "1.0",
  "rules": [
    {
      "id": "prod-apps",
      "description": "Production application secrets",
      "source_pattern": "^app/prod/.*$",
      "source_list": [],
      "transformations": [
        {
          "name": "region-swap",
          "mode": "sed"
        },
        {
          "name": "endpoint-update",
          "mode": "json"
        }
      ],
      "enabled": true,
      "priority": 10
    },
    {
      "id": "databases",
      "description": "Database connection strings",
      "source_pattern": "^db/.*$",
      "transformations": [
        {
          "name": "connection-string-transform",
          "mode": "auto"
        }
      ],
      "enabled": true,
      "priority": 20
    },
    {
      "id": "no-transform-replication",
      "description": "Secrets that replicate without transformation",
      "source_list": ["api-key-prod", "oauth-client-secret"],
      "transformations": [],
      "enabled": true,
      "priority": 30
    }
  ],
  "default_action": "deny",
  "metadata": {
    "last_updated": "2025-12-04T10:00:00Z",
    "updated_by": "admin@example.com"
  }
}
```

**Pros**:
- ✅ No size limits (64KB max for secrets)
- ✅ Encrypted at rest
- ✅ Can be updated without redeployment
- ✅ Audit trail via CloudTrail
- ✅ Can use secret versioning
- ✅ Centralized configuration
- ✅ Can include metadata (last updated, author)

**Cons**:
- ❌ Additional Secrets Manager API call on each invocation (or cached)
- ❌ Slightly higher latency
- ❌ Adds cost ($0.40/month for config secret + $0.05 per 10k API calls)
- ❌ Requires IAM permissions to read config secret
- ❌ Risk of circular dependency if config secret itself needs replication

**Security Assessment**: ⭐⭐⭐⭐⭐ (Excellent)
- Configuration encrypted at rest
- CloudTrail audit trail for all changes
- Version history maintained
- Can use KMS for additional encryption
- No visibility in Lambda console

---

### Option 3: Hybrid Approach (RECOMMENDED)

**Environment Variable**: `REPLICATION_CONFIG_SECRET` (secret name) OR inline JSON
**Fallback**: If env var contains JSON, parse it; otherwise treat as secret name

```bash
# Option A: Reference to configuration secret
REPLICATION_CONFIG_SECRET="secrets-replicator/config"

# Option B: Inline JSON (small configs)
REPLICATION_CONFIG_SECRET='{"rules":[{"source_pattern":"^app/.*","transformations":["basic"]}]}'
```

**Implementation**:
```python
def load_replication_config(config_value: str) -> Dict:
    """
    Load configuration from environment variable.

    If value starts with '{', parse as JSON.
    Otherwise, treat as Secrets Manager secret name.
    """
    if config_value.strip().startswith('{'):
        # Inline JSON configuration
        return json.loads(config_value)
    else:
        # Secret name - fetch from Secrets Manager
        client = create_secrets_manager_client()
        secret_value = client.get_secret(config_value)
        return json.loads(secret_value.secret_string)
```

**Pros**:
- ✅ Flexibility: small configs inline, large configs in Secrets Manager
- ✅ Development: use inline for testing
- ✅ Production: use Secrets Manager for centralized management
- ✅ No redeployment needed (if using Secrets Manager)
- ✅ Fast for inline configs (no API call)
- ✅ Encrypted for sensitive configs (Secrets Manager)

**Cons**:
- ❌ More complex implementation
- ❌ Two code paths to maintain
- ❌ Need to handle both JSON parsing and Secrets Manager errors

**Security Assessment**: ⭐⭐⭐⭐⭐ (Excellent)
- Best of both worlds
- Production deployments can use encrypted storage
- Dev/test can use inline for speed

---

## Detailed Design: Recommended Approach (Option 3)

### Configuration Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["version", "rules"],
  "properties": {
    "version": {
      "type": "string",
      "enum": ["1.0"]
    },
    "rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "enabled"],
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique identifier for this rule"
          },
          "description": {
            "type": "string"
          },
          "source_pattern": {
            "type": "string",
            "description": "Regex pattern to match secret names"
          },
          "source_list": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Explicit list of secret names"
          },
          "source_tags": {
            "type": "object",
            "description": "Tag filters (AND logic within rule)"
          },
          "transformations": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["name"],
              "properties": {
                "name": {"type": "string"},
                "mode": {
                  "type": "string",
                  "enum": ["auto", "sed", "json"]
                }
              }
            }
          },
          "enabled": {
            "type": "boolean"
          },
          "priority": {
            "type": "integer",
            "description": "Lower number = higher priority"
          }
        }
      }
    },
    "default_action": {
      "type": "string",
      "enum": ["allow", "deny"],
      "description": "Action when no rules match"
    }
  }
}
```

### Filtering Algorithm

```python
def find_matching_rule(secret_name: str, secret_tags: Dict[str, str],
                       rules: List[Dict]) -> Optional[Dict]:
    """
    Find the first matching rule for a secret.

    Rules are evaluated in priority order (lowest priority number first).
    Within a rule, ALL conditions must match (AND logic).
    Between rules, first match wins.
    """
    # Sort rules by priority (lower = higher priority)
    sorted_rules = sorted(rules, key=lambda r: r.get('priority', 999))

    for rule in sorted_rules:
        if not rule.get('enabled', True):
            continue

        # Check pattern match
        if 'source_pattern' in rule:
            if not re.match(rule['source_pattern'], secret_name):
                continue

        # Check explicit list
        if 'source_list' in rule:
            if secret_name not in rule['source_list']:
                continue

        # Check tags (AND logic - all specified tags must match)
        if 'source_tags' in rule:
            tag_match = all(
                secret_tags.get(k) == v
                for k, v in rule['source_tags'].items()
            )
            if not tag_match:
                continue

        # All conditions matched - return this rule
        return rule

    # No rule matched
    return None
```

### New Environment Variables

```bash
# Configuration source (secret name or inline JSON)
REPLICATION_CONFIG_SECRET="secrets-replicator/config"

# OR inline JSON for simple configs
# REPLICATION_CONFIG_SECRET='{"version":"1.0","rules":[...]}'

# Cache TTL for configuration (seconds)
REPLICATION_CONFIG_CACHE_TTL="300"  # 5 minutes

# Keep existing variables
DEST_REGION="us-east-1"
DEST_SECRET_NAME=""
DEST_ACCOUNT_ROLE_ARN=""
TRANSFORMATION_SECRET_PREFIX="secrets-replicator/transformations/"
LOG_LEVEL="INFO"
ENABLE_METRICS="true"
```

### Implementation Changes

**Files to Modify**:
1. `src/config.py` - Add configuration loading logic
2. `src/handler.py` - Replace `should_replicate()` and tag-based transform logic
3. `template.yaml` - Add new environment variable
4. Tests - Update unit tests for new logic

**Caching Strategy**:
```python
# Global variable for configuration caching
_config_cache = {
    'data': None,
    'loaded_at': 0,
    'ttl': 300  # 5 minutes
}

def get_replication_config(config_secret_name: str, ttl: int = 300) -> Dict:
    """
    Load configuration with caching.

    Cache is valid across Lambda invocations (warm starts).
    """
    now = time.time()

    if (_config_cache['data'] is not None and
        (now - _config_cache['loaded_at']) < _config_cache['ttl']):
        # Return cached configuration
        return _config_cache['data']

    # Load fresh configuration
    config_data = load_replication_config(config_secret_name)

    # Validate schema
    validate_config_schema(config_data)

    # Update cache
    _config_cache['data'] = config_data
    _config_cache['loaded_at'] = now
    _config_cache['ttl'] = ttl

    return config_data
```

---

## Migration Strategy

### Phase 1: Add New Configuration (Backwards Compatible)

1. Add new environment variable `REPLICATION_CONFIG_SECRET` (optional)
2. If not set, fall back to current tag-based logic
3. Deploy and test with new configuration alongside old
4. Validate no regressions

### Phase 2: Migrate Secrets

1. Document current filtering rules from tags
2. Create centralized configuration secret
3. Deploy with `REPLICATION_CONFIG_SECRET` set
4. Monitor for any filtering differences
5. Remove tags from secrets (optional - can keep as metadata)

### Phase 3: Remove Legacy Code

1. Remove tag-based filtering code
2. Remove `SOURCE_*_TAGS` environment variables
3. Update documentation
4. Remove unused IAM permissions (if any)

---

## Security Implications

### Improvements
1. **Reduced API Calls**: No more `describe_secret` for tags on every invocation
2. **Centralized Audit**: All configuration changes in one place
3. **Defense in Depth**: Still maintains IAM Deny policy for transformation secrets
4. **Explicit Allow List**: Default deny with explicit allow rules
5. **Priority-Based**: Clear precedence rules for conflict resolution

### Considerations
1. **Configuration Secret Protection**:
   - Must use strong IAM policies
   - Consider KMS encryption
   - Enable versioning
   - Monitor access via CloudTrail

2. **Circular Dependency Risk**:
   - Configuration secret itself must NOT be replicated
   - Add hardcoded exclusion: `if secret_name == config.replication_config_secret`

3. **Cache Invalidation**:
   - Configuration changes take up to TTL to propagate
   - Consider adding cache invalidation mechanism (e.g., via parameter or event)

---

## Performance Impact

### Current (Tag-Based)
```
Per invocation:
- 1x describe_secret API call (tags) ~ 50-100ms
- 1x get_secret_value (source) ~ 50-100ms
- Nx get_secret_value (transformations) ~ N * 50-100ms
- 1x put_secret (destination) ~ 50-100ms

Total: ~200ms + N*100ms
```

### Proposed (Config-Based)
```
Cold start:
- 1x get_secret_value (config, if using Secrets Manager) ~ 50-100ms
- Parse and validate JSON ~ 5-10ms

Warm start (cached config):
- 0 additional API calls
- Rule evaluation ~ 1-5ms

Per invocation:
- 0x describe_secret (eliminated!)
- 1x get_secret_value (source) ~ 50-100ms
- Nx get_secret_value (transformations) ~ N * 50-100ms
- 1x put_secret (destination) ~ 50-100ms

Total: ~150ms + N*100ms (warm) or ~250ms + N*100ms (cold)
```

**Net Performance**:
- **Warm starts**: 50ms faster (eliminated describe_secret call)
- **Cold starts**: Comparable or slightly slower if loading config from Secrets Manager
- **Overall**: Improved due to caching across invocations

---

## Cost Impact

### Current Costs
```
Per 1000 replications:
- 1000x describe_secret = $0.05
- 1000x get_secret_value (source) = $0.05
- 1000x put_secret (destination) = $0.05
Total API costs: $0.15 per 1000 replications
```

### Proposed Costs (Secrets Manager Config)
```
One-time:
- 1x configuration secret = $0.40/month

Per 1000 replications (warm starts):
- 1000x get_secret_value (source) = $0.05
- 1000x put_secret (destination) = $0.05
- ~2x get_secret_value (config, with 5min cache) = $0.0001

Total: $0.40/month + $0.10 per 1000 replications

Savings: $0.05 per 1000 replications
```

**Net Cost**: Slightly higher fixed cost ($0.40/month for config secret), but lower per-replication cost. Breaks even at ~8,000 replications/month.

---

## Recommendation Summary

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"content": "Analyze proposed architectural changes for security and reliability", "status": "completed", "activeForm": "Analyzing proposed architectural changes"}, {"content": "Review current filtering implementation", "status": "completed", "activeForm": "Reviewing current filtering implementation"}, {"content": "Evaluate security implications of proposed changes", "status": "completed", "activeForm": "Evaluating security implications"}, {"content": "Design recommended architecture", "status": "completed", "activeForm": "Designing recommended architecture"}, {"content": "Provide implementation recommendation", "status": "in_progress", "activeForm": "Providing implementation recommendation"}]