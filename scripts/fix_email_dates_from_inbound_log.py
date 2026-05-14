#!/usr/bin/env python3
"""
Fix email_received_at using inbound log as source of truth.

Flow:
1. Inbound log has: ticker, subject, email_key (S3 path)
2. Press release has: ticker, title (matches subject)
3. Get Date header from S3 email
4. Update press release with correct email_received_at

This is EXACT matching by ticker + subject, NOT fuzzy matching.
The inbound log is the authoritative record of email processing.
"""

import argparse
import boto3
import email
from email.utils import parsedate_to_datetime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Usage: --dry-run or --execute")
        return 1

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    s3 = boto3.client('s3', region_name='us-east-1')

    log_table = dynamodb.Table('reitsheet-inbound-log')
    pr_table = dynamodb.Table('reitsheet-reit-news-v2')

    # Get all press releases and build lookup by ticker+title
    print("Loading press releases...")
    pr_response = pr_table.scan()
    pr_items = pr_response.get('Items', [])
    while 'LastEvaluatedKey' in pr_response:
        pr_response = pr_table.scan(ExclusiveStartKey=pr_response['LastEvaluatedKey'])
        pr_items.extend(pr_response.get('Items', []))

    # Build lookup: ticker -> list of PRs (we'll match by title containment)
    pr_by_ticker = {}
    for pr in pr_items:
        ticker = pr.get('ticker', '')
        if ticker not in pr_by_ticker:
            pr_by_ticker[ticker] = []
        pr_by_ticker[ticker].append(pr)

    print(f"Loaded {len(pr_items)} press releases\n")

    # Get all inbound log records with ticker + email_key
    print("Loading inbound log records...")
    log_response = log_table.scan()
    log_items = log_response.get('Items', [])
    while 'LastEvaluatedKey' in log_response:
        log_response = log_table.scan(ExclusiveStartKey=log_response['LastEvaluatedKey'])
        log_items.extend(log_response.get('Items', []))

    print(f"Loaded {len(log_items)} inbound log records\n")

    # Process each inbound log record
    fixed = 0
    skipped = 0
    errors = 0
    already_matched = set()  # Track PRs we've already fixed

    for log in log_items:
        ticker = log.get('ticker')
        email_key = log.get('email_key')
        subject = log.get('subject', '').strip()

        if not ticker or not email_key:
            continue

        # Find matching PR by ticker + title containment
        # Email subject often has "Company Name - Title" but PR title is just "Title"
        prs_for_ticker = pr_by_ticker.get(ticker, [])
        pr = None
        for candidate in prs_for_ticker:
            candidate_title = candidate.get('title', '').strip()
            # Check if PR title is contained in log subject (handles "Company - Title" pattern)
            if candidate_title and candidate_title in subject:
                pr = candidate
                break
            # Also check exact match
            if candidate_title == subject:
                pr = candidate
                break

        if not pr:
            continue

        url = pr.get('url')

        # Skip if we've already fixed this PR (avoid duplicates)
        if url in already_matched:
            continue
        already_matched.add(url)

        # Get email Date header from S3
        try:
            email_obj = s3.get_object(Bucket='reitsheet-email-ingest', Key=email_key)
            raw = email_obj['Body'].read().decode('utf-8', errors='replace')
            msg = email.message_from_string(raw)
            date_header = msg.get('Date')

            if not date_header:
                print(f"{ticker}: No Date header in {email_key}")
                skipped += 1
                continue

            parsed = parsedate_to_datetime(date_header)
            email_received_at = parsed.isoformat()

            print(f"{ticker}: {email_received_at}")
            print(f"  Subject: {subject[:50]}...")

            if not args.dry_run:
                pr_table.update_item(
                    Key={'url': url},
                    UpdateExpression='SET email_received_at = :val',
                    ExpressionAttributeValues={':val': email_received_at}
                )

            fixed += 1

        except Exception as e:
            print(f"{ticker}: ERROR - {e}")
            errors += 1

    print(f"\n{'DRY RUN' if args.dry_run else 'COMPLETE'}:")
    print(f"  Fixed: {fixed}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")


if __name__ == '__main__':
    main()
