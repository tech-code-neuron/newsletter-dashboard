#!/usr/bin/env python3
"""
Migrate REIT News Table from V1 to V2 Schema

OLD SCHEMA (V1):
  Primary Key: press_release_id (HASH) + first_seen_at (RANGE)
  Problem: Allows duplicates (same press_release_id, different timestamps)

NEW SCHEMA (V2):
  Primary Key: url (HASH only)
  Benefit: Natural deduplication, URL is unique identifier

MIGRATION STRATEGY:
  1. Scan old table
  2. Deduplicate by URL (keep newest by first_seen_at)
  3. Insert into new table (URL as primary key)
  4. Report statistics (total, duplicates removed, migrated)

IDEMPOTENT: Can be run multiple times safely
"""

import boto3
from datetime import datetime, timezone
import hashlib
import sys
from collections import defaultdict

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table names
OLD_TABLE = 'reitsheet-reit-news'
NEW_TABLE = 'reitsheet-reit-news-v2'

def migrate():
    """Main migration function"""
    print("=" * 80)
    print("REIT News Table Migration: V1 → V2")
    print("=" * 80)
    print(f"Source: {OLD_TABLE}")
    print(f"Target: {NEW_TABLE}")
    print()

    # Connect to tables
    old_table = dynamodb.Table(OLD_TABLE)
    new_table = dynamodb.Table(NEW_TABLE)

    # Step 1: Scan old table
    print("Step 1: Scanning old table...")
    items = scan_table(old_table)
    print(f"  ✓ Found {len(items)} records in old table")
    print()

    # Step 2: Deduplicate by URL
    print("Step 2: Deduplicating by URL...")
    deduplicated = deduplicate_by_url(items)
    duplicates_removed = len(items) - len(deduplicated)
    print(f"  ✓ Kept {len(deduplicated)} unique URLs")
    print(f"  ✓ Removed {duplicates_removed} duplicates")
    print()

    # Step 3: Show sample duplicates
    if duplicates_removed > 0:
        show_duplicate_examples(items)
        print()

    # Step 4: Migrate to new table
    print("Step 3: Migrating to new table...")
    migrated = migrate_to_new_table(deduplicated, new_table)
    print(f"  ✓ Migrated {migrated} records")
    print()

    # Step 5: Verify
    print("Step 4: Verifying migration...")
    verify_migration(old_table, new_table, deduplicated)
    print()

    # Summary
    print("=" * 80)
    print("MIGRATION COMPLETE ✅")
    print("=" * 80)
    print(f"Total records in old table:     {len(items)}")
    print(f"Duplicates removed:             {duplicates_removed}")
    print(f"Unique records migrated:        {migrated}")
    print(f"New table record count:         {new_table.item_count}")
    print()
    print("Next Steps:")
    print("  1. Run verification: python3 scripts/verify_migration.py")
    print("  2. Update Lambda env vars: REIT_NEWS_TABLE=reitsheet-reit-news-v2")
    print("  3. Deploy updated Lambdas")
    print("  4. Monitor for 24-48 hours")
    print("  5. Delete old table (keep for 7 days as backup)")
    print()


def scan_table(table):
    """Scan entire table and return all items"""
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    return items


def deduplicate_by_url(items):
    """
    Deduplicate by URL, keeping the newest record (by first_seen_at)

    Returns: dict of {url: item}
    """
    url_map = {}

    for item in items:
        url = item.get('url')

        if not url:
            print(f"  ⚠️  Skipping item without URL: {item.get('press_release_id', 'UNKNOWN')}")
            continue

        # If we've seen this URL before, keep the newer one
        if url in url_map:
            existing = url_map[url]
            existing_date = existing.get('first_seen_at', '')
            new_date = item.get('first_seen_at', '')

            # Keep the newer one (larger ISO timestamp = more recent)
            if new_date > existing_date:
                url_map[url] = item
        else:
            url_map[url] = item

    return url_map


def show_duplicate_examples(items):
    """Show examples of duplicates that were removed"""
    print("  Example duplicates removed:")

    # Group by URL
    url_groups = defaultdict(list)
    for item in items:
        url = item.get('url')
        if url:
            url_groups[url].append(item)

    # Find URLs with duplicates
    duplicates = {url: items for url, items in url_groups.items() if len(items) > 1}

    # Show first 3 examples
    for i, (url, dup_items) in enumerate(list(duplicates.items())[:3]):
        ticker = dup_items[0].get('ticker', 'UNKNOWN')
        title = dup_items[0].get('title', 'Unknown Title')
        print(f"\n  Duplicate {i+1}: {ticker} - {title[:50]}...")
        print(f"    URL: {url[:70]}...")
        print(f"    Found {len(dup_items)} copies:")
        for j, dup in enumerate(dup_items, 1):
            first_seen = dup.get('first_seen_at', 'Unknown')
            source = dup.get('source', 'unknown')
            print(f"      {j}. {first_seen} ({source})")


def migrate_to_new_table(deduplicated, new_table):
    """Migrate deduplicated records to new table"""
    migrated = 0
    errors = 0

    for url, item in deduplicated.items():
        try:
            # Create new item with URL as primary key
            new_item = {
                'url': url,  # Primary key
                'ticker': item.get('ticker', 'UNKNOWN'),
                'title': item.get('title', ''),
                'first_seen_at': item.get('first_seen_at', datetime.now(timezone.utc).isoformat()),
                'press_release_date': item.get('press_release_date', item.get('first_seen_at', '')[:10]),
                'source': item.get('source', 'migrated_from_v1'),
                'needs_scraping': item.get('needs_scraping', False),
                'construction_method': item.get('construction_method', 'unknown'),
                'match_quality': item.get('match_quality', 'unknown'),
            }

            # Copy optional fields if they exist
            optional_fields = ['company_name', 'press_release_title', 'email_subject',
                             'email_date', 'idempotency_key', 'migrated_from_press_release_id']
            for field in optional_fields:
                if field in item:
                    new_item[field] = item[field]

            # Store original press_release_id for reference
            new_item['migrated_from_press_release_id'] = item.get('press_release_id', 'unknown')

            # Use conditional write to prevent overwriting (idempotent)
            new_table.put_item(
                Item=new_item,
                ConditionExpression='attribute_not_exists(#url)',
                ExpressionAttributeNames={'#url': 'url'}
            )

            migrated += 1

            if migrated % 10 == 0:
                print(f"  Migrated {migrated}/{len(deduplicated)} records...", end='\r')

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # Record already exists in new table (from previous run)
            migrated += 1

        except Exception as e:
            print(f"\n  ❌ Error migrating {url}: {e}")
            errors += 1

    print(f"  Migrated {migrated}/{len(deduplicated)} records... ✓")

    if errors > 0:
        print(f"  ⚠️  {errors} errors occurred")

    return migrated


def verify_migration(old_table, new_table, deduplicated):
    """Verify migration completed successfully"""
    old_count = old_table.item_count
    new_count = new_table.item_count
    expected_count = len(deduplicated)

    print(f"  Old table count: {old_count}")
    print(f"  Expected count:  {expected_count}")
    print(f"  New table count: {new_count}")

    if new_count >= expected_count:
        print(f"  ✅ Migration verified (new table has {new_count} records)")
    else:
        print(f"  ⚠️  Warning: Expected {expected_count}, but new table has {new_count}")
        print(f"      Missing {expected_count - new_count} records")


if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
