"""
Analytics Service - Business Logic for Dashboard Aggregations

Handles:
    - Subscriber count aggregations
    - Campaign performance averages
    - List growth tracking
    - Link tracking and top links
    - Engagement distribution

SOLID Principles:
    - Single Responsibility: Analytics and reporting only
    - Dependency Injection: DynamoDB tables injected for testability
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

logger = logging.getLogger(__name__)

# Configuration
SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE', 'reitsheet-subscribers')
CAMPAIGNS_TABLE = os.environ.get('CAMPAIGNS_TABLE', 'reitsheet-campaigns')
EMAIL_EVENTS_TABLE = os.environ.get('EMAIL_EVENTS_TABLE', 'reitsheet-email-events')
ENGAGEMENT_TABLE = os.environ.get('ENGAGEMENT_TABLE', 'reitsheet-subscriber-engagement')
LINK_TRACKING_TABLE = os.environ.get('LINK_TRACKING_TABLE', 'reitsheet-link-tracking')


class AnalyticsService:
    """Service for dashboard analytics and reporting."""

    def __init__(self, dynamodb=None):
        """
        Initialize with optional DynamoDB resource.

        Args:
            dynamodb: boto3 DynamoDB resource (defaults to production)
        """
        import boto3
        from config.aws_config import aws_config
        self.dynamodb = dynamodb or boto3.resource('dynamodb', region_name=aws_config.aws_region)
        self.subscribers_table = self.dynamodb.Table(SUBSCRIBERS_TABLE)
        self.campaigns_table = self.dynamodb.Table(CAMPAIGNS_TABLE)
        self.events_table = self.dynamodb.Table(EMAIL_EVENTS_TABLE)
        self.engagement_table = self.dynamodb.Table(ENGAGEMENT_TABLE)
        self.link_tracking_table = self.dynamodb.Table(LINK_TRACKING_TABLE)

    # =========================================================================
    # Subscriber Analytics
    # =========================================================================

    def get_subscriber_counts(self) -> Dict[str, int]:
        """
        Get subscriber counts by status.

        Returns:
            Dict with counts: {verified, pending, unsubscribed, bounced, total}
        """
        try:
            counts = {
                'verified': 0,
                'pending': 0,
                'unsubscribed': 0,
                'bounced': 0,
                'total': 0
            }

            # Query each status using GSI
            for status in ['verified', 'pending', 'unsubscribed', 'bounced']:
                try:
                    response = self.subscribers_table.query(
                        IndexName='status-subscribed_at-index',
                        KeyConditionExpression='#status = :status',
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={':status': status},
                        Select='COUNT'
                    )
                    counts[status] = response.get('Count', 0)
                except Exception:
                    # GSI may not exist for all statuses
                    pass

            counts['total'] = sum(counts.values())
            return counts

        except Exception as e:
            logger.error(f"Error getting subscriber counts: {e}")
            return {'verified': 0, 'pending': 0, 'unsubscribed': 0, 'bounced': 0, 'total': 0}

    def get_list_growth(self, days: int = 30) -> Dict[str, Any]:
        """
        Get subscriber list growth metrics for the specified period.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with growth metrics: {new, unsubscribed, bounced, net, by_date}
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            # Scan for subscribers with activity in the period
            response = self.subscribers_table.scan(
                FilterExpression='subscribed_at >= :cutoff OR unsubscribed_at >= :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff}
            )

            items = response.get('Items', [])

            # Aggregate by type
            new_subscribers = 0
            unsubscribed = 0
            bounced = 0
            by_date = defaultdict(lambda: {'new': 0, 'unsubscribed': 0, 'bounced': 0})

            for item in items:
                subscribed_at = item.get('subscribed_at', '')
                unsubscribed_at = item.get('unsubscribed_at', '')
                status = item.get('status', '')

                # Count new subscribers
                if subscribed_at >= cutoff:
                    new_subscribers += 1
                    date_key = subscribed_at[:10]  # YYYY-MM-DD
                    by_date[date_key]['new'] += 1

                # Count unsubscribes
                if unsubscribed_at and unsubscribed_at >= cutoff:
                    unsubscribed += 1
                    date_key = unsubscribed_at[:10]
                    by_date[date_key]['unsubscribed'] += 1

                # Count bounces
                if status == 'bounced' and subscribed_at >= cutoff:
                    bounced += 1
                    date_key = subscribed_at[:10]
                    by_date[date_key]['bounced'] += 1

            return {
                'period_days': days,
                'new': new_subscribers,
                'unsubscribed': unsubscribed,
                'bounced': bounced,
                'net': new_subscribers - unsubscribed - bounced,
                'by_date': dict(by_date)
            }

        except Exception as e:
            logger.error(f"Error getting list growth: {e}")
            return {'period_days': days, 'new': 0, 'unsubscribed': 0, 'bounced': 0, 'net': 0, 'by_date': {}}

    # =========================================================================
    # Campaign Analytics
    # =========================================================================

    def get_campaign_averages(self, days: int = 30) -> Dict[str, float]:
        """
        Get average campaign performance metrics over the specified period.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with average rates: {open_rate, click_rate, bounce_rate, unsubscribe_rate, campaigns_analyzed}
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            # Scan for sent campaigns in the period
            response = self.campaigns_table.scan(
                FilterExpression='#status = :sent AND send_completed_at >= :cutoff',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':sent': 'sent',
                    ':cutoff': cutoff
                }
            )

            items = response.get('Items', [])

            if not items:
                return {
                    'period_days': days,
                    'campaigns_analyzed': 0,
                    'avg_open_rate': 0.0,
                    'avg_click_rate': 0.0,
                    'avg_bounce_rate': 0.0,
                    'avg_unsubscribe_rate': 0.0,
                    'avg_click_to_open_rate': 0.0
                }

            # Calculate averages
            total_open_rate = 0.0
            total_click_rate = 0.0
            total_bounce_rate = 0.0
            total_unsubscribe_rate = 0.0
            total_cto_rate = 0.0

            for campaign in items:
                sent = int(campaign.get('total_sent', 0) or 0)
                delivered = int(campaign.get('total_delivered', 0) or 0)
                opened = int(campaign.get('total_opened', 0) or 0)
                clicked = int(campaign.get('total_clicked', 0) or 0)
                bounced = int(campaign.get('total_bounced', 0) or 0)
                unsubscribed = int(campaign.get('total_unsubscribed', 0) or 0)

                if delivered > 0:
                    total_open_rate += (opened / delivered) * 100
                    total_click_rate += (clicked / delivered) * 100
                    total_unsubscribe_rate += (unsubscribed / delivered) * 100

                if sent > 0:
                    total_bounce_rate += (bounced / sent) * 100

                if opened > 0:
                    total_cto_rate += (clicked / opened) * 100

            count = len(items)
            return {
                'period_days': days,
                'campaigns_analyzed': count,
                'avg_open_rate': round(total_open_rate / count, 2),
                'avg_click_rate': round(total_click_rate / count, 2),
                'avg_bounce_rate': round(total_bounce_rate / count, 2),
                'avg_unsubscribe_rate': round(total_unsubscribe_rate / count, 2),
                'avg_click_to_open_rate': round(total_cto_rate / count, 2)
            }

        except Exception as e:
            logger.error(f"Error getting campaign averages: {e}")
            return {
                'period_days': days,
                'campaigns_analyzed': 0,
                'avg_open_rate': 0.0,
                'avg_click_rate': 0.0,
                'avg_bounce_rate': 0.0,
                'avg_unsubscribe_rate': 0.0,
                'avg_click_to_open_rate': 0.0
            }

    def get_campaign_performance_trend(
        self,
        days: int = 90,
        metric: str = 'open_rate'
    ) -> List[Dict[str, Any]]:
        """
        Get campaign performance trend over time.

        Args:
            days: Number of days to analyze
            metric: Metric to trend ('open_rate', 'click_rate', 'bounce_rate')

        Returns:
            List of {date, value} dicts for charting
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            response = self.campaigns_table.scan(
                FilterExpression='#status = :sent AND send_completed_at >= :cutoff',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':sent': 'sent',
                    ':cutoff': cutoff
                }
            )

            items = response.get('Items', [])

            # Calculate metric for each campaign
            trend_data = []
            for campaign in items:
                sent = int(campaign.get('total_sent', 0) or 0)
                delivered = int(campaign.get('total_delivered', 0) or 0)
                opened = int(campaign.get('total_opened', 0) or 0)
                clicked = int(campaign.get('total_clicked', 0) or 0)
                bounced = int(campaign.get('total_bounced', 0) or 0)

                date = campaign.get('send_completed_at', '')[:10]
                value = 0.0

                if metric == 'open_rate' and delivered > 0:
                    value = (opened / delivered) * 100
                elif metric == 'click_rate' and delivered > 0:
                    value = (clicked / delivered) * 100
                elif metric == 'bounce_rate' and sent > 0:
                    value = (bounced / sent) * 100

                trend_data.append({
                    'date': date,
                    'campaign_id': campaign.get('campaign_id'),
                    'campaign_name': campaign.get('name'),
                    'value': round(value, 2)
                })

            # Sort by date
            trend_data.sort(key=lambda x: x['date'])
            return trend_data

        except Exception as e:
            logger.error(f"Error getting campaign trend: {e}")
            return []

    # =========================================================================
    # Link Analytics
    # =========================================================================

    def get_top_links(
        self,
        campaign_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top clicked links for a campaign.

        Args:
            campaign_id: Campaign UUID
            limit: Maximum number of links to return

        Returns:
            List of link dicts with click counts, sorted by clicks descending
        """
        try:
            # Query links for the campaign
            response = self.link_tracking_table.query(
                KeyConditionExpression='campaign_id = :campaign_id',
                ExpressionAttributeValues={':campaign_id': campaign_id}
            )

            items = response.get('Items', [])

            # Sort by click count descending
            items.sort(
                key=lambda x: int(x.get('click_count', 0) or 0),
                reverse=True
            )

            # Format response
            return [
                {
                    'link_id': item.get('link_id'),
                    'url': item.get('url'),
                    'label': item.get('label', ''),
                    'click_count': int(item.get('click_count', 0) or 0),
                    'unique_clicks': int(item.get('unique_clicks', 0) or 0)
                }
                for item in items[:limit]
            ]

        except Exception as e:
            logger.error(f"Error getting top links for campaign {campaign_id}: {e}")
            return []

    def record_link_click(
        self,
        campaign_id: str,
        link_id: str,
        url: str,
        email: str,
        label: Optional[str] = None
    ) -> None:
        """
        Record a link click event.

        Args:
            campaign_id: Campaign UUID
            link_id: Link tracking ID
            url: Destination URL
            email: Subscriber email who clicked
            label: Optional link label/description
        """
        now = datetime.now(timezone.utc).isoformat()

        try:
            # Update or create link tracking record
            self.link_tracking_table.update_item(
                Key={
                    'campaign_id': campaign_id,
                    'link_id': link_id
                },
                UpdateExpression='''
                    SET click_count = if_not_exists(click_count, :zero) + :one,
                        #url = :url,
                        label = if_not_exists(label, :label),
                        last_clicked_at = :now,
                        updated_at = :now
                    ADD clickers :email_set
                ''',
                ExpressionAttributeNames={'#url': 'url'},
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':one': 1,
                    ':url': url,
                    ':label': label or '',
                    ':now': now,
                    ':email_set': {email.lower().strip()}
                }
            )

            # Update unique clicks (count of clickers set)
            response = self.link_tracking_table.get_item(
                Key={
                    'campaign_id': campaign_id,
                    'link_id': link_id
                }
            )
            item = response.get('Item', {})
            unique_count = len(item.get('clickers', set()))

            self.link_tracking_table.update_item(
                Key={
                    'campaign_id': campaign_id,
                    'link_id': link_id
                },
                UpdateExpression='SET unique_clicks = :unique',
                ExpressionAttributeValues={':unique': unique_count}
            )

        except Exception as e:
            logger.error(f"Error recording link click: {e}")

    # =========================================================================
    # Engagement Distribution
    # =========================================================================

    def get_engagement_distribution(
        self,
        campaign_id: str
    ) -> Dict[str, int]:
        """
        Get engagement distribution for a campaign.

        Categories:
        - opened_and_clicked: Subscribers who opened AND clicked
        - opened_only: Subscribers who opened but didn't click
        - not_opened: Subscribers who didn't open
        - bounced: Emails that bounced

        Args:
            campaign_id: Campaign UUID

        Returns:
            Dict with engagement category counts
        """
        try:
            # Get campaign metrics
            response = self.campaigns_table.get_item(
                Key={'campaign_id': campaign_id}
            )
            campaign = response.get('Item')

            if not campaign:
                return {}

            total_sent = int(campaign.get('total_sent', 0) or 0)
            total_delivered = int(campaign.get('total_delivered', 0) or 0)
            total_bounced = int(campaign.get('total_bounced', 0) or 0)
            total_opened = int(campaign.get('total_opened', 0) or 0)
            total_clicked = int(campaign.get('total_clicked', 0) or 0)

            # Calculate distribution
            # Note: clicked is a subset of opened
            opened_and_clicked = total_clicked
            opened_only = total_opened - total_clicked
            not_opened = total_delivered - total_opened

            return {
                'opened_and_clicked': max(0, opened_and_clicked),
                'opened_only': max(0, opened_only),
                'not_opened': max(0, not_opened),
                'bounced': total_bounced,
                'total_sent': total_sent,
                'total_delivered': total_delivered
            }

        except Exception as e:
            logger.error(f"Error getting engagement distribution: {e}")
            return {}

    def get_segment_distribution(self) -> Dict[str, Any]:
        """
        Get overall subscriber segment distribution.

        Returns:
            Dict with segment counts and percentages
        """
        try:
            response = self.engagement_table.scan(
                ProjectionExpression='segment'
            )

            items = response.get('Items', [])
            total = len(items)

            counts = defaultdict(int)
            for item in items:
                segment = item.get('segment', 'unknown')
                counts[segment] += 1

            # Calculate percentages
            distribution = {}
            for segment, count in counts.items():
                percentage = (count / total * 100) if total > 0 else 0
                distribution[segment] = {
                    'count': count,
                    'percentage': round(percentage, 1)
                }

            distribution['total'] = total
            return distribution

        except Exception as e:
            logger.error(f"Error getting segment distribution: {e}")
            return {}

    # =========================================================================
    # Event Analytics
    # =========================================================================

    def get_events_by_campaign(
        self,
        campaign_id: str,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get email events for a campaign.

        Args:
            campaign_id: Campaign UUID
            event_type: Optional filter ('open', 'click', 'bounce', 'complaint')
            limit: Maximum events to return

        Returns:
            List of event dicts, newest first
        """
        try:
            # Build filter expression
            filter_expr = 'campaign_id = :campaign_id'
            expr_values = {':campaign_id': campaign_id}

            if event_type:
                filter_expr += ' AND event_type = :event_type'
                expr_values[':event_type'] = event_type

            response = self.events_table.scan(
                FilterExpression=filter_expr,
                ExpressionAttributeValues=expr_values,
                Limit=limit * 2
            )

            items = response.get('Items', [])

            # Sort by timestamp descending
            items.sort(
                key=lambda x: x.get('timestamp', ''),
                reverse=True
            )

            return items[:limit]

        except Exception as e:
            logger.error(f"Error getting events for campaign {campaign_id}: {e}")
            return []


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_analytics_service() -> AnalyticsService:
    """
    Get or create analytics service instance (singleton).

    Returns:
        AnalyticsService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = AnalyticsService()
    return _service_instance
