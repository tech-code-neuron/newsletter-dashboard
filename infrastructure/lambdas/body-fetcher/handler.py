"""
Body Fetcher Lambda
===================
Fetches body content for press releases marked body_needed.
Runs every 15 minutes via EventBridge.
"""

import json
import logging
import os
import time as time_module
import boto3
import trafilatura
from readability import Document
import requests
from datetime import datetime, timezone, time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# AWS clients
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

# Configuration
TABLE_NAME = os.environ.get('REIT_NEWS_TABLE', 'reitsheet-reit-news-v2')
MAX_ITEMS_PER_RUN = 20
MAX_FETCH_ATTEMPTS = 3
FETCH_TIMEOUT = 10
MAX_WORDS = 2000
USER_AGENT = 'TRS-BodyFetcher/1.0 (+https://reitsheet.co)'

# Time windows (Eastern Time) - only process during these hours
EASTERN_TZ = ZoneInfo('America/New_York')
TIME_WINDOWS = [
    (time(6, 0), time(9, 30)),   # 6:00 AM - 9:30 AM ET
    (time(16, 0), time(21, 0)),  # 4:00 PM - 9:00 PM ET
]

table = dynamodb.Table(TABLE_NAME)

# robots.txt cache (per domain)
_robots_cache = {}


def is_within_time_window():
    """Check if current time is within allowed processing windows."""
    now_et = datetime.now(EASTERN_TZ).time()
    for start, end in TIME_WINDOWS:
        if start <= now_et <= end:
            return True
    return False


def query_body_needed_items():
    """Query GSI for items needing body fetch, oldest first."""
    response = table.query(
        IndexName='social_status-first_seen_at-index',
        KeyConditionExpression='social_status = :status',
        ExpressionAttributeValues={':status': 'body_needed'},
        ScanIndexForward=True,  # Oldest first
        Limit=MAX_ITEMS_PER_RUN
    )
    return response.get('Items', [])


def is_allowed_by_robots(url):
    """Check if URL is allowed by robots.txt."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        # Check cache
        if parsed.netloc in _robots_cache:
            rp = _robots_cache[parsed.netloc]
        else:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
            except Exception:
                # If robots.txt unavailable, assume allowed
                return True
            _robots_cache[parsed.netloc] = rp

        return rp.can_fetch(USER_AGENT, url)
    except Exception as e:
        logger.warning(f"robots.txt check failed for {url}: {e}")
        return True  # Fail open


def fetch_and_extract_body(url):
    """Fetch URL and extract body text using trafilatura with readability fallback."""
    # Respect robots.txt
    if not is_allowed_by_robots(url):
        logger.info(f"Blocked by robots.txt: {url}")
        return None, "Blocked by robots.txt"

    headers = {'User-Agent': USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        logger.warning(f"HTTP fetch failed for {url}: {e}")
        return None, str(e)

    # Try trafilatura first
    body = trafilatura.extract(html, include_comments=False, include_tables=False)

    # Fallback to readability-lxml
    if not body or len(body.split()) < 50:
        try:
            doc = Document(html)
            body = doc.summary()
            # Strip HTML tags from readability output
            from bs4 import BeautifulSoup
            body = BeautifulSoup(body, 'html.parser').get_text(separator=' ', strip=True)
        except Exception as e:
            logger.warning(f"Readability fallback failed: {e}")

    if not body:
        return None, "No body extracted"

    # Truncate to MAX_WORDS
    words = body.split()
    if len(words) > MAX_WORDS:
        body = ' '.join(words[:MAX_WORDS])

    return body, None


def update_item_success(item, content_preview):
    """Update item with extracted body and flip status to pending."""
    table.update_item(
        Key={'press_release_id': item['press_release_id']},
        UpdateExpression='SET content_preview = :body, social_status = :status, '
                        'body_fetched_at = :now, word_count = :wc '
                        'REMOVE body_fetch_attempts, body_fetch_error',
        ExpressionAttributeValues={
            ':body': content_preview,
            ':status': 'pending',
            ':now': datetime.now(timezone.utc).isoformat(),
            ':wc': len(content_preview.split())
        }
    )


def update_item_failure(item, error_msg):
    """Increment attempts and mark unavailable after 3 failures."""
    attempts = item.get('body_fetch_attempts', 0) + 1

    if attempts >= MAX_FETCH_ATTEMPTS:
        # Final failure - mark as unavailable
        table.update_item(
            Key={'press_release_id': item['press_release_id']},
            UpdateExpression='SET social_status = :status, body_fetch_attempts = :attempts, '
                            'body_fetch_error = :error, body_unavailable_at = :now',
            ExpressionAttributeValues={
                ':status': 'body_unavailable',
                ':attempts': attempts,
                ':error': error_msg,
                ':now': datetime.now(timezone.utc).isoformat()
            }
        )
        emit_metric('BodyUnavailable', 1)
    else:
        # Retry later
        table.update_item(
            Key={'press_release_id': item['press_release_id']},
            UpdateExpression='SET body_fetch_attempts = :attempts, body_fetch_error = :error',
            ExpressionAttributeValues={
                ':attempts': attempts,
                ':error': error_msg
            }
        )


def emit_metric(metric_name, value):
    """Emit CloudWatch metric."""
    cloudwatch.put_metric_data(
        Namespace='ReitSheet/BodyFetcher',
        MetricData=[{
            'MetricName': metric_name,
            'Value': value,
            'Unit': 'Count'
        }]
    )


def lambda_handler(event, context):
    """Main handler - fetch bodies for body_needed items."""
    # Exit early if outside allowed time windows
    if not is_within_time_window():
        now_et = datetime.now(EASTERN_TZ).strftime('%H:%M')
        logger.info(json.dumps({
            "event": "skipped_outside_window",
            "current_time_et": now_et,
            "windows": ["6:00-9:30 AM", "4:00-9:00 PM"]
        }))
        return {"statusCode": 200, "body": "Outside processing window"}

    start_time = time_module.time()

    items = query_body_needed_items()
    logger.info(json.dumps({"event": "start", "items_found": len(items)}))

    success_count = 0
    failure_count = 0

    for item in items:
        url = item.get('url')
        press_release_id = item.get('press_release_id')

        if not url:
            logger.warning(f"No URL for item {press_release_id}")
            continue

        body, error = fetch_and_extract_body(url)

        if body:
            update_item_success(item, body)
            success_count += 1
            logger.info(json.dumps({
                "event": "body_fetched",
                "press_release_id": press_release_id,
                "word_count": len(body.split())
            }))
        else:
            update_item_failure(item, error)
            failure_count += 1
            logger.warning(json.dumps({
                "event": "fetch_failed",
                "press_release_id": press_release_id,
                "error": error,
                "attempts": item.get('body_fetch_attempts', 0) + 1
            }))

    duration_ms = int((time_module.time() - start_time) * 1000)

    emit_metric('BodyFetchSuccess', success_count)
    emit_metric('BodyFetchFailure', failure_count)

    logger.info(json.dumps({
        "event": "complete",
        "success": success_count,
        "failure": failure_count,
        "duration_ms": duration_ms
    }))

    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed": len(items),
            "success": success_count,
            "failure": failure_count
        })
    }
