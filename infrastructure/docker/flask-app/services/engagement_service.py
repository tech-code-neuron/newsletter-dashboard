"""
Engagement Service - Business Logic for Subscriber Engagement Tracking

Handles:
    - Subscriber engagement metrics
    - Open/click event processing
    - Engagement-based segmentation
    - Inactive subscriber detection

SOLID Principles:
    - Single Responsibility: Engagement tracking only
    - Dependency Injection: DynamoDB tables injected for testability
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Configuration
from config.aws_config import aws_config

ENGAGEMENT_TABLE = os.environ.get('ENGAGEMENT_TABLE', 'reitsheet-subscriber-engagement')
SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE', 'reitsheet-subscribers')
EMAIL_EVENTS_TABLE = os.environ.get('EMAIL_EVENTS_TABLE', 'reitsheet-email-events')

# Engagement segment thresholds
SEGMENT_THRESHOLDS = {
    'highly_engaged': 80,   # Engagement score >= 80
    'engaged': 50,          # Engagement score >= 50
    'passive': 20,          # Engagement score >= 20
    'at_risk': 0            # Engagement score < 20
}


class EngagementService:
    """Service for tracking and analyzing subscriber engagement."""

    def __init__(self, dynamodb=None):
        """
        Initialize with optional DynamoDB resource.

        Args:
            dynamodb: boto3 DynamoDB resource (defaults to production)
        """
        import boto3
        self.dynamodb = dynamodb or boto3.resource('dynamodb', region_name=aws_config.aws_region)
        self.engagement_table = self.dynamodb.Table(ENGAGEMENT_TABLE)
        self.subscribers_table = self.dynamodb.Table(SUBSCRIBERS_TABLE)
        self.events_table = self.dynamodb.Table(EMAIL_EVENTS_TABLE)

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_subscriber_engagement(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get engagement metrics for a subscriber.

        Args:
            email: Subscriber email address

        Returns:
            Engagement dict or None if not found
        """
        try:
            response = self.engagement_table.get_item(
                Key={'email': email.lower().strip()}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting engagement for {email[:3]}***: {e}")
            return None

    def get_subscribers_by_segment(
        self,
        segment: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get subscribers in a specific engagement segment.

        Args:
            segment: Segment name ('highly_engaged', 'engaged', 'passive', 'at_risk', 'new')
            limit: Maximum subscribers to return

        Returns:
            List of engagement records for subscribers in the segment
        """
        try:
            # Scan with filter (consider GSI for production scale)
            response = self.engagement_table.scan(
                FilterExpression='segment = :segment',
                ExpressionAttributeValues={':segment': segment},
                Limit=limit * 2  # Fetch extra for filtering
            )

            items = response.get('Items', [])

            # Sort by engagement_score descending
            items.sort(
                key=lambda x: int(x.get('engagement_score', 0)),
                reverse=True
            )

            return items[:limit]

        except Exception as e:
            logger.error(f"Error getting subscribers by segment {segment}: {e}")
            return []

    def get_inactive_subscribers(
        self,
        days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Get subscribers who haven't engaged in specified number of days.

        Args:
            days: Days of inactivity threshold

        Returns:
            List of inactive subscriber engagement records
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            # Scan for subscribers with last_opened_at before cutoff
            # or those who have never opened
            response = self.engagement_table.scan(
                FilterExpression='(last_opened_at < :cutoff) OR (attribute_not_exists(last_opened_at) AND created_at < :cutoff)',
                ExpressionAttributeValues={':cutoff': cutoff}
            )

            items = response.get('Items', [])

            # Sort by last activity (oldest first)
            items.sort(
                key=lambda x: x.get('last_opened_at', x.get('created_at', '')),
                reverse=False
            )

            return items

        except Exception as e:
            logger.error(f"Error getting inactive subscribers: {e}")
            return []

    # =========================================================================
    # Event Processing
    # =========================================================================

    def update_engagement_on_open(
        self,
        email: str,
        campaign_id: str
    ) -> None:
        """
        Update engagement metrics when subscriber opens an email.

        Args:
            email: Subscriber email
            campaign_id: Campaign that was opened
        """
        now = datetime.now(timezone.utc).isoformat()
        email_normalized = email.lower().strip()

        try:
            # Update engagement record with atomic increments
            self.engagement_table.update_item(
                Key={'email': email_normalized},
                UpdateExpression='''
                    SET lifetime_opens = if_not_exists(lifetime_opens, :zero) + :one,
                        last_opened_at = :now,
                        last_campaign_opened = :campaign,
                        updated_at = :now
                    ADD campaigns_opened :campaign_set
                ''',
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':one': 1,
                    ':now': now,
                    ':campaign': campaign_id,
                    ':campaign_set': {campaign_id}
                }
            )

            # Recalculate segment
            self.recalculate_segment(email_normalized)

            logger.debug(f"Updated engagement on open for {email_normalized[:3]}***")

        except Exception as e:
            logger.error(f"Error updating engagement on open: {e}")

    def update_engagement_on_click(
        self,
        email: str,
        campaign_id: str,
        link_url: str
    ) -> None:
        """
        Update engagement metrics when subscriber clicks a link.

        Args:
            email: Subscriber email
            campaign_id: Campaign containing the clicked link
            link_url: URL that was clicked
        """
        now = datetime.now(timezone.utc).isoformat()
        email_normalized = email.lower().strip()

        try:
            # Update engagement record
            self.engagement_table.update_item(
                Key={'email': email_normalized},
                UpdateExpression='''
                    SET lifetime_clicks = if_not_exists(lifetime_clicks, :zero) + :one,
                        last_clicked_at = :now,
                        last_campaign_clicked = :campaign,
                        last_link_clicked = :link,
                        updated_at = :now
                    ADD campaigns_clicked :campaign_set
                ''',
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':one': 1,
                    ':now': now,
                    ':campaign': campaign_id,
                    ':link': link_url,
                    ':campaign_set': {campaign_id}
                }
            )

            # Recalculate segment
            self.recalculate_segment(email_normalized)

            logger.debug(f"Updated engagement on click for {email_normalized[:3]}***")

        except Exception as e:
            logger.error(f"Error updating engagement on click: {e}")

    def update_engagement_on_send(self, email: str) -> None:
        """
        Update engagement metrics when an email is sent to subscriber.

        Args:
            email: Subscriber email
        """
        now = datetime.now(timezone.utc).isoformat()
        email_normalized = email.lower().strip()

        try:
            self.engagement_table.update_item(
                Key={'email': email_normalized},
                UpdateExpression='''
                    SET lifetime_sends = if_not_exists(lifetime_sends, :zero) + :one,
                        last_sent_at = :now,
                        updated_at = :now
                ''',
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':one': 1,
                    ':now': now
                }
            )
        except Exception as e:
            logger.error(f"Error updating engagement on send: {e}")

    # =========================================================================
    # Segmentation
    # =========================================================================

    def recalculate_segment(self, email: str) -> str:
        """
        Recalculate engagement segment for a subscriber.

        Engagement score formula:
        - Base: (opens / sends) * 50 + (clicks / opens) * 50
        - Recency bonus: +20 if active in last 30 days
        - Recency penalty: -20 if no activity in 60+ days

        Args:
            email: Subscriber email

        Returns:
            New segment name
        """
        email_normalized = email.lower().strip()

        try:
            engagement = self.get_subscriber_engagement(email_normalized)
            if not engagement:
                return 'new'

            # Extract metrics
            lifetime_sends = int(engagement.get('lifetime_sends', 0) or 0)
            lifetime_opens = int(engagement.get('lifetime_opens', 0) or 0)
            lifetime_clicks = int(engagement.get('lifetime_clicks', 0) or 0)

            # Calculate base score
            if lifetime_sends == 0:
                score = 0
            else:
                open_rate = lifetime_opens / lifetime_sends
                click_rate = (lifetime_clicks / lifetime_opens) if lifetime_opens > 0 else 0
                score = (open_rate * 50) + (click_rate * 50)

            # Apply recency adjustments
            now = datetime.now(timezone.utc)
            last_opened = engagement.get('last_opened_at')

            if last_opened:
                try:
                    last_opened_dt = datetime.fromisoformat(last_opened.replace('Z', '+00:00'))
                    days_since_open = (now - last_opened_dt).days

                    if days_since_open <= 30:
                        score += 20  # Recency bonus
                    elif days_since_open >= 60:
                        score -= 20  # Recency penalty
                except Exception:
                    pass

            # Clamp score to 0-100
            score = max(0, min(100, score))

            # Determine segment
            if score >= SEGMENT_THRESHOLDS['highly_engaged']:
                segment = 'highly_engaged'
            elif score >= SEGMENT_THRESHOLDS['engaged']:
                segment = 'engaged'
            elif score >= SEGMENT_THRESHOLDS['passive']:
                segment = 'passive'
            else:
                segment = 'at_risk'

            # Update engagement record
            self.engagement_table.update_item(
                Key={'email': email_normalized},
                UpdateExpression='SET engagement_score = :score, segment = :segment, updated_at = :now',
                ExpressionAttributeValues={
                    ':score': int(score),
                    ':segment': segment,
                    ':now': datetime.now(timezone.utc).isoformat()
                }
            )

            return segment

        except Exception as e:
            logger.error(f"Error recalculating segment for {email_normalized[:3]}***: {e}")
            return 'unknown'

    def get_segment_counts(self) -> Dict[str, int]:
        """
        Get count of subscribers in each engagement segment.

        Returns:
            Dict with segment counts
        """
        try:
            response = self.engagement_table.scan(
                ProjectionExpression='segment'
            )

            items = response.get('Items', [])
            counts = {
                'highly_engaged': 0,
                'engaged': 0,
                'passive': 0,
                'at_risk': 0,
                'new': 0,
                'unknown': 0
            }

            for item in items:
                segment = item.get('segment', 'unknown')
                if segment in counts:
                    counts[segment] += 1
                else:
                    counts['unknown'] += 1

            counts['total'] = len(items)
            return counts

        except Exception as e:
            logger.error(f"Error getting segment counts: {e}")
            return {}

    # =========================================================================
    # Engagement Record Management
    # =========================================================================

    def initialize_engagement(
        self,
        email: str,
        source: str = 'signup'
    ) -> Dict[str, Any]:
        """
        Create initial engagement record for new subscriber.

        Args:
            email: Subscriber email
            source: Signup source

        Returns:
            Created engagement record
        """
        now = datetime.now(timezone.utc).isoformat()
        email_normalized = email.lower().strip()

        item = {
            'email': email_normalized,
            'lifetime_sends': 0,
            'lifetime_opens': 0,
            'lifetime_clicks': 0,
            'engagement_score': 0,
            'segment': 'new',
            'source': source,
            'campaigns_opened': set(),
            'campaigns_clicked': set(),
            'created_at': now,
            'updated_at': now
        }

        try:
            self.engagement_table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(email)'
            )
            logger.info(f"Initialized engagement for {email_normalized[:3]}***")
            return item
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # Record already exists
            return self.get_subscriber_engagement(email_normalized)
        except Exception as e:
            logger.error(f"Error initializing engagement: {e}")
            raise

    def delete_engagement(self, email: str) -> bool:
        """
        Delete engagement record (for GDPR compliance).

        Args:
            email: Subscriber email

        Returns:
            True if successful
        """
        try:
            self.engagement_table.delete_item(
                Key={'email': email.lower().strip()}
            )
            logger.info(f"Deleted engagement for {email[:3]}***")
            return True
        except Exception as e:
            logger.error(f"Error deleting engagement: {e}")
            return False


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_engagement_service() -> EngagementService:
    """
    Get or create engagement service instance (singleton).

    Returns:
        EngagementService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = EngagementService()
    return _service_instance
