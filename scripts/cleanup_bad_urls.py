#!/usr/bin/env python3
"""
Cleanup script to remove bad URLs from reit_news table.

Removes:
- Landing page URLs (https://www.realtyincome.com/investors/press-releases)
- Unresolved tracking URLs (email.investis.com)
- Any other specified patterns

Usage:
    python3 cleanup_bad_urls.py [--dry-run] [--ticker TICKER]
"""

import boto3
import argparse
from typing import List, Dict

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('reitsheet-reit-news')

def scan_bad_urls(ticker: str = None, dry_run: bool = False) -> List[Dict]:
    """Scan for bad URLs in the database."""

    # Build filter expression
    filter_parts = []
    expr_attr_values = {}
    expr_attr_names = {'#url': 'url'}

    # Bad URL patterns
    bad_patterns = [
        ('https://www.realtyincome.com/investors/press-releases', 'exact'),
        ('email.investis.com', 'contains'),
        ('url9490.notification.gcs-web.com', 'contains'),
    ]

    # Add ticker filter if specified
    if ticker:
        filter_parts.append('ticker = :ticker')
        expr_attr_values[':ticker'] = ticker

    # Add URL pattern filters
    pattern_filters = []
    for i, (pattern, match_type) in enumerate(bad_patterns):
        if match_type == 'exact':
            pattern_filters.append(f'#url = :pattern{i}')
            expr_attr_values[f':pattern{i}'] = pattern
        elif match_type == 'contains':
            pattern_filters.append(f'contains(#url, :pattern{i})')
            expr_attr_values[f':pattern{i}'] = pattern

    if pattern_filters:
        filter_parts.append(f"({' OR '.join(pattern_filters)})")

    filter_expression = ' AND '.join(filter_parts) if filter_parts else None

    # Scan table
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, #url, first_seen_at',
        'ExpressionAttributeNames': expr_attr_names,
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

def find_duplicates(ticker: str = None) -> List[Dict]:
    """Find exact duplicate entries (same ticker + URL)."""

    # Scan entire table
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, #url, first_seen_at',
        'ExpressionAttributeNames': {'#url': 'url'},
    }

    if ticker:
        scan_kwargs['FilterExpression'] = 'ticker = :ticker'
        scan_kwargs['ExpressionAttributeValues'] = {':ticker': ticker}

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

def delete_items(items: List[Dict], dry_run: bool = False) -> int:
    """Delete items from the database."""

    deleted_count = 0

    for item in items:
        press_release_id = item['press_release_id']
        first_seen_at = item['first_seen_at']  # Range key required for deletion
        ticker = item.get('ticker', 'UNKNOWN')
        url = item.get('url', '')
        title = item.get('title', 'No title')[:50]

        if dry_run:
            print(f"[DRY RUN] Would delete: {ticker} | {press_release_id} | {title}... | {url[:80]}...")
        else:
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

def main():
    parser = argparse.ArgumentParser(description='Clean up bad URLs from reit_news table')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    parser.add_argument('--ticker', type=str, help='Filter by ticker (e.g., O for Realty Income)')
    parser.add_argument('--duplicates-only', action='store_true', help='Only find and remove duplicates')
    parser.add_argument('--auto', action='store_true', help='Run without confirmation (for automated cleanup)')
    args = parser.parse_args()

    total_deleted = 0

    # Find duplicates
    if not args.duplicates_only:
        print(f"🔍 Scanning for bad URLs...")
        if args.ticker:
            print(f"   Filtering by ticker: {args.ticker}")
        if args.dry_run:
            print(f"   DRY RUN MODE - no changes will be made")
        print()

        # Find bad URLs
        bad_items = scan_bad_urls(ticker=args.ticker, dry_run=args.dry_run)

        if bad_items:
            print(f"Found {len(bad_items)} bad URLs:\n")

            # Group by ticker for summary
            by_ticker = {}
            for item in bad_items:
                ticker = item.get('ticker', 'UNKNOWN')
                by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

            print("Summary by ticker:")
            for ticker, count in sorted(by_ticker.items()):
                print(f"  {ticker}: {count}")
            print()

            # Delete items
            if args.dry_run:
                print("\nBad URLs to delete:\n")
                delete_items(bad_items, dry_run=True)
            else:
                if args.auto:
                    deleted = delete_items(bad_items, dry_run=False)
                    total_deleted += deleted
                    print(f"\n✅ Deleted {deleted} bad URLs")
                else:
                    confirm = input(f"\n⚠️  Delete {len(bad_items)} bad URLs? (yes/no): ")
                    if confirm.lower() == 'yes':
                        deleted = delete_items(bad_items, dry_run=False)
                        total_deleted += deleted
                        print(f"\n✅ Deleted {deleted} bad URLs")
                    else:
                        print("❌ Cancelled bad URL cleanup")
        else:
            print("✨ No bad URLs found!")

    # Find duplicates
    print(f"\n🔍 Scanning for duplicates...")
    if args.ticker:
        print(f"   Filtering by ticker: {args.ticker}")
    print()

    duplicate_items = find_duplicates(ticker=args.ticker)

    if duplicate_items:
        print(f"Found {len(duplicate_items)} duplicate entries:\n")

        # Group by ticker for summary
        by_ticker = {}
        for item in duplicate_items:
            ticker = item.get('ticker', 'UNKNOWN')
            by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

        print("Summary by ticker:")
        for ticker, count in sorted(by_ticker.items()):
            print(f"  {ticker}: {count}")
        print()

        # Delete items
        if args.dry_run:
            print("\nDuplicates to delete (keeping oldest):\n")
            delete_items(duplicate_items, dry_run=True)
            print(f"\n✅ Dry run complete. Run without --dry-run to actually delete.")
        else:
            if args.auto:
                deleted = delete_items(duplicate_items, dry_run=False)
                total_deleted += deleted
                print(f"\n✅ Deleted {deleted} duplicates")
            else:
                confirm = input(f"\n⚠️  Delete {len(duplicate_items)} duplicates? (yes/no): ")
                if confirm.lower() == 'yes':
                    deleted = delete_items(duplicate_items, dry_run=False)
                    total_deleted += deleted
                    print(f"\n✅ Deleted {deleted} duplicates")
                else:
                    print("❌ Cancelled duplicate cleanup")
    else:
        print("✨ No duplicates found!")

    if total_deleted > 0:
        print(f"\n🎉 Total cleaned up: {total_deleted} items")

if __name__ == '__main__':
    main()
