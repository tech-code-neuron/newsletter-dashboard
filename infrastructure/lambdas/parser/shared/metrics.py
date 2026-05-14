"""
CloudWatch Custom Metrics Helper
=================================
Publish per-company metrics for monitoring

SOLID Compliance:
    - Single Responsibility: Only publishes CloudWatch metrics
    - Open/Closed: Add new metric types without modifying existing code
    - No hardcoded values: All namespaces and thresholds configurable

Usage:
    from metrics import publish_success_metric, publish_failure_metric

    publish_success_metric(ticker='EPRT', operation='parsing')
    publish_failure_metric(ticker='EPRT', operation='scraping', error='timeout')

Last Updated: 2026-03-09
"""

import boto3
from datetime import datetime, timedelta
import os

cloudwatch = boto3.client('cloudwatch')

# Constants - extracted for SOLID compliance
NAMESPACE = os.environ.get('METRICS_NAMESPACE', 'REITSheet/Companies')
METRIC_SUCCESS = 'OperationSuccess'
METRIC_FAILURE = 'OperationFailure'
METRIC_DURATION = 'OperationDuration'

# Dimension names
DIM_TICKER = 'Ticker'
DIM_OPERATION = 'Operation'
DIM_ERROR_TYPE = 'ErrorType'

# Units
UNIT_COUNT = 'Count'
UNIT_MILLISECONDS = 'Milliseconds'


def publish_success_metric(ticker, operation, duration_ms=None):
    """
    Publish success metric for a company operation

    Args:
        ticker: Company ticker (e.g., 'EPRT')
        operation: Operation type (parsing, enrichment, scraping)
        duration_ms: Optional duration in milliseconds

    Example:
        publish_success_metric('EPRT', 'parsing', 450.2)
    """
    try:
        metrics = [
            {
                'MetricName': METRIC_SUCCESS,
                'Dimensions': [
                    {'Name': DIM_TICKER, 'Value': ticker},
                    {'Name': DIM_OPERATION, 'Value': operation}
                ],
                'Value': 1,
                'Unit': UNIT_COUNT,
                'Timestamp': datetime.utcnow()
            }
        ]

        if duration_ms is not None:
            metrics.append({
                'MetricName': METRIC_DURATION,
                'Dimensions': [
                    {'Name': DIM_TICKER, 'Value': ticker},
                    {'Name': DIM_OPERATION, 'Value': operation}
                ],
                'Value': duration_ms,
                'Unit': UNIT_MILLISECONDS,
                'Timestamp': datetime.utcnow()
            })

        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=metrics
        )
    except Exception as e:
        # Don't fail operation if metrics fail - log only
        print(f"Warning: Failed to publish success metric for {ticker}/{operation}: {e}")


def publish_failure_metric(ticker, operation, error_type='unknown'):
    """
    Publish failure metric for a company operation

    Args:
        ticker: Company ticker (e.g., 'EPRT')
        operation: Operation type (parsing, enrichment, scraping)
        error_type: Type of error (timeout, 404, parse_error, etc.)

    Example:
        publish_failure_metric('EPRT', 'scraping', 'timeout')
    """
    try:
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    'MetricName': METRIC_FAILURE,
                    'Dimensions': [
                        {'Name': DIM_TICKER, 'Value': ticker},
                        {'Name': DIM_OPERATION, 'Value': operation},
                        {'Name': DIM_ERROR_TYPE, 'Value': error_type}
                    ],
                    'Value': 1,
                    'Unit': UNIT_COUNT,
                    'Timestamp': datetime.utcnow()
                }
            ]
        )
    except Exception as e:
        print(f"Warning: Failed to publish failure metric for {ticker}/{operation}: {e}")


def calculate_success_rate(ticker, operation, period_hours=24):
    """
    Calculate success rate for a ticker/operation over a time period

    Args:
        ticker: Company ticker
        operation: Operation type
        period_hours: Lookback period in hours (default 24)

    Returns:
        float: Success rate (0.0 to 1.0) or None if no data

    Example:
        rate = calculate_success_rate('EPRT', 'scraping', 24)
        if rate is not None and rate < 0.9:
            print(f"Warning: EPRT scraping below 90%: {rate:.1%}")
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=period_hours)

        # Get success count
        success_response = cloudwatch.get_metric_statistics(
            Namespace=NAMESPACE,
            MetricName=METRIC_SUCCESS,
            Dimensions=[
                {'Name': DIM_TICKER, 'Value': ticker},
                {'Name': DIM_OPERATION, 'Value': operation}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=period_hours * 3600,
            Statistics=['Sum']
        )

        # Get failure count
        failure_response = cloudwatch.get_metric_statistics(
            Namespace=NAMESPACE,
            MetricName=METRIC_FAILURE,
            Dimensions=[
                {'Name': DIM_TICKER, 'Value': ticker},
                {'Name': DIM_OPERATION, 'Value': operation}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=period_hours * 3600,
            Statistics=['Sum']
        )

        success_count = success_response['Datapoints'][0]['Sum'] if success_response['Datapoints'] else 0
        failure_count = failure_response['Datapoints'][0]['Sum'] if failure_response['Datapoints'] else 0

        total = success_count + failure_count

        if total == 0:
            return None

        return success_count / total

    except Exception as e:
        print(f"Warning: Failed to calculate success rate for {ticker}/{operation}: {e}")
        return None


def publish_batch_metrics(metrics_list):
    """
    Publish multiple metrics in one API call (more efficient)

    Args:
        metrics_list: List of metric dicts with keys:
            - type: 'success' or 'failure'
            - ticker: Company ticker
            - operation: Operation type
            - duration_ms: Optional duration (for success only)
            - error_type: Error type (for failure only)

    Example:
        publish_batch_metrics([
            {'type': 'success', 'ticker': 'EPRT', 'operation': 'parsing', 'duration_ms': 450},
            {'type': 'success', 'ticker': 'DLR', 'operation': 'parsing', 'duration_ms': 320}
        ])
    """
    try:
        metric_data = []

        for metric in metrics_list:
            metric_type = metric.get('type')
            ticker = metric.get('ticker')
            operation = metric.get('operation')

            if metric_type == 'success':
                metric_data.append({
                    'MetricName': METRIC_SUCCESS,
                    'Dimensions': [
                        {'Name': DIM_TICKER, 'Value': ticker},
                        {'Name': DIM_OPERATION, 'Value': operation}
                    ],
                    'Value': 1,
                    'Unit': UNIT_COUNT,
                    'Timestamp': datetime.utcnow()
                })

                duration_ms = metric.get('duration_ms')
                if duration_ms is not None:
                    metric_data.append({
                        'MetricName': METRIC_DURATION,
                        'Dimensions': [
                            {'Name': DIM_TICKER, 'Value': ticker},
                            {'Name': DIM_OPERATION, 'Value': operation}
                        ],
                        'Value': duration_ms,
                        'Unit': UNIT_MILLISECONDS,
                        'Timestamp': datetime.utcnow()
                    })

            elif metric_type == 'failure':
                error_type = metric.get('error_type', 'unknown')
                metric_data.append({
                    'MetricName': METRIC_FAILURE,
                    'Dimensions': [
                        {'Name': DIM_TICKER, 'Value': ticker},
                        {'Name': DIM_OPERATION, 'Value': operation},
                        {'Name': DIM_ERROR_TYPE, 'Value': error_type}
                    ],
                    'Value': 1,
                    'Unit': UNIT_COUNT,
                    'Timestamp': datetime.utcnow()
                })

        if metric_data:
            cloudwatch.put_metric_data(
                Namespace=NAMESPACE,
                MetricData=metric_data
            )
    except Exception as e:
        print(f"Warning: Failed to publish batch metrics: {e}")
