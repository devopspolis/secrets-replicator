#!/bin/bash
#
# Cleanup Test Secrets for SAR Testing
#
# Deletes all test secrets created by setup-test-secrets.sh:
# - Source secret
# - Transformation secret
# - Destination secret (if created by Lambda)
#
# This saves ~$0.80/month (2 secrets) or ~$1.20/month (3 secrets if destination was created)
#
# Usage:
#   ./scripts/cleanup-test-secrets.sh [--region us-west-2] [--dest-region us-east-1]
#   ./scripts/cleanup-test-secrets.sh --yes  # Skip confirmation prompts
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SOURCE_REGION="${AWS_REGION:-us-west-2}"
DEST_REGION="us-east-1"
SECRET_PREFIX="sar-test"
AUTO_APPROVE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            SOURCE_REGION="$2"
            shift 2
            ;;
        --dest-region)
            DEST_REGION="$2"
            shift 2
            ;;
        --prefix)
            SECRET_PREFIX="$2"
            shift 2
            ;;
        --yes|-y)
            AUTO_APPROVE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--region REGION] [--dest-region DEST_REGION] [--prefix PREFIX] [--yes]"
            echo ""
            echo "Options:"
            echo "  --region        Source AWS region (default: us-west-2)"
            echo "  --dest-region   Destination AWS region (default: us-east-1)"
            echo "  --prefix        Secret name prefix (default: sar-test)"
            echo "  --yes, -y       Auto-approve deletion (skip confirmation)"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Secrets Replicator - Test Cleanup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Source Region:      ${GREEN}${SOURCE_REGION}${NC}"
echo -e "Destination Region: ${GREEN}${DEST_REGION}${NC}"
echo -e "Secret Prefix:      ${GREEN}${SECRET_PREFIX}${NC}"
echo ""

# Verify AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI not installed${NC}"
    exit 1
fi

# Verify AWS credentials
echo -e "${YELLOW}Verifying AWS credentials...${NC}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
if [ -z "$ACCOUNT_ID" ]; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Authenticated as AWS Account: ${ACCOUNT_ID}${NC}"
echo ""

# List secrets to be deleted
SOURCE_SECRET_NAME="${SECRET_PREFIX}-source"
TRANSFORM_SECRET_NAME="secrets-replicator/transformations/${SECRET_PREFIX}"
SECRETS_TO_DELETE=()
REGIONS_TO_CHECK=("$SOURCE_REGION" "$DEST_REGION")

echo -e "${YELLOW}Scanning for test secrets...${NC}"
echo ""

for REGION in "${REGIONS_TO_CHECK[@]}"; do
    echo -e "${BLUE}Region: ${REGION}${NC}"

    # Check source secret
    if aws secretsmanager describe-secret \
        --secret-id "$SOURCE_SECRET_NAME" \
        --region "$REGION" &>/dev/null; then
        ARN=$(aws secretsmanager describe-secret \
            --secret-id "$SOURCE_SECRET_NAME" \
            --region "$REGION" \
            --query ARN \
            --output text)
        echo -e "  ${YELLOW}Found:${NC} ${SOURCE_SECRET_NAME}"
        echo -e "         ${ARN}"
        SECRETS_TO_DELETE+=("${REGION}:${SOURCE_SECRET_NAME}")
    fi

    # Check transformation secret (only in source region)
    if [ "$REGION" = "$SOURCE_REGION" ]; then
        if aws secretsmanager describe-secret \
            --secret-id "$TRANSFORM_SECRET_NAME" \
            --region "$REGION" &>/dev/null; then
            ARN=$(aws secretsmanager describe-secret \
                --secret-id "$TRANSFORM_SECRET_NAME" \
                --region "$REGION" \
                --query ARN \
                --output text)
            echo -e "  ${YELLOW}Found:${NC} ${TRANSFORM_SECRET_NAME}"
            echo -e "         ${ARN}"
            SECRETS_TO_DELETE+=("${REGION}:${TRANSFORM_SECRET_NAME}")
        fi
    fi

    echo ""
done

# Check if any secrets found
if [ ${#SECRETS_TO_DELETE[@]} -eq 0 ]; then
    echo -e "${GREEN}No test secrets found. Nothing to clean up.${NC}"
    exit 0
fi

# Show summary
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Cleanup Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Secrets to delete: ${RED}${#SECRETS_TO_DELETE[@]}${NC}"
echo ""

for SECRET_INFO in "${SECRETS_TO_DELETE[@]}"; do
    REGION="${SECRET_INFO%%:*}"
    SECRET_ID="${SECRET_INFO#*:}"
    echo -e "  • ${SECRET_ID} (${REGION})"
done

echo ""
echo -e "${YELLOW}Estimated savings:${NC} ~\$$(echo "scale=2; ${#SECRETS_TO_DELETE[@]} * 0.40" | bc)/month"
echo ""

# Confirm deletion
if [ "$AUTO_APPROVE" = false ]; then
    echo -e "${RED}⚠️  WARNING: This will PERMANENTLY delete all secrets listed above!${NC}"
    echo -e "${RED}⚠️  Secrets will be deleted WITHOUT recovery window.${NC}"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        echo -e "${YELLOW}Cleanup cancelled.${NC}"
        exit 0
    fi
fi

echo ""
echo -e "${YELLOW}Deleting secrets...${NC}"
echo ""

# Delete secrets
DELETED_COUNT=0
FAILED_COUNT=0

for SECRET_INFO in "${SECRETS_TO_DELETE[@]}"; do
    REGION="${SECRET_INFO%%:*}"
    SECRET_ID="${SECRET_INFO#*:}"

    echo -e "${YELLOW}Deleting:${NC} ${SECRET_ID} (${REGION})"

    if aws secretsmanager delete-secret \
        --secret-id "$SECRET_ID" \
        --force-delete-without-recovery \
        --region "$REGION" &>/dev/null; then
        echo -e "${GREEN}  ✓ Deleted${NC}"
        ((DELETED_COUNT++))
    else
        echo -e "${RED}  ✗ Failed${NC}"
        ((FAILED_COUNT++))
    fi
done

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Cleanup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Deleted: ${GREEN}${DELETED_COUNT}${NC} secrets"

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "Failed:  ${RED}${FAILED_COUNT}${NC} secrets"
fi

echo -e "Savings: ${GREEN}~\$$(echo "scale=2; ${DELETED_COUNT} * 0.40" | bc)/month${NC}"
echo ""

# Additional cleanup recommendations
echo -e "${YELLOW}Additional Cleanup Recommendations:${NC}"
echo ""
echo "1. Delete CloudWatch Log Groups:"
echo "   aws logs delete-log-group \\"
echo "     --log-group-name /aws/lambda/secrets-replicator \\"
echo "     --region ${SOURCE_REGION}"
echo ""
echo "2. Delete SAR application (if published):"
echo "   aws serverlessrepo delete-application \\"
echo "     --application-id arn:aws:serverlessrepo:${SOURCE_REGION}:${ACCOUNT_ID}:applications/secrets-replicator"
echo ""
echo "3. Delete CloudFormation stack (if deployed):"
echo "   aws cloudformation delete-stack \\"
echo "     --stack-name secrets-replicator \\"
echo "     --region ${SOURCE_REGION}"
echo ""
echo "4. Empty and delete S3 bucket (if created):"
echo "   aws s3 rm s3://secrets-replicator-sar-packages --recursive"
echo "   aws s3 rb s3://secrets-replicator-sar-packages"
echo ""
