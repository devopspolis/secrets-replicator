# SAR Publishing and Deployment Workflows

## Overview

This document describes the CI/CD workflows for the secrets-replicator project, following the **"build once, deploy many"** principle to ensure that what you test in QA is exactly what gets deployed to Production and published to SAR.

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Release v1.0.0                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               release-qa.yml (Build Once)                   │
│  1. sam build                                               │
│  2. sam package → S3 (secrets-replicator-builds-REGION)     │
│  3. sam deploy → QA Stack                                   │
│  4. Upload packaged template as GitHub artifact            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
            ┌────────────────────┐
            │  Test in QA        │
            └────────┬───────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│          release-prod.yml (Deploy Same Package)             │
│  1. Download packaged template from S3 (NO REBUILD)        │
│  2. sam deploy → Prod Stack                                │
│  3. sam publish → SAR (us-east-1, us-west-2)               │
│  4. Make SAR application public                            │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
            ┌────────────────────┐
            │  Consumers Deploy  │
            │  from SAR          │
            └────────────────────┘
```

## Workflows

### 1. `deploy-dev.yml` - Continuous Deployment to Dev

**Trigger:** Push to `main` branch or manual dispatch

**Purpose:** Fast iteration in development environment

**Process:**
- Builds and deploys directly to dev stack
- Uses workflow run number as build identifier
- No SAR publishing
- Tags: `Environment=dev`, `BuildNumber=123`, `GitSha=abc123`

**Command:**
```bash
# Automatic on push to main
git push origin main

# Or manual via GitHub CLI
gh workflow run deploy-dev.yml
```

### 2. `release-qa.yml` - Build Once and Deploy to QA

**Trigger:** GitHub Release published or manual dispatch

**Purpose:** Create the definitive build artifact for a version

**Process:**
1. **Build:** `sam build` (only happens once for this version)
2. **Package:** `sam package` uploads Lambda code to S3
   - Bucket: `secrets-replicator-builds-REGION`
   - Path: `releases/VERSION/packaged-qa.yaml`
3. **Store:** Uploads packaged template as GitHub artifact (90 day retention)
4. **Deploy:** Deploys to QA stack for testing
5. **Version:** Extracts semantic version from git tag (strips 'v' prefix)

**Package Storage:**
- S3: `s3://secrets-replicator-builds-us-west-2/releases/1.0.0/`
- GitHub Artifacts: `packaged-template-1.0.0`

**Command:**
```bash
# Create GitHub Release (triggers automatically)
gh release create v1.0.0 \
  --title "Release v1.0.0" \
  --notes "Release notes here"

# Or manual trigger
gh workflow run release-qa.yml --field version=1.0.0
```

**Example Output:**
```
Version: 1.0.0
Environment: QA
Build Package: s3://secrets-replicator-builds-us-west-2/releases/1.0.0/
Artifact: packaged-template-1.0.0
```

### 3. `release-prod.yml` - Deploy Same Package to Prod

**Trigger:** Manual dispatch only

**Purpose:** Deploy the exact QA-tested package to Production and SAR

**Process:**
1. **Download:** Fetches the packaged template from S3 (NO REBUILD)
   - Uses the exact package that was deployed and tested in QA
2. **Deploy Prod:** Deploys to production stack
3. **Publish SAR:** (Optional) Publishes to SAR in multiple regions
4. **Make Public:** Makes SAR application publicly available

**Critical:** This workflow downloads the pre-built package from QA. If you specify a version that wasn't built in QA, the workflow will fail.

**Command:**
```bash
# Promote version 1.0.0 from QA to Prod and publish to SAR
gh workflow run release-prod.yml \
  --field version=1.0.0 \
  --field publish_to_sar=true \
  --field sar_regions=us-east-1,us-west-2

# Or just deploy to Prod without SAR publishing
gh workflow run release-prod.yml \
  --field version=1.0.0 \
  --field publish_to_sar=false
```

**Jobs:**
- `deploy-prod`: Deploys to production stack (always runs)
- `publish-to-sar`: Publishes to SAR and makes public (only if `publish_to_sar=true`)

### 4. `publish-sar.yml` - Legacy Standalone Publishing

**Trigger:** GitHub Release published or manual dispatch

**Purpose:** Direct SAR publishing (builds from scratch)

**Note:** This workflow is kept for backward compatibility but **does not follow** the "build once, deploy many" principle. Use `release-qa.yml` → `release-prod.yml` instead for production releases.

## Version Management Strategy

### Development (No Version)
- Uses workflow run number: `BuildNumber=123`
- No SAR publishing
- Direct deployment via `deploy-dev.yml`

### QA/Prod (Semantic Versioning)
- GitHub Release creates git tag (e.g., `v1.0.0`)
- `release-qa.yml` extracts version (strips 'v' prefix → `1.0.0`)
- Same version used for QA, Prod, and SAR

### Version in template.yaml
- Keep a development version (e.g., `0.1.2`)
- Gets overridden by `--version` parameter in workflows
- Not committed with each release

## Build Once, Deploy Many

### Why It Matters

**Problem:** Rebuilding for production might produce a different artifact than QA:
- Different dependency versions
- Different timestamps
- Different build environment
- Different Lambda layer hashes

**Solution:** Build once, store in S3, deploy the same artifact multiple times:

```
Build v1.0.0 → Store in S3 → Deploy to QA → Test → Deploy to Prod (same package)
```

### How It Works

1. **QA Build:**
   ```bash
   sam build                          # Build Lambda code
   sam package --s3-bucket builds    # Upload to S3
   # Lambda code: s3://builds/releases/1.0.0/abc123.zip
   # Template: s3://builds/releases/1.0.0/packaged-qa.yaml
   ```

2. **Prod Deploy:**
   ```bash
   aws s3 cp s3://builds/releases/1.0.0/packaged-qa.yaml .
   sam deploy --template-file packaged-qa.yaml
   # Uses the SAME Lambda zip: s3://builds/releases/1.0.0/abc123.zip
   ```

3. **SAR Publish:**
   ```bash
   # Uses the same packaged-qa.yaml with S3 references
   sam publish --template packaged-qa.yaml
   # Consumers get the same Lambda code that was tested in QA
   ```

## S3 Buckets

### Build Artifacts Bucket
- **Name:** `secrets-replicator-builds-REGION`
- **Purpose:** Store packaged templates and Lambda code
- **Lifecycle:** Keep for 90 days or longer
- **Structure:**
  ```
  secrets-replicator-builds-us-west-2/
  └── releases/
      ├── 1.0.0/
      │   ├── packaged-qa.yaml
      │   ├── abc123.zip (Lambda code)
      │   └── ...
      └── 1.0.1/
          ├── packaged-qa.yaml
          └── ...
  ```

### SAR Documentation Buckets
- **Name:** `secrets-replicator-sar-REGION`
- **Purpose:** Store README.md and LICENSE for SAR
- **Regions:** One bucket per SAR publishing region
- **Access:** Public read via bucket policy (SAR service + consumers)

## Complete Release Process

### Step 1: Create GitHub Release (Triggers QA Build)

```bash
# Create release with git tag
gh release create v1.0.0 \
  --title "Release v1.0.0" \
  --notes "
## Features
- Feature 1
- Feature 2

## Bug Fixes
- Fix 1
- Fix 2
"

# This automatically triggers release-qa.yml
```

### Step 2: Monitor QA Deployment

```bash
# Watch the workflow
gh run watch

# Or view in browser
gh run view --web
```

**Verify:**
- ✅ Build succeeds
- ✅ Package uploaded to S3
- ✅ QA deployment succeeds
- ✅ Artifact uploaded to GitHub

### Step 3: Test in QA Environment

```bash
# Get QA stack outputs
aws cloudformation describe-stacks \
  --stack-name secrets-replicator-qa \
  --query 'Stacks[0].Outputs'

# Test the deployed function
# ... your testing process ...
```

### Step 4: Promote to Production

```bash
# Deploy to Prod and publish to SAR
gh workflow run release-prod.yml \
  --field version=1.0.0 \
  --field publish_to_sar=true \
  --field sar_regions=us-east-1,us-west-2

# Monitor the deployment
gh run watch
```

**Verify:**
- ✅ Same package downloaded from S3
- ✅ Prod deployment succeeds
- ✅ SAR publishing succeeds in all regions
- ✅ Application made public

### Step 5: Verify SAR Publication

```bash
# Check SAR application
aws serverlessrepo get-application \
  --application-id arn:aws:serverlessrepo:us-east-1:ACCOUNT_ID:applications/secrets-replicator \
  --region us-east-1

# Verify version
aws serverlessrepo list-application-versions \
  --application-id arn:aws:serverlessrepo:us-east-1:ACCOUNT_ID:applications/secrets-replicator \
  --region us-east-1 \
  --query 'Versions[?SemanticVersion==`1.0.0`]'
```

## Troubleshooting

### Error: Packaged template not found in S3

**Cause:** Version not built in QA, or wrong version number

**Solution:**
```bash
# List available versions
aws s3 ls s3://secrets-replicator-builds-us-west-2/releases/

# Re-run QA build for the correct version
gh workflow run release-qa.yml --field version=1.0.0
```

### Error: SAR publish fails with "Version already exists"

**Cause:** Version already published to SAR

**Solution:**
- SAR versions are immutable
- Bump version and release again
- Or use `aws serverlessrepo update-application` to update metadata

### Error: README not displaying in SAR

**Cause:** SAR caching delay or bucket permissions

**Solution:**
```bash
# Verify README uploaded to S3
aws s3 ls s3://secrets-replicator-sar-us-east-1/README.md

# Check bucket policy allows SAR service
aws s3api get-bucket-policy --bucket secrets-replicator-sar-us-east-1

# Wait a few minutes for SAR cache to refresh
```

## Best Practices

1. **Always test in QA before Prod:**
   - Never skip QA deployment
   - Run your test suite against QA stack
   - Verify monitoring and alarms

2. **Use semantic versioning:**
   - `MAJOR.MINOR.PATCH` format
   - Bump MAJOR for breaking changes
   - Bump MINOR for new features
   - Bump PATCH for bug fixes

3. **Keep version history:**
   - GitHub Releases serve as changelog
   - S3 packages retained for 90 days
   - CloudFormation retains stack history

4. **Monitor deployments:**
   - Watch GitHub Actions runs
   - Check CloudWatch Logs
   - Verify CloudFormation events

5. **Document release notes:**
   - Include features, fixes, and breaking changes
   - Reference issue numbers
   - Note any special deployment instructions

## Migration from Old Workflow

If you previously used `publish-sar.yml`:

**Old approach (rebuild every time):**
```bash
gh release create v1.0.0
# publish-sar.yml: sam build → sam publish
```

**New approach (build once):**
```bash
# Step 1: Build and deploy to QA
gh release create v1.0.0
# release-qa.yml: sam build → sam package → sam deploy (QA)

# Step 2: Test in QA
# ... testing ...

# Step 3: Promote to Prod using same package
gh workflow run release-prod.yml --field version=1.0.0
# release-prod.yml: download from S3 → sam deploy (Prod) → sam publish
```

## References

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [AWS SAR Publishing Guide](https://docs.aws.amazon.com/serverlessrepo/latest/devguide/serverlessrepo-how-to-publish.html)
- [GitHub Actions Workflows](https://docs.github.com/en/actions)
