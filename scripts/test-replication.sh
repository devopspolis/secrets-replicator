#!/bin/bash

# Test script for secrets-replicator functionality
# Tests basic replication from us-west-2 to us-east-1

set -e

# Configuration
SOURCE_REGION="us-west-2"
DEST_REGION="us-east-1"
TEST_SECRET_PREFIX="test-replication"
TIMESTAMP=$(date +%s)
TEST_SECRET_NAME="${TEST_SECRET_PREFIX}-${TIMESTAMP}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "Secrets Replicator Test Script"
echo "======================================"
echo ""
echo "Configuration:"
echo "  Source Region: $SOURCE_REGION"
echo "  Destination Region: $DEST_REGION"
echo "  Test Secret: $TEST_SECRET_NAME"
echo ""

# Function to wait for secret to exist in destination
wait_for_secret() {
    local region=$1
    local secret_name=$2
    local max_attempts=30
    local attempt=1

    echo -n "Waiting for secret in $region"
    while [ $attempt -le $max_attempts ]; do
        if aws secretsmanager describe-secret \
            --secret-id "$secret_name" \
            --region "$region" \
            &>/dev/null; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        ((attempt++))
    done
    echo -e " ${RED}✗${NC}"
    return 1
}

# Function to cleanup test secrets
cleanup() {
    echo ""
    echo "Cleaning up test secrets..."

    # Delete from source
    if aws secretsmanager describe-secret \
        --secret-id "$TEST_SECRET_NAME" \
        --region "$SOURCE_REGION" \
        &>/dev/null; then
        echo -n "  Deleting from $SOURCE_REGION"
        aws secretsmanager delete-secret \
            --secret-id "$TEST_SECRET_NAME" \
            --region "$SOURCE_REGION" \
            --force-delete-without-recovery \
            &>/dev/null
        echo -e " ${GREEN}✓${NC}"
    fi

    # Delete from destination
    if aws secretsmanager describe-secret \
        --secret-id "$TEST_SECRET_NAME" \
        --region "$DEST_REGION" \
        &>/dev/null; then
        echo -n "  Deleting from $DEST_REGION"
        aws secretsmanager delete-secret \
            --secret-id "$TEST_SECRET_NAME" \
            --region "$DEST_REGION" \
            --force-delete-without-recovery \
            &>/dev/null
        echo -e " ${GREEN}✓${NC}"
    fi
}

# Register cleanup on exit
trap cleanup EXIT

echo "======================================"
echo "Test 1: Basic Replication (No Transform)"
echo "======================================"
echo ""

# Create test secret in source region
echo "Step 1: Creating secret in source region ($SOURCE_REGION)..."
SECRET_VALUE='{"database":"prod-db-1","host":"db.us-west-2.example.com","port":5432}'
aws secretsmanager create-secret \
    --name "$TEST_SECRET_NAME" \
    --description "Test secret for replication" \
    --secret-string "$SECRET_VALUE" \
    --region "$SOURCE_REGION" \
    --tags Key=Purpose,Value=Testing Key=AutoDelete,Value=true \
    > /dev/null

echo -e "${GREEN}✓${NC} Secret created in $SOURCE_REGION"

# Wait for EventBridge/Lambda to trigger (CloudTrail can take up to 15 minutes)
echo ""
echo "Step 2: Waiting for replication to complete..."
echo -e "${YELLOW}Note: CloudTrail events may take 5-15 minutes to appear${NC}"
echo -e "${YELLOW}EventBridge is listening for PutSecretValue/UpdateSecret events${NC}"

if wait_for_secret "$DEST_REGION" "$TEST_SECRET_NAME"; then
    # Verify replicated secret value
    echo ""
    echo "Step 3: Verifying replicated secret value..."
    DEST_SECRET_VALUE=$(aws secretsmanager get-secret-value \
        --secret-id "$TEST_SECRET_NAME" \
        --region "$DEST_REGION" \
        --query 'SecretString' \
        --output text)

    if [ "$SECRET_VALUE" == "$DEST_SECRET_VALUE" ]; then
        echo -e "${GREEN}✓${NC} Secret value matches (no transformation applied)"
        echo ""
        echo "Source secret:"
        echo "$SECRET_VALUE" | jq .
        echo ""
        echo "Destination secret:"
        echo "$DEST_SECRET_VALUE" | jq .
        echo ""
        echo -e "${GREEN}======================================"
        echo "Test 1: PASSED"
        echo -e "======================================${NC}"
    else
        echo -e "${RED}✗${NC} Secret value mismatch"
        echo "Expected: $SECRET_VALUE"
        echo "Got: $DEST_SECRET_VALUE"
        echo ""
        echo -e "${RED}======================================"
        echo "Test 1: FAILED"
        echo -e "======================================${NC}"
        exit 1
    fi
else
    echo ""
    echo -e "${RED}✗${NC} Replication failed - secret not found in destination"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check Lambda logs:"
    echo "   aws logs tail /aws/lambda/secrets-replicator --region $SOURCE_REGION --follow"
    echo ""
    echo "2. Check CloudWatch metrics:"
    echo "   aws cloudwatch get-metric-statistics --region $SOURCE_REGION \\"
    echo "     --namespace SecretsReplicator --metric-name ReplicationSuccess \\"
    echo "     --start-time $(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%S) \\"
    echo "     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) --period 300 --statistics Sum"
    echo ""
    echo "3. Check EventBridge rule:"
    echo "   aws events describe-rule --region $SOURCE_REGION \\"
    echo "     --name secrets-replicator-dev-SecretReplicatorFunctionSecr-*"
    echo ""
    echo -e "${RED}======================================"
    echo "Test 1: FAILED"
    echo -e "======================================${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}All tests passed!${NC}"
