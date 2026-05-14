#!/usr/bin/env python3
"""
Fix Remaining Press Release Dates

For records without emails in S3, use first_seen_at as the press_release_date.
This is the best fallback since we don't have the original email content.
"""

import boto3
import argparse

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('reitsheet-reit-news')


def fix_remaining_dates(dry_run=False):
    """Fix all records with missing or default press_release_date."""

    print("🔍 Scanning for records with incorrect dates...")
    if dry_run:
        print("   DRY RUN MODE - no updates will be made\n")

    # Scan all records
    response = table.scan(
        ProjectionExpression='press_release_id, ticker, title, first_seen_at, press_release_date'
    )

    items = response.get('Items', [])

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            ProjectionExpression='press_release_id, ticker, title, first_seen_at, press_release_date',
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))

    print(f"Found {len(items)} total records\n")

    # Find records that need fixing
    items_to_fix = []
    for item in items:
        pr_date = item.get('press_release_date')
        first_seen = item.get('first_seen_at', '')[:10]

        # Fix if no date OR if date matches first_seen (default value)
        if not pr_date or pr_date == first_seen:
            items_to_fix.append(item)

    if not items_to_fix:
        print("✨ All records already have press release dates!")
        return

    print(f"Found {len(items_to_fix)} records to fix\n")

    updated_count = 0
    failed_count = 0

    for i, item in enumerate(items_to_fix, 1):
        press_release_id = item['press_release_id']
        first_seen_at = item['first_seen_at']
        ticker = item.get('ticker', 'UNKNOWN')
        title = item.get('title', '')[:50]

        # Use first_seen_at date as the press_release_date
        fallback_date = first_seen_at[:10] if first_seen_at else '2026-03-01'

        print(f"[{i}/{len(items_to_fix)}] {ticker} | {title}...")
        print(f"  → Setting date to: {fallback_date}")

        if dry_run:
            print(f"  [DRY RUN] Would update record")
            updated_count += 1
        else:
            try:
                table.update_item(
                    Key={
                        'press_release_id': press_release_id,
                        'first_seen_at': first_seen_at
                    },
                    UpdateExpression='SET press_release_date = :date',
                    ExpressionAttributeValues={
                        ':date': fallback_date
                    }
                )
                print(f"  ✓ Updated")
                updated_count += 1
            except Exception as e:
                print(f"  ❌ Error: {e}")
                failed_count += 1

    print()
    if dry_run:
        print(f"✅ Dry run complete. {updated_count} records would be updated.")
    else:
        print(f"✅ Fix complete!")
        print(f"   Updated: {updated_count}")
        print(f"   Failed: {failed_count}")


def main():
    parser = argparse.ArgumentParser(description='Fix remaining press release dates')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated')
    args = parser.parse_args()

    fix_remaining_dates(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
