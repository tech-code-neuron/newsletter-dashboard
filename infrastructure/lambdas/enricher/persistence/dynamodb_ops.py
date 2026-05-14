"""
DynamoDB Operations - V2 Schema (URL-based primary key)

NEW SCHEMA:
  Primary Key: url (HASH only)
  GSI 1: ticker + press_release_date (for queries by ticker, sorted by PR date)
  GSI 2: ticker + first_seen_at (for queries by ticker, sorted by ingestion time)

BENEFITS:
  - Natural deduplication (DynamoDB enforces uniqueness on URL)
  - No application-level deduplication needed
  - No race conditions
  - Simpler, faster inserts
  - True idempotency via conditional writes
"""

import os
import boto3
from botocore.exceptions import ClientError
import logging

# Use shared timestamp utilities (single source of truth)
from shared.timestamp_utils import (
    get_current_timestamp_utc,
    extract_date_only_from_email,
    extract_timestamp_from_email_date,
    get_current_date_only_utc
)

# Use shared landing page detector (single source of truth - SSOT)
from shared.landing_page_detector import is_landing_page, is_utility_page

# Social media pipeline utilities
from shared.sector_utils import get_sector_for_ticker
from shared.slug_utils import generate_release_slug
from shared.social_constants import SOCIAL_STATUS_PENDING

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def save_to_dynamodb(url, metadata, reit_news_table, allow_landing_page=False):
    """
    Save press release to DynamoDB using URL as primary key

    V2 Schema: URL is the primary key, natural deduplication
    Uses conditional write to prevent duplicates (idempotent)

    Args:
        url: Press release URL (primary key)
        metadata: Press release metadata dict
        reit_news_table: DynamoDB Table resource
        allow_landing_page: If True, bypass landing page rejection (for fallback saves)

    Returns:
        bool: True if saved successfully or already exists, False on error
    """
    ticker = metadata.get('ticker', 'UNKNOWN')

    # Reject landing page URLs (not specific press releases)
    # Uses shared module (SSOT - single source of truth)
    # Can be bypassed with allow_landing_page=True for fallback saves
    if not allow_landing_page and is_landing_page(url):
        logger.warning(f"Rejecting landing page URL: {url[:80]}...")
        return False

    # Reject utility page URLs (email alerts, unsubscribe, etc.)
    # Defense in depth - these should be filtered earlier, but catch any that slip through
    if is_utility_page(url):
        logger.warning(f"Rejecting utility page URL: {url[:80]}...")
        return False

    try:
        # Determine press_release_date with fallback chain:
        # 1. press_release_date from email body extraction (most accurate)
        # 2. email_date from email header (reliable fallback)
        # 3. today's date (last resort)
        press_release_date = metadata.get('press_release_date')
        if not press_release_date:
            # Try to extract from email Date header
            press_release_date = extract_date_only_from_email(metadata.get('email_date'))
            if press_release_date:
                logger.info(f"Using email_date as press_release_date: {press_release_date}")
        if not press_release_date:
            # Last resort: today's date
            press_release_date = get_current_date_only_utc()
            logger.warning(f"No date available, using today: {press_release_date}")

        # Extract email timestamp (when the email was sent)
        email_received_at = extract_timestamp_from_email_date(metadata.get('email_date'))

        title = metadata.get('subject', '')
        item = {
            'url': url,  # Primary key - naturally unique
            'ticker': ticker,
            'title': title,  # Original title (immutable)
            'display_title': metadata.get('display_title'),  # Cleaned title (optional)
            'first_seen_at': get_current_timestamp_utc(),  # ISO 8601 with timezone (when processed)
            'press_release_date': press_release_date,  # DATE ONLY (business date)
            'source': 'enricher_validated',
            'needs_scraping': False,
            'construction_method': metadata.get('construction_method', 'unknown'),
            # Social media pipeline fields
            'sector': get_sector_for_ticker(ticker),
            'release_slug': generate_release_slug(title),
            'social_status': SOCIAL_STATUS_PENDING
        }

        # Add email timestamp if available (when email was sent)
        if email_received_at:
            item['email_received_at'] = email_received_at

        # Optional fields
        optional_fields = ['press_release_title', 'email_subject', 'email_date',
                         'idempotency_key', 'company_name', 'match_quality']
        for field in optional_fields:
            if field in metadata and metadata[field]:
                item[field] = metadata[field]

        # Use conditional write to prevent duplicates (idempotent)
        # If URL already exists, this will fail gracefully
        reit_news_table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(#url)',
            ExpressionAttributeNames={'#url': 'url'}
        )

        logger.info(f"✓ Saved to DynamoDB: {ticker} - {url[:60]}...")

        # Queue for social media classification (if queue URL configured)
        classify_queue_url = os.environ.get('SOCIAL_CLASSIFY_QUEUE_URL')
        if classify_queue_url:
            try:
                from persistence.sqs_ops import queue_for_social_classification
                sqs_client = boto3.client('sqs')
                queue_for_social_classification(url, ticker, sqs_client, classify_queue_url)
            except Exception as e:
                logger.warning(f"Failed to queue for social classification: {e}")

        return True

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # URL already exists - not an error, just idempotent behavior
            logger.info(f"Duplicate prevented (URL exists): {ticker} - {url[:60]}...")
            return True  # Return success - already saved is same as success
        else:
            logger.error(f"DynamoDB error: {e}", exc_info=True)
            return False

    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {e}", exc_info=True)
        return False


def query_press_releases_by_ticker(ticker, limit=50, start_date=None, end_date=None, reit_news_table=None):
    """
    Query press releases by ticker using GSI

    Uses ticker-date-index GSI to efficiently query by ticker,
    sorted by press_release_date (newest first)

    Args:
        ticker: Company ticker symbol
        limit: Maximum number of results (default 50)
        start_date: Filter by date >= start_date (YYYY-MM-DD format)
        end_date: Filter by date <= end_date (YYYY-MM-DD format)
        reit_news_table: DynamoDB Table resource

    Returns:
        list: Press release items
    """
    if not reit_news_table:
        reit_news_table = boto3.resource('dynamodb', region_name='us-east-1').Table('reitsheet-reit-news-v2')

    try:
        # Build query expression
        key_condition = 'ticker = :ticker'
        expression_values = {':ticker': ticker}

        # Add date range filter if provided
        if start_date and end_date:
            key_condition += ' AND press_release_date BETWEEN :start_date AND :end_date'
            expression_values[':start_date'] = start_date
            expression_values[':end_date'] = end_date
        elif start_date:
            key_condition += ' AND press_release_date >= :start_date'
            expression_values[':start_date'] = start_date
        elif end_date:
            key_condition += ' AND press_release_date <= :end_date'
            expression_values[':end_date'] = end_date

        # Query GSI
        response = reit_news_table.query(
            IndexName='ticker-date-index',
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=expression_values,
            Limit=limit,
            ScanIndexForward=False  # Newest first
        )

        return response.get('Items', [])

    except Exception as e:
        logger.error(f"Error querying press releases: {e}", exc_info=True)
        return []


def get_press_release_by_url(url, reit_news_table):
    """
    Get press release by URL (primary key lookup)

    Args:
        url: Press release URL
        reit_news_table: DynamoDB Table resource

    Returns:
        dict: Press release item or None if not found
    """
    try:
        response = reit_news_table.get_item(Key={'url': url})
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting press release: {e}", exc_info=True)
        return None


def get_company_config(ticker, companies_table):
    """
    Get company configuration from DynamoDB

    Args:
        ticker: Company ticker symbol
        companies_table: DynamoDB Table resource

    Returns:
        dict: Company configuration or None
    """
    try:
        response = companies_table.get_item(Key={'ticker': ticker})

        if 'Item' not in response:
            logger.warning(f"No company config found for {ticker}")
            return None

        return response['Item']

    except Exception as e:
        logger.error(f"Error retrieving company config: {e}", exc_info=True)
        return None
