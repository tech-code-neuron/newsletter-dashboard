#!/usr/bin/env python3
"""
Migration Script: Populate email_received_at from first_seen_at
================================================================
For records where email_received_at doesn't exist, copy first_seen_at value.

This ensures existing data displays correctly after removing first_seen_at
from the DTO fallback chain.

Usage:
    python3 scripts/migrate_first_seen_to_email_received.py --dry-run  # Preview changes
    python3 scripts/migrate_first_seen_to_email_received.py --execute  # Apply changes

Last Created: 2026-03-15
"""

import argparse
import boto3
from botocore.exceptions import ClientError
import sys
from datetime import datetime, timezone

# Table name
TABLE_NAME = 'reitsheet-reit-news-v2'


def get_records_missing_email_received_at(table):
    """
    Scan for records that have first_seen_at but not email_received_at.

    Returns:
        list: Records needing migration
    """
    from boto3.dynamodb.conditions import Attr

    print(f"Scanning {TABLE_NAME} for records missing email_received_at...")

    records = []
    scan_kwargs = {
        'FilterExpression': (
            Attr('first_seen_at').exists() &
            Attr('email_received_at').not_exists()
        ),
        'ProjectionExpression': '#url, ticker, title, first_seen_at',
        'ExpressionAttributeNames': {'#url': 'url'}
    }

    response = table.scan(**scan_kwargs)
    records.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.scan(**scan_kwargs)
        records.extend(response.get('Items', []))
        print(f"  ...scanned {len(records)} records so far")

    return records


def migrate_record(table, record, dry_run=True):
    """
    Copy first_seen_at to email_received_at for a single record.

    Args:
        table: DynamoDB table resource
        record: Record dict with url, first_seen_at
        dry_run: If True, only print what would happen

    Returns:
        bool: True if successful (or dry run)
    """
    url = record['url']
    first_seen_at = record.get('first_seen_at')
    ticker = record.get('ticker', 'UNKNOWN')

    if not first_seen_at:
        print(f"  SKIP: {ticker} - No first_seen_at to copy")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would set email_received_at={first_seen_at} for {ticker}: {url[:50]}...")
        return True

    try:
        table.update_item(
            Key={'url': url},
            UpdateExpression='SET email_received_at = :era',
            ExpressionAttributeValues={':era': first_seen_at},
            ConditionExpression='attribute_not_exists(email_received_at)'
        )
        print(f"  Migrated: {ticker} - {url[:50]}...")
        return True

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print(f"  SKIP: {ticker} - email_received_at already exists")
            return True
        else:
            print(f"  ERROR: {ticker} - {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Migrate first_seen_at to email_received_at'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Apply changes to database'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Limit number of records to migrate (0 = all)'
    )

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify --dry-run or --execute")
        print("  --dry-run: Preview changes without applying")
        print("  --execute: Apply changes to database")
        sys.exit(1)

    if args.dry_run and args.execute:
        print("ERROR: Cannot specify both --dry-run and --execute")
        sys.exit(1)

    dry_run = args.dry_run

    # Connect to DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(TABLE_NAME)

    # Find records needing migration
    records = get_records_missing_email_received_at(table)

    if not records:
        print("\nNo records need migration - all have email_received_at")
        return

    print(f"\nFound {len(records)} records missing email_received_at")

    if args.limit > 0:
        records = records[:args.limit]
        print(f"Limited to first {args.limit} records")

    # Migrate records
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating {len(records)} records...")

    success_count = 0
    error_count = 0

    for record in records:
        if migrate_record(table, record, dry_run=dry_run):
            success_count += 1
        else:
            error_count += 1

    # Summary
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete:")
    print(f"  Success: {success_count}")
    print(f"  Errors:  {error_count}")

    if dry_run:
        print("\nTo apply changes, run with --execute")


if __name__ == '__main__':
    main()
