#!/bin/bash
#
# Setup Test Secrets for SAR Testing
#
# Creates minimal test secrets for validating Secrets Replicator functionality:
# - 1 source secret with realistic test data
# - 1 transformation secret with sed + JSON examples
# - Destination secret auto-created by Lambda (not created here)
#
# Total cost: ~$0.80/month (2 secrets)
#
# Usage:
#   ./scripts/setup-test-secrets.sh [--region us-west-2] [--dest-region us-east-1]
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
        --help)
            echo "Usage: $0 [--region REGION] [--dest-region DEST_REGION] [--prefix PREFIX]"
            echo ""
            echo "Options:"
            echo "  --region        Source AWS region (default: us-west-2)"
            echo "  --dest-region   Destination AWS region (default: us-east-1)"
            echo "  --prefix        Secret name prefix (default: sar-test)"
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
echo -e "${BLUE}Secrets Replicator - Test Setup${NC}"
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

# Create source secret
SOURCE_SECRET_NAME="${SECRET_PREFIX}-source"
echo -e "${YELLOW}Creating source secret: ${SOURCE_SECRET_NAME}${NC}"

# Realistic test data with multiple fields for transformation testing
SOURCE_VALUE=$(cat <<'EOF'
{
  "database": {
    "host": "db1.us-west-2.rds.amazonaws.com",
    "port": 5432,
    "name": "production_db",
    "region": "us-west-2"
  },
  "redis": {
    "endpoint": "redis.us-west-2.cache.amazonaws.com:6379",
    "region": "us-west-2"
  },
  "s3": {
    "bucket": "my-app-data-us-west-2",
    "region": "us-west-2"
  },
  "api": {
    "endpoint": "https://api.us-west-2.example.com/v1",
    "environment": "production"
  },
  "metadata": {
    "created_by": "secrets-replicator-test",
    "version": "1.0"
  }
}
EOF
)

# Check if secret already exists
if aws secretsmanager describe-secret \
    --secret-id "$SOURCE_SECRET_NAME" \
    --region "$SOURCE_REGION" &>/dev/null; then
    echo -e "${YELLOW}Secret already exists, updating...${NC}"
    SOURCE_ARN=$(aws secretsmanager put-secret-value \
        --secret-id "$SOURCE_SECRET_NAME" \
        --secret-string "$SOURCE_VALUE" \
        --region "$SOURCE_REGION" \
        --query ARN \
        --output text)
else
    echo -e "${YELLOW}Creating new secret...${NC}"
    SOURCE_ARN=$(aws secretsmanager create-secret \
        --name "$SOURCE_SECRET_NAME" \
        --description "Test source secret for Secrets Replicator SAR testing" \
        --secret-string "$SOURCE_VALUE" \
        --region "$SOURCE_REGION" \
        --tags "Key=Purpose,Value=Testing" "Key=ManagedBy,Value=secrets-replicator-test" \
        --query ARN \
        --output text)
fi

echo -e "${GREEN}✓ Created source secret${NC}"
echo -e "  ARN: ${SOURCE_ARN}"
echo ""

# Create transformation secret
TRANSFORM_SECRET_NAME="secrets-replicator/transformations/${SECRET_PREFIX}"
echo -e "${YELLOW}Creating transformation secret: ${TRANSFORM_SECRET_NAME}${NC}"

# Transformation rules for converting us-west-2 → us-east-1
TRANSFORM_VALUE=$(cat <<'EOF'
{
  "sed": [
    "s/us-west-2/us-east-1/g",
    "s/my-app-data-us-west-2/my-app-data-us-east-1/g"
  ],
  "json": [
    {
      "path": "$.database.region",
      "find": "us-west-2",
      "replace": "us-east-1"
    },
    {
      "path": "$.database.host",
      "find": "db1.us-west-2.rds.amazonaws.com",
      "replace": "db1.us-east-1.rds.amazonaws.com"
    },
    {
      "path": "$.redis.region",
      "find": "us-west-2",
      "replace": "us-east-1"
    },
    {
      "path": "$.redis.endpoint",
      "find": "redis.us-west-2.cache.amazonaws.com:6379",
      "replace": "redis.us-east-1.cache.amazonaws.com:6379"
    },
    {
      "path": "$.s3.region",
      "find": "us-west-2",
      "replace": "us-east-1"
    },
    {
      "path": "$.s3.bucket",
      "find": "my-app-data-us-west-2",
      "replace": "my-app-data-us-east-1"
    },
    {
      "path": "$.api.endpoint",
      "find": "https://api.us-west-2.example.com/v1",
      "replace": "https://api.us-east-1.example.com/v1"
    }
  ]
}
EOF
)

# Check if secret already exists
if aws secretsmanager describe-secret \
    --secret-id "$TRANSFORM_SECRET_NAME" \
    --region "$SOURCE_REGION" &>/dev/null; then
    echo -e "${YELLOW}Secret already exists, updating...${NC}"
    TRANSFORM_ARN=$(aws secretsmanager put-secret-value \
        --secret-id "$TRANSFORM_SECRET_NAME" \
        --secret-string "$TRANSFORM_VALUE" \
        --region "$SOURCE_REGION" \
        --query ARN \
        --output text)
else
    echo -e "${YELLOW}Creating new secret...${NC}"
    TRANSFORM_ARN=$(aws secretsmanager create-secret \
        --name "$TRANSFORM_SECRET_NAME" \
        --description "Transformation rules for Secrets Replicator testing (us-west-2 → us-east-1)" \
        --secret-string "$TRANSFORM_VALUE" \
        --region "$SOURCE_REGION" \
        --tags "Key=Purpose,Value=Testing" "Key=ManagedBy,Value=secrets-replicator-test" \
        --query ARN \
        --output text)
fi

echo -e "${GREEN}✓ Created transformation secret${NC}"
echo -e "  ARN: ${TRANSFORM_ARN}"
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Created secrets:${NC}"
echo -e "  1. Source:         ${SOURCE_SECRET_NAME}"
echo -e "  2. Transformation: ${TRANSFORM_SECRET_NAME}"
echo ""
echo -e "${YELLOW}Monthly cost:${NC} ~\$0.80 (2 secrets)"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}SAR Deployment Parameters${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Use these parameters when deploying from SAR:"
echo ""
echo -e "${GREEN}SourceSecretPattern:${NC}"
echo "  ${SOURCE_ARN}"
echo ""
echo -e "${GREEN}DestinationRegion:${NC}"
echo "  ${DEST_REGION}"
echo ""
echo -e "${GREEN}DestinationSecretName:${NC}"
echo "  ${SOURCE_SECRET_NAME}"
echo ""
echo -e "${GREEN}TransformationSecretPrefix:${NC}"
echo "  secrets-replicator/transformations/"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Testing Scenarios${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}1. Test Pass-Through (No Transformation)${NC}"
echo "   - Deploy SAR with TransformMode=auto"
echo "   - Source secret tags should NOT reference transformation secret"
echo "   - Destination should match source exactly"
echo ""
echo -e "${GREEN}2. Test Sed Transformation${NC}"
echo "   - Add tag to source secret:"
echo "     Key=secrets-replicator/transformation"
echo "     Value=${TRANSFORM_SECRET_NAME}"
echo "   - Update source secret (triggers replication)"
echo "   - Destination should have us-east-1 instead of us-west-2"
echo ""
echo -e "${GREEN}3. Test JSON Transformation${NC}"
echo "   - Same as scenario 2 (auto-detected from transformation content)"
echo "   - Verify all JSON paths are transformed correctly"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Next Steps${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "1. Package and publish to SAR:"
echo "   sam build --use-container"
echo "   sam package --s3-bucket YOUR_BUCKET --region ${SOURCE_REGION}"
echo "   sam publish --region ${SOURCE_REGION}"
echo ""
echo "2. Deploy from SAR console using parameters above"
echo ""
echo "3. Test replication by updating source secret:"
echo "   aws secretsmanager put-secret-value \\"
echo "     --secret-id ${SOURCE_SECRET_NAME} \\"
echo "     --secret-string '{\"test\": \"updated\"}' \\"
echo "     --region ${SOURCE_REGION}"
echo ""
echo "4. Check destination secret:"
echo "   aws secretsmanager get-secret-value \\"
echo "     --secret-id ${SOURCE_SECRET_NAME} \\"
echo "     --region ${DEST_REGION}"
echo ""
echo "5. Monitor CloudWatch Logs for replication activity"
echo ""
echo -e "${YELLOW}Cleanup:${NC}"
echo "   ./scripts/cleanup-test-secrets.sh --region ${SOURCE_REGION} --dest-region ${DEST_REGION}"
echo ""
