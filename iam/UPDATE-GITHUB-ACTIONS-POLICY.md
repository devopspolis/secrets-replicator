# GitHub Actions IAM Policy Update Guide

## Problem

The GitHub Actions workflow fails with the following error:

```
User: arn:aws:sts::737549531315:assumed-role/github-actions-role/GitHubActions-Dev-20102224608
is not authorized to perform: cloudformation:CreateChangeSet on resource:
arn:aws:cloudformation:us-west-2:aws:transform/Serverless-2016-10-31
```

## Root Cause

The `github-actions-role` IAM policy is missing permission to create CloudFormation changesets on the **SAM transform resource**. SAM (Serverless Application Model) uses a CloudFormation transform (`AWS::Serverless-2016-10-31`) to expand serverless resources, and this transform requires explicit permission.

## Solution

Add a new IAM policy statement that grants `cloudformation:CreateChangeSet` permission on the SAM transform resource.

## What Changed

The new policy file `github-actions-role-policy-FIXED.json` includes a new statement:

```json
{
  "Sid": "CloudFormationSAMTransform",
  "Effect": "Allow",
  "Action": [
    "cloudformation:CreateChangeSet"
  ],
  "Resource": [
    "arn:aws:cloudformation:*:aws:transform/Serverless-2016-10-31"
  ]
}
```

Additional minor improvements:
- Added `lambda:ListTags` to Lambda permissions
- Added `sqs:GetQueueUrl` to SQS permissions
- Added `logs:TagResource` and `logs:UntagResource` to CloudWatch Logs permissions

## How to Apply the Fix

### Step 1: Refresh AWS SSO Login

```bash
aws sso login --profile admin@meneely-dev
```

### Step 2: Verify Current Policy Name

First, check what inline policy is attached to the role:

```bash
AWS_PROFILE=admin@meneely-dev aws iam list-role-policies \
  --role-name github-actions-role
```

Expected output:
```json
{
    "PolicyNames": [
        "github-actions-deployment-policy"
    ]
}
```

### Step 3: Apply the Updated Policy

Replace the inline policy with the fixed version:

```bash
AWS_PROFILE=admin@meneely-dev aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name github-actions-deployment-policy \
  --policy-document file://iam/github-actions-role-policy-FIXED.json
```

### Step 4: Verify the Update

```bash
AWS_PROFILE=admin@meneely-dev aws iam get-role-policy \
  --role-name github-actions-role \
  --policy-name github-actions-deployment-policy \
  --query PolicyDocument
```

Look for the new `CloudFormationSAMTransform` statement in the output.

### Step 5: Test the GitHub Actions Workflow

Trigger the workflow by pushing a commit or manually triggering the "Deploy to Dev" workflow:

```bash
# Option 1: Push a commit to trigger the workflow
git add iam/github-actions-role-policy-FIXED.json iam/UPDATE-GITHUB-ACTIONS-POLICY.md
git commit -m "Add SAM transform permission to GitHub Actions role"
git push origin main

# Option 2: Manually trigger via GitHub CLI
gh workflow run deploy-dev.yml
```

## Verification

After applying the fix, the GitHub Actions workflow should:

1. ✅ Successfully create the CloudFormation changeset
2. ✅ Deploy the SAM stack to the dev environment
3. ✅ Complete without IAM permission errors

## Rollback (if needed)

If you need to rollback to the previous policy:

```bash
AWS_PROFILE=admin@meneely-dev aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name github-actions-deployment-policy \
  --policy-document file://iam/github-actions-role-policy.json
```

## References

- AWS SAM Transform Reference: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/transform-aws-serverless.html
- CloudFormation IAM Permissions: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-template.html
- GitHub Actions OIDC with AWS: https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services

## Next Steps After Fix

1. ✅ Verify GitHub Actions workflow succeeds
2. ⏭️ Run manual QA testing in dev environment
3. ⏭️ Test deployment to QA environment
4. ⏭️ Consider production release to Serverless Application Repository
