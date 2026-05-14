#!/usr/bin/env python3
"""
CTA Performance Report

Generates a report of CTA click performance from DynamoDB.
Groups by cta_id and device_type for the last 7 days.

Usage:
    python3 scripts/cta_report.py
    python3 scripts/cta_report.py --days 30
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Key, Attr


def get_cta_clicks(days: int = 7) -> list:
    """
    Query DynamoDB for CTA clicks in the last N days.

    Args:
        days: Number of days to look back

    Returns:
        List of click records
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('reitsheet-cta-analytics')

    # Calculate cutoff timestamp
    cutoff = datetime.now(ZoneInfo('UTC')) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    # Scan with filter (no GSI on server_timestamp)
    # For production, consider adding a GSI on server_timestamp
    all_items = []
    last_key = None

    while True:
        scan_kwargs = {
            'FilterExpression': Attr('server_timestamp').gte(cutoff_iso)
        }
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = last_key

        response = table.scan(**scan_kwargs)
        all_items.extend(response.get('Items', []))

        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break

    return all_items


def generate_report(clicks: list) -> None:
    """
    Generate and print CTA performance report.

    Args:
        clicks: List of click records from DynamoDB
    """
    if not clicks:
        print("No CTA clicks found in the specified time period.")
        return

    # Group by cta_id and device_type
    stats = defaultdict(lambda: {'desktop': 0, 'mobile': 0, 'total': 0})

    for click in clicks:
        cta_id = click.get('cta_id', 'unknown')
        device_type = click.get('device_type', 'desktop')

        stats[cta_id][device_type] += 1
        stats[cta_id]['total'] += 1

    # Sort by total clicks descending
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)

    # Print report
    print("\n" + "=" * 70)
    print("CTA PERFORMANCE REPORT")
    print("=" * 70)
    print(f"\nTotal clicks: {len(clicks)}")
    print(f"Unique CTAs: {len(stats)}")
    print()

    # Table header
    print(f"{'CTA ID':<30} {'Desktop':>10} {'Mobile':>10} {'Total':>10}")
    print("-" * 70)

    for cta_id, counts in sorted_stats:
        print(f"{cta_id:<30} {counts['desktop']:>10} {counts['mobile']:>10} {counts['total']:>10}")

    print("-" * 70)

    # Summary
    total_desktop = sum(s['desktop'] for _, s in sorted_stats)
    total_mobile = sum(s['mobile'] for _, s in sorted_stats)
    print(f"{'TOTAL':<30} {total_desktop:>10} {total_mobile:>10} {len(clicks):>10}")

    # Device breakdown
    print(f"\nDevice breakdown:")
    print(f"  Desktop: {total_desktop} ({total_desktop/len(clicks)*100:.1f}%)")
    print(f"  Mobile:  {total_mobile} ({total_mobile/len(clicks)*100:.1f}%)")

    # Top pages
    page_counts = defaultdict(int)
    for click in clicks:
        page_counts[click.get('page', 'unknown')] += 1

    print(f"\nTop pages by clicks:")
    for page, count in sorted(page_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {page}: {count}")

    print()


def main():
    parser = argparse.ArgumentParser(description='Generate CTA performance report')
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze (default: 7)')
    args = parser.parse_args()

    try:
        print(f"Fetching CTA clicks from the last {args.days} days...")
        clicks = get_cta_clicks(days=args.days)
        generate_report(clicks)
    except Exception as e:
        if 'ResourceNotFoundException' in str(e):
            print("Error: DynamoDB table 'reitsheet-cta-analytics' does not exist.")
            print("Create the table first or wait for Terraform deployment.")
            sys.exit(1)
        else:
            print(f"Error: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
