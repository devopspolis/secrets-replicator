"""
Main Lambda handler for secrets replicator.

Entry point for AWS Lambda function that replicates secrets across
regions and accounts with transformations.
"""

import re
import time
from typing import Dict, Any
from src.config import load_config_from_env, ConfigurationError, ReplicatorConfig
from src.event_parser import parse_eventbridge_event, validate_event_for_replication, EventParsingError
from src.transformer import transform_secret, parse_sedfile, parse_json_mapping, TransformationError
from src.logger import setup_logger, log_event, log_secret_operation, log_transformation, log_replication, log_error
from src.utils import get_secret_metadata, is_binary_data
from src.aws_clients import create_secrets_manager_client
from src.exceptions import (
    SecretNotFoundError,
    AccessDeniedError,
    InvalidRequestError,
    ThrottlingError,
    AWSClientError
)
from src.metrics import get_metrics_publisher


def should_replicate(secret_name: str, tags: Dict[str, str], config: ReplicatorConfig) -> bool:
    """
    Determine if a secret should be replicated based on filtering rules.

    Implements multi-layered filtering logic with defense-in-depth:
    1. Hardcoded exclusion for transformation secrets (highest priority)
    2. Exclude tags (explicitly skip replication)
    3. Include filters with OR logic (pattern, list, or tags)

    Args:
        secret_name: Name of the secret to check
        tags: Secret tags as key-value dict
        config: ReplicatorConfig with filtering settings

    Returns:
        True if secret should be replicated, False otherwise

    Examples:
        >>> config = ReplicatorConfig(dest_region='us-west-2')
        >>> should_replicate('prod-db', {}, config)
        True
        >>> should_replicate('transformations/my-sed', {}, config)
        False
    """
    # LAYER 1: Hardcoded exclusion for transformation secrets (defense-in-depth)
    if secret_name.startswith(config.transformation_secret_prefix):
        # This should never happen due to IAM Deny policy, but provides additional safety
        return False

    # LAYER 2: Exclude tags (explicitly skip replication)
    for key, value in config.source_exclude_tags:
        if tags.get(key) == value:
            return False

    # LAYER 3: Include filters (OR logic)
    # If no include filters configured, replicate all (except excluded above)
    has_include_filters = (
        config.source_secret_pattern is not None or
        len(config.source_secret_list) > 0 or
        len(config.source_include_tags) > 0
    )

    if not has_include_filters:
        return True

    # Check pattern match
    if config.source_secret_pattern:
        if re.match(config.source_secret_pattern, secret_name):
            return True

    # Check explicit list
    if secret_name in config.source_secret_list:
        return True

    # Check include tags (any match)
    for key, value in config.source_include_tags:
        if tags.get(key) == value:
            return True

    # No include filter matched
    return False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for secret replication.

    Args:
        event: EventBridge event from Secrets Manager
        context: Lambda context object

    Returns:
        Response dictionary with status and details

    Raises:
        Does not raise - all errors are caught and logged
    """
    # Initialize logger and metrics
    try:
        config = load_config_from_env()
        logger = setup_logger('secrets-replicator', level=config.log_level)
        metrics = get_metrics_publisher(enabled=config.enable_metrics)
    except Exception as e:
        # Fallback logger if config fails
        logger = setup_logger('secrets-replicator', level='INFO')
        log_error(logger, e, context={'stage': 'config_load'})
        return {
            'statusCode': 500,
            'body': f'Configuration error: {e}'
        }

    start_time = time.time()
    request_id = context.request_id if hasattr(context, 'request_id') else 'unknown'

    log_event(logger, 'INFO', 'Lambda invocation started', request_id=request_id)

    try:
        # Parse EventBridge event
        try:
            secret_event = parse_eventbridge_event(event)
            log_event(logger, 'INFO', 'Event parsed successfully',
                     event_name=secret_event.event_name,
                     secret_id=secret_event.secret_id,
                     region=secret_event.region)
        except EventParsingError as e:
            log_error(logger, e, context={'stage': 'event_parsing', 'event': event})
            return {
                'statusCode': 400,
                'body': f'Event parsing error: {e}'
            }

        # Validate event should trigger replication
        if not validate_event_for_replication(secret_event):
            log_event(logger, 'INFO', 'Event does not trigger replication',
                     event_name=secret_event.event_name,
                     reason='Not a replication trigger event')
            return {
                'statusCode': 200,
                'body': 'Event skipped (not a replication trigger)'
            }

        # Update config with source information
        config.source_region = secret_event.region
        config.source_account_id = secret_event.account_id

        # Retrieve secret tags for filtering
        try:
            source_client = create_secrets_manager_client(region=secret_event.region)

            # Get tags for filtering (lightweight operation)
            secret_tags = source_client.get_secret_tags(secret_event.secret_id)

            log_event(logger, 'DEBUG', 'Retrieved secret tags for filtering',
                     secret_id=secret_event.secret_id,
                     tag_count=len(secret_tags))
        except Exception as e:
            # If we can't retrieve tags, log warning but continue without tags
            log_event(logger, 'WARNING', 'Failed to retrieve secret tags, filtering without tags',
                     secret_id=secret_event.secret_id,
                     error=str(e))
            secret_tags = {}

        # Check if secret should be replicated (filtering logic)
        if not should_replicate(secret_event.secret_id, secret_tags, config):
            log_event(logger, 'INFO', 'Secret filtered out - not replicating',
                     secret_id=secret_event.secret_id,
                     reason='Did not match filtering criteria')
            return {
                'statusCode': 200,
                'body': 'Secret skipped (filtered out)',
                'secretId': secret_event.secret_id,
                'reason': 'Did not match filtering criteria'
            }

        # Check for transformation secret tags (ADR-002: Transformation Secrets)
        transform_secret_name = secret_tags.get('SecretsReplicator:TransformSecretName')
        transform_mode_override = secret_tags.get('SecretsReplicator:TransformMode')

        # Override transform mode if specified in tags
        if transform_mode_override:
            if transform_mode_override not in ['sed', 'json']:
                log_event(logger, 'WARNING', 'Invalid transform mode in tag, using config default',
                         secret_id=secret_event.secret_id,
                         tag_value=transform_mode_override,
                         using=config.transform_mode)
            else:
                config.transform_mode = transform_mode_override
                log_event(logger, 'INFO', 'Transform mode overridden by tag',
                         secret_id=secret_event.secret_id,
                         transform_mode=transform_mode_override)

        # Load transformation rules (from transformation secret or S3/bundled)
        if transform_secret_name:
            # Load transformation from transformation secret
            log_event(logger, 'INFO', 'Loading transformation from transformation secret',
                     secret_id=secret_event.secret_id,
                     transform_secret=transform_secret_name)

            try:
                transformation_secret_value = source_client.get_secret(transform_secret_name)

                if transformation_secret_value.secret_binary:
                    raise InvalidRequestError(
                        f'Transformation secret {transform_secret_name} is binary (must be text)'
                    )

                sedfile_content = transformation_secret_value.secret_string
                log_event(logger, 'INFO', 'Transformation secret loaded successfully',
                         transform_secret=transform_secret_name,
                         size_bytes=len(sedfile_content))

            except SecretNotFoundError as e:
                log_error(logger, e, context={'stage': 'transformation_secret_load',
                                             'transform_secret': transform_secret_name})
                return {
                    'statusCode': 404,
                    'body': f'Transformation secret not found: {transform_secret_name}'
                }
            except AccessDeniedError as e:
                log_error(logger, e, context={'stage': 'transformation_secret_load',
                                             'transform_secret': transform_secret_name})
                return {
                    'statusCode': 403,
                    'body': f'Access denied to transformation secret: {transform_secret_name}'
                }
            except (ThrottlingError, AWSClientError) as e:
                log_error(logger, e, context={'stage': 'transformation_secret_load',
                                             'transform_secret': transform_secret_name})
                return {
                    'statusCode': 500,
                    'body': f'Error loading transformation secret: {e}'
                }

        else:
            # Transformation secret is required
            log_event(logger, 'ERROR', 'No transformation secret specified',
                     secret_id=secret_event.secret_id,
                     note='Secret must have SecretsReplicator:TransformSecretName tag')
            return {
                'statusCode': 400,
                'body': 'No transformation secret specified. Secret must have SecretsReplicator:TransformSecretName tag.'
            }

        # Parse transformation rules
        try:
            if config.transform_mode == 'sed':
                transform_rules = parse_sedfile(sedfile_content)
                rules_count = len(transform_rules)
            else:  # json
                transform_rules = parse_json_mapping(sedfile_content)
                rules_count = len(transform_rules)

            log_event(logger, 'INFO', 'Transformation rules parsed',
                     mode=config.transform_mode,
                     rules_count=rules_count)
        except TransformationError as e:
            log_error(logger, e, context={'stage': 'rule_parsing'})
            return {
                'statusCode': 500,
                'body': f'Rule parsing error: {e}'
            }

        # Retrieve source secret
        try:
            source_client = create_secrets_manager_client(region=secret_event.region)

            log_secret_operation(logger, 'read', secret_event.secret_id,
                               secret_arn=secret_event.secret_arn,
                               region=secret_event.region)

            source_secret = source_client.get_secret(secret_event.secret_id)

            # Check if secret is binary (no transformation for binary secrets)
            if source_secret.secret_binary:
                log_event(logger, 'INFO', 'Binary secret detected, skipping transformation',
                         secret_id=secret_event.secret_id)
                transformed_value = None
                is_binary = True
            else:
                is_binary = False
                input_size = len(source_secret.secret_string)

                # Validate secret size
                if input_size > config.max_secret_size:
                    max_kb = config.max_secret_size / 1024
                    raise InvalidRequestError(
                        f'Secret size ({input_size} bytes) exceeds maximum '
                        f'({max_kb:.0f}KB)'
                    )

                # Apply transformations
                transform_start = time.time()
                transformed_value = transform_secret(
                    source_secret.secret_string,
                    mode=config.transform_mode,
                    rules_content=sedfile_content
                )
                transform_duration = (time.time() - transform_start) * 1000

                output_size = len(transformed_value)

                log_transformation(
                    logger,
                    mode=config.transform_mode,
                    rules_count=rules_count,
                    input_size=input_size,
                    output_size=output_size,
                    duration_ms=transform_duration
                )

                # Publish transformation metrics
                metrics.publish_transformation_metrics(
                    mode=config.transform_mode,
                    input_size_bytes=input_size,
                    output_size_bytes=output_size,
                    duration_ms=transform_duration,
                    rules_count=rules_count
                )

        except SecretNotFoundError as e:
            log_error(logger, e, context={'stage': 'source_retrieval',
                                         'secret_id': secret_event.secret_id})
            return {
                'statusCode': 404,
                'body': f'Source secret not found: {e}'
            }
        except AccessDeniedError as e:
            log_error(logger, e, context={'stage': 'source_retrieval',
                                         'secret_id': secret_event.secret_id})
            return {
                'statusCode': 403,
                'body': f'Access denied to source secret: {e}'
            }
        except (ThrottlingError, AWSClientError) as e:
            log_error(logger, e, context={'stage': 'source_retrieval',
                                         'secret_id': secret_event.secret_id})
            return {
                'statusCode': 500,
                'body': f'Error retrieving source secret: {e}'
            }

        # Write to destination
        try:
            dest_client = create_secrets_manager_client(
                region=config.dest_region,
                role_arn=config.dest_account_role_arn
            )

            # Determine destination secret name
            dest_secret_name = config.dest_secret_name or secret_event.secret_id

            # Check if destination would be a transformation secret (defense-in-depth)
            if dest_secret_name.startswith(config.transformation_secret_prefix):
                log_event(logger, 'ERROR', 'Cannot replicate to transformation secret',
                         source_secret=secret_event.secret_id,
                         dest_secret=dest_secret_name,
                         transformation_prefix=config.transformation_secret_prefix)
                return {
                    'statusCode': 400,
                    'body': f'Cannot replicate to transformation secret: {dest_secret_name}'
                }

            # Log non-standard configuration if custom destination name is used
            if config.dest_secret_name:
                log_event(logger, 'WARNING', 'Using custom destination secret name (non-standard)',
                         source_secret=secret_event.secret_id,
                         dest_secret=dest_secret_name,
                         note='Standard DR/HA pattern uses identical names across regions')

            log_secret_operation(logger, 'write', dest_secret_name,
                               region=config.dest_region)

            # Write secret (binary or string)
            if is_binary:
                # For binary secrets, we don't transform, just replicate
                # Note: put_secret currently only supports string secrets
                # Binary replication would need additional implementation
                log_event(logger, 'WARNING', 'Binary secret replication not yet implemented',
                         secret_id=dest_secret_name)
                return {
                    'statusCode': 501,
                    'body': 'Binary secret replication not implemented'
                }
            else:
                response = dest_client.put_secret(
                    secret_id=dest_secret_name,
                    secret_value=transformed_value,
                    kms_key_id=config.kms_key_id,
                    description=f'Replicated from {secret_event.region}/{secret_event.secret_id}'
                )

            duration_ms = (time.time() - start_time) * 1000

            log_replication(
                logger,
                source_region=secret_event.region,
                dest_region=config.dest_region,
                secret_id=secret_event.secret_id,
                success=True,
                duration_ms=duration_ms
            )

            # Publish replication success metrics
            metrics.publish_replication_success(
                source_region=secret_event.region,
                dest_region=config.dest_region,
                duration_ms=duration_ms,
                transform_mode=config.transform_mode,
                secret_size_bytes=len(transformed_value) if not is_binary else None
            )

            return {
                'statusCode': 200,
                'body': 'Secret replicated successfully',
                'sourceSecretId': secret_event.secret_id,
                'sourceRegion': secret_event.region,
                'destSecretId': dest_secret_name,
                'destRegion': config.dest_region,
                'destArn': response['ARN'],
                'destVersionId': response['VersionId'],
                'transformMode': config.transform_mode,
                'rulesCount': rules_count,
                'durationMs': round(duration_ms, 2)
            }

        except AccessDeniedError as e:
            duration_ms = (time.time() - start_time) * 1000
            log_replication(
                logger,
                source_region=secret_event.region,
                dest_region=config.dest_region,
                secret_id=secret_event.secret_id,
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )

            # Publish replication failure metrics
            metrics.publish_replication_failure(
                source_region=secret_event.region,
                dest_region=config.dest_region,
                error_type='AccessDeniedError',
                duration_ms=duration_ms
            )

            return {
                'statusCode': 403,
                'body': f'Access denied to destination: {e}'
            }
        except (ThrottlingError, AWSClientError) as e:
            duration_ms = (time.time() - start_time) * 1000
            log_replication(
                logger,
                source_region=secret_event.region,
                dest_region=config.dest_region,
                secret_id=secret_event.secret_id,
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )

            # Publish replication failure metrics
            error_type = type(e).__name__
            metrics.publish_replication_failure(
                source_region=secret_event.region,
                dest_region=config.dest_region,
                error_type=error_type,
                duration_ms=duration_ms
            )

            # Track throttling events separately
            if isinstance(e, ThrottlingError):
                metrics.publish_throttling_event(
                    operation='put_secret',
                    region=config.dest_region
                )

            return {
                'statusCode': 500,
                'body': f'Error writing to destination: {e}'
            }

    except Exception as e:
        # Catch-all for unexpected errors
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, e, context={
            'stage': 'handler',
            'request_id': request_id,
            'duration_ms': duration_ms
        })

        return {
            'statusCode': 500,
            'body': f'Unexpected error: {e}'
        }
