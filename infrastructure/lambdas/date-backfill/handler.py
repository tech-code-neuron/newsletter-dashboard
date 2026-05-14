"""
Press Release Date Backfill Lambda

Fetches HTML for press release URLs and extracts actual publication dates.
Can be run manually or on a schedule to keep dates up-to-date.
"""

import json
import boto3
import requests
import logging
from datetime import datetime
from typing import Optional

# Import date extraction module
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from date_extraction import extract_date_from_html

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('reitsheet-reit-news')

def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch HTML content from URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; PressReleasePipeline/1.0; +https://your-domain.com)'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)

        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.error(f"Error fetching {url[:60]}: {e}")

    return None

def handler(event, context):
    """
    Lambda handler for backfilling press release dates.

    Event parameters:
    - limit: Maximum number of records to process (default: 50)
    - ticker: Optional ticker to filter by
    """

    limit = event.get('limit', 50)  # Process 50 at a time to avoid timeout
    ticker = event.get('ticker')

    logger.info(f"🔍 Starting date backfill (limit={limit})")

    # Scan for records without proper press_release_date
    scan_kwargs = {
        'ProjectionExpression': 'press_release_id, ticker, title, #url, first_seen_at, press_release_date',
        'ExpressionAttributeNames': {'#url': 'url'},
        'Limit': limit
    }

    if ticker:
        scan_kwargs['FilterExpression'] = 'ticker = :ticker'
        scan_kwargs['ExpressionAttributeValues'] = {':ticker': ticker}

    response = table.scan(**scan_kwargs)
    items = response.get('Items', [])

    # Filter to items that need date extraction
    items_to_process = []
    for item in items:
        pr_date = item.get('press_release_date')
        first_seen = item.get('first_seen_at', '')[:10]

        # Process if no date or if it matches first_seen_at (default value)
        if not pr_date or pr_date == first_seen:
            items_to_process.append(item)

    logger.info(f"Found {len(items_to_process)} records to process")

    updated_count = 0
    failed_count = 0

    for item in items_to_process:
        press_release_id = item['press_release_id']
        first_seen_at = item['first_seen_at']
        ticker = item.get('ticker', 'UNKNOWN')
        url = item.get('url', '')
        title = item.get('title', '')[:50]

        logger.info(f"Processing: {ticker} | {title}...")

        # Fetch HTML
        html = fetch_html(url)
        if not html:
            logger.warning(f"Failed to fetch HTML for {url[:60]}")
            failed_count += 1
            continue

        # Extract date
        extracted_date = extract_date_from_html(html, url)

        if not extracted_date:
            # Fall back to first_seen_at date
            extracted_date = first_seen_at[:10] if first_seen_at else datetime.utcnow().strftime('%Y-%m-%d')
            logger.warning(f"Could not extract date, using fallback: {extracted_date}")

        # Update DynamoDB
        try:
            table.update_item(
                Key={
                    'press_release_id': press_release_id,
                    'first_seen_at': first_seen_at
                },
                UpdateExpression='SET press_release_date = :date',
                ExpressionAttributeValues={
                    ':date': extracted_date
                }
            )
            logger.info(f"✓ Updated {ticker} with date: {extracted_date}")
            updated_count += 1
        except Exception as e:
            logger.error(f"Error updating {press_release_id}: {e}")
            failed_count += 1

    summary = {
        'processed': len(items_to_process),
        'updated': updated_count,
        'failed': failed_count
    }

    logger.info(f"✅ Backfill complete: {json.dumps(summary)}")

    return {
        'statusCode': 200,
        'body': json.dumps(summary)
    }
