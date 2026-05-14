#!/usr/bin/env python3
"""
Analyze Reprocessing Results
=============================
Check how many activation emails were filtered vs press releases saved
"""

import boto3
from collections import Counter

# ============================================================================
# Configuration
# ============================================================================

PROJECT_NAME = 'reitsheet'
INBOUND_LOG_TABLE = f'{PROJECT_NAME}-inbound-log'
REIT_NEWS_TABLE = f'{PROJECT_NAME}-reit-news'

# ============================================================================
# AWS Clients
# ============================================================================

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

inbound_log_table = dynamodb.Table(INBOUND_LOG_TABLE)
reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)

# ============================================================================
# Analysis
# ============================================================================

def analyze_results():
    """Analyze reprocessing results"""
    print("\n" + "=" * 80)
    print("REPROCESSING RESULTS ANALYSIS")
    print("=" * 80)
    print()

    # Scan inbound log
    print("📊 Scanning inbound log...")
    response = inbound_log_table.scan()
    items = response.get('Items', [])

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = inbound_log_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    # Count by routing
    routing_counts = Counter()
    skipped_subjects = []

    for item in items:
        routing = item.get('routing', 'unknown')
        routing_counts[routing] += 1

        if routing == 'skipped_confirmation':
            subject = item.get('subject', 'No subject')
            skipped_subjects.append(subject)

    # Count press releases
    print("📊 Scanning press releases...")
    pr_response = reit_news_table.scan()
    press_releases = pr_response.get('Items', [])

    while 'LastEvaluatedKey' in pr_response:
        pr_response = reit_news_table.scan(ExclusiveStartKey=pr_response['LastEvaluatedKey'])
        press_releases.extend(pr_response.get('Items', []))

    # Print results
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()

    print(f"Total Emails Processed: {len(items)}")
    print()

    print("Routing Breakdown:")
    print("-" * 80)
    for routing, count in sorted(routing_counts.items(), key=lambda x: -x[1]):
        pct = (count / len(items) * 100) if items else 0
        print(f"  {routing:30s}: {count:3d} emails ({pct:5.1f}%)")

    print()
    print(f"Press Releases Saved: {len(press_releases)}")
    print()

    # Validation
    print("=" * 80)
    print("VALIDATION")
    print("=" * 80)
    print()

    activation_count = routing_counts.get('skipped_confirmation', 0)
    expected_activation = 120

    if activation_count >= expected_activation - 10 and activation_count <= expected_activation + 10:
        print(f"✅ Activation Filter: {activation_count} emails (expected ~{expected_activation}) ✓")
    else:
        print(f"❌ Activation Filter: {activation_count} emails (expected ~{expected_activation}) ✗")

    if len(press_releases) > 0 and len(press_releases) < 30:
        print(f"✅ Press Releases: {len(press_releases)} saved (reasonable) ✓")
    elif len(press_releases) == 0:
        print(f"⚠️  Press Releases: 0 saved (check for issues)")
    else:
        print(f"⚠️  Press Releases: {len(press_releases)} saved (higher than expected)")

    # Sample activation emails
    if skipped_subjects:
        print()
        print("=" * 80)
        print("SAMPLE ACTIVATION EMAILS (first 10)")
        print("=" * 80)
        print()
        for i, subject in enumerate(skipped_subjects[:10], 1):
            print(f"{i:2d}. {subject[:76]}")

    # Sample press releases
    if press_releases:
        print()
        print("=" * 80)
        print("PRESS RELEASES SAVED")
        print("=" * 80)
        print()
        for i, pr in enumerate(press_releases[:20], 1):
            ticker = pr.get('ticker', 'UNK')
            url = pr.get('url', '')[:70]
            source = pr.get('source', 'unknown')
            print(f"{i:2d}. {ticker:6s} | {source:20s} | {url}")

    print()


if __name__ == '__main__':
    analyze_results()
