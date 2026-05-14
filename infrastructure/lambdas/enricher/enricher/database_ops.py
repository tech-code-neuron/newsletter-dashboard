"""
Enricher - Database Operations
===============================
Save press releases and check for duplicates

SOLID Principles:
- Single Responsibility: Only handles database operations
- Dependency Injection: Tables can be injected for testing

Last Created: 2026-03-11
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger()

# Module-level table references (set by initialize_tables)
REIT_NEWS_TABLE = None


def initialize_tables(reit_news_table):
    """
    Initialize DynamoDB tables

    Single Responsibility: Only initializes tables

    Args:
        reit_news_table: DynamoDB Table resource
    """
    global REIT_NEWS_TABLE
    REIT_NEWS_TABLE = reit_news_table
    logger.info("Database tables initialized")


def save_to_dynamodb(url: str, metadata: Dict[str, Any]) -> bool:
    """
    Save press release to DynamoDB

    Single Responsibility: Only saves to database

    Args:
        url: Press release URL
        metadata: Metadata dict (ticker, subject, idempotency_key, etc.)

    Returns:
        bool: Success
    """
    if not REIT_NEWS_TABLE:
        logger.error("REIT_NEWS_TABLE not initialized")
        return False

    ticker = metadata.get('ticker', 'UNKNOWN')

    # Check if URL already exists for this ticker (deduplication)
    if url_exists_for_ticker(url, ticker):
        logger.info(f"Skipping duplicate URL: {ticker} - {url[:60]}...")
        return True  # Return success (not an error, just already saved)

    try:
        item = {
            'id': metadata['idempotency_key'],
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'title': metadata.get('subject', ''),
            'url': url,
            'first_seen_at': datetime.utcnow().isoformat(),
            'source': 'enricher_validated',
            'needs_scraping': False,
            'construction_method': metadata.get('construction_method', 'unknown')
        }

        REIT_NEWS_TABLE.put_item(Item=item)

        logger.info(f"✓ Saved to DynamoDB: {metadata.get('ticker')} - {url[:60]}...")
        return True

    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {e}", exc_info=True)
        return False


def url_exists_for_ticker(url: str, ticker: str) -> bool:
    """
    Check if URL already exists for this ticker in DynamoDB

    Single Responsibility: Only checks for URL existence

    Prevents duplicate URLs from being saved multiple times
    (e.g., BRX saved 6x, CLDT saved 9x - fixes 78% duplicate issue)

    Uses GSI ticker-url-index for O(1) lookup.
    Falls back gracefully if GSI doesn't exist.

    Args:
        url: Press release URL
        ticker: Company ticker symbol

    Returns:
        bool: True if URL already exists for ticker, False otherwise
    """
    if not REIT_NEWS_TABLE:
        logger.error("REIT_NEWS_TABLE not initialized")
        return False

    try:
        # Query by ticker and URL (requires GSI: ticker-url-index)
        response = REIT_NEWS_TABLE.query(
            IndexName='ticker-url-index',
            KeyConditionExpression='ticker = :ticker AND #url = :url',
            ExpressionAttributeNames={'#url': 'url'},  # 'url' is reserved word
            ExpressionAttributeValues={
                ':ticker': ticker,
                ':url': url
            },
            Limit=1
        )

        exists = len(response.get('Items', [])) > 0

        if exists:
            logger.info(f"Duplicate URL detected: {ticker} - {url[:60]}... (skipping)")

        return exists

    except Exception as e:
        # If GSI doesn't exist, fall back to allowing save
        logger.warning(f"Error checking URL existence (GSI may not exist): {e}")
        return False  # Safe default: allow save
