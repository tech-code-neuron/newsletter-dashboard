#!/usr/bin/env python3
"""Clear idempotency table to allow reprocessing all emails"""
import boto3

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('reitsheet-inbound-log')

print("🗑️  Clearing idempotency table (reitsheet-inbound-log)...")

# Scan and delete all items
response = table.scan()
items = response.get('Items', [])

deleted = 0
for item in items:
    table.delete_item(
        Key={'idempotency_key': item['idempotency_key']}
    )
    deleted += 1
    if deleted % 50 == 0:
        print(f"  Deleted {deleted} items...")

# Handle pagination
while 'LastEvaluatedKey' in response:
    response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
    items = response.get('Items', [])
    for item in items:
        table.delete_item(
            Key={'idempotency_key': item['idempotency_key']}
        )
        deleted += 1
        if deleted % 50 == 0:
            print(f"  Deleted {deleted} items...")

print(f"\n✅ Cleared {deleted} idempotency records")
print("📧 Ready to reprocess emails!")
