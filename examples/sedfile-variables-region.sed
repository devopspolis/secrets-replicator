# Example Sedfile with Variable Expansion - Adaptive Region Swapping
# Uses ${REGION} and ${SOURCE_REGION} variables for multi-destination replication
#
# This single transformation works for ANY destination region!
# Variables are expanded per-destination at runtime.
#
# Available core variables:
#   ${REGION} - Destination AWS region
#   ${SOURCE_REGION} - Source AWS region
#   ${SECRET_NAME} - Source secret name
#   ${DEST_SECRET_NAME} - Destination secret name (after name mapping)
#   ${ACCOUNT_ID} - Destination AWS account ID
#   ${SOURCE_ACCOUNT_ID} - Source AWS account ID

# AWS Region endpoints
s/${SOURCE_REGION}\.amazonaws\.com/${REGION}.amazonaws.com/g
s/\.${SOURCE_REGION}\./\.${REGION}./g

# Region-specific hostnames (abbreviated format)
# This pattern handles both source and destination abbreviations dynamically
s/-${SOURCE_REGION}-/-${REGION}-/g

# RDS endpoints
s/rds\.${SOURCE_REGION}/rds.${REGION}/g

# ElastiCache endpoints
s/cache\.${SOURCE_REGION}/cache.${REGION}/g

# S3 bucket region-specific URLs
s/s3\.${SOURCE_REGION}\.amazonaws/s3.${REGION}.amazonaws/g
s/s3-${SOURCE_REGION}\.amazonaws/s3-${REGION}.amazonaws/g

# DynamoDB endpoints
s/dynamodb\.${SOURCE_REGION}/dynamodb.${REGION}/g

# SQS queue URLs
s/sqs\.${SOURCE_REGION}\.amazonaws/sqs.${REGION}.amazonaws/g

# SNS topic ARNs
s/arn:aws:sns:${SOURCE_REGION}/arn:aws:sns:${REGION}/g

# Secrets Manager ARNs
s/arn:aws:secretsmanager:${SOURCE_REGION}/arn:aws:secretsmanager:${REGION}/g

# KMS key ARNs
s/arn:aws:kms:${SOURCE_REGION}/arn:aws:kms:${REGION}/g

# ECS cluster names (if region is included)
s/-${SOURCE_REGION}-/-${REGION}-/g

# Application-specific region identifiers
s/region=${SOURCE_REGION}/region=${REGION}/g
s/"region":"${SOURCE_REGION}"/"region":"${REGION}"/g

# Lambda function ARNs
s/arn:aws:lambda:${SOURCE_REGION}/arn:aws:lambda:${REGION}/g

# CloudWatch Logs group references
s/logs\.${SOURCE_REGION}\.amazonaws/logs.${REGION}.amazonaws/g

# Example usage with multiple destinations:
#
# Configuration secret (secrets-replicator/config/destinations):
# [
#   {"region": "us-west-2"},
#   {"region": "eu-west-1"},
#   {"region": "ap-south-1"}
# ]
#
# This single sedfile will correctly transform:
# - us-east-1 → us-west-2 (for first destination)
# - us-east-1 → eu-west-1 (for second destination)
# - us-east-1 → ap-south-1 (for third destination)
