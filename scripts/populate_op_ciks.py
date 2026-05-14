#!/usr/bin/env python3
"""
Populate Operating Partnership CIKs using multiple reliable strategies.

Strategies (in order of reliability):
1. Sequential CIK check (CIK+1, CIK-1) - most REITs/OPs registered together
2. Name search in SEC company_tickers.json bulk file
3. 10-K co-filer parsing (fallback)

Usage:
    python scripts/populate_op_ciks.py --dry-run     # Preview changes
    python scripts/populate_op_ciks.py               # Apply changes
    python scripts/populate_op_ciks.py --ticker SPG  # Single company
    python scripts/populate_op_ciks.py --force       # Update even if op_cik exists
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher

import boto3
import requests

# SEC API settings
SEC_USER_AGENT = "PressReleasePipeline/1.0 (contact@your-domain.comm)"
SEC_RATE_LIMIT = 0.15  # 150ms between requests (10 req/sec max)
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

# Cache for SEC API responses
_company_name_cache = {}
_tickers_data = None


def fetch_company_name(cik: str) -> str:
    """Fetch company name from SEC submissions API with caching."""
    cik = cik.zfill(10)

    if cik in _company_name_cache:
        return _company_name_cache[cik]

    try:
        time.sleep(SEC_RATE_LIMIT)
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        resp = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            name = data.get('name', '')
            _company_name_cache[cik] = name
            return name
        else:
            _company_name_cache[cik] = None
            return None
    except Exception:
        _company_name_cache[cik] = None
        return None


def fetch_tickers_data() -> dict:
    """Fetch and cache SEC company_tickers.json."""
    global _tickers_data

    if _tickers_data is not None:
        return _tickers_data

    try:
        print("Fetching SEC company_tickers.json...")
        resp = requests.get(SEC_TICKERS_URL, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
        resp.raise_for_status()
        _tickers_data = resp.json()

        # Build name -> CIK lookup for L.P. entities
        lp_entities = {}
        for item in _tickers_data.values():
            name = item.get('title', '').upper()
            if 'L.P.' in name or ', LP' in name or 'LIMITED PARTNERSHIP' in name:
                cik = str(item.get('cik_str', '')).zfill(10)
                lp_entities[name] = cik

        _tickers_data['_lp_entities'] = lp_entities
        print(f"  Found {len(lp_entities)} L.P. entities in SEC database")
        return _tickers_data
    except Exception as e:
        print(f"  Warning: Could not fetch tickers file: {e}")
        _tickers_data = {'_lp_entities': {}}
        return _tickers_data


def normalize_name(name: str) -> str:
    """Normalize company name for comparison."""
    name = name.upper()
    # Remove common suffixes
    for suffix in [', INC.', ', INC', ' INC.', ' INC', ', LLC', ' LLC',
                   ', CORP.', ', CORP', ' CORP.', ' CORP', '/MD', '/DE']:
        name = name.replace(suffix, '')
    # Remove extra whitespace
    name = ' '.join(name.split())
    return name


def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity ratio between two names."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    return SequenceMatcher(None, n1, n2).ratio()


def is_likely_op(candidate_name: str, reit_name: str, is_cofiler: bool = False) -> bool:
    """Check if candidate looks like the REIT's Operating Partnership.

    Args:
        candidate_name: Name to check
        reit_name: REIT company name
        is_cofiler: If True, this candidate was found as a co-filer on the same
                   document, so we can be less strict about name matching
    """
    if not candidate_name:
        return False

    name_upper = candidate_name.upper()

    # Must be an L.P. entity or have "OPERATING" in name
    lp_indicators = ['L.P.', 'L P', ', LP', ' LP,', ' LP ', 'LIMITED PARTNERSHIP', 'LTD PARTNERSHIP']
    has_lp = any(ind in name_upper for ind in lp_indicators)
    has_operating = 'OPERATING' in name_upper

    if not (has_lp or has_operating):
        return False

    # For co-filers, just having L.P. + OPERATING is strong enough evidence
    if is_cofiler and has_lp and has_operating:
        return True

    # Extract significant words from REIT name (skip common words)
    skip_words = {'THE', 'INC', 'CORP', 'LLC', 'REIT', 'TRUST', 'GROUP', 'COMPANY', 'CO'}
    reit_words = [w for w in normalize_name(reit_name).split()
                  if len(w) > 2 and w not in skip_words]

    # Check if significant REIT words appear in OP name
    matches = sum(1 for word in reit_words[:3] if word in name_upper)

    # Also check acronyms (e.g., EQR -> ERP, SPG -> SPG)
    # Only match if acronym appears as a word or at word boundary
    if len(reit_words) >= 2:
        acronym = ''.join(w[0] for w in reit_words[:3] if w)
        if len(acronym) >= 3:  # Require at least 3 chars for acronym match
            # Check for word boundary match (not just substring)
            candidate_words = name_upper.split()
            for word in candidate_words:
                if word.startswith(acronym) or word == acronym:
                    matches += 1
                    break

    return matches >= 1 and len(reit_words) > 0


def check_sequential_cik(reit_cik: str, reit_name: str) -> tuple:
    """
    Strategy 1: Check sequential CIKs for matching OP.

    Many REITs and their OPs were registered at the same time,
    resulting in sequential CIK numbers.
    """
    reit_cik_int = int(reit_cik)

    # Check offsets +1, -1, +2, -2
    for offset in [1, -1, 2, -2]:
        candidate_cik = str(reit_cik_int + offset).zfill(10)
        candidate_name = fetch_company_name(candidate_cik)

        if candidate_name and is_likely_op(candidate_name, reit_name):
            return candidate_cik, candidate_name, 'sequential'

    return None, None, None


def search_tickers_file(reit_name: str, reit_cik: str) -> tuple:
    """
    Strategy 2: Search SEC company_tickers.json for matching L.P. entity.
    """
    tickers = fetch_tickers_data()
    lp_entities = tickers.get('_lp_entities', {})

    if not lp_entities:
        return None, None, None

    # Try exact patterns first
    patterns = [
        f"{normalize_name(reit_name)}, L.P.",
        f"{normalize_name(reit_name)} L.P.",
        f"{normalize_name(reit_name)} OPERATING LIMITED PARTNERSHIP",
        f"{normalize_name(reit_name)} OPERATING L.P.",
    ]

    for pattern in patterns:
        if pattern in lp_entities:
            cik = lp_entities[pattern]
            if cik != reit_cik:  # Don't return the REIT itself
                return cik, pattern, 'tickers_exact'

    # Try fuzzy matching
    reit_norm = normalize_name(reit_name)
    best_match = None
    best_score = 0.6  # Minimum threshold

    for lp_name, cik in lp_entities.items():
        if cik == reit_cik:
            continue

        # Check if REIT name words appear in LP name
        if is_likely_op(lp_name, reit_name):
            score = name_similarity(reit_norm, lp_name.replace('L.P.', '').replace(', LP', ''))
            if score > best_score:
                best_score = score
                best_match = (cik, lp_name)

    if best_match:
        return best_match[0], best_match[1], 'tickers_fuzzy'

    return None, None, None


def search_10k_cofilers(reit_name: str, reit_cik: str) -> tuple:
    """
    Strategy 3: Search SEC 10-K filings for co-filers.

    Joint 10-K filings list both REIT and OP in display_names.
    This is the most reliable method but requires SEC search API.
    """
    try:
        time.sleep(SEC_RATE_LIMIT)

        # Search for 10-K filings mentioning the company
        params = {
            'q': f'"{reit_name}"',
            'forms': '10-K',
            'dateRange': 'custom',
            'startdt': '2020-01-01',
            'enddt': '2030-12-31',
        }
        resp = requests.get(
            SEC_SEARCH_URL,
            params=params,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=30
        )

        if resp.status_code != 200:
            return None, None, None

        data = resp.json()
        hits = data.get('hits', {}).get('hits', [])

        # Look through first few 10-K results for co-filers
        for hit in hits[:5]:
            source = hit.get('_source', {})
            display_names = source.get('display_names', [])
            ciks = source.get('ciks', [])

            # Find L.P. entity in co-filers
            for i, name in enumerate(display_names):
                # Extract CIK from display name format: "Company Name (CIK 0001234567)"
                cik_match = re.search(r'CIK\s*(\d+)', name)
                if not cik_match:
                    continue

                cofiler_cik = cik_match.group(1).zfill(10)

                # Skip if this is the REIT itself
                if cofiler_cik == reit_cik:
                    continue

                # Check if this is an L.P. entity (co-filer mode = less strict)
                if is_likely_op(name, reit_name, is_cofiler=True):
                    # Clean up name (remove CIK suffix)
                    op_name = re.sub(r'\s*\([^)]*CIK[^)]*\)\s*$', '', name).strip()
                    op_name = re.sub(r'\s*\([A-Z0-9-]+\)\s*$', '', op_name).strip()
                    return cofiler_cik, op_name, '10k_cofiler'

    except Exception as e:
        # Silently fail - this is a fallback strategy
        pass

    return None, None, None


def get_companies_with_cik(table, ticker: str = None) -> list:
    """Get companies with CIK from DynamoDB."""
    if ticker:
        response = table.get_item(Key={'ticker': ticker.upper()})
        item = response.get('Item')
        if item and item.get('cik'):
            return [item]
        print(f"Company not found or no CIK: {ticker}")
        return []

    # Scan for all companies with CIK
    from boto3.dynamodb.conditions import Attr

    items = []
    response = table.scan(
        FilterExpression=Attr('cik').exists(),
        ProjectionExpression='ticker,company_name,cik,op_cik,op_name'
    )
    items.extend(response.get('Items', []))

    while 'LastEvaluatedKey' in response:
        response = table.scan(
            FilterExpression=Attr('cik').exists(),
            ProjectionExpression='ticker,company_name,cik,op_cik,op_name',
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))

    return items


def update_company(table, ticker: str, op_cik: str, op_name: str, dry_run: bool = False) -> bool:
    """Update company with OP CIK in DynamoDB."""
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
        description='Populate Operating Partnership CIKs using multiple strategies'
    )
    parser.add_argument('--ticker', help='Process specific ticker only')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--force', action='store_true', help='Update even if op_cik already set')
    args = parser.parse_args()

    # Connect to DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('reitsheet-companies-config')

    # Get companies
    companies = get_companies_with_cik(table, args.ticker)
    if not companies:
        print("No companies to process")
        return

    print(f"\nProcessing {len(companies)} companies with CIKs...")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]\n")

    # Pre-fetch tickers data
    fetch_tickers_data()
    print()

    # Stats
    stats = {
        'processed': 0,
        'skipped': 0,
        'found_sequential': 0,
        'found_tickers': 0,
        'found_10k': 0,
        'not_found': 0,
        'updated': 0,
        'errors': 0
    }

    for company in sorted(companies, key=lambda x: x.get('ticker', '')):
        ticker = company.get('ticker', '')
        name = company.get('company_name', ticker)
        reit_cik = company.get('cik', '')
        existing_op_cik = company.get('op_cik')

        stats['processed'] += 1
        print(f"{ticker} ({name}):")
        print(f"  REIT CIK: {reit_cik}")

        # Skip if already has OP CIK (unless --force)
        if existing_op_cik and not args.force:
            print(f"  Already has OP CIK: {existing_op_cik} (use --force to update)")
            stats['skipped'] += 1
            continue

        # Strategy 1: Sequential CIK check
        op_cik, op_name, strategy = check_sequential_cik(reit_cik, name)

        # Strategy 2: Tickers file search (if strategy 1 failed)
        if not op_cik:
            op_cik, op_name, strategy = search_tickers_file(name, reit_cik)

        # Strategy 3: 10-K co-filer search (if strategies 1-2 failed)
        if not op_cik:
            op_cik, op_name, strategy = search_10k_cofilers(name, reit_cik)

        # Report results
        if op_cik:
            print(f"  Found OP [{strategy}]: {op_name}")
            print(f"  OP CIK: {op_cik}")

            if strategy == 'sequential':
                stats['found_sequential'] += 1
            elif strategy == '10k_cofiler':
                stats['found_10k'] += 1
            else:
                stats['found_tickers'] += 1

            if update_company(table, ticker, op_cik, op_name, args.dry_run):
                stats['updated'] += 1
            else:
                stats['errors'] += 1
        else:
            print("  No OP found (may not be UPREIT structure)")
            stats['not_found'] += 1

    # Summary
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Companies processed: {stats['processed']}")
    print(f"  Skipped (already set): {stats['skipped']}")
    print(f"  OPs found via sequential CIK: {stats['found_sequential']}")
    print(f"  OPs found via tickers search: {stats['found_tickers']}")
    print(f"  OPs found via 10-K co-filers: {stats['found_10k']}")
    print(f"  No OP found: {stats['not_found']}")
    print(f"  Records updated: {stats['updated']}")
    if stats['errors']:
        print(f"  Errors: {stats['errors']}")

    if args.dry_run:
        print("\n[DRY RUN - No changes were made]")


if __name__ == '__main__':
    main()
