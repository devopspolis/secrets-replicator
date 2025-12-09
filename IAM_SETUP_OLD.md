# IAM Setup Guide for Multi-Account Deployment

This document describes the IAM roles and policies required for the multi-account deployment pattern with proper environment isolation.

## Security Architecture

### Key Principles

1. **Environment Isolation**: QA cannot write to Production
2. **Read-Only Cross-Account Access**: Production can only READ from QA
3. **Least Privilege**: Each role has minimum required permissions
4. **Audit Trail**: All cross-account access is logged via CloudTrail

### Access Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                      QA Account                             │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  S3: secrets-replicator-builds-{region}              │  │
│  │  - releases/1.0.0/packaged-qa.yaml                   │  │
│  └─────────────────────┬────────────────────────────────┘  │
│                        │                                    │
│  ┌─────────────────────▼────────────────────────────────┐  │
│  │  IAM Role: github-actions-cross-account-read         │  │
│  │  - Trust: Production Account                         │  │
│  │  - Permissions: S3 GetObject (read-only)            │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          │ AssumeRole (read-only)
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   Production Account                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  IAM Role: github-actions-role                       │  │
│  │  - Trust: GitHub OIDC                                │  │
│  │  - Permissions: sts:AssumeRole (to QA read role)    │  │
│  │  - Permissions: CloudFormation, Lambda, etc.        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup Instructions

### 1. Development Account (Optional but Recommended)

If using a development account, it only needs its own deployment role:

#### IAM Role: `github-actions-role`

**Trust Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::{DEV_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
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

**Permissions Policy** (attach managed policy or inline):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormationAccess",
      "Effect": "Allow",
      "Action": [
        "cloudformation:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LambdaAccess",
      "Effect": "Allow",
      "Action": [
        "lambda:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAMRoleAccess",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:PassRole",
        "iam:TagRole",
        "iam:UntagRole"
      ],
      "Resource": "arn:aws:iam::{DEV_ACCOUNT_ID}:role/secrets-replicator-*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::aws-sam-cli-*",
        "arn:aws:s3:::aws-sam-cli-*/*"
      ]
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "KMSAccess",
      "Effect": "Allow",
      "Action": [
        "kms:CreateKey",
        "kms:DescribeKey",
        "kms:PutKeyPolicy",
        "kms:CreateAlias",
        "kms:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EventBridgeAccess",
      "Effect": "Allow",
      "Action": [
        "events:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SQSAccess",
      "Effect": "Allow",
      "Action": [
        "sqs:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SNSAccess",
      "Effect": "Allow",
      "Action": [
        "sns:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchAccess",
      "Effect": "Allow",
      "Action": [
        "logs:*",
        "cloudwatch:*"
      ],
      "Resource": "*"
    }
  ]
}
```

---

### 2. QA Account Setup

QA account needs TWO roles:
1. Deployment role for GitHub Actions
2. Cross-account read role for Production

#### Role 1: `github-actions-role` (QA Deployment)

**Trust Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::{QA_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
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

**Permissions Policy** (same as dev account above, replace account ID)

#### Role 2: `github-actions-cross-account-read` (Production Reads QA)

**Trust Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::{PRODUCTION_ACCOUNT_ID}:root"
    },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": {
        "sts:ExternalId": "secrets-replicator-prod-read-qa"
      }
    }
  }]
}
```

**Permissions Policy** (read-only S3 access):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadQABuilds",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::secrets-replicator-builds-{QA_REGION}/releases/*"
    },
    {
      "Sid": "ListQABucket",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketVersioning"
      ],
      "Resource": "arn:aws:s3:::secrets-replicator-builds-{QA_REGION}",
      "Condition": {
        "StringLike": {
          "s3:prefix": "releases/*"
        }
      }
    }
  ]
}
```

#### S3 Bucket Policy (QA Account)

Add this to the `secrets-replicator-builds-{region}` bucket in QA:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowProductionReadAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::{QA_ACCOUNT_ID}:role/github-actions-cross-account-read"
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::secrets-replicator-builds-{QA_REGION}/releases/*"
    },
    {
      "Sid": "AllowProductionListBucket",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::{QA_ACCOUNT_ID}:role/github-actions-cross-account-read"
      },
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketVersioning"
      ],
      "Resource": "arn:aws:s3:::secrets-replicator-builds-{QA_REGION}",
      "Condition": {
        "StringLike": {
          "s3:prefix": "releases/*"
        }
      }
    }
  ]
}
```

---

### 3. Production Account Setup

Production account needs one role with extended permissions:

#### IAM Role: `github-actions-role`

**Trust Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::{PROD_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
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

**Permissions Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeQAReadRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::{QA_ACCOUNT_ID}:role/github-actions-cross-account-read",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "secrets-replicator-prod-read-qa"
        }
      }
    },
    {
      "Sid": "CloudFormationAccess",
      "Effect": "Allow",
      "Action": [
        "cloudformation:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LambdaAccess",
      "Effect": "Allow",
      "Action": [
        "lambda:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAMRoleAccess",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:PassRole",
        "iam:TagRole",
        "iam:UntagRole"
      ],
      "Resource": "arn:aws:iam::{PROD_ACCOUNT_ID}:role/secrets-replicator-*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::aws-sam-cli-*",
        "arn:aws:s3:::aws-sam-cli-*/*",
        "arn:aws:s3:::secrets-replicator-sar-*",
        "arn:aws:s3:::secrets-replicator-sar-*/*"
      ]
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "KMSAccess",
      "Effect": "Allow",
      "Action": [
        "kms:CreateKey",
        "kms:DescribeKey",
        "kms:PutKeyPolicy",
        "kms:CreateAlias",
        "kms:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EventBridgeAccess",
      "Effect": "Allow",
      "Action": [
        "events:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SQSAccess",
      "Effect": "Allow",
      "Action": [
        "sqs:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SNSAccess",
      "Effect": "Allow",
      "Action": [
        "sns:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchAccess",
      "Effect": "Allow",
      "Action": [
        "logs:*",
        "cloudwatch:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SARAccess",
      "Effect": "Allow",
      "Action": [
        "serverlessrepo:CreateApplication",
        "serverlessrepo:UpdateApplication",
        "serverlessrepo:CreateApplicationVersion",
        "serverlessrepo:PutApplicationPolicy",
        "serverlessrepo:GetApplication",
        "serverlessrepo:ListApplicationVersions"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## GitHub Environment Variables

Configure these in GitHub Settings → Environments:

### Development Environment (`development`)
- `AWS_ACCOUNT_ID`: Development AWS account ID
- `AWS_REGION`: Primary region (e.g., `us-east-1`)

### QA Environment (`qa`)
- `AWS_ACCOUNT_ID`: QA AWS account ID
- `AWS_REGION`: Primary region (e.g., `us-east-1`)

### QA Approval Environment (`qa-approval`)
- **No variables needed**
- Configure Required Reviewers in GitHub environment settings
- Recommended: Require at least 1 reviewer for QA deployments

### Production Environment (`production`)
- `AWS_ACCOUNT_ID`: Production AWS account ID
- `AWS_REGION`: Primary region (e.g., `us-east-1`)
- `QA_ACCOUNT_ID`: QA AWS account ID (for cross-account read)
- `QA_REGION`: QA region (usually same as prod)

### Production Approval Environment (`production-approval`)
- **No variables needed**
- Configure Required Reviewers in GitHub environment settings
- Recommended: Require at least 2 reviewers for production deployments

---

## OIDC Provider Setup

Each AWS account needs an OIDC provider for GitHub Actions:

### Create OIDC Provider (All Accounts)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --tags Key=Name,Value=GitHubActions
```

**Note**: The thumbprint `6938fd4d98bab03faadb97b34396831e3780aea1` is GitHub's current certificate thumbprint. Verify it's still current at: https://github.blog/changelog/2022-01-13-github-actions-update-on-oidc-based-deployments-to-aws/

---

## Testing IAM Setup

### 1. Test Development Deployment
```bash
# Trigger dev workflow
git push origin main
# Verify: Actions → Deploy to Dev → Check for OIDC auth success
```

### 2. Test QA Build and Deployment
```bash
# Trigger QA workflow
git tag v0.1.0-test
git push origin v0.1.0-test
gh release create v0.1.0-test --generate-notes

# Verify:
# 1. Build job completes
# 2. Approval job waits for manual approval
# 3. After approval, deployment succeeds
```

### 3. Test Cross-Account Read (Production)
```bash
# In production workflow, verify assume role works
aws sts assume-role \
  --role-arn arn:aws:iam::{QA_ACCOUNT_ID}:role/github-actions-cross-account-read \
  --role-session-name test \
  --external-id secrets-replicator-prod-read-qa

# Then test S3 read
aws s3 cp s3://secrets-replicator-builds-{QA_REGION}/releases/0.1.0-test/packaged-qa.yaml . \
  --region {QA_REGION}
```

### 4. Verify Isolation (Production Cannot Write to QA)
```bash
# This should FAIL (as intended)
aws s3 cp test.txt s3://secrets-replicator-builds-{QA_REGION}/releases/test.txt
# Expected: Access Denied
```

---

## Security Best Practices

1. **ExternalId for AssumeRole**: Always use an external ID when assuming cross-account roles to prevent confused deputy attacks

2. **Least Privilege**: The cross-account read role in QA only has S3 read permissions, nothing else

3. **Audit Logging**: Enable CloudTrail in all accounts to log all API calls, especially cross-account assumptions

4. **MFA for Sensitive Operations**: Consider requiring MFA for production approvals in GitHub

5. **Temporary Credentials**: All OIDC sessions are temporary (12 hours max), no long-lived credentials

6. **Resource Tagging**: Tag all resources with Environment and ManagedBy tags for visibility

7. **Environment Protection Rules**: Configure required reviewers for qa-approval and production-approval environments

---

## Troubleshooting

### Issue: AssumeRole fails with "not authorized"

**Solution**:
1. Verify trust policy in QA cross-account read role allows production account
2. Verify external ID matches in both trust policy and assume-role call
3. Check IAM role in production has `sts:AssumeRole` permission

### Issue: S3 GetObject fails from production

**Solution**:
1. Verify S3 bucket policy in QA allows the cross-account read role
2. Check the S3 object exists: `aws s3 ls s3://bucket/path/ --region {region}`
3. Verify bucket versioning is enabled if using GetObjectVersion

### Issue: OIDC authentication fails

**Solution**:
1. Verify OIDC provider exists: `aws iam list-open-id-connect-providers`
2. Check repository name in trust policy exactly matches GitHub repo
3. Verify thumbprint is current

### Issue: Approval not showing in GitHub Actions

**Solution**:
1. Verify GitHub environment exists with exact name (e.g., `qa-approval`)
2. Add required reviewers in environment settings
3. Check workflow syntax: `environment: qa-approval` (not `env:`)

---

## CloudFormation Alternative

For automated setup, consider creating CloudFormation stacks for IAM roles:

### Example: QA Cross-Account Read Role

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Cross-account read role for Production to read QA artifacts

Parameters:
  ProductionAccountId:
    Type: String
    Description: Production AWS Account ID
  QARegion:
    Type: String
    Default: us-east-1
    Description: QA region where build bucket exists

Resources:
  CrossAccountReadRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: github-actions-cross-account-read
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Sub 'arn:aws:iam::${ProductionAccountId}:root'
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: secrets-replicator-prod-read-qa
      Policies:
        - PolicyName: ReadQABuilds
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - s3:GetObject
                  - s3:GetObjectVersion
                Resource: !Sub 'arn:aws:s3:::secrets-replicator-builds-${QARegion}/releases/*'
              - Effect: Allow
                Action:
                  - s3:ListBucket
                  - s3:GetBucketVersioning
                Resource: !Sub 'arn:aws:s3:::secrets-replicator-builds-${QARegion}'
                Condition:
                  StringLike:
                    s3:prefix: 'releases/*'
      Tags:
        - Key: Purpose
          Value: CrossAccountArtifactRead
        - Key: ManagedBy
          Value: CloudFormation

Outputs:
  RoleArn:
    Description: ARN of cross-account read role
    Value: !GetAtt CrossAccountReadRole.Arn
    Export:
      Name: CrossAccountReadRoleArn
```

Deploy with:
```bash
aws cloudformation create-stack \
  --stack-name secrets-replicator-cross-account-read \
  --template-body file://cross-account-read-role.yaml \
  --parameters ParameterKey=ProductionAccountId,ParameterValue={PROD_ACCOUNT_ID} \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

---

## Summary

This IAM setup ensures:
- ✅ Complete environment isolation (QA cannot write to Production)
- ✅ Controlled artifact promotion (Production reads from QA, read-only)
- ✅ Least privilege access (each role has minimum required permissions)
- ✅ Audit trail (CloudTrail logs all cross-account access)
- ✅ Approval gates (manual approval required for deployments)
- ✅ No long-lived credentials (OIDC provides temporary tokens)

For questions or issues, refer to:
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [GitHub OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS Cross-Account Access](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_aws-accounts.html)
