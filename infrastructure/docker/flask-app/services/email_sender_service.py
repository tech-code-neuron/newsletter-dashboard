"""
Email Sender Service - Business Logic for SES Newsletter Sending

Handles:
    - Newsletter campaign sending via SES
    - Tracking pixel and link injection
    - List-Unsubscribe header management
    - Per-recipient customization
    - Send rate limiting

SOLID Principles:
    - Single Responsibility: Email sending only
    - Dependency Injection: SES client and services injected
"""

import os
import re
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

# Configuration
from config.aws_config import aws_config
from config.company import NEWSLETTER_EMAIL, REPLY_TO_EMAIL
from utils.unsubscribe import generate_unsubscribe_url

SES_CONFIGURATION_SET = os.environ.get('SES_CONFIGURATION_SET', 'reitsheet-newsletter')
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'https://reitsheet.co')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', f'The Press Release Pipeline <{NEWSLETTER_EMAIL}>')
BATCH_SIZE = int(os.environ.get('SES_BATCH_SIZE', '50'))


class EmailSenderService:
    """Service for sending newsletter campaigns via AWS SES."""

    def __init__(self, ses=None, subscriber_service=None, campaign_service=None, engagement_service=None):
        """
        Initialize with optional AWS and service dependencies.

        Args:
            ses: boto3 SES client (defaults to production)
            subscriber_service: SubscriberService instance
            campaign_service: CampaignService instance
            engagement_service: EngagementService instance
        """
        import boto3
        self.ses = ses or boto3.client('ses', region_name=aws_config.aws_region)

        # Lazy-load services to avoid circular imports
        self._subscriber_service = subscriber_service
        self._campaign_service = campaign_service
        self._engagement_service = engagement_service

    @property
    def subscriber_service(self):
        if self._subscriber_service is None:
            from services.subscriber_service import get_subscriber_service
            self._subscriber_service = get_subscriber_service()
        return self._subscriber_service

    @property
    def campaign_service(self):
        if self._campaign_service is None:
            from services.campaign_service import get_campaign_service
            self._campaign_service = get_campaign_service()
        return self._campaign_service

    @property
    def engagement_service(self):
        if self._engagement_service is None:
            from services.engagement_service import get_engagement_service
            self._engagement_service = get_engagement_service()
        return self._engagement_service

    # =========================================================================
    # Main Send Method
    # =========================================================================

    def send_newsletter(
        self,
        campaign_id: str,
        subject: str,
        html_content: str,
        test_mode: bool = False,
        test_recipients: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send newsletter to all verified subscribers.

        For each verified subscriber:
        - Adds List-Unsubscribe headers
        - Injects tracking pixel for open tracking
        - Rewrites links for click tracking
        - Tags email with campaign_id for SES events
        - Creates/updates engagement record

        Args:
            campaign_id: Campaign UUID
            subject: Email subject line
            html_content: HTML email body
            test_mode: If True, only send to test_recipients
            test_recipients: List of test email addresses

        Returns:
            Dict with send results: {
                'campaign_id': str,
                'total_recipients': int,
                'successful': int,
                'failed': int,
                'errors': [...]
            }
        """
        result = {
            'campaign_id': campaign_id,
            'total_recipients': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }

        # Get recipients
        if test_mode and test_recipients:
            recipients = [{'email': email.lower().strip()} for email in test_recipients]
        else:
            recipients = self.subscriber_service.get_verified_subscribers()

        result['total_recipients'] = len(recipients)

        if not recipients:
            logger.warning(f"No recipients for campaign {campaign_id}")
            return result

        # Create campaign record first, then mark as sending
        if not test_mode:
            # Create the campaign in draft state first (with the provided campaign_id)
            self.campaign_service.create_campaign(
                subject=subject,
                html_content=html_content,
                name=f"Newsletter {campaign_id[:8]}",
                campaign_id=campaign_id
            )
            # Now mark it as sending (this updates the existing record)
            self.campaign_service.start_send(campaign_id, len(recipients))

        # Send to each recipient
        for recipient in recipients:
            email = recipient.get('email')
            if not email:
                continue

            try:
                # Personalize content for this recipient
                personalized_html = self._personalize_content(
                    html_content=html_content,
                    campaign_id=campaign_id,
                    email=email
                )

                # Send email
                self._send_single_email(
                    to_email=email,
                    subject=subject,
                    html_content=personalized_html,
                    campaign_id=campaign_id
                )

                result['successful'] += 1

                # Update engagement
                self.engagement_service.update_engagement_on_send(email)

            except Exception as e:
                result['failed'] += 1
                result['errors'].append({
                    'email': email[:3] + '***',
                    'error': str(e)
                })
                logger.error(f"Failed to send to {email[:3]}***: {e}")

        # Mark campaign as complete
        if not test_mode:
            self.campaign_service.complete_send(campaign_id, {
                'sent': result['successful'],
                'delivered': result['successful'],  # SES events will update actual delivered count
                'bounced': 0
            })

        logger.info(
            f"Campaign {campaign_id} sent: {result['successful']}/{result['total_recipients']} successful"
        )

        return result

    # =========================================================================
    # Content Personalization
    # =========================================================================

    def _personalize_content(
        self,
        html_content: str,
        campaign_id: str,
        email: str
    ) -> str:
        """
        Personalize HTML content for a specific recipient.

        - Injects tracking pixel for open tracking
        - Adds unsubscribe link if not present

        Note: Link click tracking is handled by SES configuration set.
        SES wraps links automatically and sends events to SNS -> Lambda -> DynamoDB.

        Args:
            html_content: Original HTML content
            campaign_id: Campaign UUID
            email: Recipient email

        Returns:
            Personalized HTML content
        """
        # Generate subscriber hash for tracking (privacy-preserving)
        email_hash = hashlib.sha256(email.encode()).hexdigest()[:16]

        # Inject tracking pixel before </body>
        tracking_pixel = self._generate_tracking_pixel(campaign_id, email_hash)
        if '</body>' in html_content.lower():
            html_content = re.sub(
                r'(</body>)',
                f'{tracking_pixel}\\1',
                html_content,
                flags=re.IGNORECASE
            )
        else:
            html_content += tracking_pixel

        # Note: Link rewriting removed - SES handles click tracking via configuration set
        # This prevents double-wrapping (app tracking + SES tracking)

        # Ensure unsubscribe link exists
        if '{{unsubscribe_url}}' in html_content:
            unsubscribe_url = generate_unsubscribe_url(email)
            html_content = html_content.replace('{{unsubscribe_url}}', unsubscribe_url)

        return html_content

    def _generate_tracking_pixel(self, campaign_id: str, email_hash: str) -> str:
        """Generate invisible tracking pixel HTML."""
        pixel_url = f"{PUBLIC_BASE_URL}/track/open?c={campaign_id}&e={email_hash}"
        return f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:none;" />'

    def _rewrite_links(
        self,
        html_content: str,
        campaign_id: str,
        email_hash: str
    ) -> str:
        """
        Rewrite links for click tracking.

        Wraps links in tracking redirects while preserving original destination.
        """
        def replace_link(match):
            original_url = match.group(1)

            # Skip tracking for certain URLs
            skip_patterns = [
                'unsubscribe',
                'mailto:',
                'tel:',
                PUBLIC_BASE_URL + '/track',  # Don't double-wrap
                'reitsheet.co',           # Don't track own site links
            ]

            for pattern in skip_patterns:
                if pattern in original_url.lower():
                    return match.group(0)

            # Skip relative URLs (they won't redirect properly)
            if not original_url.startswith(('http://', 'https://')):
                return match.group(0)

            # Generate link ID
            link_id = hashlib.md5(original_url.encode()).hexdigest()[:8]

            # Build tracking URL
            params = urlencode({
                'c': campaign_id,
                'e': email_hash,
                'l': link_id,
                'u': original_url
            })
            tracking_url = f"{PUBLIC_BASE_URL}/track/click?{params}"

            return f'href="{tracking_url}"'

        # Match href="..." patterns
        pattern = r'href="([^"]+)"'
        return re.sub(pattern, replace_link, html_content)

    # =========================================================================
    # SES Sending
    # =========================================================================

    def _send_single_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        campaign_id: str
    ) -> str:
        """
        Send a single email via SES.

        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML body
            campaign_id: Campaign UUID for tagging

        Returns:
            SES message ID
        """
        # Generate List-Unsubscribe header (RFC 8058)
        unsubscribe_url = generate_unsubscribe_url(to_email)
        list_unsubscribe = f"<{unsubscribe_url}>"
        list_unsubscribe_post = "List-Unsubscribe=One-Click"

        # Build raw email with headers
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Reply-To'] = REPLY_TO_EMAIL
        msg['List-Unsubscribe'] = list_unsubscribe
        msg['List-Unsubscribe-Post'] = list_unsubscribe_post

        # Add plain text version (strip HTML for fallback)
        text_content = self._html_to_text(html_content)
        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        # Send via SES
        response = self.ses.send_raw_email(
            Source=SENDER_EMAIL,
            Destinations=[to_email],
            RawMessage={'Data': msg.as_string()},
            ConfigurationSetName=SES_CONFIGURATION_SET,
            Tags=[
                {'Name': 'campaign_id', 'Value': campaign_id},
                {'Name': 'email_type', 'Value': 'newsletter'}
            ]
        )

        return response['MessageId']

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (basic conversion)."""
        # Remove style and script tags
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Convert common HTML to text equivalents
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h[1-6]>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)

        # Extract link URLs
        text = re.sub(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', r'\2 (\1)', text, flags=re.IGNORECASE)

        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        import html
        text = html.unescape(text)

        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def send_test_email(
        self,
        campaign_id: str,
        subject: str,
        html_content: str,
        to_email: str
    ) -> bool:
        """
        Send a single test email for campaign preview.

        Args:
            campaign_id: Campaign UUID
            subject: Email subject (will be prefixed with [TEST])
            html_content: HTML body
            to_email: Test recipient email

        Returns:
            True if sent successfully
        """
        try:
            result = self.send_newsletter(
                campaign_id=campaign_id,
                subject=f"[TEST] {subject}",
                html_content=html_content,
                test_mode=True,
                test_recipients=[to_email]
            )
            return result['successful'] == 1
        except Exception as e:
            logger.error(f"Error sending test email: {e}")
            return False

    def validate_email(self, email: str) -> bool:
        """
        Basic email validation.

        Args:
            email: Email address to validate

        Returns:
            True if email appears valid
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def get_send_quota(self) -> Dict[str, Any]:
        """
        Get SES sending quota and current usage.

        Returns:
            Dict with quota info: {max_24_hour_send, max_send_rate, sent_last_24_hours}
        """
        try:
            response = self.ses.get_send_quota()
            return {
                'max_24_hour_send': int(response.get('Max24HourSend', 0)),
                'max_send_rate': float(response.get('MaxSendRate', 0)),
                'sent_last_24_hours': int(response.get('SentLast24Hours', 0)),
                'available': int(response.get('Max24HourSend', 0) - response.get('SentLast24Hours', 0))
            }
        except Exception as e:
            logger.error(f"Error getting SES quota: {e}")
            return {}


# =============================================================================
# Startup Validation - Fail Fast on Missing Config
# =============================================================================

# Required environment variables for email sending
# If these are missing, emails will silently fail - which is worse than crashing at startup
REQUIRED_EMAIL_ENV_VARS = [
    'UNSUBSCRIBE_SECRET',  # Required for generating secure unsubscribe links
]


class EmailConfigError(Exception):
    """Raised when required email configuration is missing."""
    pass


def validate_email_config() -> None:
    """
    Validate that all required environment variables are set.

    Raises:
        EmailConfigError: If any required env var is missing
    """
    missing = [var for var in REQUIRED_EMAIL_ENV_VARS if not os.environ.get(var)]
    if missing:
        raise EmailConfigError(
            f"Missing required environment variable(s) for email sending: {', '.join(missing)}. "
            f"Newsletter emails will fail without these. "
            f"Add to /etc/systemd/system/flask-app.service on EC2."
        )


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_email_sender_service() -> EmailSenderService:
    """
    Get or create email sender service instance (singleton).

    Validates required configuration on first instantiation.

    Returns:
        EmailSenderService instance

    Raises:
        EmailConfigError: If required env vars are missing
    """
    global _service_instance
    if _service_instance is None:
        # Validate config BEFORE creating service - fail fast
        validate_email_config()
        _service_instance = EmailSenderService()
    return _service_instance
