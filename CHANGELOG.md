# Changelog

All notable changes to the Secrets Replicator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI/CD workflows for trunk-based development
- Pre-commit hooks for code quality and security
- Comprehensive code quality configurations (Black, Pylint, Mypy)
- Automated release workflow
- OIDC authentication for AWS deployments

## [1.0.0] - 2025-11-01

### Added
- **Phase 1-3: Core Functionality**
  - Sed-based transformation engine with regex support
  - JSON transformation engine with JSONPath support
  - EventBridge event parsing for Secrets Manager events
  - Configuration management from environment variables
  - Sedfile loading from S3 with caching
  - AWS Secrets Manager client with retry logic
  - Cross-account replication via STS AssumeRole
  - KMS encryption support for secrets

- **Phase 4: Error Handling & Resilience**
  - Exponential backoff retry logic with jitter
  - CloudWatch metrics publishing (success, failure, duration, throttling)
  - Structured JSON logging with context
  - Dead Letter Queue (DLQ) integration
  - Exception hierarchy for AWS errors

- **Phase 5: SAM Template & Deployment**
  - Complete SAM template with all AWS resources
  - CloudWatch alarms (replication failures, throttling, high duration)
  - Multi-environment deployment support (dev, staging, prod)
  - Example deployment configurations (4 scenarios)
  - Example sedfiles (basic, regions, JSON)
  - Automated deployment and cleanup scripts
  - Comprehensive IAM policies and trust policies

- **Phase 6: Testing & Validation**
  - 290 unit tests with 92.39% coverage
  - 35+ integration tests for AWS operations
  - 15+ performance tests with benchmarks
  - 12+ security validation tests
  - Test automation scripts (local and CI/CD)
  - Comprehensive testing documentation
  - Performance benchmarks documented
  - Security validations (no secret leakage, KMS, IAM, ReDoS)

### Features
- **Secret Replication**
  - Same-region replication
  - Cross-region replication (disaster recovery)
  - Cross-account replication (organizational boundaries)
  - Support for secrets up to 64KB

- **Transformations**
  - Sed-style regex transformations with flags (global, case-insensitive)
  - JSON field transformations with JSONPath
  - Custom sedfiles from S3 or bundled
  - Region swapping (us-east-1 → us-west-2, etc.)
  - Environment transformations (dev → prod)
  - ARN transformations for AWS resources

- **Monitoring & Observability**
  - CloudWatch Logs with structured JSON
  - CloudWatch Metrics (custom namespace: SecretsReplicator)
  - CloudWatch Alarms with SNS notifications
  - Secret masking in logs (security)
  - Detailed error messages without secret leakage

- **Performance**
  - Cold start: ~2-3 seconds
  - Warm execution: ~200-500ms (no retries)
  - Transformation: 10-30ms average
  - Cross-region: ~2-5 seconds
  - Automatic retry on transient errors (up to 5 attempts)

- **Security**
  - No plaintext secrets in logs (verified)
  - KMS encryption for secrets
  - IAM least-privilege policies
  - External ID for cross-account access
  - CloudTrail integration for audit trail
  - ReDoS prevention for regex patterns

### Documentation
- Comprehensive README (installation, configuration, examples)
- IAM policies and trust policy templates
- Testing guide (650+ lines)
- Deployment guide with 4 scenarios
- Troubleshooting guide
- Phase summaries for all implementation phases

### Performance Benchmarks
- Small secrets (1KB): 1-2s same-region, 2-4s cross-region
- Medium secrets (10KB): 1.5-2.5s same-region, 2.5-4.5s cross-region
- Large secrets (60KB): 2.5-4s same-region, 3.5-5s cross-region
- Sed transformation (10 rules): 15-20ms (50-70 ops/s)
- JSON transformation (4 mappings): 10-15ms (65-100 ops/s)

### Cost Estimate
For light usage (100 replications/month):
- Lambda: ~$0.20
- EventBridge: ~$0.10
- CloudWatch: ~$0.30
- **Total: ~$0.60/month** (excludes Secrets Manager storage)

### Known Limitations
- Binary secrets not supported (returns HTTP 501)
- Maximum secret size: 64KB (configurable)
- Maximum retry attempts: 5
- EventBridge delivery: eventually consistent (~1-5 seconds)

### Technical Stack
- **Runtime**: Python 3.12
- **Framework**: AWS SAM
- **AWS Services**: Lambda, Secrets Manager, EventBridge, CloudWatch, S3, STS, KMS
- **Testing**: pytest, moto, pytest-cov
- **Code Quality**: black, pylint, mypy
- **CI/CD**: GitHub Actions

## [0.1.0] - 2025-10-15

### Added
- Initial project structure
- Basic Lambda handler skeleton
- SAM template skeleton
- Requirements files

---

**Legend:**
- `Added` for new features
- `Changed` for changes in existing functionality
- `Deprecated` for soon-to-be removed features
- `Removed` for now removed features
- `Fixed` for any bug fixes
- `Security` for vulnerability fixes

[Unreleased]: https://github.com/devopspolis/secrets-replicator/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/devopspolis/secrets-replicator/releases/tag/v1.0.0
[0.1.0]: https://github.com/devopspolis/secrets-replicator/releases/tag/v0.1.0
