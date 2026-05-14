#!/usr/bin/env python3
"""
Fix email_received_at by extracting Date headers from S3 emails.

This script ONLY updates timestamps - no enrichment, no URL processing.

Flow:
1. Get press release idempotency_key
2. Look up inbound log → get email_key
3. Fetch email from S3 → parse Date header
4. Update ONLY email_received_at field
"""

import argparse
import boto3
import email
from email.utils import parsedate_to_datetime


def main():
    parser = argparse.ArgumentParser(description='Fix email_received_at from S3 emails')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--execute', action='store_true', help='Apply changes')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Usage: --dry-run or --execute")
        return 1

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    s3 = boto3.client('s3', region_name='us-east-1')

    press_releases = dynamodb.Table('reitsheet-reit-news-v2')
    inbound_log = dynamodb.Table('reitsheet-inbound-log')

    # Scan all press releases
    print("Scanning press releases...")
    response = press_releases.scan()
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = press_releases.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    print(f"Found {len(items)} press releases\n")

    fixed = 0
    skipped = 0
    errors = 0

    for item in items:
        ticker = item.get('ticker')
        url = item.get('url')
        idempotency_key = item.get('idempotency_key')
        current_email_received = item.get('email_received_at')

        # Skip if no idempotency_key (can't link to email)
        if not idempotency_key:
            skipped += 1
            continue

        # Look up inbound log for email_key
        log_response = inbound_log.get_item(Key={'idempotency_key': idempotency_key})
        log_item = log_response.get('Item')

        if not log_item:
            print(f"  {ticker}: No inbound log found")
            skipped += 1
            continue

        email_key = log_item.get('email_key')
        if not email_key:
            print(f"  {ticker}: No email_key in log")
            skipped += 1
            continue

        # Fetch email from S3
        try:
            email_obj = s3.get_object(Bucket='reitsheet-email-ingest', Key=email_key)
            raw_email = email_obj['Body'].read().decode('utf-8', errors='replace')
            msg = email.message_from_string(raw_email)

            date_header = msg.get('Date')
            if not date_header:
                print(f"  {ticker}: No Date header in email")
                skipped += 1
                continue

            # Parse the date
            parsed_date = parsedate_to_datetime(date_header)
            email_received_at = parsed_date.isoformat()

            print(f"{ticker}: {email_received_at}")

            if not args.dry_run:
                # Update ONLY email_received_at
                press_releases.update_item(
                    Key={'url': url},
                    UpdateExpression='SET email_received_at = :val',
                    ExpressionAttributeValues={':val': email_received_at}
                )

            fixed += 1

        except Exception as e:
            print(f"  {ticker}: Error - {e}")
            errors += 1

    print(f"\n{'DRY RUN' if args.dry_run else 'COMPLETE'}: Fixed {fixed}, Skipped {skipped}, Errors {errors}")
    return 0


if __name__ == '__main__':
    exit(main())
