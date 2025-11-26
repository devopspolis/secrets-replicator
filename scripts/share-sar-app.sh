#!/bin/bash
set -e

# Share SAR application with specific AWS accounts across multiple regions
# Usage: ./scripts/share-sar-app.sh ACCOUNT_ID_1 ACCOUNT_ID_2 ... [--regions us-east-1,us-west-2]

if [ $# -eq 0 ]; then
  echo "Usage: $0 ACCOUNT_ID_1 [ACCOUNT_ID_2 ...] [--regions REGION_1,REGION_2]"
  echo ""
  echo "Examples:"
  echo "  # Share with one account in us-east-1 and us-west-2"
  echo "  $0 123456789012 --regions us-east-1,us-west-2"
  echo ""
  echo "  # Share with multiple accounts in default regions (us-west-2, us-east-1)"
  echo "  $0 123456789012 234567890123"
  echo ""
  echo "  # Make public in all regions"
  echo "  $0 --public --regions us-east-1,us-west-2,eu-west-1"
  exit 1
fi

# Parse arguments
ACCOUNT_IDS=()
REGIONS="us-west-2,us-east-1"  # Default regions
PUBLIC_MODE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --regions)
      REGIONS="$2"
      shift 2
      ;;
    --public)
      PUBLIC_MODE=true
      shift
      ;;
    *)
      ACCOUNT_IDS+=("$1")
      shift
      ;;
  esac
done

# Get current account
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Convert comma-separated regions to array
IFS=',' read -ra REGION_ARRAY <<< "$REGIONS"

echo "=========================================="
echo "SAR Application Sharing"
echo "=========================================="
echo "Source Account: ${ACCOUNT_ID}"
echo "Regions: ${REGION_ARRAY[@]}"

if [ "$PUBLIC_MODE" = true ]; then
  echo "Mode: PUBLIC (anyone can deploy)"
  PRINCIPALS="*"
else
  echo "Target Accounts: ${ACCOUNT_IDS[@]}"
  # Join account IDs with commas
  PRINCIPALS=$(IFS=,; echo "${ACCOUNT_IDS[*]}")
fi
echo ""

for REGION in "${REGION_ARRAY[@]}"; do
  echo "=========================================="
  echo "Sharing in ${REGION}..."
  echo "=========================================="

  APP_ID="arn:aws:serverlessrepo:${REGION}:${ACCOUNT_ID}:applications/secrets-replicator"

  # Check if application exists in this region
  if ! aws serverlessrepo get-application \
      --application-id "${APP_ID}" \
      --region ${REGION} &>/dev/null; then
    echo "⚠️  Application not found in ${REGION}"
    echo "   Run: ./scripts/publish-multi-region.sh ${REGION}"
    echo ""
    continue
  fi

  # Set sharing policy
  echo "Setting policy: Principals=${PRINCIPALS}, Actions=Deploy"

  aws serverlessrepo put-application-policy \
    --application-id "${APP_ID}" \
    --statements Principals="${PRINCIPALS}",Actions=Deploy \
    --region ${REGION}

  echo "✅ Shared in ${REGION}"
  echo "   Application: ${APP_ID}"

  if [ "$PUBLIC_MODE" = true ]; then
    echo "   Public URL: https://console.aws.amazon.com/serverlessrepo/home?region=${REGION}#/available-applications"
  else
    echo "   Shared Accounts: ${PRINCIPALS}"
  fi
  echo ""
done

echo "=========================================="
echo "✅ Sharing complete!"
echo "=========================================="
echo ""

if [ "$PUBLIC_MODE" = false ]; then
  echo "Target accounts can now deploy from SAR:"
  for REGION in "${REGION_ARRAY[@]}"; do
    echo ""
    echo "# In target account, from ${REGION}:"
    echo "aws serverlessrepo get-application \\"
    echo "  --application-id arn:aws:serverlessrepo:${REGION}:${ACCOUNT_ID}:applications/secrets-replicator \\"
    echo "  --region ${REGION}"
  done
  echo ""
  echo "Or via console (target account must select correct region):"
  for REGION in "${REGION_ARRAY[@]}"; do
    echo "  ${REGION}: https://${REGION}.console.aws.amazon.com/serverlessrepo/home?region=${REGION}#/available-applications"
  done
fi
