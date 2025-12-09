# Multi-Region Replication Architecture

## Overview

This document provides architectural guidance for replicating secrets to multiple destination regions with region-specific transformations and name mappings.

## Problem Statement

**Use Case**: Replicate a source secret to multiple regions with different transformations per region:
- Source: `app/prod/db` in `us-west-2`
- Destination 1: `app/prod/db` in `us-east-1` (transform: `us-west-2` → `us-east-1`)
- Destination 2: `app/prod/db` in `eu-west-1` (transform: `us-west-2` → `eu-west-1`)
- Destination 3: `app/prod/db-backup` in `us-east-2` (transform: `us-west-2` → `us-east-2`, rename)

**Current Limitation**: Each Lambda instance is configured with a single `DEST_REGION` environment variable, limiting it to one destination.

## Architecture Options

### Option 1: Multiple Lambda Deployments (Current Capability)

Deploy separate Lambda functions for each destination region.

#### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Source Region (us-west-2)                │
│                                                              │
│  Secret Update Event                                         │
│         │                                                    │
│         ├─────► EventBridge Rule ────────────────────┐      │
│         │                                             │      │
└─────────┼─────────────────────────────────────────────┼──────┘
          │                                             │
          ▼                                             ▼
┌─────────────────────────┐              ┌─────────────────────────┐
│   Lambda Stack 1        │              │   Lambda Stack 2        │
│   (us-east-1)           │              │   (eu-west-1)           │
│                         │              │                         │
│ DEST_REGION=us-east-1   │              │ DEST_REGION=eu-west-1   │
│ SECRETS_FILTER=         │              │ SECRETS_FILTER=         │
│   ...filters/us-east-1  │              │   ...filters/eu-west-1  │
│ DEST_SECRET_NAMES=      │              │ DEST_SECRET_NAMES=      │
│   ...names/us-east-1    │              │   ...names/eu-west-1    │
└─────────┬───────────────┘              └─────────┬───────────────┘
          │                                        │
          ▼                                        ▼
┌─────────────────────────┐              ┌─────────────────────────┐
│  Destination (us-east-1)│              │  Destination (eu-west-1)│
│                         │              │                         │
│  app/prod/db            │              │  app/prod/db            │
│  (transformed)          │              │  (transformed)          │
└─────────────────────────┘              └─────────────────────────┘
```

#### Implementation

**Stack Naming Convention**:
```bash
secrets-replicator-to-us-east-1
secrets-replicator-to-us-east-2
secrets-replicator-to-eu-west-1
```

**Deployment**:
```bash
# Deploy to us-east-1
sam deploy \
  --stack-name secrets-replicator-to-us-east-1 \
  --parameter-overrides \
    DestinationRegion=us-east-1 \
    SecretsFilter=secrets-replicator/filters/to-us-east-1 \
    DestSecretNames=secrets-replicator/names/to-us-east-1 \
    Environment=prod

# Deploy to eu-west-1
sam deploy \
  --stack-name secrets-replicator-to-eu-west-1 \
  --parameter-overrides \
    DestinationRegion=eu-west-1 \
    SecretsFilter=secrets-replicator/filters/to-eu-west-1 \
    DestSecretNames=secrets-replicator/names/to-eu-west-1 \
    Environment=prod
```

**Configuration Secrets Structure**:

Each destination has its own set of configuration secrets:

```json
// secrets-replicator/filters/to-us-east-1
{
  "app/prod/*": "secrets-replicator/transformations/to-us-east-1",
  "db/prod/*": "secrets-replicator/transformations/to-us-east-1"
}

// secrets-replicator/filters/to-eu-west-1
{
  "app/prod/*": "secrets-replicator/transformations/to-eu-west-1",
  "db/prod/*": "secrets-replicator/transformations/to-eu-west-1"
}

// secrets-replicator/transformations/to-us-east-1
s/us-west-2/us-east-1/g
s/usw2/use1/g

// secrets-replicator/transformations/to-eu-west-1
s/us-west-2/eu-west-1/g
s/usw2/euw1/g

// secrets-replicator/names/to-us-east-1 (if needed)
{
  "app/prod/db": "app/prod/db",
  "app/prod/api": "app/prod/api-primary"
}

// secrets-replicator/names/to-eu-west-1 (if needed)
{
  "app/prod/db": "app/prod/db-replica"
}
```

#### Pros
✅ **Works with current code** - No code changes required
✅ **Complete isolation** - Each Lambda has independent configuration, DLQ, metrics
✅ **Independent scaling** - Each destination can scale independently
✅ **Region-specific IAM** - Each Lambda can have different cross-account roles
✅ **Flexible filtering** - Each Lambda can filter different secrets per destination
✅ **Easy to understand** - One Lambda = one destination
✅ **Independent failures** - If one Lambda fails, others continue

#### Cons
❌ **Resource overhead** - Multiple Lambda functions, EventBridge rules, DLQs
❌ **Configuration duplication** - Each stack needs separate configuration
❌ **Cost** - N Lambda invocations per secret update (one per destination)
❌ **Deployment complexity** - Must deploy and manage N stacks
❌ **EventBridge fan-out** - All Lambdas triggered for every secret update

#### When to Use
- ✅ You have **2-5 destination regions**
- ✅ You want **complete isolation** between destinations
- ✅ You want to **minimize code changes**
- ✅ Cost is not a primary concern (~$0.20 per million invocations)

---

### Option 2: Multi-Destination Configuration (Recommended)

Extend the current architecture to support multiple destinations from a single Lambda.

#### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Source Region (us-west-2)                │
│                                                              │
│  Secret Update Event                                         │
│         │                                                    │
│         └─────► EventBridge Rule ────────┐                  │
│                                           │                  │
└───────────────────────────────────────────┼──────────────────┘
                                            ▼
                              ┌──────────────────────────┐
                              │  Lambda Function         │
                              │  (Enhanced)              │
                              │                          │
                              │ DEST_REGIONS=            │
                              │   us-east-1,eu-west-1    │
                              │                          │
                              │ Per-region configs:      │
                              │ - Filters                │
                              │ - Transformations        │
                              │ - Name mappings          │
                              └────────┬─────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
          ┌─────────────────────┐              ┌─────────────────────┐
          │ Destination         │              │ Destination         │
          │ (us-east-1)         │              │ (eu-west-1)         │
          │                     │              │                     │
          │ app/prod/db         │              │ app/prod/db         │
          │ (transformed)       │              │ (transformed)       │
          └─────────────────────┘              └─────────────────────┘
```

#### Implementation Changes Required

**1. Configuration Schema Changes** (`src/config.py`):

```python
@dataclass
class DestinationConfig:
    """Configuration for a single destination"""
    region: str
    account_role_arn: Optional[str] = None
    filters_secret: Optional[str] = None      # Region-specific filter
    names_secret: Optional[str] = None        # Region-specific name mapping
    kms_key_id: Optional[str] = None

@dataclass
class ReplicatorConfig:
    # Replace single dest_region with list of destinations
    destinations: List[DestinationConfig] = field(default_factory=list)

    # Global fallback configuration
    secrets_filter: Optional[str] = None          # Global filter (all regions)
    dest_secret_names: Optional[str] = None       # Global name mapping
```

**2. Handler Changes** (`src/handler.py`):

```python
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Replicate to multiple destinations"""

    # ... (existing event parsing) ...

    results = []
    for dest_config in config.destinations:
        try:
            # Use region-specific or global filter
            filter_secret = dest_config.filters_secret or config.secrets_filter
            should_replicate, transform = should_replicate_secret(
                secret_name, filter_secret, source_client
            )

            if not should_replicate:
                continue

            # Use region-specific or global name mapping
            names_secret = dest_config.names_secret or config.dest_secret_names
            dest_name = get_destination_name(
                secret_name, names_secret, dest_config.region, source_client
            )

            # Replicate to this destination
            result = replicate_to_destination(
                secret_name, dest_name, dest_config, transform
            )
            results.append(result)

        except Exception as e:
            # Log error but continue with other destinations
            logger.error(f"Failed to replicate to {dest_config.region}: {e}")
            results.append({"region": dest_config.region, "success": False})

    return {
        "statusCode": 200,
        "destinations": results,
        "success_count": sum(1 for r in results if r.get("success")),
        "failure_count": sum(1 for r in results if not r.get("success"))
    }
```

**3. Environment Variable Format**:

```yaml
# Option A: JSON-encoded list (simple)
DEST_REGIONS: "us-east-1,eu-west-1,us-east-2"
DEST_CONFIGS: |
  {
    "us-east-1": {
      "filters": "secrets-replicator/filters/to-us-east-1",
      "names": "secrets-replicator/names/to-us-east-1"
    },
    "eu-west-1": {
      "filters": "secrets-replicator/filters/to-eu-west-1",
      "names": "secrets-replicator/names/to-eu-west-1"
    }
  }

# Option B: Comma-separated (backward compatible)
DEST_REGIONS: "us-east-1,eu-west-1"
SECRETS_FILTER_US_EAST_1: "secrets-replicator/filters/to-us-east-1"
SECRETS_FILTER_EU_WEST_1: "secrets-replicator/filters/to-eu-west-1"
DEST_SECRET_NAMES_US_EAST_1: "secrets-replicator/names/to-us-east-1"
DEST_SECRET_NAMES_EU_WEST_1: "secrets-replicator/names/to-eu-west-1"
```

**4. Configuration Secrets Structure**:

```json
// secrets-replicator/destinations
{
  "destinations": [
    {
      "region": "us-east-1",
      "filters": "secrets-replicator/filters/to-us-east-1",
      "names": "secrets-replicator/names/to-us-east-1",
      "transformations": "secrets-replicator/transformations/to-us-east-1"
    },
    {
      "region": "eu-west-1",
      "filters": "secrets-replicator/filters/to-eu-west-1",
      "names": "secrets-replicator/names/to-eu-west-1",
      "transformations": "secrets-replicator/transformations/to-eu-west-1"
    }
  ]
}
```

#### Pros
✅ **Single deployment** - One Lambda function handles all destinations
✅ **Reduced cost** - One invocation per secret update (vs N invocations)
✅ **Simplified management** - Single stack to deploy and monitor
✅ **Atomic operations** - All replications happen in one transaction
✅ **Centralized logging** - All destinations logged in one place
✅ **Better failure handling** - Can implement partial success retry logic

#### Cons
❌ **Code changes required** - Need to modify config, handler, and tests
❌ **Increased timeout risk** - More destinations = longer execution time
❌ **Shared fate** - If Lambda fails, all destinations fail
❌ **Complex configuration** - More environment variables or config secrets
❌ **Limited by Lambda timeout** - Max 15 minutes for all replications

#### When to Use
- ✅ You have **3+ destination regions**
- ✅ You want to **minimize cost** (80% cost reduction vs Option 1)
- ✅ You want **centralized management**
- ✅ You can tolerate **shared failure** across destinations
- ✅ Total replication time < 10 minutes

---

### Option 3: Hybrid Approach with Step Functions

Use Step Functions to orchestrate parallel replications to multiple regions.

#### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Source Region (us-west-2)                │
│                                                              │
│  Secret Update Event                                         │
│         │                                                    │
│         └─────► EventBridge Rule ────────┐                  │
│                                           │                  │
└───────────────────────────────────────────┼──────────────────┘
                                            ▼
                              ┌──────────────────────────┐
                              │  Step Functions          │
                              │  (Coordinator)           │
                              │                          │
                              │  Parallel State          │
                              │                          │
                              └────┬─────────────┬───────┘
                                   │             │
                    ┌──────────────┘             └──────────────┐
                    ▼                                           ▼
          ┌─────────────────────┐                    ┌─────────────────────┐
          │ Lambda Replicator   │                    │ Lambda Replicator   │
          │ (us-east-1)         │                    │ (eu-west-1)         │
          │                     │                    │                     │
          │ Single destination  │                    │ Single destination  │
          └─────────┬───────────┘                    └─────────┬───────────┘
                    │                                           │
                    ▼                                           ▼
          ┌─────────────────────┐                    ┌─────────────────────┐
          │ Destination         │                    │ Destination         │
          │ (us-east-1)         │                    │ (eu-west-1)         │
          └─────────────────────┘                    └─────────────────────┘
```

#### Implementation

**Step Functions State Machine**:

```json
{
  "Comment": "Replicate secret to multiple regions in parallel",
  "StartAt": "ValidateEvent",
  "States": {
    "ValidateEvent": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:us-west-2:...:function:secrets-replicator-validator",
      "Next": "ParallelReplicate"
    },
    "ParallelReplicate": {
      "Type": "Parallel",
      "Branches": [
        {
          "StartAt": "ReplicateToUSEast1",
          "States": {
            "ReplicateToUSEast1": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:us-west-2:...:function:secrets-replicator-worker",
              "Parameters": {
                "secret_name.$": "$.secret_name",
                "dest_region": "us-east-1",
                "config_prefix": "to-us-east-1"
              },
              "End": true,
              "Retry": [{
                "ErrorEquals": ["ThrottlingError"],
                "IntervalSeconds": 2,
                "MaxAttempts": 3,
                "BackoffRate": 2.0
              }],
              "Catch": [{
                "ErrorEquals": ["States.ALL"],
                "ResultPath": "$.error",
                "Next": "USEast1Failed"
              }]
            },
            "USEast1Failed": {
              "Type": "Pass",
              "Result": {"status": "failed"},
              "End": true
            }
          }
        },
        {
          "StartAt": "ReplicateToEUWest1",
          "States": {
            "ReplicateToEUWest1": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:us-west-2:...:function:secrets-replicator-worker",
              "Parameters": {
                "secret_name.$": "$.secret_name",
                "dest_region": "eu-west-1",
                "config_prefix": "to-eu-west-1"
              },
              "End": true,
              "Retry": [{
                "ErrorEquals": ["ThrottlingError"],
                "IntervalSeconds": 2,
                "MaxAttempts": 3,
                "BackoffRate": 2.0
              }],
              "Catch": [{
                "ErrorEquals": ["States.ALL"],
                "ResultPath": "$.error",
                "Next": "EUWest1Failed"
              }]
            },
            "EUWest1Failed": {
              "Type": "Pass",
              "Result": {"status": "failed"},
              "End": true
            }
          }
        }
      ],
      "Next": "AggregateResults"
    },
    "AggregateResults": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:us-west-2:...:function:secrets-replicator-aggregator",
      "End": true
    }
  }
}
```

#### Pros
✅ **Parallel execution** - All destinations replicate simultaneously
✅ **Independent retries** - Each destination can retry independently
✅ **Partial success** - Some destinations can succeed while others fail
✅ **Unlimited destinations** - Not limited by Lambda timeout
✅ **Built-in error handling** - Step Functions handles retries and DLQ
✅ **Visual monitoring** - AWS Console shows execution flow
✅ **Flexible orchestration** - Can add pre/post-processing steps

#### Cons
❌ **Additional cost** - Step Functions state transitions ($0.025 per 1000 transitions)
❌ **Increased complexity** - Another AWS service to manage
❌ **Higher latency** - Orchestration overhead (typically +500ms)
❌ **More moving parts** - Validator, Worker, Aggregator Lambdas
❌ **Debugging complexity** - Need to check both Step Functions and Lambda logs

#### When to Use
- ✅ You have **5+ destination regions**
- ✅ You need **independent retry** per destination
- ✅ You want **parallel execution** (fastest option)
- ✅ You need **partial success handling**
- ✅ Total replication time would exceed Lambda timeout

---

## Comparison Matrix

| Criteria | Option 1: Multiple Lambdas | Option 2: Multi-Destination | Option 3: Step Functions |
|----------|---------------------------|----------------------------|-------------------------|
| **Cost (per 1M events)** | $0.60 (3 regions × $0.20) | $0.20 (1 invocation) | $0.45 ($0.20 + $0.25) |
| **Latency** | ~1-2s per region (parallel) | ~2-5s (sequential) | ~1-2s (parallel) + 500ms overhead |
| **Complexity** | Low | Medium | High |
| **Scalability** | Excellent (independent) | Good (limited by timeout) | Excellent (unlimited) |
| **Failure Isolation** | Excellent | Poor | Excellent |
| **Code Changes** | None | Significant | Moderate |
| **Operational Overhead** | High (N stacks) | Low (1 stack) | Medium (1 stack + State Machine) |
| **Max Destinations** | Unlimited | ~10-20 (timeout limited) | Unlimited |
| **Retry Flexibility** | Per-Lambda | All-or-nothing | Per-destination |

---

## Recommendations

### For 2-3 Destinations
**Use Option 1 (Multiple Lambdas)** ✅
- Simplest approach
- No code changes
- Acceptable cost
- Complete isolation

### For 3-10 Destinations
**Use Option 2 (Multi-Destination)** ✅ RECOMMENDED
- Best cost/benefit ratio
- Centralized management
- Acceptable complexity
- Good for most use cases

### For 10+ Destinations or Complex Requirements
**Use Option 3 (Step Functions)** ✅
- Handles many destinations
- Parallel execution
- Best failure handling
- Worth the complexity

---

## Implementation Guide for Option 1 (Quick Start)

Since Option 1 requires no code changes, here's how to implement it today:

### Step 1: Deploy Multiple Stacks

```bash
#!/bin/bash
# deploy-multi-region.sh

REGIONS=("us-east-1" "us-east-2" "eu-west-1")

for REGION in "${REGIONS[@]}"; do
  echo "Deploying to $REGION..."

  sam deploy \
    --stack-name "secrets-replicator-to-${REGION}" \
    --region us-west-2 \
    --parameter-overrides \
      DestinationRegion="${REGION}" \
      SecretsFilter="secrets-replicator/filters/to-${REGION}" \
      DestSecretNames="secrets-replicator/names/to-${REGION}" \
      Environment=prod \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset
done
```

### Step 2: Create Configuration Secrets

```bash
# Create filter for us-east-1
aws secretsmanager create-secret \
  --name secrets-replicator/filters/to-us-east-1 \
  --secret-string '{
    "app/prod/*": "secrets-replicator/transformations/to-us-east-1",
    "db/prod/*": ""
  }'

# Create transformation for us-east-1
aws secretsmanager create-secret \
  --name secrets-replicator/transformations/to-us-east-1 \
  --secret-string 's/us-west-2/us-east-1/g
s/usw2/use1/g'

# Create name mapping for us-east-1 (if needed)
aws secretsmanager create-secret \
  --name secrets-replicator/names/to-us-east-1 \
  --secret-string '{
    "app/prod/api": "app/prod/api-east"
  }'

# Repeat for other regions...
```

### Step 3: Test Replication

```bash
# Update a source secret
aws secretsmanager update-secret \
  --secret-id app/prod/db \
  --secret-string '{"host":"db.us-west-2.amazonaws.com","region":"us-west-2"}' \
  --region us-west-2

# Wait 5-10 seconds for replication

# Verify in us-east-1
aws secretsmanager get-secret-value \
  --secret-id app/prod/db \
  --region us-east-1

# Verify in eu-west-1
aws secretsmanager get-secret-value \
  --secret-id app/prod/db \
  --region eu-west-1
```

---

## Migration Path

If you start with Option 1 and want to migrate to Option 2 later:

1. **Develop and test Option 2** in a separate stack
2. **Run both in parallel** for a validation period
3. **Compare results** between old and new implementations
4. **Switch EventBridge rule** to new Lambda
5. **Decommission old Lambdas** after validation

---

## Conclusion

For **most use cases**, start with **Option 1 (Multiple Lambdas)** since it:
- Works today with no code changes
- Provides complete isolation
- Is easy to understand and debug
- Has acceptable cost for 2-5 regions

If you grow beyond 5 regions or need better cost optimization, implement **Option 2 (Multi-Destination)** as a v2 enhancement.

Only use **Option 3 (Step Functions)** if you have specific requirements for parallel execution or very many destinations (10+).
