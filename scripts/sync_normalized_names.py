#!/usr/bin/env python3
"""
Sync Normalized Names - Bulk Update DynamoDB Company Names
===========================================================
Uses actual parser normalization logic to update all companies

Usage:
    python scripts/sync_normalized_names.py --dry-run    # Preview changes
    python scripts/sync_normalized_names.py --apply      # Apply updates
    python scripts/sync_normalized_names.py --ticker PEB,SMA --apply  # Specific companies

Author: Claude Code
Date: 2026-03-11
"""

import sys
import os
import re
import argparse
import json
from datetime import datetime

# Add Lambda parser to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'infrastructure', 'lambdas', 'parser'))

import boto3
from botocore.exceptions import ClientError

# Import normalization logic from parser
from constants import COMPANY_NAME_SUFFIXES

# Import or redefine normalize function (to avoid Lambda dependencies)
def normalize_company_name(name):
    """
    Normalize company name for fuzzy matching

    Examples:
        "Alexander's, Inc." → "alexanders"
        "Terreno Realty Corporation" → "terreno realty"
        "SL Green Realty Corp." → "sl green realty"
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower()

    # Remove common suffixes
    for suffix in COMPANY_NAME_SUFFIXES:
        normalized = re.sub(suffix, '', normalized)

    # Remove all punctuation except spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized.strip()


def scan_companies(dynamodb, table_name, ticker_filter=None):
    """Scan all companies from DynamoDB"""
    table = dynamodb.Table(table_name)

    companies = []
    scan_kwargs = {}

    if ticker_filter:
        # Batch get specific tickers
        tickers = [t.strip() for t in ticker_filter.split(',')]
        response = dynamodb.batch_get_item(
            RequestItems={
                table_name: {
                    'Keys': [{'ticker': ticker} for ticker in tickers]
                }
            }
        )
        companies = response['Responses'].get(table_name, [])
    else:
        # Full table scan
        while True:
            response = table.scan(**scan_kwargs)
            companies.extend(response.get('Items', []))

            # Check for more pages
            if 'LastEvaluatedKey' not in response:
                break
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    return companies


def update_normalized_name(dynamodb, table_name, ticker, normalized_name):
    """Update normalized_name field for a company"""
    table = dynamodb.Table(table_name)

    try:
        table.update_item(
            Key={'ticker': ticker},
            UpdateExpression='SET normalized_name = :name',
            ExpressionAttributeValues={':name': normalized_name}
        )
        return True
    except ClientError as e:
        print(f"❌ Error updating {ticker}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Sync normalized company names')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without writing')
    parser.add_argument('--apply', action='store_true',
                       help='Apply changes to DynamoDB')
    parser.add_argument('--ticker', type=str,
                       help='Comma-separated tickers to update (e.g., PEB,SMA)')
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("❌ Must specify either --dry-run or --apply")
        sys.exit(1)

    if args.dry_run and args.apply:
        print("❌ Cannot specify both --dry-run and --apply")
        sys.exit(1)

    # Initialize AWS
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table_name = 'reitsheet-companies-config'

    print(f"{'🔍 DRY RUN MODE' if args.dry_run else '✏️  APPLY MODE'}")
    print(f"Table: {table_name}")
    if args.ticker:
        print(f"Filter: {args.ticker}")
    print("=" * 80)
    print()

    # Scan companies
    print("Scanning companies...")
    companies = scan_companies(dynamodb, table_name, args.ticker)
    print(f"Found {len(companies)} companies")
    print()

    # Track changes
    changes = []
    unchanged = []
    no_name = []

    # Process each company
    for company in companies:
        ticker = company.get('ticker', 'UNKNOWN')
        name = company.get('name', '')
        current_normalized = company.get('normalized_name', '')

        if not name:
            no_name.append(ticker)
            continue

        # Apply normalization
        new_normalized = normalize_company_name(name)

        if new_normalized != current_normalized:
            changes.append({
                'ticker': ticker,
                'name': name,
                'old': current_normalized,
                'new': new_normalized
            })
        else:
            unchanged.append(ticker)

    # Display changes
    if changes:
        print(f"{'📋 WOULD CHANGE' if args.dry_run else '✏️  UPDATING'} {len(changes)} companies:")
        print()

        for change in changes:
            print(f"  {change['ticker']} - {change['name']}")
            print(f"    Old: '{change['old']}'")
            print(f"    New: '{change['new']}'")
            print()

            # Apply if not dry-run
            if args.apply:
                success = update_normalized_name(
                    dynamodb, table_name,
                    change['ticker'], change['new']
                )
                if success:
                    print(f"    ✅ Updated")
                else:
                    print(f"    ❌ Failed")
                print()
    else:
        print("✅ No changes needed - all normalized_name fields are correct!")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total companies: {len(companies)}")
    print(f"{'Would change' if args.dry_run else 'Updated'}: {len(changes)}")
    print(f"Unchanged: {len(unchanged)}")
    if no_name:
        print(f"No name field: {len(no_name)} (skipped)")
    print()

    # Save log
    if changes and args.apply:
        log_file = f"normalized_name_changes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        with open(log_file, 'w') as f:
            json.dump(changes, f, indent=2)
        print(f"📝 Changes logged to: {log_file}")
        print()

    if args.dry_run and changes:
        print("💡 Run with --apply to make these changes")


if __name__ == '__main__':
    main()
