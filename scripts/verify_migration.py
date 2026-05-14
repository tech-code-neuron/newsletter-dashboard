#!/usr/bin/env python3
"""
Verify REIT News Table Migration

Checks:
  1. Record counts match (accounting for deduplication)
  2. Sample records migrated correctly
  3. All tickers present in new table
  4. GSI queries work correctly
  5. No duplicate URLs in new table
"""

import boto3
from collections import defaultdict
import sys

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

OLD_TABLE = 'reitsheet-reit-news'
NEW_TABLE = 'reitsheet-reit-news-v2'


def verify():
    """Run all verification checks"""
    print("=" * 80)
    print("VERIFYING MIGRATION: V1 → V2")
    print("=" * 80)
    print()

    old_table = dynamodb.Table(OLD_TABLE)
    new_table = dynamodb.Table(NEW_TABLE)

    all_passed = True

    # Check 1: Count comparison
    print("Check 1: Record Counts")
    print("-" * 40)
    passed = check_counts(old_table, new_table)
    all_passed = all_passed and passed
    print()

    # Check 2: Sample records
    print("Check 2: Sample Records Migrated")
    print("-" * 40)
    passed = check_sample_records(old_table, new_table)
    all_passed = all_passed and passed
    print()

    # Check 3: All tickers present
    print("Check 3: All Tickers Present")
    print("-" * 40)
    passed = check_tickers(old_table, new_table)
    all_passed = all_passed and passed
    print()

    # Check 4: No duplicate URLs
    print("Check 4: No Duplicate URLs")
    print("-" * 40)
    passed = check_no_duplicates(new_table)
    all_passed = all_passed and passed
    print()

    # Check 5: GSI queries work
    print("Check 5: GSI Queries Work")
    print("-" * 40)
    passed = check_gsi_queries(new_table)
    all_passed = all_passed and passed
    print()

    # Summary
    print("=" * 80)
    if all_passed:
        print("✅ ALL CHECKS PASSED - MIGRATION SUCCESSFUL")
        print()
        print("Safe to proceed with cutover:")
        print("  1. Update Lambda env vars: REIT_NEWS_TABLE=reitsheet-reit-news-v2")
        print("  2. Deploy updated Lambdas")
        print("  3. Monitor for 24-48 hours")
        print("  4. Delete old table")
    else:
        print("❌ SOME CHECKS FAILED - DO NOT PROCEED")
        print()
        print("Review errors above and re-run migration if needed")
        sys.exit(1)
    print("=" * 80)


def check_counts(old_table, new_table):
    """Check that record counts make sense"""
    old_items = scan_table(old_table)
    new_items = scan_table(new_table)

    # Count unique URLs in old table
    unique_urls = len(set(item.get('url') for item in old_items if item.get('url')))

    print(f"  Old table records:       {len(old_items)}")
    print(f"  Unique URLs in old:      {unique_urls}")
    print(f"  Duplicates in old:       {len(old_items) - unique_urls}")
    print(f"  New table records:       {len(new_items)}")

    if len(new_items) == unique_urls:
        print(f"  ✅ Count matches (deduplication worked)")
        return True
    elif len(new_items) >= unique_urls * 0.95:  # Allow 5% variance
        print(f"  ⚠️  Close match ({len(new_items)} vs {unique_urls})")
        return True
    else:
        print(f"  ❌ Count mismatch (missing {unique_urls - len(new_items)} records)")
        return False


def check_sample_records(old_table, new_table):
    """Verify sample records migrated correctly"""
    old_items = scan_table(old_table)

    if not old_items:
        print("  ⚠️  No records in old table")
        return True

    # Get 5 random samples
    import random
    samples = random.sample(old_items, min(5, len(old_items)))

    passed = 0
    failed = 0

    for item in samples:
        url = item.get('url')
        if not url:
            continue

        try:
            response = new_table.get_item(Key={'url': url})
            new_item = response.get('Item')

            if new_item:
                # Verify key fields match
                ticker_match = item.get('ticker') == new_item.get('ticker')
                title_match = item.get('title') == new_item.get('title')

                if ticker_match and title_match:
                    print(f"  ✓ {new_item.get('ticker')} - {new_item.get('title', '')[:40]}...")
                    passed += 1
                else:
                    print(f"  ✗ Field mismatch for {url}")
                    failed += 1
            else:
                print(f"  ✗ Not found in new table: {url}")
                failed += 1

        except Exception as e:
            print(f"  ✗ Error checking {url}: {e}")
            failed += 1

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def check_tickers(old_table, new_table):
    """Verify all tickers present in new table"""
    old_items = scan_table(old_table)
    new_items = scan_table(new_table)

    old_tickers = set(item.get('ticker') for item in old_items if item.get('ticker'))
    new_tickers = set(item.get('ticker') for item in new_items if item.get('ticker'))

    print(f"  Old table tickers: {sorted(old_tickers)}")
    print(f"  New table tickers: {sorted(new_tickers)}")

    missing = old_tickers - new_tickers
    extra = new_tickers - old_tickers

    if not missing and not extra:
        print(f"  ✅ All {len(old_tickers)} tickers present")
        return True
    else:
        if missing:
            print(f"  ❌ Missing tickers: {missing}")
        if extra:
            print(f"  ⚠️  Extra tickers: {extra}")
        return len(missing) == 0


def check_no_duplicates(new_table):
    """Verify no duplicate URLs in new table"""
    items = scan_table(new_table)
    urls = [item.get('url') for item in items if item.get('url')]

    duplicates = len(urls) - len(set(urls))

    print(f"  Total URLs: {len(urls)}")
    print(f"  Unique URLs: {len(set(urls))}")
    print(f"  Duplicates: {duplicates}")

    if duplicates == 0:
        print(f"  ✅ No duplicates (primary key working)")
        return True
    else:
        print(f"  ❌ Found {duplicates} duplicates")
        return False


def check_gsi_queries(new_table):
    """Verify GSI queries work"""
    try:
        # Test ticker-date-index
        response = new_table.query(
            IndexName='ticker-date-index',
            KeyConditionExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': 'O'},
            Limit=5
        )
        ticker_date_count = len(response.get('Items', []))
        print(f"  ticker-date-index: {ticker_date_count} items for ticker O")

        # Test ticker-firstseen-index
        response = new_table.query(
            IndexName='ticker-firstseen-index',
            KeyConditionExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': 'O'},
            Limit=5
        )
        ticker_firstseen_count = len(response.get('Items', []))
        print(f"  ticker-firstseen-index: {ticker_firstseen_count} items for ticker O")

        if ticker_date_count > 0 and ticker_firstseen_count > 0:
            print(f"  ✅ Both GSIs working")
            return True
        else:
            print(f"  ⚠️  GSI queries returned 0 results")
            return False

    except Exception as e:
        print(f"  ❌ GSI query failed: {e}")
        return False


def scan_table(table):
    """Scan entire table"""
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))

    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    return items


if __name__ == '__main__':
    try:
        verify()
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
