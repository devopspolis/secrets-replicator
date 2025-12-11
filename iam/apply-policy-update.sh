#!/bin/bash
#
# Apply GitHub Actions IAM Policy Update
#
# This script applies the fixed IAM policy to the github-actions-role.
# Run this after refreshing your AWS SSO login.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== GitHub Actions IAM Policy Update ===${NC}"
echo ""

# Check if AWS SSO session is valid
echo "Checking AWS SSO session..."
if ! AWS_PROFILE=admin@meneely-dev aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS SSO session expired or not found${NC}"
    echo ""
    echo "Please refresh your AWS SSO login first:"
    echo "  aws sso login --profile admin@meneely-dev"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ AWS SSO session valid${NC}"
echo ""

# Get current identity
IDENTITY=$(AWS_PROFILE=admin@meneely-dev aws sts get-caller-identity)
echo "Current AWS identity:"
echo "$IDENTITY" | jq -r '"  Account: \(.Account)\n  User: \(.Arn)"'
echo ""

# Check if policy file exists
POLICY_FILE="iam/github-actions-role-policy-FIXED.json"
if [ ! -f "$POLICY_FILE" ]; then
    echo -e "${RED}Error: Policy file not found: $POLICY_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Policy file found: $POLICY_FILE${NC}"
echo ""

# Show what will be updated
echo -e "${YELLOW}This will update the github-actions-role with:${NC}"
echo "  1. CloudFormation SAM transform permission"
echo "  2. Corrected Lambda function ARN (secrets-replicator)"
echo ""

# Ask for confirmation
read -p "Continue with IAM policy update? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Applying IAM policy update..."

# Apply the policy
AWS_PROFILE=admin@meneely-dev aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name github-actions-deployment-policy \
  --policy-document "file://$POLICY_FILE"

echo -e "${GREEN}✓ IAM policy updated successfully${NC}"
echo ""

# Verify the update
echo "Verifying policy update..."
POLICY_VERSION=$(AWS_PROFILE=admin@meneely-dev aws iam get-role-policy \
  --role-name github-actions-role \
  --policy-name github-actions-deployment-policy \
  --query 'PolicyDocument.Statement[?Sid==`CloudFormationSAMTransform`].Sid' \
  --output text)

if [ -n "$POLICY_VERSION" ]; then
    echo -e "${GREEN}✓ SAM transform permission confirmed${NC}"
else
    echo -e "${RED}⚠ Warning: Could not verify SAM transform permission${NC}"
fi

LAMBDA_ARN=$(AWS_PROFILE=admin@meneely-dev aws iam get-role-policy \
  --role-name github-actions-role \
  --policy-name github-actions-deployment-policy \
  --query 'PolicyDocument.Statement[?Sid==`LambdaManagement`].Resource[0]' \
  --output text)

echo "Lambda function ARN in policy: $LAMBDA_ARN"
if [[ "$LAMBDA_ARN" == *"secrets-replicator"* ]] && [[ "$LAMBDA_ARN" != *"secrets-replicator-dev"* ]]; then
    echo -e "${GREEN}✓ Lambda ARN is correct (no environment suffix)${NC}"
else
    echo -e "${RED}⚠ Warning: Lambda ARN may not be correct${NC}"
fi

echo ""
echo -e "${GREEN}=== Policy Update Complete ===${NC}"
echo ""
echo "Next steps:"
echo "  1. The GitHub Actions workflow should now succeed"
echo "  2. Monitor the workflow: gh run watch"
echo "  3. Or view in browser: https://github.com/devopspolis/secrets-replicator/actions"
echo ""
