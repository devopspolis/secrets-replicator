# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Principles

Secrets Replicator is designed with security as a top priority:

1. **No Secret Leakage**: Secrets are never logged in plaintext
2. **Least Privilege**: IAM policies follow least privilege principle
3. **Encryption in Transit**: All AWS API calls use TLS 1.2+
4. **Encryption at Rest**: Secrets encrypted with AWS KMS
5. **Audit Trail**: All operations logged in CloudTrail
6. **External ID**: Cross-account access requires External ID
7. **Input Validation**: All inputs validated and sanitized

## Security Features

### Secret Protection

- **Masked Logging**: All secret values are masked in CloudWatch Logs
- **No Environment Variables**: Secrets never stored in Lambda environment variables
- **Temporary Access**: Uses short-lived credentials for cross-account access
- **KMS Encryption**: Supports customer-managed KMS keys

### Code Security

- **Dependency Scanning**: Automated vulnerability scanning with Safety and Bandit
- **Static Analysis**: Pylint and Mypy for code quality
- **Pre-commit Hooks**: Security checks run before every commit
- **CI/CD Security**: GitHub Actions with OIDC (no long-lived credentials)

### Network Security

- **VPC Support**: Can be deployed in VPC with private subnets
- **TLS 1.2+**: All AWS SDK calls use TLS 1.2 or higher
- **No Public Endpoints**: Lambda doesn't expose public endpoints

### IAM Security

- **Scoped Permissions**: All IAM policies scoped to specific resources
- **Condition Keys**: KMS policies use condition keys (kms:ViaService)
- **External ID**: Required for cross-account AssumeRole
- **Session Tagging**: AssumeRole uses session naming for traceability

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, report via one of these methods:

1. **Email**: Send details to devopspolis@example.com with subject "SECURITY"
2. **GitHub Security Advisory**: Use GitHub's private vulnerability reporting feature

### What to Include

Please include the following in your report:

- **Description**: Clear description of the vulnerability
- **Impact**: Potential impact and severity
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Affected Versions**: Which versions are affected
- **Suggested Fix**: If you have a suggested fix (optional)
- **Your Contact Info**: For follow-up questions

**Example Report**:

```
Subject: SECURITY - Potential secret leakage in error messages

Description:
Under certain error conditions, the Lambda function logs the full secret value
in CloudWatch Logs instead of a masked version.

Impact:
HIGH - Secrets exposed in CloudWatch Logs, accessible to anyone with log read permissions.

Steps to Reproduce:
1. Deploy Secrets Replicator v1.0.0
2. Configure with invalid destination secret name containing special characters
3. Update source secret
4. Check CloudWatch Logs - full secret value is logged

Affected Versions:
1.0.0, 1.0.1

Suggested Fix:
Update error handling in src/handler.py:145 to mask secret values before logging.

Contact:
security-researcher@example.com
```

### What to Expect

1. **Acknowledgment**: We'll acknowledge receipt within 24 hours
2. **Assessment**: We'll assess the issue within 72 hours
3. **Updates**: We'll provide regular updates on progress
4. **Fix**: We'll develop and test a fix
5. **Disclosure**: We'll coordinate disclosure timeline with you
6. **Credit**: We'll credit you in release notes (if desired)

### Disclosure Timeline

- **0-7 days**: Validate and assess severity
- **7-30 days**: Develop and test fix
- **30-90 days**: Release fix and publish advisory
- **90+ days**: Public disclosure (if not resolved, we'll notify you first)

## Security Best Practices

### For Users

1. **Use KMS Encryption**: Always use customer-managed KMS keys
2. **Enable CloudTrail**: Monitor all Secrets Manager operations
3. **Rotate Credentials**: Enable automatic secret rotation in source account
4. **Least Privilege**: Scope IAM permissions to specific secret ARNs
5. **External ID**: Always use External ID for cross-account access
6. **VPC Deployment**: Deploy Lambda in VPC for additional network isolation
7. **Monitor Metrics**: Set up CloudWatch alarms for failures and anomalies
8. **Regular Updates**: Keep Secrets Replicator updated to latest version

### For Developers

1. **Never Log Secrets**: Always mask sensitive values before logging
2. **Input Validation**: Validate all inputs (ARNs, region names, etc.)
3. **Dependency Updates**: Regularly update dependencies for security patches
4. **Code Reviews**: Require code review for all changes
5. **Security Testing**: Run security scans in CI/CD pipeline
6. **Least Privilege Testing**: Test with minimal IAM permissions

## Security Audits

Secrets Replicator undergoes regular security audits:

- **Code Scanning**: Automated with Bandit (Python security linter)
- **Dependency Scanning**: Automated with Safety (vulnerability database)
- **SAST**: Static Application Security Testing in CI/CD
- **Manual Review**: Periodic manual security reviews

### Audit History

| Date       | Type          | Findings | Status   |
|------------|---------------|----------|----------|
| 2025-11-01 | Code Scan     | 0        | ✅ Passed |
| 2025-11-01 | Dependency    | 0        | ✅ Passed |
| 2025-11-01 | Manual Review | 0        | ✅ Passed |

## Known Security Considerations

### ReDoS (Regular Expression Denial of Service)

**Risk**: Complex sed patterns could cause catastrophic backtracking

**Mitigation**:
- Pattern validation before execution
- Lambda timeout limits execution time
- Testing with malicious patterns

**Best Practice**: Keep sed patterns simple and test with long inputs

### Secret Size Limits

**Risk**: Extremely large secrets could cause memory issues

**Mitigation**:
- Configurable max secret size (default 64KB)
- Validation before transformation
- Lambda memory limits

**Best Practice**: Use AWS native replication for large secrets

### Cross-Account Trust

**Risk**: Incorrect trust policies could grant unauthorized access

**Mitigation**:
- External ID required for cross-account access
- Trust policies scoped to specific roles
- Session naming for traceability

**Best Practice**: Review trust policies regularly, use unique External IDs

## Security Updates

Security updates are released as soon as possible after vulnerability disclosure.

### Update Notification

Subscribe to security updates:

1. **GitHub Watch**: Watch this repository for releases
2. **GitHub Security Advisories**: Enable notifications
3. **RSS Feed**: Subscribe to releases RSS

### Applying Updates

```bash
# Check current version
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.VERSION'

# Update to latest version
git pull origin main
sam build --cached
sam deploy --config-env production

# Verify update
aws lambda get-function-configuration \
  --function-name secrets-replicator-prod-replicator \
  --query 'Environment.Variables.VERSION'
```

## Compliance

Secrets Replicator supports compliance with:

- **HIPAA**: Can be deployed in HIPAA-eligible AWS services
- **PCI-DSS**: Supports PCI-DSS requirements for secret protection
- **SOC 2**: Audit logging and encryption support SOC 2 controls
- **GDPR**: Data residency controls (region-specific deployment)

**Note**: Compliance depends on proper configuration and deployment practices.

## Security Contact

For security-related questions (not vulnerabilities):

- **Email**: devopspolis@example.com
- **GitHub Discussions**: https://github.com/devopspolis/secrets-replicator/discussions

For vulnerabilities, use the [reporting process](#reporting-a-vulnerability) above.

## Acknowledgments

We thank the following security researchers for responsible disclosure:

- *None yet*

---

**Last Updated**: 2025-11-01
**Security Policy Version**: 1.0.0
