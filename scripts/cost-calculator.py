#!/usr/bin/env python3
"""
AWS Secrets Replicator - Cost Calculator

Estimates monthly AWS costs based on your usage patterns.
Run with --help for options.
"""

import argparse
import sys
from typing import Dict


class CostCalculator:
    """Calculate AWS costs for Secrets Replicator"""

    # Pricing (US regions, as of 2024)
    LAMBDA_REQUEST_COST = 0.20 / 1_000_000  # $0.20 per 1M requests
    LAMBDA_DURATION_COST = 0.0000166667  # Per GB-second
    SECRETS_API_COST = 0.05 / 10_000  # $0.05 per 10,000 API calls
    SECRETS_STORAGE_COST = 0.40  # Per secret per month
    EVENTBRIDGE_COST = 1.00 / 1_000_000  # $1 per 1M events
    CLOUDWATCH_LOGS_INGESTION = 0.50  # Per GB
    CLOUDWATCH_LOGS_STORAGE = 0.03  # Per GB per month
    CLOUDWATCH_METRICS = 0.30 / 1_000  # Per 1,000 custom metrics
    CLOUDWATCH_ALARM = 0.10  # Per alarm per month
    XRAY_TRACES = 5.00 / 1_000_000  # Per 1M traces
    S3_STORAGE = 0.023  # Per GB per month
    SQS_REQUESTS = 0.40 / 1_000_000  # Per 1M requests
    SNS_NOTIFICATIONS = 0.50 / 1_000_000  # Per 1M notifications

    def __init__(self, replications_per_month: int, num_secrets: int,
                 lambda_memory_mb: int = 512, avg_duration_sec: float = 3.0,
                 enable_metrics: bool = True, enable_alarms: bool = True):
        """
        Initialize cost calculator

        Args:
            replications_per_month: Number of secret replications per month
            num_secrets: Number of destination secrets stored
            lambda_memory_mb: Lambda memory allocation (MB)
            avg_duration_sec: Average Lambda duration (seconds)
            enable_metrics: Whether CloudWatch custom metrics are enabled
            enable_alarms: Whether CloudWatch alarms are enabled
        """
        self.replications = replications_per_month
        self.num_secrets = num_secrets
        self.lambda_memory_gb = lambda_memory_mb / 1024
        self.duration_sec = avg_duration_sec
        self.enable_metrics = enable_metrics
        self.enable_alarms = enable_alarms

    def calculate_lambda_costs(self) -> Dict[str, float]:
        """Calculate Lambda costs"""
        request_cost = self.replications * self.LAMBDA_REQUEST_COST
        duration_cost = (self.replications * self.duration_sec *
                        self.lambda_memory_gb * self.LAMBDA_DURATION_COST)

        return {
            'lambda_requests': request_cost,
            'lambda_duration': duration_cost,
            'lambda_total': request_cost + duration_cost
        }

    def calculate_secrets_manager_costs(self) -> Dict[str, float]:
        """Calculate Secrets Manager costs"""
        # 2 API calls per replication (GetSecretValue + PutSecretValue)
        api_calls = self.replications * 2
        api_cost = api_calls * self.SECRETS_API_COST
        storage_cost = self.num_secrets * self.SECRETS_STORAGE_COST

        return {
            'secrets_api': api_cost,
            'secrets_storage': storage_cost,
            'secrets_total': api_cost + storage_cost
        }

    def calculate_eventbridge_costs(self) -> float:
        """Calculate EventBridge costs"""
        return self.replications * self.EVENTBRIDGE_COST

    def calculate_cloudwatch_costs(self) -> Dict[str, float]:
        """Calculate CloudWatch costs"""
        # Estimate log size: ~2KB per replication
        log_size_gb = (self.replications * 2 * 1024) / (1024 ** 3)

        log_ingestion = log_size_gb * self.CLOUDWATCH_LOGS_INGESTION
        log_storage = log_size_gb * self.CLOUDWATCH_LOGS_STORAGE

        # Custom metrics (if enabled)
        metrics_cost = 0.0
        if self.enable_metrics:
            # 4 custom metrics per replication (success/failure/duration/throttle)
            metrics_count = self.replications * 4
            metrics_cost = metrics_count * self.CLOUDWATCH_METRICS

        # Alarms (if enabled)
        alarm_cost = 0.0
        if self.enable_alarms:
            # 3 alarms (failure, throttling, high duration)
            alarm_cost = 3 * self.CLOUDWATCH_ALARM

        return {
            'cloudwatch_logs_ingestion': log_ingestion,
            'cloudwatch_logs_storage': log_storage,
            'cloudwatch_metrics': metrics_cost,
            'cloudwatch_alarms': alarm_cost,
            'cloudwatch_total': log_ingestion + log_storage + metrics_cost + alarm_cost
        }

    def calculate_xray_costs(self) -> float:
        """Calculate X-Ray costs"""
        return self.replications * self.XRAY_TRACES

    def calculate_s3_costs(self) -> float:
        """Calculate S3 costs (for SAR packages)"""
        # Assume ~10MB Lambda package
        package_size_gb = 10 / 1024
        return package_size_gb * self.S3_STORAGE

    def calculate_sqs_sns_costs(self) -> Dict[str, float]:
        """Calculate SQS/SNS costs"""
        # Assume 1% failure rate to DLQ
        dlq_messages = max(1, int(self.replications * 0.01))
        sqs_cost = dlq_messages * self.SQS_REQUESTS

        # SNS notifications for alarms (assume 2 per month)
        sns_cost = 2 * self.SNS_NOTIFICATIONS if self.enable_alarms else 0.0

        return {
            'sqs_dlq': sqs_cost,
            'sns_notifications': sns_cost,
            'sqs_sns_total': sqs_cost + sns_cost
        }

    def calculate_total_costs(self) -> Dict[str, float]:
        """Calculate total monthly costs"""
        lambda_costs = self.calculate_lambda_costs()
        secrets_costs = self.calculate_secrets_manager_costs()
        eventbridge_cost = self.calculate_eventbridge_costs()
        cloudwatch_costs = self.calculate_cloudwatch_costs()
        xray_cost = self.calculate_xray_costs()
        s3_cost = self.calculate_s3_costs()
        sqs_sns_costs = self.calculate_sqs_sns_costs()

        # Compute services total (excluding Secrets Manager storage)
        services_total = (
            lambda_costs['lambda_total'] +
            secrets_costs['secrets_api'] +
            eventbridge_cost +
            cloudwatch_costs['cloudwatch_total'] +
            xray_cost +
            s3_cost +
            sqs_sns_costs['sqs_sns_total']
        )

        # Grand total (including Secrets Manager storage)
        grand_total = services_total + secrets_costs['secrets_storage']

        return {
            **lambda_costs,
            **secrets_costs,
            'eventbridge': eventbridge_cost,
            **cloudwatch_costs,
            'xray': xray_cost,
            's3': s3_cost,
            **sqs_sns_costs,
            'services_total': services_total,
            'grand_total': grand_total
        }

    def print_report(self):
        """Print formatted cost report"""
        costs = self.calculate_total_costs()

        print("=" * 70)
        print("AWS Secrets Replicator - Monthly Cost Estimate")
        print("=" * 70)
        print()
        print("Usage Parameters:")
        print(f"  Replications per month:     {self.replications:,}")
        print(f"  Destination secrets:        {self.num_secrets}")
        print(f"  Lambda memory:              {int(self.lambda_memory_gb * 1024)} MB")
        print(f"  Avg Lambda duration:        {self.duration_sec} seconds")
        print(f"  Custom metrics enabled:     {self.enable_metrics}")
        print(f"  CloudWatch alarms enabled:  {self.enable_alarms}")
        print()
        print("-" * 70)
        print("Cost Breakdown:")
        print("-" * 70)
        print()
        print("Lambda:")
        print(f"  Invocations:                ${costs['lambda_requests']:.4f}")
        print(f"  Duration:                   ${costs['lambda_duration']:.4f}")
        print(f"  Subtotal:                   ${costs['lambda_total']:.4f}")
        print()
        print("Secrets Manager:")
        print(f"  API calls (Get/Put):        ${costs['secrets_api']:.4f}")
        print(f"  Secret storage:             ${costs['secrets_storage']:.2f}")
        print(f"  Subtotal:                   ${costs['secrets_total']:.2f}")
        print()
        print("EventBridge:")
        print(f"  Events:                     ${costs['eventbridge']:.4f}")
        print()
        print("CloudWatch:")
        print(f"  Logs ingestion:             ${costs['cloudwatch_logs_ingestion']:.4f}")
        print(f"  Logs storage:               ${costs['cloudwatch_logs_storage']:.4f}")
        print(f"  Custom metrics:             ${costs['cloudwatch_metrics']:.4f}")
        print(f"  Alarms:                     ${costs['cloudwatch_alarms']:.2f}")
        print(f"  Subtotal:                   ${costs['cloudwatch_total']:.2f}")
        print()
        print("Other Services:")
        print(f"  X-Ray traces:               ${costs['xray']:.4f}")
        print(f"  S3 storage (packages):      ${costs['s3']:.4f}")
        print(f"  SQS/SNS:                    ${costs['sqs_sns_total']:.4f}")
        print()
        print("=" * 70)
        print(f"Services Total (excl. secrets storage):   ${costs['services_total']:.2f}")
        print(f"Secrets Storage ({self.num_secrets} secrets):             ${costs['secrets_storage']:.2f}")
        print(f"MONTHLY TOTAL:                             ${costs['grand_total']:.2f}")
        print("=" * 70)
        print()
        print("Notes:")
        print("  - Prices based on US regions (2024)")
        print("  - Free tier not included (see AWS Free Tier for details)")
        print("  - Secrets storage is the largest cost component")
        print("  - Use --no-metrics to disable custom metrics and reduce costs")
        print("  - Use --no-alarms to disable CloudWatch alarms and reduce costs")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Calculate monthly AWS costs for Secrets Replicator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Testing phase (50 replications)
  ./cost-calculator.py --replications 50 --secrets 1

  # Light production (100 replications, 5 secrets)
  ./cost-calculator.py --replications 100 --secrets 5

  # Moderate production (1000 replications, 10 secrets)
  ./cost-calculator.py --replications 1000 --secrets 10

  # Heavy production (10000 replications, 50 secrets)
  ./cost-calculator.py --replications 10000 --secrets 50

  # Disable metrics and alarms to reduce costs
  ./cost-calculator.py --replications 1000 --secrets 10 --no-metrics --no-alarms
        """
    )

    parser.add_argument('--replications', type=int, default=100,
                        help='Number of replications per month (default: 100)')
    parser.add_argument('--secrets', type=int, default=1,
                        help='Number of destination secrets (default: 1)')
    parser.add_argument('--memory', type=int, default=512,
                        help='Lambda memory in MB (default: 512)')
    parser.add_argument('--duration', type=float, default=3.0,
                        help='Average Lambda duration in seconds (default: 3.0)')
    parser.add_argument('--no-metrics', action='store_true',
                        help='Disable CloudWatch custom metrics')
    parser.add_argument('--no-alarms', action='store_true',
                        help='Disable CloudWatch alarms')

    args = parser.parse_args()

    # Validation
    if args.replications < 0:
        print("Error: replications must be >= 0", file=sys.stderr)
        sys.exit(1)
    if args.secrets < 0:
        print("Error: secrets must be >= 0", file=sys.stderr)
        sys.exit(1)
    if args.memory < 128 or args.memory > 10240:
        print("Error: memory must be between 128 and 10240 MB", file=sys.stderr)
        sys.exit(1)
    if args.duration < 0.1 or args.duration > 900:
        print("Error: duration must be between 0.1 and 900 seconds", file=sys.stderr)
        sys.exit(1)

    # Calculate and print
    calculator = CostCalculator(
        replications_per_month=args.replications,
        num_secrets=args.secrets,
        lambda_memory_mb=args.memory,
        avg_duration_sec=args.duration,
        enable_metrics=not args.no_metrics,
        enable_alarms=not args.no_alarms
    )

    calculator.print_report()


if __name__ == '__main__':
    main()
