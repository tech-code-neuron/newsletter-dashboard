#!/usr/bin/env python3
"""
Merge DynamoDB Companies Tables
===============================
Consolidates reitsheet-companies (older) INTO reitsheet-companies-config (newer).
Newer data wins during merge.

Usage:
    python3 scripts/merge_companies_tables.py --dry-run  # Preview changes
    python3 scripts/merge_companies_tables.py --execute  # Execute merge
    python3 scripts/merge_companies_tables.py --verify   # Verify after merge

Exit codes:
    0 = Success
    1 = Error
"""

import argparse
import json
import sys
from datetime import datetime

import boto3

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

# Table names
OLD_TABLE = 'reitsheet-companies'
NEW_TABLE = 'reitsheet-companies-config'


def scan_table(table_name):
    """Scan all items from a DynamoDB table using boto3.resource."""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    items = []
    response = table.scan()
    items.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    return items


def merge_items(old_items, new_items):
    """
    Merge items from old table into new table.

    Strategy: Newer data wins. Fields from new table take precedence.
    Missing fields from old table are added to new item.

    Returns:
        list: Merged items ready for write
        dict: Merge report
    """
    # Index by ticker
    old_by_ticker = {item['ticker']: item for item in old_items}
    new_by_ticker = {item['ticker']: item for item in new_items}

    all_tickers = set(old_by_ticker.keys()) | set(new_by_ticker.keys())

    merged = []
    report = {
        'only_in_old': [],
        'only_in_new': [],
        'merged': [],
        'unchanged': []
    }

    for ticker in sorted(all_tickers):
        old_item = old_by_ticker.get(ticker, {})
        new_item = new_by_ticker.get(ticker, {})

        if ticker in old_by_ticker and ticker not in new_by_ticker:
            # Only in old table - add to new
            report['only_in_old'].append(ticker)
            merged.append(old_item)
        elif ticker not in old_by_ticker and ticker in new_by_ticker:
            # Only in new table - keep as is
            report['only_in_new'].append(ticker)
            merged.append(new_item)
        else:
            # In both - merge (new wins, old fills gaps)
            result = dict(old_item)  # Start with old
            result.update(new_item)  # New overwrites

            if result != new_item:
                report['merged'].append(ticker)
            else:
                report['unchanged'].append(ticker)

            merged.append(result)

    return merged, report


def write_items(table_name, items, dry_run=False):
    """Write items to DynamoDB table using batch_writer."""
    if dry_run:
        print(f"\n{YELLOW}[DRY RUN] Would write {len(items)} items to {table_name}{RESET}")
        return True

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    print(f"\n{CYAN}Writing {len(items)} items to {table_name}...{RESET}")

    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    print(f"{GREEN}Successfully wrote {len(items)} items{RESET}")
    return True


def print_report(report, old_count, new_count, merged_count):
    """Print merge report."""
    print(f"\n{'=' * 60}")
    print(f"{CYAN}Merge Report{RESET}")
    print(f"{'=' * 60}")

    print(f"\n{YELLOW}Source Tables:{RESET}")
    print(f"  {OLD_TABLE}: {old_count} items")
    print(f"  {NEW_TABLE}: {new_count} items")

    print(f"\n{YELLOW}Result:{RESET}")
    print(f"  Total merged: {merged_count} items")

    if report['only_in_old']:
        print(f"\n{GREEN}Added from old table ({len(report['only_in_old'])}):{RESET}")
        for ticker in report['only_in_old']:
            print(f"  + {ticker}")

    if report['merged']:
        print(f"\n{CYAN}Merged (old filled gaps) ({len(report['merged'])}):{RESET}")
        for ticker in report['merged']:
            print(f"  ~ {ticker}")

    if report['unchanged']:
        print(f"\n{YELLOW}Unchanged ({len(report['unchanged'])}):{RESET}")
        print(f"  {', '.join(report['unchanged'][:10])}", end='')
        if len(report['unchanged']) > 10:
            print(f"... and {len(report['unchanged']) - 10} more")
        else:
            print()

    print(f"\n{'=' * 60}")


def verify_merge():
    """Verify the merged table has expected data."""
    print(f"\n{CYAN}Verifying merged table...{RESET}")

    items = scan_table(NEW_TABLE)

    print(f"\n{GREEN}Table: {NEW_TABLE}{RESET}")
    print(f"Total items: {len(items)}")

    # Check for required fields
    required_fields = ['ticker', 'company_name']
    optional_fields = ['url_construction_method', 'press_release_url',
                       'playwright_url', 'playwright_selector', 'playwright_wait_for']

    missing_required = []
    playwright_companies = []

    for item in items:
        ticker = item.get('ticker', 'UNKNOWN')

        for field in required_fields:
            if field not in item:
                missing_required.append((ticker, field))

        if item.get('url_construction_method') == 'playwright_scraper':
            playwright_companies.append(ticker)

    if missing_required:
        print(f"\n{RED}Missing required fields:{RESET}")
        for ticker, field in missing_required:
            print(f"  {ticker}: missing '{field}'")
    else:
        print(f"\n{GREEN}All required fields present{RESET}")

    if playwright_companies:
        print(f"\n{CYAN}Playwright companies ({len(playwright_companies)}):{RESET}")
        for ticker in playwright_companies:
            item = next(i for i in items if i['ticker'] == ticker)
            has_url = 'playwright_url' in item
            has_selector = 'playwright_selector' in item
            has_wait = 'playwright_wait_for' in item

            status = f"{GREEN}OK{RESET}" if (has_url and has_selector) else f"{RED}INCOMPLETE{RESET}"
            print(f"  {ticker}: {status}")
            if not has_url:
                print(f"    {RED}Missing: playwright_url{RESET}")
            if not has_selector:
                print(f"    {RED}Missing: playwright_selector{RESET}")

    return len(missing_required) == 0


def main():
    parser = argparse.ArgumentParser(description='Merge DynamoDB companies tables')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true',
                       help='Preview merge without making changes')
    group.add_argument('--execute', action='store_true',
                       help='Execute the merge')
    group.add_argument('--verify', action='store_true',
                       help='Verify the merged table')

    args = parser.parse_args()

    if args.verify:
        success = verify_merge()
        return 0 if success else 1

    print(f"{'=' * 60}")
    print(f"{CYAN}DynamoDB Table Merge{RESET}")
    print(f"{'=' * 60}")
    print(f"\nMerging: {OLD_TABLE} → {NEW_TABLE}")
    print(f"Strategy: Newer data wins (from {NEW_TABLE})")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")

    # Scan both tables
    print(f"\n{CYAN}Scanning tables...{RESET}")
    try:
        old_items = scan_table(OLD_TABLE)
        print(f"  {OLD_TABLE}: {len(old_items)} items")
    except Exception as e:
        print(f"  {YELLOW}{OLD_TABLE}: Table not found or empty ({e}){RESET}")
        old_items = []

    try:
        new_items = scan_table(NEW_TABLE)
        print(f"  {NEW_TABLE}: {len(new_items)} items")
    except Exception as e:
        print(f"  {RED}{NEW_TABLE}: Error scanning ({e}){RESET}")
        return 1

    if not old_items and not new_items:
        print(f"\n{YELLOW}Both tables empty - nothing to merge{RESET}")
        return 0

    # Merge
    merged_items, report = merge_items(old_items, new_items)

    # Print report
    print_report(report, len(old_items), len(new_items), len(merged_items))

    # Write merged data
    if args.execute:
        print(f"\n{YELLOW}Executing merge...{RESET}")
        success = write_items(NEW_TABLE, merged_items, dry_run=False)

        if success:
            print(f"\n{GREEN}Merge complete!{RESET}")
            print(f"\n{YELLOW}Next steps:{RESET}")
            print(f"  1. Verify: python3 scripts/merge_companies_tables.py --verify")
            print(f"  2. Update Terraform env vars to use {NEW_TABLE}")
            print(f"  3. Test all Lambdas")
            print(f"  4. Delete old table: aws dynamodb delete-table --table-name {OLD_TABLE}")

        return 0 if success else 1
    else:
        write_items(NEW_TABLE, merged_items, dry_run=True)
        print(f"\n{YELLOW}To execute merge, run:{RESET}")
        print(f"  python3 scripts/merge_companies_tables.py --execute")
        return 0


if __name__ == '__main__':
    sys.exit(main())
