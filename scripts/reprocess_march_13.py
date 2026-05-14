#!/usr/bin/env python3
"""
Reprocess all March 13 emails to get correct timestamps.

1. Delete press release from DynamoDB
2. Delete inbound log record
3. Invoke parser Lambda to reprocess
"""

import boto3
import json
import time

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')

pr_table = dynamodb.Table('reitsheet-reit-news-v2')
log_table = dynamodb.Table('reitsheet-inbound-log')

# March 13 emails to reprocess (from analysis above)
EMAILS_TO_REPROCESS = [
    {'ticker': 'TRTX', 'email_key': 'incoming/1a0i6jv5a8b9tk4g61ghal0hmlaf94see96tvo81', 'idem_key': '705dc582f12a1e30e72eb8a47cc9084eba3cb639e3738754891cffb7cf3d6b32'},
    {'ticker': 'CBL', 'email_key': 'incoming/g4ftepghrn9m6lctm0albojus81q7h6p3ohr33o1', 'idem_key': 'test-74ba67b917cf'},
    {'ticker': 'VRE', 'email_key': 'incoming/test-vre-1772829516.eml', 'idem_key': 'reprocess-test-vre-1772829516.eml'},
    {'ticker': 'BXMT', 'email_key': 'incoming/12kjv05h3ilcdh710pn7b0q7qkq99sve2ooq7781', 'idem_key': 'a7735ea1cf3a185790b87ab16de36deaa890d4e2b0351f670e91e50d71305f72'},
    {'ticker': 'SMA', 'email_key': 'incoming/76hrdnq2qn5d01uhm0vu1tho1vn4s9qfkv844v01', 'idem_key': '99b9087dca10c364a77441f83be2f4b37aaec3efed611ebba1533c452ca84e28'},
    {'ticker': 'RC', 'email_key': 'incoming/qakhu4hpvg79esq0ugce2jhmp0kojrnj6klbh1g1', 'idem_key': 'test-e257f63d160c'},
    {'ticker': 'INVH', 'email_key': 'incoming/polahh2m3cencnr217id6cfjm58f16cvlii3c201', 'idem_key': '2264da5590740bf1814bb5510f07f2e319969e3213c08c4bdb9cc3a80f4d8d91'},
    {'ticker': 'SLG', 'email_key': 'incoming/1qmoubmcfbp3kgdr6g5cq6fbqsr9diqtc3bkauo1', 'idem_key': 'reprocess-1qmoubmcfbp3kgdr6g5cq6fbqsr9diqtc3bkauo1'},
    {'ticker': 'RLJ', 'email_key': 'incoming/82o1gfmga94c0u18ra5mqmia3julqddnd88o7f81', 'idem_key': '82o1gfmga94c0u18ra5mqmia3julqddnd88o7f81'},
    {'ticker': 'EPRT', 'email_key': 'incoming/ifgitsmvnsr96rap1k9pfebt67870aut52gj6381', 'idem_key': 'reprocess-ifgitsmvnsr96rap1k9pfebt67870aut52gj6381'},
]

# Note: FCPT already done, SLG 690 Madison has no log match

def find_pr_url(ticker, date='2026-03-13'):
    """Find the URL for a March 13 press release by ticker"""
    response = pr_table.scan(
        FilterExpression='ticker = :t AND press_release_date = :d',
        ExpressionAttributeValues={':t': ticker, ':d': date}
    )
    items = response.get('Items', [])
    return items[0]['url'] if items else None

def invoke_parser(email_key, idem_key):
    """Invoke parser Lambda with the email"""
    # Parser expects: Records[].body = JSON{"bucket","key","idempotency_key"}
    payload = {
        'Records': [{
            'body': json.dumps({
                'bucket': 'reitsheet-email-ingest',
                'key': email_key,
                'idempotency_key': idem_key
            })
        }]
    }

    response = lambda_client.invoke(
        FunctionName='reitsheet-parser',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    return json.loads(response['Payload'].read())

def main():
    for email in EMAILS_TO_REPROCESS:
        ticker = email['ticker']
        email_key = email['email_key']
        idem_key = email['idem_key']

        print(f"\n{'='*60}")
        print(f"Processing {ticker}")
        print(f"{'='*60}")

        # Step 1: Find and delete press release
        url = find_pr_url(ticker)
        if url:
            pr_table.delete_item(Key={'url': url})
            print(f"Deleted PR: {url[:60]}...")
        else:
            print(f"No PR found for {ticker}")

        # Step 2: Delete inbound log
        log_table.delete_item(Key={'idempotency_key': idem_key})
        print(f"Deleted log: {idem_key[:30]}...")

        # Step 3: Invoke parser
        print(f"Reprocessing email: {email_key}")
        result = invoke_parser(email_key, idem_key)
        print(f"Parser result: {result.get('statusCode', 'unknown')}")

        # Wait to avoid Cloudflare rate limiting
        print("Waiting 10 seconds before next...")
        time.sleep(10)

    print(f"\n{'='*60}")
    print("COMPLETE - Wait 30 seconds for enricher to finish processing")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
