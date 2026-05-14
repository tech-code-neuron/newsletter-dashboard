#!/usr/bin/env python3
"""
Map S3 emails by From field, Subject, and URLs
Creates a reliable index to avoid manual filename searching

Usage:
    python3 scripts/map_s3_emails.py [--company TICKER] [--subject KEYWORD]
"""

import boto3
import argparse
from email.parser import BytesParser
from email import policy
import re

def extract_email_metadata(email_content):
    """Extract From, Subject, and URLs from email"""
    msg = BytesParser(policy=policy.default).parsebytes(email_content)

    from_field = msg.get('From', '')
    subject = msg.get('Subject', '')

    # Extract URLs from body
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break
    else:
        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

    urls = re.findall(r'https?://[^\s<>"]+', body)

    return {
        'from': from_field,
        'subject': subject,
        'urls': urls[:3]  # First 3 URLs
    }


def main():
    parser = argparse.ArgumentParser(description='Map S3 emails by metadata')
    parser.add_argument('--company', help='Filter by company name/ticker')
    parser.add_argument('--subject', help='Filter by subject keyword')
    parser.add_argument('--bucket', default='reitsheet-email-ingest', help='S3 bucket')
    parser.add_argument('--prefix', default='incoming/', help='S3 prefix')
    args = parser.parse_args()

    s3 = boto3.client('s3', region_name='us-east-1')

    # List all emails
    response = s3.list_objects_v2(Bucket=args.bucket, Prefix=args.prefix)
    email_keys = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.eml') or len(obj['Key']) > 50]

    print(f"📧 Scanning {len(email_keys)} emails in s3://{args.bucket}/{args.prefix}\n")

    results = []

    for key in email_keys:
        try:
            # Download email
            email_obj = s3.get_object(Bucket=args.bucket, Key=key)
            email_content = email_obj['Body'].read()

            # Extract metadata
            meta = extract_email_metadata(email_content)

            # Apply filters
            if args.company:
                if args.company.lower() not in meta['from'].lower() and args.company.lower() not in meta['subject'].lower():
                    continue

            if args.subject:
                if args.subject.lower() not in meta['subject'].lower():
                    continue

            results.append({
                'key': key.replace(args.prefix, ''),
                'from': meta['from'],
                'subject': meta['subject'],
                'urls': meta['urls']
            })

        except Exception as e:
            print(f"⚠️  Error processing {key}: {e}")
            continue

    # Print results
    print(f"Found {len(results)} matching emails:\n")
    print("=" * 120)

    for r in results:
        print(f"\n📄 File: {r['key']}")
        print(f"   From: {r['from'][:80]}")
        print(f"   Subject: {r['subject'][:80]}")
        if r['urls']:
            print(f"   First URL: {r['urls'][0][:80]}...")
        print("-" * 120)

    print(f"\n✅ Total: {len(results)} emails")


if __name__ == '__main__':
    main()
