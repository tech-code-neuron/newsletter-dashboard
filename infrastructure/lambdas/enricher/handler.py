"""
Press Release Pipeline - URL Enricher Lambda (SOLID Refactored)
===================================================
Purpose: Construct and validate press release URLs
Triggered by: SQS Enrichment Queue

SOLID Architecture:
- 91% size reduction (1,042 → 95 lines)
- Single Responsibility: Each module has one clear purpose
- Open/Closed: Easy to extend without modification
- Dependency Injection: All dependencies injected
- Interface Segregation: Small, focused modules

Module Structure:
  url_selection/       - Smart URL selection with scoring
  url_construction/    - URL construction strategies
  persistence/         - Database & queue operations
  config/              - Constants & configuration

Last Updated: 2026-03-12
"""

import json
import logging
import boto3
import os
import sys
from datetime import datetime, timezone

# Add shared directory to path for imports
sys.path.insert(0, '/opt/python')  # Lambda layer path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Module imports (SOLID architecture)
from url_selection.selector import select_best_url_from_email
from url_construction.constructor import construct_url_for_company
from url_construction.validator import validate_url_exists
from persistence.dynamodb_ops import save_to_dynamodb, get_company_config
from persistence.sqs_ops import queue_for_scraping, classify_url, queue_for_manual_review
from title_cleanup import add_display_title_to_metadata
from metadata_builder import MetadataBuilder
# Import circuit breaker from shared (now in shared/ for use by both Parser and Enricher)
try:
    from shared.redirect_circuit_breaker import (
        should_attempt_redirect,
        update_redirect_tracking,
        should_route_to_playwright
    )
except ImportError:
    # Fallback for local testing
    from redirect_circuit_breaker import (
        should_attempt_redirect,
        update_redirect_tracking,
        should_route_to_playwright
    )

# Timezone utilities (ET timezone for circuit breaker)
try:
    from shared.timezone_utils import get_today_et
except ImportError:
    # Fallback for local testing
    from timezone_utils import get_today_et

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================
# Environment variables and DynamoDB tables are accessed lazily to allow
# AST-based smoke tests to import this module without actual AWS credentials.

_initialized = False
_config = {}
_tables = {}
_clients = {}

logger = logging.getLogger()


def _ensure_initialized():
    """
    Lazy initialization of AWS clients, env vars, and DynamoDB tables.
    Called once per Lambda container (cached for container lifetime).
    """
    global _initialized, _config, _tables, _clients

    if _initialized:
        return

    # AWS Clients
    _clients['sqs'] = boto3.client('sqs')
    _clients['dynamodb'] = boto3.resource('dynamodb')

    # Environment Variables (fail-fast if required vars missing)
    _config['SCRAPE_QUEUE_URL'] = os.environ['SCRAPE_QUEUE_URL']
    _config['PLAYWRIGHT_QUEUE_URL'] = os.environ['PLAYWRIGHT_QUEUE_URL']
    _config['ENRICH_DLQ_URL'] = os.environ.get('ENRICH_DLQ_URL')
    _config['REIT_NEWS_TABLE'] = os.environ['REIT_NEWS_TABLE']
    _config['COMPANIES_TABLE'] = os.environ['COMPANIES_TABLE']
    _config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', 'INFO')

    # Logging
    logger.setLevel(getattr(logging, _config['LOG_LEVEL']))

    # DynamoDB Tables
    dynamodb = _clients['dynamodb']
    _tables['reit_news'] = dynamodb.Table(_config['REIT_NEWS_TABLE'])
    _tables['companies'] = dynamodb.Table(_config['COMPANIES_TABLE'])

    _initialized = True


# Accessor functions for clean code
def _sqs():
    return _clients['sqs']


def _reit_news_table():
    return _tables['reit_news']


def _companies_table():
    return _tables['companies']


# ============================================================================
# Generic Subject Detection
# ============================================================================

# Patterns that indicate the email subject is NOT the actual press release title
# These companies use alerting services with generic subjects
GENERIC_SUBJECT_PATTERNS = [
    'alerting service',      # Apollo Commercial Real Estate Finance Alerting Service
    'email notification',
    'press release alert',
    'news alert',
    'investor alert',
    'ir alert',
]


def _is_generic_subject(email_subject: str) -> bool:
    """
    Check if email subject is generic (not the actual press release title).

    Some companies use alerting services that send emails with generic subjects
    like "Apollo Commercial Real Estate Finance Alerting Service" instead of
    the actual press release title.

    When detected, we route to Playwright to extract the real title from the page.

    Args:
        email_subject: The email subject line

    Returns:
        True if subject appears to be generic (needs Playwright for title extraction)
    """
    if not email_subject:
        return False

    subject_lower = email_subject.lower().strip()

    for pattern in GENERIC_SUBJECT_PATTERNS:
        if pattern in subject_lower:
            return True

    return False


# ============================================================================
# Enrichment Workflow Orchestration
# ============================================================================


def process_enrichment_job(job):
    """
    Process one enrichment job

    Workflow:
        1. Get company config
        2. Try URL construction
        3. Validate constructed URL
        4. If valid → Save to DynamoDB
        5. If invalid → Fall back to email URLs
        6. Select best URL from email (smart scoring)
        7. Classify URL → Route to scraper or save

    Args:
        job: Enrichment job dict from Parser

    Returns:
        dict: Result with status and details
    """
    ticker = job.get('ticker')
    email_subject = job.get('email_subject')
    email_date = job.get('email_date', '')
    press_release_date = job.get('press_release_date')  # NEW: PR date from email body (YYYY-MM-DD)
    idempotency_key = job.get('idempotency_key')
    urls = job.get('urls', [])
    press_release_title = job.get('press_release_title')  # Optional (from email body)

    logger.info(f"📧 Processing enrichment for {ticker}")

    # Step 1: Get company configuration
    company = get_company_config(ticker, _companies_table())

    if not company:
        logger.error(f"Company config not found: {ticker}")
        return {'status': 'failed', 'reason': 'company_not_found', 'company_name': 'Unknown Company'}

    # Step 1.5: Check if company needs Playwright scraping
    construction_method = company.get('url_construction_method')
    company_name = company.get('company_name', f'Unknown ({ticker})')  # Get company name for better error messages

    # Step 1.6: Check for generic email subjects that need Playwright title extraction
    # Some companies use alerting services that have generic subjects like "Alerting Service"
    # In these cases, we need Playwright to extract the actual title from the press release page
    if _is_generic_subject(email_subject):
        logger.info(f"🔍 Generic subject detected for {company_name} ({ticker}): '{email_subject[:50]}...' → routing to Playwright")

        # Select best URL from email for Playwright to navigate directly
        # This avoids Playwright having to scrape landing pages (e.g., Apollo's accordion page)
        selected_url = None
        if urls:
            selected_url = select_best_url_from_email(urls, company, email_subject)
            if selected_url:
                logger.info(f"📎 Passing direct URL to Playwright: {selected_url[:60]}...")

        builder = MetadataBuilder(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            company_name=company_name,
            press_release_date=press_release_date,
            press_release_title=press_release_title
        )
        queue_for_scraping(selected_url, builder.for_playwright(), _sqs(), _config['PLAYWRIGHT_QUEUE_URL'])
        return {'status': 'queued_playwright', 'method': 'generic_subject_detection', 'company_name': company_name}

    if construction_method == 'playwright_scraper':
        logger.info(f"Routing {company_name} ({ticker}) to Playwright scraper")
        builder = MetadataBuilder(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            company_name=company_name,
            press_release_date=press_release_date,
            press_release_title=press_release_title
        )
        queue_for_scraping(None, builder.for_playwright(), _sqs(), _config['PLAYWRIGHT_QUEUE_URL'])
        return {'status': 'queued_playwright', 'method': 'playwright_scraper', 'company_name': company_name}

    # Step 2: Try URL construction
    constructed_url, method = construct_url_for_company(company, email_subject, email_date)

    if constructed_url:
        logger.info(f"Constructed URL using {method}: {constructed_url[:60]}...")

        # Step 3: Check if we can skip validation (company-specific flag)
        # Only skip for companies with standardized URL patterns (e.g., SUI with gcs_9_word_slug)
        # Companies like RHP/VNO use GCS but have variable slugs and need validation
        skip_validation = company.get('skip_url_validation', False)

        if skip_validation:
            logger.info(f"Skipping validation for {ticker} (standardized URL pattern)")
            is_valid, final_url, status_code = True, constructed_url, 200
        else:
            # Circuit Breaker: Check if we should attempt redirect (using ET timezone)
            today_iso = get_today_et()  # ET timezone (not UTC)
            should_attempt, use_playwright, reason = should_attempt_redirect(company, today_iso)

            if use_playwright:
                # Circuit breaker active OR already failed today → Route to Playwright
                # Playwright will use press_release_url as fallback if no specific config
                builder = MetadataBuilder(
                    ticker=ticker,
                    email_subject=email_subject,
                    email_date=email_date,
                    idempotency_key=idempotency_key,
                    company_name=company_name,
                    press_release_date=press_release_date,
                    press_release_title=press_release_title
                )

                logger.info(f"⏭️  Routing {ticker} to Playwright: {reason}")
                queue_for_scraping(constructed_url, builder.for_playwright(), _sqs(), _config['PLAYWRIGHT_QUEUE_URL'])
                return {'status': 'queued_playwright', 'method': 'circuit_breaker_fallback', 'company_name': company_name}

            # Validate constructed URL (includes redirect following for tracking URLs)
            logger.info(f"Validating constructed URL for {ticker}")
            is_valid, final_url, status_code = validate_url_exists(constructed_url)

            # Update circuit breaker tracking
            redirect_success = is_valid
            update_redirect_tracking(ticker, redirect_success, _companies_table(), today_iso)

            # If redirect failed → Check if we can still save (timeout with valid URL)
            if not is_valid:
                logger.warning(f"❌ Redirect failed ({status_code})")

                # TIMEOUT FIX: If status_code=0 (timeout) but we captured a final URL,
                # and it's on the company's domain, save it anyway. Timeout != 404.
                if status_code == 0 and final_url:
                    # Check if final URL is on company's IR domain (not a tracking URL)
                    company_domain = company.get('ir_domain', '').lower()
                    press_release_url = company.get('press_release_url', '').lower()
                    final_url_lower = final_url.lower()

                    is_company_url = (
                        (company_domain and company_domain in final_url_lower) or
                        (press_release_url and any(d in final_url_lower for d in press_release_url.split('/')[2:3]))
                    )

                    if is_company_url or 'gcs-web.com' in final_url_lower:
                        logger.info(f"✓ Timeout but captured valid company URL, saving anyway: {final_url[:60]}...")
                        builder = MetadataBuilder(
                            ticker=ticker,
                            email_subject=email_subject,
                            email_date=email_date,
                            idempotency_key=idempotency_key,
                            press_release_date=press_release_date,
                            construction_method=method + '_timeout_recovered'
                        )
                        save_to_dynamodb(final_url, builder.for_dynamodb(), _reit_news_table())
                        return {'status': 'saved', 'url': final_url, 'method': 'constructed_timeout_recovered'}

                # Route to Playwright - try email URL fallback first before using broken constructed URL
                fallback_url = None
                if urls:
                    fallback_url = select_best_url_from_email(urls, company, email_subject)
                    if fallback_url:
                        logger.info(f"⏭️  Using email URL fallback for {ticker}: {fallback_url[:60]}...")

                builder = MetadataBuilder(
                    ticker=ticker,
                    email_subject=email_subject,
                    email_date=email_date,
                    idempotency_key=idempotency_key,
                    company_name=company_name,
                    press_release_date=press_release_date,
                    press_release_title=press_release_title
                )

                playwright_url = fallback_url or constructed_url
                logger.info(f"⏭️  Routing {ticker} to Playwright (redirect failure fallback)")
                queue_for_scraping(playwright_url, builder.for_playwright(), _sqs(), _config['PLAYWRIGHT_QUEUE_URL'])
                return {'status': 'queued_playwright', 'method': 'redirect_failure_fallback', 'company_name': company_name}

        if is_valid:
            # Step 4a: Save to DynamoDB (no scraping needed)
            builder = MetadataBuilder(
                ticker=ticker,
                email_subject=email_subject,
                email_date=email_date,
                idempotency_key=idempotency_key,
                press_release_date=press_release_date,
                construction_method=method
            )
            save_to_dynamodb(final_url, builder.for_dynamodb(), _reit_news_table())
            return {'status': 'saved', 'url': final_url, 'method': 'constructed'}
        else:
            logger.warning(f"Constructed URL invalid ({status_code}), falling back to email URLs")

    # Step 4b: Use URLs from email body
    if not urls:
        logger.warning(f"No URLs found for {ticker}")
        return {'status': 'failed', 'reason': 'no_url'}

    # Step 5: Smart URL selection (landing page detection + subject scoring)
    selected_url = select_best_url_from_email(urls, company, email_subject)

    if not selected_url:
        logger.warning(f"No valid URL selected for {ticker}")
        return {'status': 'failed', 'reason': 'no_valid_url'}

    # Step 5.5: Check if we should skip validation (direct_url method = bot protection)
    if construction_method == 'direct_url':
        logger.info(f"Skipping validation for {ticker} (direct_url method - bot protection)")
        # URLs from trusted company emails, skip validation entirely
        url_type = classify_url(selected_url)
        builder = MetadataBuilder(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            press_release_date=press_release_date
        )

        if url_type == 'newswire':
            queue_for_scraping(selected_url, builder.for_scraper(), _sqs(), _config['SCRAPE_QUEUE_URL'])
            return {'status': 'queued_scraping', 'url': selected_url, 'method': 'email_newswire_direct'}
        else:
            saved = save_to_dynamodb(selected_url, builder.for_dynamodb(), _reit_news_table())
            if saved:
                return {'status': 'saved', 'url': selected_url, 'method': 'email_direct_url'}
            else:
                # Landing page rejected - use company's press_release_url as fallback
                fallback_url = company.get('press_release_url')
                if fallback_url:
                    logger.info(f"📋 Using landing page fallback for {ticker}: {fallback_url[:60]}...")
                    saved = save_to_dynamodb(fallback_url, builder.for_dynamodb(), _reit_news_table(), allow_landing_page=True)
                    if saved:
                        return {'status': 'saved', 'url': fallback_url, 'method': 'landing_page_fallback'}

                # No fallback available
                logger.warning(f"❌ No fallback URL for {ticker}")
                return {'status': 'failed', 'reason': 'no_fallback_url'}

    # Step 5.6: Circuit Breaker + Follow redirects for tracking URLs
    # This handles SendGrid, GCS-Web, and any other tracking service automatically
    today_iso = get_today_et()  # ET timezone (not UTC)
    should_attempt, use_playwright, reason = should_attempt_redirect(company, today_iso)

    if use_playwright:
        # Circuit breaker active OR already failed today → Route to Playwright
        # Playwright will use press_release_url as fallback if no specific config
        builder = MetadataBuilder(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            company_name=company_name,
            press_release_date=press_release_date,
            press_release_title=press_release_title
        )

        logger.info(f"⏭️  Routing {ticker} to Playwright: {reason}")
        queue_for_scraping(selected_url, builder.for_playwright(), _sqs(), _config['PLAYWRIGHT_QUEUE_URL'])
        return {'status': 'queued_playwright', 'method': 'circuit_breaker_fallback', 'company_name': company_name}

    # Step 5.7: Attempt redirect validation
    logger.info(f"Validating selected URL from email: {selected_url[:60]}...")
    is_valid, final_url, status_code = validate_url_exists(selected_url)

    # IMPROVEMENT: Use final URL even if validation timed out, as long as we made redirect progress
    redirect_happened = final_url != selected_url

    if redirect_happened:
        # We successfully followed redirect (even if final destination timed out)
        logger.info(f"✅ Followed redirect: {selected_url[:60]}... → {final_url[:60]}...")
        if status_code == 0:
            logger.info(f"⚠️  Final URL timed out, but using it anyway (works in browsers)")
        selected_url = final_url

        # Update circuit breaker - redirect worked even if destination is slow
        update_redirect_tracking(ticker, True, _companies_table(), today_iso)

    elif is_valid:
        # No redirect, but URL is valid - use it
        logger.info(f"✅ URL validated successfully (no redirect)")
        update_redirect_tracking(ticker, True, _companies_table(), today_iso)

    else:
        # No redirect AND validation failed → Route to Playwright
        # Playwright will use press_release_url as fallback if no specific config
        logger.warning(f"❌ Validation failed ({status_code}), no redirect progress")
        builder = MetadataBuilder(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            company_name=company_name,
            press_release_date=press_release_date,
            press_release_title=press_release_title
        )

        logger.info(f"⏭️  Routing {ticker} to Playwright (validation failure fallback)")
        queue_for_scraping(selected_url, builder.for_playwright(), _sqs(), _config['PLAYWRIGHT_QUEUE_URL'])
        return {'status': 'queued_playwright', 'method': 'redirect_failure_fallback', 'company_name': company_name}

    # Step 6: Classify URL type (now using resolved URL)
    url_type = classify_url(selected_url)

    builder = MetadataBuilder(
        ticker=ticker,
        email_subject=email_subject,
        email_date=email_date,
        idempotency_key=idempotency_key,
        press_release_date=press_release_date
    )

    # Step 7: Route based on URL type
    if url_type == 'newswire':
        queue_for_scraping(selected_url, builder.for_scraper(), _sqs(), _config['SCRAPE_QUEUE_URL'])
        return {'status': 'queued_scraping', 'url': selected_url, 'method': 'email_newswire'}
    else:
        save_to_dynamodb(selected_url, builder.for_dynamodb(), _reit_news_table())
        return {'status': 'saved', 'url': selected_url, 'method': 'email_direct'}


# ============================================================================
# Lambda Handler
# ============================================================================


def lambda_handler(event, context):
    """
    Main Lambda handler - process enrichment jobs from SQS

    Args:
        event: SQS event with enrichment jobs
        context: Lambda context

    Returns:
        dict: Batch processing results
    """
    # Health check - verifies handler imports work (used by deploy_lambda.py)
    # Added 2026-03-24 to catch import errors immediately after deployment
    if event.get('health_check'):
        return {
            'status': 'healthy',
            'handler': 'enricher',
            'modules': ['url_selection', 'url_construction', 'persistence', 'title_cleanup']
        }

    # Lazy initialization (first invocation only)
    _ensure_initialized()

    logger.info(f"📨 Received {len(event['Records'])} enrichment job(s)")

    results = {'saved': 0, 'queued_scraping': 0, 'failed': 0}
    batch_failures = []

    for record in event['Records']:
        try:
            # Validate SQS record structure
            if 'body' not in record:
                raise ValueError(
                    "Invalid SQS record format: missing 'body' field. "
                    "Expected: {\"Records\":[{\"body\":\"...\"}]}"
                )

            # Parse and process job
            job = json.loads(record['body'])

            # Validate required fields
            # Note: 'urls' is optional since Playwright companies don't need URLs from email
            required_fields = ['ticker', 'idempotency_key']
            missing_fields = [f for f in required_fields if f not in job]
            if missing_fields:
                raise ValueError(
                    f"Invalid message body: missing required fields {missing_fields}"
                )

            result = process_enrichment_job(job)
            status = result.get('status', 'failed')
            results[status] = results.get(status, 0) + 1

        except Exception as e:
            logger.error(f"Error processing job: {e}", exc_info=True)
            results['failed'] += 1
            batch_failures.append({'itemIdentifier': record['messageId']})

    logger.info(f"✅ Enrichment complete: {results}")

    return {
        'statusCode': 200,
        'batchItemFailures': batch_failures,
        'body': json.dumps(results)
    }
