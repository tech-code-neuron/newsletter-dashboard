"""
Enricher - Queue Operations
============================
Send messages to scraper queue

SOLID Principles:
- Single Responsibility: Only handles queue operations
- Dependency Injection: SQS client can be injected for testing

Last Created: 2026-03-11
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger()

# Module-level SQS client (set by initialize_sqs)
SQS_CLIENT = None
SCRAPE_QUEUE_URL = None


def initialize_sqs(sqs_client, scrape_queue_url: str):
    """
    Initialize SQS client and queue URL

    Single Responsibility: Only initializes SQS

    Args:
        sqs_client: Boto3 SQS client
        scrape_queue_url: Scrape queue URL
    """
    global SQS_CLIENT, SCRAPE_QUEUE_URL
    SQS_CLIENT = sqs_client
    SCRAPE_QUEUE_URL = scrape_queue_url
    logger.info("SQS client initialized")


def queue_for_scraping(url: str, metadata: Dict[str, Any]) -> bool:
    """
    Queue URL for scraping

    Single Responsibility: Only queues messages

    Args:
        url: URL to scrape
        metadata: Metadata dict

    Returns:
        bool: Success
    """
    if not SQS_CLIENT or not SCRAPE_QUEUE_URL:
        logger.error("SQS not initialized")
        return False

    try:
        message = {
            'url': url,
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'email_subject': metadata.get('subject', ''),
            'idempotency_key': metadata['idempotency_key'],
            'queued_at': datetime.utcnow().isoformat()
        }

        response = SQS_CLIENT.send_message(
            QueueUrl=SCRAPE_QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        logger.info(f"✓ Queued for scraping: {url[:60]}... (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for scraping: {e}", exc_info=True)
        return False
