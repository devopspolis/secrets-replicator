# AWS Serverless Application Repository Publishing Guide

## Prerequisites

- [x] SAM CLI installed and configured
- [x] AWS account with SAR publishing permissions
- [x] S3 bucket for packaged artifacts (in us-east-1)
- [x] All SAR metadata in template.yaml
- [x] Comprehensive README.md
- [x] LICENSE file (MIT)

## Publishing Steps

### 1. Create S3 Bucket (if needed)

```bash
# Create bucket in us-west-2 (primary region for private testing)
aws s3 mb s3://secrets-replicator-sar-packages --region us-west-2

# Enable versioning (recommended)
aws s3api put-bucket-versioning \
  --bucket secrets-replicator-sar-packages \
  --versioning-configuration Status=Enabled
```

### 2. Package Application

```bash
# Build Lambda function
sam build --use-container

# Package with all artifacts (using us-west-2 for private testing)
sam package \
  --template-file .aws-sam/build/template.yaml \
  --output-template-file packaged.yaml \
  --s3-bucket secrets-replicator-sar-packages \
  --region us-west-2
```

### 3. Publish to SAR (Private by Default)

```bash
# First time publish (PRIVATE - only visible to your account)
sam publish \
  --template packaged.yaml \
  --region us-west-2

# The output will show the application ARN:
# Created new application with the following metadata:
# {
#   "ApplicationId": "arn:aws:serverlessrepo:us-west-2:123456789012:applications/secrets-replicator",
#   "CreationTime": "...",
#   "Version": {
#     "ApplicationId": "arn:aws:serverlessrepo:us-west-2:123456789012:applications/secrets-replicator",
#     "SemanticVersion": "0.1.0"
#   }
# }
```

**Important**: Your application is **PRIVATE** by default. Only you can see and deploy it until you explicitly make it public.

### 4. Test Private Deployment from SAR

**Option A: SAR Console (Easiest)**
1. Go to [AWS SAR Console](https://console.aws.amazon.com/serverlessrepo)
2. Click "Available applications" → "Private applications" tab
3. Find "secrets-replicator"
4. Click "Deploy" and test the deployment experience

**Option B: CLI Deployment**
```bash
# Deploy from your private SAR application
sam deploy \
  --stack-name secrets-replicator-test \
  --capabilities CAPABILITY_IAM \
  --region us-west-2 \
  --guided
```

**Option C: Share with Specific Test Accounts**
```bash
# Grant permission to specific AWS accounts for testing
aws serverlessrepo put-application-policy \
  --application-id arn:aws:serverlessrepo:us-west-2:YOUR_ACCOUNT:applications/secrets-replicator \
  --statements Principals=123456789012,Actions=Deploy \
  --region us-west-2
```

### 5. Make Application Public (When Ready)

**Via Console (Recommended)**:
1. Go to [SAR Console](https://console.aws.amazon.com/serverlessrepo) → "My Applications"
2. Click "secrets-replicator"
3. Click "Sharing" tab
4. Click "Make application public"
5. Review and confirm

**Via CLI**:
```bash
aws serverlessrepo put-application-policy \
  --application-id arn:aws:serverlessrepo:us-west-2:YOUR_ACCOUNT:applications/secrets-replicator \
  --statements Principals=*,Actions=Deploy \
  --region us-west-2
```

### 6. Publish to Additional Regions (Public Release)

Once thoroughly tested and made public in us-west-2, publish to other regions for wider adoption:

```bash
# Package for us-east-1 (largest user base)
sam package \
  --template-file .aws-sam/build/template.yaml \
  --output-template-file packaged.yaml \
  --s3-bucket secrets-replicator-sar-packages-us-east-1 \
  --region us-east-1

sam publish \
  --template packaged.yaml \
  --region us-east-1

# Repeat for other popular regions as needed (eu-west-1, ap-southeast-1, etc.)
```

### 7. Update Application Version (Future Updates)

```bash
# Update SemanticVersion in template.yaml (e.g., 0.1.0 → 0.2.0 → 1.0.0)
# Then rebuild, package, and publish again

sam build --use-container
sam package \
  --template-file .aws-sam/build/template.yaml \
  --output-template-file packaged.yaml \
  --s3-bucket secrets-replicator-sar-packages \
  --region us-west-2

sam publish \
  --template packaged.yaml \
  --region us-west-2

# If already published to multiple regions, update all:
sam publish --template packaged.yaml --region us-east-1
```

**Semantic Versioning Guide**:
- `0.1.0` - `0.9.x`: Pre-release, testing, breaking changes expected
- `1.0.0`: First stable public release
- `1.0.x`: Bug fixes (backward compatible)
- `1.x.0`: New features (backward compatible)
- `x.0.0`: Breaking changes

## Publishing Checklist

Before making the application public:

### SAM Template Validation
- [x] All required SAR metadata fields present
- [x] SemanticVersion follows SemVer (1.0.0)
- [x] Description is clear and concise
- [x] Labels/tags for discoverability
- [x] LICENSE file exists and referenced
- [x] README.md comprehensive

### Documentation Review
- [x] README has quick start guide
- [x] All parameters documented
- [x] IAM permissions documented
- [x] Example configurations provided
- [x] Troubleshooting guide complete

### Testing
- [ ] Deploy from SAR succeeds
- [ ] All examples work as documented
- [ ] Cross-region replication tested
- [ ] Cross-account replication tested
- [ ] Transformation examples tested
- [ ] CloudWatch metrics publishing
- [ ] CloudWatch alarms working

### Security
- [ ] No hardcoded secrets in code
- [ ] IAM permissions follow least privilege
- [ ] KMS encryption working
- [ ] External ID for cross-account access
- [ ] Security policy in SECURITY.md
- [ ] Vulnerability reporting process documented

### Community
- [ ] GitHub repository public
- [ ] CONTRIBUTING.md complete
- [ ] CODE_OF_CONDUCT.md present
- [ ] Issue templates created
- [ ] PR template created

## Post-Publishing

### 1. Update README.md

Update the SAR installation section:

```markdown
### Option 1: AWS Serverless Application Repository (Recommended)

1. Go to [AWS Serverless Application Repository](https://serverlessrepo.aws.amazon.com/applications/arn:aws:serverlessrepo:us-east-1:YOUR_ACCOUNT:applications/secrets-replicator)
2. Click "Deploy"
3. Configure parameters:
   - DestinationRegion: us-west-2
   - SourceSecretPattern: arn:aws:secretsmanager:us-east-1:*:secret:*
4. Review IAM permissions
5. Click "Deploy"
```

### 2. Create GitHub Release

```bash
# Create git tag
git tag -a v1.0.0 -m "Release v1.0.0 - Production ready"
git push origin v1.0.0

# Create GitHub release with release notes
gh release create v1.0.0 \
  --title "v1.0.0 - Production Ready" \
  --notes-file CHANGELOG.md
```

### 3. Announce

- [ ] AWS Community forums
- [ ] AWS Subreddit (r/aws)
- [ ] Dev.to blog post
- [ ] LinkedIn/Twitter announcement
- [ ] AWS Newsletter submission

### 4. Monitor

- [ ] SAR deployment metrics
- [ ] GitHub issues
- [ ] GitHub discussions
- [ ] CloudWatch metrics (if you deploy your own instance)

## Troubleshooting

### "Template validation failed"

Check that all required SAR metadata fields are present:
- Name
- Description
- Author
- SpdxLicenseId
- LicenseUrl
- ReadmeUrl
- HomePageUrl
- SourceCodeUrl
- SemanticVersion

### "Unable to upload artifact"

Ensure S3 bucket is in the same region as your SAR publish command (us-west-2 for private testing).

### "README not rendering"

- README must be named README.md (case-sensitive)
- Must be in repository root
- Must use valid Markdown

## Resources

- [AWS SAR Developer Guide](https://docs.aws.amazon.com/serverlessrepo/latest/devguide/what-is-serverlessrepo.html)
- [SAR Publishing Requirements](https://docs.aws.amazon.com/serverlessrepo/latest/devguide/serverlessrepo-how-to-publish.html)
- [SAM Publish Command](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-publish.html)
