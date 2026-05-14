#!/usr/bin/env python3
"""
Fix Press Release Dates
=======================
Fix date mismatches and deduplicate records identified by audit.

Actions:
1. Update press_release_date to correct value (from email header)
2. Delete enricher duplicate when RSS record exists for same URL

Usage:
    python scripts/fix_press_release_dates.py --dry-run       # Preview changes
    python scripts/fix_press_release_dates.py --apply         # Apply changes
    python scripts/fix_press_release_dates.py --csv report.csv --apply

Author: Claude Code
Date: 2026-03-15
"""

import argparse
import boto3
import csv
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from collections import defaultdict

# AWS Configuration
REIT_NEWS_TABLE = 'reitsheet-reit-news-v2'
S3_BUCKET = 'reitsheet-email-ingest'

# Initialize clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)


def load_audit_report(csv_file):
    """
    Load audit report from CSV file.

    Returns:
        list: Records with date mismatches
    """
    records = []
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('is_mismatch') == 'True':
                    records.append(row)
    except FileNotFoundError:
        print(f"CSV file not found: {csv_file}")
        return []

    return records


def find_all_records_for_url(url):
    """
    Find all DynamoDB records for a URL.

    The V2 schema uses URL as primary key, so there should only be one.
    But let's verify.
    """
    try:
        response = reit_news_table.get_item(Key={'url': url})
        item = response.get('Item')
        return [item] if item else []
    except Exception as e:
        print(f"   Error querying URL: {e}")
        return []


def scan_for_duplicates(month_prefix='2026-03'):
    """
    Scan for URLs with multiple records (RSS + enricher).

    In V2 schema, URL is primary key so true duplicates shouldn't exist.
    But there may be records from before migration.
    """
    print("Scanning for potential duplicates...")

    # Group by ticker + title (same PR, different sources)
    by_ticker_title = defaultdict(list)

    scan_kwargs = {}
    if month_prefix:
        scan_kwargs['FilterExpression'] = 'begins_with(press_release_date, :month)'
        scan_kwargs['ExpressionAttributeValues'] = {':month': month_prefix}

    while True:
        response = reit_news_table.scan(**scan_kwargs)
        for item in response.get('Items', []):
            ticker = item.get('ticker', 'UNKNOWN')
            title = item.get('title', '')[:50]  # First 50 chars
            key = f"{ticker}:{title}"
            by_ticker_title[key].append(item)

        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    # Find groups with multiple records
    duplicates = {k: v for k, v in by_ticker_title.items() if len(v) > 1}
    print(f"   Found {len(duplicates)} ticker/title combinations with multiple records")

    return duplicates


def fix_date_mismatch(url, correct_date, dry_run=True):
    """
    Update press_release_date for a record.

    Args:
        url: Primary key (URL)
        correct_date: Correct date in YYYY-MM-DD format
        dry_run: If True, only preview the change

    Returns:
        bool: Success
    """
    try:
        if dry_run:
            print(f"   [DRY RUN] Would update: {url[:60]}...")
            print(f"            New date: {correct_date}")
            return True

        reit_news_table.update_item(
            Key={'url': url},
            UpdateExpression='SET press_release_date = :date, date_corrected_at = :now',
            ExpressionAttributeValues={
                ':date': correct_date,
                ':now': datetime.utcnow().isoformat()
            }
        )
        print(f"   Updated: {url[:60]}... -> {correct_date}")
        return True

    except Exception as e:
        print(f"   Error updating {url[:60]}...: {e}")
        return False


def delete_enricher_duplicate(url, dry_run=True):
    """
    Delete an enricher record when RSS record exists.

    Args:
        url: Primary key (URL) of enricher record to delete
        dry_run: If True, only preview the deletion

    Returns:
        bool: Success
    """
    try:
        if dry_run:
            print(f"   [DRY RUN] Would delete enricher duplicate: {url[:60]}...")
            return True

        reit_news_table.delete_item(Key={'url': url})
        print(f"   Deleted: {url[:60]}...")
        return True

    except Exception as e:
        print(f"   Error deleting {url[:60]}...: {e}")
        return False


def process_duplicates(duplicates, dry_run=True):
    """
    Process duplicate groups - keep RSS, delete enricher.

    Args:
        duplicates: Dict of ticker:title -> list of records
        dry_run: If True, only preview changes

    Returns:
        tuple: (deleted_count, kept_count)
    """
    deleted = 0
    kept = 0

    for key, records in duplicates.items():
        # Sort by source priority: RSS > enricher
        rss_records = [r for r in records if r.get('source') == 'company_rss']
        enricher_records = [r for r in records if r.get('source') == 'enricher_validated']

        if rss_records and enricher_records:
            # Keep RSS, delete enricher
            print(f"\nDuplicate: {key}")
            print(f"   RSS records: {len(rss_records)} (keep)")
            print(f"   Enricher records: {len(enricher_records)} (delete)")

            for rec in enricher_records:
                if delete_enricher_duplicate(rec['url'], dry_run):
                    deleted += 1

            kept += len(rss_records)

    return deleted, kept


def extract_date_from_email_date(email_date_str):
    """
    Extract YYYY-MM-DD from RFC 2822 email Date header.
    """
    if not email_date_str:
        return None
    try:
        dt = parsedate_to_datetime(email_date_str)
        return dt.strftime('%Y-%m-%d')
    except:
        return None


def fix_mismatches_from_email_date(month_prefix='2026-03', dry_run=True):
    """
    Fix date mismatches using stored email_date field.

    For records that have email_date stored, use it to correct press_release_date.
    """
    print(f"\nScanning for mismatches with stored email_date...")

    fixed = 0
    skipped = 0

    scan_kwargs = {
        'FilterExpression': 'begins_with(press_release_date, :month) AND attribute_exists(email_date)',
        'ExpressionAttributeValues': {':month': month_prefix}
    }

    while True:
        response = reit_news_table.scan(**scan_kwargs)

        for item in response.get('Items', []):
            url = item.get('url')
            stored_date = item.get('press_release_date')
            email_date = item.get('email_date')
            ticker = item.get('ticker')

            # Extract correct date from email_date
            correct_date = extract_date_from_email_date(email_date)

            if correct_date and correct_date != stored_date:
                print(f"\n{ticker}: {stored_date} -> {correct_date}")
                if fix_date_mismatch(url, correct_date, dry_run):
                    fixed += 1
            else:
                skipped += 1

        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    print(f"\n   Fixed: {fixed}")
    print(f"   Skipped (date matched or no email_date): {skipped}")

    return fixed


def main():
    parser = argparse.ArgumentParser(description='Fix press release date mismatches')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Preview changes without applying (default)')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply the changes')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompt')
    parser.add_argument('--csv', help='Load audit report from CSV')
    parser.add_argument('--month', default='2026-03', help='Month to fix (YYYY-MM)')
    parser.add_argument('--fix-from-email-date', action='store_true',
                        help='Fix dates using stored email_date field')
    parser.add_argument('--dedupe', action='store_true',
                        help='Deduplicate records (delete enricher when RSS exists)')
    args = parser.parse_args()

    dry_run = not args.apply

    print("=" * 60)
    print("PRESS RELEASE DATE FIX")
    print("=" * 60)
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'APPLY CHANGES'}")
    print(f"Month: {args.month}")
    print()

    if args.apply and not args.yes:
        confirm = input("This will modify DynamoDB records. Type 'yes' to continue: ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return 1

    # Process based on options
    total_fixed = 0
    total_deleted = 0

    # Option 1: Fix from CSV audit report
    if args.csv:
        print(f"\nLoading audit report: {args.csv}")
        mismatches = load_audit_report(args.csv)
        print(f"   Found {len(mismatches)} mismatches")

        for record in mismatches:
            url = record.get('url', '').rstrip('...')  # Remove truncation
            expected_date = record.get('expected_date')

            if expected_date and expected_date != 'N/A':
                if fix_date_mismatch(url, expected_date, dry_run):
                    total_fixed += 1

    # Option 2: Fix from email_date field
    if args.fix_from_email_date:
        fixed = fix_mismatches_from_email_date(args.month, dry_run)
        total_fixed += fixed

    # Option 3: Deduplicate
    if args.dedupe:
        duplicates = scan_for_duplicates(args.month)
        deleted, _ = process_duplicates(duplicates, dry_run)
        total_deleted += deleted

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Dates fixed: {total_fixed}")
    print(f"Duplicates deleted: {total_deleted}")

    if dry_run:
        print("\nThis was a DRY RUN. Use --apply to make changes.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
