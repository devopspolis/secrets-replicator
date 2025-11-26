#!/bin/bash
set -e

# Multi-region SAR publishing script
# Usage: ./scripts/publish-multi-region.sh [regions...] [--no-container]
# Example: ./scripts/publish-multi-region.sh us-east-1 us-west-2 eu-west-1
# Example: ./scripts/publish-multi-region.sh us-east-1 --no-container

# Parse arguments
USE_CONTAINER=true
REGION_ARGS=()

for arg in "$@"; do
  if [ "$arg" = "--no-container" ]; then
    USE_CONTAINER=false
  else
    REGION_ARGS+=("$arg")
  fi
done

# Default regions if none specified
if [ ${#REGION_ARGS[@]} -eq 0 ]; then
  REGIONS="us-west-2 us-east-1"
else
  REGIONS="${REGION_ARGS[@]}"
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_PREFIX="secrets-replicator-sar"

echo "=========================================="
echo "Multi-Region SAR Publishing"
echo "=========================================="
echo "Account ID: ${ACCOUNT_ID}"
echo "Regions: ${REGIONS}"
echo "Use Container: ${USE_CONTAINER}"
echo ""

# Build once (reuse for all regions)
echo "Building SAM application..."
if [ "$USE_CONTAINER" = true ]; then
  sam build --use-container
else
  sam build
fi

for REGION in $REGIONS; do
  echo ""
  echo "=========================================="
  echo "Publishing to ${REGION}..."
  echo "=========================================="

  BUCKET_NAME="${BUCKET_PREFIX}-${ACCOUNT_ID}-${REGION}"

  # Create S3 bucket if it doesn't exist
  if ! aws s3 ls "s3://${BUCKET_NAME}" --region ${REGION} 2>/dev/null; then
    echo "Creating S3 bucket: ${BUCKET_NAME}"

    if [ "${REGION}" = "us-east-1" ]; then
      # us-east-1 doesn't support LocationConstraint
      aws s3 mb "s3://${BUCKET_NAME}" --region ${REGION}
    else
      aws s3api create-bucket \
        --bucket "${BUCKET_NAME}" \
        --region ${REGION} \
        --create-bucket-configuration LocationConstraint=${REGION}
    fi

    # Enable versioning
    aws s3api put-bucket-versioning \
      --bucket "${BUCKET_NAME}" \
      --versioning-configuration Status=Enabled \
      --region ${REGION}
  fi

  # Set bucket policy for SAR access
  echo "Setting bucket policy for SAR access..."
  aws s3api put-bucket-policy \
    --bucket "${BUCKET_NAME}" \
    --policy "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {
          \"Effect\": \"Allow\",
          \"Principal\": {
            \"Service\": \"serverlessrepo.amazonaws.com\"
          },
          \"Action\": \"s3:GetObject\",
          \"Resource\": \"arn:aws:s3:::${BUCKET_NAME}/*\"
        }
      ]
    }" \
    --region ${REGION}

  # Publish to SAR (sam publish handles packaging internally)
  echo "Publishing to SAR in ${REGION}..."
  echo "Note: sam publish will upload README.md and LICENSE from project root"

  OUTPUT=$(sam publish \
    --template .aws-sam/build/template.yaml \
    --region ${REGION} \
    2>&1 || true)

  echo "$OUTPUT"

  # Extract application ARN
  APP_ARN=$(echo "$OUTPUT" | grep -o "arn:aws:serverlessrepo:${REGION}:[^:]*:applications/secrets-replicator" || echo "")

  if [ -n "$APP_ARN" ]; then
    echo "✅ Published to ${REGION}"
    echo "   Application ARN: ${APP_ARN}"
    echo "   Console: https://console.aws.amazon.com/serverlessrepo/home?region=${REGION}#/published-applications/${APP_ARN}"
  else
    echo "⚠️  Publish may have failed or application already exists"
  fi
done

echo ""
echo "=========================================="
echo "✅ Multi-region publishing complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Share applications with specific accounts:"
echo ""
for REGION in $REGIONS; do
  echo "   # ${REGION}"
  echo "   aws serverlessrepo put-application-policy \\"
  echo "     --application-id arn:aws:serverlessrepo:${REGION}:${ACCOUNT_ID}:applications/secrets-replicator \\"
  echo "     --statements Principals='ACCOUNT_ID_1,ACCOUNT_ID_2',Actions=Deploy \\"
  echo "     --region ${REGION}"
  echo ""
done
echo "2. Target accounts can deploy from their preferred region"
