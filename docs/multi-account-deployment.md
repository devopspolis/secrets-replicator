# Multi-Account Deployment Strategy

## Overview

This document describes how to deploy secrets-replicator across multiple AWS accounts (Dev, QA, Prod) using GitHub Actions with OIDC authentication.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  GitHub Actions (CI/CD)                                  │
│  - Workflows run in GitHub's infrastructure              │
│  - Uses OIDC to assume roles in different accounts       │
│  - No long-lived AWS credentials                         │
└──────────────┬───────────────────────────────────────────┘
               │
               │ OIDC Assume Role
               │
    ┌──────────┼──────────┬──────────────┐
    ▼          ▼          ▼              ▼
┌─────────┐ ┌──────┐ ┌──────┐      ┌──────────┐
│Build Acct│ │ Dev  │ │  QA  │      │   Prod   │
│         │ │ Acct │ │ Acct │      │   Acct   │
│ S3:     │ │      │ │      │      │          │
│ builds/ │ │Stack │ │Stack │      │  Stack   │
│         │ │      │ │      │      │          │
└─────────┘ └──────┘ └──────┘      └────┬─────┘
                                         │
                                         ▼
                                    ┌─────────┐
                                    │   SAR   │
                                    │ (Public)│
                                    └─────────┘
```

## Account Strategy

### Option 1: Dedicated Build Account (Recommended)

**Accounts:**
- **Build Account:** Stores build artifacts, runs CI/CD
- **Dev Account:** Development environment
- **QA Account:** Testing environment
- **Prod Account:** Production environment + SAR publishing

**Benefits:**
- ✅ Single source of truth for builds
- ✅ Clear separation of concerns
- ✅ Easier cross-account access management
- ✅ Centralized build artifact storage

### Option 2: Use Prod Account for Builds

**Accounts:**
- **Prod Account:** Builds, production stack, SAR publishing
- **QA Account:** Testing environment
- **Dev Account:** Development environment

**Benefits:**
- ✅ Fewer accounts to manage
- ✅ Simpler IAM setup
- ⚠️ Build artifacts in production account

## GitHub Actions Configuration

### GitHub Environments

Set up three environments in GitHub: `Settings → Environments`

#### Development Environment
```yaml
Name: development
Protection rules: None
Environment secrets: None
Environment variables:
  AWS_ACCOUNT_ID: 111111111111  # Dev account
  AWS_REGION: us-west-2
```

#### QA Environment
```yaml
Name: qa
Protection rules:
  - Required reviewers: None (or specific team members)
  - Wait timer: 0 minutes
Environment variables:
  AWS_ACCOUNT_ID: 222222222222  # QA account
  AWS_REGION: us-west-2
```

#### Production Environment
```yaml
Name: production
Protection rules:
  - Required reviewers: @devops-team, @security-team
  - Wait timer: 5 minutes
  - Prevent administrators from bypassing: ✓
Environment variables:
  AWS_ACCOUNT_ID: 333333333333  # Prod account
  AWS_REGION: us-east-1
```

### Workflow Configuration

Each workflow uses the appropriate environment:

```yaml
# .github/workflows/deploy-dev.yml
jobs:
  deploy-dev:
    environment: development
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/github-actions-role
          aws-region: ${{ vars.AWS_REGION }}

# .github/workflows/release-qa.yml
jobs:
  build-and-deploy-qa:
    environment: qa
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/github-actions-role
          aws-region: ${{ vars.AWS_REGION }}

# .github/workflows/release-prod.yml
jobs:
  deploy-prod:
    environment: production
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/github-actions-role
          aws-region: ${{ vars.AWS_REGION }}
```

## IAM Setup

### 1. OIDC Provider (In Each Account)

Create OIDC provider in Dev, QA, and Prod accounts:

```bash
# Run in each account
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. IAM Role for GitHub Actions (In Each Account)

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

**Permissions Policy (Dev/QA Accounts):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormationDeployment",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateStack",
        "cloudformation:UpdateStack",
        "cloudformation:DescribeStacks",
        "cloudformation:DescribeStackEvents"
      ],
      "Resource": "arn:aws:cloudformation:*:*:stack/secrets-replicator-*/*"
    },
    {
      "Sid": "LambdaDeployment",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:GetFunction"
      ],
      "Resource": "arn:aws:lambda:*:*:function:secrets-replicator-*"
    },
    {
      "Sid": "IAMPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/secrets-replicator-*"
    },
    {
      "Sid": "S3BuildAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::secrets-replicator-builds-*/*"
    }
  ]
}
```

**Additional Permissions for Prod Account:**
```json
{
  "Sid": "SARPublishing",
  "Effect": "Allow",
  "Action": [
    "serverlessrepo:CreateApplication",
    "serverlessrepo:UpdateApplication",
    "serverlessrepo:CreateApplicationVersion",
    "serverlessrepo:PutApplicationPolicy",
    "serverlessrepo:GetApplication"
  ],
  "Resource": "arn:aws:serverlessrepo:*:*:applications/secrets-replicator"
}
```

## S3 Build Artifacts Bucket

### Option 1: Bucket in Build Account

**Create bucket in build account:**
```bash
# In build account
aws s3 mb s3://secrets-replicator-builds-us-west-2 --region us-west-2

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket secrets-replicator-builds-us-west-2 \
  --versioning-configuration Status=Enabled
```

**Bucket policy to allow cross-account access:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCrossAccountRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::111111111111:role/github-actions-role",
          "arn:aws:iam::222222222222:role/github-actions-role",
          "arn:aws:iam::333333333333:role/github-actions-role"
        ]
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::secrets-replicator-builds-us-west-2",
        "arn:aws:s3:::secrets-replicator-builds-us-west-2/*"
      ]
    }
  ]
}
```

### Option 2: Bucket Per Account

Each account has its own builds bucket (simpler permissions, more buckets):

```
Dev Account:   secrets-replicator-builds-us-west-2-111111111111
QA Account:    secrets-replicator-builds-us-west-2-222222222222
Prod Account:  secrets-replicator-builds-us-west-2-333333333333
```

## Deployment Flow

### 1. Development (Continuous)

```bash
# Triggered by push to main
git push origin main
```

**Flow:**
1. GitHub Actions assumes role in Dev account
2. Builds Lambda code
3. Deploys directly to Dev stack
4. No artifact storage (ephemeral builds)

### 2. QA Release (Build Once)

```bash
# Create GitHub Release
gh release create v1.0.0 --title "Release v1.0.0" --notes "..."
```

**Flow:**
1. GitHub Actions assumes role in Build account
2. Builds Lambda code once
3. Uploads to S3: `s3://secrets-replicator-builds-REGION/releases/1.0.0/`
4. Assumes role in QA account
5. Deploys to QA stack (references S3 artifacts from build account)

### 3. Production Release (Same Package)

```bash
# Promote to Prod
gh workflow run release-prod.yml \
  --field version=1.0.0 \
  --field publish_to_sar=true
```

**Flow:**
1. GitHub Actions assumes role in Build account
2. Downloads packaged template from S3 (same as QA)
3. Assumes role in Prod account
4. Deploys to Prod stack
5. (Optional) Publishes to SAR
6. (Optional) Makes SAR application public

## SAR Publishing

### Single SAR Publisher (Prod Account)

**Only Prod account publishes to SAR:**
- Application ARN: `arn:aws:serverlessrepo:us-east-1:333333333333:applications/secrets-replicator`
- Visibility: Public (anyone can deploy)
- Source: Exact package tested in QA

**QA and Dev do NOT publish to SAR**

### Why QA Shouldn't Publish to SAR

1. **SAR is for distribution:** Meant for external consumers, not testing
2. **Immutable versions:** Can't change after publishing, QA may need retries
3. **Version pollution:** Creates test versions that clutter SAR
4. **No added value:** QA can test via `sam deploy` without SAR

## Testing the Setup

### 1. Test Dev Deployment

```bash
# Push a change to main
git commit -am "Test dev deployment"
git push origin main

# Verify deployment
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-dev \
  --region us-west-2 \
  --profile dev-account
```

### 2. Test QA Build and Deploy

```bash
# Create test release
gh release create v0.1.4-test --title "Test QA" --notes "Testing QA workflow"

# Monitor workflow
gh run watch

# Verify build artifacts stored
aws s3 ls s3://secrets-replicator-builds-us-west-2/releases/0.1.4-test/ \
  --profile build-account

# Verify QA stack deployed
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-qa \
  --region us-west-2 \
  --profile qa-account
```

### 3. Test Prod Deployment

```bash
# Promote to prod (without SAR)
gh workflow run release-prod.yml \
  --field version=0.1.4-test \
  --field publish_to_sar=false

# Verify prod stack deployed
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-prod \
  --region us-east-1 \
  --profile prod-account
```

### 4. Test SAR Publishing

```bash
# Publish to SAR
gh workflow run release-prod.yml \
  --field version=0.1.4-test \
  --field publish_to_sar=true \
  --field sar_regions=us-east-1

# Verify SAR application
aws serverlessrepo get-application \
  --application-id arn:aws:serverlessrepo:us-east-1:333333333333:applications/secrets-replicator \
  --region us-east-1 \
  --profile prod-account
```

## Troubleshooting

### Error: Access Denied when downloading from S3

**Cause:** Cross-account S3 permissions not configured

**Solution:**
1. Check bucket policy allows target account
2. Check IAM role in target account has S3 read permissions
3. Verify S3 bucket encryption settings

### Error: AssumeRole failed

**Cause:** OIDC trust policy misconfigured

**Solution:**
```bash
# Verify OIDC provider exists
aws iam list-open-id-connect-providers

# Check trust policy
aws iam get-role --role-name github-actions-role \
  --query 'Role.AssumeRolePolicyDocument'
```

### Error: Stack deployment fails in target account

**Cause:** IAM permissions insufficient

**Solution:** Review CloudFormation execution role permissions

## Security Best Practices

1. **Use GitHub Environment Protection Rules:**
   - Require approval for production deployments
   - Limit who can approve prod releases
   - Add wait timer for prod deployments

2. **Principle of Least Privilege:**
   - Dev role: Only CloudFormation/Lambda/S3 read
   - QA role: Same as Dev + S3 write for builds
   - Prod role: Dev permissions + SAR publishing

3. **Audit Trail:**
   - All deployments logged in CloudTrail
   - GitHub Actions logs retained
   - S3 bucket versioning enabled

4. **Secrets Management:**
   - No long-lived credentials in GitHub
   - Use OIDC for temporary credentials
   - Rotate OIDC thumbprints annually

## References

- [GitHub Actions OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS SAM Cross-Account Deployments](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference.html)
- [SAR Publishing Guide](https://docs.aws.amazon.com/serverlessrepo/latest/devguide/serverlessrepo-how-to-publish.html)
