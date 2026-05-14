#!/usr/bin/env python3
"""
Process S3 Emails One by One - Methodical Testing
==================================================
Test the email processing pipeline methodically:
1. Show each email's details
2. Test with parser
3. Show decision logs
4. Show what was saved to DynamoDB
"""

import boto3
import json
import time
import sys
from datetime import datetime

s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')
logs = boto3.client('logs')
dynamodb = boto3.resource('dynamodb')

BUCKET = 'reitsheet-email-ingest'
PREFIX = 'incoming/'
PARSER_FUNCTION = 'reitsheet-parser'
LOG_GROUP = '/aws/lambda/reitsheet-enricher'

# Colors for terminal
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'


def get_all_emails():
    """Get all email keys from S3"""
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX)
    if 'Contents' not in response:
        return []
    
    # Sort by last modified (newest first)
    emails = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
    return [obj['Key'] for obj in emails if obj['Size'] > 0]


def get_email_subject(key):
    """Get email subject from S3 object"""
    try:
        response = s3.get_object(Bucket=BUCKET, Key=key)
        email_content = response['Body'].read()
        
        # Quick parse to get subject
        from email import message_from_bytes
        msg = message_from_bytes(email_content)
        subject = msg.get('Subject', 'No subject')
        from_addr = msg.get('From', 'Unknown')
        date = msg.get('Date', 'Unknown')
        
        return {
            'subject': subject,
            'from': from_addr,
            'date': date
        }
    except Exception as e:
        return {'subject': 'Error reading email', 'from': '', 'date': ''}


def test_email(key):
    """Test email with parser Lambda"""
    payload = {
        "Records": [{
            "body": json.dumps({
                "bucket": BUCKET,
                "key": key,
                "idempotency_key": f"test-{key.split('/')[-1][:16]}"
            })
        }]
    }
    
    response = lambda_client.invoke(
        FunctionName=PARSER_FUNCTION,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    result = json.loads(response['Payload'].read())
    return result


def get_decision_logs(ticker, since_minutes=2):
    """Get URL selection decision logs for a ticker"""
    query = f"""
    fields @timestamp, outcome.selected_url, outcome.winning_score, candidate_urls
    | filter event_type = "url_selection_decision"
    | filter ticker = "{ticker}"
    | sort @timestamp desc
    | limit 1
    """
    
    start_time = int((time.time() - since_minutes * 60) * 1000)
    end_time = int(time.time() * 1000)
    
    try:
        response = logs.start_query(
            logGroupName=LOG_GROUP,
            startTime=start_time,
            endTime=end_time,
            queryString=query
        )
        
        query_id = response['queryId']
        
        # Wait for query to complete
        for _ in range(10):
            time.sleep(0.5)
            result = logs.get_query_results(queryId=query_id)
            if result['status'] == 'Complete':
                return result.get('results', [])
        
        return []
    except Exception as e:
        print(f"{YELLOW}Note: Could not fetch decision logs: {e}{RESET}")
        return []


def get_saved_urls(ticker):
    """Check what URLs were saved to DynamoDB for this ticker"""
    table = dynamodb.Table('reitsheet-reit-news')
    
    try:
        response = table.scan(
            FilterExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': ticker}
        )
        return response.get('Items', [])
    except Exception as e:
        return []


def main():
    print(f"\n{BOLD}=== Email Processing - One by One ==={RESET}\n")
    
    # Get all emails
    emails = get_all_emails()
    print(f"Found {len(emails)} emails in S3\n")
    
    if not emails:
        print("No emails found!")
        return
    
    for i, key in enumerate(emails, 1):
        # Get email details
        email_info = get_email_subject(key)
        
        print(f"\n{BOLD}{'='*80}{RESET}")
        print(f"{BOLD}Email {i}/{len(emails)}{RESET}")
        print(f"{BOLD}{'='*80}{RESET}")
        print(f"S3 Key:  {BLUE}{key}{RESET}")
        print(f"From:    {email_info['from']}")
        print(f"Date:    {email_info['date']}")
        print(f"Subject: {GREEN}{email_info['subject']}{RESET}")
        print()
        
        # Ask user what to do
        choice = input(f"[{i}/{len(emails)}] (t)est, (s)kip, (q)uit? ").lower().strip()
        
        if choice == 'q':
            print("\nExiting...")
            break
        elif choice == 's':
            print(f"{YELLOW}Skipped{RESET}")
            continue
        elif choice != 't':
            print(f"{YELLOW}Invalid choice, skipping{RESET}")
            continue
        
        # Test the email
        print(f"\n{BLUE}Testing email...{RESET}")
        result = test_email(key)
        
        # Parse result
        body = json.loads(result.get('body', '{}'))
        print(f"\n{BOLD}Parser Result:{RESET}")
        print(f"  Processed: {body.get('processed', 0)}")
        print(f"  Skipped:   {body.get('skipped', 0)}")
        print(f"  Failed:    {body.get('failed', 0)}")
        print(f"  Routing:   {body.get('routing', {})}")
        
        # If enricher was called, wait and check decision logs
        routing = body.get('routing', {})
        if routing.get('enricher', 0) > 0:
            print(f"\n{BLUE}Waiting for enricher to process...{RESET}")
            time.sleep(3)
            
            # Try to extract ticker from subject or from
            # This is a simple heuristic - might need improvement
            ticker = "UNKNOWN"
            
            print(f"\n{BOLD}Checking DynamoDB for saved URLs...{RESET}")
            # Get recent saves (last 30 seconds)
            table = dynamodb.Table('reitsheet-reit-news')
            response = table.scan(Limit=10)
            recent_items = sorted(response.get('Items', []), 
                                key=lambda x: x.get('first_seen_at', ''), 
                                reverse=True)
            
            if recent_items:
                latest = recent_items[0]
                print(f"\n{GREEN}✓ Saved to DynamoDB:{RESET}")
                print(f"  Ticker: {latest.get('ticker')}")
                print(f"  Title:  {latest.get('title', '')[:60]}...")
                print(f"  URL:    {latest.get('url', '')[:80]}...")
                print(f"  Method: {latest.get('construction_method', 'unknown')}")
                print(f"  Source: {latest.get('source', 'unknown')}")
            else:
                print(f"{YELLOW}No items saved (might be duplicate){RESET}")
        
        elif routing.get('skipped', 0) > 0:
            print(f"\n{YELLOW}✓ Email was skipped (confirmation or SEC filing){RESET}")
        
        print()
    
    print(f"\n{BOLD}=== Testing Complete ==={RESET}")
    print(f"\n{GREEN}Check DynamoDB to see all saved URLs{RESET}")
    print(f"{BLUE}aws dynamodb scan --table-name reitsheet-reit-news --query 'Items[*].[ticker.S,title.S,url.S]' --output table{RESET}\n")


if __name__ == '__main__':
    main()
