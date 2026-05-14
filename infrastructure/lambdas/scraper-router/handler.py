"""
Scraper Router Lambda
=====================
Reads company config from DynamoDB and routes to appropriate scraper

Routing logic:
    - scraper_type: "simple_http" → Simple Scraper Queue
    - scraper_type: "playwright" → Playwright Queue
    - scraper_type: "api" → API Scraper Queue

SOLID: Single Responsibility - Only routes based on config
Last Updated: 2026-03-09
"""

import json
import logging
import boto3
import os

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

    # Environment Variables
    _config['SIMPLE_SCRAPER_QUEUE_URL'] = os.environ['SIMPLE_SCRAPER_QUEUE_URL']
    _config['PLAYWRIGHT_QUEUE_URL'] = os.environ['PLAYWRIGHT_QUEUE_URL']
    _config['API_SCRAPER_QUEUE_URL'] = os.environ.get('API_SCRAPER_QUEUE_URL', '')
    _config['COMPANIES_TABLE'] = os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config')
    _config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', 'INFO')

    # Logging
    logger.setLevel(getattr(logging, _config['LOG_LEVEL']))

    # DynamoDB Tables
    _tables['companies_config'] = _clients['dynamodb'].Table(_config['COMPANIES_TABLE'])

    # Queue mapping (Strategy Pattern)
    _config['SCRAPER_QUEUES'] = {
        'simple_http': _config['SIMPLE_SCRAPER_QUEUE_URL'],
        'playwright': _config['PLAYWRIGHT_QUEUE_URL'],
        'api': _config['API_SCRAPER_QUEUE_URL']
    }

    _initialized = True


def _sqs():
    return _clients['sqs']


def _companies_config_table():
    return _tables['companies_config']


def get_scraper_type(ticker):
    """
    Get scraper type for company from DynamoDB config

    Single Responsibility: Only reads config

    Returns:
        str: scraper_type ('simple_http', 'playwright', 'api')
    """
    try:
        response = _companies_config_table().get_item(Key={'ticker': ticker})

        if 'Item' not in response:
            logger.warning(f"No config for {ticker}, defaulting to simple_http")
            return 'simple_http'

        company = response['Item']
        scraper_type = company.get('scraper_type', 'simple_http')

        logger.info(f"✓ {ticker} → {scraper_type} scraper")
        return scraper_type

    except Exception as e:
        logger.error(f"Error getting scraper type for {ticker}: {e}")
        return 'simple_http'  # Safe default


def route_to_scraper(job, scraper_type):
    """
    Route job to appropriate scraper queue

    Single Responsibility: Only routes messages

    Returns:
        bool: Success
    """
    queue_url = _config['SCRAPER_QUEUES'].get(scraper_type)

    if not queue_url:
        logger.error(f"No queue configured for scraper_type: {scraper_type}")
        return False

    try:
        _sqs().send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(job)
        )

        logger.info(f"✓ Routed to {scraper_type} queue")
        return True

    except Exception as e:
        logger.error(f"Error routing to {scraper_type} queue: {e}")
        return False


def process_routing_job(job):
    """
    Process one routing job

    Orchestrates: Get config → Route to scraper
    """
    ticker = job.get('ticker', 'UNKNOWN')

    # Step 1: Get scraper type from config
    scraper_type = get_scraper_type(ticker)

    # Step 2: Route to appropriate scraper
    success = route_to_scraper(job, scraper_type)

    return {
        'success': success,
        'ticker': ticker,
        'scraper_type': scraper_type
    }


def lambda_handler(event, context):
    """
    Main Lambda handler - route scraping jobs to appropriate scraper

    Message format:
    {
        "url": "https://...",
        "ticker": "EPRT",
        "email_subject": "...",
        "idempotency_key": "abc123"
    }
    """
    # Lazy initialization (first invocation only)
    _ensure_initialized()

    logger.info(f"📨 Received {len(event['Records'])} routing job(s)")

    results = {
        'routed': 0,
        'failed': 0,
        'by_scraper_type': {}
    }

    for record in event['Records']:
        try:
            job = json.loads(record['body'])
            result = process_routing_job(job)

            if result['success']:
                results['routed'] += 1
            else:
                results['failed'] += 1

            # Track by scraper type
            scraper_type = result.get('scraper_type', 'unknown')
            results['by_scraper_type'][scraper_type] = results['by_scraper_type'].get(scraper_type, 0) + 1

        except Exception as e:
            logger.error(f"Error routing job: {e}", exc_info=True)
            results['failed'] += 1

    logger.info(f"✅ Routing complete: {results}")

    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
