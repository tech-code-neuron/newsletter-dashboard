#!/usr/bin/env python3
"""
Find Operating Partnership CIKs from SEC EDGAR and update DynamoDB.

For UPREITs, the Operating Partnership (OP) files jointly with the REIT.
This script searches SEC EDGAR for L.P. co-filers and updates DynamoDB.

Usage:
    python scripts/find_op_cik.py                    # Scan all public companies
    python scripts/find_op_cik.py --ticker SPG      # Check specific ticker
    python scripts/find_op_cik.py --dry-run         # Preview without updating

Examples:
    # Check what would be updated without making changes
    python scripts/find_op_cik.py --dry-run

    # Update a specific company
    python scripts/find_op_cik.py --ticker SPG

    # Force update even if op_cik already set
    python scripts/find_op_cik.py --ticker SPG --force
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

import boto3


def find_op_for_company(company_name: str, reit_cik: str = None) -> tuple:
    """
    Search SEC EDGAR for L.P. co-filer in the company's 10-K filings.

    Args:
        company_name: Company name to search for
        reit_cik: REIT's CIK (used to avoid returning the REIT itself as OP)

    Returns:
        (op_cik, op_name) or (None, None) if not found
    """
    search_name = urllib.parse.quote(company_name)
    url = (
        f"https://efts.sec.gov/LATEST/search-index?"
        f"q={search_name}&dateRange=custom&startdt=2024-01-01&enddt=2026-12-31&forms=10-K"
    )

    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'reit-newsletter contact@your-domain.com'}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    Error querying SEC: {e}")
        return None, None

    # Search through first few filings for L.P. co-filers
    for hit in data.get('hits', {}).get('hits', [])[:5]:
        names = hit['_source'].get('display_names', [])
        ciks = hit['_source'].get('ciks', [])

        for i, name in enumerate(names):
            # Check if this is an L.P. entity
            if not ('L.P.' in name or 'L P' in name or ', LP' in name):
                continue

            # Extract CIK from display name format: "Company Name  (CIK 0001234567)"
            match = re.search(r'CIK\s*(\d+)', name)
            if not match:
                continue

            op_cik = match.group(1).zfill(10)

            # Skip if this is the same as the REIT CIK
            if reit_cik and op_cik == reit_cik:
                continue

            # Clean up name (remove CIK suffix and ticker info)
            op_name = re.sub(r'\s*\([^)]*CIK[^)]*\)\s*$', '', name).strip()
            op_name = re.sub(r'\s*\([A-Z0-9-]+\)\s*$', '', op_name).strip()

            return op_cik, op_name

    return None, None


def get_public_companies(table, ticker: str = None):
    """
    Get public companies from DynamoDB.

    Args:
        table: DynamoDB table resource
        ticker: Optional specific ticker to fetch

    Returns:
        List of company dicts
    """
    if ticker:
        response = table.get_item(Key={'ticker': ticker.upper()})
        item = response.get('Item')
        if item:
            return [item]
        print(f"Company not found: {ticker}")
        return []

    # Scan for public companies with CIK set
    from boto3.dynamodb.conditions import Attr

    response = table.scan(
        FilterExpression=Attr('is_public').eq(True) & Attr('cik').exists()
    )
    items = response.get('Items', [])

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            FilterExpression=Attr('is_public').eq(True) & Attr('cik').exists(),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))

    return items


def update_dynamodb(table, ticker: str, op_cik: str, op_name: str, dry_run: bool = False):
    """
    Update company record in DynamoDB with OP fields.

    Only updates op_cik and op_name - leaves existing cik field untouched.
    """
    if dry_run:
        print(f"    [DRY RUN] Would update: op_cik={op_cik}, op_name={op_name}")
        return True

    try:
        table.update_item(
            Key={'ticker': ticker},
            UpdateExpression='SET op_cik = :cik, op_name = :name, updated_at = :ts',
            ExpressionAttributeValues={
                ':cik': op_cik,
                ':name': op_name,
                ':ts': datetime.now(timezone.utc).isoformat()
            }
        )
        print(f"    Updated: op_cik={op_cik}, op_name={op_name}")
        return True
    except Exception as e:
        print(f"    Error updating DynamoDB: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Find Operating Partnership CIKs from SEC EDGAR'
    )
    parser.add_argument(
        '--ticker',
        help='Process specific ticker only'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without updating DynamoDB'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Update even if op_cik already set'
    )

    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('reitsheet-companies-config')

    companies = get_public_companies(table, args.ticker)
    if not companies:
        print("No companies to process")
        return

    print(f"\nProcessing {len(companies)} public companies...")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]\n")

    found_count = 0
    updated_count = 0
    skipped_count = 0

    for company in sorted(companies, key=lambda x: x.get('ticker', '')):
        ticker = company.get('ticker', '')
        name = company.get('company_name', '')
        reit_cik = company.get('cik', '')
        existing_op_cik = company.get('op_cik', '')

        print(f"\n{ticker} ({name}):")
        print(f"  REIT CIK: {reit_cik}")

        # Skip if already has OP CIK (unless --force)
        if existing_op_cik and not args.force:
            print(f"  Already has OP CIK: {existing_op_cik} (use --force to update)")
            skipped_count += 1
            continue

        # Search SEC for OP
        op_cik, op_name = find_op_for_company(name, reit_cik)

        if op_cik:
            found_count += 1
            print(f"  Found OP: {op_name}")
            print(f"  OP CIK: {op_cik}")

            if update_dynamodb(table, ticker, op_cik, op_name, args.dry_run):
                updated_count += 1
        else:
            print("  No OP found (may not be UPREIT structure)")

        # Rate limit to avoid overwhelming SEC API
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Companies processed: {len(companies)}")
    print(f"  OPs found: {found_count}")
    print(f"  Records updated: {updated_count}")
    print(f"  Skipped (already set): {skipped_count}")

    if args.dry_run:
        print("\n[DRY RUN - No changes were made]")


if __name__ == '__main__':
    import urllib.parse  # Import here to ensure it's available
    main()
