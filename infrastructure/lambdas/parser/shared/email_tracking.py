"""
Email Tracking - Pipeline Observability

Tracks email processing through the entire pipeline to answer:
- "Where is this email right now?"
- "How long has it been in the current stage?"
- "Which emails are stuck?"

Stage flow:
    producer → parser → enricher → playwright → completed
                  ↓
                scraper → completed

Usage:
    from email_tracking import track_stage_transition, get_email_status

    # Mark email entering parser
    track_stage_transition(
        idempotency_key='abc123',
        stage='parser',
        ticker='EPRT',
        subject='Essential Properties Announces...',
        queue_url='https://sqs...parser-queue',
        message_id='sqs-msg-456'
    )

    # Check where email is
    status = get_email_status('abc123')
    # Returns: {'stage': 'parser', 'updated_at': '2026-03-14T10:30:00Z', ...}
"""

import boto3
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# DynamoDB client
dynamodb = boto3.resource('dynamodb')
TRACKING_TABLE = os.environ.get('EMAIL_TRACKING_TABLE', 'reitsheet-email-tracking')
tracking_table = dynamodb.Table(TRACKING_TABLE)

# Stage constants
STAGE_PRODUCER = 'producer'
STAGE_PARSER = 'parser'
STAGE_ENRICHER = 'enricher'
STAGE_PLAYWRIGHT = 'playwright'
STAGE_SCRAPER = 'scraper'
STAGE_COMPLETED = 'completed'
STAGE_FAILED = 'failed'

# TTL: 90 days (auto-delete old entries)
TTL_DAYS = 90


def track_stage_transition(
    idempotency_key: str,
    stage: str,
    ticker: Optional[str] = None,
    subject: Optional[str] = None,
    queue_url: Optional[str] = None,
    message_id: Optional[str] = None,
    error_message: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> bool:
    """
    Track email transition to a new stage

    Args:
        idempotency_key: Unique email identifier
        stage: Current stage (producer, parser, enricher, playwright, completed, failed)
        ticker: Company ticker (if known)
        subject: Email subject
        queue_url: SQS queue URL (if queued)
        message_id: SQS message ID (if queued)
        error_message: Error message (if failed)
        metadata: Additional metadata dict

    Returns:
        bool: Success

    Example:
        track_stage_transition(
            idempotency_key='abc123',
            stage='enricher',
            ticker='PK',
            subject='Park Hotels Announces...',
            queue_url='https://sqs.../enrich-queue',
            message_id='sqs-msg-789'
        )
    """
    try:
        now = datetime.now(timezone.utc)
        ttl_timestamp = int((now + timedelta(days=TTL_DAYS)).timestamp())

        item = {
            'idempotency_key': idempotency_key,
            'stage': stage,
            'updated_at': now.isoformat(),
            'ttl': ttl_timestamp
        }

        # Add optional fields if provided
        if ticker:
            item['ticker'] = ticker
        if subject:
            item['subject'] = subject
        if queue_url:
            item['queue_url'] = queue_url
        if message_id:
            item['message_id'] = message_id
        if error_message:
            item['error_message'] = error_message
        if metadata:
            item['metadata'] = metadata

        tracking_table.put_item(Item=item)
        logger.debug(f"✓ Tracked {idempotency_key} → {stage}")
        return True

    except Exception as e:
        # Non-blocking: Don't fail email processing if tracking fails
        logger.error(f"Error tracking {idempotency_key}: {e}")
        return False


def get_email_status(idempotency_key: str) -> Optional[Dict]:
    """
    Get current status of an email

    Args:
        idempotency_key: Unique email identifier

    Returns:
        Dict with stage, updated_at, ticker, etc. or None if not found

    Example:
        status = get_email_status('abc123')
        if status:
            print(f"Email is in {status['stage']} stage")
            print(f"Last updated: {status['updated_at']}")
    """
    try:
        response = tracking_table.get_item(Key={'idempotency_key': idempotency_key})
        return response.get('Item')

    except Exception as e:
        logger.error(f"Error getting status for {idempotency_key}: {e}")
        return None


def find_emails_by_ticker(ticker: str, hours: int = 24) -> List[Dict]:
    """
    Find all emails for a ticker in the last N hours

    Args:
        ticker: Company ticker
        hours: Look back hours (default: 24)

    Returns:
        List of tracking entries

    Example:
        emails = find_emails_by_ticker('EPRT', hours=48)
        for email in emails:
            print(f"{email['subject']} - {email['stage']}")
    """
    try:
        from boto3.dynamodb.conditions import Key

        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        response = tracking_table.query(
            IndexName='ticker-updated-index',
            KeyConditionExpression=Key('ticker').eq(ticker) & Key('updated_at').gte(cutoff_time),
            ScanIndexForward=False  # Most recent first
        )

        return response.get('Items', [])

    except Exception as e:
        logger.error(f"Error finding emails for {ticker}: {e}")
        return []


def find_stale_emails(stage: str, threshold_minutes: int = 60) -> List[Dict]:
    """
    Find emails stuck in a stage for longer than threshold

    Args:
        stage: Stage to check (parser, enricher, playwright, etc.)
        threshold_minutes: Alert threshold in minutes (default: 60)

    Returns:
        List of stale tracking entries

    Example:
        stale = find_stale_emails('enricher', threshold_minutes=30)
        if stale:
            print(f"WARNING: {len(stale)} emails stuck in enricher for >30 min")
    """
    try:
        from boto3.dynamodb.conditions import Key

        cutoff_time = (datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)).isoformat()

        response = tracking_table.query(
            IndexName='stage-updated-index',
            KeyConditionExpression=Key('stage').eq(stage) & Key('updated_at').lte(cutoff_time)
        )

        return response.get('Items', [])

    except Exception as e:
        logger.error(f"Error finding stale emails in {stage}: {e}")
        return []


def get_pipeline_stats() -> Dict[str, int]:
    """
    Get count of emails in each stage (last 24 hours)

    Returns:
        Dict with stage counts

    Example:
        stats = get_pipeline_stats()
        print(f"Parser: {stats['parser']}, Enricher: {stats['enricher']}")
    """
    try:
        from boto3.dynamodb.conditions import Attr

        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        # Scan with filter (not ideal for production scale, but OK for stats)
        response = tracking_table.scan(
            FilterExpression=Attr('updated_at').gte(cutoff_time)
        )

        items = response.get('Items', [])

        # Count by stage
        stats = {}
        for item in items:
            stage = item.get('stage', 'unknown')
            stats[stage] = stats.get(stage, 0) + 1

        return stats

    except Exception as e:
        logger.error(f"Error getting pipeline stats: {e}")
        return {}


# Convenience functions for each stage
def track_producer(idempotency_key: str, ticker: str, subject: str):
    """Track email entering producer stage"""
    return track_stage_transition(
        idempotency_key=idempotency_key,
        stage=STAGE_PRODUCER,
        ticker=ticker,
        subject=subject
    )


def track_parser(idempotency_key: str, ticker: str, subject: str, queue_url: str, message_id: str):
    """Track email entering parser stage"""
    return track_stage_transition(
        idempotency_key=idempotency_key,
        stage=STAGE_PARSER,
        ticker=ticker,
        subject=subject,
        queue_url=queue_url,
        message_id=message_id
    )


def track_enricher(idempotency_key: str, ticker: str, subject: str, queue_url: str, message_id: str):
    """Track email entering enricher stage"""
    return track_stage_transition(
        idempotency_key=idempotency_key,
        stage=STAGE_ENRICHER,
        ticker=ticker,
        subject=subject,
        queue_url=queue_url,
        message_id=message_id
    )


def track_playwright(idempotency_key: str, ticker: str, subject: str, queue_url: str, message_id: str):
    """Track email entering playwright stage"""
    return track_stage_transition(
        idempotency_key=idempotency_key,
        stage=STAGE_PLAYWRIGHT,
        ticker=ticker,
        subject=subject,
        queue_url=queue_url,
        message_id=message_id
    )


def track_completed(idempotency_key: str, ticker: str, url: str):
    """Track email successfully processed and saved to DynamoDB"""
    return track_stage_transition(
        idempotency_key=idempotency_key,
        stage=STAGE_COMPLETED,
        ticker=ticker,
        metadata={'saved_url': url}
    )


def track_failed(idempotency_key: str, ticker: str, error_message: str, stage: str):
    """Track email processing failure"""
    return track_stage_transition(
        idempotency_key=idempotency_key,
        stage=STAGE_FAILED,
        ticker=ticker,
        error_message=error_message,
        metadata={'failed_at_stage': stage}
    )
