# IAM Policy Templates

This document contains IAM policy templates for the Secrets Replicator Lambda function.

## Table of Contents

- [Lambda Execution Role Policy](#lambda-execution-role-policy)
- [Cross-Account Destination Role Policy](#cross-account-destination-role-policy)
- [Cross-Account Trust Policy](#cross-account-trust-policy)
- [Minimum Permissions Example](#minimum-permissions-example)

---

## Lambda Execution Role Policy

This policy should be attached to the Lambda function's execution role in the **source account**.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchLogsAccess",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/secrets-replicator*"
    },
    {
      "Sid": "ReadSourceSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:*"
      ],
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "${SOURCE_REGION}"
        }
      }
    },
    {
      "Sid": "WriteDestinationSecretsSameAccount",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:DescribeSecret",
        "secretsmanager:TagResource"
      ],
      "Resource": [
        "arn:aws:secretsmanager:${DEST_REGION}:${ACCOUNT_ID}:secret:*"
      ]
    },
    {
      "Sid": "KMSDecryptSource",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": [
        "arn:aws:kms:${SOURCE_REGION}:${ACCOUNT_ID}:key/*"
      ],
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.${SOURCE_REGION}.amazonaws.com"
        }
      }
    },
    {
      "Sid": "KMSEncryptDestination",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:DescribeKey"
      ],
      "Resource": [
        "arn:aws:kms:${DEST_REGION}:${ACCOUNT_ID}:key/*"
      ],
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.${DEST_REGION}.amazonaws.com"
        }
      }
    },
    {
      "Sid": "LoadSedfileFromS3",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": [
        "arn:aws:s3:::${SEDFILE_BUCKET}/${SEDFILE_KEY}"
      ]
    },
    {
      "Sid": "AssumeDestinationRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::${DEST_ACCOUNT_ID}:role/${DEST_ROLE_NAME}"
      ]
    },
    {
      "Sid": "PublishMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "SecretsReplicator"
        }
      }
    },
    {
      "Sid": "SendToDLQ",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": [
        "arn:aws:sqs:${SOURCE_REGION}:${ACCOUNT_ID}:secrets-replicator-dlq"
      ]
    }
  ]
}
```

### Variables to Replace

- `${SOURCE_REGION}`: Source AWS region (e.g., `us-east-1`)
- `${DEST_REGION}`: Destination AWS region (e.g., `us-west-2`)
- `${ACCOUNT_ID}`: AWS account ID (source account)
- `${DEST_ACCOUNT_ID}`: Destination AWS account ID (for cross-account)
- `${DEST_ROLE_NAME}`: Name of the destination role (for cross-account)
- `${SEDFILE_BUCKET}`: S3 bucket containing sedfile
- `${SEDFILE_KEY}`: S3 key for sedfile

---

## Cross-Account Destination Role Policy

This policy should be attached to a role in the **destination account** that the Lambda function will assume.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteDestinationSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:DescribeSecret",
        "secretsmanager:TagResource"
      ],
      "Resource": [
        "arn:aws:secretsmanager:${DEST_REGION}:${DEST_ACCOUNT_ID}:secret:*"
      ]
    },
    {
      "Sid": "KMSEncryptDestination",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": [
        "arn:aws:kms:${DEST_REGION}:${DEST_ACCOUNT_ID}:key/${KMS_KEY_ID}"
      ],
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.${DEST_REGION}.amazonaws.com"
        }
      }
    }
  ]
}
```

---

## Cross-Account Trust Policy

This trust policy should be attached to the destination role to allow the source Lambda to assume it.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${SOURCE_ACCOUNT_ID}:role/${LAMBDA_EXECUTION_ROLE_NAME}"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "${EXTERNAL_ID}"
        }
      }
    }
  ]
}
```

### Variables to Replace

- `${SOURCE_ACCOUNT_ID}`: Source AWS account ID
- `${LAMBDA_EXECUTION_ROLE_NAME}`: Name of the Lambda execution role
- `${EXTERNAL_ID}`: External ID for additional security (optional but recommended)

---

## Minimum Permissions Example

For development or testing, here's a minimal policy that allows replication within the same account and region:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MinimalLogging",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Sid": "MinimalSecretsAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
```

**Warning**: This minimal policy grants broad permissions and should only be used for testing. Use the more specific policies above for production.

---

## Setup Instructions

### Same-Account Replication

1. Create an IAM role for the Lambda function
2. Attach the Lambda Execution Role Policy (remove the `AssumeDestinationRole` statement)
3. Attach the AWS managed policy: `AWSLambdaBasicExecutionRole`
4. Configure the Lambda function to use this role

### Cross-Account Replication

#### In Source Account:

1. Create an IAM role for the Lambda function
2. Attach the full Lambda Execution Role Policy
3. Attach the AWS managed policy: `AWSLambdaBasicExecutionRole`
4. Note the role ARN

#### In Destination Account:

1. Create an IAM role with the Destination Role Policy
2. Attach the Cross-Account Trust Policy
3. Generate a secure external ID (e.g., using `uuidgen`)
4. Update the trust policy with the external ID
5. Note the role ARN

#### Configure Lambda:

Set these environment variables:
```bash
DEST_ACCOUNT_ROLE_ARN=arn:aws:iam::DEST_ACCOUNT:role/SecretsReplicatorDestRole
```

---

## Security Best Practices

1. **Use External ID**: Always use an external ID for cross-account role assumption
2. **Limit Resource Access**: Use specific ARN patterns instead of wildcards
3. **Enable CloudTrail**: Monitor all secret access and replication events
4. **Rotate External ID**: Periodically rotate the external ID
5. **Use KMS**: Encrypt secrets with customer-managed KMS keys
6. **Least Privilege**: Grant only the minimum permissions needed
7. **Condition Keys**: Use IAM condition keys to restrict access further
8. **Resource Tags**: Use resource tags for fine-grained access control

---

## Troubleshooting

### Access Denied Errors

If you encounter "Access Denied" errors:

1. Check CloudTrail logs for the specific API call that failed
2. Verify the IAM policy has the required action
3. Check resource ARN patterns match your secrets
4. Verify KMS key policies allow the Lambda role
5. For cross-account, verify trust policy and external ID

### Common Issues

**Issue**: `AccessDeniedException` when reading source secret
- **Solution**: Add `secretsmanager:GetSecretValue` to source policy

**Issue**: `AccessDeniedException` when writing to destination
- **Solution**: Add `secretsmanager:CreateSecret` and `PutSecretValue` to destination policy

**Issue**: `KMS.DisabledException` or KMS access errors
- **Solution**: Verify KMS key policy allows the Lambda role to encrypt/decrypt

**Issue**: Cross-account assumption fails
- **Solution**: Check trust policy, external ID, and source role ARN

---

## Example CloudFormation

Here's a CloudFormation snippet to create the Lambda execution role:

```yaml
LambdaExecutionRole:
  Type: AWS::IAM::Role
  Properties:
    RoleName: SecretsReplicatorExecutionRole
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: lambda.amazonaws.com
          Action: sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    Policies:
      - PolicyName: SecretsReplicatorPolicy
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            # Add policy statements from above
```

---

## Testing IAM Policies

Use the IAM Policy Simulator to test policies before deployment:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT:role/SecretsReplicatorRole \
  --action-names secretsmanager:GetSecretValue \
  --resource-arns arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:test-secret
```

---

**Last Updated**: 2025-11-01
**Version**: 1.0.0
