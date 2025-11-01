# Example Sedfile - Region Swapping
# Transforms region-specific values when replicating across AWS regions
# Common use case: DR/multi-region deployments

# AWS Region endpoints
s/us-east-1\.amazonaws\.com/us-west-2.amazonaws.com/g
s/\.us-east-1\./\.us-west-2./g

# Region-specific hostnames
s/\.use1\./\.usw2./g
s/-use1-/-usw2-/g

# RDS endpoints
s/rds\.us-east-1/rds.us-west-2/g

# ElastiCache endpoints
s/cache\.us-east-1/cache.us-west-2/g

# S3 bucket region-specific URLs
s/s3\.us-east-1\.amazonaws/s3.us-west-2.amazonaws/g
s/s3-us-east-1\.amazonaws/s3-us-west-2.amazonaws/g

# DynamoDB endpoints
s/dynamodb\.us-east-1/dynamodb.us-west-2/g

# SQS queue URLs
s/sqs\.us-east-1\.amazonaws/sqs.us-west-2.amazonaws/g

# SNS topic ARNs
s/arn:aws:sns:us-east-1/arn:aws:sns:us-west-2/g

# Secrets Manager ARNs
s/arn:aws:secretsmanager:us-east-1/arn:aws:secretsmanager:us-west-2/g

# KMS key ARNs
s/arn:aws:kms:us-east-1/arn:aws:kms:us-west-2/g

# ECS cluster names (if region is included)
s/-us-east-1-/-us-west-2-/g

# Application-specific region identifiers
s/region=us-east-1/region=us-west-2/g
s/"region":"us-east-1"/"region":"us-west-2"/g

# Replace az suffixes (us-east-1a → us-west-2a)
s/us-east-1[a-f]/us-west-2a/g
