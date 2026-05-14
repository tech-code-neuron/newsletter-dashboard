"""
Press Release Pipeline - Playwright Scraper Lambda (Refactored - SOLID 10/10)
==================================================================
Purpose: Scrape JavaScript-rendered press releases (EPRT, etc.)
Triggered by: SQS Playwright Scraper Queue

SOLID Refactoring Complete:
  - Modular Architecture: 4 focused modules (browser, matching, persistence, config)
  - Single Responsibility: Each module does ONE thing
  - Clean Separation: Browser logic, matching logic, persistence separated
  - Easy Testing: Each module independently testable

Code Reduction: 662 lines → ~400 lines handler (40% reduction)

Flow:
  1. Receive scraping job from SQS (ticker, email subject, date)
  2. Launch headless Chrome via Playwright
  3. Navigate to company's press releases list page
  4. Extract press release links from JavaScript-rendered content
  5. Match email subject to scraped titles (fuzzy matching)
  6. Save matched press release to DynamoDB
  7. Mark as processed

Last Updated: 2026-03-13
"""

import json
import os
import re
import sys
import logging
import shutil
from datetime import datetime, timezone, timedelta
import boto3

# Import refactored modules
from browser.context_manager import create_browser_context
from browser.page_navigator import scrape_press_releases
from matching.fuzzy_matcher import find_matching_press_release
from persistence.dynamodb_ops import (
    initialize as initialize_persistence,
    save_press_release,
    queue_failed_match_for_review
)

# Import Playwright (installed via Lambda layer or package)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.error("Playwright not available - Lambda will fail")

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================

_initialized = False
_config = {}
_tables = {}
_clients = {}

logger = logging.getLogger()


def _ensure_initialized():
    """Lazy initialization of AWS clients, env vars, and DynamoDB tables."""
    global _initialized, _config, _tables, _clients

    if _initialized:
        return

    # AWS Clients
    _clients['dynamodb'] = boto3.resource('dynamodb')
    _clients['sqs'] = boto3.client('sqs')

    # Environment Variables
    _config['REIT_NEWS_TABLE'] = os.environ['REIT_NEWS_TABLE']
    _config['COMPANIES_TABLE'] = os.environ['COMPANIES_TABLE']
    _config['PLAYWRIGHT_DLQ_URL'] = os.environ.get('PLAYWRIGHT_DLQ_URL', '')
    _config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', 'INFO')
    _config['MAX_MESSAGE_AGE_MINUTES'] = int(os.environ.get('MAX_MESSAGE_AGE_MINUTES', '60'))

    # Logging
    logger.setLevel(getattr(logging, _config['LOG_LEVEL']))

    # DynamoDB Tables
    dynamodb = _clients['dynamodb']
    _tables['reit_news'] = dynamodb.Table(_config['REIT_NEWS_TABLE'])
    _tables['companies'] = dynamodb.Table(_config['COMPANIES_TABLE'])

    # Initialize persistence module with AWS clients
    initialize_persistence(_tables['reit_news'], _clients['sqs'], _config['PLAYWRIGHT_DLQ_URL'])

    _initialized = True


def _companies_table():
    return _tables['companies']

# ============================================================================
# Constants - SOLID: Single Source of Truth (imported from browser/config.py)
# ============================================================================

from browser.config import (
    BROWSER_HEADLESS,
    BROWSER_TIMEOUT_MS,
    BROWSER_ARGS,
    USER_AGENT,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
    LOCALE,
    MAX_PRESS_RELEASES,
    MIN_TITLE_LENGTH,
    MIN_MATCH_SCORE,
    EXCELLENT_MATCH_SCORE,
    SELECTOR_TIMEOUT_MS
)

# ============================================================================
# Company Configuration - SOLID: Database-Driven (No Hardcoded Config!)
# ============================================================================
# Configuration now stored in DynamoDB reitsheet-companies-config table
#
# Required fields:
#   - playwright_url: Press releases list page URL
#   - playwright_selector: CSS selector for press release links
#   - playwright_wait_for: Element to wait for before scraping
#   - playwright_wait_network_idle: Boolean (wait for network idle)
#   - playwright_title_cleanup: Optional cleanup regex pattern
#
# Example DynamoDB record:
# {
#   "ticker": "SAFE",
#   "url_construction_method": "playwright_scraper",
#   "playwright_url": "https://ir.safeholdinc.com/news-releases",
#   "playwright_selector": "a[href*='/news-release-details/']",
#   "playwright_wait_for": "a[href*='/news-release-details/']",
#   "playwright_wait_network_idle": true
# }

def get_playwright_config(ticker):
    """
    Fetch Playwright scraping configuration from DynamoDB

    SOLID: Single Source of Truth - All config in database

    UPDATED 2026-03-17: Falls back to press_release_url with generic selectors
    when company-specific Playwright config is missing. This enables the circuit
    breaker to route ANY company to Playwright, not just pre-configured ones.

    Args:
        ticker: Company ticker symbol

    Returns:
        dict: Playwright configuration or None if not found/invalid
    """
    try:
        response = _companies_table().get_item(Key={'ticker': ticker})
        company = response.get('Item')

        if not company:
            logger.error(f"❌ Company not found in database: {ticker}")
            return None

        # Debug: Log what we got from DynamoDB
        logger.info(f"📋 Retrieved company config for {ticker}, has {len(company)} fields")

        # Check for company-specific Playwright config first
        has_specific_config = all(
            company.get(f) for f in ['playwright_url', 'playwright_selector', 'playwright_wait_for']
        )

        if has_specific_config:
            # Use company-specific Playwright config
            config = {
                'url': company['playwright_url'],
                'selector': company['playwright_selector'],
                'wait_for': company['playwright_wait_for'],
                'wait_network_idle': company.get('playwright_wait_network_idle', True),
                'title_cleanup': lambda s: s,  # Default: no cleanup
                'use_generic_scraping': False
            }

            # Optional: Apply title cleanup pattern if provided
            cleanup_pattern = company.get('playwright_title_cleanup')
            if cleanup_pattern:
                import re
                config['title_cleanup'] = lambda s: re.sub(cleanup_pattern, '', s).strip()

            logger.info(f"✓ Loaded company-specific Playwright config for {ticker}")
            return config

        # FALLBACK: Use press_release_url with generic selectors
        # This enables circuit breaker routing for ANY company
        if company.get('press_release_url'):
            logger.info(f"⚡ Using press_release_url fallback for {ticker} (no specific Playwright config)")
            config = {
                'url': company['press_release_url'],
                'selector': 'body',  # Generic - just wait for page to load
                'wait_for': 'body',
                'wait_network_idle': True,  # Wait for JS to finish
                'title_cleanup': lambda s: s,
                'use_generic_scraping': True  # Flag for generic link extraction
            }
            logger.info(f"   URL: {company['press_release_url'][:60]}...")
            return config

        # No URL at all - this shouldn't happen for valid companies
        logger.error(f"❌ No press_release_url found for {ticker} - cannot proceed")
        logger.info(f"Available fields: {list(company.keys())}")
        return None

    except Exception as e:
        logger.error(f"❌ Failed to fetch Playwright config for {ticker}: {e}")
        return None

# ============================================================================
# Stale Message Detection (Phase 1: Age-Based Prevention)
# ============================================================================


def is_message_stale(message_body: dict, max_age_minutes: int = None) -> tuple[bool, float]:
    """
    Check if message is older than deployment threshold.

    This prevents processing messages that were queued before a bug fix deployment.
    Messages older than max_age_minutes are automatically dropped.

    Args:
        message_body: SQS message body dict
        max_age_minutes: Maximum age in minutes (default from config)

    Returns:
        tuple: (is_stale, age_in_minutes)
    """
    if max_age_minutes is None:
        max_age_minutes = _config.get('MAX_MESSAGE_AGE_MINUTES', 60)

    queued_at = message_body.get('queued_at')
    if not queued_at:
        return False, 0.0  # No timestamp = process it (backwards compatible)

    try:
        queued_time = datetime.fromisoformat(queued_at)
        age_minutes = (datetime.now(timezone.utc) - queued_time).total_seconds() / 60
        return age_minutes > max_age_minutes, age_minutes
    except (ValueError, TypeError):
        # Invalid timestamp = process it (safe default)
        return False, 0.0


# ============================================================================
# Helper Functions - SOLID: Single Responsibility
# ============================================================================


def cleanup_tmp_directory():
    """
    Clean up /tmp directory to prevent "no space left on device" errors

    Playwright creates artifacts in /tmp/playwright-* that accumulate across
    Lambda invocations. Lambda's ephemeral storage is limited, so we must
    clean up before each run.

    SOLID: Single Responsibility - Only handles /tmp cleanup
    """
    tmp_dir = '/tmp'
    playwright_pattern = 'playwright-'

    try:
        # Count items before cleanup
        items_before = len([f for f in os.listdir(tmp_dir) if playwright_pattern in f])

        if items_before > 0:
            logger.info(f"🧹 Cleaning /tmp: {items_before} Playwright artifacts found")

            # Remove only Playwright-related artifacts (safe cleanup)
            for item in os.listdir(tmp_dir):
                if playwright_pattern in item:
                    item_path = os.path.join(tmp_dir, item)
                    try:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove {item_path}: {e}")

            # Count items after cleanup
            items_after = len([f for f in os.listdir(tmp_dir) if playwright_pattern in f])
            logger.info(f"✓ Cleanup complete: {items_before - items_after} artifacts removed")
        else:
            logger.info("✓ /tmp is clean (no Playwright artifacts)")

    except Exception as e:
        # Don't fail Lambda if cleanup fails - log and continue
        logger.warning(f"⚠️ /tmp cleanup failed: {e}")


# ============================================================================
# Extracted Functions (moved to modules)
# ============================================================================
# create_browser_context() → browser/context_manager.py
# scrape_press_releases() → browser/page_navigator.py
# calculate_similarity() → matching/fuzzy_matcher.py
# find_matching_press_release() → matching/fuzzy_matcher.py
# save_press_release() → persistence/dynamodb_ops.py
# queue_failed_match_for_review() → persistence/dynamodb_ops.py


# ============================================================================
# Direct URL Processing (NEW: For enricher fallback cases)
# ============================================================================


def process_direct_url(ticker, url, idempotency_key, email_subject, press_release_title=None, press_release_date=None, email_date=None):
    """
    Process a direct URL - no fuzzy matching needed, just verify and save.

    This is used when the enricher already found the correct URL but validation
    failed (e.g., 403 bot protection). Playwright can load the page with a
    real browser to bypass bot protection.

    Args:
        ticker: Company ticker symbol
        url: Direct URL to process (already found by enricher)
        idempotency_key: Unique key for deduplication
        email_subject: Email subject (used as fallback title)
        press_release_title: Optional title from email body
        press_release_date: Optional date from email body (YYYY-MM-DD)
        email_date: Optional email Date header (RFC 2822 format)

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"🌐 Direct URL scrape: {ticker} → {url[:80]}...")

    try:
        with sync_playwright() as p:
            # Create browser context
            browser, context, page = create_browser_context(p)

            try:
                # Navigate to the specific URL with networkidle fallback
                logger.info(f"📡 Navigating to: {url[:80]}...")
                try:
                    page.goto(url, wait_until='networkidle', timeout=BROWSER_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    # Fallback: networkidle hung, try domcontentloaded + wait
                    logger.warning(f"⚠️ networkidle timed out, falling back to domcontentloaded")
                    page.goto(url, wait_until='domcontentloaded', timeout=BROWSER_TIMEOUT_MS)
                    page.wait_for_timeout(3000)  # Let JS render

                # Wait a bit for any dynamic content
                page.wait_for_timeout(2000)

                # Extract title from page
                page_title = extract_title_from_page(page)

                # Use extracted title, or fall back to press_release_title, or email_subject
                final_title = page_title or press_release_title or email_subject
                logger.info(f"📋 Title: {final_title[:60]}...")

                # Extract body for social media pipeline
                body_content = extract_body_from_page(page)

                # Save to DynamoDB
                save_press_release(
                    ticker, final_title, url, idempotency_key,
                    press_release_date=press_release_date,
                    email_date=email_date,
                    content_preview=body_content
                )
                logger.info(f"✅ Successfully saved direct URL: {ticker}")
                return True

            finally:
                browser.close()
                logger.info("✓ Browser closed")

    except PlaywrightTimeoutError as e:
        logger.error(f"❌ Timeout loading direct URL: {e}")
        # Queue for manual review since we couldn't load the page
        queue_failed_match_for_review(
            ticker, email_subject, url, idempotency_key,
            reason=f'Timeout loading direct URL: {str(e)[:100]}'
        )
        return False
    except Exception as e:
        logger.error(f"❌ Error processing direct URL: {e}", exc_info=True)
        return False


def _is_domain_only_title(title: str) -> bool:
    """Check if title is just a domain name (should be rejected as invalid title)."""
    if not title:
        return False
    title_clean = title.lower().strip()
    # Check for domain patterns like "company.com" or "investor.company.com"
    if re.match(r'^[a-z0-9.-]+\.(com|net|org|io|co|us|gov|edu|info|biz)$', title_clean):
        return True
    return False


# Generic title phrases that should fall back to email subject
GENERIC_TITLE_PHRASES = {
    'news release',
    'press release',
    'media release',
    'news',
    'press',
    'media',
    'investor relations',
}


def _is_generic_title(title: str) -> bool:
    """Check if title is a generic label (should fall back to email subject)."""
    if not title:
        return False
    return title.lower().strip() in GENERIC_TITLE_PHRASES


def extract_title_from_page(page):
    """
    Extract press release title from page content.

    Tries multiple strategies:
    1. H1 tag (most common for press releases)
    2. Article title tag
    3. Page title tag (fallback)

    Args:
        page: Playwright page object

    Returns:
        str: Extracted title or None
    """
    # Strategy 1: Look for H1 (most common)
    try:
        h1 = page.locator('h1').first
        if h1.count() > 0:
            title = h1.inner_text().strip()
            if title and len(title) >= MIN_TITLE_LENGTH and not _is_domain_only_title(title) and not _is_generic_title(title):
                logger.info(f"📑 Found title from H1: {title[:50]}...")
                return title
    except Exception:
        pass

    # Strategy 2: Look for article/press release specific elements
    for selector in ['.press-release-title', '.article-title', '[class*="title"]']:
        try:
            elem = page.locator(selector).first
            if elem.count() > 0:
                title = elem.inner_text().strip()
                if title and len(title) >= MIN_TITLE_LENGTH and not _is_domain_only_title(title) and not _is_generic_title(title):
                    logger.info(f"📑 Found title from {selector}: {title[:50]}...")
                    return title
        except Exception:
            pass

    # Strategy 3: Page title tag (fallback)
    try:
        title = page.title().strip()
        # Clean up common suffixes
        for suffix in [' | Investor Relations', ' - Press Release', ' | News']:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        if title and len(title) >= MIN_TITLE_LENGTH and not _is_domain_only_title(title) and not _is_generic_title(title):
            logger.info(f"📑 Found title from page title: {title[:50]}...")
            return title
    except Exception:
        pass

    logger.warning("⚠️ Could not extract title from page")
    return None


def extract_body_from_page(page):
    """
    Extract press release body text from page.

    Tries common press release container selectors and extracts first 2000 words.
    Used for social media pipeline classification.

    Args:
        page: Playwright page object

    Returns:
        str: Extracted body text (up to 2000 words) or None
    """
    selectors = [
        '.xn-content',           # PR Newswire
        '.module_body',          # Business Wire
        'article',               # Generic article container
        '.press-release-body',   # Company-specific
        '.release-body',         # Alternative
        '[class*="press-release"]',
        '[class*="article-body"]',
        'main',                  # Fallback to main content
    ]

    for selector in selectors:
        try:
            elem = page.locator(selector).first
            if elem.count() > 0:
                text = elem.inner_text().strip()
                if text and len(text) > 100:
                    words = text.split()[:2000]
                    logger.info(f"📄 Extracted {len(words)} words from {selector}")
                    return ' '.join(words)
        except Exception:
            pass

    logger.warning("⚠️ Could not extract body from page")
    return None


# ============================================================================
# Helper Functions (still in handler)
# ============================================================================

def extract_date_from_email_date(email_date_str):
    """
    Extract YYYY-MM-DD date from email Date header.

    Email dates are in RFC 2822 format like "Tue, 11 Mar 2026 20:00:00 +0000".

    Args:
        email_date_str: Email Date header string

    Returns:
        str: Date in YYYY-MM-DD format, or None if parsing fails
    """
    if not email_date_str:
        return None

    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(email_date_str)
        return dt.strftime('%Y-%m-%d')
    except Exception as e:
        logger.warning(f"Could not parse email date '{email_date_str}': {e}")
        return None


def process_scraping_job(ticker, email_subject, idempotency_key, press_release_title=None, press_release_date=None, email_date=None, direct_url=None):
    """
    Process a single scraping job for JavaScript-rendered company

    SOLID: Orchestrator function - coordinates workflow

    Args:
        ticker: Company ticker symbol
        email_subject: Email subject line
        idempotency_key: Unique key for deduplication
        press_release_title: Optional title extracted from email body (Realty Income)
        press_release_date: Optional date from email body (YYYY-MM-DD)
        email_date: Optional email Date header (RFC 2822 format, for date fallback)
        direct_url: Optional URL from enricher fallback (skip list page scraping)

    Returns:
        bool: True if successful, False otherwise
    """
    # Validate Playwright availability
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("❌ Playwright not available - cannot process job")
        return False

    # DIRECT URL MODE: Enricher already found the URL, just scrape it with a real browser
    # This happens when validation failed (403 bot protection) but the URL is correct
    if direct_url:
        logger.info(f"📬 Direct URL mode: {direct_url[:80]}...")
        return process_direct_url(
            ticker, direct_url, idempotency_key, email_subject,
            press_release_title=press_release_title,
            press_release_date=press_release_date,
            email_date=email_date
        )

    # STANDARD MODE: Scrape press releases list page and fuzzy match
    # Get company configuration from DynamoDB
    config = get_playwright_config(ticker)
    if not config:
        logger.error(f"❌ No Playwright configuration found for {ticker} in DynamoDB")
        logger.info(f"💡 Add config: aws dynamodb update-item --table-name reitsheet-companies-config --key '{{\"ticker\":{{\"S\":\"{ticker}\"}}}}' ...")
        return False

    # Use title from email body if provided, otherwise email subject
    match_text = press_release_title if press_release_title else email_subject
    logger.info(f"🎬 Processing Playwright job: {ticker} - Matching: {match_text[:60]}...")

    try:
        with sync_playwright() as p:
            # Create browser context
            browser, context, page = create_browser_context(p)

            try:
                # Scrape press releases
                press_releases = scrape_press_releases(page, config)

                if not press_releases:
                    logger.error(f"❌ No press releases found on page")
                    queue_failed_match_for_review(ticker, match_text, config['url'], idempotency_key, reason='No press releases found on page')
                    return False

                # Match email subject (or extracted title) to scraped PRs
                match = find_matching_press_release(
                    press_releases,
                    match_text,
                    config.get('title_cleanup')
                )

                if match:
                    # Save matched press release
                    save_press_release(
                        ticker, match['title'], match['url'], idempotency_key,
                        press_release_date=press_release_date,
                        email_date=email_date
                    )
                    logger.info(f"✅ Successfully processed: {ticker}")
                    return True
                else:
                    # Queue for manual review or save as fallback
                    logger.warning(f"⚠️  No good match found - queueing for review")
                    saved = queue_failed_match_for_review(ticker, match_text, config['url'], idempotency_key, reason='No fuzzy match above threshold')
                    return saved  # True if fallback saved, False otherwise

            finally:
                # Always close browser
                browser.close()
                logger.info("✓ Browser closed")

    except PlaywrightTimeoutError as e:
        logger.error(f"❌ Timeout error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return False


# ============================================================================
# Lambda Handler
# ============================================================================

def lambda_handler(event, context):
    """
    Main Lambda handler - processes SQS messages

    Message format:
    {
        "ticker": "EPRT",
        "email_subject": "Essential Properties: Announces Dividend...",
        "email_date": "2026-03-09",
        "idempotency_key": "abc123...",
        "press_release_title": "..."  # Optional (from email body for Realty Income)
    }

    Returns:
        dict: Status response
    """
    # Lazy initialization (first invocation only)
    _ensure_initialized()

    logger.info(f"📨 Received {len(event['Records'])} message(s)")

    # Clean up /tmp to prevent "no space left on device" errors
    # Playwright creates artifacts that can accumulate across invocations
    cleanup_tmp_directory()

    success_count = 0
    failure_count = 0
    stale_dropped_count = 0

    for record in event['Records']:
        try:
            message = json.loads(record['body'])

            # Drop stale messages immediately
            is_stale, age = is_message_stale(message)
            if is_stale:
                logger.warning(
                    f"⏰ Dropping stale message",
                    extra={
                        'age_minutes': round(age, 1),
                        'threshold_minutes': _config.get('MAX_MESSAGE_AGE_MINUTES', 60),
                        'ticker': message.get('ticker', 'UNKNOWN'),
                        'idempotency_key': message.get('idempotency_key')
                    }
                )
                stale_dropped_count += 1
                # Don't raise exception = message auto-deleted
                continue

            ticker = message['ticker']
            email_subject = message['email_subject']
            email_date = message.get('email_date')  # For date fallback chain
            idempotency_key = message['idempotency_key']
            press_release_title = message.get('press_release_title')  # Optional
            press_release_date = message.get('press_release_date')  # Optional (from email body)
            direct_url = message.get('url')  # NEW: URL from enricher fallback

            # Process scraping job
            success = process_scraping_job(
                ticker,
                email_subject,
                idempotency_key,
                press_release_title=press_release_title,
                press_release_date=press_release_date,
                email_date=email_date,
                direct_url=direct_url
            )

            if success:
                success_count += 1
            else:
                failure_count += 1
                # Let SQS retry by raising exception
                raise Exception(f"Failed to process {ticker}")

        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)
            failure_count += 1
            raise  # Let SQS handle retry and DLQ

    logger.info(
        f"✅ Completed: {success_count} success, {failure_count} failures, "
        f"{stale_dropped_count} stale dropped"
    )

    return {
        'statusCode': 200 if failure_count == 0 else 500,
        'body': json.dumps({
            'success': success_count,
            'failures': failure_count,
            'stale_dropped': stale_dropped_count
        })
    }
