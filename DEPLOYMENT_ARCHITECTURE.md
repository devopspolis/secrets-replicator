# Deployment Architecture - Secrets Replicator

## Overview

This document describes the simplified multi-account deployment architecture using **environment switching** instead of cross-account IAM roles. This approach maintains environment isolation while leveraging GitHub's environment feature for authentication.

## Key Principles

1. **Environment Isolation**: QA cannot write to Production (separate AWS accounts)
2. **Environment Switching**: Use GitHub environments to authenticate to different AWS accounts
3. **Single Approval Environment**: One `approval` environment for both QA and Production workflows
4. **Approval After Retrieval**: Verify package exists before requesting approval
5. **Build Once, Deploy Many**: Same package from QA is deployed to Production and SAR

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      QA Workflow                                │
│                                                                 │
│  ┌─────────┐    ┌─────────────┐    ┌──────────┐    ┌────────┐ │
│  │ Setup   │ →  │ Build &     │ →  │ Approval │ →  │ Deploy │ │
│  │         │    │ Package     │    │          │    │ to QA  │ │
│  └─────────┘    │ (env: qa)   │    │(env:     │    │(env:qa)│ │
│                 │             │    │ approval)│    │        │ │
│                 │ ↓ Upload to │    │          │    │        │ │
│                 │   QA S3     │    │          │    │        │ │
│                 └─────────────┘    └──────────┘    └────────┘ │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ S3: secrets-replicator-builds/
                           │     releases/{version}/
                           │
┌─────────────────────────▼─────────────────────────────────────────┐
│                   Production Workflow                             │
│                                                                   │
│  ┌───────┐  ┌──────────────┐  ┌──────────┐  ┌────────┐  ┌─────┐│
│  │ Setup │→ │ Promote from │→ │ Approval │→ │ Deploy │→ │ SAR ││
│  │       │  │ QA           │  │          │  │ to Prod│  │     ││
│  └───────┘  │ (env: qa)    │  │(env:     │  │(env:   │  │     ││
│              │              │  │ approval)│  │ prod)  │  │     ││
│              │ ↓ Download   │  │          │  │        │  │     ││
│              │   from QA S3 │  │          │  │        │  │     ││
│              │ ↓ Upload to  │  │          │  │        │  │     ││
│              │   GitHub     │  │          │  │        │  │     ││
│              │   Artifact   │  │          │  │        │  │     ││
│              └──────────────┘  └──────────┘  └────────┘  └─────┘│
└───────────────────────────────────────────────────────────────────┘
```

## Environment Switching Pattern

### How It Works

Instead of using cross-account IAM roles, we use GitHub's environment feature to switch between AWS accounts:

1. **QA Workflow** - Build job uses `environment: qa`
   - Authenticates to QA AWS account via OIDC
   - Builds and packages application
   - Uploads to QA S3 bucket

2. **Production Workflow** - Promote job uses `environment: qa`
   - Authenticates to QA AWS account via OIDC
   - Downloads package from QA S3
   - Uploads to GitHub artifact
   - Then switches to production credentials for deployment

### Benefits

✅ **No Cross-Account IAM Roles**: Eliminates complex IAM trust policies and AssumeRole
✅ **Simpler Architecture**: Use GitHub environments instead of AWS cross-account access
✅ **Environment Isolation**: QA cannot access Production (separate GitHub environments)
✅ **Standard Pattern**: Follows DevOpsPolis reusable workflow patterns
✅ **Easier Debugging**: Each environment has clear AWS credentials

## Workflows

### QA Workflow (release-qa.yml)

**Jobs**:
1. **setup** - Extract version, set S3 configuration
2. **build-and-package** (`environment: qa`) - Build, package, upload to QA S3
3. **approval** (`uses: devopspolis/github-actions/.github/workflows/approval.yml@main`)
4. **deploy-to-qa** (`environment: qa`) - Deploy to QA CloudFormation stack

**Triggers**:
- GitHub Release published
- Manual `workflow_dispatch` with version input

**Approval Gate**: Between package and deployment

### Production Workflow (release-prod.yml)

**Jobs**:
1. **setup** - Extract version, set S3 configuration
2. **promote-from-qa** (`uses: devopspolis/github-actions/.github/workflows/promote-s3-artifact.yml@main`)
   - Uses `environment: qa` to download from QA S3
   - Uploads to GitHub artifact
3. **approval** (`uses: devopspolis/github-actions/.github/workflows/approval.yml@main`)
4. **deploy-to-prod** (`environment: production`) - Deploy to Prod CloudFormation stack
5. **publish-to-sar** (`environment: production`, optional) - Publish to SAR

**Triggers**:
- Manual `workflow_dispatch` with version input

**Approval Gate**: After package retrieval, before deployment

## GitHub Environment Configuration

### Required Environments

| Environment | Purpose | Variables | Reviewers |
|------------|---------|-----------|-----------|
| `qa` | QA deployment and package storage | `AWS_ACCOUNT_ID`, `AWS_REGION` | 0 |
| `production` | Production deployment and SAR | `AWS_ACCOUNT_ID`, `AWS_REGION` | 0 |
| `approval` | Manual approval gate (shared) | None | 1+ (you) |

### How to Configure

1. Go to: Repository Settings → Environments
2. Create each environment above
3. Add variables:
   - `qa`: QA AWS account ID and region
   - `production`: Production AWS account ID and region
4. Configure `approval` environment:
   - Enable "Required reviewers"
   - Add your GitHub username
   - Optionally: "Wait timer" for additional safety

## AWS IAM Configuration

### Required IAM Roles

Each AWS account needs **one IAM role**:

**Role Name**: `github-actions-role`

**Trust Policy** (same for all accounts):
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:devopspolis/secrets-replicator:*"
      }
    }
  }]
}
```

**Permissions Policy** (same for all accounts):
- CloudFormation full access
- Lambda full access
- IAM role management (scoped to `secrets-replicator-*`)
- S3 access (for build buckets and SAR buckets)
- Secrets Manager full access
- KMS key management
- EventBridge, SQS, SNS, CloudWatch

**Production Account Additional Permissions**:
- `serverlessrepo:*` - For SAR publishing

### OIDC Provider Setup

Each account needs the GitHub OIDC provider:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

## S3 Bucket Strategy

### QA Account

**Bucket**: `secrets-replicator-builds`
**Purpose**: Store versioned build artifacts
**Structure**:
```
s3://secrets-replicator-builds/
└── releases/
    ├── 1.0.0/
    │   ├── packaged-qa.yaml
    │   └── <lambda-code>.zip
    ├── 1.0.1/
    └── 1.1.0/
```

**Configuration**:
- Versioning: Enabled
- Encryption: AES-256
- Lifecycle: Optional (delete builds older than 1 year)

**Access**:
- QA `github-actions-role`: Read/Write
- Production workflow (via QA environment): Read-only

### Production Account

**Buckets**: `secrets-replicator-sar-{region}`
**Purpose**: Store README and LICENSE for SAR publishing
**Regions**: One bucket per SAR region (e.g., us-east-1, us-west-2)

**Access**:
- SAR service: Read
- Public (HTTPS only): Read

## DevOpsPolis Reusable Workflows

### `promote-s3-artifact.yml`

**Purpose**: Download artifact from S3 in one environment, upload to GitHub artifact

**Usage**:
```yaml
promote-from-qa:
  uses: devopspolis/github-actions/.github/workflows/promote-s3-artifact.yml@main
  with:
    environment: qa  # Authenticates to QA account
    s3_uri: s3://secrets-replicator-builds/releases/1.0.0/packaged-qa.yaml
    artifact_name: packaged-template-1.0.0
    artifact_file: packaged-qa.yaml
  secrets: inherit
```

**What it does**:
1. Uses `environment: qa` to authenticate to QA AWS account
2. Downloads file from QA S3
3. Uploads to GitHub artifact
4. Returns `outputs.artifact_name` for next job

### `approval.yml`

**Purpose**: Manual approval gate

**Usage**:
```yaml
approval:
  needs: [promote-from-qa]
  uses: devopspolis/github-actions/.github/workflows/approval.yml@main
```

**What it does**:
1. Waits for manual approval from configured reviewers
2. Blocks workflow until approved or rejected
3. Uses GitHub environment protection rules

## Security Model

### Environment Isolation

✅ **QA Cannot Write to Production**
- QA workflow never authenticates to production account
- GitHub environment variables prevent accidental cross-account access

✅ **Production Can Only Read from QA**
- Production workflow uses `environment: qa` only in promote job
- After promotion, switches to `environment: production`
- No persistent credentials cross environments

✅ **Approval Gates**
- Manual approval required for both QA and Production deployments
- Approval happens AFTER package verification (not before)
- Single reviewer can approve (you are the only approver)

✅ **Audit Trail**
- GitHub Actions logs all environment switches
- AWS CloudTrail logs all API calls
- Role session names include run ID for correlation

### No Cross-Account IAM Roles

**Old Pattern** (complex):
```
Production → AssumeRole → QA Cross-Account Read Role → S3
```

**New Pattern** (simple):
```
Production Job (environment: qa) → QA S3 → GitHub Artifact
Production Job (environment: production) → Deploy
```

## Deployment Flow

### QA Release

```
1. Create git tag (v1.0.0)
2. Publish GitHub Release
   ↓
3. QA workflow starts
   ↓
4. Setup job (extract version)
   ↓
5. Build job (environment: qa)
   - Authenticate to QA account
   - sam build
   - sam package → QA S3
   ↓
6. Approval job
   - Wait for manual approval
   ↓
7. Deploy job (environment: qa)
   - Download from QA S3
   - sam deploy → secrets-replicator-qa
```

### Production Release

```
1. Manual workflow trigger (version: 1.0.0)
   ↓
2. Setup job (extract version)
   ↓
3. Promote job (environment: qa)
   - Authenticate to QA account
   - Download from QA S3
   - Upload to GitHub artifact
   ↓
4. Approval job
   - Wait for manual approval
   ↓
5. Deploy job (environment: production)
   - Authenticate to Production account
   - Download from GitHub artifact
   - sam deploy → secrets-replicator-prod
   ↓
6. SAR job (environment: production, optional)
   - sam publish (multi-region)
   - Make public
```

## Cost Optimization

### S3 Storage

**QA Account**:
- Builds bucket: ~$0.10/month (versioning, small artifacts)
- Lifecycle policy: Delete builds > 1 year old

**Production Account**:
- SAR buckets: ~$0.05/month per region (README + LICENSE only)

**Total S3**: ~$0.20-0.30/month

### Lambda Executions

- Dev: ~$0.10/month (testing)
- QA: ~$0.50/month (pre-prod testing)
- Prod: ~$2-5/month (actual usage)

### GitHub Actions Minutes

- QA workflow: ~5 minutes per release
- Production workflow: ~10 minutes per release (includes SAR)
- Free tier: 2,000 minutes/month (plenty for this project)

**Total Monthly Cost**: ~$3-6 (mostly Lambda usage, not infrastructure)

## Comparison to Previous Architecture

| Aspect | Old (Cross-Account IAM) | New (Environment Switching) |
|--------|------------------------|----------------------------|
| **IAM Roles** | 3 roles (QA deploy, QA read, Prod deploy) | 2 roles (QA deploy, Prod deploy) |
| **Trust Policies** | Complex (AssumeRole + ExternalId) | Simple (OIDC only) |
| **S3 Bucket Policies** | Cross-account access needed | Not needed |
| **Approval Environments** | 2 (qa-approval, prod-approval) | 1 (approval) |
| **Approval Timing** | Before retrieval | After retrieval ✅ |
| **Debugging** | Complex (multi-account AssumeRole) | Simple (environment switches) |
| **Audit Trail** | CloudTrail cross-account | CloudTrail + GitHub logs |
| **Security** | Good (read-only cross-account) | Better (no cross-account) ✅ |

## Testing the Setup

### 1. Test QA Workflow

```bash
# Create and push tag
git tag v0.1.0-test
git push origin v0.1.0-test

# Create GitHub Release
gh release create v0.1.0-test --generate-notes

# Watch workflow
gh run watch

# Approve deployment
# Go to: Actions → Release to QA → Review deployments → Approve

# Verify deployment
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-qa \
  --region us-east-1
```

### 2. Test Production Workflow

```bash
# Trigger production workflow
gh workflow run release-prod.yml \
  -f version=0.1.0-test \
  -f publish_to_sar=false

# Watch workflow
gh run watch

# Approve deployment
# Go to: Actions → Release to Prod → Review deployments → Approve

# Verify deployment
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-prod \
  --region us-east-1
```

### 3. Verify Environment Isolation

```bash
# QA workflow should NOT have production credentials
# Production promote job should use QA credentials
# Production deploy job should use production credentials

# Check GitHub Actions logs for:
# - "Configure AWS credentials" steps
# - "aws sts get-caller-identity" outputs
# - Verify account IDs match expected environments
```

## Troubleshooting

### Issue: OIDC authentication fails

**Solution**:
1. Verify OIDC provider exists in AWS account
2. Check trust policy repository name matches exactly
3. Verify GitHub environment variables are set

### Issue: Approval not showing

**Solution**:
1. Verify `approval` environment exists in GitHub
2. Add yourself as required reviewer
3. Check workflow uses correct reusable workflow path

### Issue: Package not found in QA S3

**Solution**:
1. Verify QA workflow completed successfully
2. Check S3 bucket and key path
3. Verify versioning matches (1.0.0 vs v1.0.0)

### Issue: Cannot assume role

**Solution**:
- This should not happen with environment switching!
- Verify you're not using the old workflow files
- Check that jobs use `environment:` not `role-to-assume:`

## Next Steps

1. **Create GitHub Environments**: `qa`, `production`, `approval`
2. **Configure Environment Variables**: AWS_ACCOUNT_ID, AWS_REGION
3. **Set Up OIDC**: Create providers and roles in each AWS account
4. **Test QA Workflow**: Create a test release
5. **Test Production Workflow**: Promote test release to production

## References

- [GitHub OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [GitHub Environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [DevOpsPolis GitHub Actions](https://github.com/devopspolis/github-actions)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
