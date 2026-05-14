"""
Simple HTTP Scraper Lambda
==========================
Handles 90% of companies using lightweight HTTP clients

Layers:
    1. curl_cffi (TLS fingerprinting)
    2. cloudscraper (Cloudflare solver)
    3. Fallback: Save URL only

SOLID: Single Responsibility - Only simple HTTP scraping
Cost: ~$0.001 per invocation (256MB, 5-10s)
Last Updated: 2026-03-09
"""

import json
import logging
import boto3
import os
from datetime import datetime

# Layer 1: curl_cffi
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

# Layer 2: cloudscraper
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

# AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
REIT_NEWS_TABLE = os.environ['REIT_NEWS_TABLE']
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# DynamoDB table
reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)

# Logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# Social media pipeline imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
try:
    from sector_utils import get_sector_for_ticker
    from slug_utils import generate_release_slug
    from social_constants import SOCIAL_STATUS_PENDING
except ImportError:
    def get_sector_for_ticker(ticker): return None
    def generate_release_slug(title): return None
    SOCIAL_STATUS_PENDING = 'pending'

# Constants
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = 'Mozilla/5.0 (compatible; REITSheet/1.0)'


def scrape_with_curl_cffi(url):
    """
    Scrape using curl_cffi (TLS fingerprinting)

    Success rate: 70-85%
    Speed: Fast (1-3s)
    """
    if not CURL_CFFI_AVAILABLE:
        return None, "curl_cffi_not_available"

    try:
        response = curl_requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            impersonate="chrome110",
            headers={'User-Agent': USER_AGENT}
        )

        if response.status_code == 200:
            logger.info(f"✓ curl_cffi success: {url[:50]}...")
            return response.text, "curl_cffi"

        return None, f"curl_cffi_failed_{response.status_code}"

    except Exception as e:
        logger.warning(f"curl_cffi failed: {e}")
        return None, f"curl_cffi_error"


def scrape_with_cloudscraper(url):
    """
    Scrape using cloudscraper (Cloudflare solver)

    Success rate: 60-80%
    Speed: Medium (3-8s)
    """
    if not CLOUDSCRAPER_AVAILABLE:
        return None, "cloudscraper_not_available"

    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows'}
        )

        response = scraper.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': USER_AGENT}
        )

        if response.status_code == 200:
            logger.info(f"✓ cloudscraper success: {url[:50]}...")
            return response.text, "cloudscraper"

        return None, f"cloudscraper_failed_{response.status_code}"

    except Exception as e:
        logger.warning(f"cloudscraper failed: {e}")
        return None, f"cloudscraper_error"


def scrape_url_simple(url):
    """
    Scrape URL using simple HTTP methods (2-layer cascade)

    Returns:
        tuple: (content, method_used) or (None, error_reason)
    """
    # Layer 1: curl_cffi
    content, method = scrape_with_curl_cffi(url)
    if content:
        return content, method

    # Layer 2: cloudscraper
    content, method = scrape_with_cloudscraper(url)
    if content:
        return content, method

    # Layer 3: Graceful failure
    logger.warning(f"All simple methods failed for {url[:50]}...")
    return None, "all_methods_failed"


def save_press_release(url, metadata, content=None, scraping_method=None):
    """
    Save press release to DynamoDB

    Args:
        url: Press release URL
        metadata: Metadata dict
        content: Scraped content (optional)
        scraping_method: Method used (curl_cffi, cloudscraper, etc.)
    """
    try:
        ticker = metadata.get('ticker', 'UNKNOWN')
        title = metadata.get('email_subject', '')
        item = {
            'id': metadata['idempotency_key'],
            'ticker': ticker,
            'title': title,
            'url': url,
            'first_seen_at': datetime.utcnow().isoformat(),
            'source': 'simple_scraper',
            'scraping_method': scraping_method or 'unknown',
            'needs_scraping': content is None,  # True if scraping failed
            # Social media pipeline fields
            'sector': get_sector_for_ticker(ticker),
            'release_slug': generate_release_slug(title),
            'social_status': SOCIAL_STATUS_PENDING
        }

        if content:
            # Extract first 2000 words for summary
            words = content.split()[:2000]
            item['content_preview'] = ' '.join(words)

        reit_news_table.put_item(Item=item)
        logger.info(f"✓ Saved: {ticker} via {scraping_method}")

    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {e}")


def process_scraping_job(job):
    """
    Process one scraping job

    Args:
        job: Job dict from Scraper Router

    Returns:
        dict: Result
    """
    url = job.get('url')
    ticker = job.get('ticker', 'UNKNOWN')

    logger.info(f"🔍 Scraping {ticker}: {url[:50]}...")

    # Scrape using simple methods
    content, method = scrape_url_simple(url)

    # Save to DynamoDB
    save_press_release(
        url=url,
        metadata=job,
        content=content,
        scraping_method=method
    )

    return {
        'success': content is not None,
        'method': method,
        'ticker': ticker
    }


def lambda_handler(event, context):
    """
    Main Lambda handler - process simple scraping jobs from SQS

    Message format:
    {
        "url": "https://...",
        "ticker": "EPRT",
        "email_subject": "...",
        "idempotency_key": "abc123"
    }
    """
    logger.info(f"📨 Received {len(event['Records'])} scraping job(s)")

    results = {
        'success': 0,
        'failed': 0,
        'by_method': {}
    }

    for record in event['Records']:
        try:
            job = json.loads(record['body'])
            result = process_scraping_job(job)

            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1

            # Track by method
            method = result.get('method', 'unknown')
            results['by_method'][method] = results['by_method'].get(method, 0) + 1

        except Exception as e:
            logger.error(f"Error processing job: {e}", exc_info=True)
            results['failed'] += 1

    logger.info(f"✅ Simple scraping complete: {results}")

    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
