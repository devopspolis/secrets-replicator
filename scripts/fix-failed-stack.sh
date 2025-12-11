#!/bin/bash
#
# Fix CloudFormation Stack in UPDATE_ROLLBACK_FAILED State
#
# This script continues the rollback operation and cleans up the stack
# so it can be updated again.
#

set -e

STACK_NAME="secrets-replicator-dev"
REGION="us-west-2"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== CloudFormation Stack Rollback Recovery ===${NC}"
echo ""

# Check if AWS SSO session is valid
echo "Checking AWS credentials..."
if ! AWS_PROFILE=admin@meneely-dev aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not valid${NC}"
    echo ""
    echo "Please refresh your AWS SSO login first:"
    echo "  aws sso login --profile admin@meneely-dev"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ AWS credentials valid${NC}"
echo ""

# Check stack status
echo "Checking stack status..."
STACK_STATUS=$(AWS_PROFILE=admin@meneely-dev aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

echo "Current stack status: $STACK_STATUS"
echo ""

if [ "$STACK_STATUS" = "UPDATE_ROLLBACK_FAILED" ]; then
    echo -e "${YELLOW}Stack is in UPDATE_ROLLBACK_FAILED state. Initiating rollback continuation...${NC}"
    echo ""

    # Continue the rollback
    echo "Running: aws cloudformation continue-update-rollback..."
    AWS_PROFILE=admin@meneely-dev aws cloudformation continue-update-rollback \
        --stack-name "$STACK_NAME" \
        --region "$REGION"

    echo -e "${GREEN}✓ Rollback continuation initiated${NC}"
    echo ""
    echo "Waiting for rollback to complete (this may take a few minutes)..."

    # Wait for rollback to complete
    AWS_PROFILE=admin@meneely-dev aws cloudformation wait stack-rollback-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"

    echo -e "${GREEN}✓ Rollback completed successfully${NC}"
    echo ""

    # Check final status
    FINAL_STATUS=$(AWS_PROFILE=admin@meneely-dev aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)

    echo "Final stack status: $FINAL_STATUS"
    echo ""

elif [ "$STACK_STATUS" = "UPDATE_ROLLBACK_IN_PROGRESS" ]; then
    echo -e "${YELLOW}Stack is already rolling back. Waiting for completion...${NC}"
    echo ""

    AWS_PROFILE=admin@meneely-dev aws cloudformation wait stack-rollback-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"

    echo -e "${GREEN}✓ Rollback completed successfully${NC}"
    echo ""

elif [ "$STACK_STATUS" = "UPDATE_ROLLBACK_COMPLETE" ]; then
    echo -e "${GREEN}✓ Stack is already in UPDATE_ROLLBACK_COMPLETE state${NC}"
    echo "The stack is ready for a new deployment."
    echo ""

elif [ "$STACK_STATUS" = "CREATE_COMPLETE" ] || [ "$STACK_STATUS" = "UPDATE_COMPLETE" ]; then
    echo -e "${GREEN}✓ Stack is in a healthy state: $STACK_STATUS${NC}"
    echo "No rollback needed."
    echo ""

else
    echo -e "${RED}Error: Stack is in unexpected state: $STACK_STATUS${NC}"
    echo "Please check the CloudFormation console for details."
    exit 1
fi

echo -e "${GREEN}=== Stack Recovery Complete ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Apply the IAM policy fix: ./iam/apply-policy-update.sh"
echo "  2. Deploy again: sam deploy --config-env dev"
echo "  3. Or push to GitHub to trigger the workflow"
echo ""
