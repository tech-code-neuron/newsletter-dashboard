"""
Prospectus Fetcher Lambda (repurposed from 8K-Fetcher)

Polls SEC EDGAR for 424 prospectus and FWP filings, queues for processing.

Trigger: EventBridge schedule (3x daily: 7:30 AM, 9:00 AM, 6:00 PM ET weekdays)

Flow:
1. Query reitsheet-companies-config for all companies with CIK
2. For each company (REIT + OP CIKs):
   - Fetch SEC submissions API for 424B2, 424B5, FWP filings
   - Compare against already-processed filings
   - Queue new filings to processor queue
"""
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

import boto3
import requests

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Resources
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

# Table names
COMPANIES_TABLE = os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config')
FILINGS_TABLE = os.environ.get('FILINGS_TABLE', 'reitsheet-8k-disclosures')

# Queue URL
PROCESSOR_QUEUE_URL = os.environ.get('PROCESSOR_QUEUE_URL', '')

# SEC EDGAR Configuration
SEC_USER_AGENT = "REITSheet/1.0 (contact@reitsheet.com)"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_RATE_LIMIT_DELAY = 0.12  # 10 req/sec max, use 0.12s to be safe

# Form types to track
PROSPECTUS_FORMS = {
    # 424B Series (Prospectus Supplements)
    '424B1', '424B2', '424B3', '424B4', '424B5', '424B7', '424B8',
    # Free Writing Prospectus
    'FWP',
    # Registration Statements
    'S-1', 'S-11',
    # Exchange Act Registration
    '10-12B',
}


def get_companies_with_cik() -> List[Dict]:
    """
    Get all companies with CIK from DynamoDB.

    Returns companies with:
    - cik: REIT CIK (required)
    - op_cik: Operating Partnership CIK (optional)
    """
    table = dynamodb.Table(COMPANIES_TABLE)

    companies = []
    response = table.scan()

    for item in response.get('Items', []):
        if item.get('cik'):
            companies.append({
                'ticker': item.get('ticker'),
                'company_name': item.get('company_name', ''),
                'cik': item.get('cik'),
                'op_cik': item.get('op_cik'),
                'op_name': item.get('op_name'),
            })

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        for item in response.get('Items', []):
            if item.get('cik'):
                companies.append({
                    'ticker': item.get('ticker'),
                    'company_name': item.get('company_name', ''),
                    'cik': item.get('cik'),
                    'op_cik': item.get('op_cik'),
                    'op_name': item.get('op_name'),
                })

    logger.info(f"Found {len(companies)} companies with CIK")
    return companies


def get_processed_filing_urls() -> Set[str]:
    """Get set of already-processed filing URLs from DynamoDB."""
    table = dynamodb.Table(FILINGS_TABLE)

    processed = set()

    try:
        response = table.scan(ProjectionExpression='filing_url')

        for item in response.get('Items', []):
            if item.get('filing_url'):
                processed.add(item['filing_url'])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ProjectionExpression='filing_url',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                if item.get('filing_url'):
                    processed.add(item['filing_url'])

        logger.info(f"Found {len(processed)} already-processed filings")

    except Exception as e:
        logger.warning(f"Could not scan filings table: {e}")

    return processed


def fetch_prospectus_filings(cik: str, days_back: int = 7) -> List[Dict]:
    """
    Fetch 424/FWP filings from SEC submissions API.

    Args:
        cik: SEC Central Index Key (10 digits, zero-padded)
        days_back: Only return filings from last N days

    Returns:
        List of filing dicts with: url, form_type, filing_date, accession_number
    """
    # Ensure CIK is 10 digits, zero-padded
    cik_padded = cik.zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=cik_padded)
    headers = {"User-Agent": SEC_USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Get company name from response
        company_name = data.get('name', '')

        # Get recent filings
        filings_data = data.get('filings', {}).get('recent', {})
        forms = filings_data.get('form', [])
        accession_numbers = filings_data.get('accessionNumber', [])
        filing_dates = filings_data.get('filingDate', [])
        primary_documents = filings_data.get('primaryDocument', [])
        acceptance_datetimes = filings_data.get('acceptanceDateTime', [])  # SEC acceptance timestamp

        # Calculate cutoff date
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')

        filings = []
        for i, form in enumerate(forms):
            if form not in PROSPECTUS_FORMS:
                continue

            filing_date = filing_dates[i] if i < len(filing_dates) else ''

            # Skip old filings
            if filing_date and filing_date < cutoff:
                continue

            accession = accession_numbers[i] if i < len(accession_numbers) else ''
            primary_doc = primary_documents[i] if i < len(primary_documents) else ''
            acceptance_dt = acceptance_datetimes[i] if i < len(acceptance_datetimes) else ''

            # Validate acceptance timestamp exists
            if not acceptance_dt:
                logger.warning(f"Missing acceptanceDateTime for {form} {accession} - SEC API propagation delay, processor will fetch from index page")

            # Build filing URL
            # Format: https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}
            accession_no_dashes = accession.replace('-', '')

            # Use primary document URL instead of index page
            if primary_doc:
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik_padded)}/{accession_no_dashes}/{primary_doc}"
            else:
                # Fallback if primaryDocument not provided
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik_padded)}/{accession_no_dashes}/{accession}-index.htm"
                logger.warning(f"No primaryDocument for {form} filing {accession}, using index page")

            # Document URL (for actual prospectus) - now same as filing_url
            doc_url = filing_url

            filings.append({
                'url': filing_url,
                'doc_url': doc_url,
                'form_type': form,
                'filing_date': filing_date,
                'accession_number': accession,
                'issuer_name': company_name,
                'acceptance_datetime': acceptance_dt  # SEC's exact acceptance timestamp
            })

        return filings

    except requests.RequestException as e:
        logger.error(f"Failed to fetch SEC submissions for CIK {cik}: {e}")
        return []
    except (KeyError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse SEC response for CIK {cik}: {e}")
        return []


def queue_filing_for_processing(
    filing: Dict,
    ticker: str,
    cik: str,
    company_name: str,
    issuer_type: str = 'reit'
) -> bool:
    """
    Queue a prospectus filing for processing.

    Args:
        filing: Filing dict from SEC API
        ticker: Company ticker
        cik: CIK that was polled
        company_name: Company name
        issuer_type: 'reit' or 'op'

    Returns:
        True if queued successfully
    """
    if not PROCESSOR_QUEUE_URL:
        logger.error("PROCESSOR_QUEUE_URL not configured")
        return False

    message = {
        'ticker': ticker,
        'issuer_cik': cik,
        'issuer_name': filing.get('issuer_name', company_name),
        'issuer_type': issuer_type,
        'filing_url': filing['url'],
        'doc_url': filing.get('doc_url'),
        'form_type': filing['form_type'],
        'filing_date': filing['filing_date'],
        'accession_number': filing['accession_number'],
        'acceptance_datetime': filing.get('acceptance_datetime', ''),  # SEC acceptance timestamp
        'fetched_at': datetime.now(timezone.utc).isoformat()
    }

    try:
        sqs.send_message(
            QueueUrl=PROCESSOR_QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageGroupId=ticker,  # FIFO queue grouping by ticker
            MessageDeduplicationId=filing['accession_number'] or filing['url']
        )
        logger.info(f"Queued {ticker} {filing['form_type']}: {filing['accession_number']}")
        return True

    except Exception as e:
        logger.error(f"Failed to queue filing {filing['url']}: {e}")
        return False


def process_company(
    company: Dict,
    processed_urls: Set[str],
    days_back: int = 7
) -> Dict:
    """
    Process a single company - fetch prospectus filings and queue new ones.

    Polls BOTH REIT CIK and OP CIK (if exists) since:
    - Equity offerings → Filed under REIT CIK
    - Debt offerings → Filed under REIT or OP CIK (varies)
    """
    ticker = company['ticker']
    stats = {
        'ticker': ticker,
        'reit_filings_found': 0,
        'reit_filings_new': 0,
        'op_filings_found': 0,
        'op_filings_new': 0,
        'queued': 0,
        'errors': 0
    }

    # Fetch REIT prospectus filings
    reit_filings = fetch_prospectus_filings(company['cik'], days_back)
    stats['reit_filings_found'] = len(reit_filings)

    time.sleep(SEC_RATE_LIMIT_DELAY)

    # Process REIT filings
    for filing in reit_filings:
        if filing['url'] in processed_urls:
            continue

        stats['reit_filings_new'] += 1

        if queue_filing_for_processing(
            filing, ticker, company['cik'],
            company['company_name'], 'reit'
        ):
            stats['queued'] += 1
            processed_urls.add(filing['url'])
        else:
            stats['errors'] += 1

    # Fetch OP prospectus filings (always poll if OP CIK exists)
    if company.get('op_cik'):
        op_filings = fetch_prospectus_filings(company['op_cik'], days_back)
        stats['op_filings_found'] = len(op_filings)

        time.sleep(SEC_RATE_LIMIT_DELAY)

        for filing in op_filings:
            if filing['url'] in processed_urls:
                continue

            stats['op_filings_new'] += 1

            if queue_filing_for_processing(
                filing, ticker, company['op_cik'],
                company.get('op_name', company['company_name']), 'op'
            ):
                stats['queued'] += 1
                processed_urls.add(filing['url'])
            else:
                stats['errors'] += 1

    return stats


def handler(event, context):
    """
    Lambda handler - polls SEC EDGAR for prospectus filings.

    Triggered by EventBridge schedule (3x daily).

    Event parameters (optional):
        tickers: List of tickers to process (e.g., ["SPG", "EQR"])
        days_back: Only process filings from last N days (default: 7)
    """
    start_time = datetime.now(timezone.utc)

    # Parse event parameters
    tickers_filter = event.get('tickers', [])
    days_back = event.get('days_back', 7)

    logger.info(f"Prospectus-Fetcher starting at {start_time.isoformat()}")
    if tickers_filter:
        logger.info(f"Filtering to tickers: {tickers_filter}")
    logger.info(f"Processing filings from last {days_back} days")

    # Get companies and already-processed filings
    companies = get_companies_with_cik()
    processed_urls = get_processed_filing_urls()

    # Filter to specific tickers if provided
    if tickers_filter:
        tickers_upper = [t.upper() for t in tickers_filter]
        companies = [c for c in companies if c['ticker'].upper() in tickers_upper]
        logger.info(f"Found {len(companies)} companies matching filter")

    # Stats
    total_stats = {
        'companies_processed': 0,
        'total_filings_found': 0,
        'total_new_filings': 0,
        'total_queued': 0,
        'total_errors': 0
    }

    # Process each company
    for company in companies:
        try:
            stats = process_company(company, processed_urls, days_back)

            total_stats['companies_processed'] += 1
            total_stats['total_filings_found'] += stats['reit_filings_found'] + stats['op_filings_found']
            total_stats['total_new_filings'] += stats['reit_filings_new'] + stats['op_filings_new']
            total_stats['total_queued'] += stats['queued']
            total_stats['total_errors'] += stats['errors']

            if stats['reit_filings_new'] > 0 or stats['op_filings_new'] > 0:
                logger.info(f"{company['ticker']}: {stats['reit_filings_new']} REIT + {stats['op_filings_new']} OP new filings")

        except Exception as e:
            logger.error(f"Error processing {company['ticker']}: {e}")
            total_stats['total_errors'] += 1

    # Summary
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"Prospectus-Fetcher complete in {duration:.1f}s: "
                f"{total_stats['companies_processed']} companies, "
                f"{total_stats['total_new_filings']} new filings, "
                f"{total_stats['total_queued']} queued")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Prospectus-Fetcher complete',
            'duration_seconds': duration,
            **total_stats
        })
    }
