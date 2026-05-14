#!/usr/bin/env python3
"""
Backfill Press Release Dates from Emails

Reads all DynamoDB records, fetches corresponding emails from S3,
extracts press release dates from email body, and updates DynamoDB.

Usage:
    python3 backfill_dates_from_emails.py [--dry-run] [--limit N] [--ticker TICKER]
"""

import boto3
import re
import argparse
from datetime import datetime
from typing import Optional

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

TABLE_NAME = 'reitsheet-reit-news'
INBOUND_LOG_TABLE = 'reitsheet-inbound-log'
BUCKET_NAME = 'reitsheet-email-ingest'

table = dynamodb.Table(TABLE_NAME)
inbound_log_table = dynamodb.Table(INBOUND_LOG_TABLE)


def extract_press_release_date(email_body: str) -> Optional[str]:
    """
    Extract press release date from email body.

    Pattern: "Date Sent: YYYY-MM-DD H:MM:SS AM/PM"

    Returns:
        str: Date in YYYY-MM-DD format, or None if not found
    """
    # Primary pattern: "Date Sent: 2026-03-11 7:18:30 PM"
    date_pattern = r'Date Sent:\s*(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}:\d{2}\s+(?:AM|PM)'

    match = re.search(date_pattern, email_body, re.IGNORECASE)
    if match:
        return match.group(1)  # YYYY-MM-DD

    # Fallback patterns
    alt_patterns = [
        (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),         # 2026-03-11
        (r'(\d{1,2}/\d{1,2}/\d{4})', '%m/%d/%Y'),    # 3/11/2026
        (r'(\w+ \d{1,2}, \d{4})', '%B %d, %Y'),      # March 11, 2026
    ]

    for pattern, date_format in alt_patterns:
        match = re.search(pattern, email_body)
        if match:
            try:
                dt = datetime.strptime(match.group(1), date_format)
                return dt.strftime('%Y-%m-%d')
            except:
                continue

    return None


def get_email_key(press_release_id: str) -> Optional[str]:
    """
    Get email S3 key from inbound_log table.

    The press_release_id matches idempotency_key in inbound_log,
    which has the email_key (S3 key).
    """
    try:
        response = inbound_log_table.get_item(
            Key={'idempotency_key': press_release_id}
        )
        item = response.get('Item')
        if item:
            return item.get('email_key')
        return None
    except Exception as e:
        print(f"  ❌ Error fetching email_key from inbound_log: {e}")
        return None


def fetch_email_from_s3(email_key: str) -> Optional[str]:
    """
    Fetch email from S3 using email_key.

    email_key is like "incoming/pfl3uvinuvmms1dnhhihnufsca1i6shqdc7pr8o1"
    """
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=email_key)
        email_body = response['Body'].read().decode('utf-8', errors='ignore')
        return email_body
    except s3.exceptions.NoSuchKey:
        return None
    except Exception as e:
        print(f"  ❌ Error fetching from S3: {e}")
        return None


def backfill_dates(dry_run: bool = False, limit: Optional[int] = None, ticker: Optional[str] = None):
    """Backfill press release dates for all records."""

    print(f"🔍 Scanning DynamoDB for records...")
    if ticker:
        print(f"   Filtering by ticker: {ticker}")
    if limit:
        print(f"   Limiting to {limit} records")
    if dry_run:
        print(f"   DRY RUN MODE - no updates will be made")
    print()

    # Scan DynamoDB
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, first_seen_at, press_release_date',
    }

    if ticker:
        scan_kwargs['FilterExpression'] = 'ticker = :ticker'
        scan_kwargs['ExpressionAttributeValues'] = {':ticker': ticker}

    if limit:
        scan_kwargs['Limit'] = limit

    items = []
    response = table.scan(**scan_kwargs)
    items.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response and (not limit or len(items) < limit):
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        if limit:
            scan_kwargs['Limit'] = limit - len(items)
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))

    print(f"Found {len(items)} total records")

    # Filter to records that need date extraction
    items_to_process = []
    for item in items:
        pr_date = item.get('press_release_date')
        first_seen = item.get('first_seen_at', '')[:10]

        # Process if no date or if it matches first_seen_at (default value)
        if not pr_date or pr_date == first_seen:
            items_to_process.append(item)

    if not items_to_process:
        print("✨ All records already have press release dates!")
        return

    print(f"Found {len(items_to_process)} records to process\n")

    # Process each record
    updated_count = 0
    failed_count = 0
    no_email_count = 0
    no_date_count = 0

    for i, item in enumerate(items_to_process, 1):
        press_release_id = item['press_release_id']
        first_seen_at = item['first_seen_at']
        ticker_name = item.get('ticker', 'UNKNOWN')
        title = item.get('title', '')[:50]

        print(f"[{i}/{len(items_to_process)}] {ticker_name} | {title}...")

        # Get email S3 key from inbound_log
        email_key = get_email_key(press_release_id)
        if not email_key:
            print(f"  ⚠️  Email key not found in inbound_log")
            no_email_count += 1
            continue

        # Fetch email from S3
        email_body = fetch_email_from_s3(email_key)
        if not email_body:
            print(f"  ⚠️  Email not found in S3 (key: {email_key})")
            no_email_count += 1
            continue

        # Extract date
        extracted_date = extract_press_release_date(email_body)

        if not extracted_date:
            print(f"  ⚠️  Could not extract date, using first_seen_at")
            extracted_date = first_seen_at[:10]
            no_date_count += 1
        else:
            print(f"  ✓ Extracted date: {extracted_date}")

        if dry_run:
            print(f"  [DRY RUN] Would update record with date: {extracted_date}")
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
                        ':date': extracted_date
                    }
                )
                print(f"  ✓ Updated in DynamoDB")
                updated_count += 1
            except Exception as e:
                print(f"  ❌ Error updating: {e}")
                failed_count += 1

    print()
    if dry_run:
        print(f"✅ Dry run complete. {len(items_to_process)} records would be processed.")
    else:
        print(f"✅ Backfill complete!")
        print(f"   Updated: {updated_count}")
        print(f"   Failed: {failed_count}")
        print(f"   No email in S3: {no_email_count}")
        print(f"   No date found: {no_date_count}")


def main():
    parser = argparse.ArgumentParser(description='Backfill press release dates from emails')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without actually updating')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--ticker', type=str, help='Filter by ticker')
    args = parser.parse_args()

    backfill_dates(dry_run=args.dry_run, limit=args.limit, ticker=args.ticker)


if __name__ == '__main__':
    main()
