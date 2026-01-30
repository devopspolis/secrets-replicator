"""
Unit tests for metrics module
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
from metrics import MetricsPublisher, get_metrics_publisher, reset_metrics_publisher, NAMESPACE


class TestMetricsPublisher:
    """Tests for MetricsPublisher class"""

    def test_init_enabled(self):
        """Test metrics publisher initialization when enabled"""
        with patch("metrics.boto3.client") as mock_boto_client:
            mock_boto_client.return_value = Mock()
            publisher = MetricsPublisher(enabled=True)

            assert publisher.enabled is True
            assert publisher.namespace == NAMESPACE
            mock_boto_client.assert_called_once_with("cloudwatch")

    def test_init_disabled(self):
        """Test metrics publisher initialization when disabled"""
        publisher = MetricsPublisher(enabled=False)

        assert publisher.enabled is False
        assert publisher._client is None

    def test_init_boto3_failure(self):
        """Test graceful handling of boto3 client initialization failure"""
        with patch("metrics.boto3.client", side_effect=Exception("AWS error")):
            publisher = MetricsPublisher(enabled=True)

            assert publisher.enabled is False

    def test_publish_replication_success(self):
        """Test publishing replication success metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_replication_success(
                source_region="us-east-1",
                dest_region="us-west-2",
                duration_ms=250.5,
                transform_mode="sed",
                secret_size_bytes=1024,
            )

            # Verify put_metric_data was called
            assert mock_client.put_metric_data.called
            call_args = mock_client.put_metric_data.call_args[1]

            assert call_args["Namespace"] == NAMESPACE
            metric_data = call_args["MetricData"]

            # Should have 3 metrics: success count, duration, size
            assert len(metric_data) == 3

            # Check metric names
            metric_names = [m["MetricName"] for m in metric_data]
            assert "ReplicationSuccess" in metric_names
            assert "ReplicationDuration" in metric_names
            assert "SecretSize" in metric_names

    def test_publish_replication_success_without_size(self):
        """Test publishing replication success without secret size"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_replication_success(
                source_region="us-east-1", dest_region="us-west-2", duration_ms=250.5
            )

            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Should have 2 metrics without size
            assert len(metric_data) == 2
            metric_names = [m["MetricName"] for m in metric_data]
            assert "SecretSize" not in metric_names

    def test_publish_replication_failure(self):
        """Test publishing replication failure metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_replication_failure(
                source_region="us-east-1",
                dest_region="us-west-2",
                error_type="ThrottlingError",
                duration_ms=100.0,
            )

            assert mock_client.put_metric_data.called
            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Should have 2 metrics: failure count and duration
            assert len(metric_data) == 2

            metric_names = [m["MetricName"] for m in metric_data]
            assert "ReplicationFailure" in metric_names
            assert "FailureDuration" in metric_names

    def test_publish_transformation_metrics(self):
        """Test publishing transformation metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_transformation_metrics(
                mode="json",
                input_size_bytes=500,
                output_size_bytes=550,
                duration_ms=15.3,
                rules_count=5,
            )

            assert mock_client.put_metric_data.called
            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Should have 4 metrics
            assert len(metric_data) == 4

            metric_names = [m["MetricName"] for m in metric_data]
            assert "TransformationDuration" in metric_names
            assert "TransformationInputSize" in metric_names
            assert "TransformationOutputSize" in metric_names
            assert "TransformationRulesCount" in metric_names

    def test_publish_retry_metrics(self):
        """Test publishing retry metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_retry_metrics(operation="get_secret", attempt_number=3, success=True)

            assert mock_client.put_metric_data.called
            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Should have 2 metrics
            assert len(metric_data) == 2

            metric_names = [m["MetricName"] for m in metric_data]
            assert "RetryAttempt" in metric_names
            assert "RetryAttemptNumber" in metric_names

    def test_publish_throttling_event(self):
        """Test publishing throttling event"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_throttling_event(operation="put_secret", region="us-west-2")

            assert mock_client.put_metric_data.called
            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Should have 1 metric
            assert len(metric_data) == 1
            assert metric_data[0]["MetricName"] == "ThrottlingEvent"

    def test_publish_metrics_disabled(self):
        """Test that no metrics are published when disabled"""
        publisher = MetricsPublisher(enabled=False)

        # Should not raise, should do nothing
        publisher.publish_replication_success(
            source_region="us-east-1", dest_region="us-west-2", duration_ms=100.0
        )

    def test_publish_metrics_handles_errors_gracefully(self):
        """Test that metric publishing errors don't crash the app"""
        mock_client = MagicMock()
        mock_client.put_metric_data.side_effect = Exception("CloudWatch error")

        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            # Should not raise exception
            publisher.publish_replication_success(
                source_region="us-east-1", dest_region="us-west-2", duration_ms=100.0
            )

    def test_dimensions_included(self):
        """Test that proper dimensions are included in metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_replication_success(
                source_region="us-east-1",
                dest_region="us-west-2",
                duration_ms=250.5,
                transform_mode="sed",
            )

            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Check dimensions on first metric
            dimensions = metric_data[0]["Dimensions"]
            dimension_names = [d["Name"] for d in dimensions]

            assert "SourceRegion" in dimension_names
            assert "DestRegion" in dimension_names
            assert "TransformMode" in dimension_names

    def test_timestamp_added_to_metrics(self):
        """Test that timestamp is added to all metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_replication_success(
                source_region="us-east-1", dest_region="us-west-2", duration_ms=250.5
            )

            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # All metrics should have timestamps
            for metric in metric_data:
                assert "Timestamp" in metric
                assert isinstance(metric["Timestamp"], datetime)

    def test_batch_publishing(self):
        """Test that metrics are published in batches of 20"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            # Create 25 metrics (should result in 2 batches)
            metrics = [
                {"MetricName": f"TestMetric{i}", "Value": i, "Unit": "Count", "Dimensions": []}
                for i in range(25)
            ]

            publisher._publish_metrics(metrics)

            # Should be called twice (20 + 5)
            assert mock_client.put_metric_data.call_count == 2


class TestGetMetricsPublisher:
    """Tests for get_metrics_publisher function"""

    def setup_method(self):
        """Reset global publisher before each test"""
        reset_metrics_publisher()

    def test_get_metrics_publisher_creates_instance(self):
        """Test that get_metrics_publisher creates an instance"""
        with patch("metrics.boto3.client"):
            publisher = get_metrics_publisher()
            assert publisher is not None
            assert isinstance(publisher, MetricsPublisher)

    def test_get_metrics_publisher_returns_same_instance(self):
        """Test that subsequent calls return the same instance"""
        with patch("metrics.boto3.client"):
            publisher1 = get_metrics_publisher()
            publisher2 = get_metrics_publisher()

            assert publisher1 is publisher2

    def test_get_metrics_publisher_respects_enabled_flag(self):
        """Test that enabled flag is respected"""
        publisher = get_metrics_publisher(enabled=False)
        assert publisher.enabled is False


class TestResetMetricsPublisher:
    """Tests for reset_metrics_publisher function"""

    def test_reset_clears_global_instance(self):
        """Test that reset clears the global instance"""
        with patch("metrics.boto3.client"):
            publisher1 = get_metrics_publisher()
            reset_metrics_publisher()
            publisher2 = get_metrics_publisher()

            assert publisher1 is not publisher2


class TestEdgeCases:
    """Tests for edge cases"""

    def test_empty_metrics_list(self):
        """Test publishing empty metrics list"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()
            publisher._publish_metrics([])

            # Should not call CloudWatch
            assert not mock_client.put_metric_data.called

    def test_custom_namespace(self):
        """Test using custom namespace"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher(namespace="CustomNamespace")

            publisher.publish_replication_success(
                source_region="us-east-1", dest_region="us-west-2", duration_ms=100.0
            )

            call_args = mock_client.put_metric_data.call_args[1]
            assert call_args["Namespace"] == "CustomNamespace"

    def test_metric_units(self):
        """Test that proper units are used for metrics"""
        mock_client = MagicMock()
        with patch("metrics.boto3.client", return_value=mock_client):
            publisher = MetricsPublisher()

            publisher.publish_replication_success(
                source_region="us-east-1",
                dest_region="us-west-2",
                duration_ms=250.5,
                secret_size_bytes=1024,
            )

            call_args = mock_client.put_metric_data.call_args[1]
            metric_data = call_args["MetricData"]

            # Find duration metric
            duration_metric = next(
                m for m in metric_data if m["MetricName"] == "ReplicationDuration"
            )
            assert duration_metric["Unit"] == "Milliseconds"

            # Find size metric
            size_metric = next(m for m in metric_data if m["MetricName"] == "SecretSize")
            assert size_metric["Unit"] == "Bytes"
