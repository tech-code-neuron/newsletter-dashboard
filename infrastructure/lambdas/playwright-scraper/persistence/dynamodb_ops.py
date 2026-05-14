"""
DynamoDB Operations - Press Release Persistence
=================================================
Extracted from handler.py (lines 420-496)

SOLID: Single Responsibility - Only handles database and queue operations

Last Created: 2026-03-13
Last Updated: 2026-03-15 (Added date fallback chain + shared timestamp utilities)
"""

import json
import logging
import sys
import os
from datetime import datetime, timezone

# Add shared modules to path (two levels up from persistence/ to build context, then into shared/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from landing_page_detector import is_landing_page, get_landing_page_reason
from timestamp_utils import (
    get_current_timestamp_utc,
    extract_date_only_from_email,
    extract_timestamp_from_email_date,
    get_current_date_only_utc
)
from sector_utils import get_sector_for_ticker
from slug_utils import generate_release_slug
from social_constants import SOCIAL_STATUS_PENDING
from title_case import clean_title

logger = logging.getLogger()

# Module-level clients (injected via initialize())
_reit_news_table = None
_sqs_client = None
_playwright_dlq_url = None


# ============================================================================
# Initialization
# ============================================================================

def initialize(reit_news_table, sqs_client, playwright_dlq_url):
    """
    Initialize module with AWS clients

    Args:
        reit_news_table: DynamoDB table for press releases
        sqs_client: SQS client for queue operations
        playwright_dlq_url: Dead Letter Queue URL for failed matches
    """
    global _reit_news_table, _sqs_client, _playwright_dlq_url
    _reit_news_table = reit_news_table
    _sqs_client = sqs_client
    _playwright_dlq_url = playwright_dlq_url


# ============================================================================
# DynamoDB Operations
# ============================================================================

def save_press_release(ticker, title, url, idempotency_key, press_release_date=None, email_date=None, content_preview=None):
    """
    Save press release to DynamoDB

    SOLID: Single Responsibility - Only handles database save

    Date fallback chain:
    1. press_release_date from email body extraction (most accurate)
    2. email_date from email header (reliable fallback)
    3. today's date (last resort)

    Args:
        ticker: Company ticker symbol
        title: Press release title
        url: Press release URL
        idempotency_key: Unique key for deduplication
        press_release_date: Optional date from email body (YYYY-MM-DD)
        email_date: Optional email Date header (RFC 2822 format)
        content_preview: Optional body text for social media pipeline (up to 2000 words)
    """
    # Determine press_release_date with fallback chain
    final_date = press_release_date
    if not final_date:
        # Try to extract from email Date header
        final_date = extract_date_only_from_email(email_date)
        if final_date:
            logger.info(f"Using email_date as press_release_date: {final_date}")
    if not final_date:
        # Last resort: today's date
        final_date = get_current_date_only_utc()
        logger.warning(f"No date available, using today: {final_date}")

    # Extract email timestamp (when the email was sent)
    email_received_at = extract_timestamp_from_email_date(email_date)

    # Apply title cleanup (remove company name duplication, apply title case)
    cleanup_result = clean_title(title, ticker)
    display_title = cleanup_result['cleaned_title']
    if cleanup_result['was_cleaned']:
        logger.info(f"✂️  Title cleaned: '{title[:40]}...' → '{display_title[:40]}...'")

    item = {
        'press_release_id': idempotency_key,
        'ticker': ticker,
        'title': title,  # Original title (immutable)
        'display_title': display_title,  # Cleaned title for display
        'url': url,
        'press_release_date': final_date,  # DATE ONLY (business date)
        'first_seen_at': get_current_timestamp_utc(),  # ISO 8601 with timezone (when processed)
        'source': 'email_playwright_scraper',
        'needs_scraping': False,  # URL found, no further scraping needed
        # Social media pipeline fields
        'sector': get_sector_for_ticker(ticker),
        'release_slug': generate_release_slug(display_title),  # Use cleaned title for slug
        'social_status': SOCIAL_STATUS_PENDING
    }

    # Add email timestamp if available (when email was sent)
    if email_received_at:
        item['email_received_at'] = email_received_at

    # Add content preview if available (for social media pipeline)
    if content_preview:
        item['content_preview'] = content_preview

    _reit_news_table.put_item(Item=item)
    logger.info(f"💾 Saved to DynamoDB: {ticker} - {title[:50]}...")


# ============================================================================
# Queue Operations
# ============================================================================

def queue_failed_match_for_review(ticker, email_subject, list_page_url, idempotency_key, reason='Failed fuzzy match'):
    """
    Queue failed match for manual review instead of saving landing page

    REPLACES: save_fallback_press_release() - no longer saves landing pages to production

    SOLID: Single Responsibility - Routes failed matches to review queue

    Args:
        ticker: Company ticker symbol
        email_subject: Original email subject
        list_page_url: Press releases list page URL (landing page)
        idempotency_key: Unique key for deduplication
        reason: Reason for failure (default: 'Failed fuzzy match')

    Returns:
        bool: True if queued successfully, False otherwise
    """
    # Check if URL is a landing page
    if is_landing_page(list_page_url):
        landing_page_reason = get_landing_page_reason(list_page_url)
        logger.warning(f"⚠️  Landing page detected: {landing_page_reason}")

    if not _playwright_dlq_url:
        # Fallback: Save extracted title + landing page URL directly to DynamoDB
        # This ensures we never lose data even without a DLQ configured
        logger.warning("⚠️  PLAYWRIGHT_DLQ_URL not configured - saving extracted title as fallback")
        try:
            save_press_release(
                ticker=ticker,
                title=email_subject,  # This is actually the extracted title (match_text)
                url=list_page_url,
                idempotency_key=idempotency_key
            )
            logger.info(f"✓ Fallback saved: {ticker} - {email_subject[:50]}... (landing page: {list_page_url})")
            return True
        except Exception as e:
            logger.error(f"❌ Fallback save failed: {e}")
            return False

    try:
        review_message = {
            'classification': 'failed_match',
            'url': list_page_url,
            'ticker': ticker,
            'email_subject': email_subject,
            'idempotency_key': idempotency_key,
            'reason': reason,
            'queued_at': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                'source': 'playwright_scraper',
                'note': 'Fuzzy match below threshold - needs manual review'
            }
        }

        _sqs_client.send_message(
            QueueUrl=_playwright_dlq_url,
            MessageBody=json.dumps(review_message)
        )

        logger.info(f"✓ Queued for manual review: {ticker} (DLQ MessageId sent)")
        return True

    except Exception as e:
        logger.error(f"Error queuing for review: {e}", exc_info=True)
        return False
