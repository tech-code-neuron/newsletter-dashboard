"""
DLQ Processor Lambda
====================
Process messages from Dead Letter Queues with intelligent retry strategies

SOLID Compliance:
    - Single Responsibility: Only processes DLQ messages
    - Open/Closed: Add new retry strategies without modifying existing code
    - Strategy Pattern: Retry strategies extracted to functions
    - No Hardcoded Values: All config in environment variables

Retry Strategies:
    1. Exponential backoff retry (3 attempts) - for parse/scrape/playwright
    2. Enricher failures → Playwright (prevents recursive loops)
    3. Fallback scraper (Playwright → Simple)
    4. Manual review table (permanent failures)
    5. SNS alerts (on-call engineer notification)

IMPORTANT: Enricher failures are routed to Playwright, NOT back to enricher.
This prevents recursive invocation loops (AWS detected and blocked these).
Enricher failures are typically URL validation issues that Playwright can handle.

Last Updated: 2026-03-16
"""

import json
import logging
import boto3
import os
import time
from datetime import datetime, timedelta, timezone

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
    _clients['sqs'] = boto3.client('sqs')
    _clients['dynamodb'] = boto3.resource('dynamodb')
    _clients['sns'] = boto3.client('sns')

    # Environment Variables
    _config['PARSE_QUEUE_URL'] = os.environ['PARSE_QUEUE_URL']
    _config['ENRICH_QUEUE_URL'] = os.environ.get('ENRICH_QUEUE_URL', '')
    _config['SCRAPE_QUEUE_URL'] = os.environ['SCRAPE_QUEUE_URL']
    _config['PLAYWRIGHT_QUEUE_URL'] = os.environ.get('PLAYWRIGHT_QUEUE_URL', '')
    _config['MANUAL_REVIEW_TABLE'] = os.environ['MANUAL_REVIEW_TABLE']
    _config['ALERT_SNS_TOPIC'] = os.environ.get('ALERT_SNS_TOPIC', '')
    _config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', 'INFO')
    _config['MAX_RETRY_ATTEMPTS'] = int(os.environ.get('MAX_RETRY_ATTEMPTS', '3'))
    _config['RETRY_BACKOFF_BASE'] = int(os.environ.get('RETRY_BACKOFF_BASE', '2'))

    # Logging
    logger.setLevel(getattr(logging, _config['LOG_LEVEL']))

    # DynamoDB Tables
    _tables['manual_review'] = _clients['dynamodb'].Table(_config['MANUAL_REVIEW_TABLE'])

    # Queue mapping - SOLID: Open/Closed principle
    _config['QUEUE_MAP'] = {
        'parse': _config['PARSE_QUEUE_URL'],
        'enrich': _config['ENRICH_QUEUE_URL'],
        'scrape': _config['SCRAPE_QUEUE_URL'],
        'playwright': _config['PLAYWRIGHT_QUEUE_URL']
    }

    _initialized = True


def _sqs():
    return _clients['sqs']


def _sns():
    return _clients['sns']


def _manual_review_table():
    return _tables['manual_review']


def get_failure_count(message):
    """
    Get failure count from message attributes

    Returns:
        int: Number of times this message has failed
    """
    return int(message.get('failure_count', 0))


def increment_failure_count(message):
    """
    Increment failure count in message

    Returns:
        dict: Updated message with incremented count and timestamp
    """
    message['failure_count'] = get_failure_count(message) + 1
    message['last_retry_at'] = datetime.now(timezone.utc).isoformat()

    # Track first failure for alerting
    if 'first_failed_at' not in message:
        message['first_failed_at'] = datetime.now(timezone.utc).isoformat()

    return message


def retry_with_backoff(message, target_queue_url, attempt):
    """
    Retry message with exponential backoff

    Strategy: Wait 2^attempt seconds before retry

    Args:
        message: Message to retry
        target_queue_url: Queue to send to
        attempt: Attempt number (1, 2, 3)

    Returns:
        bool: Success
    """
    try:
        # Calculate backoff delay: 2^1=2s, 2^2=4s, 2^3=8s
        delay_seconds = _config['RETRY_BACKOFF_BASE'] ** attempt

        logger.info(f"Retrying after {delay_seconds}s (attempt {attempt}/{_config['MAX_RETRY_ATTEMPTS']})")
        time.sleep(delay_seconds)

        # Send to queue with updated failure count
        updated_message = increment_failure_count(message)

        _sqs().send_message(
            QueueUrl=target_queue_url,
            MessageBody=json.dumps(updated_message)
        )

        logger.info(f"✓ Retried message to {target_queue_url}")
        return True

    except Exception as e:
        logger.error(f"Error retrying message: {e}")
        return False


def try_fallback_scraper(message):
    """
    Try fallback scraper for failed scraping jobs

    Strategy: If Playwright failed, try Simple Scraper (lighter, faster)

    Returns:
        bool: Success
    """
    try:
        # Only applicable for scraping jobs
        if 'url' not in message:
            logger.warning("Message has no URL - cannot use fallback scraper")
            return False

        logger.info("Trying fallback: Simple Scraper")

        # Route to simple scraper queue
        _sqs().send_message(
            QueueUrl=_config['SCRAPE_QUEUE_URL'],
            MessageBody=json.dumps(message)
        )

        logger.info("✓ Sent to fallback scraper")
        return True

    except Exception as e:
        logger.error(f"Error sending to fallback scraper: {e}")
        return False


def send_to_playwright(message):
    """
    Route failed enricher message to Playwright queue.

    IMPORTANT: This prevents recursive loops. Enricher failures should NOT
    retry to enricher (causes infinite loop). Instead, route to Playwright
    which uses a real browser to handle:
    - 403/404 errors (bot protection)
    - Dynamic content
    - Redirect failures

    Args:
        message: Failed enricher message

    Returns:
        bool: Success
    """
    if not _config['PLAYWRIGHT_QUEUE_URL']:
        logger.warning("No Playwright queue configured - cannot route enricher failure")
        return False

    try:
        # Adapt message format for Playwright
        playwright_message = {
            'ticker': message.get('ticker'),
            'company_name': message.get('company_name'),
            'idempotency_key': message.get('idempotency_key'),
            'email_date': message.get('email_date'),
            'email_subject': message.get('email_subject'),
            'urls': message.get('urls', []),
            'source': 'dlq_processor_fallback',
            'original_failure_count': get_failure_count(message),
            'original_failure_reason': message.get('error', 'enricher_failure')
        }

        _sqs().send_message(
            QueueUrl=_config['PLAYWRIGHT_QUEUE_URL'],
            MessageBody=json.dumps(playwright_message)
        )

        logger.info(f"✓ Routed enricher failure to Playwright (ticker: {message.get('ticker')})")
        return True

    except Exception as e:
        logger.error(f"Error routing to Playwright: {e}")
        return False


def save_to_manual_review(message, failure_reason):
    """
    Save permanently failed message to manual review table

    Args:
        message: Failed message
        failure_reason: Reason for failure
    """
    try:
        item = {
            'id': message.get('idempotency_key', f"unknown-{int(time.time())}"),
            'message': json.dumps(message),
            'failure_reason': failure_reason,
            'failure_count': get_failure_count(message),
            'first_failed_at': message.get('first_failed_at', datetime.now(timezone.utc).isoformat()),
            'saved_for_review_at': datetime.now(timezone.utc).isoformat(),
            'status': 'needs_review',
            'ticker': message.get('ticker', 'UNKNOWN'),
            'company_name': message.get('company_name', 'Unknown Company'),
            'url': message.get('url', 'No URL')
        }

        _manual_review_table().put_item(Item=item)
        logger.info(f"✓ Saved to manual review: {item['id']}")

    except Exception as e:
        logger.error(f"Error saving to manual review: {e}")


def send_alert(message, failure_reason):
    """
    Send alert to on-call engineer via SNS

    Args:
        message: Failed message
        failure_reason: Reason for failure
    """
    if not _config['ALERT_SNS_TOPIC']:
        logger.warning("No SNS topic configured for alerts")
        return

    try:
        ticker = message.get('ticker', 'UNKNOWN')
        company_name = message.get('company_name', 'Unknown Company')
        subject = f"Press Release Pipeline: Permanent failure for {ticker}"

        alert_message = f"""
Press Release Pipeline - Permanent Processing Failure

Company: {company_name} ({ticker})
Failure Reason: {failure_reason}
Failure Count: {get_failure_count(message)}
Idempotency Key: {message.get('idempotency_key', 'unknown')}
First Failed: {message.get('first_failed_at', 'unknown')}

Message has been saved to manual review table.

View manual review table:
https://console.aws.amazon.com/dynamodb/home?region=us-east-1#tables:selected={MANUAL_REVIEW_TABLE}

Message Details:
{json.dumps(message, indent=2)}
"""

        _sns().publish(
            TopicArn=_config['ALERT_SNS_TOPIC'],
            Subject=subject,
            Message=alert_message
        )

        logger.info(f"✓ Alert sent via SNS for {ticker}")

    except Exception as e:
        logger.error(f"Error sending alert: {e}")


def determine_source_queue(source_arn):
    """
    Determine source queue from event source ARN

    SOLID: Single responsibility - only parses ARN

    Args:
        source_arn: Event source ARN

    Returns:
        str: Queue name (parse, enrich, scrape, playwright) or 'unknown'
    """
    if 'parse-dlq' in source_arn:
        return 'parse'
    elif 'enrich-dlq' in source_arn:
        return 'enrich'
    elif 'scrape-dlq' in source_arn:
        return 'scrape'
    elif 'playwright' in source_arn:
        return 'playwright'
    else:
        logger.warning(f"Unknown source queue from ARN: {source_arn}")
        return 'unknown'


def process_dlq_message(record, source_queue):
    """
    Process one DLQ message using intelligent retry strategies

    Strategy Progression:
        Attempts 1-3: Retry with exponential backoff to original queue
        Attempt 4: Try fallback scraper (if applicable)
        Attempt 5+: Save to manual review + alert

    Args:
        record: SQS record
        source_queue: Name of source queue (parse, enrich, scrape, playwright)

    Returns:
        dict: Result with status and metadata
    """
    try:
        message = json.loads(record['body'])
        failure_count = get_failure_count(message)

        logger.info(f"Processing DLQ message from {source_queue} (failure #{failure_count + 1})")

        # Strategy 1-3: Retry with exponential backoff
        if failure_count < _config['MAX_RETRY_ATTEMPTS']:
            # ENRICHER SPECIAL CASE: Route to Playwright instead of retrying
            # Reason: Enricher failures are usually URL validation issues (403/404,
            # redirects, bot protection) that a real browser (Playwright) can handle.
            # Retrying to enricher causes RECURSIVE LOOPS (AWS detected this).
            if source_queue == 'enrich':
                logger.info("Enricher failure - routing to Playwright (no retry to enricher)")
                success = send_to_playwright(message)
                if success:
                    return {'status': 'fallback', 'scraper': 'playwright', 'queue': source_queue}
                # If Playwright routing fails, fall through to manual review
                logger.warning("Failed to route to Playwright - will save to manual review")
            else:
                target_queue = _config['QUEUE_MAP'].get(source_queue)

                if target_queue:
                    success = retry_with_backoff(message, target_queue, failure_count + 1)
                    if success:
                        return {'status': 'retried', 'attempt': failure_count + 1, 'queue': source_queue}
                else:
                    logger.warning(f"No target queue found for {source_queue}")

        # Strategy 4: Try fallback scraper (only for playwright failures)
        elif failure_count < _config['MAX_RETRY_ATTEMPTS'] + 2 and source_queue == 'playwright':
            success = try_fallback_scraper(message)
            if success:
                return {'status': 'fallback', 'scraper': 'simple', 'queue': source_queue}

        # Strategy 5: Permanent failure - save for manual review
        logger.warning(f"Permanent failure after {failure_count} attempts")
        save_to_manual_review(message, f"Failed after {failure_count} retry attempts")
        send_alert(message, f"Exceeded {_config['MAX_RETRY_ATTEMPTS']} retry attempts")

        return {'status': 'manual_review', 'failure_count': failure_count, 'queue': source_queue}

    except Exception as e:
        logger.error(f"Error processing DLQ message: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e), 'queue': source_queue}


def lambda_handler(event, context):
    """
    Main Lambda handler - process DLQ messages

    Triggered by: SQS DLQ events (all DLQs route here)

    Returns:
        dict: Summary of processing results
    """
    # Lazy initialization (first invocation only)
    _ensure_initialized()

    logger.info(f"📨 Received {len(event['Records'])} DLQ message(s)")

    results = {
        'retried': 0,
        'fallback': 0,
        'manual_review': 0,
        'errors': 0
    }

    for record in event['Records']:
        try:
            # Determine source queue from event source ARN
            source_arn = record['eventSourceARN']
            source_queue = determine_source_queue(source_arn)

            # Process message with intelligent retry strategies
            result = process_dlq_message(record, source_queue)

            # Update results counters
            status = result.get('status', 'error')
            results[status] = results.get(status, 0) + 1

            logger.info(f"Message processed: {json.dumps(result)}")

        except Exception as e:
            logger.error(f"Error processing record: {e}", exc_info=True)
            results['errors'] += 1

    logger.info(f"✅ DLQ processing complete: {results}")

    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
