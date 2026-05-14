"""
Subscriber Service - Business Logic for Newsletter Subscriptions

Handles:
    - Subscriber CRUD operations
    - Double opt-in verification
    - Confirmation email sending
    - Unsubscribe processing

SOLID Principles:
    - Single Responsibility: Subscriber management only
    - Dependency Injection: DynamoDB table injected
"""

import os
import logging
import uuid
import hashlib
import boto3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Configuration
from config.company import COMPANY_ADDRESS, NEWSLETTER_EMAIL, REPLY_TO_EMAIL
from config.aws_config import aws_config
from config.site_config import get_public_config
from utils.unsubscribe import generate_unsubscribe_url

SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE', 'reitsheet-subscribers')
ENGAGEMENT_TABLE = os.environ.get('ENGAGEMENT_TABLE', 'reitsheet-subscriber-engagement')
EMAIL_EVENTS_TABLE = os.environ.get('EMAIL_EVENTS_TABLE', 'reitsheet-email-events')
VERIFICATION_TOKEN_TTL_HOURS = 24


class SubscriberService:
    """Service for managing newsletter subscribers."""

    def __init__(self, dynamodb=None, ses=None):
        """
        Initialize with optional DynamoDB and SES clients.

        Args:
            dynamodb: boto3 DynamoDB resource (defaults to production)
            ses: boto3 SES client (defaults to production)
        """
        self.dynamodb = dynamodb or boto3.resource('dynamodb', region_name=aws_config.aws_region)
        self.ses = ses or boto3.client('ses', region_name=aws_config.aws_region)
        self.subscribers_table = self.dynamodb.Table(SUBSCRIBERS_TABLE)
        self.engagement_table = self.dynamodb.Table(ENGAGEMENT_TABLE)
        self.events_table = self.dynamodb.Table(EMAIL_EVENTS_TABLE)

    # =========================================================================
    # Immutable Event Logging
    # =========================================================================

    def _hash_email(self, email: str) -> str:
        """SHA256 hash of email for privacy-preserving logging."""
        return hashlib.sha256(email.lower().strip().encode()).hexdigest()

    def _get_ttl_timestamp(self) -> int:
        """TTL 2 years from now (matches email-events pattern)."""
        return int((datetime.now(timezone.utc) + timedelta(days=730)).timestamp())

    def log_subscription_event(
        self,
        event_type: str,
        email: str,
        ip_address: str = None,
        user_agent: str = None,
        source: str = None
    ) -> None:
        """
        Log subscription event to immutable email-events table.

        Event types: subscription_signup, subscription_verified, subscription_unsubscribed
        """
        item = {
            'event_id': str(uuid.uuid4()),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'email_hash': self._hash_email(email),
            'ttl': self._get_ttl_timestamp(),
        }

        if ip_address:
            item['ip_address'] = ip_address
        if user_agent:
            item['user_agent'] = user_agent[:500]
        if source:
            item['source'] = source

        try:
            self.events_table.put_item(Item=item)
            logger.info(f"Logged {event_type} for {email[:3]}***")
        except Exception as e:
            # Non-blocking - don't fail the operation if logging fails
            logger.error(f"Failed to log {event_type}: {e}")

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_subscriber(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get subscriber by email.

        Args:
            email: Subscriber email (case-insensitive)

        Returns:
            Subscriber dict or None if not found
        """
        try:
            response = self.subscribers_table.get_item(
                Key={'email': email.lower().strip()}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting subscriber {email[:3]}***: {e}")
            return None

    def get_subscriber_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get subscriber by verification token.

        Note: This requires a scan (not indexed). For production scale,
        consider adding a GSI on verification_token.

        Args:
            token: Verification token UUID

        Returns:
            Subscriber dict or None if not found
        """
        try:
            # Scan with filter (acceptable for low-frequency verification)
            response = self.subscribers_table.scan(
                FilterExpression='verification_token = :token',
                ExpressionAttributeValues={':token': token}
            )
            items = response.get('Items', [])
            return items[0] if items else None
        except Exception as e:
            logger.error(f"Error getting subscriber by token: {e}")
            return None

    def get_verified_subscribers(self) -> list:
        """
        Get all verified subscribers for sending.

        Returns:
            List of verified subscriber dicts
        """
        try:
            response = self.subscribers_table.query(
                IndexName='status-subscribed_at-index',
                KeyConditionExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': 'verified'}
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error getting verified subscribers: {e}")
            return []

    def get_subscriber_count(self) -> Dict[str, int]:
        """
        Get subscriber counts by status.

        Returns:
            Dict with counts: {verified, pending, unsubscribed, total}
        """
        try:
            # Count by status using GSI
            counts = {'verified': 0, 'pending': 0, 'unsubscribed': 0, 'total': 0}

            for status in ['verified', 'pending', 'unsubscribed']:
                response = self.subscribers_table.query(
                    IndexName='status-subscribed_at-index',
                    KeyConditionExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': status},
                    Select='COUNT'
                )
                counts[status] = response.get('Count', 0)

            counts['total'] = sum(counts.values())
            return counts
        except Exception as e:
            logger.error(f"Error getting subscriber count: {e}")
            return {'verified': 0, 'pending': 0, 'unsubscribed': 0, 'total': 0}

    # =========================================================================
    # Write Operations
    # =========================================================================

    def create_or_update_subscriber(
        self,
        email: str,
        verification_token: str,
        source: str = 'website',
        ip_address: str = None,
        user_agent: str = None
    ) -> Dict[str, Any]:
        """
        Create new subscriber or update unsubscribed subscriber.

        Args:
            email: Subscriber email
            verification_token: UUID for verification link
            source: Where signup came from
            ip_address: Client IP for audit
            user_agent: Client user agent for audit

        Returns:
            Created/updated subscriber dict
        """
        now = datetime.now(timezone.utc)
        token_expires = int((now + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)).timestamp())

        item = {
            'email': email.lower().strip(),
            'status': 'pending',
            'verification_token': verification_token,
            'token_expires_at': token_expires,
            'subscribed_at': now.isoformat(),
            'source': source,
            'created_at': now.isoformat()
        }

        if ip_address:
            item['ip_address'] = ip_address
        if user_agent:
            item['user_agent'] = user_agent[:500]  # Truncate long UAs

        try:
            self.subscribers_table.put_item(Item=item)
            logger.info(f"Created subscriber: {email[:3]}***")
            self.log_subscription_event(
                event_type='subscription_signup',
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                source=source
            )
            return item
        except Exception as e:
            logger.error(f"Error creating subscriber: {e}")
            raise

    def verify_subscriber(
        self,
        email: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Mark subscriber as verified.

        Args:
            email: Subscriber email
            ip_address: Client IP at verification (for immutable audit log)
            user_agent: Client user agent at verification (for immutable audit log)

        Returns:
            Tuple of (success, error_reason).
            - (True, None) if successful
            - (False, 'unsubscribed') if user has unsubscribed
            - Raises exception for other errors
        """
        now = datetime.now(timezone.utc)

        try:
            # Note: We intentionally do NOT clear verification_token here.
            # Email security scanners (URLDefense, SafeLinks, Barracuda) prefetch
            # verification links, which would consume the token before the user clicks.
            # By keeping the token, users can still verify after scanner prefetch.
            # Token expires naturally via token_expires_at (24h TTL).
            # See: BetterAuth allowedAttempts pattern, NextAuth #1840, Supabase #1214
            self.subscribers_table.update_item(
                Key={'email': email.lower().strip()},
                UpdateExpression='''
                    SET #status = :verified,
                        verified_at = :now
                ''',
                # Block verification if user has unsubscribed - they must sign up again
                ConditionExpression='#status <> :unsubscribed',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':verified': 'verified',
                    ':now': now.isoformat(),
                    ':unsubscribed': 'unsubscribed'
                }
            )

            # Initialize engagement record
            self._initialize_engagement(email)

            logger.info(f"Verified subscriber: {email[:3]}***")
            self.log_subscription_event(
                event_type='subscription_verified',
                email=email,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return (True, None)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.info(f"Blocked verification for unsubscribed user: {email[:3]}***")
                return (False, 'unsubscribed')
            logger.error(f"Error verifying subscriber: {e}")
            raise
        except Exception as e:
            logger.error(f"Error verifying subscriber: {e}")
            raise

    def unsubscribe(self, email: str) -> bool:
        """
        Mark subscriber as unsubscribed.

        Args:
            email: Subscriber email

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc)

        try:
            self.subscribers_table.update_item(
                Key={'email': email.lower().strip()},
                UpdateExpression='''
                    SET #status = :unsubscribed,
                        unsubscribed_at = :now
                ''',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':unsubscribed': 'unsubscribed',
                    ':now': now.isoformat()
                }
            )
            logger.info(f"Unsubscribed: {email[:3]}***")
            self.log_subscription_event(
                event_type='subscription_unsubscribed',
                email=email
            )
            return True
        except Exception as e:
            logger.error(f"Error unsubscribing: {e}")
            raise

    def delete_subscriber(self, email: str) -> bool:
        """
        Delete subscriber completely (GDPR right to erasure).

        Args:
            email: Subscriber email

        Returns:
            True if successful
        """
        try:
            # Delete from subscribers table
            self.subscribers_table.delete_item(
                Key={'email': email.lower().strip()}
            )

            # Delete from engagement table
            try:
                self.engagement_table.delete_item(
                    Key={'email': email.lower().strip()}
                )
            except Exception:
                pass  # Engagement record may not exist

            # Note: Events in email_events table should be anonymized,
            # not deleted (keep aggregates, remove email_hash)

            logger.info(f"Deleted subscriber: {email[:3]}***")
            return True
        except Exception as e:
            logger.error(f"Error deleting subscriber: {e}")
            raise

    # =========================================================================
    # Email Operations
    # =========================================================================

    def send_confirmation_email(self, email: str, token: str) -> bool:
        """
        Send double opt-in confirmation email with RFC 8058 unsubscribe headers.

        Args:
            email: Subscriber email
            token: Verification token

        Returns:
            True if sent successfully
        """
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        base_url = os.environ.get('PUBLIC_BASE_URL', 'https://your-domain.com')
        verify_url = f"{base_url}/verify?token={token}"

        # Get configurable email content
        config = get_public_config()
        email_config = config.get('emails', {}).get('confirmation', {})
        brand = config.get('brand', {})
        footer = config.get('footer', {})

        subject = email_config.get('subject', 'Confirm your subscription')
        heading = email_config.get('heading', 'Confirm your subscription')
        body_text = email_config.get('body', 'Click the button below to confirm your subscription:')
        button_text = email_config.get('button_text', 'Confirm Subscription')
        expiry_notice = email_config.get('expiry_notice', 'This link expires in 24 hours.')
        ignore_notice = email_config.get('ignore_notice', "If you didn't sign up, you can safely ignore this email.")
        brand_name = brand.get('name', 'The Press Release Pipeline')
        privacy_url = footer.get('privacy_url', 'https://your-domain.com/privacy')

        # Generate unsubscribe URL
        unsubscribe_url = generate_unsubscribe_url(email)

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #2563eb; color: white; text-decoration: none; border-radius: 6px; }}
                .footer {{ margin-top: 40px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>{heading}</h2>

                <p>{body_text}</p>

                <p style="margin: 30px 0;">
                    <a href="{verify_url}" class="button">{button_text}</a>
                </p>

                <p>Or copy and paste this link:</p>
                <p style="word-break: break-all; color: #666;">{verify_url}</p>

                <p><strong>{expiry_notice}</strong></p>

                <p>{ignore_notice}</p>

                <div class="footer">
                    <p>{brand_name} - Daily REIT Press Release Digest</p>
                    <p style="margin-top: 8px; font-size: 11px; color: #999;">
                        {COMPANY_ADDRESS}
                    </p>
                    <p style="margin-top: 8px;">
                        <a href="{privacy_url}" style="color: #999;">Privacy Policy</a>
                        <span style="color: #ccc; margin: 0 8px;">|</span>
                        <a href="{unsubscribe_url}" style="color: #999;">Unsubscribe</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
{heading}

{body_text}

{verify_url}

{expiry_notice}

{ignore_notice}

--
{brand_name} - Daily REIT Press Release Digest
{COMPANY_ADDRESS}

Unsubscribe: {unsubscribe_url}
        """

        try:
            # Build raw email with RFC 8058 headers
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f'{brand_name} <{NEWSLETTER_EMAIL}>'
            msg['To'] = email
            msg['Reply-To'] = REPLY_TO_EMAIL
            msg['List-Unsubscribe'] = f'<{unsubscribe_url}>'
            msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            logger.info(f"Attempting to send confirmation email to {email[:3]}*** via SES")
            logger.info(f"Sender: {brand_name} <{NEWSLETTER_EMAIL}>, Verify URL: {verify_url}")

            response = self.ses.send_raw_email(
                Source=f'{brand_name} <{NEWSLETTER_EMAIL}>',
                Destinations=[email],
                RawMessage={'Data': msg.as_string()}
            )
            message_id = response.get('MessageId', 'unknown')
            logger.info(f"SES accepted confirmation email for {email[:3]}*** - MessageId: {message_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending confirmation email: {e}")
            raise

    def resend_confirmation(self, email: str) -> bool:
        """
        Resend confirmation email with new token.

        Args:
            email: Subscriber email

        Returns:
            True if sent successfully
        """
        new_token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        token_expires = int((now + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)).timestamp())

        try:
            # Update token
            self.subscribers_table.update_item(
                Key={'email': email.lower().strip()},
                UpdateExpression='''
                    SET verification_token = :token,
                        token_expires_at = :expires
                ''',
                ExpressionAttributeValues={
                    ':token': new_token,
                    ':expires': token_expires
                }
            )

            # Send email
            return self.send_confirmation_email(email, new_token)
        except Exception as e:
            logger.error(f"Error resending confirmation: {e}")
            raise

    def send_already_subscribed_email(self, email: str) -> bool:
        """
        Send notification to already-subscribed user with RFC 8058 unsubscribe headers.

        This is sent privately when someone tries to subscribe with an
        already-verified email. We send this email instead of revealing
        the subscription status publicly (prevents email enumeration).

        Args:
            email: Subscriber email

        Returns:
            True if sent successfully
        """
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        # Get configurable email content
        config = get_public_config()
        email_config = config.get('emails', {}).get('already_subscribed', {})
        brand = config.get('brand', {})
        footer = config.get('footer', {})

        brand_name = brand.get('name', 'The Press Release Pipeline')
        subject = email_config.get('subject', f"You're already subscribed to {brand_name}")
        heading = email_config.get('heading', "You're already subscribed!")
        body_text = email_config.get('body', f"Someone (hopefully you!) just tried to sign up for {brand_name} using this email address. Since you're already on our list, there's nothing you need to do.")
        privacy_url = footer.get('privacy_url', 'https://your-domain.com/privacy')

        # Generate unsubscribe URL
        unsubscribe_url = generate_unsubscribe_url(email)

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .footer {{ margin-top: 40px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>{heading}</h2>

                <p>{body_text}</p>

                <p><strong>Good news:</strong> You're already subscribed! No action is needed.</p>

                <p>You'll continue to receive our daily REIT press release digest.</p>

                <p>If this wasn't you, you can safely ignore this email. Your subscription remains unchanged.</p>

                <div class="footer">
                    <p>{brand_name} - Daily REIT Press Release Digest</p>
                    <p style="margin-top: 8px; font-size: 11px; color: #999;">
                        {COMPANY_ADDRESS}
                    </p>
                    <p style="margin-top: 8px;">
                        <a href="{privacy_url}" style="color: #999;">Privacy Policy</a>
                        <span style="color: #ccc; margin: 0 8px;">|</span>
                        <a href="{unsubscribe_url}" style="color: #999;">Unsubscribe</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
{heading}

{body_text}

Good news: You're already subscribed! No action is needed.

You'll continue to receive our daily REIT press release digest.

If this wasn't you, you can safely ignore this email. Your subscription remains unchanged.

--
{brand_name} - Daily REIT Press Release Digest
{COMPANY_ADDRESS}

Unsubscribe: {unsubscribe_url}
        """

        try:
            # Build raw email with RFC 8058 headers
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f'{brand_name} <{NEWSLETTER_EMAIL}>'
            msg['To'] = email
            msg['Reply-To'] = REPLY_TO_EMAIL
            msg['List-Unsubscribe'] = f'<{unsubscribe_url}>'
            msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            self.ses.send_raw_email(
                Source=f'{brand_name} <{NEWSLETTER_EMAIL}>',
                Destinations=[email],
                RawMessage={'Data': msg.as_string()}
            )
            logger.info(f"Sent already-subscribed notification to {email[:3]}***")
            return True
        except Exception as e:
            logger.error(f"Error sending already-subscribed email: {e}")
            # Don't raise - this is a non-critical notification
            return False

    # =========================================================================
    # Engagement Tracking
    # =========================================================================

    def _initialize_engagement(self, email: str) -> None:
        """Initialize engagement record for new verified subscriber."""
        try:
            self.engagement_table.put_item(
                Item={
                    'email': email.lower().strip(),
                    'lifetime_sends': 0,
                    'lifetime_opens': 0,
                    'lifetime_clicks': 0,
                    'engagement_score': 0,
                    'segment': 'new',
                    'campaigns_opened': [],
                    'created_at': datetime.now(timezone.utc).isoformat()
                },
                ConditionExpression='attribute_not_exists(email)'
            )
        except Exception:
            pass  # Record may already exist (re-subscription)

    def get_subscriber_engagement(self, email: str) -> Optional[Dict[str, Any]]:
        """Get engagement metrics for a subscriber."""
        try:
            response = self.engagement_table.get_item(
                Key={'email': email.lower().strip()}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting engagement for {email[:3]}***: {e}")
            return None

    # =========================================================================
    # GDPR / Data Export
    # =========================================================================

    def export_subscriber_data(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Export all data for a subscriber (GDPR data request).

        Args:
            email: Subscriber email

        Returns:
            Dict with all subscriber data
        """
        subscriber = self.get_subscriber(email)
        if not subscriber:
            return None

        engagement = self.get_subscriber_engagement(email)

        # Note: Events would be queried from email_events table
        # using email_hash for full export

        return {
            'subscriber': subscriber,
            'engagement': engagement,
            'exported_at': datetime.now(timezone.utc).isoformat()
        }


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_subscriber_service() -> SubscriberService:
    """
    Get or create subscriber service instance (singleton).

    Returns:
        SubscriberService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = SubscriberService()
    return _service_instance
