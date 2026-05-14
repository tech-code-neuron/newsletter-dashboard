"""
Parser Lambda - Routing
========================
Route press releases to appropriate destination

SOLID Principles:
- Single Responsibility: Each function does ONE thing
- Strategy Pattern: Routing logic data-driven
- No Hardcoded Values: All constants imported
- DRY: Unified queue message builders

SOLID Refactoring (2026-03-19):
- Extracted RealtIncomeTitleExtractor (eliminates 3x duplication)
- Created unified QueueMessageBuilder (DRY queue messages)
- Split route_press_release() into strategy functions
- Added RoutingConfig dataclass (9 params → 1 config object)

Last Updated: 2026-03-19 (SOLID refactoring)
"""

import json
import logging
import uuid
import re
import sys
import os
import boto3
from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime, timezone

# Add shared directory to path for imports
sys.path.insert(0, '/opt/python')  # Lambda layer path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from constants import JAVASCRIPT_RENDERED_COMPANIES  # DEPRECATED: Use company_config instead
from company_config import should_use_playwright  # NEW: Single Source of Truth
from url_utils import classify_url, validate_url_exists, extract_domain_from_url, is_press_release_url
from url_construction import construct_url_for_company
from title_extractors import RealtyIncomeTitleExtractor, AlertingServiceTitleExtractor

# Timezone utilities (ET timezone for circuit breaker)
try:
    from shared.timezone_utils import get_today_et
    from shared.timestamp_utils import get_current_timestamp_utc, extract_timestamp_from_email_date
except ImportError:
    # Fallback for local testing
    from timezone_utils import get_today_et
    from timestamp_utils import get_current_timestamp_utc, extract_timestamp_from_email_date

# Social media pipeline imports
try:
    from shared.sector_utils import get_sector_for_ticker
    from shared.slug_utils import generate_release_slug
    from shared.social_constants import SOCIAL_STATUS_PENDING, SOCIAL_STATUS_BODY_NEEDED
except ImportError:
    from sector_utils import get_sector_for_ticker
    from slug_utils import generate_release_slug
    from social_constants import SOCIAL_STATUS_PENDING, SOCIAL_STATUS_BODY_NEEDED

# Title case conversion (for RSS fast path)
try:
    from shared.title_case import smart_title_case, is_all_caps
except ImportError:
    from title_case import smart_title_case, is_all_caps

logger = logging.getLogger()

# AWS clients for direct DynamoDB access (RSS fast path)
dynamodb = boto3.resource('dynamodb')


# ============================================================================
# Configuration Dataclass (SOLID: Replace 9 parameters with config object)
# ============================================================================


@dataclass
class RoutingConfig:
    """
    Configuration for routing operations.

    SOLID: Single config object instead of 9 parameters.
    Makes function signatures cleaner and easier to test.
    """
    reit_news_table: any  # DynamoDB table resource
    sqs_client: any
    scrape_queue_url: str
    playwright_queue_url: str
    enrich_queue_url: str
    companies_table: any  # DynamoDB table resource


# ============================================================================
# Queue Message Builder (SOLID: DRY - Unified message construction)
# ============================================================================


class QueueMessageBuilder:
    """
    Build SQS queue messages for different destinations.

    SOLID: Single Responsibility - Only builds queue messages.
    DRY: Consolidates common message fields in one place.
    """

    @staticmethod
    def _build_base_message(
        ticker: str,
        email_subject: str,
        email_date: str,
        idempotency_key: str
    ) -> dict:
        """Build common message fields shared by all queues."""
        return {
            'ticker': ticker,
            'email_subject': email_subject,
            'email_date': email_date,
            'idempotency_key': idempotency_key,
            'queued_at': datetime.now(timezone.utc).isoformat()
        }

    @classmethod
    def build_playwright_message(
        cls,
        ticker: str,
        email_subject: str,
        email_date: str,
        idempotency_key: str,
        press_release_title: Optional[str] = None,
        press_release_date: Optional[str] = None
    ) -> dict:
        """
        Build message for Playwright scraper queue.

        Args:
            ticker: Company ticker symbol
            email_subject: Email subject line
            email_date: Email date
            idempotency_key: Unique key
            press_release_title: Optional title from email body
            press_release_date: Optional date (YYYY-MM-DD)

        Returns:
            dict: SQS message body
        """
        message = cls._build_base_message(ticker, email_subject, email_date, idempotency_key)

        if press_release_date:
            message['press_release_date'] = press_release_date
            logger.info(f"📅 Added press release date to Playwright queue: {press_release_date}")

        if press_release_title:
            message['press_release_title'] = press_release_title
            logger.info(f"📝 Added press release title to Playwright queue: {press_release_title[:60]}...")

        return message

    @classmethod
    def build_enricher_message(
        cls,
        ticker: str,
        email_subject: str,
        email_date: str,
        idempotency_key: str,
        urls: List[str],
        press_release_title: Optional[str] = None,
        press_release_date: Optional[str] = None
    ) -> dict:
        """
        Build message for enricher queue.

        Args:
            ticker: Company ticker symbol
            email_subject: Email subject line
            email_date: Email date
            idempotency_key: Unique key
            urls: List of URLs from email
            press_release_title: Optional title
            press_release_date: Optional date (YYYY-MM-DD)

        Returns:
            dict: SQS message body
        """
        message = cls._build_base_message(ticker, email_subject, email_date, idempotency_key)
        message['urls'] = urls

        if press_release_date:
            message['press_release_date'] = press_release_date

        if press_release_title:
            message['press_release_title'] = press_release_title

        return message

# ============================================================================
# Direct Link Saving (URL found, no scraping needed)
# ============================================================================


def save_direct_link(url, metadata, reit_news_table):
    """
    Save press release directly to DynamoDB

    Single Responsibility: Only saves to database

    Args:
        url: Press release URL
        metadata: Press release metadata (ticker, subject, etc.)
        reit_news_table: DynamoDB table resource

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ticker = metadata.get('ticker', 'UNKNOWN')
        title = metadata.get('subject', '')
        item = {
            'id': metadata['idempotency_key'],
            'ticker': ticker,
            'title': title,
            'url': url,
            'first_seen_at': get_current_timestamp_utc(),  # ISO 8601 with timezone (for GSI)
            'source': 'email_direct',
            'needs_scraping': False,  # URL found, no scraping needed
            # Social media pipeline fields
            'sector': get_sector_for_ticker(ticker),
            'release_slug': generate_release_slug(title),
            'social_status': SOCIAL_STATUS_BODY_NEEDED,  # No body access at parse time
            **metadata  # Include all metadata
        }

        # Add email_received_at (actual email time - used for display)
        email_received_at = extract_timestamp_from_email_date(metadata.get('date'))
        if email_received_at:
            item['email_received_at'] = email_received_at

        reit_news_table.put_item(Item=item)

        logger.info(f"✓ Saved direct link: {ticker} - {url[:60]}...")
        return True

    except Exception as e:
        logger.error(f"Error saving direct link: {e}")
        return False


# ============================================================================
# Scraping Queue (Newswire URLs that need scraping)
# ============================================================================


def queue_for_scraping(url, metadata, sqs_client, scrape_queue_url):
    """
    Queue URL for web scraping (newswire redirects)

    Single Responsibility: Only queues for scraping

    Args:
        url: URL to scrape
        metadata: Scraping metadata
        sqs_client: SQS client
        scrape_queue_url: SQS queue URL

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        message = {
            'url': url,
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'email_subject': metadata.get('subject', ''),
            'idempotency_key': metadata['idempotency_key'],
            'queued_at': datetime.now(timezone.utc).isoformat()
        }

        response = sqs_client.send_message(
            QueueUrl=scrape_queue_url,
            MessageBody=json.dumps(message)
        )

        logger.info(f"✓ Queued for scraping: {url[:60]}... (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for scraping: {e}")
        return False


# ============================================================================
# Playwright Queue (JavaScript-rendered companies)
# ============================================================================


def queue_for_playwright_scraping(ticker, email_subject, email_date, idempotency_key, sqs_client, playwright_queue_url, press_release_title=None, press_release_date=None):
    """
    Queue job for Playwright scraper (JavaScript-rendered pages)

    Single Responsibility: Only queues for Playwright
    DRY: Uses QueueMessageBuilder for message construction

    Args:
        ticker: Company ticker symbol
        email_subject: Email subject line
        email_date: Email date (for date fallback chain)
        idempotency_key: Unique key
        sqs_client: SQS client
        playwright_queue_url: Playwright queue URL
        press_release_title: Optional press release title extracted from email body (for Realty Income)
        press_release_date: Optional press release date (YYYY-MM-DD) extracted from email body

    Returns:
        bool: True if successful, False otherwise
    """
    if not playwright_queue_url:
        logger.warning("Playwright queue URL not configured")
        return False

    try:
        message = QueueMessageBuilder.build_playwright_message(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            press_release_title=press_release_title,
            press_release_date=press_release_date
        )

        response = sqs_client.send_message(
            QueueUrl=playwright_queue_url,
            MessageBody=json.dumps(message)
        )

        logger.info(f"🎬 Queued for Playwright scraping: {ticker} - {email_subject[:40]}... (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for Playwright: {e}")
        return False


# ============================================================================
# URL Validation with Auto-Correction
# ============================================================================


def validate_and_correct_url(url, company, companies_table, email_subject, email_date):
    """
    Validate constructed URL and auto-correct if wrong

    Single Responsibility: Orchestrates validation + correction

    If URL is 404, tries fallback to redirect_follow method

    Args:
        url: Constructed URL to validate
        company: Company dictionary
        companies_table: DynamoDB table resource
        email_subject: Email subject (for re-construction)
        email_date: Email date

    Returns:
        tuple: (final_url, is_valid, method_used)
    """
    ticker = company.get('ticker', 'UNKNOWN')

    # Validate URL
    is_valid, final_url, status_code = validate_url_exists(url)

    if is_valid:
        logger.info(f"✓ URL validated (200): {url[:60]}...")
        return final_url, True, company.get('url_construction_method')

    # URL failed - try redirect_follow fallback
    logger.warning(f"⚠️  URL validation failed ({status_code}): {url[:60]}...")
    logger.info(f"Switching to redirect_follow method for {ticker}")

    # Update company record to use redirect_follow
    try:
        companies_table.update_item(
            Key={'ticker': ticker},
            UpdateExpression='SET url_construction_method = :method',
            ExpressionAttributeValues={':method': 'redirect_follow'}
        )
        logger.info(f"Updated {ticker} to use redirect_follow method")
    except Exception as e:
        logger.warning(f"Failed to update company method: {e}")

    return None, False, 'redirect_follow'


# ============================================================================
# URL Enhancement with Company Domain Matching
# ============================================================================


def enhance_urls_with_company_domains(urls, company):
    """
    Enhance URL list by checking against company IR domains

    Single Responsibility: Re-evaluates filtered URLs against company domains

    If a URL was filtered but matches the company's IR domain, it's likely
    a legitimate notification/redirect URL, so re-allow it.

    This fixes the "missing PR" issue where notification URLs like
    "notification.gcs-web.com/..." or "investor.terreno.com/email-alert/..."
    were filtered but actually redirect to the press release.

    Args:
        urls: List of URLs extracted from email
        company: Company record with ir_domain, press_release_url

    Returns:
        list: Enhanced list of valid URLs (prioritized by company domain match)
    """
    if not company:
        logger.info("No company record - skipping domain enhancement")
        return [url for url in urls if is_press_release_url(url)]

    # Extract company domains from company record
    # NOTE: ir_domain field doesn't exist in schema, so we extract from URLs
    company_domains = set()

    if company.get('press_release_url'):
        domain = extract_domain_from_url(company['press_release_url'])
        if domain:
            company_domains.add(domain.lower())

    if company.get('ir_url'):
        domain = extract_domain_from_url(company['ir_url'])
        if domain:
            company_domains.add(domain.lower())

    logger.info(f"Company domains for {company.get('ticker')}: {company_domains}")

    # Evaluate each URL
    valid_urls = []
    re_allowed_count = 0

    for url in urls:
        url_domain = extract_domain_from_url(url)
        passes_filter = is_press_release_url(url)

        # If URL passes standard filter, keep it
        if passes_filter:
            valid_urls.append(url)
            continue

        # If URL failed filter but matches company domain, re-allow it
        if url_domain and url_domain.lower() in company_domains:
            logger.info(f"Re-allowing filtered URL (matches company domain '{url_domain}'): {url[:60]}...")
            valid_urls.append(url)
            re_allowed_count += 1

    if re_allowed_count > 0:
        logger.info(f"✓ Re-allowed {re_allowed_count} URL(s) based on company domain matching")

    return valid_urls


# ============================================================================
# RSS Fast Path - Direct DynamoDB Save (Skip Enricher)
# ============================================================================


def url_already_exists(url, ticker, reit_news_table):
    """
    Check if URL already exists in DynamoDB reit_news table

    Single Responsibility: Only checks existence

    Uses ticker+url combination to dedupe

    Args:
        url: URL to check
        ticker: Company ticker
        reit_news_table: DynamoDB table resource

    Returns:
        bool: True if URL exists
    """
    try:
        # Query by ticker first to reduce scan size
        response = reit_news_table.scan(
            FilterExpression='ticker = :ticker AND #url = :url',
            ExpressionAttributeNames={'#url': 'url'},  # 'url' is reserved keyword
            ExpressionAttributeValues={
                ':ticker': ticker,
                ':url': url
            },
            Limit=1
        )

        items = response.get('Items', [])
        return len(items) > 0

    except Exception as e:
        logger.error(f"Dedupe check failed: {e}")
        return False  # Fail open (allow save)


def save_to_dynamodb_direct(metadata, reit_news_table):
    """
    Save press release directly to DynamoDB (skip Enricher queue)

    Single Responsibility: Only saves to DynamoDB

    Used for RSS fast path - when RSS feed provides direct URL,
    we can save immediately without queueing for enrichment

    Args:
        metadata: Dict with ticker, title, url, published_date, source, etc.
        reit_news_table: DynamoDB table resource

    Returns:
        bool: True if saved successfully
    """
    try:
        ticker = metadata['ticker']
        title = metadata['title']

        # Apply title case if ALL CAPS (RSS feeds often have ALL CAPS titles)
        display_title = smart_title_case(title) if is_all_caps(title) else title

        item = {
            'press_release_id': metadata.get('idempotency_key', str(uuid.uuid4())),
            'first_seen_at': get_current_timestamp_utc(),  # ISO 8601 with timezone (for GSI)
            'ticker': ticker,
            'title': title,  # Original title (immutable)
            'display_title': display_title,  # Cleaned title for display
            'url': metadata['url'],
            'press_release_date': metadata['published_date'][:10],  # YYYY-MM-DD format (backward compat)
            'rss_pub_date_at': metadata['published_date'],  # Full ISO 8601 timestamp from RSS pubDate
            'source': metadata.get('source', 'company_rss'),
            'construction_method': 'rss_feed',
            # Social media pipeline fields
            'sector': get_sector_for_ticker(ticker),
            'release_slug': generate_release_slug(display_title),  # Use cleaned title for slug
            'social_status': SOCIAL_STATUS_BODY_NEEDED  # RSS has title only, no body
        }

        # Add email_received_at (actual email time - used for display)
        email_received_at = extract_timestamp_from_email_date(metadata.get('email_date'))
        if email_received_at:
            item['email_received_at'] = email_received_at

        reit_news_table.put_item(Item=item)
        logger.info(f"Saved to DynamoDB: {ticker} - {metadata['url'][:50]}...")
        return True

    except Exception as e:
        logger.error(f"DynamoDB save failed: {e}")
        return False


# ============================================================================
# Company-Specific Title Extraction (LEGACY - Use RealtyIncomeTitleExtractor)
# ============================================================================
# NOTE: extract_realty_income_title() moved to RealtyIncomeTitleExtractor class
# Keeping this alias for backward compatibility

def extract_realty_income_title(html_body):
    """DEPRECATED: Use RealtyIncomeTitleExtractor.extract() instead."""
    return RealtyIncomeTitleExtractor.extract(html_body)


# ============================================================================
# Enricher Queue (NEW - Parser/Enricher Split)
# ============================================================================


def queue_for_enrichment(ticker, email_subject, email_date, idempotency_key, urls, sqs_client, enrich_queue_url, press_release_title=None, press_release_date=None):
    """
    Queue enrichment job for Enricher Lambda

    Single Responsibility: Only queues for enrichment
    DRY: Uses QueueMessageBuilder for message construction

    Args:
        ticker: Company ticker symbol
        email_subject: Email subject line
        email_date: Email date (email send date from headers)
        idempotency_key: Unique key
        urls: List of URLs extracted from email
        sqs_client: SQS client
        enrich_queue_url: Enrichment queue URL
        press_release_title: Optional press release title
        press_release_date: Optional press release date (YYYY-MM-DD) extracted from email body

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        message = QueueMessageBuilder.build_enricher_message(
            ticker=ticker,
            email_subject=email_subject,
            email_date=email_date,
            idempotency_key=idempotency_key,
            urls=urls,
            press_release_title=press_release_title,
            press_release_date=press_release_date
        )

        response = sqs_client.send_message(
            QueueUrl=enrich_queue_url,
            MessageBody=json.dumps(message)
        )

        logger.info(f"✓ Queued for enrichment: {ticker} - {email_subject[:40]}... (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for enrichment: {e}")
        return False


# ============================================================================
# Routing Context (SOLID: Encapsulate routing state)
# ============================================================================


@dataclass
class RoutingContext:
    """
    Encapsulates all routing state for a press release.

    SOLID: Reduces parameter passing between strategy functions.
    """
    ticker: str
    email_subject: str
    email_date: str
    idempotency_key: str
    press_release_date: Optional[str]
    urls: List[str]
    html_body: str
    company: dict
    config: RoutingConfig
    sender_name: str = ''
    sender_domain: str = ''


# ============================================================================
# Routing Strategy Functions (SOLID: Single Responsibility)
# ============================================================================


def _route_to_playwright(ctx: RoutingContext, reason: str = "JS-rendered") -> Tuple[bool, str]:
    """
    Route to Playwright queue.

    SOLID: Single Responsibility - Only handles Playwright routing.
    DRY: Uses RealtyIncomeTitleExtractor for title extraction.

    Args:
        ctx: Routing context
        reason: Routing reason for logging

    Returns:
        Tuple[bool, str]: (success, destination)
    """
    logger.info(f"🎬 Routing to Playwright: {ctx.ticker} ({reason})")

    # Extract title from email body (Realty Income or alerting service emails)
    press_release_title = RealtyIncomeTitleExtractor.extract_if_realty_income(
        ctx.ticker, ctx.html_body
    )
    if not press_release_title:
        press_release_title = AlertingServiceTitleExtractor.extract_if_alerting_service(
            ctx.email_subject,
            ctx.html_body,
            sender_name=ctx.sender_name,
            sender_domain=ctx.sender_domain
        )

    success = queue_for_playwright_scraping(
        ticker=ctx.ticker,
        email_subject=ctx.email_subject,
        email_date=ctx.email_date,
        idempotency_key=ctx.idempotency_key,
        sqs_client=ctx.config.sqs_client,
        playwright_queue_url=ctx.config.playwright_queue_url,
        press_release_title=press_release_title,
        press_release_date=ctx.press_release_date
    )

    return success, 'playwright' if success else 'failed'


def _route_via_rss(ctx: RoutingContext) -> Tuple[bool, str]:
    """
    Attempt RSS fast path routing.

    SOLID: Single Responsibility - Only handles RSS routing.

    Args:
        ctx: Routing context

    Returns:
        Tuple[bool, str]: (success, destination) or (False, '') if RSS unavailable
    """
    from rss_fetcher import fetch_latest_pr_from_rss

    rss_result = fetch_latest_pr_from_rss(ctx.company, max_age_days=7)

    if not rss_result:
        return False, ''

    logger.info(f"📡 Using RSS feed for {ctx.ticker} (FAST PATH)")

    # Check dedupe before saving
    if url_already_exists(rss_result['url'], ctx.ticker, ctx.config.reit_news_table):
        logger.info(f"Duplicate RSS URL (already in DB): {rss_result['url'][:60]}...")
        return True, 'rss_direct'

    # Build metadata and save
    metadata = {
        'ticker': ctx.ticker,
        'title': rss_result['title'],
        'url': rss_result['url'],
        'published_date': rss_result['published_date'].isoformat(),
        'source': 'company_rss',
        'email_subject': ctx.email_subject,
        'email_date': ctx.email_date,
        'idempotency_key': ctx.idempotency_key,
        'rss_url': rss_result['rss_url']
    }

    success = save_to_dynamodb_direct(metadata, ctx.config.reit_news_table)
    if success:
        logger.info(f"✅ RSS PR saved to DB: {ctx.ticker}")
        return True, 'rss_direct'

    logger.warning(f"RSS PR save failed, falling back to email URLs")
    return False, ''


def _route_via_enricher(ctx: RoutingContext) -> Tuple[bool, str]:
    """
    Route to enricher queue.

    SOLID: Single Responsibility - Only handles enricher routing.

    Args:
        ctx: Routing context

    Returns:
        Tuple[bool, str]: (success, destination)
    """
    logger.info(f"📧 Using email URL extraction for {ctx.ticker}")

    # Enhance URLs with company domain matching
    enhanced_urls = enhance_urls_with_company_domains(ctx.urls, ctx.company)
    logger.info(f"URL filtering: {len(ctx.urls)} total → {len(enhanced_urls)} after enhancement")

    # Extract title from email body (Realty Income or alerting service emails)
    press_release_title = RealtyIncomeTitleExtractor.extract_if_realty_income(
        ctx.ticker, ctx.html_body
    )
    if not press_release_title:
        press_release_title = AlertingServiceTitleExtractor.extract_if_alerting_service(
            ctx.email_subject,
            ctx.html_body,
            sender_name=ctx.sender_name,
            sender_domain=ctx.sender_domain
        )

    success = queue_for_enrichment(
        ticker=ctx.ticker,
        email_subject=ctx.email_subject,
        email_date=ctx.email_date,
        idempotency_key=ctx.idempotency_key,
        urls=enhanced_urls,
        sqs_client=ctx.config.sqs_client,
        enrich_queue_url=ctx.config.enrich_queue_url,
        press_release_title=press_release_title,
        press_release_date=ctx.press_release_date
    )

    return success, 'enricher' if success else 'failed'


def _check_circuit_breaker(ctx: RoutingContext) -> Tuple[bool, str]:
    """
    Check circuit breaker and route to Playwright if triggered.

    SOLID: Single Responsibility - Only handles circuit breaker logic.

    Args:
        ctx: Routing context

    Returns:
        Tuple[bool, str]: (triggered, reason) - triggered=True means route to Playwright
    """
    try:
        from shared.redirect_circuit_breaker import should_attempt_redirect
    except ImportError:
        from redirect_circuit_breaker import should_attempt_redirect

    today_iso = get_today_et()
    should_attempt, use_playwright, reason = should_attempt_redirect(ctx.company, today_iso)

    if use_playwright:
        logger.info(f"⚡ Circuit breaker active for {ctx.ticker}: {reason}")
        return True, reason

    return False, ''


# ============================================================================
# Press Release Routing (Strategy Pattern - REFACTORED)
# ============================================================================


def route_press_release(company, email_metadata, idempotency_key, reit_news_table, sqs_client, scrape_queue_url, playwright_queue_url, enrich_queue_url, companies_table):
    """
    Route press release to appropriate destination.

    SOLID Refactoring (2026-03-19):
    - Split into strategy functions (_route_to_playwright, _route_via_rss, etc.)
    - Uses RoutingContext to reduce parameter passing
    - Uses RealtyIncomeTitleExtractor to eliminate 3x duplication
    - Uses QueueMessageBuilder for DRY message construction

    Strategy Pattern:
        1. JavaScript-rendered company → Playwright queue
        2. Circuit breaker active → Playwright queue
        3. RSS feed available → Direct DynamoDB save
        4. Default → Enricher queue

    Args:
        company: Company dictionary
        email_metadata: Email metadata dict
        idempotency_key: Unique key
        reit_news_table: DynamoDB table resource
        sqs_client: SQS client
        scrape_queue_url: Scrape queue URL
        playwright_queue_url: Playwright queue URL
        enrich_queue_url: Enrichment queue URL
        companies_table: Companies table resource

    Returns:
        str: Routing destination ('playwright', 'rss_direct', 'enricher', 'failed')
    """
    # Build routing context
    config = RoutingConfig(
        reit_news_table=reit_news_table,
        sqs_client=sqs_client,
        scrape_queue_url=scrape_queue_url,
        playwright_queue_url=playwright_queue_url,
        enrich_queue_url=enrich_queue_url,
        companies_table=companies_table
    )

    ctx = RoutingContext(
        ticker=company.get('ticker', 'UNKNOWN'),
        email_subject=email_metadata.get('subject', ''),
        email_date=email_metadata.get('date', ''),
        idempotency_key=idempotency_key,
        press_release_date=email_metadata.get('press_release_date'),
        urls=email_metadata.get('urls', []),
        html_body=email_metadata.get('html_text', ''),
        company=company,
        config=config,
        sender_name=email_metadata.get('sender_name', ''),
        sender_domain=email_metadata.get('sender_domain', '')
    )

    # Strategy 1: JavaScript-rendered companies → Playwright
    if should_use_playwright(ctx.ticker):
        logger.info(f"🎬 JavaScript-rendered company detected: {ctx.ticker} (via DynamoDB SSOT)")
        success, destination = _route_to_playwright(ctx, "JS-rendered")
        return destination

    # Strategy 2: Circuit breaker active → Playwright
    triggered, reason = _check_circuit_breaker(ctx)
    if triggered:
        logger.info(f"   Routing directly to Playwright (prevents wasted Enricher invocation)")
        success, destination = _route_to_playwright(ctx, f"circuit breaker: {reason}")
        return 'playwright_circuit_breaker' if success else 'failed'

    # Strategy 3: Try RSS feed first (fast path)
    success, destination = _route_via_rss(ctx)
    if success:
        return destination

    # Strategy 4: Fall back to enricher
    success, destination = _route_via_enricher(ctx)
    return destination
