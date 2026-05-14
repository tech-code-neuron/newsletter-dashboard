#!/usr/bin/env python3
"""Clear all items from reitsheet-reit-news table to start fresh"""
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('reitsheet-reit-news')

print("🗑️  Clearing reitsheet-reit-news table...")

# Scan and delete all items
response = table.scan()
items = response.get('Items', [])

deleted = 0
for item in items:
    table.delete_item(
        Key={
            'press_release_id': item['press_release_id'],
            'first_seen_at': item['first_seen_at']
        }
    )
    deleted += 1
    if deleted % 10 == 0:
        print(f"  Deleted {deleted} items...")

# Handle pagination if more than 1MB
while 'LastEvaluatedKey' in response:
    response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
    items = response.get('Items', [])
    for item in items:
        table.delete_item(
            Key={
                'press_release_id': item['press_release_id'],
                'first_seen_at': item['first_seen_at']
            }
        )
        deleted += 1
        if deleted % 10 == 0:
            print(f"  Deleted {deleted} items...")

print(f"\n✅ Cleared {deleted} items from table")
print("📧 Ready to reprocess all emails!")
