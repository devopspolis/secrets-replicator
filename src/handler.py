"""
Main Lambda handler for secrets replicator.

Entry point for AWS Lambda function that replicates secrets across
regions and accounts with transformations.
"""

import re
import time
from typing import Dict, Any
from config import load_config_from_env, load_destinations, ConfigurationError, ReplicatorConfig, DestinationConfig, TRANSFORMATION_SECRET_PREFIX, NAME_MAPPING_PREFIX
from event_parser import parse_eventbridge_event, validate_event_for_replication, EventParsingError
from transformer import (
    transform_secret, parse_sedfile, parse_json_mapping,
    detect_transform_type, parse_transform_names, TransformationError,
    expand_variables, VariableExpansionError
)
from logger import setup_logger, log_event, log_secret_operation, log_transformation, log_replication, log_error
from utils import get_secret_metadata, is_binary_data
from aws_clients import create_secrets_manager_client
from exceptions import (
    SecretNotFoundError,
    AccessDeniedError,
    InvalidRequestError,
    ThrottlingError,
    AWSClientError
)
from metrics import get_metrics_publisher
from filters import should_replicate_secret
from name_mappings import get_destination_name


def build_variable_context(
    destination: DestinationConfig,
    source_secret_id: str,
    dest_secret_name: str,
    source_region: str,
    source_account_id: str
) -> Dict[str, str]:
    """
    Build variable expansion context for a destination.

    Creates a dictionary of variables that can be used in transformation secrets
    using the ${VARIABLE} syntax.

    Args:
        destination: Destination configuration
        source_secret_id: Source secret name/ID
        dest_secret_name: Destination secret name (after name mapping)
        source_region: Source AWS region
        source_account_id: Source AWS account ID

    Returns:
        Dictionary mapping variable names to values

    Examples:
        >>> dest = DestinationConfig(region='us-east-1')
        >>> ctx = build_variable_context(dest, 'my-secret', 'my-secret', 'us-west-2', '123456')
        >>> ctx['REGION']
        'us-east-1'
        >>> ctx['SOURCE_REGION']
        'us-west-2'
    """
    # Core variables available to all transformations
    context = {
        'REGION': destination.region,
        'SOURCE_REGION': source_region,
        'SECRET_NAME': source_secret_id,
        'DEST_SECRET_NAME': dest_secret_name,
        'ACCOUNT_ID': destination.account_role_arn.split(':')[4] if destination.account_role_arn else source_account_id,
        'SOURCE_ACCOUNT_ID': source_account_id
    }

    # Add custom variables from destination config
    if destination.variables:
        # Custom variables override core variables (user takes responsibility)
        context.update(destination.variables)

    return context


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

        # Create Secrets Manager client for source region
        source_client = create_secrets_manager_client(region=secret_event.region)

        # Load destination configurations from Secrets Manager
        try:
            load_destinations(config, source_client)
            log_event(logger, 'INFO', f'Loaded {len(config.destinations)} destination(s)',
                     config_secret=config.config_secret,
                     destination_regions=[d.region for d in config.destinations])
        except ConfigurationError as e:
            log_error(logger, e, context={'stage': 'load_destinations', 'secret': config.config_secret})
            return {
                'statusCode': 500,
                'body': f'Failed to load destinations: {e}'
            }

        # Extract secret name from ARN (removes AWS 6-char suffix)
        from event_parser import extract_secret_name_from_arn
        secret_name = extract_secret_name_from_arn(secret_event.secret_id)
        if not secret_name:
            # If extraction fails, use the secret_id as-is (might be a name, not ARN)
            secret_name = secret_event.secret_id

        # NEW: Check if secret should be replicated using SECRETS_FILTER
        # Returns (should_replicate: bool, transformation_name: Optional[str])
        should_replicate_result, transform_secret_name = should_replicate_secret(
            secret_name,
            config,
            source_client
        )

        # Check if secret passed filter check
        if not should_replicate_result:
            log_event(logger, 'INFO', 'Secret filtered out - not replicating',
                     secret_id=secret_event.secret_id,
                     reason='Did not match SECRETS_FILTER criteria')
            return {
                'statusCode': 200,
                'body': 'Secret skipped (filtered out)',
                'secretId': secret_event.secret_id,
                'reason': 'Did not match SECRETS_FILTER criteria'
            }

        # Parse transformation chain (supports single or comma-separated list)
        # If no transformation specified, perform pass-through replication
        if not transform_secret_name:
            log_event(logger, 'INFO', 'No transformation tag - performing pass-through replication',
                     secret_id=secret_event.secret_id,
                     note='Secret will be replicated without transformation')
            transformation_chain = []
        else:
            # Parse transformation names (supports chains)
            transform_names = parse_transform_names(transform_secret_name)

            if not transform_names:
                log_event(logger, 'ERROR', 'Empty transformation secret name',
                         secret_id=secret_event.secret_id)
                return {
                    'statusCode': 400,
                    'body': 'Empty transformation secret name in tag'
                }

            log_event(logger, 'INFO', 'Transformation chain detected',
                     secret_id=secret_event.secret_id,
                     transform_count=len(transform_names),
                     transforms=transform_names)

            # Load and validate all transformations in the chain
            transformation_chain = []
            for i, transform_name in enumerate(transform_names, 1):
                # Check if transform_name already has the prefix
                if transform_name.startswith(TRANSFORMATION_SECRET_PREFIX):
                    full_transform_name = transform_name
                else:
                    full_transform_name = f"{TRANSFORMATION_SECRET_PREFIX}{transform_name}"

                log_event(logger, 'INFO', f'Loading transformation {i}/{len(transform_names)}',
                         secret_id=secret_event.secret_id,
                         transform_name=transform_name,
                         full_name=full_transform_name)

                try:
                    transformation_secret_value = source_client.get_secret(full_transform_name)

                    if transformation_secret_value.secret_binary:
                        raise InvalidRequestError(
                            f'Transformation secret {transform_name} is binary (must be text)'
                        )

                    transform_content = transformation_secret_value.secret_string

                    # Auto-detect or use configured transform mode
                    if config.transform_mode == 'auto':
                        detected_mode = detect_transform_type(transform_content)
                        log_event(logger, 'INFO', 'Transform type auto-detected',
                                 transform_name=transform_name,
                                 detected_type=detected_mode)
                    else:
                        # Use configured mode (sed or json)
                        detected_mode = config.transform_mode
                        log_event(logger, 'INFO', 'Using configured transform type',
                                 transform_name=transform_name,
                                 transform_type=detected_mode)

                    # Store raw content (parsing happens per-destination after variable expansion)
                    transformation_chain.append({
                        'name': transform_name,
                        'mode': detected_mode,
                        'content': transform_content
                    })

                    log_event(logger, 'INFO', f'Transformation {i}/{len(transform_names)} loaded successfully',
                             transform_name=transform_name,
                             mode=detected_mode,
                             size_bytes=len(transform_content))

                except SecretNotFoundError as e:
                    log_error(logger, e, context={'stage': 'transformation_secret_load',
                                                 'transform_name': transform_name,
                                                 'chain_position': f'{i}/{len(transform_names)}'})
                    return {
                        'statusCode': 404,
                        'body': f'Transformation secret not found: {transform_name} (position {i}/{len(transform_names)})'
                    }
                except AccessDeniedError as e:
                    log_error(logger, e, context={'stage': 'transformation_secret_load',
                                                 'transform_name': transform_name,
                                                 'chain_position': f'{i}/{len(transform_names)}'})
                    return {
                        'statusCode': 403,
                        'body': f'Access denied to transformation secret: {transform_name} (position {i}/{len(transform_names)})'
                    }
                except TransformationError as e:
                    log_error(logger, e, context={'stage': 'rule_parsing',
                                                 'transform_name': transform_name,
                                                 'chain_position': f'{i}/{len(transform_names)}'})
                    return {
                        'statusCode': 500,
                        'body': f'Rule parsing error in {transform_name}: {e}'
                    }
                except (ThrottlingError, AWSClientError) as e:
                    log_error(logger, e, context={'stage': 'transformation_secret_load',
                                                 'transform_name': transform_name,
                                                 'chain_position': f'{i}/{len(transform_names)}'})
                    return {
                        'statusCode': 500,
                        'body': f'Error loading transformation secret {transform_name}: {e}'
                    }

            log_event(logger, 'INFO', 'All transformations in chain loaded successfully',
                     secret_id=secret_event.secret_id,
                     chain_length=len(transformation_chain))

        # Retrieve source secret
        try:
            source_client = create_secrets_manager_client(region=secret_event.region)

            log_secret_operation(logger, 'read', secret_event.secret_id,
                               secret_arn=secret_event.secret_arn,
                               region=secret_event.region)

            source_secret = source_client.get_secret(secret_event.secret_id)

            # Check if secret is binary (no transformation for binary secrets)
            is_binary = bool(source_secret.secret_binary)
            if is_binary:
                log_event(logger, 'INFO', 'Binary secret detected',
                         secret_id=secret_event.secret_id)
            else:
                input_size = len(source_secret.secret_string)

                # Validate secret size
                if input_size > config.max_secret_size:
                    max_kb = config.max_secret_size / 1024
                    raise InvalidRequestError(
                        f'Secret size ({input_size} bytes) exceeds maximum '
                        f'({max_kb:.0f}KB)'
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

        # Write to all configured destinations
        all_destinations_succeeded = True
        destination_results = []

        for dest_idx, destination in enumerate(config.destinations, 1):
            log_event(logger, 'INFO', f'Replicating to destination {dest_idx}/{len(config.destinations)}',
                     dest_region=destination.region,
                     has_role_arn=bool(destination.account_role_arn))

            try:
                dest_client = create_secrets_manager_client(
                    region=destination.region,
                    role_arn=destination.account_role_arn
                )

                # Determine destination secret name using name mapping lookup
                # Returns None if secret doesn't match any pattern (filtering behavior)
                dest_secret_name = get_destination_name(secret_event.secret_id, destination, source_client)

                # If None returned, secret doesn't match secret_names filter - skip this destination
                if dest_secret_name is None:
                    log_event(logger, 'INFO', 'Secret filtered out by secret_names - skipping destination',
                             source_secret=secret_event.secret_id,
                             dest_region=destination.region,
                             reason='No matching pattern in secret_names mapping')
                    # Don't add to destination_results - this is expected filtering, not an error
                    continue

                # Check if destination would be a transformation secret (defense-in-depth)
                if dest_secret_name.startswith(TRANSFORMATION_SECRET_PREFIX):
                    log_event(logger, 'ERROR', 'Cannot replicate to transformation secret',
                             source_secret=secret_event.secret_id,
                             dest_secret=dest_secret_name,
                             transformation_prefix=TRANSFORMATION_SECRET_PREFIX)
                    destination_results.append({
                        'region': destination.region,
                        'secret_name': dest_secret_name,
                        'success': False,
                        'error': f'Cannot replicate to transformation secret: {dest_secret_name}'
                    })
                    all_destinations_succeeded = False
                    continue

                # Check if destination would be a name mapping secret (defense-in-depth)
                if dest_secret_name.startswith(NAME_MAPPING_PREFIX):
                    log_event(logger, 'ERROR', 'Cannot replicate to name mapping secret',
                             source_secret=secret_event.secret_id,
                             dest_secret=dest_secret_name,
                             name_mapping_prefix=NAME_MAPPING_PREFIX)
                    destination_results.append({
                        'region': destination.region,
                        'secret_name': dest_secret_name,
                        'success': False,
                        'error': f'Cannot replicate to name mapping secret: {dest_secret_name}'
                    })
                    all_destinations_succeeded = False
                    continue

                # Log if name mapping was used
                if dest_secret_name != secret_event.secret_id:
                    log_event(logger, 'INFO', 'Name mapping applied',
                             source_secret=secret_event.secret_id,
                             dest_secret=dest_secret_name,
                             dest_region=destination.region)

                log_secret_operation(logger, 'write', dest_secret_name,
                                   region=destination.region)

                # Apply transformations with variable expansion for this destination
                if is_binary:
                    # Binary secrets are not transformed
                    transformed_value = None
                else:
                    # Build variable context for this destination
                    var_context = build_variable_context(
                        destination=destination,
                        source_secret_id=secret_event.secret_id,
                        dest_secret_name=dest_secret_name,
                        source_region=secret_event.region,
                        source_account_id=config.source_account_id or 'unknown'
                    )

                    # Apply transformation chain with variable expansion
                    transformed_value = source_secret.secret_string
                    total_transform_duration = 0

                    for i, transformation in enumerate(transformation_chain, 1):
                        transform_start = time.time()

                        # Expand variables in transformation content for this destination
                        try:
                            expanded_content = expand_variables(transformation['content'], var_context)
                        except VariableExpansionError as e:
                            log_error(logger, e, context={
                                'stage': 'variable_expansion',
                                'transform_name': transformation['name'],
                                'destination': destination.region
                            })
                            raise TransformationError(f"Variable expansion failed in {transformation['name']}: {e}")

                        log_event(logger, 'INFO', f'Applying transformation {i}/{len(transformation_chain)}',
                                 transform_name=transformation['name'],
                                 mode=transformation['mode'],
                                 dest_region=destination.region)

                        # Apply this transformation
                        transformed_value = transform_secret(
                            transformed_value,
                            mode=transformation['mode'],
                            rules_content=expanded_content
                        )

                        transform_duration = (time.time() - transform_start) * 1000
                        total_transform_duration += transform_duration

                        log_event(logger, 'INFO', f'Transformation {i}/{len(transformation_chain)} applied',
                                 transform_name=transformation['name'],
                                 duration_ms=transform_duration,
                                 output_size=len(transformed_value))

                    if len(transformation_chain) > 0:
                        log_event(logger, 'INFO', 'Transformation chain completed for destination',
                                 dest_region=destination.region,
                                 chain_length=len(transformation_chain),
                                 total_duration_ms=total_transform_duration)

                # Write secret (binary or string)
                if is_binary:
                    # For binary secrets, we don't transform, just replicate
                    # Note: put_secret currently only supports string secrets
                    # Binary replication would need additional implementation
                    log_event(logger, 'WARNING', 'Binary secret replication not yet implemented',
                             secret_id=dest_secret_name,
                             dest_region=destination.region)
                    destination_results.append({
                        'region': destination.region,
                        'secret_name': dest_secret_name,
                        'success': False,
                        'error': 'Binary secret replication not implemented'
                    })
                    all_destinations_succeeded = False
                    continue
                else:
                    response = dest_client.put_secret(
                        secret_id=dest_secret_name,
                        secret_value=transformed_value,
                        kms_key_id=destination.kms_key_id,
                        description=f'Replicated from {secret_event.region}/{secret_event.secret_id}'
                    )

                dest_duration_ms = (time.time() - start_time) * 1000

                log_replication(
                    logger,
                    source_region=secret_event.region,
                    dest_region=destination.region,
                    secret_id=secret_event.secret_id,
                    success=True,
                    duration_ms=dest_duration_ms
                )

                # Publish replication success metrics
                metrics.publish_replication_success(
                    source_region=secret_event.region,
                    dest_region=destination.region,
                    duration_ms=dest_duration_ms,
                    transform_mode=config.transform_mode,
                    secret_size_bytes=len(transformed_value) if not is_binary else None
                )

                # Record successful destination
                destination_results.append({
                    'region': destination.region,
                    'secret_name': dest_secret_name,
                    'success': True,
                    'arn': response['ARN'],
                    'version_id': response['VersionId'],
                    'duration_ms': round(dest_duration_ms, 2)
                })

                log_event(logger, 'INFO', f'Successfully replicated to destination {dest_idx}/{len(config.destinations)}',
                         dest_region=destination.region,
                         dest_secret=dest_secret_name,
                         duration_ms=dest_duration_ms)

            except AccessDeniedError as e:
                dest_duration_ms = (time.time() - start_time) * 1000
                log_replication(
                    logger,
                    source_region=secret_event.region,
                    dest_region=destination.region,
                    secret_id=secret_event.secret_id,
                    success=False,
                    duration_ms=dest_duration_ms,
                    error=str(e)
                )

                # Publish replication failure metrics
                metrics.publish_replication_failure(
                    source_region=secret_event.region,
                    dest_region=destination.region,
                    error_type='AccessDeniedError',
                    duration_ms=dest_duration_ms
                )

                destination_results.append({
                    'region': destination.region,
                    'success': False,
                    'error': f'Access denied: {e}',
                    'error_type': 'AccessDeniedError'
                })
                all_destinations_succeeded = False

            except (ThrottlingError, AWSClientError) as e:
                dest_duration_ms = (time.time() - start_time) * 1000
                log_replication(
                    logger,
                    source_region=secret_event.region,
                    dest_region=destination.region,
                    secret_id=secret_event.secret_id,
                    success=False,
                    duration_ms=dest_duration_ms,
                    error=str(e)
                )

                # Publish replication failure metrics
                error_type = type(e).__name__
                metrics.publish_replication_failure(
                    source_region=secret_event.region,
                    dest_region=destination.region,
                    error_type=error_type,
                    duration_ms=dest_duration_ms
                )

                # Track throttling events separately
                if isinstance(e, ThrottlingError):
                    metrics.publish_throttling_event(
                        operation='put_secret',
                        region=destination.region
                    )

                destination_results.append({
                    'region': destination.region,
                    'success': False,
                    'error': str(e),
                    'error_type': error_type
                })
                all_destinations_succeeded = False

        # After all destinations processed, generate final response
        total_duration_ms = (time.time() - start_time) * 1000
        successful_destinations = [r for r in destination_results if r['success']]
        failed_destinations = [r for r in destination_results if not r['success']]

        # Determine transform mode for response
        if len(transformation_chain) == 0:
            transform_mode_response = 'passthrough'
        elif len(transformation_chain) == 1:
            transform_mode_response = config.transform_mode
        else:
            transform_mode_response = 'chain'

        if all_destinations_succeeded:
            log_event(logger, 'INFO', 'All destinations replicated successfully',
                     total_destinations=len(config.destinations),
                     total_duration_ms=total_duration_ms)

            return {
                'statusCode': 200,
                'body': 'Secret replicated successfully to all destinations',
                'sourceSecretId': secret_event.secret_id,
                'sourceRegion': secret_event.region,
                'transformMode': transform_mode_response,
                'rulesCount': total_rules_count,
                'transformChainLength': len(transformation_chain),
                'totalDurationMs': round(total_duration_ms, 2),
                'destinations': destination_results
            }
        else:
            log_event(logger, 'WARNING', 'Some destinations failed',
                     total_destinations=len(config.destinations),
                     successful=len(successful_destinations),
                     failed=len(failed_destinations),
                     total_duration_ms=total_duration_ms)

            return {
                'statusCode': 207,  # Multi-Status
                'body': f'Replicated to {len(successful_destinations)}/{len(config.destinations)} destinations',
                'sourceSecretId': secret_event.secret_id,
                'sourceRegion': secret_event.region,
                'transformMode': transform_mode_response,
                'rulesCount': total_rules_count,
                'transformChainLength': len(transformation_chain),
                'totalDurationMs': round(total_duration_ms, 2),
                'destinations': destination_results
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
