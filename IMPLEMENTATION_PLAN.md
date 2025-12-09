# Implementation Plan - Secrets Replicator

## Overview

This document outlines the step-by-step implementation plan for the Secrets Replicator project, organized into logical phases with clear milestones and deliverables.

## Development Phases

### Phase 1: Foundation & Core Transformation Engine

**Duration**: 1-2 weeks
**Goal**: Build and test the transformation engine in isolation

#### Tasks

- [ ] **1.1 Project Setup**
  - [ ] Create directory structure
    ```
    src/
    ├── __init__.py
    ├── handler.py
    ├── transformer.py
    ├── aws_clients.py
    └── utils.py
    tests/
    ├── __init__.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_transformer.py
    │   └── test_handler.py
    └── integration/
        ├── __init__.py
        └── test_e2e.py
    ```
  - [ ] Create `requirements.txt`
    ```
    boto3>=1.34.0
    botocore>=1.34.0
    tenacity>=8.2.3
    jsonpath-ng>=1.6.0
    pytest>=7.4.0
    pytest-cov>=4.1.0
    moto>=4.2.0  # for mocking AWS services
    ```
  - [ ] Create `requirements-dev.txt`
    ```
    black>=23.0.0
    pylint>=3.0.0
    mypy>=1.7.0
    boto3-stubs[secretsmanager,sts]>=1.34.0
    ```
  - [ ] Setup `.gitignore` for Python projects
  - [ ] Initialize Git repository (already done)
  - [ ] Create initial `template.yaml` SAM template skeleton

- [ ] **1.2 Transformation Engine - Sed Mode**
  - [ ] Create `transformer.py` module
  - [ ] Implement `SedRule` dataclass
    ```python
    @dataclass
    class SedRule:
        pattern: str
        replacement: str
        flags: int = 0
    ```
  - [ ] Implement `parse_sedfile()` function
    - Parse sed-style rules from text file
    - Support comments and empty lines
    - Validate regex patterns
  - [ ] Implement `apply_sed_transforms()` function
    - Apply regex replacements in order
    - Handle errors gracefully
    - Enforce timeout limits (prevent ReDoS)
  - [ ] Add unit tests for sed transformations
    - Test basic replacements
    - Test global flag (`/g`)
    - Test case-insensitive flag (`/i`)
    - Test special regex characters
    - Test malformed regex (negative test)
    - Test ReDoS protection

- [ ] **1.3 Transformation Engine - JSON Mode**
  - [ ] Implement `JsonMapping` dataclass
    ```python
    @dataclass
    class JsonMapping:
        path: str        # JSONPath expression
        find: str        # Value to find
        replace: str     # Replacement value
    ```
  - [ ] Implement `parse_json_mapping()` function
    - Parse JSON mapping configuration
    - Validate JSONPath expressions
  - [ ] Implement `apply_json_transforms()` function
    - Parse JSON secret
    - Apply JSONPath-based replacements
    - Preserve JSON structure
    - Handle missing paths gracefully
  - [ ] Add unit tests for JSON transformations
    - Test simple field replacement
    - Test nested field replacement
    - Test array element replacement
    - Test missing path handling
    - Test invalid JSON (negative test)
    - Test JSONPath edge cases

- [ ] **1.4 Utilities Module**
  - [ ] Create `utils.py` with helper functions
    - `mask_secret()` - Mask secret for logging (show first/last 4 chars)
    - `validate_regex()` - Validate regex pattern safety
    - `get_secret_metadata()` - Extract metadata without value
    - `format_arn()` - Format/parse AWS ARNs
  - [ ] Add unit tests for utilities

#### Deliverables
- Working transformation engine with 90%+ test coverage
- Comprehensive unit tests
- Documentation for transformation rule syntax

---

### Phase 2: Lambda Handler & Event Processing

**Duration**: 1-2 weeks
**Goal**: Build Lambda handler that processes EventBridge events

#### Tasks

- [ ] **2.1 Event Parsing**
  - [ ] Create `event_parser.py` module
  - [ ] Implement `parse_eventbridge_event()` function
    - Extract secret ARN/name from CloudTrail event
    - Handle both `requestParameters` and `responseElements`
    - Handle both `arn` and `aRN` fields
    - Extract event metadata (timestamp, user, etc.)
  - [ ] Create sample EventBridge event fixtures for testing
    - `PutSecretValue` event
    - `UpdateSecret` event
    - `ReplicateSecretToRegions` event
    - Invalid/malformed events
  - [ ] Add unit tests for event parsing

- [ ] **2.2 Configuration Management**
  - [ ] Create `config.py` module
  - [ ] Implement configuration loading from environment variables
    ```python
    @dataclass
    class ReplicatorConfig:
        dest_region: str
        dest_secret_name: Optional[str]
        dest_account_role_arn: Optional[str]
        transformation_secret_prefix: str = "secrets-replicator/transformations/"
        transform_mode: str = "sed"
        log_level: str = "INFO"
        enable_metrics: bool = True
    ```
  - [ ] Add validation for required fields
  - [ ] Add unit tests for configuration

- [ ] **2.3 Lambda Handler**
  - [ ] Implement `lambda_handler()` in `handler.py`
    - Parse EventBridge event
    - Load configuration
    - Retrieve source secret (placeholder - implement in Phase 3)
    - Apply transformations
    - Write destination secret (placeholder - implement in Phase 3)
    - Handle errors and emit metrics
  - [ ] Implement structured logging
    - JSON log format
    - Metadata only (no secret values)
    - Contextual information (request ID, ARNs, etc.)
  - [ ] Add unit tests for handler logic (with mocked AWS calls)

- [ ] **2.4 Transformation Secret Loading**
  - [ ] Implement transformation secret loader
    - Retrieve transformation secret name from source secret tags
    - Load transformation secret from Secrets Manager (with prefix)
    - Cache in memory for Lambda execution context
    - Exclude transformation secrets from replication
  - [ ] Add unit tests with mocked Secrets Manager (using `moto`)

#### Deliverables
- Lambda handler that processes EventBridge events
- Configuration management system
- Comprehensive unit tests with mocked AWS services

---

### Phase 3: AWS Integration & Secret Management

**Duration**: 1-2 weeks
**Goal**: Integrate with AWS Secrets Manager for read/write operations

#### Tasks

- [ ] **3.1 AWS Clients Module**
  - [ ] Create `aws_clients.py` module
  - [ ] Implement `SecretsManagerClient` class
    - `__init__()` - Initialize with region and optional role ARN
    - `_assume_role()` - STS AssumeRole for cross-account
    - `get_secret()` - Retrieve secret value
    - `put_secret()` - Create or update secret
    - `secret_exists()` - Check if secret exists
    - `get_secret_tags()` - Retrieve secret tags for transformation routing
  - [ ] Add error handling for AWS exceptions
    - `ResourceNotFoundException`
    - `AccessDeniedException`
    - `InvalidRequestException`
    - `ThrottlingException`
    - `InternalServiceError`
  - [ ] Add unit tests with `moto` mocking

- [ ] **3.2 Source Secret Retrieval**
  - [ ] Implement source secret retrieval in handler
    - Create Secrets Manager client for source region
    - Call `GetSecretValue`
    - Handle both `SecretString` and `SecretBinary`
    - Extract metadata (ARN, version ID, etc.)
  - [ ] Add integration tests (requires AWS account)
    - Create test secret
    - Retrieve test secret
    - Cleanup test resources

- [ ] **3.3 Destination Secret Writing**
  - [ ] Implement destination secret writing in handler
    - Determine if secret exists
    - Call `CreateSecret` (if new) or `PutSecretValue` (if exists)
    - Handle KMS encryption
    - Preserve tags (optional)
  - [ ] Implement idempotency check
    - Compare source and destination version IDs
    - Skip write if already up-to-date
  - [ ] Add integration tests
    - Write to same region
    - Write to different region
    - Update existing secret
    - Create new secret

- [ ] **3.4 Cross-Account Support**
  - [ ] Implement STS AssumeRole flow
    - Create STS client
    - Assume role with external ID
    - Use temporary credentials for destination client
    - Handle role assumption errors
  - [ ] Create IAM policy templates
    - Lambda execution role (source account)
    - Destination role (destination account)
    - Trust policy for destination role
  - [ ] Add integration tests (requires two AWS accounts)
    - Assume role in destination account
    - Write secret cross-account
    - Verify permissions

#### Deliverables
- Full integration with AWS Secrets Manager
- Cross-account replication working
- IAM policy templates
- Integration test suite

---

### Phase 4: Error Handling & Resilience

**Duration**: 1 week
**Goal**: Implement robust error handling, retries, and observability

#### Tasks

- [ ] **4.1 Retry Logic**
  - [ ] Implement exponential backoff with `tenacity`
    - Retry on transient errors (throttling, internal errors)
    - Stop after 5 attempts
    - Exponential wait: 2s, 4s, 8s, 16s, 32s
  - [ ] Add jitter to prevent thundering herd
  - [ ] Add unit tests for retry behavior

- [ ] **4.2 Dead Letter Queue**
  - [ ] Update SAM template to include SQS DLQ
  - [ ] Configure Lambda DLQ
  - [ ] Send permanent failures to DLQ
  - [ ] Add CloudWatch alarm for DLQ depth
  - [ ] Create DLQ processor Lambda (optional - for Phase 6)

- [ ] **4.3 CloudWatch Metrics**
  - [ ] Implement custom metrics in handler
    - `ReplicationSuccess` (count)
    - `ReplicationFailure` (count)
    - `TransformationDuration` (milliseconds)
    - `ReplicationDuration` (milliseconds)
    - `AssumeRoleSuccess` (count)
    - `AssumeRoleFailure` (count)
  - [ ] Add dimensions (SourceRegion, DestinationRegion, TransformationType)
  - [ ] Test metric publishing

- [ ] **4.4 Structured Logging**
  - [ ] Implement JSON structured logging
    - Use Python `logging` with JSON formatter
    - Include request ID, ARNs, duration, etc.
    - NEVER log secret values
  - [ ] Add log level configuration
  - [ ] Test log output format

- [ ] **4.5 CloudWatch Alarms**
  - [ ] Update SAM template with alarms
    - Replication failure alarm
    - DLQ depth alarm
    - Lambda error rate alarm
    - Lambda duration alarm (timeout warning)
  - [ ] Create SNS topic for alarm notifications
  - [ ] Test alarm triggering

#### Deliverables
- Robust error handling with retries
- Dead Letter Queue configured
- CloudWatch metrics and alarms
- Structured logging implemented

---

### Phase 5: SAM Template & Deployment

**Duration**: 1 week
**Goal**: Complete SAM template for easy deployment

#### Tasks

- [ ] **5.1 SAM Template**
  - [ ] Define all parameters
    ```yaml
    Parameters:
      SourceSecretPattern:
        Type: String
        Description: ARN pattern for source secrets (supports wildcards)
      DestinationRegion:
        Type: String
        Description: AWS region for destination secret
      DestinationSecretName:
        Type: String
        Description: Name for destination secret (optional)
        Default: ""
      DestinationAccountRoleArn:
        Type: String
        Description: IAM role ARN in destination account (for cross-account)
        Default: ""
      TransformationSecretPrefix:
        Type: String
        Description: Prefix for transformation secrets in Secrets Manager
        Default: "secrets-replicator/transformations/"
      TransformMode:
        Type: String
        Description: Transformation mode (sed or json)
        Default: sed
        AllowedValues:
          - sed
          - json
      LogLevel:
        Type: String
        Description: Log level
        Default: INFO
        AllowedValues:
          - DEBUG
          - INFO
          - WARN
          - ERROR
    ```
  - [ ] Define Lambda function resource
    - Runtime: Python 3.12
    - Memory: 256 MB
    - Timeout: 60 seconds
    - Environment variables from parameters
  - [ ] Define IAM execution role
    - Secrets Manager read permissions (source secrets and transformation secrets)
    - STS AssumeRole permissions
    - CloudWatch Logs permissions
    - CloudWatch PutMetricData permissions
  - [ ] Define EventBridge rule
    - Event pattern for Secrets Manager updates
    - Target: Lambda function
    - Optional: filter by source secret ARN
  - [ ] Define DLQ (SQS)
  - [ ] Define CloudWatch alarms
  - [ ] Define SNS topic for notifications

- [ ] **5.2 SAM Configuration**
  - [ ] Create `samconfig.toml` for deployment
  - [ ] Define deployment stages (dev, qa, prod)
  - [ ] Configure stack name and tags

- [ ] **5.3 Example Configurations**
  - [ ] Create example parameter files
    - `examples/same-region.yaml` - Same account, same region
    - `examples/cross-region.yaml` - Same account, cross-region
    - `examples/cross-account.yaml` - Cross-account, same region
    - `examples/cross-account-region.yaml` - Cross-account, cross-region
  - [ ] Create example sedfiles
    - `examples/sedfile-basic.sed` - Simple replacements
    - `examples/sedfile-regions.sed` - Region swapping
    - `examples/sedfile-json.json` - JSON field mappings

- [ ] **5.4 Deployment Scripts**
  - [ ] Create deployment script `scripts/deploy.sh`
    - Build Lambda package
    - Run SAM build
    - Deploy to AWS
    - Output stack outputs
  - [ ] Create cleanup script `scripts/cleanup.sh`
    - Delete CloudFormation stack
    - Optionally clean up transformation secrets
    - Purge SQS DLQ
  - [ ] Make scripts executable and test

#### Deliverables
- Complete SAM template ready for deployment
- Example configurations for all scenarios
- Deployment and cleanup scripts
- Documentation for manual deployment

---

### Phase 6: Testing & Validation

**Duration**: 1-2 weeks
**Goal**: Comprehensive testing across all scenarios

#### Tasks

- [ ] **6.1 Unit Tests**
  - [ ] Achieve 90%+ code coverage
  - [ ] Test all error paths
  - [ ] Test edge cases
  - [ ] Run with `pytest --cov`

- [ ] **6.2 Integration Tests**
  - [ ] Test same-region replication
    - Create source secret
    - Trigger Lambda
    - Verify destination secret
    - Verify transformations applied
    - Cleanup resources
  - [ ] Test cross-region replication
    - Deploy Lambda in us-east-1
    - Replicate to us-west-2
    - Verify destination
  - [ ] Test cross-account replication (requires second AWS account)
    - Setup destination account role
    - Configure trust policy
    - Test replication
    - Verify permissions
  - [ ] Test EventBridge trigger
    - Create source secret
    - Update source secret value
    - Wait for EventBridge → Lambda
    - Verify destination updated
  - [ ] Test error scenarios
    - Invalid sedfile
    - Missing source secret
    - Permission denied
    - Throttling
    - DLQ handling

- [ ] **6.3 Performance Testing**
  - [ ] Test with small secrets (<1KB)
  - [ ] Test with medium secrets (10KB)
  - [ ] Test with large secrets (64KB - max size)
  - [ ] Measure transformation duration
  - [ ] Measure end-to-end replication time
  - [ ] Test concurrent replications (10+ simultaneous)

- [ ] **6.4 Security Testing**
  - [ ] Verify no plaintext secrets in logs
  - [ ] Verify KMS encryption working
  - [ ] Verify IAM permissions (least privilege)
  - [ ] Test with external security scanner (optional)
  - [ ] Review CloudTrail logs for audit trail

- [ ] **6.5 Test Automation**
  - [ ] Create test automation script
  - [ ] Add to CI/CD pipeline (Phase 7)

#### Deliverables
- Comprehensive test suite
- Test automation scripts
- Performance benchmarks
- Security validation report

---

### Phase 7: CI/CD & Automation

**Duration**: 1 week
**Goal**: Automate testing, building, and deployment

#### Tasks

- [ ] **7.1 GitHub Actions Workflow**
  - [ ] Create `.github/workflows/ci.yml`
    - Trigger on push to main and PRs
    - Run linters (black, pylint, mypy)
    - Run unit tests with coverage
    - Upload coverage report to Codecov
  - [ ] Create `.github/workflows/deploy.yml`
    - Trigger on release tag
    - Build Lambda package
    - Run SAM build and package
    - Deploy to qa
    - Run integration tests
    - Deploy to production (manual approval)

- [ ] **7.2 Code Quality**
  - [ ] Setup `black` for code formatting
    - Create `.black.toml` configuration
    - Add to pre-commit hook
  - [ ] Setup `pylint` for linting
    - Create `.pylintrc` configuration
    - Set minimum score threshold (8.0+)
  - [ ] Setup `mypy` for type checking
    - Create `mypy.ini` configuration
    - Add type hints to all functions
  - [ ] Setup `pytest-cov` for coverage
    - Set minimum coverage threshold (90%)

- [ ] **7.3 Pre-commit Hooks**
  - [ ] Install `pre-commit` framework
  - [ ] Create `.pre-commit-config.yaml`
    - Run black
    - Run pylint
    - Run mypy
    - Run unit tests (fast tests only)
  - [ ] Document setup in README

- [ ] **7.4 Versioning & Releases**
  - [ ] Setup semantic versioning
  - [ ] Create CHANGELOG.md
  - [ ] Document release process
  - [ ] Create release GitHub workflow

#### Deliverables
- GitHub Actions CI/CD pipeline
- Code quality tools configured
- Pre-commit hooks setup
- Versioning and release process

---

### Phase 8: Documentation & SAR Publishing

**Duration**: 1-2 weeks
**Goal**: Complete documentation and publish to AWS SAR

#### Tasks

- [ ] **8.1 README**
  - [ ] Write comprehensive README.md
    - Project overview and value proposition
    - Architecture diagram
    - Installation instructions
    - Quick start guide
    - Configuration reference
    - Example use cases
    - Troubleshooting section
    - FAQ
    - Contributing guidelines
    - License information
  - [ ] Add badges (build status, coverage, license)

- [ ] **8.2 IAM Documentation**
  - [ ] Create `docs/iam-setup.md`
    - Lambda execution role policy
    - Destination account role policy
    - Trust policy examples
    - KMS key policy examples
    - Step-by-step setup instructions
    - Security best practices

- [ ] **8.3 Transformation Documentation**
  - [ ] Create `docs/transformations.md`
    - Sed-style syntax reference
    - JSON mapping syntax reference
    - Example transformations
    - Best practices
    - Limitations and edge cases

- [ ] **8.4 Troubleshooting Guide**
  - [ ] Create `docs/troubleshooting.md`
    - Common errors and solutions
    - Permission issues
    - KMS encryption errors
    - EventBridge trigger issues
    - Performance optimization
    - How to read CloudWatch logs
    - How to process DLQ messages

- [ ] **8.5 API Documentation**
  - [ ] Generate API docs with Sphinx (optional)
  - [ ] Document Lambda handler parameters
  - [ ] Document configuration options
  - [ ] Document transformation engine API

- [ ] **8.6 SAR Publishing Preparation**
  - [ ] Update SAM template with SAR metadata
    - Application name
    - Description (short and long)
    - Author
    - SpdxLicenseId: MIT
    - LicenseUrl
    - ReadmeUrl
    - HomePageUrl
    - SourceCodeUrl
    - SemanticVersion
    - Labels/tags
  - [ ] Create SAR-specific README
  - [ ] Test SAM package and publish locally

- [ ] **8.7 SAR Publication**
  - [ ] Create AWS SAR application
  - [ ] Upload packaged template
  - [ ] Add screenshots/diagrams
  - [ ] Test deployment from SAR
  - [ ] Mark as public (when ready)
  - [ ] Announce on AWS community forums

- [ ] **8.8 Additional Documentation**
  - [ ] Create CONTRIBUTING.md
  - [ ] Create CODE_OF_CONDUCT.md
  - [ ] Create SECURITY.md (security policy)
  - [ ] Update LICENSE file

#### Deliverables
- Complete documentation set
- Published to AWS Serverless Application Repository
- Public GitHub repository
- Community guidelines

---

## Success Criteria

### Phase 1-3
- [ ] Transformation engine works correctly
- [ ] Lambda handler processes events
- [ ] Secrets replicate successfully
- [ ] Unit test coverage ≥90%

### Phase 4-5
- [ ] Error handling robust
- [ ] Retries working
- [ ] CloudWatch metrics/alarms configured
- [ ] SAM template deploys successfully

### Phase 6-7
- [ ] Integration tests pass
- [ ] Performance acceptable (<5s end-to-end)
- [ ] CI/CD pipeline working
- [ ] No security vulnerabilities

### Phase 8
- [ ] Documentation complete
- [ ] Published to SAR
- [ ] At least 3 successful community deployments

---

## Timeline Summary

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Foundation | 1-2 weeks | 1-2 weeks |
| Phase 2: Handler | 1-2 weeks | 2-4 weeks |
| Phase 3: AWS Integration | 1-2 weeks | 3-6 weeks |
| Phase 4: Error Handling | 1 week | 4-7 weeks |
| Phase 5: SAM Template | 1 week | 5-8 weeks |
| Phase 6: Testing | 1-2 weeks | 6-10 weeks |
| Phase 7: CI/CD | 1 week | 7-11 weeks |
| Phase 8: Documentation | 1-2 weeks | 8-13 weeks |

**Total Estimated Time**: 2-3 months (part-time development)

---

## Risk Management

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| AWS API rate limiting | High | Implement exponential backoff, use reserved concurrency |
| KMS key access issues | High | Provide clear IAM documentation, test cross-account |
| EventBridge lag | Medium | Accept eventual consistency, add monitoring |
| Lambda cold starts | Low | Use provisioned concurrency for critical workloads |
| Transformation complexity | Medium | Validate sedfiles, limit regex complexity |

### Project Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep | Medium | Stick to implementation plan, defer enhancements |
| Testing complexity | High | Automate tests early, use mocking extensively |
| Documentation debt | Medium | Write docs alongside code, not at the end |
| SAR approval delays | Low | Follow AWS guidelines strictly, test thoroughly |

---

## Next Steps

**Immediate actions** (after documentation):
1. Create project directory structure
2. Initialize Python virtual environment
3. Create initial `requirements.txt`
4. Implement Phase 1.1 (Project Setup)
5. Begin Phase 1.2 (Transformation Engine - Sed Mode)

**Decision points**:
- [x] ~~Choose sedfile storage method (S3 vs bundled)~~ **Decision: Use transformation secrets in Secrets Manager**
- [ ] Decide on additional features for v1.0
- [ ] Set up AWS test accounts (need 2 for cross-account testing)
- [ ] Choose monitoring/alerting strategy beyond CloudWatch

---

## Notes

- This plan assumes part-time development (10-20 hours/week)
- Phases can overlap if multiple developers are involved
- Integration testing requires AWS account(s) with appropriate permissions
- SAR publishing requires AWS developer account
- Consider creating a demo video for SAR listing
- Plan for ongoing maintenance and feature requests after launch
