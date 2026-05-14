#!/usr/bin/env python3
"""
Migrate newsletter_title to display_title in DynamoDB.

This script:
1. Scans for records with newsletter_title attribute
2. If display_title is empty: copies newsletter_title to display_title
3. Removes newsletter_title attribute

Usage:
    # Dry run (default) - shows what would change
    python3 scripts/migrate_newsletter_title_to_display_title.py

    # Actually perform migration
    python3 scripts/migrate_newsletter_title_to_display_title.py --execute
"""

import argparse
import boto3
from boto3.dynamodb.conditions import Attr


def migrate_newsletter_titles(table_name: str, dry_run: bool = True):
    """Migrate newsletter_title to display_title."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(table_name)

    print(f"Scanning {table_name} for records with newsletter_title...")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()

    # Scan for records with newsletter_title attribute
    response = table.scan(
        FilterExpression=Attr('newsletter_title').exists()
    )

    items = response.get('Items', [])

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            FilterExpression=Attr('newsletter_title').exists(),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))

    print(f"Found {len(items)} records with newsletter_title")
    print()

    migrated = 0
    errors = 0

    for item in items:
        url = item.get('url', 'NO_URL')
        newsletter_title = item.get('newsletter_title')
        display_title = item.get('display_title')
        title = item.get('title', '')

        print(f"URL: {url[:80]}...")
        print(f"  newsletter_title: {newsletter_title[:60] if newsletter_title else 'None'}...")
        print(f"  display_title: {display_title[:60] if display_title else 'None'}...")
        print(f"  title: {title[:60] if title else 'None'}...")

        # Determine action - always remove the attribute
        if display_title or not newsletter_title:
            print(f"  ACTION: Remove newsletter_title attribute")
        else:
            print(f"  ACTION: Copy newsletter_title -> display_title, then remove")

        if not dry_run:
            try:
                # Always remove newsletter_title
                # Only copy to display_title if it's empty AND newsletter_title has a value
                if not display_title and newsletter_title:
                    table.update_item(
                        Key={'url': url},
                        UpdateExpression='SET display_title = :dt REMOVE newsletter_title',
                        ExpressionAttributeValues={':dt': newsletter_title}
                    )
                else:
                    table.update_item(
                        Key={'url': url},
                        UpdateExpression='REMOVE newsletter_title'
                    )
                print(f"  MIGRATED")
                migrated += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                errors += 1
        else:
            migrated += 1

        print()

    print("=" * 60)
    print(f"Summary:")
    print(f"  Total with newsletter_title: {len(items)}")
    print(f"  Migrated: {migrated}")
    if not dry_run:
        print(f"  Errors: {errors}")
    if dry_run:
        print()
        print("This was a DRY RUN. Run with --execute to perform migration.")


def main():
    parser = argparse.ArgumentParser(description='Migrate newsletter_title to display_title')
    parser.add_argument('--execute', action='store_true',
                        help='Actually perform migration (default is dry run)')
    parser.add_argument('--table', default='reitsheet-reit-news-v2',
                        help='DynamoDB table name')
    args = parser.parse_args()

    migrate_newsletter_titles(args.table, dry_run=not args.execute)


if __name__ == '__main__':
    main()
