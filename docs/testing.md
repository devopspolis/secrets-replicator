# Testing Guide

Comprehensive testing documentation for the Secrets Replicator project.

---

## Table of Contents

1. [Overview](#overview)
2. [Test Organization](#test-organization)
3. [Running Tests](#running-tests)
4. [Unit Tests](#unit-tests)
5. [Integration Tests](#integration-tests)
6. [Performance Tests](#performance-tests)
7. [Security Tests](#security-tests)
8. [Test Coverage](#test-coverage)
9. [CI/CD Integration](#cicd-integration)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Secrets Replicator test suite includes:

- **Unit Tests** (290 tests): Test individual components in isolation
- **Integration Tests** (30+ tests): Test AWS integration end-to-end
- **Performance Tests** (15+ tests): Measure latency and throughput
- **Security Tests** (12+ tests): Validate security properties

### Current Coverage

- **Total Coverage**: 92.39%
- **Target Coverage**: 90%
- **Total Tests**: 350+
- **Test Execution Time**: ~6 seconds (unit), ~5 minutes (integration)

---

## Test Organization

```
tests/
├── __init__.py
├── fixtures/                   # Test fixtures and sample data
│   ├── __init__.py
│   └── eventbridge_events.py   # Sample EventBridge events
├── unit/                       # Unit tests (no AWS required)
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_aws_clients.py     # AWS client wrapper tests (mocked)
│   ├── test_config.py          # Configuration loading tests
│   ├── test_event_parser.py    # EventBridge event parsing
│   ├── test_handler_integration.py  # Handler tests (mocked AWS)
│   ├── test_logger.py          # Logging functionality
│   ├── test_metrics.py         # CloudWatch metrics
│   ├── test_retry.py           # Retry logic
│   ├── test_sedfile_loader.py  # Sedfile loading
│   ├── test_transformer.py     # Transformation engine
│   └── test_utils.py           # Utility functions
├── integration/                # Integration tests (requires AWS)
│   ├── __init__.py
│   ├── conftest.py             # Integration test fixtures
│   ├── test_same_region.py     # Same-region replication
│   ├── test_cross_region.py    # Cross-region replication
│   ├── test_error_scenarios.py # Error handling
│   └── test_security.py        # Security validation
└── performance/                # Performance tests (requires AWS)
    ├── __init__.py
    ├── conftest.py
    └── test_performance.py     # Performance benchmarks
```

---

## Running Tests

### Quick Start

```bash
# Run all unit tests
./scripts/run-tests.sh --unit

# Run unit tests with coverage
./scripts/run-tests.sh --unit --coverage --html

# Run integration tests (requires AWS credentials)
./scripts/run-tests.sh --integration

# Run all tests
./scripts/run-tests.sh --all
```

### Using Pytest Directly

```bash
# Activate virtual environment
source venv/bin/activate

# Run unit tests
pytest tests/unit/ -v

# Run unit tests with coverage
pytest tests/unit/ -v --cov=src --cov-report=term-missing

# Run integration tests (requires --integration flag)
pytest tests/integration/ -v --integration

# Run specific test file
pytest tests/unit/test_transformer.py -v

# Run specific test
pytest tests/unit/test_transformer.py::TestSedRule::test_valid_sed_rule -v

# Run tests matching pattern
pytest -k "test_replication" -v
```

---

## Unit Tests

Unit tests run in isolation without requiring AWS credentials. They use `moto` to mock AWS services.

### Running Unit Tests

```bash
# All unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ -v --cov=src --cov-report=html

# Specific module
pytest tests/unit/test_transformer.py -v

# Fast mode (no coverage)
pytest tests/unit/ -v --tb=short
```

### Key Unit Test Modules

**test_transformer.py** (85% coverage)
- Sed transformation parsing and application
- JSON transformation with JSONPath
- Edge cases (empty secrets, unicode, large secrets)

**test_aws_clients.py** (96% coverage)
- Secrets Manager operations (mocked)
- Cross-account AssumeRole (mocked)
- Error handling and retries

**test_handler_integration.py** (90% coverage)
- End-to-end handler flow (mocked AWS)
- Error scenarios
- Metric publishing

**test_config.py** (99% coverage)
- Configuration loading from environment
- Validation logic
- Edge cases

### Example

```bash
# Run transformer tests with verbose output
pytest tests/unit/test_transformer.py -v

# Run specific test with debug output
pytest tests/unit/test_transformer.py::TestSedRule::test_valid_sed_rule -vvs
```

---

## Integration Tests

Integration tests require AWS credentials and create real AWS resources (secrets).

### Prerequisites

1. **AWS Credentials**:
   ```bash
   aws configure
   # OR
   export AWS_PROFILE=your-profile
   ```

2. **AWS Permissions**:
   - `secretsmanager:CreateSecret`
   - `secretsmanager:GetSecretValue`
   - `secretsmanager:PutSecretValue`
   - `secretsmanager:DeleteSecret`
   - `secretsmanager:DescribeSecret`

3. **AWS Regions** (for cross-region tests):
   - Source region (default: us-east-1)
   - Destination region (default: us-west-2)

### Running Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v --integration

# Run with specific regions
pytest tests/integration/ -v --integration \
  --aws-region us-east-1 \
  --dest-region us-west-2

# Run same-region tests only
pytest tests/integration/test_same_region.py -v --integration

# Run cross-region tests only
pytest tests/integration/test_cross_region.py -v --integration

# Run security tests
pytest tests/integration/test_security.py -v --integration

# Run error scenario tests
pytest tests/integration/test_error_scenarios.py -v --integration
```

### Test Categories

**Same-Region Tests** (`test_same_region.py`)
- Basic replication without transformation
- Sed transformations
- JSON transformations
- Update existing secrets
- Large secrets (60KB)
- Special characters
- Concurrent replications

**Cross-Region Tests** (`test_cross_region.py`)
- Basic cross-region replication
- Cross-region with transformations
- Latency measurements
- KMS encryption
- Multiple region pairs

**Error Scenarios** (`test_error_scenarios.py`)
- Source secret not found
- Binary secrets (not supported)
- Secrets too large
- Invalid event format
- Missing configuration
- Network errors and retries

**Security Tests** (`test_security.py`)
- No plaintext secrets in logs
- Error messages don't leak secrets
- KMS encryption verification
- IAM permissions validation
- Secret version tracking
- Regex safety (ReDoS prevention)

### Cleanup

Integration tests automatically clean up created secrets in the `cleanup` phase. If tests are interrupted:

```bash
# List test secrets
aws secretsmanager list-secrets --query 'SecretList[?starts_with(Name, `test-`)].Name'

# Delete test secrets
aws secretsmanager delete-secret --secret-id test-secret-name --force-delete-without-recovery
```

---

## Performance Tests

Performance tests measure latency, throughput, and resource usage.

### Running Performance Tests

```bash
# Run all performance tests
pytest tests/performance/ -v --integration

# Run specific performance test
pytest tests/performance/test_performance.py::TestReplicationPerformance::test_replication_by_size -v --integration

# Run benchmarks only
pytest tests/performance/ -v -m benchmark
```

### Performance Metrics

**Replication Performance**
- Small secrets (<1KB): < 3 seconds
- Medium secrets (10-32KB): < 4 seconds
- Large secrets (60KB): < 5 seconds

**Transformation Performance**
- Sed (10 rules): < 100ms average
- JSON (4 mappings): < 50ms average
- Complex regex: < 100ms average

**Cross-Region Performance**
- us-east-1 → us-west-2: < 5 seconds average

**Throughput**
- Sequential replications: ~0.2-0.5 replications/second
- Transformation throughput: 10-20 transformations/second

### Benchmarking

```bash
# Run with timing output
pytest tests/performance/ -v --integration --durations=10

# Run memory profiling
pytest tests/performance/test_performance.py::TestMemoryUsage -v
```

---

## Security Tests

Security tests validate that the application follows security best practices.

### Running Security Tests

```bash
# Run all security tests
pytest tests/integration/test_security.py -v --integration

# Run specific security test
pytest tests/integration/test_security.py::TestSecurityValidation::test_no_plaintext_secrets_in_logs -v --integration
```

### Security Validations

✅ **No Plaintext Secrets in Logs**
- Verifies secret values never appear in CloudWatch Logs
- Tests log redaction and masking

✅ **Error Messages Don't Leak Secrets**
- Ensures error responses don't contain secret values
- Validates sanitization logic

✅ **KMS Encryption**
- Verifies secrets are encrypted with KMS
- Tests custom KMS key support

✅ **IAM Permissions**
- Validates least-privilege access
- Tests cross-account permissions

✅ **Secret Version Tracking**
- Ensures version IDs are properly tracked
- Verifies idempotency

✅ **Regex Safety**
- Prevents ReDoS (Regular Expression Denial of Service)
- Validates dangerous pattern detection

---

## Test Coverage

### Viewing Coverage

```bash
# Generate coverage report
pytest tests/unit/ --cov=src --cov-report=term-missing

# Generate HTML report
pytest tests/unit/ --cov=src --cov-report=html
open htmlcov/index.html

# Generate XML report (for CI/CD)
pytest tests/unit/ --cov=src --cov-report=xml
```

### Coverage by Module

| Module | Coverage | Missing Lines |
|--------|----------|---------------|
| src/exceptions.py | 100% | - |
| src/logger.py | 100% | - |
| src/metrics.py | 100% | - |
| src/config.py | 99% | 1 line |
| src/utils.py | 98% | 2 lines |
| src/retry.py | 97% | 1 line |
| src/aws_clients.py | 96% | 4 lines |
| src/sedfile_loader.py | 95% | 3 lines |
| src/event_parser.py | 93% | 6 lines |
| src/transformer.py | 85% | 21 lines |
| src/handler.py | 75% | 27 lines |

### Improving Coverage

```bash
# Find uncovered lines
pytest tests/unit/ --cov=src --cov-report=term-missing | grep "MISS"

# Run coverage on specific module
pytest tests/unit/test_handler.py --cov=src.handler --cov-report=term-missing
```

---

## CI/CD Integration

### GitHub Actions (Recommended)

Create `.github/workflows/test.yml`:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run CI tests
        run: ./scripts/ci-tests.sh

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          fail_ci_if_error: true
```

### Using CI Script

```bash
# Run full CI test suite
./scripts/ci-tests.sh

# Skip linting
./scripts/ci-tests.sh --skip-lint

# Include integration tests (requires AWS credentials)
./scripts/ci-tests.sh --integration

# Strict mode (fail on warnings)
./scripts/ci-tests.sh --strict
```

### Environment Variables for CI

```bash
export AWS_REGION=us-east-1
export AWS_DEST_REGION=us-west-2
export COVERAGE_THRESHOLD=90
```

---

## Troubleshooting

### Common Issues

**1. Integration tests skip with "need --integration option to run"**

```bash
# Use --integration flag
pytest tests/integration/ -v --integration
```

**2. AWS credentials not configured**

```bash
# Check credentials
aws sts get-caller-identity

# Configure if needed
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_REGION=us-east-1
```

**3. Permission denied on test scripts**

```bash
# Make scripts executable
chmod +x scripts/run-tests.sh scripts/ci-tests.sh
```

**4. Import errors**

```bash
# Install in editable mode
pip install -e ".[dev]"

# Or activate virtual environment
source venv/bin/activate
```

**5. Test secrets not cleaned up**

```bash
# Manual cleanup
aws secretsmanager list-secrets \
  --query 'SecretList[?starts_with(Name, `test-`)].Name' \
  --output table

# Delete all test secrets
for secret in $(aws secretsmanager list-secrets --query 'SecretList[?starts_with(Name, `test-`)].Name' --output text); do
  aws secretsmanager delete-secret --secret-id "$secret" --force-delete-without-recovery
done
```

**6. Cross-region tests failing**

```bash
# Check permissions in both regions
aws secretsmanager list-secrets --region us-east-1
aws secretsmanager list-secrets --region us-west-2

# Specify regions explicitly
pytest tests/integration/test_cross_region.py -v --integration \
  --aws-region us-east-1 \
  --dest-region us-west-2
```

**7. Performance tests too slow**

```bash
# Run with timeout
pytest tests/performance/ -v --integration --timeout=300

# Skip slow tests
pytest tests/performance/ -v --integration -m "not slow"
```

---

## Best Practices

### Writing Tests

1. **Use fixtures**: Leverage pytest fixtures for setup/teardown
2. **Test isolation**: Each test should be independent
3. **Descriptive names**: Test names should describe what they test
4. **One assertion per test**: Focus on single behavior
5. **Test edge cases**: Empty values, large values, special characters
6. **Mock external dependencies**: Use moto for AWS services in unit tests

### Running Tests Locally

```bash
# Before committing
./scripts/run-tests.sh --unit --coverage

# Before pushing
./scripts/ci-tests.sh

# Before deploying
./scripts/run-tests.sh --all
```

### Test Markers

```bash
# Run only integration tests
pytest -m integration -v

# Skip slow tests
pytest -m "not slow" -v

# Run only performance tests
pytest -m performance -v

# Run only benchmarks
pytest -m benchmark -v
```

---

## Test Data

### Sample Secrets

```json
// Small secret
{"username": "testuser", "password": "testpass123"}

// Medium secret with AWS resources
{
  "environment": "production",
  "region": "us-east-1",
  "database": {
    "host": "db-prod.us-east-1.rds.amazonaws.com",
    "port": 5432
  },
  "redis": "redis-prod.us-east-1.cache.amazonaws.com"
}

// Large secret (for performance testing)
// 60KB of data
```

### Sample Sedfiles

```sed
# Basic transformations
s/dev/prod/g
s/us-east-1/us-west-2/g
s/http:/https:/g

# Complex regex
s/arn:aws:[a-z]+:us-east-1:[0-9]+:[a-z]+\/.+/arn:aws:SERVICE:us-west-2:ACCOUNT:RESOURCE/g
```

---

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [moto Documentation](https://docs.getmoto.org/) (AWS mocking)
- [coverage.py Documentation](https://coverage.readthedocs.io/)
- [AWS SDK for Python (Boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

---

**Last Updated**: 2025-11-01
**Test Suite Version**: Phase 6
**Total Tests**: 350+
**Coverage**: 92.39%
