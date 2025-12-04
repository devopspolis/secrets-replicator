# GitHub Actions Role Policy Comparison

## Current Policy vs Required Policy

### Missing Permissions in Current Policy

Your current `secrets-replicator-policy` is missing the following permissions needed for SAM deployments:

#### 1. CloudFormation - Missing Actions
```diff
+ "cloudformation:DescribeStackResources"
+ "cloudformation:GetTemplate"
+ "cloudformation:ValidateTemplate"
```

#### 2. CloudFormation - Missing Resources (QA/Prod)
```diff
+ "arn:aws:cloudformation:*:737549531315:stack/secrets-replicator-qa/*"
+ "arn:aws:cloudformation:*:737549531315:stack/secrets-replicator-prod/*"
```

#### 3. S3 - Missing Actions
```diff
+ "s3:GetBucketLocation"
+ "s3:GetBucketPolicy"
+ "s3:PutBucketPolicy"
+ "s3:GetBucketVersioning"
+ "s3:PutBucketVersioning"
+ "s3:GetBucketTagging"
+ "s3:PutBucketTagging"
+ "s3:DeleteObject"
```

#### 4. S3 - Missing Resources (Build Artifacts)
```diff
+ "arn:aws:s3:::secrets-replicator-builds"
+ "arn:aws:s3:::secrets-replicator-builds/*"
```

#### 5. IAM - Missing Actions
```diff
+ "iam:GetRolePolicy"
+ "iam:TagRole"
+ "iam:UntagRole"
```

#### 6. IAM - Missing Resources (QA/Prod)
```diff
+ "arn:aws:iam::737549531315:role/secrets-replicator-qa-*"
+ "arn:aws:iam::737549531315:role/secrets-replicator-prod-*"
```

#### 7. Lambda - Missing Actions
```diff
+ "lambda:GetFunctionConfiguration"
+ "lambda:TagResource"
+ "lambda:UntagResource"
+ "lambda:PublishVersion"
+ "lambda:ListTags"
```

#### 8. Lambda - Missing Resources (QA/Prod)
```diff
+ "arn:aws:lambda:*:737549531315:function:secrets-replicator-qa-*"
+ "arn:aws:lambda:*:737549531315:function:secrets-replicator-prod-*"
```

#### 9. EventBridge - COMPLETELY MISSING
```json
{
    "Sid": "EventBridgeManagement",
    "Effect": "Allow",
    "Action": [
        "events:PutRule",
        "events:DeleteRule",
        "events:DescribeRule",
        "events:PutTargets",
        "events:RemoveTargets",
        "events:TagResource",
        "events:UntagResource"
    ],
    "Resource": [
        "arn:aws:events:*:737549531315:rule/secrets-replicator-dev-*",
        "arn:aws:events:*:737549531315:rule/secrets-replicator-qa-*",
        "arn:aws:events:*:737549531315:rule/secrets-replicator-prod-*"
    ]
}
```

#### 10. SQS - COMPLETELY MISSING
```json
{
    "Sid": "SQSManagement",
    "Effect": "Allow",
    "Action": [
        "sqs:CreateQueue",
        "sqs:DeleteQueue",
        "sqs:GetQueueAttributes",
        "sqs:SetQueueAttributes",
        "sqs:TagQueue",
        "sqs:UntagQueue",
        "sqs:GetQueueUrl"
    ],
    "Resource": [
        "arn:aws:sqs:*:737549531315:secrets-replicator-dev-*",
        "arn:aws:sqs:*:737549531315:secrets-replicator-qa-*",
        "arn:aws:sqs:*:737549531315:secrets-replicator-prod-*"
    ]
}
```

#### 11. SNS - COMPLETELY MISSING
```json
{
    "Sid": "SNSManagement",
    "Effect": "Allow",
    "Action": [
        "sns:CreateTopic",
        "sns:DeleteTopic",
        "sns:GetTopicAttributes",
        "sns:SetTopicAttributes",
        "sns:Subscribe",
        "sns:Unsubscribe",
        "sns:TagResource",
        "sns:UntagResource"
    ],
    "Resource": [
        "arn:aws:sns:*:737549531315:secrets-replicator-dev-*",
        "arn:aws:sns:*:737549531315:secrets-replicator-qa-*",
        "arn:aws:sns:*:737549531315:secrets-replicator-prod-*"
    ]
}
```

#### 12. CloudWatch - COMPLETELY MISSING
```json
{
    "Sid": "CloudWatchManagement",
    "Effect": "Allow",
    "Action": [
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms",
        "cloudwatch:DescribeAlarms",
        "cloudwatch:TagResource",
        "cloudwatch:UntagResource"
    ],
    "Resource": [
        "arn:aws:cloudwatch:*:737549531315:alarm:secrets-replicator-dev-*",
        "arn:aws:cloudwatch:*:737549531315:alarm:secrets-replicator-qa-*",
        "arn:aws:cloudwatch:*:737549531315:alarm:secrets-replicator-prod-*"
    ]
}
```

#### 13. CloudWatch Logs - COMPLETELY MISSING
```json
{
    "Sid": "LogsManagement",
    "Effect": "Allow",
    "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:PutRetentionPolicy",
        "logs:TagLogGroup",
        "logs:UntagLogGroup",
        "logs:TagResource",
        "logs:UntagResource"
    ],
    "Resource": [
        "arn:aws:logs:*:737549531315:log-group:/aws/lambda/secrets-replicator-dev-*",
        "arn:aws:logs:*:737549531315:log-group:/aws/lambda/secrets-replicator-qa-*",
        "arn:aws:logs:*:737549531315:log-group:/aws/lambda/secrets-replicator-prod-*"
    ]
}
```

#### 14. STS - COMPLETELY MISSING
```json
{
    "Sid": "STSGetCallerIdentity",
    "Effect": "Allow",
    "Action": [
        "sts:GetCallerIdentity"
    ],
    "Resource": "*"
}
```

## Summary

**Total Missing Statement Blocks:** 6 entire services (EventBridge, SQS, SNS, CloudWatch, Logs, STS)

**Missing Actions in Existing Services:**
- CloudFormation: 3 actions + 2 environments
- S3: 7 actions + 2 resources
- IAM: 3 actions + 2 environments
- Lambda: 5 actions + 2 environments

## Recommendation

**Replace** the current `secrets-replicator-policy` with the updated policy in `github-actions-role-policy-UPDATED.json`.

### How to Apply

```bash
# Update the inline policy
aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name secrets-replicator-policy \
  --policy-document file://iam/github-actions-role-policy-UPDATED.json

# Verify
aws iam get-role-policy \
  --role-name github-actions-role \
  --policy-name secrets-replicator-policy
```

Or via AWS Console:
1. Go to IAM → Roles → github-actions-role
2. Click on the `secrets-replicator-policy` inline policy
3. Click **Edit**
4. Replace JSON with contents from `github-actions-role-policy-UPDATED.json`
5. Click **Save changes**

## Why These Permissions Are Needed

| Service | Why Needed |
|---------|------------|
| **EventBridge** | SAM template creates EventBridge rules to trigger Lambda on secret changes |
| **SQS** | Dead Letter Queue (DLQ) for failed Lambda invocations |
| **SNS** | Alert topic for CloudWatch alarms |
| **CloudWatch** | Alarms for replication failures, throttling, high duration |
| **Logs** | Lambda function log groups with retention policies |
| **STS** | Identity verification in deployment workflows |

All permissions follow the principle of least privilege with resource-level scoping to `secrets-replicator-*` prefixes.
