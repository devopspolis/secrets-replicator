"""
Performance tests for secret replication.

These tests measure timing, throughput, and resource usage.

Run with:
    pytest tests/performance/ -v --integration
"""

import json
import os
import time
import statistics
import pytest
from src.handler import lambda_handler
from src.transformer import apply_sed_transforms, parse_sedfile, apply_json_transforms, parse_json_mapping
from tests.fixtures.eventbridge_events import create_test_event


@pytest.mark.integration
@pytest.mark.performance
class TestReplicationPerformance:
    """Performance tests for end-to-end replication."""

    @pytest.mark.parametrize("secret_size_kb", [1, 10, 32, 60])
    def test_replication_by_size(
        self,
        secret_helper,
        aws_region,
        account_id,
        secret_size_kb
    ):
        """Test replication performance for different secret sizes."""
        # Create secret of specified size
        secret_value = "x" * (secret_size_kb * 1024)
        source = secret_helper.create_secret(value=secret_value)
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "INFO",
            "ENABLE_METRICS": "false",
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Measure replication time
        start = time.time()
        result = lambda_handler(event, {})
        duration = time.time() - start

        # Verify success
        assert result["statusCode"] == 200

        # Log performance
        print(f"\\nReplication performance for {secret_size_kb}KB secret:")
        print(f"  Duration: {duration:.3f}s")
        print(f"  Throughput: {secret_size_kb / duration:.2f} KB/s")

        # Performance assertions
        if secret_size_kb <= 10:
            assert duration < 3.0, f"Small secret replication too slow: {duration:.3f}s"
        elif secret_size_kb <= 32:
            assert duration < 4.0, f"Medium secret replication too slow: {duration:.3f}s"
        else:
            assert duration < 5.0, f"Large secret replication too slow: {duration:.3f}s"

        # Cleanup
        secret_helper.delete_secret(dest_name, force=True)

    @pytest.mark.slow
    def test_concurrent_replications(
        self,
        secret_helper,
        aws_region,
        account_id
    ):
        """Test performance with concurrent replications."""
        num_secrets = 10
        sources = []

        # Create multiple secrets
        for i in range(num_secrets):
            value = json.dumps({"index": i, "data": f"test_{i}"})
            source = secret_helper.create_secret(value=value)
            sources.append(source)

        os.environ.update({
            "DESTINATION_REGION": aws_region,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "INFO",
            "ENABLE_METRICS": "false",
        })

        # Measure time for sequential processing
        start = time.time()
        durations = []

        for source in sources:
            dest_name = f"test-dest-{source['Name']}"
            os.environ["DESTINATION_SECRET_NAME"] = dest_name

            event = create_test_event(
                event_name="PutSecretValue",
                secret_arn=source["ARN"],
                region=aws_region,
                account_id=account_id,
            )

            op_start = time.time()
            result = lambda_handler(event, {})
            op_duration = time.time() - op_start
            durations.append(op_duration)

            assert result["statusCode"] == 200

            # Cleanup
            secret_helper.delete_secret(dest_name, force=True)

        total_duration = time.time() - start

        # Performance metrics
        avg_duration = statistics.mean(durations)
        min_duration = min(durations)
        max_duration = max(durations)

        print(f"\\nConcurrent replication performance ({num_secrets} secrets):")
        print(f"  Total time: {total_duration:.3f}s")
        print(f"  Average per replication: {avg_duration:.3f}s")
        print(f"  Min duration: {min_duration:.3f}s")
        print(f"  Max duration: {max_duration:.3f}s")
        print(f"  Throughput: {num_secrets / total_duration:.2f} replications/s")

        # Performance assertions
        assert avg_duration < 5.0, f"Average replication too slow: {avg_duration:.3f}s"
        assert total_duration < num_secrets * 5.0, "Sequential processing too slow"


@pytest.mark.benchmark
class TestTransformationPerformance:
    """Performance tests for transformation operations."""

    @pytest.mark.parametrize("num_rules", [1, 5, 10, 20])
    def test_sed_transformation_performance(self, num_rules):
        """Test sed transformation performance with varying rule counts."""
        # Generate rules
        sedfile_content = "\n".join([
            f"s/pattern{i}/replacement{i}/g" for i in range(num_rules)
        ])
        rules = parse_sedfile(sedfile_content)

        # Create test secret
        secret_value = "This is pattern0 and pattern5 and pattern10 text " * 100

        # Measure transformation time
        iterations = 100
        start = time.time()
        for _ in range(iterations):
            result = apply_sed_transforms(secret_value, rules)
        duration = time.time() - start

        avg_duration = duration / iterations

        print(f"\\nSed transformation performance ({num_rules} rules):")
        print(f"  Average time: {avg_duration * 1000:.3f}ms")
        print(f"  Throughput: {1 / avg_duration:.0f} transformations/s")

        # Performance assertions
        assert avg_duration < 0.1, f"Sed transformation too slow: {avg_duration:.3f}s"

    @pytest.mark.parametrize("secret_size_kb", [1, 10, 50])
    def test_transformation_by_secret_size(self, secret_size_kb):
        """Test transformation performance for different secret sizes."""
        # Create test data
        secret_value = "This is production data in us-east-1 region. " * (secret_size_kb * 20)
        sedfile_content = """
s/production/staging/g
s/us-east-1/us-west-2/g
s/db-prod/db-staging/g
"""
        rules = parse_sedfile(sedfile_content)

        # Measure transformation time
        start = time.time()
        result = apply_sed_transforms(secret_value, rules)
        duration = time.time() - start

        print(f"\\nTransformation performance for {secret_size_kb}KB secret:")
        print(f"  Duration: {duration * 1000:.3f}ms")
        print(f"  Throughput: {secret_size_kb / duration:.2f} KB/s")

        # Performance assertions
        if secret_size_kb <= 10:
            assert duration < 0.05, f"Small secret transformation too slow: {duration:.3f}s"
        elif secret_size_kb <= 50:
            assert duration < 0.2, f"Medium secret transformation too slow: {duration:.3f}s"

    def test_json_transformation_performance(self):
        """Test JSON transformation performance."""
        # Create test JSON secret
        secret_value = json.dumps({
            "environment": "development",
            "region": "us-east-1",
            "database": {
                "host": "db-dev.us-east-1.rds.amazonaws.com",
                "port": 5432,
                "replicas": ["replica1.us-east-1", "replica2.us-east-1"]
            },
            "cache": {
                "redis": "redis-dev.us-east-1.cache.amazonaws.com",
                "memcached": "memcached-dev.us-east-1.cache.amazonaws.com"
            }
        })

        # Create JSON mapping
        mapping_content = json.dumps({
            "transformations": [
                {"path": "$.environment", "find": "development", "replace": "production"},
                {"path": "$.region", "find": "us-east-1", "replace": "us-west-2"},
                {"path": "$.database.host", "find": "us-east-1", "replace": "us-west-2"},
                {"path": "$.cache.redis", "find": "us-east-1", "replace": "us-west-2"},
            ]
        })
        mappings = parse_json_mapping(mapping_content)

        # Measure transformation time
        iterations = 100
        start = time.time()
        for _ in range(iterations):
            result = apply_json_transforms(secret_value, mappings)
        duration = time.time() - start

        avg_duration = duration / iterations

        print(f"\\nJSON transformation performance:")
        print(f"  Average time: {avg_duration * 1000:.3f}ms")
        print(f"  Throughput: {1 / avg_duration:.0f} transformations/s")

        # Performance assertions
        assert avg_duration < 0.05, f"JSON transformation too slow: {avg_duration:.3f}s"

    def test_complex_regex_performance(self):
        """Test performance with complex regex patterns."""
        # Create complex regex patterns
        sedfile_content = """
s/arn:aws:[a-z]+:us-east-1:[0-9]+:[a-z]+\\/.+/arn:aws:SERVICE:us-west-2:ACCOUNT:RESOURCE/g
s/https?:\\/\\/[a-z0-9.-]+\\.us-east-1\\.amazonaws\\.com/https:\\/\\/ENDPOINT.us-west-2.amazonaws.com/g
s/[a-z]+-[a-z]+-[0-9][a-z]?/us-west-2a/g
"""
        rules = parse_sedfile(sedfile_content)

        # Create test secret with ARNs and URLs
        secret_value = json.dumps({
            "db_arn": "arn:aws:rds:us-east-1:123456789012:db/mydb",
            "s3_arn": "arn:aws:s3:us-east-1:123456789012:bucket/mybucket",
            "api_url": "https://api.us-east-1.amazonaws.com",
            "az": "us-east-1a"
        })

        # Measure transformation time
        iterations = 100
        start = time.time()
        for _ in range(iterations):
            result = apply_sed_transforms(secret_value, rules)
        duration = time.time() - start

        avg_duration = duration / iterations

        print(f"\\nComplex regex transformation performance:")
        print(f"  Average time: {avg_duration * 1000:.3f}ms")
        print(f"  Throughput: {1 / avg_duration:.0f} transformations/s")

        # Performance assertions
        assert avg_duration < 0.1, f"Complex regex too slow: {avg_duration:.3f}s"


@pytest.mark.benchmark
class TestMemoryUsage:
    """Memory usage tests (informational)."""

    def test_large_secret_memory(self):
        """Test memory usage with large secrets."""
        import tracemalloc

        # Start memory tracking
        tracemalloc.start()

        # Create large secret
        secret_size = 60 * 1024  # 60KB
        secret_value = "x" * secret_size

        # Perform transformation
        sedfile_content = "s/x/y/g"
        rules = parse_sedfile(sedfile_content)

        snapshot1 = tracemalloc.take_snapshot()
        result = apply_sed_transforms(secret_value, rules)
        snapshot2 = tracemalloc.take_snapshot()

        # Calculate memory difference
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        total_memory = sum(stat.size_diff for stat in top_stats)

        print(f"\\nMemory usage for 60KB secret transformation:")
        print(f"  Memory increase: {total_memory / 1024:.2f} KB")

        tracemalloc.stop()

        # Memory should be reasonable (not excessive)
        assert total_memory < 10 * 1024 * 1024, "Memory usage too high"


@pytest.mark.integration
@pytest.mark.cross_region
@pytest.mark.slow
class TestCrossRegionPerformance:
    """Performance tests for cross-region replication."""

    def test_cross_region_latency(
        self,
        secret_helper,
        dest_secret_helper,
        aws_region,
        dest_region,
        account_id
    ):
        """Measure cross-region replication latency."""
        # Create source secret
        source = secret_helper.create_secret()
        dest_name = f"test-dest-{source['Name']}"

        os.environ.update({
            "DESTINATION_REGION": dest_region,
            "DESTINATION_SECRET_NAME": dest_name,
            "TRANSFORM_MODE": "sed",
            "LOG_LEVEL": "INFO",
            "ENABLE_METRICS": "false",
        })

        event = create_test_event(
            event_name="PutSecretValue",
            secret_arn=source["ARN"],
            region=aws_region,
            account_id=account_id,
        )

        # Measure multiple runs for statistical significance
        durations = []
        for i in range(5):
            start = time.time()
            result = lambda_handler(event, {})
            duration = time.time() - start
            durations.append(duration)
            assert result["statusCode"] == 200
            time.sleep(1)  # Brief pause between runs

        # Calculate statistics
        avg_duration = statistics.mean(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        stdev = statistics.stdev(durations) if len(durations) > 1 else 0

        print(f"\\nCross-region replication performance ({aws_region} -> {dest_region}):")
        print(f"  Average: {avg_duration:.3f}s")
        print(f"  Min: {min_duration:.3f}s")
        print(f"  Max: {max_duration:.3f}s")
        print(f"  Std dev: {stdev:.3f}s")

        # Performance assertions
        assert avg_duration < 5.0, f"Cross-region replication too slow: {avg_duration:.3f}s"

        # Cleanup
        dest_secret_helper.delete_secret(dest_name, force=True)
