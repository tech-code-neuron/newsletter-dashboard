#!/usr/bin/env python3
"""
Populate CIK numbers for all companies from SEC EDGAR

This script:
1. Downloads SEC's official ticker-to-CIK mapping
2. Matches each company in DynamoDB to its CIK
3. Updates DynamoDB with CIK numbers (single source of truth)
4. Optionally discovers Operating Partnership (OP) CIKs from 10-K filings

Usage:
    python3 scripts/populate_cik_numbers.py                    # Dry run
    python3 scripts/populate_cik_numbers.py --apply            # Apply changes
    python3 scripts/populate_cik_numbers.py --ticker EPRT      # Single company
    python3 scripts/populate_cik_numbers.py --discover-ops     # Also find OP CIKs

SEC EDGAR API rate limit: 10 requests/second
"""
import argparse
import json
import os
import sys
import time
from typing import Dict, Optional, Tuple
from urllib.parse import quote

import boto3
import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SEC EDGAR endpoints
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt=2020-01-01&enddt=2030-12-31&forms=10-K"

# User-Agent required by SEC (they block requests without proper UA)
SEC_USER_AGENT = "PressReleasePipeline/1.0 (contact@your-domain.comm)"

# DynamoDB table (single source of truth)
COMPANIES_TABLE = "reitsheet-companies-config"

# Rate limiting
SEC_RATE_LIMIT_DELAY = 0.15  # 150ms between requests (well under 10/sec limit)


def fetch_sec_ticker_mapping() -> Dict[str, dict]:
    """
    Fetch SEC's official ticker-to-CIK mapping.

    Returns:
        Dict mapping ticker (uppercase) to company info dict with keys:
        - cik_str: CIK as string with leading zeros
        - title: Company name
    """
    print("Fetching SEC ticker mapping...")
    headers = {"User-Agent": SEC_USER_AGENT}

    response = requests.get(SEC_TICKERS_URL, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()

    # SEC returns: {"0": {"cik_str": "...", "ticker": "...", "title": "..."}, ...}
    ticker_map = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        if ticker:
            ticker_map[ticker] = {
                "cik_str": str(entry.get("cik_str", "")).zfill(10),
                "title": entry.get("title", ""),
            }

    print(f"Loaded {len(ticker_map)} ticker mappings from SEC")
    return ticker_map


def get_companies_from_dynamodb() -> list:
    """Get all companies from DynamoDB (single source of truth)."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(COMPANIES_TABLE)

    # Scan for all companies
    companies = []
    response = table.scan()
    companies.extend(response.get('Items', []))

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        companies.extend(response.get('Items', []))

    # Sort by ticker
    companies.sort(key=lambda x: x.get('ticker', ''))

    print(f"Found {len(companies)} companies in DynamoDB")
    return companies


def lookup_cik_for_ticker(ticker: str, sec_mapping: Dict[str, dict]) -> Optional[str]:
    """
    Look up CIK for a ticker using SEC's official mapping.

    Args:
        ticker: Stock ticker (e.g., "EPRT")
        sec_mapping: SEC ticker-to-CIK mapping

    Returns:
        CIK string (10 digits with leading zeros) or None
    """
    ticker_upper = ticker.upper()

    if ticker_upper in sec_mapping:
        return sec_mapping[ticker_upper]["cik_str"]

    return None


def search_sec_for_op(company_name: str) -> Optional[Tuple[str, str]]:
    """
    Search SEC EDGAR for Operating Partnership (OP) by name pattern.

    Many REITs have an OP with name like "{Company Name}, L.P." or
    "{Company Name} Operating Partnership"

    Args:
        company_name: REIT company name

    Returns:
        Tuple of (op_cik, op_name) or None if not found
    """
    # Common OP name patterns
    search_patterns = [
        f"{company_name}, L.P.",
        f"{company_name} L.P.",
        f"{company_name} Operating Partnership",
    ]

    headers = {"User-Agent": SEC_USER_AGENT}

    for pattern in search_patterns:
        try:
            url = SEC_SEARCH_URL.format(query=quote(pattern))
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", {}).get("hits", [])

                if len(hits) == 1:
                    # Exactly one match - likely the OP
                    source = hits[0].get("_source", {})
                    cik = str(source.get("ciks", [""])[0]).zfill(10)
                    name = source.get("entity", "")
                    return (cik, name)

            time.sleep(SEC_RATE_LIMIT_DELAY)

        except Exception as e:
            print(f"  Warning: SEC search failed for '{pattern}': {e}")
            continue

    return None


def update_dynamodb_cik(ticker: str, cik: str, op_cik: Optional[str] = None,
                         op_name: Optional[str] = None, dry_run: bool = True) -> bool:
    """
    Update company CIK in DynamoDB.
    """
    if dry_run:
        return True

    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('reitsheet-companies-config')

        update_expr = "SET cik = :cik"
        expr_values = {":cik": cik}

        if op_cik:
            update_expr += ", op_cik = :op_cik, op_name = :op_name"
            expr_values[":op_cik"] = op_cik
            expr_values[":op_name"] = op_name or ""

        table.update_item(
            Key={'ticker': ticker},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )

        return True

    except Exception as e:
        print(f"  DynamoDB error: {e}")
        return False


def populate_cik_numbers(
    ticker_filter: Optional[str] = None,
    discover_ops: bool = False,
    dry_run: bool = True
) -> Dict[str, any]:
    """
    Main function to populate CIK numbers for all companies.

    Args:
        ticker_filter: Optional single ticker to process
        discover_ops: If True, also search for OP CIKs
        dry_run: If True, don't make any changes

    Returns:
        Summary dict with counts
    """
    # Fetch SEC mapping
    sec_mapping = fetch_sec_ticker_mapping()

    # Get companies from DynamoDB (single source of truth)
    companies = get_companies_from_dynamodb()

    if ticker_filter:
        companies = [c for c in companies if c.get('ticker', '').upper() == ticker_filter.upper()]
        if not companies:
            print(f"No company found with ticker: {ticker_filter}")
            return {}

    # Stats
    stats = {
        "total": len(companies),
        "cik_found": 0,
        "cik_not_found": 0,
        "op_found": 0,
        "updated": 0,
        "errors": 0,
    }

    not_found = []

    print(f"\n{'DRY RUN - ' if dry_run else ''}Processing {len(companies)} companies...\n")

    for company in companies:
        ticker = company.get('ticker', '')
        name = company.get('company_name', '')

        if not ticker:
            continue

        # Look up CIK
        cik = lookup_cik_for_ticker(ticker, sec_mapping)

        if not cik:
            stats["cik_not_found"] += 1
            not_found.append(ticker)
            print(f"  {ticker}: CIK not found in SEC mapping")
            continue

        stats["cik_found"] += 1

        # Optionally discover OP CIK
        op_cik = None
        op_name = None

        if discover_ops:
            print(f"  {ticker}: Searching for OP...")
            op_result = search_sec_for_op(name)
            if op_result:
                op_cik, op_name = op_result
                stats["op_found"] += 1
                print(f"  {ticker}: Found OP - {op_name} (CIK: {op_cik})")
            time.sleep(SEC_RATE_LIMIT_DELAY)

        # Update DynamoDB (single source of truth)
        print(f"  {ticker}: CIK {cik}" + (f", OP CIK {op_cik}" if op_cik else ""))

        dynamo_ok = update_dynamodb_cik(ticker, cik, op_cik, op_name, dry_run)

        if dynamo_ok:
            stats["updated"] += 1
        else:
            stats["errors"] += 1

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total companies:     {stats['total']}")
    print(f"CIK found:           {stats['cik_found']}")
    print(f"CIK not found:       {stats['cik_not_found']}")
    if discover_ops:
        print(f"OP found:            {stats['op_found']}")
    print(f"Updated:             {stats['updated']}")
    print(f"Errors:              {stats['errors']}")

    if not_found:
        print(f"\nTickers not found in SEC mapping: {', '.join(not_found)}")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run with --apply to update databases.")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Populate CIK numbers from SEC EDGAR")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (default is dry run)")
    parser.add_argument("--ticker", type=str,
                        help="Process single ticker only")
    parser.add_argument("--discover-ops", action="store_true",
                        help="Also search for Operating Partnership CIKs")

    args = parser.parse_args()

    populate_cik_numbers(
        ticker_filter=args.ticker,
        discover_ops=args.discover_ops,
        dry_run=not args.apply
    )


if __name__ == "__main__":
    main()
