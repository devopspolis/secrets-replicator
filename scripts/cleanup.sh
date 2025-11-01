#!/bin/bash
#
# Cleanup script for Secrets Replicator
#
# Deletes the CloudFormation stack and associated resources
#
# Usage:
#   ./scripts/cleanup.sh [environment] [options]
#
# Environments:
#   default   - Delete default stack
#   dev       - Delete development stack
#   staging   - Delete staging stack
#   prod      - Delete production stack
#
# Options:
#   --yes     - Skip confirmation prompt
#   --keep-logs - Keep CloudWatch log groups
#
# Examples:
#   ./scripts/cleanup.sh dev
#   ./scripts/cleanup.sh prod --yes
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="default"
AUTO_CONFIRM=false
KEEP_LOGS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    dev|staging|prod)
      ENVIRONMENT=$1
      shift
      ;;
    --yes|-y)
      AUTO_CONFIRM=true
      shift
      ;;
    --keep-logs)
      KEEP_LOGS=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [environment] [options]"
      echo ""
      echo "Environments: default, dev, staging, prod"
      echo "Options:"
      echo "  --yes, -y    Skip confirmation prompt"
      echo "  --keep-logs  Keep CloudWatch log groups"
      echo "  --help       Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Determine stack name
if [ "$ENVIRONMENT" != "default" ]; then
    STACK_NAME="secrets-replicator-$ENVIRONMENT"
else
    STACK_NAME="secrets-replicator"
fi

echo -e "${YELLOW}=== Secrets Replicator Cleanup ===${NC}"
echo ""
echo "Stack to delete: $STACK_NAME"
echo ""

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" &>/dev/null; then
    echo -e "${YELLOW}Stack '$STACK_NAME' does not exist${NC}"
    exit 0
fi

# Show stack resources
echo "Current stack resources:"
aws cloudformation list-stack-resources \
    --stack-name "$STACK_NAME" \
    --query 'StackResourceSummaries[*].[ResourceType,LogicalResourceId,ResourceStatus]' \
    --output table

echo ""

# Confirmation prompt
if [ "$AUTO_CONFIRM" = false ]; then
    echo -e "${RED}WARNING: This will permanently delete the stack and all associated resources!${NC}"
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Cleanup cancelled"
        exit 0
    fi
fi

echo ""
echo "Deleting CloudFormation stack..."

# Empty and delete SQS queue first (if it has messages)
DLQ_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`DeadLetterQueueUrl`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -n "$DLQ_URL" ]; then
    echo "Purging Dead Letter Queue messages..."
    aws sqs purge-queue --queue-url "$DLQ_URL" 2>/dev/null || true
fi

# Delete stack
if ! aws cloudformation delete-stack --stack-name "$STACK_NAME"; then
    echo -e "${RED}Failed to initiate stack deletion${NC}"
    exit 1
fi

echo "Waiting for stack deletion to complete..."
if ! aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"; then
    echo -e "${RED}Stack deletion failed or timed out${NC}"
    echo "Check AWS Console for details"
    exit 1
fi

echo -e "${GREEN}✓ Stack deleted successfully${NC}"
echo ""

# Delete CloudWatch log groups (if not keeping)
if [ "$KEEP_LOGS" = false ]; then
    echo "Deleting CloudWatch log groups..."
    LOG_GROUP="/aws/lambda/${STACK_NAME}-replicator"

    if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --query 'logGroups[0]' &>/dev/null; then
        aws logs delete-log-group --log-group-name "$LOG_GROUP" 2>/dev/null || true
        echo -e "${GREEN}✓ Log groups deleted${NC}"
    else
        echo "No log groups found to delete"
    fi
else
    echo -e "${YELLOW}Keeping CloudWatch log groups (--keep-logs specified)${NC}"
fi

echo ""
echo -e "${GREEN}Cleanup complete!${NC}"
echo ""
echo "Deleted resources:"
echo "  - CloudFormation stack: $STACK_NAME"
echo "  - Lambda function"
echo "  - IAM roles and policies"
echo "  - EventBridge rule"
echo "  - SQS Dead Letter Queue"
echo "  - CloudWatch alarms"
echo "  - SNS topic"
if [ "$KEEP_LOGS" = false ]; then
    echo "  - CloudWatch log groups"
fi
echo ""
echo -e "${YELLOW}Note: Secrets in Secrets Manager are NOT deleted${NC}"
echo "You must manually delete any secrets that were created by the replicator"
