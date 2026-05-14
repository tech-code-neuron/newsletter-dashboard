"""
Enricher - Enrichment Processor
================================
Orchestrates enrichment workflow

SOLID Principles:
- Single Responsibility: Only orchestrates enrichment workflow
- Dependency Injection: All dependencies injected from handler

Last Created: 2026-03-11
"""

import logging
from typing import Dict, Any

from .url_construction import construct_url_for_company
from .url_validation import validate_url_exists
from .url_selection import select_best_url_from_email
from .url_classification import classify_url
from .database_ops import save_to_dynamodb
from .queue_ops import queue_for_scraping
from .company_lookup import get_company_config

logger = logging.getLogger()


def process_enrichment_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process one enrichment job

    Single Responsibility: Orchestrates enrichment workflow

    Workflow:
        1. Get company config
        2. Try URL construction
        3. Validate constructed URL
        4. If valid → Save to DynamoDB
        5. If invalid → Fall back to email URLs
        6. Select best URL from email (domain matching)
        7. Classify URL → Route to scraper or save

    Args:
        job: Enrichment job dict from Parser

    Returns:
        dict: Result with status and details
    """
    ticker = job.get('ticker')
    email_subject = job.get('email_subject')
    email_date = job.get('email_date', '')
    idempotency_key = job.get('idempotency_key')
    urls = job.get('urls', [])

    logger.info(f"📧 Processing enrichment for {ticker}")

    # Step 1: Get company configuration
    company = get_company_config(ticker)

    if not company:
        logger.error(f"Company config not found: {ticker}")
        return {'status': 'failed', 'reason': 'company_not_found'}

    # Step 2: Try URL construction
    constructed_url, method = construct_url_for_company(company, email_subject, email_date)

    if constructed_url:
        logger.info(f"Constructed URL using {method}: {constructed_url[:60]}...")

        # Step 3: Validate constructed URL
        is_valid, final_url, status_code = validate_url_exists(constructed_url)

        if is_valid:
            # Step 4a: Save to DynamoDB (no scraping needed)
            metadata = {
                'ticker': ticker,
                'subject': email_subject,
                'idempotency_key': idempotency_key,
                'construction_method': method
            }
            success = save_to_dynamodb(final_url, metadata)
            return {'status': 'saved', 'url': final_url, 'method': 'constructed'}
        else:
            logger.warning(f"Constructed URL invalid ({status_code}), falling back to email URLs")

    # Step 4b: Use URLs from email body
    if not urls:
        logger.warning(f"No URLs found for {ticker}")
        return {'status': 'failed', 'reason': 'no_url'}

    # NEW: Select best URL based on domain matching (not just first URL!)
    selected_url = select_best_url_from_email(urls, company)

    if not selected_url:
        logger.warning(f"No valid URL selected for {ticker}")
        return {'status': 'failed', 'reason': 'no_valid_url'}

    url_type = classify_url(selected_url)

    metadata = {
        'ticker': ticker,
        'subject': email_subject,
        'idempotency_key': idempotency_key
    }

    if url_type == 'newswire':
        # Newswire → Queue for scraping
        success = queue_for_scraping(selected_url, metadata)
        return {'status': 'queued_scraping', 'url': selected_url, 'method': 'email_newswire'}
    else:
        # Direct link → Save to DynamoDB
        success = save_to_dynamodb(selected_url, metadata)
        return {'status': 'saved', 'url': selected_url, 'method': 'email_direct'}
