# Secrets Replicator

AWS Lambda function for cross-region/cross-account AWS Secrets Manager replication with value transformation.

## Overview

This project provides an AWS Lambda function that:
- Replicates AWS Secrets Manager secrets across regions and accounts
- Applies configurable string transformations to destination values (e.g., replacing `us-east-1` with `us-west-2`)
- Fills the gap in AWS's native secret replication (which doesn't support value modification)
- Supports disaster recovery and business continuity use cases

## Key Features

- **Event-Driven**: Triggered automatically by AWS Secrets Manager updates via EventBridge
- **Flexible Transformations**: Supports sed-style regex replacements and JSON field mappings
- **Cross-Region**: Replicate secrets to any AWS region
- **Cross-Account**: Replicate secrets to different AWS accounts with proper IAM controls
- **Secure**: Never logs plaintext secrets, uses KMS encryption, least-privilege IAM policies
- **Resilient**: Automatic retries, Dead Letter Queue, CloudWatch metrics and alarms
- **Easy Deployment**: Published to AWS Serverless Application Repository (SAR) for one-click installation

## Documentation

- **[CLAUDE.md](CLAUDE.md)** - Project context, ChatGPT conversation summary, and key requirements
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture and design details
- **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** - Development roadmap and implementation phases

## Quick Start

*Coming soon - after Phase 5 implementation*

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Status

**Current Phase**: Phase 1 - Foundation & Core Transformation Engine

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the complete development roadmap.
