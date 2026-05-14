#!/usr/bin/env python3
"""
Reprocess failed emails from S3 by re-invoking parser Lambda

Usage: python3 scripts/reprocess_failed_emails.py --since-hours 18
"""
import boto3
import json
from datetime import datetime, timedelta, timezone
import argparse
import time

def reprocess_emails(since_hours=18):
    """Reprocess emails from last N hours (or all if since_hours=0)"""
    s3 = boto3.client('s3', region_name='us-east-1')
    lambda_client = boto3.client('lambda', region_name='us-east-1')

    bucket = 'reitsheet-email-ingest'
    prefix = 'incoming/'

    if since_hours == 0:
        print(f"🔍 Finding ALL emails in S3...")
        cutoff = None
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        print(f"🔍 Finding emails since {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    # List objects
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    emails = []

    for obj in response.get('Contents', []):
        if cutoff is None or obj['LastModified'] > cutoff:
            emails.append(obj['Key'])

    print(f"📧 Found {len(emails)} emails to reprocess")

    # Reprocess each email
    success = 0
    failed = 0

    for i, key in enumerate(emails, 1):
        try:
            # Generate idempotency key from S3 key
            email_id = key.replace('incoming/', '')
            idempotency_key = f'reprocess-{email_id}'

            # Create SQS-formatted event
            event = {
                'Records': [{
                    'body': json.dumps({
                        'bucket': bucket,
                        'key': key,
                        'etag': 'reprocess',
                        'idempotency_key': idempotency_key,
                        'ingested_at': datetime.now(timezone.utc).isoformat() + '+00:00',
                        'attempts': 0
                    })
                }]
            }

            # Invoke parser Lambda asynchronously
            lambda_client.invoke(
                FunctionName='reitsheet-parser',
                InvocationType='Event',  # Async
                Payload=json.dumps(event)
            )

            success += 1
            if i % 10 == 0:
                print(f"  ✓ Queued {i}/{len(emails)} emails...")
                time.sleep(1)  # Rate limit

        except Exception as e:
            print(f"  ✗ Failed to queue {key}: {e}")
            failed += 1

    print(f"\n✅ Reprocessing complete!")
    print(f"   ✓ {success} emails queued")
    print(f"   ✗ {failed} emails failed")
    print(f"\n💡 Check CloudWatch logs for parser execution results")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Reprocess failed emails')
    parser.add_argument('--since-hours', type=int, default=18,
                       help='Reprocess emails from last N hours (default: 18)')
    args = parser.parse_args()

    reprocess_emails(args.since_hours)
