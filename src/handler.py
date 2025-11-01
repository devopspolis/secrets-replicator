"""
Main Lambda handler for secrets replicator.

Entry point for AWS Lambda function that replicates secrets across
regions and accounts with transformations.
"""

import time
from typing import Dict, Any
from src.config import load_config_from_env, ConfigurationError
from src.event_parser import parse_eventbridge_event, validate_event_for_replication, EventParsingError
from src.sedfile_loader import load_sedfile, SedfileLoadError
from src.transformer import transform_secret, parse_sedfile, parse_json_mapping, TransformationError
from src.logger import setup_logger, log_event, log_secret_operation, log_transformation, log_replication, log_error
from src.utils import get_secret_metadata


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
    # Initialize logger
    try:
        config = load_config_from_env()
        logger = setup_logger('secrets-replicator', level=config.log_level)
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

        # Load sedfile/transformation rules
        try:
            sedfile_content = load_sedfile(
                bucket=config.sedfile_s3_bucket,
                key=config.sedfile_s3_key
            )
            log_event(logger, 'INFO', 'Sedfile loaded',
                     mode=config.transform_mode,
                     source='s3' if config.sedfile_s3_bucket else 'bundled')
        except SedfileLoadError as e:
            log_error(logger, e, context={'stage': 'sedfile_load'})
            return {
                'statusCode': 500,
                'body': f'Sedfile load error: {e}'
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

        # In a real implementation, we would:
        # 1. Retrieve the source secret using boto3
        # 2. Apply transformations
        # 3. Write to destination
        #
        # For now, we'll return success as Phase 2 focuses on handler structure
        # Phase 3 will implement the actual AWS integration

        duration_ms = (time.time() - start_time) * 1000

        log_replication(
            logger,
            source_region=secret_event.region,
            dest_region=config.dest_region,
            secret_id=secret_event.secret_id,
            success=True,
            duration_ms=duration_ms
        )

        return {
            'statusCode': 200,
            'body': 'Success (handler structure complete, AWS integration pending Phase 3)',
            'secretId': secret_event.secret_id,
            'sourceRegion': secret_event.region,
            'destRegion': config.dest_region,
            'transformMode': config.transform_mode,
            'rulesCount': rules_count
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
