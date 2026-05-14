#!/usr/bin/env python3
"""
Find Email - Quick S3 Email Finder
===================================
Search BOTH DynamoDB inbound_log AND S3 bucket for emails

Searches in order:
1. DynamoDB inbound_log (fast, indexed, has metadata)
2. S3 bucket (slower, comprehensive, source of truth)

Usage:
    python scripts/find_email.py --ticker SMA
    python scripts/find_email.py --search "Edmonton"
    python scripts/find_email.py --subject "Announces"
    python scripts/find_email.py --search "Ryman" --s3-only  # Skip DynamoDB

Author: Claude Code
Date: 2026-03-11
"""

import argparse
import boto3
from datetime import datetime
from email.parser import BytesParser
from email.policy import default

def find_by_ticker(table, ticker):
    """
    Find emails by ticker (scan with filter)

    First tries exact ticker match, then falls back to searching
    subject/sender fields for the ticker string (handles renamed companies)
    """
    # Try exact ticker match first
    response = table.scan(
        FilterExpression='ticker = :ticker',
        ExpressionAttributeValues={':ticker': ticker}
    )
    results = response.get('Items', [])

    # If no exact match, search subject/sender for ticker string
    # (handles cases like "COPT" → "COPT Defense" with ticker "CDP")
    if not results:
        response = table.scan(
            FilterExpression='contains(subject, :text) OR contains(#from, :text) OR contains(sender_domain, :text)',
            ExpressionAttributeNames={'#from': 'from_field'},
            ExpressionAttributeValues={':text': ticker}
        )
        results = response.get('Items', [])

    return results

def find_by_subject(table, search_text):
    """Find emails by subject text (scan with filter)"""
    response = table.scan(
        FilterExpression='contains(subject, :text)',
        ExpressionAttributeValues={':text': search_text}
    )
    return response.get('Items', [])

def find_by_search(table, search_text):
    """Find emails by text in subject, sender, or from_field"""
    response = table.scan(
        FilterExpression='contains(subject, :text) OR contains(#from, :text) OR contains(sender_domain, :text)',
        ExpressionAttributeNames={'#from': 'from_field'},  # 'from' is reserved word
        ExpressionAttributeValues={':text': search_text}
    )
    return response.get('Items', [])

def search_s3_emails(s3_client, bucket, search_text, limit=100):
    """
    Search S3 bucket directly for emails matching search text

    This is slower but more comprehensive - finds emails that:
    - Haven't been processed by forwarder Lambda yet
    - Failed to log to DynamoDB
    - Exist in S3 but missing from inbound_log table

    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        search_text: Text to search for in email subject/body
        limit: Max number of emails to scan (default 100)

    Returns:
        list: Matching email metadata dicts
    """
    print(f"🔍 Searching S3 bucket (source of truth)...")

    # List recent objects in S3
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix='incoming/')

    results = []
    scanned = 0

    for page in pages:
        if 'Contents' not in page:
            continue

        # Sort by last modified (most recent first)
        objects = sorted(page['Contents'], key=lambda x: x['LastModified'], reverse=True)

        for obj in objects:
            if scanned >= limit:
                break

            scanned += 1
            key = obj['Key']

            try:
                # Download email
                response = s3_client.get_object(Bucket=bucket, Key=key)
                email_bytes = response['Body'].read()

                # Parse email headers
                msg = BytesParser(policy=default).parsebytes(email_bytes)
                subject = msg.get('Subject', '')
                from_field = msg.get('From', '')

                # Check if search text matches
                search_lower = search_text.lower()
                if search_lower in subject.lower() or search_lower in from_field.lower():
                    results.append({
                        'email_key': key,
                        'subject': subject,
                        'from_field': from_field,
                        'last_modified': obj['LastModified'].isoformat(),
                        'size': obj['Size'],
                        'source': 'S3'
                    })

            except Exception as e:
                # Skip files that can't be parsed
                continue

        if scanned >= limit:
            break

    print(f"   Scanned {scanned} S3 objects")
    return results

def main():
    parser = argparse.ArgumentParser(description='Find emails in DynamoDB and S3')
    parser.add_argument('--ticker', help='Company ticker (e.g., SMA)')
    parser.add_argument('--subject', help='Search text in subject')
    parser.add_argument('--search', help='Search text in subject or sender')
    parser.add_argument('--s3-only', action='store_true', help='Skip DynamoDB, search S3 only')
    parser.add_argument('--limit', type=int, default=100, help='Max S3 objects to scan (default: 100)')
    args = parser.parse_args()

    if not any([args.ticker, args.subject, args.search]):
        print("❌ Must specify --ticker, --subject, or --search")
        return 1

    search_text = args.search or args.subject or args.ticker
    all_results = []

    # Search DynamoDB first (unless --s3-only)
    if not args.s3_only:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('reitsheet-inbound-log')

        print(f"🔍 Searching inbound_log table...")

        if args.ticker:
            dynamo_results = find_by_ticker(table, args.ticker)
        elif args.subject:
            dynamo_results = find_by_subject(table, args.subject)
        else:
            dynamo_results = find_by_search(table, args.search)

        # Mark as DynamoDB source
        for item in dynamo_results:
            item['source'] = 'DynamoDB'

        all_results.extend(dynamo_results)
        print(f"   Found {len(dynamo_results)} in DynamoDB")

    # Search S3 (source of truth)
    s3_client = boto3.client('s3', region_name='us-east-1')
    s3_results = search_s3_emails(s3_client, 'reitsheet-email-ingest', search_text, limit=args.limit)

    # Deduplicate (prefer DynamoDB version which has more metadata)
    s3_keys_in_dynamo = {r.get('email_key', '') for r in all_results}
    for s3_item in s3_results:
        if s3_item['email_key'] not in s3_keys_in_dynamo:
            all_results.append(s3_item)

    print(f"   Found {len(s3_results)} in S3 ({len(s3_results) - len([r for r in s3_results if r['email_key'] not in s3_keys_in_dynamo])} duplicates)")

    # Display results
    if not all_results:
        print("\n❌ No emails found in DynamoDB or S3")
        return 0

    print(f"\n✅ Found {len(all_results)} unique email(s):\n")

    # Sort by timestamp (DynamoDB has ingested_at, S3 has last_modified)
    def get_sort_key(item):
        if 'ingested_at' in item:
            return item['ingested_at']
        elif 'last_modified' in item:
            return item['last_modified']
        return ''

    for item in sorted(all_results, key=get_sort_key, reverse=True):
        ticker = item.get('ticker', 'UNKNOWN')
        subject = item.get('subject', 'No subject')[:70]
        email_key = item.get('email_key', 'No key')
        source = item.get('source', 'Unknown')

        # Format timestamp
        timestamp = item.get('ingested_at') or item.get('last_modified', 'Unknown')
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_str = dt.strftime('%Y-%m-%d %H:%M UTC')
        except:
            time_str = timestamp

        print(f"📧 {ticker} - {time_str} [{source}]")
        print(f"   Subject: {subject}")
        print(f"   S3 Key:  {email_key}")
        print()

    return 0

if __name__ == '__main__':
    exit(main())
