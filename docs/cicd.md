# CI/CD Guide

Comprehensive CI/CD documentation for the Secrets Replicator project.

---

## Table of Contents

1. [Overview](#overview)
2. [Workflows](#workflows)
3. [Trunk-Based Development](#trunk-based-development)
4. [Pre-Commit Hooks](#pre-commit-hooks)
5. [Code Quality](#code-quality)
6. [Release Process](#release-process)
7. [Deployment](#deployment)
8. [Environment Configuration](#environment-configuration)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The Secrets Replicator uses **GitHub Actions** for CI/CD with a **trunk-based development** workflow.

### Key Features

- ✅ Automated testing on every PR and push to main
- ✅ Code quality checks (Black, Pylint, Mypy)
- ✅ Security scanning (Bandit, Safety)
- ✅ SAM template validation
- ✅ OIDC authentication to AWS (no long-lived credentials)
- ✅ Automated deployments on releases
- ✅ Pre-commit hooks for local development

### Workflow Summary

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| **CI** | PR, Push to main | Run tests, linting, validation |
| **Deploy** | Release published, Manual | Deploy to production via OIDC |
| **Release** | Manual (workflow_dispatch) | Create tagged releases |

---

## Workflows

### 1. CI Workflow (`.github/workflows/ci.yml`)

**Triggers:**
- Pull requests to `main`
- Pushes to `main`

**Jobs:**

**a) Code Quality (`lint`)**
```yaml
- Black (code formatting)
- Pylint (code quality, min score: 8.0)
- Mypy (type checking)
```

**b) Unit Tests (`test`)**
```yaml
- Run 290 unit tests
- Coverage requirement: ≥ 90%
- Upload to Codecov
- Generate HTML coverage report
```

**c) SAM Validation (`validate-sam`)**
```yaml
- Validate template.yaml
- Run sam build
- Upload build artifacts
```

**d) Security Scan (`security`)**
```yaml
- Bandit (static security analysis)
- Safety (vulnerability checking)
- Upload security reports
```

**e) All Checks (`all-checks`)**
```yaml
- Verify all jobs passed
- Comment PR with status
- Block merge if checks fail
```

**Example PR Comment:**
```
## CI Results

✅ 4/4 checks passed

- ✅ Code Quality (Black, Pylint, Mypy)
- ✅ Unit Tests (Coverage ≥ 90%)
- ✅ SAM Template Validation
- ✅ Security Scan

🎉 All checks passed! Ready to merge.
```

### 2. Deploy Workflow (`.github/workflows/deploy.yml`)

**Triggers:**
- Release published
- Manual dispatch (`workflow_dispatch`)

**Environment:**
- Uses GitHub `production` environment
- Variables: `AWS_ACCOUNT_ID`, `AWS_REGION`
- OIDC role: `github-actions-role`

**Steps:**

1. **Authenticate to AWS** (OIDC)
   ```yaml
   - uses: aws-actions/configure-aws-credentials@v4
     with:
       role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/github-actions-role
       aws-region: ${{ vars.AWS_REGION }}
   ```

2. **Validate and Build**
   ```bash
   sam validate --lint
   sam build --cached
   ```

3. **Deploy to Production**
   ```bash
   sam deploy \
     --stack-name secrets-replicator-prod \
     --no-confirm-changeset \
     --capabilities CAPABILITY_IAM \
     --resolve-s3
   ```

4. **Smoke Tests**
   - Verify Lambda function exists
   - Check EventBridge rule is enabled
   - Get stack outputs

5. **Create Deployment Record**
   - Record deployment in GitHub
   - Set deployment status to success
   - Link to AWS Console

### 3. Release Workflow (`.github/workflows/release.yml`)

**Trigger:**
- Manual dispatch with version input

**Process:**

1. **Validate Version Format**
   ```bash
   # Valid: v1.0.0, v1.0.0-beta
   # Invalid: 1.0.0, v1.0
   ```

2. **Run Tests**
   ```bash
   pytest tests/unit/ -v --cov=src --cov-fail-under=90
   ```

3. **Generate Changelog**
   ```bash
   # Get commits since last tag
   git log $PREVIOUS_TAG..HEAD --pretty=format:"- %s (%h)"
   ```

4. **Create and Push Tag**
   ```bash
   git tag -a "v1.0.0" -m "Release v1.0.0"
   git push origin "v1.0.0"
   ```

5. **Create GitHub Release**
   - Attach release notes
   - Mark as pre-release if specified
   - Auto-generate release notes

6. **Update CHANGELOG.md**
   - Add new version entry
   - Commit and push to main

---

## Trunk-Based Development

The project uses **trunk-based development** with short-lived feature branches.

### Branch Strategy

```
main (protected)
  ├─ feature/add-json-transform (short-lived)
  ├─ fix/handle-binary-secrets (short-lived)
  └─ docs/update-readme (short-lived)
```

### Key Principles

1. **One Long-Lived Branch**: Only `main` is permanent
2. **Short-Lived Feature Branches**: Merged within 1-2 days
3. **Continuous Integration**: CI runs on every push
4. **Feature Flags**: Use config for incomplete features
5. **Small, Frequent Merges**: Small PRs merged often

### Workflow

```bash
# 1. Create feature branch from main
git checkout main
git pull origin main
git checkout -b feature/my-feature

# 2. Make changes and commit
git add .
git commit -m "feat: add my feature"

# 3. Push and create PR
git push origin feature/my-feature
# Create PR on GitHub

# 4. CI runs automatically
# - Linting
# - Tests
# - Security scan
# - SAM validation

# 5. After PR approval and CI passes, merge to main
# Branch is deleted automatically

# 6. main is always releasable
```

### Protected Branch Rules (main)

- ✅ Require PR before merging
- ✅ Require status checks to pass
  - Code Quality
  - Unit Tests
  - SAM Validation
  - Security Scan
- ✅ Require conversation resolution
- ✅ Require linear history
- ✅ Include administrators
- ✅ Restrict force pushes
- ✅ Restrict deletions

---

## Pre-Commit Hooks

Pre-commit hooks run automatically before each commit to ensure code quality.

### Installation

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Hooks Configured

1. **General File Checks**
   - Trailing whitespace
   - End of file fixer
   - YAML/JSON validation
   - Large file detection
   - Merge conflict detection
   - Private key detection

2. **Python Code Formatting**
   - **Black**: Enforce consistent formatting
   - **isort**: Sort imports

3. **Python Linting**
   - **Pylint**: Code quality (min score: 8.0)
   - **Mypy**: Type checking

4. **Security**
   - **Bandit**: Security vulnerability scanning
   - **detect-secrets**: Secret detection

5. **Shell Scripts**
   - **Shellcheck**: Shell script linting

6. **Documentation**
   - **yamllint**: YAML linting
   - **markdownlint**: Markdown linting

7. **Quick Tests**
   - Run critical unit tests (< 5 seconds)

### Skip Hooks (when needed)

```bash
# Skip all hooks
git commit --no-verify -m "Emergency fix"

# Skip specific hook
SKIP=pylint git commit -m "WIP: not ready for linting"
```

### Update Hooks

```bash
# Update to latest versions
pre-commit autoupdate

# Re-install hooks
pre-commit install --install-hooks
```

---

## Code Quality

### Black (Code Formatting)

**Configuration:** `pyproject.toml`

```toml
[tool.black]
line-length = 100
target-version = ['py312']
```

**Usage:**

```bash
# Check formatting
black --check src/ tests/

# Auto-format
black src/ tests/

# Format specific file
black src/handler.py
```

### Pylint (Code Quality)

**Configuration:** `pyproject.toml`

```toml
[tool.pylint.main]
fail-under = 8.0

[tool.pylint.messages_control]
disable = ["C0103", "C0114", "fixme"]
```

**Usage:**

```bash
# Run pylint
pylint src/

# Run with specific disable
pylint src/ --disable=fixme,duplicate-code

# Generate report
pylint src/ --output-format=json > pylint-report.json
```

**Score Ranges:**
- **10**: Perfect (very rare)
- **8.0+**: Excellent (required)
- **7.0-7.9**: Good (needs improvement)
- **< 7.0**: Poor (fails CI)

### Mypy (Type Checking)

**Configuration:** `pyproject.toml`

```toml
[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
warn_unused_configs = true
```

**Usage:**

```bash
# Run mypy
mypy src/

# Check specific module
mypy src/handler.py

# Strict mode
mypy src/ --strict
```

### Running All Quality Checks

```bash
# Use CI script
./scripts/ci-tests.sh

# Or manually
black --check src/ tests/
pylint src/ --fail-under=8.0
mypy src/ --ignore-missing-imports
```

---

## Release Process

### Semantic Versioning

Format: `vMAJOR.MINOR.PATCH[-PRERELEASE]`

Examples:
- `v1.0.0` - Major release
- `v1.1.0` - Minor release (new features)
- `v1.1.1` - Patch release (bug fixes)
- `v2.0.0-beta` - Pre-release

### Creating a Release

**Method 1: GitHub UI (Recommended)**

1. Go to Actions → Release
2. Click "Run workflow"
3. Enter version (e.g., `v1.0.0`)
4. Select pre-release if applicable
5. Click "Run workflow"

**Method 2: GitHub CLI**

```bash
# Trigger release workflow
gh workflow run release.yml \
  -f version=v1.0.0 \
  -f prerelease=false
```

**What Happens:**

1. ✅ Validates version format
2. ✅ Runs unit tests
3. ✅ Generates changelog
4. ✅ Creates and pushes git tag
5. ✅ Creates GitHub release
6. ✅ Updates CHANGELOG.md
7. ✅ **Triggers deployment workflow**

### Release Checklist

Before creating a release:

- [ ] All PRs merged to main
- [ ] CI passing on main
- [ ] CHANGELOG.md updated (automated)
- [ ] Documentation updated
- [ ] Version number decided
- [ ] Breaking changes documented (if any)

---

## Deployment

### Production Deployment

**Automatic:**
```bash
# Create release (triggers deployment)
gh workflow run release.yml -f version=v1.0.0
```

**Manual:**
```bash
# Go to Actions → Deploy → Run workflow
# Select environment: production
```

### Deployment Verification

**1. Check Workflow Status**
```bash
gh run list --workflow=deploy.yml
gh run view <run-id>
```

**2. Verify AWS Resources**
```bash
# Check stack
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-prod

# Check Lambda
aws lambda get-function \
  --function-name secrets-replicator-prod-replicator

# Check EventBridge rule
aws events describe-rule \
  --name secrets-replicator-prod-SecretChangeRule
```

**3. Run Smoke Tests**
```bash
# Create test secret
aws secretsmanager create-secret \
  --name test-deployment \
  --secret-string '{"test":"value"}'

# Update to trigger
aws secretsmanager put-secret-value \
  --secret-id test-deployment \
  --secret-string '{"test":"updated"}'

# Check logs
aws logs tail /aws/lambda/secrets-replicator-prod-replicator
```

### Rollback

**Option 1: Redeploy Previous Version**
```bash
# Create release from previous tag
gh workflow run release.yml -f version=v1.0.0
```

**Option 2: Manual Rollback**
```bash
# Checkout previous version
git checkout v1.0.0

# Deploy
sam deploy --config-env production
```

**Option 3: CloudFormation Rollback**
```bash
# In AWS Console:
# CloudFormation → Stacks → secrets-replicator-prod → Stack actions → Roll back
```

---

## Environment Configuration

### GitHub Environment: `production`

**Setup in GitHub:**

1. Go to Settings → Environments
2. Create environment: `production`
3. Add environment variables:
   - `AWS_ACCOUNT_ID`: Your AWS account ID
   - `AWS_REGION`: AWS region (e.g., `us-east-1`)
4. Add protection rules:
   - Required reviewers (optional)
   - Wait timer (optional)

### AWS IAM Role for OIDC

**Trust Policy:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:devopspolis/secrets-replicator:*"
        }
      }
    }
  ]
}
```

**Permissions Policy:**

Attach managed policies:
- `AWSCloudFormationFullAccess`
- `AWSLambda_FullAccess`
- `IAMFullAccess` (for role creation)
- `AmazonS3FullAccess` (for SAM artifacts)

Or create custom policy with least privilege.

### Secrets Configuration

**Required Secrets:** None (uses OIDC)

**Optional Secrets:**
- `CODECOV_TOKEN`: For coverage uploads

**Configure:**
```bash
# In GitHub: Settings → Secrets and variables → Actions
# Add repository secret: CODECOV_TOKEN
```

---

## Troubleshooting

### CI Failures

**Problem: Black formatting fails**
```bash
# Fix locally
black src/ tests/
git add .
git commit --amend --no-edit
git push --force
```

**Problem: Pylint score too low**
```bash
# Check score
pylint src/

# Fix issues
# Then commit
```

**Problem: Tests failing**
```bash
# Run locally
pytest tests/unit/ -v --tb=short

# Fix issues
# Commit and push
```

### Deployment Failures

**Problem: OIDC authentication fails**
```
Error: AssumeRoleWithWebIdentity failed
```

**Solution:**
1. Verify environment variables in GitHub
2. Check IAM role trust policy
3. Ensure role exists in correct account

**Problem: SAM deploy fails**
```
Error: Stack secrets-replicator-prod already exists
```

**Solution:**
```bash
# Delete stack first
aws cloudformation delete-stack --stack-name secrets-replicator-prod

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name secrets-replicator-prod

# Re-run deployment
```

**Problem: Permission denied**
```
Error: User is not authorized to perform: lambda:CreateFunction
```

**Solution:**
- Check IAM role has required permissions
- Verify role is assumed correctly
- Check CloudFormation execution role

### Pre-Commit Issues

**Problem: Hooks not running**
```bash
# Reinstall
pre-commit uninstall
pre-commit install

# Verify
pre-commit run --all-files
```

**Problem: Hook fails but commit succeeds**
```bash
# This happens with --no-verify
# Don't use --no-verify unless emergency
```

**Problem: Hook updates needed**
```bash
# Update all hooks
pre-commit autoupdate

# Reinstall
pre-commit install --install-hooks
```

---

## Best Practices

### Development Workflow

1. **Always pull latest main**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

3. **Make small, focused commits**
   ```bash
   git add src/handler.py
   git commit -m "feat: add retry logic to handler"
   ```

4. **Run pre-commit before pushing**
   ```bash
   pre-commit run --all-files
   ```

5. **Keep PRs small** (< 400 lines changed)

6. **Merge quickly** (< 2 days from branch creation)

### Release Best Practices

1. **Use semantic versioning** strictly
2. **Write clear release notes**
3. **Test thoroughly** before releasing
4. **Release often** (every 1-2 weeks)
5. **Avoid breaking changes** in minor/patch releases
6. **Document breaking changes** clearly

### CI/CD Best Practices

1. **Keep main always green** (all tests passing)
2. **Fix broken builds immediately**
3. **Don't skip CI checks** (except emergencies)
4. **Monitor deployment health**
5. **Have rollback plan ready**

---

**Last Updated**: 2025-11-01
**CI/CD Version**: Phase 7
**GitHub Actions Version**: Latest
