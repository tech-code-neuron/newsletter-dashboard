#!/usr/bin/env python3
"""
Reprocess All S3 Emails Through Lambda
========================================
Clears idempotency log and requeues all emails to test activation filter

Expected: ~120 activation emails should be filtered out
"""

import boto3
import json
from datetime import datetime
import time

# ============================================================================
# Configuration
# ============================================================================

PROJECT_NAME = 'reitsheet'
S3_BUCKET = f'{PROJECT_NAME}-email-ingest'
S3_PREFIX = 'incoming/'
PARSE_QUEUE_NAME = f'{PROJECT_NAME}-email-parse-queue'  # Fixed name
INBOUND_LOG_TABLE = f'{PROJECT_NAME}-inbound-log'
REIT_NEWS_TABLE = f'{PROJECT_NAME}-reit-news'

# ============================================================================
# AWS Clients
# ============================================================================

s3 = boto3.client('s3', region_name='us-east-1')
sqs = boto3.client('sqs', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

inbound_log_table = dynamodb.Table(INBOUND_LOG_TABLE)
reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)

# ============================================================================
# Step 1: Clear Idempotency Log
# ============================================================================

def clear_idempotency_log():
    """Delete all items from inbound-log table"""
    print("=" * 80)
    print("STEP 1: Clearing Idempotency Log")
    print("=" * 80)
    print()

    # Scan and delete all items
    response = inbound_log_table.scan()
    items = response.get('Items', [])

    deleted_count = 0

    with inbound_log_table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={'idempotency_key': item['idempotency_key']})
            deleted_count += 1
            if deleted_count % 50 == 0:
                print(f"  Deleted {deleted_count} items...")

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = inbound_log_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items = response.get('Items', [])

        with inbound_log_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'idempotency_key': item['idempotency_key']})
                deleted_count += 1
                if deleted_count % 50 == 0:
                    print(f"  Deleted {deleted_count} items...")

    print(f"\n✓ Deleted {deleted_count} items from {INBOUND_LOG_TABLE}")
    print()
    return deleted_count


# ============================================================================
# Step 2: Clear Press Releases Table
# ============================================================================

def clear_press_releases():
    """Delete all items from reit-news table"""
    print("=" * 80)
    print("STEP 2: Clearing Press Releases Table")
    print("=" * 80)
    print()

    response = reit_news_table.scan()
    items = response.get('Items', [])

    deleted_count = 0

    with reit_news_table.batch_writer() as batch:
        for item in items:
            # Key is composite: press_release_id (partition) + first_seen_at (sort)
            batch.delete_item(Key={
                'press_release_id': item['press_release_id'],
                'first_seen_at': item['first_seen_at']
            })
            deleted_count += 1
            if deleted_count % 50 == 0:
                print(f"  Deleted {deleted_count} items...")

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = reit_news_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items = response.get('Items', [])

        with reit_news_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={
                    'press_release_id': item['press_release_id'],
                    'first_seen_at': item['first_seen_at']
                })
                deleted_count += 1
                if deleted_count % 50 == 0:
                    print(f"  Deleted {deleted_count} items...")

    print(f"\n✓ Deleted {deleted_count} items from {REIT_NEWS_TABLE}")
    print()
    return deleted_count


# ============================================================================
# Step 3: Requeue All S3 Emails
# ============================================================================

def requeue_all_emails():
    """Send all S3 emails to parse queue"""
    print("=" * 80)
    print("STEP 3: Requeuing All S3 Emails")
    print("=" * 80)
    print()

    # Get queue URL
    queue_url = sqs.get_queue_url(QueueName=PARSE_QUEUE_NAME)['QueueUrl']

    # List all S3 emails
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    email_keys = [obj['Key'] for obj in response.get('Contents', [])
                 if not obj['Key'].endswith('/')]

    print(f"Found {len(email_keys)} emails in s3://{S3_BUCKET}/{S3_PREFIX}\n")

    # Send each to queue
    sent_count = 0
    batch_entries = []

    for key in email_keys:
        # Create idempotency key from S3 key
        idempotency_key = key.replace(S3_PREFIX, '').replace('.eml', '').replace('/', '-')

        # Correct message format expected by Parser Lambda
        message = {
            'bucket': S3_BUCKET,
            'key': key,
            'idempotency_key': idempotency_key,
            'ingested_at': datetime.utcnow().isoformat() + 'Z'
        }

        batch_entries.append({
            'Id': str(sent_count),
            'MessageBody': json.dumps(message)
        })

        sent_count += 1

        # Send in batches of 10 (SQS limit)
        if len(batch_entries) == 10:
            sqs.send_message_batch(QueueUrl=queue_url, Entries=batch_entries)
            print(f"  Queued {sent_count}/{len(email_keys)} emails...")
            batch_entries = []
            time.sleep(0.1)  # Rate limiting

    # Send remaining
    if batch_entries:
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch_entries)

    print(f"\n✓ Queued {sent_count} emails to {PARSE_QUEUE_NAME}")
    print()
    return sent_count


# ============================================================================
# Main
# ============================================================================

def main():
    print("\n" + "=" * 80)
    print("REPROCESS ALL S3 EMAILS - ACTIVATION FILTER TEST")
    print("=" * 80)
    print()
    print("This will:")
    print("  1. Clear idempotency log (allow reprocessing)")
    print("  2. Clear press releases table (fresh start)")
    print("  3. Requeue all 187 S3 emails")
    print("  4. Lambda will process and filter ~120 activation emails")
    print()

    confirm = input("Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        return

    print()

    # Execute steps
    step1_deleted = clear_idempotency_log()
    step2_deleted = clear_press_releases()
    step3_queued = requeue_all_emails()

    # Summary
    print("=" * 80)
    print("✅ REPROCESSING INITIATED")
    print("=" * 80)
    print()
    print(f"Cleared {step1_deleted} idempotency entries")
    print(f"Cleared {step2_deleted} press releases")
    print(f"Queued {step3_queued} emails for processing")
    print()
    print("⏳ Lambda is now processing emails...")
    print()
    print("Expected Results (after ~2 minutes):")
    print("  • ~120 activation emails filtered (routing: skipped_confirmation)")
    print("  • ~67 emails processed (actual press releases)")
    print("  • ~10-20 press releases saved to DynamoDB")
    print()
    print("Monitor progress:")
    print("  Watch logs:  aws logs tail /aws/lambda/reitsheet-parser --region us-east-1 --follow")
    print("  Check count: aws dynamodb scan --table-name reitsheet-inbound-log --select COUNT")
    print()
    print("Wait 2 minutes, then run:")
    print("  python3 scripts/analyze_reprocessing_results.py")
    print()


if __name__ == '__main__':
    main()
