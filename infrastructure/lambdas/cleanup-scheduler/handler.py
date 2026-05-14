"""
Automated cleanup Lambda - runs daily to remove bad URLs and duplicates.

This Lambda function:
1. Scans reit_news table for bad URL patterns (landing pages, tracking URLs)
2. Finds exact duplicates (same ticker + URL)
3. Deletes bad URLs and duplicates automatically
4. Sends summary to CloudWatch Logs
"""

import json
import boto3
import os
from decimal import Decimal
from typing import List, Dict

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('REIT_NEWS_TABLE', 'reitsheet-reit-news'))

# Bad URL patterns to detect
BAD_PATTERNS = [
    ('https://www.realtyincome.com/investors/press-releases', 'exact'),
    ('email.investis.com', 'contains'),
    ('url9490.notification.gcs-web.com', 'contains'),
]

def scan_bad_urls() -> List[Dict]:
    """Scan for bad URLs in the database."""

    # Build filter expression for bad patterns
    pattern_filters = []
    expr_attr_values = {}

    for i, (pattern, match_type) in enumerate(BAD_PATTERNS):
        if match_type == 'exact':
            pattern_filters.append(f'#url = :pattern{i}')
            expr_attr_values[f':pattern{i}'] = pattern
        elif match_type == 'contains':
            pattern_filters.append(f'contains(#url, :pattern{i})')
            expr_attr_values[f':pattern{i}'] = pattern

    filter_expression = ' OR '.join(pattern_filters) if pattern_filters else None

    # Scan table
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, #url, first_seen_at',
        'ExpressionAttributeNames': {'#url': 'url'},
    }

    if filter_expression:
        scan_kwargs['FilterExpression'] = filter_expression
    if expr_attr_values:
        scan_kwargs['ExpressionAttributeValues'] = expr_attr_values

    items = []
    response = table.scan(**scan_kwargs)
    items.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))

    return items

def find_duplicates() -> List[Dict]:
    """Find exact duplicate entries (same ticker + URL)."""

    # Scan entire table
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, #url, first_seen_at',
        'ExpressionAttributeNames': {'#url': 'url'},
    }

    items = []
    response = table.scan(**scan_kwargs)
    items.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))

    # Group by (ticker, url) to find duplicates
    grouped = {}
    for item in items:
        key = (item.get('ticker', ''), item.get('url', ''))
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)

    # Find groups with more than one item (duplicates)
    duplicates_to_delete = []
    for key, group in grouped.items():
        if len(group) > 1:
            # Sort by first_seen_at (oldest first)
            group.sort(key=lambda x: x.get('first_seen_at', ''))
            # Keep the oldest, mark the rest for deletion
            duplicates_to_delete.extend(group[1:])  # Skip first (oldest)

    return duplicates_to_delete

def delete_items(items: List[Dict]) -> int:
    """Delete items from the database."""

    deleted_count = 0

    for item in items:
        press_release_id = item['press_release_id']
        first_seen_at = item['first_seen_at']
        ticker = item.get('ticker', 'UNKNOWN')

        try:
            table.delete_item(
                Key={
                    'press_release_id': press_release_id,
                    'first_seen_at': first_seen_at
                }
            )
            print(f"✅ Deleted: {ticker} | {press_release_id}")
            deleted_count += 1
        except Exception as e:
            print(f"❌ Error deleting {press_release_id}: {e}")

    return deleted_count

def handler(event, context):
    """Lambda handler for automated cleanup."""

    print("🧹 Starting automated cleanup...")
    print()

    total_deleted = 0
    summary = {
        'bad_urls_deleted': 0,
        'duplicates_deleted': 0,
        'total_deleted': 0,
        'errors': []
    }

    # Step 1: Find and delete bad URLs
    print("🔍 Scanning for bad URLs...")
    try:
        bad_items = scan_bad_urls()

        if bad_items:
            print(f"Found {len(bad_items)} bad URLs")

            # Group by ticker for summary
            by_ticker = {}
            for item in bad_items:
                ticker = item.get('ticker', 'UNKNOWN')
                by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

            print("Summary by ticker:")
            for ticker, count in sorted(by_ticker.items()):
                print(f"  {ticker}: {count}")

            deleted = delete_items(bad_items)
            summary['bad_urls_deleted'] = deleted
            total_deleted += deleted
            print(f"✅ Deleted {deleted} bad URLs")
        else:
            print("✨ No bad URLs found")
    except Exception as e:
        print(f"❌ Error in bad URL cleanup: {e}")
        summary['errors'].append(f"Bad URL cleanup: {str(e)}")

    print()

    # Step 2: Find and delete duplicates
    print("🔍 Scanning for duplicates...")
    try:
        duplicate_items = find_duplicates()

        if duplicate_items:
            print(f"Found {len(duplicate_items)} duplicates")

            # Group by ticker for summary
            by_ticker = {}
            for item in duplicate_items:
                ticker = item.get('ticker', 'UNKNOWN')
                by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

            print("Summary by ticker:")
            for ticker, count in sorted(by_ticker.items()):
                print(f"  {ticker}: {count}")

            deleted = delete_items(duplicate_items)
            summary['duplicates_deleted'] = deleted
            total_deleted += deleted
            print(f"✅ Deleted {deleted} duplicates")
        else:
            print("✨ No duplicates found")
    except Exception as e:
        print(f"❌ Error in duplicate cleanup: {e}")
        summary['errors'].append(f"Duplicate cleanup: {str(e)}")

    print()
    summary['total_deleted'] = total_deleted

    if total_deleted > 0:
        print(f"🎉 Cleanup complete: {total_deleted} items removed")
    else:
        print("✨ Database is clean - no items removed")

    return {
        'statusCode': 200,
        'body': json.dumps(summary)
    }
