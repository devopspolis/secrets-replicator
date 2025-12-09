#!/bin/bash
#
# Deploy script for Secrets Replicator
#
# Usage:
#   ./scripts/deploy.sh [environment] [options]
#
# Environments:
#   default   - Deploy with default settings
#   dev       - Deploy to development environment
#   qa   - Deploy to qa environment
#   prod      - Deploy to production environment
#
# Options:
#   --guided  - Run in guided mode with prompts
#   --validate-only - Only validate the template
#   --no-confirm - Skip changeset confirmation (auto-approve)
#
# Examples:
#   ./scripts/deploy.sh dev
#   ./scripts/deploy.sh prod --no-confirm
#   ./scripts/deploy.sh --guided
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="default"
GUIDED=false
VALIDATE_ONLY=false
NO_CONFIRM=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    dev|qa|prod)
      ENVIRONMENT=$1
      shift
      ;;
    --guided)
      GUIDED=true
      shift
      ;;
    --validate-only)
      VALIDATE_ONLY=true
      shift
      ;;
    --no-confirm)
      NO_CONFIRM=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [environment] [options]"
      echo ""
      echo "Environments: default, dev, qa, prod"
      echo "Options:"
      echo "  --guided         Run in guided mode"
      echo "  --validate-only  Only validate template"
      echo "  --no-confirm     Skip changeset confirmation"
      echo "  --help           Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

echo -e "${GREEN}=== Secrets Replicator Deployment ===${NC}"
echo ""

# Check for required tools
echo "Checking for required tools..."
if ! command -v sam &> /dev/null; then
    echo -e "${RED}Error: AWS SAM CLI is not installed${NC}"
    echo "Install from: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All required tools found${NC}"
echo ""

# Validate template
echo "Validating SAM template..."
if ! sam validate --lint; then
    echo -e "${RED}Template validation failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Template is valid${NC}"
echo ""

if [ "$VALIDATE_ONLY" = true ]; then
    echo "Validation complete (--validate-only specified)"
    exit 0
fi

# Build Lambda package
echo "Building Lambda function..."
if ! sam build --cached; then
    echo -e "${RED}Build failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Deploy
echo "Deploying to ${ENVIRONMENT} environment..."

DEPLOY_CMD="sam deploy"

if [ "$ENVIRONMENT" != "default" ]; then
    DEPLOY_CMD="$DEPLOY_CMD --config-env $ENVIRONMENT"
fi

if [ "$GUIDED" = true ]; then
    DEPLOY_CMD="$DEPLOY_CMD --guided"
fi

if [ "$NO_CONFIRM" = true ]; then
    # Add --no-confirm-changeset flag
    DEPLOY_CMD="$DEPLOY_CMD --no-confirm-changeset"
fi

echo "Running: $DEPLOY_CMD"
echo ""

if ! eval $DEPLOY_CMD; then
    echo -e "${RED}Deployment failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo ""

# Get stack outputs
STACK_NAME=$(sam list stack-outputs --output json 2>/dev/null | jq -r '.[] | .OutputKey' | head -1 | sed 's/-FunctionArn//' || echo "secrets-replicator-$ENVIRONMENT")

if [ "$ENVIRONMENT" != "default" ]; then
    STACK_NAME="secrets-replicator-$ENVIRONMENT"
else
    STACK_NAME="secrets-replicator"
fi

echo "Stack outputs:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs' \
    --output table 2>/dev/null || echo "Could not retrieve stack outputs"

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Subscribe to SNS topic for alerts (check outputs for topic ARN)"
echo "2. Create a test secret in source region to trigger replication"
echo "3. Monitor CloudWatch Logs for Lambda function execution"
echo "4. Check CloudWatch Metrics for replication metrics"
echo ""
echo -e "${GREEN}Deployment successful!${NC}"
