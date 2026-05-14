"""
Campaign Service - Business Logic for Email Marketing Campaigns

Handles:
    - Campaign CRUD operations
    - Campaign state management (draft, scheduled, sending, sent)
    - Campaign metrics calculation

SOLID Principles:
    - Single Responsibility: Campaign management only
    - Dependency Injection: DynamoDB table injected for testability
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from decimal import Decimal

logger = logging.getLogger(__name__)

# Configuration
from config.aws_config import aws_config

CAMPAIGNS_TABLE = os.environ.get('CAMPAIGNS_TABLE', 'reitsheet-campaigns')


class CampaignService:
    """Service for managing email marketing campaigns."""

    def __init__(self, dynamodb=None):
        """
        Initialize with optional DynamoDB resource.

        Args:
            dynamodb: boto3 DynamoDB resource (defaults to production)
        """
        import boto3
        self.dynamodb = dynamodb or boto3.resource('dynamodb', region_name=aws_config.aws_region)
        self.campaigns_table = self.dynamodb.Table(CAMPAIGNS_TABLE)

    # =========================================================================
    # Create Operations
    # =========================================================================

    def create_campaign(
        self,
        subject: str,
        html_content: str,
        name: Optional[str] = None,
        scheduled_at: Optional[str] = None,
        campaign_id: Optional[str] = None
    ) -> str:
        """
        Create a new email campaign.

        Args:
            subject: Email subject line
            html_content: HTML email body
            name: Optional campaign name (defaults to subject)
            scheduled_at: Optional ISO 8601 scheduled send time
            campaign_id: Optional campaign ID (generates UUID if not provided)

        Returns:
            campaign_id (UUID string)
        """
        campaign_id = campaign_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item = {
            'campaign_id': campaign_id,
            'name': name or subject,
            'subject': subject,
            'html_content': html_content,
            'status': 'draft',
            'created_at': now,
            'updated_at': now,
            # Metrics (initialized to 0)
            'total_recipients': 0,
            'total_sent': 0,
            'total_delivered': 0,
            'total_bounced': 0,
            'total_opened': 0,
            'total_clicked': 0,
            'total_unsubscribed': 0,
            'total_complained': 0
        }

        if scheduled_at:
            item['scheduled_at'] = scheduled_at
            item['status'] = 'scheduled'

        try:
            self.campaigns_table.put_item(Item=item)
            logger.info(f"Created campaign: {campaign_id}")
            return campaign_id
        except Exception as e:
            logger.error(f"Error creating campaign: {e}")
            raise

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """
        Get campaign by ID.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Campaign dict or None if not found
        """
        try:
            response = self.campaigns_table.get_item(
                Key={'campaign_id': campaign_id}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting campaign {campaign_id}: {e}")
            return None

    def list_campaigns(
        self,
        status: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        List campaigns with optional status filter.

        Args:
            status: Optional status filter ('draft', 'scheduled', 'sending', 'sent')
            limit: Maximum number of campaigns to return

        Returns:
            List of campaign dicts, newest first
        """
        try:
            if status:
                # Filter by status
                response = self.campaigns_table.scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': status},
                    Limit=limit * 2  # Fetch extra for post-filtering
                )
            else:
                response = self.campaigns_table.scan(
                    Limit=limit * 2
                )

            items = response.get('Items', [])

            # Sort by created_at descending (newest first)
            items.sort(
                key=lambda x: x.get('created_at', ''),
                reverse=True
            )

            return items[:limit]

        except Exception as e:
            logger.error(f"Error listing campaigns: {e}")
            return []

    # =========================================================================
    # State Management
    # =========================================================================

    def start_send(self, campaign_id: str, total_recipients: int = 0) -> bool:
        """
        Mark campaign as sending and record recipient count.

        Args:
            campaign_id: Campaign UUID
            total_recipients: Number of recipients to send to

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()

        try:
            self.campaigns_table.update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='''
                    SET #status = :sending,
                        send_started_at = :now,
                        total_recipients = :recipients,
                        updated_at = :now
                ''',
                ConditionExpression='#status IN (:draft, :scheduled)',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':sending': 'sending',
                    ':now': now,
                    ':recipients': total_recipients,
                    ':draft': 'draft',
                    ':scheduled': 'scheduled'
                }
            )
            logger.info(f"Started sending campaign: {campaign_id}")
            return True
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Campaign {campaign_id} cannot be started (invalid status)")
            return False
        except Exception as e:
            logger.error(f"Error starting campaign send: {e}")
            raise

    def complete_send(
        self,
        campaign_id: str,
        stats: Dict[str, int]
    ) -> bool:
        """
        Mark campaign as sent and record final statistics.

        Args:
            campaign_id: Campaign UUID
            stats: Dict with keys: sent, delivered, bounced, etc.

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()

        update_expr = 'SET #status = :status_value, send_completed_at = :now, updated_at = :now'
        expr_values = {
            ':status_value': 'sent',
            ':now': now,
            ':sending': 'sending'
        }
        expr_names = {'#status': 'status'}

        # Add stats to update
        stat_fields = [
            'total_sent', 'total_delivered', 'total_bounced',
            'total_opened', 'total_clicked', 'total_unsubscribed', 'total_complained'
        ]

        for field in stat_fields:
            key = field.replace('total_', '')  # e.g., 'sent' from 'total_sent'
            if key in stats:
                update_expr += f', {field} = :{key}'
                expr_values[f':{key}'] = stats[key]

        try:
            self.campaigns_table.update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ConditionExpression='#status = :sending'
            )
            logger.info(f"Completed campaign send: {campaign_id}")
            return True
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Campaign {campaign_id} is not in sending state")
            return False
        except Exception as e:
            logger.error(f"Error completing campaign send: {e}")
            raise

    def update_campaign_metrics(
        self,
        campaign_id: str,
        metric: str,
        increment: int = 1
    ) -> bool:
        """
        Increment a campaign metric (atomic update).

        Args:
            campaign_id: Campaign UUID
            metric: Metric name ('opened', 'clicked', 'bounced', etc.)
            increment: Amount to increment (default: 1)

        Returns:
            True if successful
        """
        field_name = f'total_{metric}'
        now = datetime.now(timezone.utc).isoformat()

        try:
            self.campaigns_table.update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression=f'SET {field_name} = if_not_exists({field_name}, :zero) + :inc, updated_at = :now',
                ExpressionAttributeValues={
                    ':inc': increment,
                    ':zero': 0,
                    ':now': now
                }
            )
            return True
        except Exception as e:
            logger.error(f"Error updating campaign metric {metric}: {e}")
            return False

    # =========================================================================
    # Metrics Calculation
    # =========================================================================

    def get_campaign_metrics(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """
        Get calculated campaign metrics including rates.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Dict with metrics and calculated rates, or None if not found
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return None

        # Extract counts (handle Decimal from DynamoDB)
        total_sent = int(campaign.get('total_sent', 0) or 0)
        total_delivered = int(campaign.get('total_delivered', 0) or 0)
        total_bounced = int(campaign.get('total_bounced', 0) or 0)
        total_opened = int(campaign.get('total_opened', 0) or 0)
        total_clicked = int(campaign.get('total_clicked', 0) or 0)
        total_unsubscribed = int(campaign.get('total_unsubscribed', 0) or 0)
        total_complained = int(campaign.get('total_complained', 0) or 0)

        # Calculate rates (avoid division by zero)
        def safe_rate(numerator: int, denominator: int) -> float:
            if denominator == 0:
                return 0.0
            return round((numerator / denominator) * 100, 2)

        return {
            'campaign_id': campaign_id,
            'status': campaign.get('status'),
            # Counts
            'total_recipients': int(campaign.get('total_recipients', 0) or 0),
            'total_sent': total_sent,
            'total_delivered': total_delivered,
            'total_bounced': total_bounced,
            'total_opened': total_opened,
            'total_clicked': total_clicked,
            'total_unsubscribed': total_unsubscribed,
            'total_complained': total_complained,
            # Calculated rates
            'delivery_rate': safe_rate(total_delivered, total_sent),
            'bounce_rate': safe_rate(total_bounced, total_sent),
            'open_rate': safe_rate(total_opened, total_delivered),
            'click_rate': safe_rate(total_clicked, total_delivered),
            'click_to_open_rate': safe_rate(total_clicked, total_opened),
            'unsubscribe_rate': safe_rate(total_unsubscribed, total_delivered),
            'complaint_rate': safe_rate(total_complained, total_delivered),
            # Timestamps
            'send_started_at': campaign.get('send_started_at'),
            'send_completed_at': campaign.get('send_completed_at')
        }

    # =========================================================================
    # Update Operations
    # =========================================================================

    def update_campaign(
        self,
        campaign_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update campaign fields (only allowed in draft/scheduled status).

        Args:
            campaign_id: Campaign UUID
            updates: Dict of fields to update (subject, html_content, name, scheduled_at)

        Returns:
            True if successful
        """
        allowed_fields = {'subject', 'html_content', 'name', 'scheduled_at'}
        updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not updates:
            return True  # Nothing to update

        now = datetime.now(timezone.utc).isoformat()

        # Build update expression
        update_parts = ['updated_at = :now']
        expr_values = {':now': now, ':draft': 'draft', ':scheduled': 'scheduled'}
        expr_names = {'#status': 'status'}

        for i, (key, value) in enumerate(updates.items()):
            placeholder = f':val{i}'
            update_parts.append(f'{key} = {placeholder}')
            expr_values[placeholder] = value

        update_expr = 'SET ' + ', '.join(update_parts)

        try:
            self.campaigns_table.update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ConditionExpression='#status IN (:draft, :scheduled)'
            )
            logger.info(f"Updated campaign: {campaign_id}")
            return True
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Campaign {campaign_id} cannot be updated (not in draft/scheduled)")
            return False
        except Exception as e:
            logger.error(f"Error updating campaign: {e}")
            raise

    def delete_campaign(self, campaign_id: str) -> bool:
        """
        Delete a campaign (only allowed in draft status).

        Args:
            campaign_id: Campaign UUID

        Returns:
            True if successful
        """
        try:
            self.campaigns_table.delete_item(
                Key={'campaign_id': campaign_id},
                ConditionExpression='#status = :draft',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':draft': 'draft'}
            )
            logger.info(f"Deleted campaign: {campaign_id}")
            return True
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Campaign {campaign_id} cannot be deleted (not in draft)")
            return False
        except Exception as e:
            logger.error(f"Error deleting campaign: {e}")
            raise


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_campaign_service() -> CampaignService:
    """
    Get or create campaign service instance (singleton).

    Returns:
        CampaignService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = CampaignService()
    return _service_instance
