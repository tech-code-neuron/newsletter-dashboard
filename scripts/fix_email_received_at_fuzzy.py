#!/usr/bin/env python3
"""
Fix email_received_at by fuzzy matching press releases to S3 emails.

Strategy:
1. First try exact match via idempotency_key → inbound_log → email_key
2. For remaining, fuzzy match by title similarity to email subject
"""

import argparse
import boto3
import email
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher


def similarity(a, b):
    """Calculate string similarity ratio (0-1)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def normalize_title(text):
    """Normalize title for comparison"""
    # Remove common prefixes like "Company Name - "
    if ' - ' in text:
        parts = text.split(' - ', 1)
        if len(parts) > 1:
            text = parts[1]
    return text.strip().lower()


def main():
    parser = argparse.ArgumentParser(description='Fix email_received_at via fuzzy matching')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--execute', action='store_true', help='Apply changes')
    parser.add_argument('--threshold', type=float, default=0.7, help='Similarity threshold (0-1)')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Usage: --dry-run or --execute")
        return 1

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    s3 = boto3.client('s3', region_name='us-east-1')

    press_releases = dynamodb.Table('reitsheet-reit-news-v2')
    inbound_log = dynamodb.Table('reitsheet-inbound-log')

    # Step 1: Build email index from S3
    print("Building email index from S3...")
    emails = []
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket='reitsheet-email-ingest', Prefix='incoming/'):
        for obj in page.get('Contents', []):
            key = obj['Key']
            try:
                email_obj = s3.get_object(Bucket='reitsheet-email-ingest', Key=key)
                raw = email_obj['Body'].read().decode('utf-8', errors='replace')
                msg = email.message_from_string(raw)

                date_header = msg.get('Date')
                subject = msg.get('Subject', '')

                if date_header and subject:
                    parsed = parsedate_to_datetime(date_header)
                    emails.append({
                        'key': key,
                        'date': parsed,
                        'subject': subject,
                        'normalized': normalize_title(subject)
                    })
            except:
                pass

    print(f"Indexed {len(emails)} emails\n")

    # Step 2: Get all press releases
    print("Scanning press releases...")
    response = press_releases.scan()
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = press_releases.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    print(f"Found {len(items)} press releases\n")

    fixed_exact = 0
    fixed_fuzzy = 0
    skipped = 0

    for item in items:
        ticker = item.get('ticker')
        url = item.get('url')
        title = item.get('title', '')
        idempotency_key = item.get('idempotency_key')

        email_received_at = None
        match_type = None

        # Try exact match first
        if idempotency_key:
            log = inbound_log.get_item(Key={'idempotency_key': idempotency_key}).get('Item')
            if log and log.get('email_key'):
                email_key = log['email_key']
                try:
                    email_obj = s3.get_object(Bucket='reitsheet-email-ingest', Key=email_key)
                    raw = email_obj['Body'].read().decode('utf-8', errors='replace')
                    msg = email.message_from_string(raw)
                    date_header = msg.get('Date')
                    if date_header:
                        parsed = parsedate_to_datetime(date_header)
                        email_received_at = parsed.isoformat()
                        match_type = 'exact'
                except:
                    pass

        # Try fuzzy match
        if not email_received_at:
            normalized_title = normalize_title(title)
            best_match = None
            best_score = 0

            for em in emails:
                score = similarity(normalized_title, em['normalized'])
                if score > best_score:
                    best_score = score
                    best_match = em

            if best_match and best_score >= args.threshold:
                email_received_at = best_match['date'].isoformat()
                match_type = f'fuzzy ({best_score:.0%})'

        # Update if found
        if email_received_at:
            print(f"{ticker}: {email_received_at} [{match_type}]")
            print(f"  Title: {title[:60]}...")

            if not args.dry_run:
                press_releases.update_item(
                    Key={'url': url},
                    UpdateExpression='SET email_received_at = :val',
                    ExpressionAttributeValues={':val': email_received_at}
                )

            if match_type == 'exact':
                fixed_exact += 1
            else:
                fixed_fuzzy += 1
        else:
            print(f"{ticker}: NO MATCH - {title[:50]}...")
            skipped += 1

    print(f"\n{'DRY RUN' if args.dry_run else 'COMPLETE'}:")
    print(f"  Exact matches: {fixed_exact}")
    print(f"  Fuzzy matches: {fixed_fuzzy}")
    print(f"  Skipped: {skipped}")
    return 0


if __name__ == '__main__':
    exit(main())
