#!/usr/bin/env python3
"""
Timestamp Migration Script
==========================
Fixes existing DynamoDB records by adding email_received_at timestamp field.

Background:
- Old records only have press_release_date (date-only: '2026-03-11')
- New records have email_received_at (full timestamp: '2026-03-11T20:00:00+00:00')
- Flask app needs email_received_at to show actual time instead of midnight

Migration Strategy:
1. Scan all items in reitsheet-reit-news-v2 table
2. For each item without email_received_at:
   - Check if email_date field exists (from original email)
   - If yes: Extract timestamp from email_date
   - If no: Use first_seen_at as fallback (when email was processed)
3. Update item with email_received_at

Usage:
    python3 scripts/migrate_timestamps.py --dry-run     # Preview changes
    python3 scripts/migrate_timestamps.py --limit 10    # Test on 10 records
    python3 scripts/migrate_timestamps.py --execute     # Run migration

Author: Claude Code
Date: 2026-03-15
"""

import argparse
import boto3
from datetime import datetime, timezone
import sys
import os

# Add shared modules to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'infrastructure', 'lambdas', 'shared'))
from timestamp_utils import extract_timestamp_from_email_date

# ANSI colors
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'


def scan_table(table, limit=None):
    """
    Scan DynamoDB table and return all items

    Args:
        table: DynamoDB Table resource
        limit: Optional limit on number of items to scan

    Yields:
        dict: DynamoDB item
    """
    scan_kwargs = {}
    if limit:
        scan_kwargs['Limit'] = limit

    count = 0
    while True:
        response = table.scan(**scan_kwargs)

        for item in response.get('Items', []):
            yield item
            count += 1
            if limit and count >= limit:
                return

        # Check if there are more items to scan
        if 'LastEvaluatedKey' not in response:
            break

        if limit and count >= limit:
            break

        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']


def needs_migration(item):
    """
    Check if item needs migration

    Args:
        item: DynamoDB item

    Returns:
        bool: True if item needs email_received_at field
    """
    # Skip if already has email_received_at
    if 'email_received_at' in item:
        return False

    # Skip if no press_release_date (incomplete record)
    if 'press_release_date' not in item:
        return False

    return True


def extract_email_received_at(item):
    """
    Extract email_received_at timestamp from item

    Fallback chain:
    1. email_date field (RFC 2822 format from original email)
    2. first_seen_at field (when email was processed)
    3. None (skip migration)

    Args:
        item: DynamoDB item

    Returns:
        str: ISO 8601 timestamp, or None if extraction fails
    """
    # Try extracting from email_date (most accurate)
    if 'email_date' in item:
        email_received_at = extract_timestamp_from_email_date(item['email_date'])
        if email_received_at:
            return email_received_at

    # Fallback: Use first_seen_at (when email was processed)
    if 'first_seen_at' in item:
        # Check if first_seen_at already has time component
        first_seen_at = item['first_seen_at']
        if 'T' in first_seen_at:
            # Already has time component, use it
            return first_seen_at
        else:
            # Date-only, add noon ET as best guess
            return f"{first_seen_at}T12:00:00-05:00"

    # No suitable field found
    return None


def migrate_item(table, item, dry_run=True):
    """
    Migrate a single item by adding email_received_at field

    Args:
        table: DynamoDB Table resource
        item: DynamoDB item
        dry_run: If True, only preview changes without writing

    Returns:
        bool: True if migration succeeded (or would succeed in dry-run)
    """
    url = item.get('url', 'UNKNOWN')
    ticker = item.get('ticker', 'UNKNOWN')

    # Extract email_received_at
    email_received_at = extract_email_received_at(item)

    if not email_received_at:
        print(f"{YELLOW}⚠️  Skip: {ticker} - No timestamp source{RESET}")
        print(f"   URL: {url[:80]}...")
        return False

    # Preview change
    print(f"{CYAN}📝 {ticker}{RESET}")
    print(f"   URL: {url[:80]}...")
    print(f"   {CYAN}email_received_at:{RESET} {email_received_at}")

    if dry_run:
        print(f"   {YELLOW}(dry-run - not saved){RESET}")
        return True

    # Update item in DynamoDB
    try:
        table.update_item(
            Key={'url': url},
            UpdateExpression='SET email_received_at = :timestamp',
            ExpressionAttributeValues={
                ':timestamp': email_received_at
            }
        )
        print(f"   {GREEN}✅ Updated{RESET}")
        return True
    except Exception as e:
        print(f"   {RED}❌ Failed: {e}{RESET}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Migrate DynamoDB timestamp fields',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (dry-run)
  python3 scripts/migrate_timestamps.py --dry-run

  # Test on 10 records
  python3 scripts/migrate_timestamps.py --dry-run --limit 10

  # Execute migration
  python3 scripts/migrate_timestamps.py --execute

  # Execute migration with limit
  python3 scripts/migrate_timestamps.py --execute --limit 100
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true',
                       help='Preview changes without writing to DynamoDB')
    group.add_argument('--execute', action='store_true',
                       help='Execute migration (writes to DynamoDB)')

    parser.add_argument('--limit', type=int,
                        help='Limit number of items to process (for testing)')

    parser.add_argument('--table', default='reitsheet-reit-news-v2',
                        help='DynamoDB table name (default: reitsheet-reit-news-v2)')

    args = parser.parse_args()

    # Initialize DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(args.table)

    print("=" * 60)
    print(f"Timestamp Migration - {args.table}")
    print("=" * 60)
    print(f"Mode: {'DRY-RUN (preview only)' if args.dry_run else 'EXECUTE (will write to DynamoDB)'}")
    if args.limit:
        print(f"Limit: {args.limit} items")
    print()

    if args.execute:
        print(f"{RED}⚠️  WARNING: This will modify DynamoDB records!{RESET}")
        print(f"Press Ctrl+C to cancel, or Enter to continue...")
        input()

    # Scan table
    print(f"Scanning {args.table}...")
    items_scanned = 0
    items_needing_migration = 0
    items_migrated = 0
    items_failed = 0

    for item in scan_table(table, limit=args.limit):
        items_scanned += 1

        if not needs_migration(item):
            continue

        items_needing_migration += 1

        # Migrate item
        success = migrate_item(table, item, dry_run=args.dry_run)

        if success:
            items_migrated += 1
        else:
            items_failed += 1

        print()  # Blank line between items

    # Summary
    print("=" * 60)
    print(f"Migration Summary")
    print("=" * 60)
    print(f"Items scanned: {items_scanned}")
    print(f"Items needing migration: {items_needing_migration}")
    print(f"Items {'would be' if args.dry_run else ''} migrated: {items_migrated}")
    if items_failed > 0:
        print(f"{RED}Items failed: {items_failed}{RESET}")
    print()

    if args.dry_run and items_needing_migration > 0:
        print(f"{YELLOW}This was a dry-run. Run with --execute to apply changes.{RESET}")
    elif args.execute and items_migrated > 0:
        print(f"{GREEN}✅ Migration complete!{RESET}")
    elif items_needing_migration == 0:
        print(f"{GREEN}✅ No items need migration - database is up to date!{RESET}")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Migration cancelled by user{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
