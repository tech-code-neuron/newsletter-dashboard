#!/usr/bin/env python3
"""
Fix email_received_at using EXACT linkage only.

- Records WITH idempotency_key linkage: use S3 email Date header
- Records WITHOUT linkage: CLEAR email_received_at (fallback to press_release_date)

NO fuzzy matching. Only exact linkage.
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

    pr_table = dynamodb.Table('reitsheet-reit-news-v2')
    log_table = dynamodb.Table('reitsheet-inbound-log')

    # Get all press releases
    response = pr_table.scan()
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = pr_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    print(f'Total: {len(items)} press releases\n')

    exact_fixed = 0
    cleared = 0
    errors = 0

    for item in items:
        ticker = item.get('ticker')
        url = item.get('url')
        title = item.get('title', '')[:40]
        idem_key = item.get('idempotency_key')
        pr_date = item.get('press_release_date')

        email_received_at = None

        # Try exact linkage
        if idem_key:
            log = log_table.get_item(Key={'idempotency_key': idem_key}).get('Item')
            if log:
                email_key = log.get('email_key')
                if email_key:
                    try:
                        email_obj = s3.get_object(Bucket='reitsheet-email-ingest', Key=email_key)
                        raw = email_obj['Body'].read().decode('utf-8', errors='replace')
                        msg = email.message_from_string(raw)
                        date_header = msg.get('Date')
                        if date_header:
                            parsed = parsedate_to_datetime(date_header)
                            email_received_at = parsed.isoformat()
                    except Exception as e:
                        print(f'{ticker}: ERROR getting email - {e}')
                        errors += 1
                        continue

        if email_received_at:
            print(f'{ticker}: EXACT {email_received_at}')
            if not args.dry_run:
                pr_table.update_item(
                    Key={'url': url},
                    UpdateExpression='SET email_received_at = :val',
                    ExpressionAttributeValues={':val': email_received_at}
                )
            exact_fixed += 1
        else:
            # No linkage - clear email_received_at, will fallback to press_release_date
            print(f'{ticker}: CLEAR (fallback to pr_date={pr_date}) - {title}')
            if not args.dry_run:
                pr_table.update_item(
                    Key={'url': url},
                    UpdateExpression='REMOVE email_received_at'
                )
            cleared += 1

    print(f"\n{'DRY RUN' if args.dry_run else 'COMPLETE'}:")
    print(f"  Exact matches: {exact_fixed}")
    print(f"  Cleared (using pr_date): {cleared}")
    print(f"  Errors: {errors}")


if __name__ == '__main__':
    main()
