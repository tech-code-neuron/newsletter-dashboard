"""
Scraper Persistence - Database Operations
==========================================
Save press releases and maintain scraping cache

SOLID Principles:
- Single Responsibility: Only handles database operations
- Dependency Injection: Tables can be injected for testing
- No Hardcoded Values: All constants defined

Last Created: 2026-03-11
Last Modified: 2026-03-15 (added shared timestamp utilities)
"""

import logging
import hashlib
import os
import sys
from typing import Optional, Tuple, Dict, Any

# Import from shared (bundled in Lambda package at same level)
try:
    # Try Lambda/packaged import (shared at root level)
    from shared.landing_page_detector import is_landing_page, get_landing_page_reason
    from shared.timestamp_utils import get_current_timestamp_utc, extract_timestamp_from_email_date
    from shared.sector_utils import get_sector_for_ticker
    from shared.slug_utils import generate_release_slug
    from shared.social_constants import SOCIAL_STATUS_PENDING
except ImportError:
    # Try development import (shared in parent directory)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
    from landing_page_detector import is_landing_page, get_landing_page_reason
    from timestamp_utils import get_current_timestamp_utc, extract_timestamp_from_email_date
    from sector_utils import get_sector_for_ticker
    from slug_utils import generate_release_slug
    from social_constants import SOCIAL_STATUS_PENDING

logger = logging.getLogger()

# ============================================================================
# DynamoDB Tables (Module-Level, can be overridden)
# ============================================================================

# These are set by initialize_tables() at module load time
REIT_NEWS_TABLE = None
URL_CACHE_TABLE = None


def initialize_tables(reit_news_table, url_cache_table):
    """
    Initialize DynamoDB tables

    Single Responsibility: Only initializes tables

    Args:
        reit_news_table: DynamoDB Table resource
        url_cache_table: DynamoDB Table resource
    """
    global REIT_NEWS_TABLE, URL_CACHE_TABLE
    REIT_NEWS_TABLE = reit_news_table
    URL_CACHE_TABLE = url_cache_table
    logger.info("Database tables initialized")


# ============================================================================
# Press Release Persistence
# ============================================================================

def save_press_release(url: str, content_preview: Optional[str], word_count: int, metadata: Dict[str, Any]) -> bool:
    """
    Save press release URL + extracted content to DynamoDB

    Single Responsibility: Only saves press release

    Landing Page Protection: Validates URL is NOT a landing page before saving

    Args:
        url: Press release URL
        content_preview: Extracted text preview (first 2000 words)
        word_count: Total word count
        metadata: Additional metadata (ticker, company_name, scrape_method, etc.)

    Returns:
        bool: Success
    """
    if not REIT_NEWS_TABLE:
        logger.error("REIT_NEWS_TABLE not initialized")
        return False

    # CRITICAL: Validate URL is not a landing page
    if is_landing_page(url):
        reason = get_landing_page_reason(url)
        ticker = metadata.get('ticker', 'UNKNOWN')
        logger.warning(f"⚠️  BLOCKED: Landing page detected for {ticker}")
        logger.warning(f"   URL: {url[:80]}...")
        logger.warning(f"   Reason: {reason}")
        logger.warning(f"   Landing pages are NOT saved to production")
        return False  # Block save, return failure

    try:
        from content_extractor import extract_company_domain

        press_release_id = hashlib.sha256(url.encode()).hexdigest()
        company_domain = extract_company_domain(url)
        ticker = metadata.get('ticker', 'UNKNOWN')
        title = metadata.get('title', metadata.get('email_subject', ''))

        item = {
            'press_release_id': press_release_id,
            'first_seen_at': get_current_timestamp_utc(),  # ISO 8601 with timezone (for GSI)
            'url': url,
            'company_domain': company_domain,
            'source_type': metadata.get('source_type', 'scraped'),
            'scraped_at': get_current_timestamp_utc(),  # ISO 8601 with timezone
            # Social media pipeline fields
            'sector': get_sector_for_ticker(ticker),
            'release_slug': generate_release_slug(title),
            'social_status': SOCIAL_STATUS_PENDING,
            **metadata
        }

        # Add email_received_at (actual email time - used for display) if available
        email_received_at = extract_timestamp_from_email_date(metadata.get('email_date'))
        if email_received_at:
            item['email_received_at'] = email_received_at

        # Add extracted content if available
        if content_preview:
            item['content_preview'] = content_preview
            item['word_count'] = word_count
            item['content_extracted'] = True
        else:
            item['content_extracted'] = False

        # Add company_id if domain extracted successfully
        if company_domain:
            item['company_id'] = company_domain

        REIT_NEWS_TABLE.put_item(Item=item)

        logger.info(f"✅ Saved: {url[:60]}... ({word_count} words, {metadata.get('scrape_method', 'unknown')})")
        return True

    except Exception as e:
        logger.error(f"Error saving press release: {e}", exc_info=True)
        return False


# ============================================================================
# URL Cache (Immutable Log)
# ============================================================================

def log_to_url_cache(url: str, scrape_metadata: Dict[str, Any]) -> bool:
    """
    Write immutable log entry to URL cache table

    Single Responsibility: Only logs to cache

    CRITICAL: This table is NEVER deleted - permanent record of all scrape attempts
    Even if reitsheet-reit-news gets cleared, this preserves the history

    Purpose:
    - Prevent re-scraping same URL
    - Audit trail of all activity
    - Recovery from accidental deletion

    Args:
        url: URL that was scraped
        scrape_metadata: Metadata about scrape attempt

    Returns:
        bool: Success
    """
    if not URL_CACHE_TABLE:
        logger.error("URL_CACHE_TABLE not initialized")
        return False

    try:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        timestamp = get_current_timestamp_utc()

        cache_entry = {
            'url_hash': url_hash,
            'scraped_at': timestamp,
            'url': url,
            'ticker': scrape_metadata.get('ticker'),
            'company_name': scrape_metadata.get('company_name'),
            'scrape_status': 'success' if scrape_metadata.get('success') else 'failed',
            'scrape_method': scrape_metadata.get('scrape_method'),
            'word_count': scrape_metadata.get('word_count', 0),
            'content_extracted': scrape_metadata.get('content_extracted', False),
            'bypass_403': scrape_metadata.get('bypass_403', False),
            'source_type': scrape_metadata.get('source_type'),
        }

        # Add error info if failed
        if scrape_metadata.get('error'):
            cache_entry['error'] = scrape_metadata['error']
        if scrape_metadata.get('note'):
            cache_entry['note'] = scrape_metadata['note']

        URL_CACHE_TABLE.put_item(Item=cache_entry)

        logger.info(f"📝 Logged to immutable URL cache: {url_hash[:16]}...")
        return True

    except Exception as e:
        logger.error(f"CRITICAL: Failed to log to URL cache: {e}", exc_info=True)
        # Don't fail the whole operation if cache logging fails
        return False


def check_already_scraped(url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if URL has already been scraped successfully

    Single Responsibility: Only checks cache

    CRITICAL: Checks BOTH url_cache (immutable log) and reit_news tables
    Prevents unnecessary re-scraping and avoids rate limits

    Args:
        url: URL to check

    Returns:
        tuple: (already_scraped, existing_data)
    """
    if not URL_CACHE_TABLE:
        logger.error("URL_CACHE_TABLE not initialized")
        return False, None

    try:
        url_hash = hashlib.sha256(url.encode()).hexdigest()

        # Query immutable URL cache first (faster, purpose-built for this)
        response = URL_CACHE_TABLE.query(
            KeyConditionExpression='url_hash = :hash',
            ExpressionAttributeValues={':hash': url_hash},
            Limit=10,  # Get recent attempts
            ScanIndexForward=False  # Most recent first
        )

        items = response.get('Items', [])
        if not items:
            logger.info(f"🆕 New URL - not in cache")
            return False, None

        # Check for successful scrape with content
        for item in items:
            if item.get('scrape_status') == 'success' and item.get('content_extracted'):
                logger.info(f"✅ CACHE HIT - URL already scraped ({item.get('word_count', 0)} words)")
                logger.info(f"   Last scraped: {item.get('scraped_at')}")
                return True, item

        # Found attempts but no successful content extraction
        logger.info(f"⚠️  URL attempted before but no successful content - will retry")
        return False, None

    except Exception as e:
        logger.error(f"Error checking cache: {e}", exc_info=True)
        # On error, assume not scraped (fail-safe: allow scraping)
        return False, None


# ============================================================================
# Deduplication Check
# ============================================================================

def is_duplicate_url(url: str, ticker: Optional[str] = None) -> bool:
    """
    Quick check if URL already exists in database

    Single Responsibility: Only checks for duplicates

    This is a faster check than check_already_scraped() since it only
    checks the primary table, not the full cache history

    Args:
        url: URL to check
        ticker: Optional ticker for faster lookup

    Returns:
        bool: True if duplicate
    """
    if not REIT_NEWS_TABLE:
        logger.error("REIT_NEWS_TABLE not initialized")
        return False

    try:
        press_release_id = hashlib.sha256(url.encode()).hexdigest()

        response = REIT_NEWS_TABLE.get_item(
            Key={'press_release_id': press_release_id}
        )

        exists = 'Item' in response

        if exists:
            logger.info(f"Duplicate URL detected: {url[:60]}...")

        return exists

    except Exception as e:
        logger.warning(f"Error checking duplicate: {e}")
        return False  # Fail-safe: allow save
