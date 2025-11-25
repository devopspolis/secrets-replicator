# GitHub Actions SAR Testing Guide

## Overview

This guide walks you through testing Secrets Replicator deployment to AWS Serverless Application Repository (SAR) using GitHub Actions with OIDC authentication.

## Prerequisites

✅ You have configured:
- GitHub repository: `devopspolis/secrets-replicator`
- AWS Account ID: `965862100780`
- OIDC Provider: `token.actions.githubusercontent.com`
- IAM Role: `github-actions-role`
- Environment variables: `AWS_ACCOUNT_ID` and `AWS_REGION`

## Step 1: Verify IAM Role Permissions

Your `github-actions-role` needs the following permissions for SAR testing:

### Required IAM Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
        "secretsmanager:DeleteSecret",
        "secretsmanager:TagResource",
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutBucketVersioning",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::secrets-replicator-sar-test-*",
        "arn:aws:s3:::secrets-replicator-sar-test-*/*"
      ]
    },
    {
      "Sid": "ServerlessRepoAccess",
      "Effect": "Allow",
      "Action": [
        "serverlessrepo:CreateApplication",
        "serverlessrepo:CreateApplicationVersion",
        "serverlessrepo:UpdateApplication",
        "serverlessrepo:GetApplication",
        "serverlessrepo:ListApplications",
        "serverlessrepo:DeleteApplication"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudFormationAccess",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateStack",
        "cloudformation:UpdateStack",
        "cloudformation:DeleteStack",
        "cloudformation:DescribeStacks",
        "cloudformation:DescribeStackEvents",
        "cloudformation:GetTemplate",
        "cloudformation:ValidateTemplate"
      ],
      "Resource": "arn:aws:cloudformation:*:965862100780:stack/secrets-replicator-sar-test-*/*"
    },
    {
      "Sid": "LambdaAccess",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:DeleteFunction",
        "lambda:GetFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:AddPermission",
        "lambda:RemovePermission",
        "lambda:ListTags",
        "lambda:TagResource"
      ],
      "Resource": "arn:aws:lambda:*:965862100780:function:secrets-replicator-sar-test-*"
    },
    {
      "Sid": "IAMAccess",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PassRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy"
      ],
      "Resource": "arn:aws:iam::965862100780:role/secrets-replicator-sar-test-*"
    },
    {
      "Sid": "EventBridgeAccess",
      "Effect": "Allow",
      "Action": [
        "events:PutRule",
        "events:DeleteRule",
        "events:DescribeRule",
        "events:PutTargets",
        "events:RemoveTargets",
        "events:EnableRule",
        "events:DisableRule"
      ],
      "Resource": "arn:aws:events:*:965862100780:rule/secrets-replicator-sar-test-*"
    },
    {
      "Sid": "CloudWatchLogsAccess",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
        "logs:PutRetentionPolicy",
        "logs:DeleteRetentionPolicy",
        "logs:TagLogGroup"
      ],
      "Resource": "arn:aws:logs:*:965862100780:log-group:/aws/lambda/secrets-replicator-sar-test-*"
    },
    {
      "Sid": "SQSAccess",
      "Effect": "Allow",
      "Action": [
        "sqs:CreateQueue",
        "sqs:DeleteQueue",
        "sqs:GetQueueAttributes",
        "sqs:SetQueueAttributes",
        "sqs:TagQueue"
      ],
      "Resource": "arn:aws:sqs:*:965862100780:secrets-replicator-sar-test-*"
    },
    {
      "Sid": "SNSAccess",
      "Effect": "Allow",
      "Action": [
        "sns:CreateTopic",
        "sns:DeleteTopic",
        "sns:GetTopicAttributes",
        "sns:SetTopicAttributes",
        "sns:Subscribe",
        "sns:Unsubscribe",
        "sns:TagResource"
      ],
      "Resource": "arn:aws:sns:*:965862100780:secrets-replicator-sar-test-*"
    },
    {
      "Sid": "CloudWatchMetricsAccess",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms",
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "arn:aws:cloudwatch:*:965862100780:alarm:secrets-replicator-sar-test-*"
    },
    {
      "Sid": "STSAccess",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

### How to Add/Verify Permissions

```bash
# 1. Get current role policy (if using inline policy)
aws iam get-role-policy \
  --role-name github-actions-role \
  --policy-name GitHubActionsPolicy

# 2. Update role policy
aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name GitHubActionsPolicy \
  --policy-document file://github-actions-policy.json

# OR attach managed policy (if using managed policy)
aws iam attach-role-policy \
  --role-name github-actions-role \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
```

## Step 2: Verify GitHub Environment Configuration

### Check Environment Variables

1. Go to your GitHub repository: https://github.com/devopspolis/secrets-replicator
2. Navigate to: **Settings** → **Environments** → **production**
3. Verify these variables exist:
   - `AWS_ACCOUNT_ID`: `965862100780`
   - `AWS_REGION`: `us-west-2` (or your preferred region)

### If Variables Don't Exist

1. Click "Add variable"
2. Name: `AWS_ACCOUNT_ID`, Value: `965862100780`
3. Name: `AWS_REGION`, Value: `us-west-2`
4. Click "Add variable" for each

## Step 3: Commit and Push Workflow

```bash
# Add the workflow file
git add .github/workflows/test-sar.yml

# Commit
git commit -m "Add SAR testing workflow with OIDC authentication"

# Push to GitHub
git push origin main
```

## Step 4: Run the Workflow

### Via GitHub UI (Recommended)

1. Go to your repository: https://github.com/devopspolis/secrets-replicator
2. Click the **Actions** tab
3. Click **Test SAR Deployment** (left sidebar)
4. Click **Run workflow** (right side)
5. Choose:
   - **Branch**: `main`
   - **cleanup**: ✅ `true` (automatically delete resources after test)
6. Click **Run workflow**

### Via GitHub CLI

```bash
# Install GitHub CLI if needed
brew install gh

# Authenticate
gh auth login

# Run workflow
gh workflow run test-sar.yml \
  --ref main \
  --field cleanup=true
```

## Step 5: Monitor the Workflow

### Watch Progress

1. Click on the running workflow
2. Click on the "Test SAR Deployment" job
3. Expand steps to see real-time logs

### Expected Steps

1. ✅ Checkout code
2. ✅ Configure AWS credentials (OIDC)
3. ✅ Setup test secrets (creates 2 secrets)
4. ✅ SAM build
5. ✅ SAM package (creates S3 bucket if needed)
6. ✅ SAM publish to SAR (private)
7. ✅ Deploy from SAR
8. ✅ Test replication (updates source, checks destination)
9. ✅ Check CloudWatch Logs
10. ✅ Cleanup test resources (if enabled)

### Expected Duration

- **Total**: 8-12 minutes
- **Build**: 2-3 minutes
- **Deploy**: 3-5 minutes
- **Test**: 30 seconds
- **Cleanup**: 2-3 minutes

## Step 6: Review Results

### Check Job Summary

After the workflow completes:
1. Click the workflow run
2. Scroll down to see the **Summary**
3. Review:
   - AWS Identity
   - Test secrets created
   - Application packaged
   - Published to SAR
   - Deployment status
   - CloudWatch Logs

### Verify in AWS Console

**Secrets Manager:**
1. Go to: https://console.aws.amazon.com/secretsmanager/
2. Region: us-west-2
3. Look for: `sar-test-{run_id}-source`
4. Should be DELETED if cleanup=true

**Serverless Application Repository:**
1. Go to: https://console.aws.amazon.com/serverlessrepo/
2. Click "My Applications"
3. Look for: `secrets-replicator`
4. Status: PRIVATE (not public yet)

**CloudFormation:**
1. Go to: https://console.aws.amazon.com/cloudformation/
2. Look for: `secrets-replicator-sar-test-{run_id}`
3. Should be DELETED if cleanup=true

## Troubleshooting

### Issue: "User is not authorized to perform: sts:AssumeRoleWithWebIdentity"

**Cause:** OIDC provider not configured or trust policy incorrect

**Solution:**
```bash
# Verify OIDC provider exists
aws iam list-open-id-connect-providers

# Should show:
# arn:aws:iam::965862100780:oidc-provider/token.actions.githubusercontent.com

# If missing, create it:
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Issue: "Access Denied" errors during deployment

**Cause:** IAM role missing required permissions

**Solution:** Review and update IAM policy (see Step 1)

### Issue: Workflow doesn't appear in Actions tab

**Cause:** Workflow file not in correct location or has syntax errors

**Solution:**
```bash
# Verify file location
ls -la .github/workflows/test-sar.yml

# Validate workflow syntax
gh workflow view test-sar.yml
```

### Issue: "Environment 'production' not found"

**Cause:** GitHub environment not created

**Solution:**
1. Settings → Environments → New environment
2. Name: `production`
3. Add variables: `AWS_ACCOUNT_ID` and `AWS_REGION`

### Issue: Secrets not cleaned up

**Cause:** Cleanup step failed or cleanup=false

**Solution:**
```bash
# Manual cleanup via local script
./scripts/cleanup-test-secrets.sh \
  --region us-west-2 \
  --dest-region us-east-1 \
  --prefix sar-test-{run_id} \
  --yes

# Or via AWS CLI
aws secretsmanager delete-secret \
  --secret-id sar-test-{run_id}-source \
  --force-delete-without-recovery \
  --region us-west-2
```

## Cost Estimation

### Per Workflow Run (with cleanup=true)

| Resource | Duration | Cost |
|----------|----------|------|
| Secrets Manager (2 secrets) | ~10 minutes | $0.01 |
| Lambda executions | 1-2 invocations | $0.001 |
| S3 storage | Persistent | $0.02/month |
| CloudWatch Logs | ~50MB | $0.03 |
| **Total per run** | | **~$0.05** |

### Monthly Cost (if running weekly)

- 4 runs/month × $0.05 = **$0.20/month**
- Plus S3 storage: **$0.02/month**
- **Total: ~$0.22/month**

### Cost Optimization

1. **Always use cleanup=true** for test runs
2. **Delete S3 bucket** after testing complete
3. **Delete SAR application** when not needed
4. **Use on-demand testing** (don't schedule automatically)

## Next Steps

After successful GitHub Actions testing:

1. **Make SAR application public** (see [SAR Publishing Guide](sar-publishing.md))
2. **Publish to additional regions** (us-east-1, eu-west-1)
3. **Create GitHub release** (version 1.0.0)
4. **Update README** with SAR installation instructions
5. **Announce** on AWS forums/Reddit

## Resources

- [GitHub Actions OIDC Documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [SAR Publishing Guide](sar-publishing.md)
- [Testing Guide](testing-sar.md)
