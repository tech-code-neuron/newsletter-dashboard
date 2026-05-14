#!/usr/bin/env python3
"""
Backfill Press Release Dates

Fetches HTML for each press release URL and extracts the actual publication date.
Updates DynamoDB with the extracted date.

Usage:
    python3 backfill_press_release_dates.py [--dry-run] [--limit N] [--ticker TICKER]
"""

import boto3
import requests
import argparse
import sys
import os
from datetime import datetime, timezone
from typing import Optional

# Add enricher path for date_extraction module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../infrastructure/lambdas/enricher'))

try:
    from date_extraction import extract_date_from_html
except ImportError:
    print("Error: Could not import date_extraction module")
    print("Make sure beautifulsoup4 is installed: pip3 install beautifulsoup4")
    sys.exit(1)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('reitsheet-reit-news')

def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch HTML content from URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; PressReleasePipeline/1.0; +https://your-domain.com)'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)

        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"  ❌ Error fetching {url[:60]}: {e}")

    return None

def backfill_dates(dry_run: bool = False, limit: Optional[int] = None, ticker: Optional[str] = None):
    """Backfill press release dates for all records."""

    print(f"🔍 Scanning for records without press_release_date...")
    if ticker:
        print(f"   Filtering by ticker: {ticker}")
    if limit:
        print(f"   Limiting to {limit} records")
    if dry_run:
        print(f"   DRY RUN MODE - no updates will be made")
    print()

    # Scan table for records
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, #url, first_seen_at, press_release_date',
        'ExpressionAttributeNames': {'#url': 'url'},
    }

    if ticker:
        scan_kwargs['FilterExpression'] = 'ticker = :ticker'
        scan_kwargs['ExpressionAttributeValues'] = {':ticker': ticker}

    if limit:
        scan_kwargs['Limit'] = limit

    items = []
    response = table.scan(**scan_kwargs)
    items.extend(response.get('Items', []))

    # Handle pagination (up to limit)
    while 'LastEvaluatedKey' in response and (not limit or len(items) < limit):
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        if limit:
            scan_kwargs['Limit'] = limit - len(items)
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))

    # Filter to only items without press_release_date or with default date
    items_to_process = []
    for item in items:
        pr_date = item.get('press_release_date')
        first_seen = item.get('first_seen_at', '')[:10]  # Get just the date part

        # Process if no press_release_date or if it matches first_seen_at (default value)
        if not pr_date or pr_date == first_seen:
            items_to_process.append(item)

    if not items_to_process:
        print("✨ All records already have press release dates!")
        return

    print(f"Found {len(items_to_process)} records to process\n")

    # Group by ticker for summary
    by_ticker = {}
    for item in items_to_process:
        ticker = item.get('ticker', 'UNKNOWN')
        by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

    print("Summary by ticker:")
    for ticker, count in sorted(by_ticker.items()):
        print(f"  {ticker}: {count}")
    print()

    # Process each record
    updated_count = 0
    failed_count = 0

    for i, item in enumerate(items_to_process, 1):
        press_release_id = item['press_release_id']
        first_seen_at = item['first_seen_at']
        ticker = item.get('ticker', 'UNKNOWN')
        url = item.get('url', '')
        title = item.get('title', '')[:50]

        print(f"[{i}/{len(items_to_process)}] {ticker} | {title}...")

        # Fetch HTML
        html = fetch_html(url)
        if not html:
            print(f"  ❌ Failed to fetch HTML")
            failed_count += 1
            continue

        # Extract date
        extracted_date = extract_date_from_html(html, url)

        if extracted_date:
            print(f"  ✓ Extracted date: {extracted_date}")

            if dry_run:
                print(f"  [DRY RUN] Would update record")
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
        else:
            print(f"  ⚠️  Could not extract date, using first_seen_at")

            if not dry_run:
                try:
                    # Use first_seen_at date as fallback
                    fallback_date = first_seen_at[:10] if first_seen_at else datetime.now(timezone.utc).strftime('%Y-%m-%d')

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
                    print(f"  ✓ Updated with fallback date: {fallback_date}")
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

def main():
    parser = argparse.ArgumentParser(description='Backfill press release dates')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without actually updating')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--ticker', type=str, help='Filter by ticker')
    args = parser.parse_args()

    backfill_dates(dry_run=args.dry_run, limit=args.limit, ticker=args.ticker)

if __name__ == '__main__':
    main()
