"""
CloudWatch custom metrics helper for Brave News Fetcher.
"""

import boto3

cloudwatch = boto3.client("cloudwatch")

NAMESPACE = "ReitSheet/BraveNewsFetcher"


def emit_metric(metric_name: str, value: float, unit: str = "Count"):
    """
    Emit a custom CloudWatch metric.

    Args:
        metric_name: Name of the metric
        value: Numeric value
        unit: CloudWatch unit (Count, Milliseconds, etc.)
    """
    cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[
            {
                "MetricName": metric_name,
                "Value": value,
                "Unit": unit
            }
        ]
    )
