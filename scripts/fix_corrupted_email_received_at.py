#!/usr/bin/env python3
"""
Fix Corrupted email_received_at Values

Problem: Migration script copied first_seen_at → email_received_at, but first_seen_at
was already wrong (Lambda processing time, not actual email receipt time).

Solution: DELETE email_received_at where it equals first_seen_at (corrupted).
The DTO will then fall back to press_release_date which is correct.

Usage:
    python3 scripts/fix_corrupted_email_received_at.py --dry-run   # Preview changes
    python3 scripts/fix_corrupted_email_received_at.py --execute   # Apply changes
"""

import argparse
import boto3
from datetime import datetime


def get_table():
    """Get DynamoDB table resource."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    return dynamodb.Table('reitsheet-reit-news-v2')


def scan_corrupted_records(table):
    """
    Find records where email_received_at equals first_seen_at (corrupted).

    These are corrupted because:
    - first_seen_at = Lambda processing time (WRONG)
    - email_received_at was copied from first_seen_at (also WRONG)
    - press_release_date is correct (we want DTO to use this)
    """
    corrupted = []

    # Scan all records
    response = table.scan()
    items = response.get('Items', [])

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    print(f"Scanned {len(items)} total records")

    for item in items:
        email_received_at = item.get('email_received_at')
        first_seen_at = item.get('first_seen_at')
        press_release_date = item.get('press_release_date')

        # Skip if no email_received_at (nothing to delete)
        if not email_received_at:
            continue

        # Skip if no first_seen_at (can't compare)
        if not first_seen_at:
            continue

        # Check if email_received_at equals first_seen_at (corrupted)
        # They might be exactly equal or very close (within seconds)
        if email_received_at == first_seen_at:
            corrupted.append({
                'url': item.get('url'),  # Primary key
                'ticker': item.get('ticker'),
                'press_release_date': press_release_date,
                'email_received_at': email_received_at,
                'first_seen_at': first_seen_at,
                'title': item.get('title', '')[:50],
            })

    return corrupted


def delete_email_received_at(table, records, dry_run=True):
    """
    Delete email_received_at attribute from corrupted records.

    After deletion, the DTO will fall back to press_release_date (correct).
    """
    if dry_run:
        print("\n=== DRY RUN - No changes will be made ===\n")
    else:
        print("\n=== EXECUTING - Deleting corrupted email_received_at values ===\n")

    fixed_count = 0

    for record in records:
        url = record['url']
        ticker = record['ticker']
        pr_date = record['press_release_date']
        email_at = record['email_received_at']
        title = record['title']

        print(f"{ticker} | PR: {pr_date} | email_received_at: {email_at}")
        print(f"  Title: {title}...")

        if not dry_run:
            # Delete email_received_at attribute (url is the primary key)
            table.update_item(
                Key={'url': url},
                UpdateExpression='REMOVE email_received_at',
            )
            print(f"  -> DELETED email_received_at (will use press_release_date: {pr_date})")
        else:
            print(f"  -> Would delete email_received_at (fallback to press_release_date: {pr_date})")

        print()
        fixed_count += 1

    return fixed_count


def main():
    parser = argparse.ArgumentParser(
        description='Delete corrupted email_received_at values that equal first_seen_at'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Apply changes to DynamoDB'
    )

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Error: Must specify either --dry-run or --execute")
        print("\nUsage:")
        print("  python3 scripts/fix_corrupted_email_received_at.py --dry-run   # Preview")
        print("  python3 scripts/fix_corrupted_email_received_at.py --execute   # Apply")
        return 1

    if args.dry_run and args.execute:
        print("Error: Cannot specify both --dry-run and --execute")
        return 1

    print("=" * 60)
    print("Fix Corrupted email_received_at Values")
    print("=" * 60)
    print()
    print("Strategy:")
    print("  1. Find records where email_received_at == first_seen_at (corrupted)")
    print("  2. DELETE email_received_at attribute from those records")
    print("  3. DTO will fall back to press_release_date (correct)")
    print()

    table = get_table()

    print("Scanning for corrupted records...")
    corrupted = scan_corrupted_records(table)

    if not corrupted:
        print("\nNo corrupted records found. Nothing to fix.")
        return 0

    print(f"\nFound {len(corrupted)} corrupted records:\n")

    fixed = delete_email_received_at(table, corrupted, dry_run=args.dry_run)

    print("=" * 60)
    if args.dry_run:
        print(f"DRY RUN COMPLETE: Would fix {fixed} records")
        print("\nTo apply changes, run:")
        print("  python3 scripts/fix_corrupted_email_received_at.py --execute")
    else:
        print(f"EXECUTION COMPLETE: Fixed {fixed} records")
        print("\nVerify by reloading the publisher page - dates should now be correct.")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    exit(main())
