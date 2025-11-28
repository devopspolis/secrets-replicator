#!/bin/bash
set -e

# Multi-region SAR publishing script
# Usage: ./scripts/publish-multi-region.sh [regions...] [--no-container] [--version VERSION]
#
# Examples:
#   ./scripts/publish-multi-region.sh us-east-1 us-west-2
#   ./scripts/publish-multi-region.sh us-east-1 --no-container
#   ./scripts/publish-multi-region.sh us-east-1 --version 1.0.0
#   ./scripts/publish-multi-region.sh us-east-1 us-west-2 --version 1.0.0 --no-container
#
# Options:
#   --no-container     Build without Docker (uses local Python)
#   --version VERSION  Override SemanticVersion in template (default: use template.yaml value)
#                      Useful for CI/CD pipelines or publishing from git tags
#
# Prerequisites:
# - PyYAML: pip3 install --user pyyaml
# - S3 buckets: secrets-replicator-sar-<region> (created automatically)
# - FILES in bucket: LICENSE and README.md must be uploaded separately
#
# Version Management:
# - Development: Keep version in template.yaml (e.g., 0.3.0-dev)
# - Releases: Use --version flag driven by git tags (e.g., --version 1.0.0)
# - CI/CD: GitHub workflow extracts version from release tag

# Parse arguments
USE_CONTAINER=true
OVERRIDE_VERSION=""
REGION_ARGS=()

while [[ $# -gt 0 ]]; do
  case $1 in
    --no-container)
      USE_CONTAINER=false
      shift
      ;;
    --version)
      OVERRIDE_VERSION="$2"
      shift 2
      ;;
    *)
      REGION_ARGS+=("$1")
      shift
      ;;
  esac
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
if [ -n "$OVERRIDE_VERSION" ]; then
  echo "Version Override: ${OVERRIDE_VERSION}"
fi
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

  #BUCKET_NAME="${BUCKET_PREFIX}-${ACCOUNT_ID}-${REGION}"
  BUCKET_NAME="${BUCKET_PREFIX}-${REGION}"

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

  # Package first (uploads Lambda code to S3)
  echo "Packaging application for ${REGION}..."
  sam package \
    --template-file .aws-sam/build/template.yaml \
    --output-template-file "packaged-${REGION}.yaml" \
    --s3-bucket "${BUCKET_NAME}" \
    --region ${REGION}

  # Restore SAR metadata (sam package strips it)
  echo "Restoring SAR metadata to packaged template..."
  $(which python3) -c "
import yaml
import sys

# Read original template
with open('template.yaml', 'r') as f:
    original = yaml.safe_load(f)

# Read packaged template
with open('packaged-${REGION}.yaml', 'r') as f:
    packaged = yaml.safe_load(f)

# Copy Metadata section
if 'Metadata' in original:
    packaged['Metadata'] = original['Metadata']

    # Override version if specified
    override_version = '${OVERRIDE_VERSION}'
    if override_version:
        if 'AWS::ServerlessRepo::Application' in packaged['Metadata']:
            packaged['Metadata']['AWS::ServerlessRepo::Application']['SemanticVersion'] = override_version
            print(f'Version overridden to: {override_version}', file=sys.stderr)

# Write back
with open('packaged-${REGION}.yaml', 'w') as f:
    yaml.dump(packaged, f, default_flow_style=False, sort_keys=False)
" || {
    echo "Error: PyYAML not installed. Please run: pip3 install pyyaml"
    exit 1
  }

  # Publish to SAR
  echo "Publishing to SAR in ${REGION}..."
  echo "Note: README.md and LICENSE will be uploaded from project root"

  OUTPUT=$(sam publish \
    --template "packaged-${REGION}.yaml" \
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

  # Cleanup packaged template
  rm -f "packaged-${REGION}.yaml"
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
  echo "     --statements Principals='211125650454,905418247177,340671811473,202533525047,381491855141,767397962497,851725215806,179907032632',Actions=Deploy \\"
  echo "     --region ${REGION}"
  echo ""
done
echo "2. Target accounts can deploy from their preferred region"
