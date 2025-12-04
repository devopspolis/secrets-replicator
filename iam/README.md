# IAM Policies for GitHub Actions

This directory contains IAM policies required for the GitHub Actions workflows to deploy the Secrets Replicator application.

## GitHub Actions Role Policy

**File**: `github-actions-role-policy.json`

This policy grants the `github-actions-role` IAM role the necessary permissions to:
- Deploy SAM applications via CloudFormation
- Manage Lambda functions, EventBridge rules, SQS queues, SNS topics
- Create and manage CloudWatch alarms and log groups
- Upload artifacts to S3

### How to Apply

#### Option 1: AWS Console

1. Go to [IAM Console](https://console.aws.amazon.com/iam/)
2. Navigate to **Roles** → `github-actions-role`
3. Click **Add permissions** → **Create inline policy**
4. Switch to **JSON** tab
5. Copy the contents of `github-actions-role-policy.json`
6. Paste into the policy editor
7. Click **Review policy**
8. Name it: `SecretsReplicatorDeployment`
9. Click **Create policy**

#### Option 2: AWS CLI

```bash
# Set your account ID
ACCOUNT_ID=737549531315

# Create the policy
aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name SecretsReplicatorDeployment \
  --policy-document file://iam/github-actions-role-policy.json

# Verify the policy was created
aws iam get-role-policy \
  --role-name github-actions-role \
  --policy-name SecretsReplicatorDeployment
```

#### Option 3: Terraform (if using IaC)

```hcl
resource "aws_iam_role_policy" "github_actions_secrets_replicator" {
  name   = "SecretsReplicatorDeployment"
  role   = aws_iam_role.github_actions.name
  policy = file("${path.module}/iam/github-actions-role-policy.json")
}
```

### Permissions Breakdown

The policy includes permissions for:

| Service | Actions | Resources |
|---------|---------|-----------|
| **CloudFormation** | Create/manage stacks and changesets | Application stacks and SAM managed stack |
| **S3** | Bucket and object operations | SAM managed buckets and build artifacts bucket |
| **Lambda** | Function management | secrets-replicator-* functions |
| **IAM** | Role management | secrets-replicator-* execution roles |
| **EventBridge** | Rule management | secrets-replicator-* rules |
| **SQS** | Queue management | secrets-replicator-* queues |
| **SNS** | Topic management | secrets-replicator-* topics |
| **CloudWatch** | Alarms and metrics | secrets-replicator-* alarms |
| **CloudWatch Logs** | Log group management | /aws/lambda/secrets-replicator-* |
| **STS** | GetCallerIdentity | All (needed for identity verification) |

### Environment Scoping

The policy is scoped to three environments:
- `secrets-replicator-dev-*`
- `secrets-replicator-qa-*`
- `secrets-replicator-prod-*`

This follows the principle of least privilege while allowing deployments to all environments.

### Security Considerations

1. **Least Privilege**: Resources are scoped to `secrets-replicator-*` prefixes
2. **No Wildcards**: Specific actions are listed (no `*` actions)
3. **Account Scoped**: All ARNs include the account ID `737549531315`
4. **Environment Aware**: Each environment has its own resource namespace

### Troubleshooting

If deployments fail with permission errors:

1. Check the error message for the specific action and resource
2. Verify the resource name matches the pattern in this policy
3. Ensure the policy is attached to the correct role
4. Check CloudTrail for denied API calls

### Testing

After applying the policy, test by triggering a deployment:

```bash
# Trigger the dev deployment workflow
gh workflow run "Deploy to Dev" --ref main

# Watch the workflow
gh run watch
```

## Other IAM Policies

This directory may contain additional policies for:
- Lambda execution roles
- Cross-account destination roles
- Service-specific policies

Refer to the main [IAM_SETUP.md](../docs/multi-account-deployment.md) for comprehensive IAM setup instructions.
