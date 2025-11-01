# Example Sedfile - Basic Replacements
# Simple find/replace patterns for common transformation scenarios

# Replace development environment with production
s/dev\.example\.com/prod.example.com/g

# Replace HTTP with HTTPS
s/http:/https:/g

# Replace database host
s/db-dev-01/db-prod-01/g

# Replace API endpoints
s/api\.dev\.internal/api.prod.internal/g

# Replace S3 bucket names
s/my-dev-bucket/my-prod-bucket/g

# Replace port numbers
s/:3000/:8080/g

# Comments are supported (lines starting with #)
# Empty lines are ignored

# Case-insensitive replacement (using /i flag)
s/development/production/gi

# Replace secret ARN region
s/us-east-1/us-west-2/g
