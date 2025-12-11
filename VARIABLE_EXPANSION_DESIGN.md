# Variable Expansion in Transformation Secrets - Design Document

## Problem Statement

Currently, transformation secrets contain hardcoded values that must be duplicated for each destination region. For example:

```bash
# Transformation secret for us-east-1 destination
s/us-west-2/us-east-1/g

# Transformation secret for eu-west-1 destination
s/us-west-2/eu-west-1/g

# Transformation secret for ap-southeast-1 destination
s/us-west-2/ap-southeast-1/g
```

This leads to:
- **Duplication**: Same transformation logic repeated across multiple secrets
- **Maintenance burden**: Updating the pattern requires changing all transformation secrets
- **Configuration complexity**: Each destination needs its own transformation secret
- **Error-prone**: Easy to make mistakes when copying transformation logic

## Proposed Solution

Enable **variable expansion** in transformation secrets using `${VARIABLE}` or `{VARIABLE}` syntax, where variables are substituted with runtime values from the destination configuration.

### Example Usage

**Single transformation secret** (replaces all per-region secrets):
```bash
# secrets-replicator/transformations/region-swap
s/us-west-2/${REGION}/g
```

**Destination configuration**:
```json
[
  {"region": "us-east-1"},
  {"region": "eu-west-1"},
  {"region": "ap-southeast-1"}
]
```

When replicating to `us-east-1`, `${REGION}` expands to `us-east-1`, making the transformation: `s/us-west-2/us-east-1/g`

## Available Variables

### Core Variables (Always Available)

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `${REGION}` | Destination region | `us-east-1` |
| `${SOURCE_REGION}` | Source region | `us-west-2` |
| `${ACCOUNT_ID}` | Destination account ID | `999888777666` |
| `${SOURCE_ACCOUNT_ID}` | Source account ID | `123456789012` |
| `${SECRET_NAME}` | Source secret name | `app/prod/db-password` |
| `${DEST_SECRET_NAME}` | Destination secret name (after name mapping) | `app/prod/db-password-replica` |

### Optional Variables (From Destination Config)

| Variable | Description | Source |
|----------|-------------|--------|
| `${KMS_KEY_ID}` | Destination KMS key ID | `destination.kms_key_id` |
| `${ROLE_ARN}` | Cross-account role ARN | `destination.account_role_arn` |

### Custom Variables (User-Defined)

Users can define custom variables in the destination configuration:

```json
{
  "region": "us-east-1",
  "variables": {
    "ENVIRONMENT": "prod",
    "CLUSTER_NAME": "prod-cluster-1",
    "DB_ENDPOINT": "prod-db.us-east-1.rds.amazonaws.com"
  }
}
```

Usage in transformation:
```bash
s/dev-cluster/${CLUSTER_NAME}/g
s/dev-db\..*\.rds/${DB_ENDPOINT}/g
s/environment=dev/environment=${ENVIRONMENT}/g
```

## Syntax Options

### Option 1: `${VARIABLE}` (Shell-Style, Recommended)

**Pros**:
- Familiar to bash/shell users
- Clear distinction from literal braces
- Standard in many templating systems

**Cons**:
- Must escape literal `${}` sequences

**Example**:
```bash
s/us-west-2/${REGION}/g
s/account-${SOURCE_ACCOUNT_ID}/account-${ACCOUNT_ID}/g
```

### Option 2: `{VARIABLE}` (Minimal)

**Pros**:
- Simpler syntax
- No dollar sign needed

**Cons**:
- Ambiguous with literal braces (common in regex)
- Harder to distinguish from regex patterns

**Example**:
```bash
s/us-west-2/{REGION}/g
s/account-{SOURCE_ACCOUNT_ID}/account-{ACCOUNT_ID}/g
```

### Option 3: `{{VARIABLE}}` (Double-Brace, Jinja2-Style)

**Pros**:
- Less ambiguous than single braces
- Familiar to Jinja2/Ansible users

**Cons**:
- More verbose
- Still conflicts with regex patterns

**Example**:
```bash
s/us-west-2/{{REGION}}/g
```

**Recommendation**: Use `${VARIABLE}` syntax (Option 1) for consistency with shell scripting and AWS conventions.

## Implementation Design

### 1. Variable Context Builder

Create a function to build the variable substitution context from destination configuration:

```python
def build_variable_context(
    destination: DestinationConfig,
    source_secret_name: str,
    dest_secret_name: str,
    source_region: str,
    source_account_id: str
) -> Dict[str, str]:
    """
    Build variable substitution context for transformation.

    Args:
        destination: Destination configuration
        source_secret_name: Source secret name
        dest_secret_name: Destination secret name (after mapping)
        source_region: Source AWS region
        source_account_id: Source AWS account ID

    Returns:
        Dict mapping variable names to values
    """
    context = {
        # Core variables
        'REGION': destination.region,
        'SOURCE_REGION': source_region,
        'ACCOUNT_ID': destination.account_role_arn.split(':')[4] if destination.account_role_arn else source_account_id,
        'SOURCE_ACCOUNT_ID': source_account_id,
        'SECRET_NAME': source_secret_name,
        'DEST_SECRET_NAME': dest_secret_name,

        # Optional variables
        'KMS_KEY_ID': destination.kms_key_id or '',
        'ROLE_ARN': destination.account_role_arn or '',
    }

    # Add custom variables from destination config
    if hasattr(destination, 'variables') and destination.variables:
        context.update(destination.variables)

    return context
```

### 2. Variable Expansion Function

Add a variable expansion function to `transformer.py`:

```python
import re
from typing import Dict

def expand_variables(text: str, context: Dict[str, str]) -> str:
    """
    Expand ${VARIABLE} references in text using context values.

    Args:
        text: Text containing variable references (e.g., "s/old/${REGION}/g")
        context: Dict mapping variable names to values

    Returns:
        Text with variables expanded

    Raises:
        TransformationError: If variable is undefined

    Examples:
        >>> context = {'REGION': 'us-east-1', 'ENV': 'prod'}
        >>> expand_variables('s/us-west-2/${REGION}/g', context)
        's/us-west-2/us-east-1/g'
        >>> expand_variables('environment=${ENV}', context)
        'environment=prod'
    """
    # Pattern matches ${VARIABLE_NAME} where VARIABLE_NAME is alphanumeric + underscore
    pattern = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')

    def replace_variable(match):
        var_name = match.group(1)
        if var_name not in context:
            raise TransformationError(
                f"Undefined variable: ${{{var_name}}}. "
                f"Available variables: {', '.join(sorted(context.keys()))}"
            )
        return context[var_name]

    return pattern.sub(replace_variable, text)
```

### 3. Integration Points

**In `handler.py` (Lambda handler)**:

```python
# Build variable context
context = build_variable_context(
    destination=destination,
    source_secret_name=source_secret_name,
    dest_secret_name=dest_secret_name,
    source_region=config.source_region,
    source_account_id=config.source_account_id
)

# Load transformation secret
transform_content = load_transformation_secret(...)

# Expand variables BEFORE parsing transformation rules
expanded_content = expand_variables(transform_content, context)

# Parse and apply transformation (existing code)
if transform_mode == 'sed':
    rules = parse_sedfile(expanded_content)
    transformed_value = apply_sed_transforms(secret_value, rules)
elif transform_mode == 'json':
    mappings = parse_json_mapping(expanded_content)
    transformed_value = apply_json_transforms(secret_value, mappings)
```

### 4. Destination Config Schema Update

Add optional `variables` field to `DestinationConfig`:

```python
@dataclass
class DestinationConfig:
    """Configuration for a single replication destination"""

    region: str
    account_role_arn: Optional[str] = None
    secret_names: Optional[str] = None
    secret_names_cache_ttl: int = 300
    kms_key_id: Optional[str] = None
    variables: Optional[Dict[str, str]] = None  # NEW: Custom variables
```

Example configuration secret:
```json
[
  {
    "region": "us-east-1",
    "variables": {
      "ENVIRONMENT": "prod",
      "CLUSTER": "prod-cluster-1",
      "DB_HOST": "prod-db.us-east-1.rds.amazonaws.com"
    }
  },
  {
    "region": "eu-west-1",
    "variables": {
      "ENVIRONMENT": "prod",
      "CLUSTER": "prod-cluster-eu",
      "DB_HOST": "prod-db.eu-west-1.rds.amazonaws.com"
    }
  }
]
```

## Use Cases

### Use Case 1: Region-Specific Transformations

**Problem**: Same transformation logic for all regions, just swap region names

**Transformation Secret** (`secrets-replicator/transformations/region-swap`):
```bash
s/us-west-2/${REGION}/g
s/usw2/${REGION_SHORT}/g  # Custom variable for short region codes
```

**Configuration**:
```json
[
  {
    "region": "us-east-1",
    "variables": {"REGION_SHORT": "use1"}
  },
  {
    "region": "eu-west-1",
    "variables": {"REGION_SHORT": "euw1"}
  }
]
```

**Result**: One transformation secret works for all regions

### Use Case 2: Cross-Account with Different Endpoints

**Problem**: Replicating to different accounts with account-specific infrastructure

**Transformation Secret**:
```bash
s/arn:aws:rds:${SOURCE_REGION}:${SOURCE_ACCOUNT_ID}/arn:aws:rds:${REGION}:${ACCOUNT_ID}/g
s/db\.${SOURCE_REGION}\.amazonaws\.com/db\.${REGION}\.amazonaws\.com/g
```

**Configuration**:
```json
[
  {
    "region": "us-east-1",
    "account_role_arn": "arn:aws:iam::999888777666:role/ReplicatorRole"
  }
]
```

**Result**: ARNs and endpoints automatically updated for destination account

### Use Case 3: Environment Promotion

**Problem**: Promoting secrets from dev → qa → prod with environment-specific values

**Transformation Secret**:
```bash
s/dev-/${ENV}-/g
s/development/${ENV}/g
s/dev\./${ENV}./g
```

**Configuration**:
```json
[
  {
    "region": "us-east-1",
    "variables": {"ENV": "qa"}
  },
  {
    "region": "us-west-2",
    "variables": {"ENV": "prod"}
  }
]
```

### Use Case 4: Complex Multi-Region Setup

**Transformation Secret**:
```bash
s/"region":"${SOURCE_REGION}"/"region":"${REGION}"/g
s/"endpoint":"https:\/\/api\.${SOURCE_REGION}/"endpoint":"https:\/\/api\.${REGION}/g
s/"bucket":"data-${SOURCE_REGION}"/"bucket":"data-${REGION}"/g
s/"cluster":"${SOURCE_CLUSTER}"/"cluster":"${DEST_CLUSTER}"/g
```

**Configuration**:
```json
[
  {
    "region": "us-east-1",
    "variables": {
      "SOURCE_CLUSTER": "prod-usw2",
      "DEST_CLUSTER": "prod-use1"
    }
  },
  {
    "region": "eu-west-1",
    "variables": {
      "SOURCE_CLUSTER": "prod-usw2",
      "DEST_CLUSTER": "prod-euw1"
    }
  }
]
```

## Security Considerations

### 1. Variable Injection Prevention

**Risk**: Malicious variable values could inject sed commands or break regex

**Mitigation**:
- Escape special regex characters in variable values
- Validate variable names (alphanumeric + underscore only)
- Limit variable value length

```python
def sanitize_variable_value(value: str, max_length: int = 256) -> str:
    """Sanitize variable value to prevent injection attacks"""
    if len(value) > max_length:
        raise TransformationError(f"Variable value too long (max {max_length} chars)")

    # Escape regex special characters
    return re.escape(value)
```

### 2. Undefined Variable Handling

**Risk**: Undefined variables could cause silent failures or unexpected behavior

**Mitigation**:
- Fail fast on undefined variables (no silent substitution)
- Log available variables in error message
- Provide clear error messages

### 3. Variable Precedence

**Priority order**:
1. Custom variables (destination.variables)
2. Core variables (REGION, ACCOUNT_ID, etc.)
3. Optional variables (KMS_KEY_ID, ROLE_ARN)

Custom variables can override core variables if needed (advanced use case).

## Testing Strategy

### Unit Tests

```python
def test_expand_variables_basic():
    context = {'REGION': 'us-east-1', 'ENV': 'prod'}
    assert expand_variables('${REGION}', context) == 'us-east-1'
    assert expand_variables('${ENV}', context) == 'prod'

def test_expand_variables_in_sed_pattern():
    context = {'REGION': 'us-west-2'}
    result = expand_variables('s/us-east-1/${REGION}/g', context)
    assert result == 's/us-east-1/us-west-2/g'

def test_expand_variables_multiple():
    context = {'SOURCE': 'us-east-1', 'DEST': 'us-west-2'}
    result = expand_variables('s/${SOURCE}/${DEST}/g', context)
    assert result == 's/us-east-1/us-west-2/g'

def test_expand_variables_undefined():
    context = {'REGION': 'us-east-1'}
    with pytest.raises(TransformationError, match="Undefined variable.*UNDEFINED"):
        expand_variables('${UNDEFINED}', context)

def test_expand_variables_no_substitution():
    context = {'REGION': 'us-east-1'}
    assert expand_variables('no variables here', context) == 'no variables here'

def test_expand_variables_literal_braces():
    context = {'REGION': 'us-east-1'}
    # Literal ${} should not be expanded
    assert expand_variables('literal {} braces', context) == 'literal {} braces'
```

### Integration Tests

```python
def test_transformation_with_region_variable(sm_client):
    # Create transformation secret with variable
    sm_client.create_secret(
        Name='secrets-replicator/transformations/test',
        SecretString='s/us-west-2/${REGION}/g'
    )

    # Create destination config
    config = [{'region': 'us-east-1'}]

    # Test transformation
    source_value = 'host: db.us-west-2.aws.com'
    result = replicate_with_transformation(source_value, config)

    assert result == 'host: db.us-east-1.aws.com'

def test_custom_variables_in_transformation(sm_client):
    sm_client.create_secret(
        Name='secrets-replicator/transformations/test',
        SecretString='s/dev/${ENV}/g'
    )

    config = [{
        'region': 'us-east-1',
        'variables': {'ENV': 'prod'}
    }]

    source_value = 'environment: dev'
    result = replicate_with_transformation(source_value, config)

    assert result == 'environment: prod'
```

## Backward Compatibility

**Non-breaking change**: Existing transformation secrets without variables will continue to work unchanged.

**Migration path**:
1. Old secrets without variables: Work as-is
2. New secrets with variables: Enable new functionality
3. No forced migration required

**Example**:
```bash
# Old transformation (still works)
s/us-west-2/us-east-1/g

# New transformation (with variables)
s/us-west-2/${REGION}/g
```

## Documentation Updates Required

1. **README.md**: Add variable expansion examples
2. **ARCHITECTURE.md**: Document variable expansion in transformation flow
3. **docs/transformations.md**: Add comprehensive variable expansion guide
4. **Examples**: Create example transformation secrets with variables

## Implementation Phases

### Phase 1: Core Implementation ✅ COMPLETED
- [x] Add `expand_variables()` function to `transformer.py`
- [x] Add `build_variable_context()` helper
- [x] Update `DestinationConfig` to support `variables` field
- [x] Integrate variable expansion in handler.py
- [x] Unit tests for variable expansion (23 tests, all passing)

**Implementation Details**:
- Added `expand_variables()` in `src/transformer.py:50-74`
- Added `build_variable_context()` in `src/transformer.py:77-111`
- Updated `DestinationConfig` in `src/config.py:26` with `variables: Optional[Dict[str, str]]`
- Integrated in `handler.py:327-345` for per-destination expansion
- Custom exception `VariableExpansionError` in `src/exceptions.py:83-88`

### Phase 2: Testing & Validation ✅ COMPLETED
- [x] Comprehensive unit tests (23 tests covering all scenarios)
- [x] Error handling tests (undefined variables, malformed syntax)
- [x] Edge case tests (empty values, special characters, overlapping variables)
- [x] Integration with sed and JSON transformations
- [x] Per-destination context validation

**Test Coverage**:
- Basic variable expansion: 5 tests
- Multiple variables: 3 tests
- Error handling: 4 tests
- Edge cases: 5 tests
- Integration: 6 tests
- Total: 23 tests, 100% passing

### Phase 3: Documentation & Examples ✅ COMPLETED
- [x] Update README.md with variable examples (233 lines added)
- [x] Create transformation examples with variables:
  - `examples/sedfile-variables-region.sed` (68 lines)
  - `examples/sedfile-variables-json.json` (60 lines)
  - `examples/config-custom-variables.json` (139 lines)
- [x] Update ARCHITECTURE.md (149 lines added)
- [x] Update docs/transformations.md with variable expansion section

### Phase 4: Advanced Features (Future Enhancements - Not Implemented)
- [ ] Variable arithmetic (e.g., `${PORT+1}`)
- [ ] Conditional expansion (e.g., `${VAR:-default}`)
- [ ] Nested variable references (e.g., `${${PREFIX}_NAME}`)
- [ ] Computed variables (e.g., `REGION_SHORT` from `REGION`)
- [ ] Variable validation (e.g., must be valid region code)

## Future Enhancements

1. **Computed Variables**: Derive variables from other variables
   ```json
   {
     "region": "us-east-1",
     "variables": {
       "REGION_SHORT": "${REGION[0:3]}",  // "use"
       "UPPER_REGION": "${REGION.upper()}"  // "US-EAST-1"
     }
   }
   ```

2. **Environment Variable Passthrough**: Allow Lambda environment variables as fallback
   ```python
   context['CUSTOM_VAR'] = os.environ.get('CUSTOM_VAR', '')
   ```

3. **Secret-Based Variables**: Load variables from other secrets
   ```json
   {
     "region": "us-east-1",
     "variable_secrets": {
       "DB_CONFIG": "secrets-replicator/config/db-endpoints"
     }
   }
   ```

## Questions for Discussion

1. Should we support both `${VAR}` and `{VAR}` syntax, or just one?
2. Should undefined variables fail hard or substitute with empty string?
3. Should we sanitize/escape variable values by default?
4. Do we need variable validation (e.g., must be valid region code)?
5. Should custom variables be able to override core variables?
6. Do we need a "dry-run" mode to preview variable expansion?

## Conclusion

Variable expansion in transformation secrets would:
- **Reduce duplication**: One transformation secret for all regions
- **Simplify configuration**: Fewer secrets to manage
- **Improve maintainability**: Update logic in one place
- **Enable flexibility**: Custom variables for complex scenarios
- **Maintain security**: Variables never logged, validated before use

**Recommendation**: Implement Phase 1 (core functionality) first, then gather user feedback before adding advanced features.
