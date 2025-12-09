# GitHub Actions Workflows Guide

This document describes the CI/CD workflows for the Secrets Replicator project, including how to deploy to different environments.

## Overview

The project uses a multi-account AWS deployment strategy with three separate environments:

- **Development**: For active development and feature testing
- **QA**: For pre-production validation and testing
- **Production**: For stable releases and SAR publishing

Each environment has its own AWS account and GitHub environment configuration with OIDC authentication.

## GitHub Environment Configuration

### Deployment Environments

Each GitHub environment should have the following variables configured:

| Environment    | GitHub Environment Name | Variables                                    | Required Reviewers |
|----------------|------------------------|----------------------------------------------|--------------------|
| Development    | `development`          | `AWS_ACCOUNT_ID`, `AWS_REGION`              | 0 (auto-deploy)    |
| QA             | `qa`                   | `AWS_ACCOUNT_ID`, `AWS_REGION`              | 0 (after approval) |
| Production     | `production`           | `AWS_ACCOUNT_ID`, `AWS_REGION`, `QA_ACCOUNT_ID`, `QA_REGION` | 0 (after approval) |

### Approval Environments

These environments control approval gates and should have required reviewers configured:

| Environment          | Purpose                       | Required Reviewers | Variables |
|---------------------|-------------------------------|-------------------|-----------|
| `qa-approval`       | Approve QA deployments        | 1+ recommended    | None      |
| `production-approval` | Approve production deployments | 2+ recommended   | None      |

**How to Configure Reviewers**:
1. Go to: Repository Settings → Environments → {environment-name}
2. Enable "Required reviewers"
3. Add GitHub usernames who can approve deployments
4. Optionally enable "Prevent administrators from bypassing" for strict control

### Required IAM Roles

Each AWS account needs specific IAM roles configured for OIDC authentication:

**All Accounts**:
- `github-actions-role`: Main deployment role with trust to GitHub OIDC provider
  - Provider: `token.actions.githubusercontent.com`
  - Repository: `devopspolis/secrets-replicator`

**QA Account Only**:
- `github-actions-cross-account-read`: Cross-account read role for production
  - Trust: Production AWS account
  - Permissions: S3 GetObject (read-only)
  - ExternalId: `secrets-replicator-prod-read-qa`

See [IAM_SETUP.md](./IAM_SETUP.md) for complete IAM configuration details.

## Workflows

### 1. Development Workflow (deploy-dev.yml)

**Purpose**: Continuous deployment to the development environment for testing new features and bug fixes.

**Triggers**:
- Automatic deployment on every push to `main` branch
- Manual deployment via workflow_dispatch (can specify any git ref)

**Stack Name**: `secrets-replicator-dev`

**Usage**:

#### Automatic Deployment (Push to Main)
```bash
git push origin main
```
The workflow automatically deploys to the development environment.

#### Manual Deployment (Feature Branch Testing)
1. Go to: Actions → Deploy to Dev → Run workflow
2. Select the branch or enter:
   - Branch name: `feature/my-feature`
   - Tag: `v1.0.0`
   - Commit SHA: `abc123def456`
3. Click "Run workflow"

**What it does**:
1. Checks out the specified git ref
2. Builds the SAM application
3. Deploys to development AWS account
4. Tags with GitSha and BuildNumber

**Use cases**:
- Test feature branches before merging
- Validate bug fixes in isolation
- Rapid iteration during development

---

### 2. QA Workflow (release-qa.yml)

**Purpose**: Deploy versioned releases to QA for pre-production validation. Builds once, requires approval, then deploys and packages artifacts for promotion to production.

**Triggers**:
- Automatic start when a GitHub Release is published
- Manual start via workflow_dispatch (with optional tag creation)

**Stack Name**: `secrets-replicator-qa`

**Jobs**:
1. **build-and-package**: Builds and packages the application
2. **approve-qa-deployment**: **Waits for manual approval** (environment: `qa-approval`)
3. **deploy-to-qa**: Deploys to QA account after approval

**Usage**:

#### Via GitHub Release (Recommended)
1. Create a new release in GitHub:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
2. Go to: Releases → Draft a new release
3. Select tag: `v1.0.0`
4. Click "Publish release"
5. Workflow starts, build completes
6. **Approve deployment**: Go to Actions → Approve the "Approve QA Deployment" job
7. After approval, deployment proceeds automatically

#### Via Workflow Dispatch
1. Go to: Actions → Release to QA → Run workflow
2. Enter version: `1.0.0` or `v1.0.0`
3. Choose whether to create git tag (default: true)
4. Click "Run workflow"
5. **Approve deployment** when build completes (see step 6 above)

**What it does**:

**Job 1: Build and Package**
1. Creates git tag if it doesn't exist (workflow_dispatch only)
2. Builds the SAM application
3. Packages and uploads to S3 in QA account (version-specific prefix)
4. Stores packaged template as GitHub artifact (backup, 90-day retention)
5. Waits for approval

**Job 2: Approve QA Deployment** 🔒
- Requires manual approval from configured reviewers
- Checkpoint before deploying to QA environment

**Job 3: Deploy to QA**
1. Downloads package from QA S3
2. Deploys to QA AWS account
3. Tags with Environment=qa and Version

**Artifacts created**:
- S3 Package: `s3://secrets-replicator-builds-{region}/releases/{version}/` (primary)
- GitHub Artifact: `packaged-template-{version}` (backup, 90-day retention)

**Use cases**:
- Pre-production validation
- Integration testing
- User acceptance testing
- QA environment for customer demos

**Security Note**: Package is stored in QA account's S3. Production will read it via cross-account role (QA cannot write to production).

---

### 3. Production Workflow (release-prod.yml)

**Purpose**: Promote QA-tested releases to production and optionally publish to AWS Serverless Application Repository (SAR). Uses cross-account read-only access to retrieve packages from QA.

**Triggers**:
- Manual deployment via workflow_dispatch only (for safety)

**Stack Name**: `secrets-replicator-prod`

**Jobs**:
1. **approve-prod-deployment**: **Waits for manual approval** (environment: `production-approval`)
2. **retrieve-qa-package**: Retrieves package from QA via cross-account role
3. **deploy-prod**: Deploys to production account
4. **publish-to-sar**: Optionally publishes to SAR (if enabled)

**Usage**:

1. Go to: Actions → Release to Prod → Run workflow
2. Configure inputs:
   - **Version**: `1.0.0` (must match QA version)
   - **Publish to SAR**: `true` (default) or `false`
   - **SAR Regions**: `us-east-1,us-west-2` (default) or custom list
3. Click "Run workflow"
4. **Approve deployment**: Go to Actions → Approve the "Approve Production Deployment" job
5. After approval, package retrieval and deployment proceed automatically

**What it does**:

**Job 1: Approve Production Deployment** 🔒
- Requires manual approval from configured reviewers (2+ recommended)
- Critical checkpoint before production changes

**Job 2: Retrieve QA Package** 🔐
1. Assumes cross-account read role in QA account
2. Downloads packaged template from QA's S3 bucket
3. Uploads to workflow artifact for deployment job
4. **Security**: Uses read-only role with ExternalId (cannot write to QA)

**Job 3: Deploy to Production**
1. Downloads package from previous job (originally from QA)
2. Switches to production credentials
3. Deploys to production AWS account (no rebuild)
4. Tags with Environment=prod and Version

**Job 4: Publish to SAR** (if enabled)
1. Retrieves same package from previous job
2. Creates SAR S3 buckets in specified regions
3. Uploads README.md and LICENSE to SAR buckets
4. Publishes application to SAR in each region
5. Makes application publicly available

**Important Notes**:
- This workflow uses the EXACT same package that was deployed to QA (no rebuild)
- The QA workflow must have completed successfully for the specified version
- Package is retrieved from QA's S3 via **cross-account read-only role**
- **Environment Isolation**: Production can read from QA but cannot write to QA
- Production and SAR publishing happen sequentially (production first)

**Use cases**:
- Promoting validated releases from QA to production
- Publishing new versions to AWS Serverless Application Repository
- Making application available to public consumers

**Security Note**: Production uses `sts:AssumeRole` to temporarily access QA's S3 bucket with read-only permissions. This maintains environment isolation while enabling artifact promotion.

---

## Deployment Pipeline Flow

```
┌─────────────────────┐
│   Feature Branch    │
│   Development       │
└──────────┬──────────┘
           │
           │ Push to main
           ▼
┌─────────────────────┐
│   Development Env   │
│   (Auto Deploy)     │
└─────────────────────┘
           │
           │ Create release tag
           ▼
┌─────────────────────────────────────────────────────────────┐
│                        QA Workflow                          │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Build &   │ →  │   Approval   │ →  │   Deploy to  │  │
│  │   Package   │    │   Required   │    │   QA Account │  │
│  └─────────────┘    └──────────────┘    └──────────────┘  │
│         │                                                   │
│         │ Stores in QA S3                                  │
│         ▼                                                   │
│  ┌────────────────────────────────────┐                    │
│  │  s3://secrets-replicator-builds/  │                    │
│  │  releases/{version}/               │                    │
│  └────────────────────────────────────┘                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Manual promotion
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Production Workflow                      │
│                                                             │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────┐ │
│  │   Approval   │ →  │  Retrieve from   │ →  │  Deploy  │ │
│  │   Required   │    │  QA S3 (Cross-   │    │  to Prod │ │
│  │              │    │  Account Read)   │    │          │ │
│  └──────────────┘    └──────────────────┘    └──────────┘ │
│                                                      │      │
│                                                      │      │
│                              If publish_to_sar=true  │      │
│                                                      ▼      │
│                                              ┌──────────┐   │
│                                              │  Publish │   │
│                                              │  to SAR  │   │
│                                              └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Build-Once, Deploy-Many Strategy

The workflows implement a "build-once, deploy-many" approach with proper environment isolation:

1. **QA Workflow**: Builds and packages the application once, stores in QA S3
2. **Approval Gates**: Both QA and Production deployments require manual approval
3. **Cross-Account Read**: Production retrieves package from QA via cross-account read-only role
4. **Production**: Reuses the exact QA build (no rebuild)
5. **SAR**: Publishes the same tested artifact

**Benefits**:
- Guarantees production runs the same code that was tested in QA
- Reduces build time and CI/CD costs
- Eliminates "works in QA, breaks in prod" scenarios
- Provides audit trail of what was deployed
- **Environment Isolation**: QA cannot write to production (read-only cross-account access)
- **Approval Gates**: Human verification before deployments

## Security Model

### Environment Isolation

```
┌─────────────────────────────────────────┐
│           QA Account                    │
│                                         │
│  S3: secrets-replicator-builds/        │
│      releases/{version}/                │
│                                         │
│  IAM Role: cross-account-read           │
│  - Trust: Production Account            │
│  - Permissions: S3 GetObject (READ)     │
│  - NO write permissions to Production   │
└────────────┬────────────────────────────┘
             │
             │ AssumeRole (Read-Only)
             │ with ExternalId
             ▼
┌─────────────────────────────────────────┐
│        Production Account               │
│                                         │
│  IAM Role: github-actions-role          │
│  - Permissions: sts:AssumeRole to QA    │
│  - Full deployment permissions in Prod  │
│  - NO permissions in QA account         │
└─────────────────────────────────────────┘
```

### Key Security Features

1. **Read-Only Cross-Account Access**: Production can only READ from QA, never write
2. **ExternalId**: Prevents confused deputy attacks in cross-account access
3. **Least Privilege**: Each role has minimum required permissions
4. **Approval Gates**: Manual approval required for both QA and Production deployments
5. **Audit Trail**: CloudTrail logs all cross-account role assumptions
6. **Temporary Credentials**: OIDC provides short-lived tokens (no long-lived keys)

## Authentication

All workflows use AWS OIDC authentication:

```yaml
- name: Configure AWS credentials (OIDC)
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/github-actions-role
    aws-region: ${{ vars.AWS_REGION }}
    role-session-name: GitHubActions-{Environment}-${{ github.run_id }}
```

**Security benefits**:
- No long-lived AWS credentials stored in GitHub
- Short-lived session tokens (12 hours max)
- Role session names include run ID for audit trail
- Cross-account isolation

## Required IAM Permissions

The `github-actions-role` in each account needs these permissions:

### Development & QA Accounts
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "iam:GetRole",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PassRole",
        "s3:*",
        "secretsmanager:*",
        "kms:*",
        "events:*",
        "sqs:*",
        "sns:*",
        "logs:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### Production Account (Additional SAR Permissions)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "serverlessrepo:CreateApplication",
        "serverlessrepo:UpdateApplication",
        "serverlessrepo:CreateApplicationVersion",
        "serverlessrepo:PutApplicationPolicy"
      ],
      "Resource": "*"
    }
  ]
}
```

## Troubleshooting

### Issue: QA artifact not found in Production workflow

**Error**: `Packaged template artifact not found`

**Solution**:
1. Verify QA workflow completed successfully:
   ```bash
   gh run list --workflow=release-qa.yml
   ```
2. Check artifact exists:
   ```bash
   gh run view <run-id> --log
   ```
3. Ensure artifact name matches: `packaged-template-{version}`
4. Artifacts expire after 90 days - rebuild if expired

### Issue: OIDC authentication fails

**Error**: `Not authorized to perform sts:AssumeRoleWithWebIdentity`

**Solution**:
1. Verify GitHub environment variables are set:
   - `AWS_ACCOUNT_ID`
   - `AWS_REGION`
2. Check IAM role trust policy in AWS account
3. Verify repository name matches trust policy
4. Ensure OIDC provider is configured in AWS account

### Issue: SAR publish fails

**Error**: `Application already exists`

**Solution**:
- This is expected for version updates
- SAM automatically creates new application version
- Check SAR console to verify update

### Issue: Tag already exists when running QA workflow

**Error**: `tag 'v1.0.0' already exists`

**Solution**:
- Set `create_tag` to `false` in workflow_dispatch
- Or delete existing tag:
  ```bash
  git tag -d v1.0.0
  git push origin :refs/tags/v1.0.0
  ```

## Best Practices

1. **Version Numbering**: Use semantic versioning (e.g., `v1.0.0`)
2. **Git Tags**: Always prefix with `v` (e.g., `v1.0.0` not `1.0.0`)
3. **Testing**: Test in Dev → Deploy to QA → Validate → Promote to Prod
4. **Rollbacks**: Redeploy previous version from QA artifacts
5. **Monitoring**: Check CloudFormation stack outputs after deployment
6. **SAR Publishing**: Only publish stable, tested versions to SAR

## Example Scenarios

### Scenario 1: Regular Feature Development

```bash
# 1. Develop feature locally
git checkout -b feature/new-transformation

# 2. Test in development account
git commit -am "Add new transformation logic"
# Manual: Actions → Deploy to Dev → Run workflow → Branch: feature/new-transformation

# 3. Merge to main after testing
git checkout main
git merge feature/new-transformation
git push origin main
# Auto-deploys to development

# 4. Create release for QA
git tag v1.1.0
git push origin v1.1.0
gh release create v1.1.0 --generate-notes
# Auto-deploys to QA

# 5. Validate in QA, then promote to production
# Manual: Actions → Release to Prod → Version: 1.1.0
```

### Scenario 2: Hotfix to Production

```bash
# 1. Create hotfix branch
git checkout -b hotfix/critical-bug

# 2. Test fix in development
git commit -am "Fix critical bug"
# Manual: Actions → Deploy to Dev → Branch: hotfix/critical-bug

# 3. Merge and create patch release
git checkout main
git merge hotfix/critical-bug
git tag v1.0.1
git push origin v1.0.1 main
gh release create v1.0.1 --generate-notes
# Auto-deploys to QA

# 4. Fast-track to production (after quick QA validation)
# Manual: Actions → Release to Prod → Version: 1.0.1 → Publish to SAR: false
```

### Scenario 3: SAR-Only Update (Documentation Fix)

```bash
# 1. Update README.md (no code changes)
git commit -am "Update documentation"
git push origin main

# 2. Create new version for SAR
git tag v1.0.2
git push origin v1.0.2
gh release create v1.0.2 --notes "Documentation updates"

# 3. Deploy to QA (required for artifact creation)
# Auto-triggered by release

# 4. Update SAR with new README (skip prod deployment if no code changes)
# Manual: Actions → Release to Prod → Version: 1.0.2
```

## Workflow Files Location

- Development: `.github/workflows/deploy-dev.yml`
- QA: `.github/workflows/release-qa.yml`
- Production: `.github/workflows/release-prod.yml`

## Additional Resources

- [AWS SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [GitHub Actions OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS Serverless Application Repository](https://aws.amazon.com/serverless/serverlessrepo/)
- [Semantic Versioning](https://semver.org/)
