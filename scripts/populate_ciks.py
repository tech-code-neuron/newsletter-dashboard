#!/usr/bin/env python3
"""
Populate CIKs and OP CIKs for all REITs in reitsheet-companies-config.

Uses SEC EDGAR API to:
1. Look up REIT CIKs from company tickers file
2. Search for associated Operating Partnerships (OPs)
3. Update DynamoDB with both CIKs
"""
import json
import time
import re
import boto3
import requests

# SEC API settings
SEC_USER_AGENT = "REITSheet/1.0 (contact@reitsheet.com)"
SEC_RATE_LIMIT = 0.15  # 10 req/sec max, use 0.15s to be safe

# DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('reitsheet-companies-config')


def fetch_sec_tickers() -> dict:
    """Fetch SEC company tickers JSON file."""
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": SEC_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    # Convert to ticker -> CIK mapping
    data = response.json()
    ticker_to_cik = {}
    for item in data.values():
        ticker = item['ticker'].upper()
        cik = str(item['cik_str']).zfill(10)
        ticker_to_cik[ticker] = {
            'cik': cik,
            'title': item['title']
        }
    return ticker_to_cik


def search_for_op(company_name: str, ticker: str) -> dict:
    """
    Search SEC EDGAR for Operating Partnership associated with a REIT.

    Common patterns:
    - "Simon Property Group" -> "Simon Property Group, L.P."
    - "Equity Residential" -> "ERP Operating Limited Partnership"
    - "Prologis" -> "Prologis, L.P."
    """
    headers = {"User-Agent": SEC_USER_AGENT}

    # Try different search patterns
    search_terms = [
        f"{company_name} L.P.",
        f"{company_name} LP",
        f"{company_name} Limited Partnership",
        f"{company_name} Operating",
        f"{ticker} Operating",
    ]

    for term in search_terms:
        # Use SEC full-text search API
        url = f"https://efts.sec.gov/LATEST/search-index?q={requests.utils.quote(term)}&dateRange=custom&startdt=2020-01-01&enddt=2026-12-31&forms=10-K&page=1&from=0"

        try:
            time.sleep(SEC_RATE_LIMIT)
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # Check results for LP/OP filings
                hits = data.get('hits', {}).get('hits', [])
                for hit in hits[:5]:
                    source = hit.get('_source', {})
                    entity = source.get('display_names', [''])[0]
                    cik = source.get('ciks', [''])[0]

                    # Check if this looks like an OP
                    if any(pattern in entity.upper() for pattern in ['L.P.', 'LP', 'LIMITED PARTNERSHIP', 'OPERATING']):
                        if company_name.upper()[:10] in entity.upper() or ticker.upper() in entity.upper():
                            return {
                                'op_cik': str(cik).zfill(10),
                                'op_name': entity
                            }
        except Exception as e:
            print(f"  Search error for '{term}': {e}")
            continue

    return None


def get_op_from_10k(reit_cik: str) -> dict:
    """
    Check REIT's recent 10-K for Operating Partnership info.
    The 10-K often lists both REIT and OP in the header.
    """
    headers = {"User-Agent": SEC_USER_AGENT}

    # Get submissions for REIT
    url = f"https://data.sec.gov/submissions/CIK{reit_cik}.json"

    try:
        time.sleep(SEC_RATE_LIMIT)
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None

        data = response.json()
        filings = data.get('filings', {}).get('recent', {})

        # Find recent 10-K
        forms = filings.get('form', [])
        accessions = filings.get('accessionNumber', [])

        for i, form in enumerate(forms[:20]):
            if form == '10-K':
                accession = accessions[i].replace('-', '')

                # Fetch 10-K index
                index_url = f"https://www.sec.gov/Archives/edgar/data/{int(reit_cik)}/{accession}/index.json"
                time.sleep(SEC_RATE_LIMIT)
                index_resp = requests.get(index_url, headers=headers, timeout=30)

                if index_resp.status_code == 200:
                    index_data = index_resp.json()

                    # Check for multiple filers (REIT + OP file jointly)
                    # This is visible in the directory listing
                    items = index_data.get('directory', {}).get('item', [])

                    # Look for the 10-K HTML to parse header
                    for item in items:
                        if item.get('name', '').endswith('.htm') and '10-k' in item.get('name', '').lower():
                            doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(reit_cik)}/{accession}/{item['name']}"
                            time.sleep(SEC_RATE_LIMIT)
                            doc_resp = requests.get(doc_url, headers=headers, timeout=30)

                            if doc_resp.status_code == 200:
                                # Look for OP references in first 10KB
                                text = doc_resp.text[:10000]

                                # Common patterns in 10-K headers
                                patterns = [
                                    r'([A-Z][A-Za-z\s&,\.]+(?:L\.P\.|LP|Limited Partnership))',
                                    r'(?:Operating Partnership|OP).*?(?:CIK|Commission File).*?(\d{7,10})',
                                ]

                                for pattern in patterns:
                                    matches = re.findall(pattern, text)
                                    for match in matches:
                                        if 'L.P.' in match or 'LP' in match or 'Limited Partnership' in match:
                                            # Found potential OP name
                                            return {'op_name': match.strip(), 'op_cik': None}
                            break
                break
    except Exception as e:
        print(f"  10-K check error: {e}")

    return None


def get_all_reits() -> list:
    """Get all REITs from DynamoDB."""
    response = table.scan(
        ProjectionExpression='ticker,company_name,cik,op_cik,op_name'
    )
    return response.get('Items', [])


def update_company_ciks(ticker: str, updates: dict):
    """Update company with CIK info."""
    if not updates:
        return

    update_expr = 'SET '
    expr_values = {}
    expr_names = {}

    for key, value in updates.items():
        if value:
            safe_key = f"#{key}"
            update_expr += f"{safe_key} = :{key}, "
            expr_values[f":{key}"] = value
            expr_names[safe_key] = key

    if not expr_values:
        return

    update_expr = update_expr.rstrip(', ')

    table.update_item(
        Key={'ticker': ticker},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names
    )
    print(f"  Updated {ticker}: {updates}")


def main():
    print("Fetching SEC company tickers...")
    sec_tickers = fetch_sec_tickers()
    print(f"  Found {len(sec_tickers)} companies in SEC database")

    print("\nFetching REITs from DynamoDB...")
    reits = get_all_reits()
    print(f"  Found {len(reits)} REITs")

    # Stats
    missing_cik = 0
    missing_op_cik = 0
    updated = 0

    for reit in reits:
        ticker = reit['ticker']
        company_name = reit.get('company_name', '')
        current_cik = reit.get('cik')
        current_op_cik = reit.get('op_cik')

        updates = {}

        # Check REIT CIK
        if not current_cik:
            if ticker in sec_tickers:
                updates['cik'] = sec_tickers[ticker]['cik']
                print(f"\n{ticker}: Found REIT CIK {updates['cik']}")
            else:
                print(f"\n{ticker}: WARNING - Not found in SEC database")
                missing_cik += 1

        # Check OP CIK
        if not current_op_cik:
            reit_cik = updates.get('cik') or current_cik
            if reit_cik:
                print(f"\n{ticker}: Searching for Operating Partnership...")

                # Try searching by company name
                op_info = search_for_op(company_name, ticker)

                if not op_info:
                    # Try checking 10-K
                    op_info = get_op_from_10k(reit_cik)

                if op_info:
                    if op_info.get('op_cik'):
                        updates['op_cik'] = op_info['op_cik']
                    if op_info.get('op_name'):
                        updates['op_name'] = op_info['op_name']
                    print(f"  Found OP: {op_info}")
                else:
                    print(f"  No OP found (may not have one)")
            else:
                missing_op_cik += 1

        # Update if we have changes
        if updates:
            update_company_ciks(ticker, updates)
            updated += 1

        # Rate limiting
        time.sleep(SEC_RATE_LIMIT)

    print(f"\n\nSummary:")
    print(f"  Total REITs: {len(reits)}")
    print(f"  Missing REIT CIK: {missing_cik}")
    print(f"  Updated: {updated}")


if __name__ == '__main__':
    main()
