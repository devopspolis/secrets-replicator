"""
Pytest configuration for performance tests.

Performance tests measure timing, throughput, and resource usage.

Run with:
    pytest tests/performance/ -v --integration
"""

import pytest


def pytest_configure(config):
    """Configure custom markers for performance tests."""
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "benchmark: mark test as benchmark test"
    )
