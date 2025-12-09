"""
CloudWatch metrics publishing for monitoring replication operations.

Provides utilities for tracking operational metrics including success rates,
durations, error counts, and retry statistics.
"""

import boto3
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from logger import get_logger

# Initialize logger
logger = get_logger()

# CloudWatch namespace for all metrics
NAMESPACE = 'SecretsReplicator'


class MetricsPublisher:
    """
    Publisher for CloudWatch custom metrics.

    Handles metric publishing with proper error handling to ensure
    metrics failures don't impact the main replication flow.

    Examples:
        >>> publisher = MetricsPublisher()
        >>> publisher.publish_replication_success(
        ...     source_region='us-east-1',
        ...     dest_region='us-west-2',
        ...     duration_ms=250.5
        ... )
    """

    def __init__(self, namespace: str = NAMESPACE, enabled: bool = True):
        """
        Initialize metrics publisher.

        Args:
            namespace: CloudWatch namespace for metrics
            enabled: Whether metrics publishing is enabled
        """
        self.namespace = namespace
        self.enabled = enabled
        self._client = None

        if enabled:
            try:
                self._client = boto3.client('cloudwatch')
            except Exception as e:
                logger.warning(f'Failed to initialize CloudWatch client: {e}')
                self.enabled = False

    def publish_replication_success(
        self,
        source_region: str,
        dest_region: str,
        duration_ms: float,
        transform_mode: str = 'sed',
        secret_size_bytes: Optional[int] = None
    ) -> None:
        """
        Publish metrics for successful replication.

        Args:
            source_region: Source AWS region
            dest_region: Destination AWS region
            duration_ms: Total replication duration in milliseconds
            transform_mode: Transformation mode (sed or json)
            secret_size_bytes: Size of secret in bytes
        """
        dimensions = [
            {'Name': 'SourceRegion', 'Value': source_region},
            {'Name': 'DestRegion', 'Value': dest_region},
            {'Name': 'TransformMode', 'Value': transform_mode}
        ]

        metrics = [
            {
                'MetricName': 'ReplicationSuccess',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': dimensions
            },
            {
                'MetricName': 'ReplicationDuration',
                'Value': duration_ms,
                'Unit': 'Milliseconds',
                'Dimensions': dimensions
            }
        ]

        if secret_size_bytes is not None:
            metrics.append({
                'MetricName': 'SecretSize',
                'Value': secret_size_bytes,
                'Unit': 'Bytes',
                'Dimensions': dimensions
            })

        self._publish_metrics(metrics)

    def publish_replication_failure(
        self,
        source_region: str,
        dest_region: str,
        error_type: str,
        duration_ms: Optional[float] = None
    ) -> None:
        """
        Publish metrics for failed replication.

        Args:
            source_region: Source AWS region
            dest_region: Destination AWS region
            error_type: Type of error (e.g., 'ThrottlingError', 'AccessDeniedError')
            duration_ms: Duration before failure (if available)
        """
        dimensions = [
            {'Name': 'SourceRegion', 'Value': source_region},
            {'Name': 'DestRegion', 'Value': dest_region},
            {'Name': 'ErrorType', 'Value': error_type}
        ]

        metrics = [
            {
                'MetricName': 'ReplicationFailure',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': dimensions
            }
        ]

        if duration_ms is not None:
            metrics.append({
                'MetricName': 'FailureDuration',
                'Value': duration_ms,
                'Unit': 'Milliseconds',
                'Dimensions': dimensions
            })

        self._publish_metrics(metrics)

    def publish_transformation_metrics(
        self,
        mode: str,
        input_size_bytes: int,
        output_size_bytes: int,
        duration_ms: float,
        rules_count: int
    ) -> None:
        """
        Publish transformation performance metrics.

        Args:
            mode: Transformation mode (sed or json)
            input_size_bytes: Input secret size in bytes
            output_size_bytes: Output secret size in bytes
            duration_ms: Transformation duration in milliseconds
            rules_count: Number of transformation rules applied
        """
        dimensions = [{'Name': 'TransformMode', 'Value': mode}]

        metrics = [
            {
                'MetricName': 'TransformationDuration',
                'Value': duration_ms,
                'Unit': 'Milliseconds',
                'Dimensions': dimensions
            },
            {
                'MetricName': 'TransformationInputSize',
                'Value': input_size_bytes,
                'Unit': 'Bytes',
                'Dimensions': dimensions
            },
            {
                'MetricName': 'TransformationOutputSize',
                'Value': output_size_bytes,
                'Unit': 'Bytes',
                'Dimensions': dimensions
            },
            {
                'MetricName': 'TransformationRulesCount',
                'Value': rules_count,
                'Unit': 'Count',
                'Dimensions': dimensions
            }
        ]

        self._publish_metrics(metrics)

    def publish_retry_metrics(
        self,
        operation: str,
        attempt_number: int,
        success: bool
    ) -> None:
        """
        Publish retry attempt metrics.

        Args:
            operation: Operation being retried (e.g., 'get_secret', 'put_secret')
            attempt_number: Current attempt number (1-based)
            success: Whether the retry succeeded
        """
        dimensions = [
            {'Name': 'Operation', 'Value': operation},
            {'Name': 'Success', 'Value': str(success)}
        ]

        metrics = [
            {
                'MetricName': 'RetryAttempt',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': dimensions
            },
            {
                'MetricName': 'RetryAttemptNumber',
                'Value': attempt_number,
                'Unit': 'Count',
                'Dimensions': dimensions
            }
        ]

        self._publish_metrics(metrics)

    def publish_throttling_event(
        self,
        operation: str,
        region: str
    ) -> None:
        """
        Publish throttling event metric.

        Args:
            operation: Operation that was throttled
            region: AWS region where throttling occurred
        """
        dimensions = [
            {'Name': 'Operation', 'Value': operation},
            {'Name': 'Region', 'Value': region}
        ]

        metrics = [
            {
                'MetricName': 'ThrottlingEvent',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': dimensions
            }
        ]

        self._publish_metrics(metrics)

    def _publish_metrics(self, metrics: List[Dict[str, Any]]) -> None:
        """
        Internal method to publish metrics to CloudWatch.

        Handles errors gracefully to ensure metrics failures don't
        impact the main application flow.

        Args:
            metrics: List of metric data dictionaries
        """
        if not self.enabled or not self._client:
            logger.debug('Metrics publishing is disabled')
            return

        if not metrics:
            return

        try:
            # Add timestamp to all metrics
            timestamp = datetime.now(timezone.utc)
            for metric in metrics:
                metric['Timestamp'] = timestamp

            # Publish metrics (CloudWatch allows up to 20 metrics per call)
            batch_size = 20
            for i in range(0, len(metrics), batch_size):
                batch = metrics[i:i + batch_size]

                self._client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )

                logger.debug(f'Published {len(batch)} metrics to CloudWatch')

        except Exception as e:
            # Log error but don't raise - metrics should never break main flow
            logger.warning(f'Failed to publish metrics to CloudWatch: {e}')


# Global metrics publisher instance
_metrics_publisher: Optional[MetricsPublisher] = None


def get_metrics_publisher(enabled: bool = True) -> MetricsPublisher:
    """
    Get or create global metrics publisher instance.

    Args:
        enabled: Whether metrics publishing should be enabled

    Returns:
        MetricsPublisher instance

    Examples:
        >>> publisher = get_metrics_publisher()
        >>> publisher.publish_replication_success(...)
    """
    global _metrics_publisher

    if _metrics_publisher is None:
        _metrics_publisher = MetricsPublisher(enabled=enabled)

    return _metrics_publisher


def reset_metrics_publisher() -> None:
    """
    Reset the global metrics publisher instance.

    Useful for testing to ensure clean state.
    """
    global _metrics_publisher
    _metrics_publisher = None
