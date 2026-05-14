"""
SQS Operations
==============
Single Responsibility: SQS queue operations
"""

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from config.constants import NEWSWIRE_DOMAINS

logger = logging.getLogger()


def queue_for_scraping(url, metadata, sqs_client, scrape_queue_url):
    """
    Queue URL for scraping (or Playwright job if url is None)

    Args:
        url: URL to scrape (None for Playwright jobs)
        metadata: Metadata dict
        sqs_client: Boto3 SQS client
        scrape_queue_url: SQS queue URL

    Returns:
        bool: Success
    """
    try:
        message = {
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'email_subject': metadata.get('subject', metadata.get('email_subject', '')),
            'idempotency_key': metadata['idempotency_key'],
            'queued_at': datetime.now(timezone.utc).isoformat()
        }

        # Add URL if provided (for scraper), omit for Playwright jobs
        if url:
            message['url'] = url

        # Add press_release_title if provided (for Playwright matching)
        if 'press_release_title' in metadata:
            message['press_release_title'] = metadata['press_release_title']

        # Add email_date for timestamp preservation (converts to email_received_at in Playwright)
        if 'email_date' in metadata and metadata['email_date']:
            message['email_date'] = metadata['email_date']

        # Add press_release_date if provided
        if 'press_release_date' in metadata and metadata['press_release_date']:
            message['press_release_date'] = metadata['press_release_date']

        response = sqs_client.send_message(
            QueueUrl=scrape_queue_url,
            MessageBody=json.dumps(message)
        )

        if url:
            logger.info(f"✓ Queued for scraping: {url[:60]}... (MessageId: {response['MessageId']})")
        else:
            ticker = metadata.get('ticker', 'UNKNOWN')
            logger.info(f"✓ Queued for Playwright: {ticker} (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for scraping: {e}", exc_info=True)
        return False


def classify_url(url):
    """
    Classify URL type

    Args:
        url: URL to classify

    Returns:
        str: 'newswire' or 'direct'
    """
    domain = urlparse(url).netloc.lower()

    # Remove www. prefix for consistent matching
    domain = domain.replace('www.', '')

    if any(nw in domain for nw in NEWSWIRE_DOMAINS):
        return 'newswire'
    else:
        return 'direct'


def queue_for_social_classification(url, ticker, sqs_client, classify_queue_url):
    """
    Queue a press release for social media classification.

    Called after a successful save to DynamoDB to trigger the classifier Lambda.

    Args:
        url: Press release URL (also the DynamoDB primary key)
        ticker: Company ticker symbol
        sqs_client: Boto3 SQS client
        classify_queue_url: Social classify queue URL

    Returns:
        bool: Success
    """
    try:
        message = {
            'url': url,
            'ticker': ticker,
            'queued_at': datetime.now(timezone.utc).isoformat()
        }

        response = sqs_client.send_message(
            QueueUrl=classify_queue_url,
            MessageBody=json.dumps(message)
        )

        logger.info(f"✓ Queued for classification: {ticker} (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for classification: {e}", exc_info=True)
        return False


def queue_for_manual_review(url, metadata, reason, sqs_client, dlq_url):
    """
    Queue landing page or failed URL for manual review

    Sends message to DLQ with classification='landing_page' for
    manual triage via review system.

    Args:
        url: Landing page URL
        metadata: Press release metadata dict
        reason: Human-readable reason (e.g., 'Generic segment: news-releases')
        sqs_client: Boto3 SQS client
        dlq_url: Dead Letter Queue URL

    Returns:
        bool: Success
    """
    try:
        review_message = {
            'classification': 'landing_page',
            'url': url,
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'email_subject': metadata.get('subject', metadata.get('email_subject', '')),
            'idempotency_key': metadata.get('idempotency_key', ''),
            'reason': reason,
            'queued_at': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                'press_release_date': metadata.get('press_release_date'),
                'email_date': metadata.get('email_date'),
                'construction_method': metadata.get('construction_method'),
            }
        }

        response = sqs_client.send_message(
            QueueUrl=dlq_url,
            MessageBody=json.dumps(review_message)
        )

        logger.info(
            f"✓ Queued for manual review: {metadata.get('ticker', 'UNKNOWN')} "
            f"(MessageId: {response['MessageId']})"
        )
        return True

    except Exception as e:
        logger.error(f"Error queuing for manual review: {e}", exc_info=True)
        return False
