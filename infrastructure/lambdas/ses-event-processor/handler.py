"""
SES Event Processor Lambda - Processes email events from SNS

Handles SES events (Send, Delivery, Bounce, Complaint, Open, Click) and updates:
  1. reitsheet-email-events - Immutable event log (append-only)
  2. reitsheet-campaigns - Aggregate campaign metrics (atomic increments)
  3. reitsheet-subscriber-engagement - Per-subscriber engagement stats
  4. reitsheet-subscribers - Marks bounced/complained subscribers

Uses boto3.resource('dynamodb') per project conventions (auto-deserializes).

Event Flow:
  SES -> SNS Topic -> This Lambda -> DynamoDB (4 tables)
"""

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================

_initialized = False
_tables = {}


def _ensure_initialized():
    """Lazy initialization of AWS clients and DynamoDB tables."""
    global _initialized, _tables

    if _initialized:
        return

    import boto3

    dynamodb = boto3.resource('dynamodb')

    _tables['email_events'] = dynamodb.Table(os.environ['EMAIL_EVENTS_TABLE'])
    _tables['campaigns'] = dynamodb.Table(os.environ['CAMPAIGNS_TABLE'])
    _tables['subscriber_engagement'] = dynamodb.Table(os.environ['SUBSCRIBER_ENGAGEMENT_TABLE'])
    _tables['subscribers'] = dynamodb.Table(os.environ['SUBSCRIBERS_TABLE'])

    _initialized = True


def _email_events_table():
    return _tables['email_events']


def _campaigns_table():
    return _tables['campaigns']


def _subscriber_engagement_table():
    return _tables['subscriber_engagement']


def _subscribers_table():
    return _tables['subscribers']


# ============================================================================
# Constants
# ============================================================================

# TTL: 2 years in seconds
TTL_SECONDS = 2 * 365 * 24 * 60 * 60  # ~63,072,000 seconds

# Event types we handle
EVENT_TYPES = {
    'Send', 'Delivery', 'Bounce', 'Complaint', 'Open', 'Click',
    'Subscription',  # For List-Unsubscribe events
}

# Segment thresholds (engagement score)
SEGMENT_THRESHOLDS = {
    'highly_engaged': 80,
    'engaged': 40,
    'at_risk': 10,
    # Below 10 = inactive
}


# ============================================================================
# Utility Functions
# ============================================================================

def hash_email(email: str) -> str:
    """
    Hash email address with SHA256 for privacy.

    The events table stores hashed emails to allow queries without
    exposing PII in the audit log.
    """
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def get_ttl_timestamp() -> int:
    """
    Get TTL timestamp (2 years from now) as Unix epoch.

    DynamoDB TTL requires Unix timestamp in seconds.
    """
    return int(time.time()) + TTL_SECONDS


def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def extract_campaign_id(ses_event: dict) -> Optional[str]:
    """
    Extract campaign_id from SES event tags.

    SES sends tags in format: {"campaign_id": ["campaign-2026-03-27"]}
    """
    mail = ses_event.get('mail', {})
    tags = mail.get('tags', {})
    campaign_ids = tags.get('campaign_id', [])

    if campaign_ids:
        return campaign_ids[0]
    return None


def extract_email(ses_event: dict) -> Optional[str]:
    """
    Extract recipient email from SES event.

    For most events, the destination is in mail.destination.
    """
    mail = ses_event.get('mail', {})
    destinations = mail.get('destination', [])

    if destinations:
        return destinations[0].strip().lower()
    return None


def calculate_engagement_score(
    lifetime_opens: int,
    lifetime_clicks: int,
    campaigns_sent: int
) -> int:
    """
    Calculate engagement score (0-100) based on interaction rates.

    Formula: (opens_weight * open_rate + clicks_weight * click_rate)
    - Opens are weighted 40%
    - Clicks are weighted 60% (more valuable engagement)
    """
    if campaigns_sent == 0:
        return 0

    open_rate = min(lifetime_opens / campaigns_sent, 1.0)
    click_rate = min(lifetime_clicks / campaigns_sent, 1.0)

    # Weighted score: clicks are more valuable than opens
    score = int((0.4 * open_rate + 0.6 * click_rate) * 100)
    return min(score, 100)


def get_segment_from_score(engagement_score: int) -> str:
    """
    Determine subscriber segment based on engagement score.
    """
    if engagement_score >= SEGMENT_THRESHOLDS['highly_engaged']:
        return 'highly_engaged'
    elif engagement_score >= SEGMENT_THRESHOLDS['engaged']:
        return 'engaged'
    elif engagement_score >= SEGMENT_THRESHOLDS['at_risk']:
        return 'at_risk'
    else:
        return 'inactive'


# ============================================================================
# Event Logging (email-events table)
# ============================================================================

def log_event(
    event_type: str,
    campaign_id: Optional[str],
    email: Optional[str],
    ses_event: dict
) -> str:
    """
    Log event to email-events table (immutable audit log).

    Returns:
        str: The generated event_id
    """
    event_id = str(uuid.uuid4())
    timestamp = get_current_timestamp()

    item = {
        'event_id': event_id,
        'timestamp': timestamp,
        'event_type': event_type.lower(),
        'ttl': get_ttl_timestamp(),
    }

    if campaign_id:
        item['campaign_id'] = campaign_id

    if email:
        item['email_hash'] = hash_email(email)

    # Extract event-specific data
    event_data = ses_event.get(event_type.lower(), {})

    if event_type == 'Click':
        item['link_url'] = event_data.get('link', '')
        item['user_agent'] = event_data.get('userAgent', '')
    elif event_type == 'Open':
        item['user_agent'] = event_data.get('userAgent', '')
    elif event_type == 'Bounce':
        bounce_data = ses_event.get('bounce', {})
        item['bounce_type'] = bounce_data.get('bounceType', 'Unknown')
        item['bounce_sub_type'] = bounce_data.get('bounceSubType', '')
    elif event_type == 'Complaint':
        complaint_data = ses_event.get('complaint', {})
        item['complaint_type'] = complaint_data.get('complaintFeedbackType', '')

    try:
        _email_events_table().put_item(Item=item)
        logger.info(f"Logged event: {event_type} for campaign={campaign_id}")
    except Exception as e:
        logger.error(f"Failed to log event: {e}")
        raise

    return event_id


# ============================================================================
# Campaign Updates (campaigns table)
# ============================================================================

def update_campaign_metrics(
    campaign_id: str,
    event_type: str,
    email: Optional[str]
) -> None:
    """
    Update campaign aggregate metrics using atomic increments.

    For unique_opens/clicks, we use a Set to track which emails have engaged.
    This ensures we only count unique engagement per subscriber.
    """
    if not campaign_id:
        logger.warning("No campaign_id, skipping campaign metrics update")
        return

    try:
        if event_type == 'Send':
            # Increment total_sent
            _campaigns_table().update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='SET total_sent = if_not_exists(total_sent, :zero) + :inc',
                ExpressionAttributeValues={':zero': 0, ':inc': 1}
            )

        elif event_type == 'Delivery':
            _campaigns_table().update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='SET delivered = if_not_exists(delivered, :zero) + :inc',
                ExpressionAttributeValues={':zero': 0, ':inc': 1}
            )

        elif event_type == 'Bounce':
            _campaigns_table().update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='SET bounced = if_not_exists(bounced, :zero) + :inc',
                ExpressionAttributeValues={':zero': 0, ':inc': 1}
            )

        elif event_type == 'Complaint':
            _campaigns_table().update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='SET complained = if_not_exists(complained, :zero) + :inc',
                ExpressionAttributeValues={':zero': 0, ':inc': 1}
            )

        elif event_type == 'Open' and email:
            email_hash = hash_email(email)

            # Increment total_opens always
            # Add to opened_emails set for unique tracking
            try:
                _campaigns_table().update_item(
                    Key={'campaign_id': campaign_id},
                    UpdateExpression='''
                        SET total_opens = if_not_exists(total_opens, :zero) + :inc,
                            unique_opens = if_not_exists(unique_opens, :zero) + :inc
                        ADD opened_emails :email_set
                    ''',
                    ConditionExpression='NOT contains(opened_emails, :email_hash)',
                    ExpressionAttributeValues={
                        ':zero': 0,
                        ':inc': 1,
                        ':email_set': {email_hash},
                        ':email_hash': email_hash
                    }
                )
            except Exception as e:
                # If condition fails (email already in set), just increment total
                if 'ConditionalCheckFailedException' in str(type(e).__name__):
                    _campaigns_table().update_item(
                        Key={'campaign_id': campaign_id},
                        UpdateExpression='SET total_opens = if_not_exists(total_opens, :zero) + :inc',
                        ExpressionAttributeValues={':zero': 0, ':inc': 1}
                    )
                else:
                    raise

        elif event_type == 'Click' and email:
            email_hash = hash_email(email)

            # Increment total_clicks always
            # Add to clicked_emails set for unique tracking
            try:
                _campaigns_table().update_item(
                    Key={'campaign_id': campaign_id},
                    UpdateExpression='''
                        SET total_clicks = if_not_exists(total_clicks, :zero) + :inc,
                            unique_clicks = if_not_exists(unique_clicks, :zero) + :inc
                        ADD clicked_emails :email_set
                    ''',
                    ConditionExpression='NOT contains(clicked_emails, :email_hash)',
                    ExpressionAttributeValues={
                        ':zero': 0,
                        ':inc': 1,
                        ':email_set': {email_hash},
                        ':email_hash': email_hash
                    }
                )
            except Exception as e:
                # If condition fails (email already in set), just increment total
                if 'ConditionalCheckFailedException' in str(type(e).__name__):
                    _campaigns_table().update_item(
                        Key={'campaign_id': campaign_id},
                        UpdateExpression='SET total_clicks = if_not_exists(total_clicks, :zero) + :inc',
                        ExpressionAttributeValues={':zero': 0, ':inc': 1}
                    )
                else:
                    raise

        elif event_type == 'Subscription':
            # Unsubscribe event via List-Unsubscribe header
            _campaigns_table().update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='SET unsubscribed = if_not_exists(unsubscribed, :zero) + :inc',
                ExpressionAttributeValues={':zero': 0, ':inc': 1}
            )

        logger.info(f"Updated campaign metrics: {campaign_id} / {event_type}")

    except Exception as e:
        logger.error(f"Failed to update campaign metrics: {e}")
        raise


# ============================================================================
# Subscriber Engagement Updates (subscriber-engagement table)
# ============================================================================

def update_subscriber_engagement(
    email: str,
    event_type: str,
    campaign_id: Optional[str]
) -> None:
    """
    Update per-subscriber engagement metrics.

    Tracks lifetime opens/clicks and recalculates engagement score/segment.
    """
    if not email:
        return

    timestamp = get_current_timestamp()

    try:
        if event_type == 'Send':
            # Increment lifetime_sends
            _subscriber_engagement_table().update_item(
                Key={'email': email},
                UpdateExpression='''
                    SET lifetime_sends = if_not_exists(lifetime_sends, :zero) + :inc,
                        last_send_at = :ts
                ''',
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':inc': 1,
                    ':ts': timestamp
                }
            )

        elif event_type == 'Open':
            # Get current stats to calculate new score
            response = _subscriber_engagement_table().get_item(Key={'email': email})
            item = response.get('Item', {})

            current_opens = int(item.get('lifetime_opens', 0))
            current_clicks = int(item.get('lifetime_clicks', 0))
            current_sends = int(item.get('lifetime_sends', 1))

            new_opens = current_opens + 1
            new_score = calculate_engagement_score(new_opens, current_clicks, current_sends)
            new_segment = get_segment_from_score(new_score)

            # Build campaigns_opened list (last 10)
            campaigns_opened = list(item.get('campaigns_opened', []))
            if campaign_id and campaign_id not in campaigns_opened:
                campaigns_opened.append(campaign_id)
                campaigns_opened = campaigns_opened[-10:]  # Keep last 10

            update_expr = '''
                SET lifetime_opens = :opens,
                    last_open_at = :ts,
                    engagement_score = :score,
                    segment = :segment
            '''
            expr_values = {
                ':opens': new_opens,
                ':ts': timestamp,
                ':score': new_score,
                ':segment': new_segment
            }

            # Set first_engaged_at if not already set
            if 'first_engaged_at' not in item:
                update_expr += ', first_engaged_at = :first_ts'
                expr_values[':first_ts'] = timestamp

            if campaigns_opened:
                update_expr += ', campaigns_opened = :campaigns'
                expr_values[':campaigns'] = campaigns_opened

            _subscriber_engagement_table().update_item(
                Key={'email': email},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )

        elif event_type == 'Click':
            # Get current stats to calculate new score
            response = _subscriber_engagement_table().get_item(Key={'email': email})
            item = response.get('Item', {})

            current_opens = int(item.get('lifetime_opens', 0))
            current_clicks = int(item.get('lifetime_clicks', 0))
            current_sends = int(item.get('lifetime_sends', 1))

            new_clicks = current_clicks + 1
            new_score = calculate_engagement_score(current_opens, new_clicks, current_sends)
            new_segment = get_segment_from_score(new_score)

            update_expr = '''
                SET lifetime_clicks = :clicks,
                    last_click_at = :ts,
                    engagement_score = :score,
                    segment = :segment
            '''
            expr_values = {
                ':clicks': new_clicks,
                ':ts': timestamp,
                ':score': new_score,
                ':segment': new_segment
            }

            # Set first_engaged_at if not already set
            if 'first_engaged_at' not in item:
                update_expr += ', first_engaged_at = :first_ts'
                expr_values[':first_ts'] = timestamp

            _subscriber_engagement_table().update_item(
                Key={'email': email},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )

        logger.info(f"Updated subscriber engagement: {email} / {event_type}")

    except Exception as e:
        logger.error(f"Failed to update subscriber engagement for {email}: {e}")
        raise


# ============================================================================
# Subscriber Status Updates (subscribers table)
# ============================================================================

def update_subscriber_status(
    email: str,
    event_type: str,
    ses_event: dict
) -> None:
    """
    Update subscriber status on bounce/complaint.

    - Hard bounces -> status='bounced'
    - Complaints -> status='complained'
    - List-Unsubscribe -> status='unsubscribed'
    """
    if not email:
        return

    timestamp = get_current_timestamp()
    new_status = None

    if event_type == 'Bounce':
        bounce_data = ses_event.get('bounce', {})
        bounce_type = bounce_data.get('bounceType', '')

        # Only mark as bounced for permanent bounces
        if bounce_type == 'Permanent':
            new_status = 'bounced'

    elif event_type == 'Complaint':
        new_status = 'complained'

    elif event_type == 'Subscription':
        # List-Unsubscribe event
        new_status = 'unsubscribed'

    if new_status:
        try:
            _subscribers_table().update_item(
                Key={'email': email},
                UpdateExpression=f'''
                    SET #status = :status,
                        {new_status}_at = :ts
                ''',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': new_status,
                    ':ts': timestamp
                }
            )
            logger.info(f"Updated subscriber status: {email} -> {new_status}")
        except Exception as e:
            logger.error(f"Failed to update subscriber status for {email}: {e}")
            raise


# ============================================================================
# Event Processing
# ============================================================================

def process_ses_event(ses_event: dict) -> None:
    """
    Process a single SES event.

    Updates all relevant tables based on event type.
    """
    event_type = ses_event.get('eventType', '')

    if event_type not in EVENT_TYPES:
        logger.warning(f"Unknown event type: {event_type}")
        return

    campaign_id = extract_campaign_id(ses_event)
    email = extract_email(ses_event)

    logger.info(f"Processing {event_type} event for campaign={campaign_id}, email={email[:20] if email else None}...")

    # 1. Log to immutable event log
    log_event(event_type, campaign_id, email, ses_event)

    # 2. Update campaign aggregate metrics
    if campaign_id:
        update_campaign_metrics(campaign_id, event_type, email)

    # 3. Update subscriber engagement stats
    if email and event_type in ('Send', 'Open', 'Click'):
        update_subscriber_engagement(email, event_type, campaign_id)

    # 4. Update subscriber status on bounce/complaint/unsubscribe
    if email and event_type in ('Bounce', 'Complaint', 'Subscription'):
        update_subscriber_status(email, event_type, ses_event)


# ============================================================================
# Lambda Handler
# ============================================================================

def lambda_handler(event, context):
    """
    Main Lambda handler for SES events from SNS.

    SNS delivers events as records with Message containing the SES event JSON.
    """
    _ensure_initialized()

    records = event.get('Records', [])
    logger.info(f"Processing {len(records)} SNS records")

    failed_records = []

    for i, record in enumerate(records):
        try:
            # SNS wraps the message in a 'Sns' object
            sns_message = record.get('Sns', {}).get('Message', '{}')
            ses_event = json.loads(sns_message)

            process_ses_event(ses_event)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SNS message {i}: {e}")
            failed_records.append(record)
        except Exception as e:
            logger.error(f"Failed to process record {i}: {e}")
            failed_records.append(record)

    # Log summary
    success_count = len(records) - len(failed_records)
    logger.info(f"Processed {success_count}/{len(records)} events successfully")

    if failed_records:
        # Return partial failure for SNS to retry
        logger.warning(f"{len(failed_records)} records failed processing")
        # For SNS, we don't have batch failure reporting like SQS
        # The entire batch either succeeds or fails
        # Log details but don't raise to allow successful events to complete

    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': success_count,
            'failed': len(failed_records)
        })
    }
