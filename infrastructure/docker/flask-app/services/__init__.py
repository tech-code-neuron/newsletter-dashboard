"""
Services Layer for REIT Newsletter

Business logic separated from route handlers.
"""

# Service factory imports for convenience
from services.campaign_service import CampaignService, get_campaign_service
from services.engagement_service import EngagementService, get_engagement_service
from services.analytics_service import AnalyticsService, get_analytics_service
from services.email_sender_service import EmailSenderService, get_email_sender_service
from services.newsletter_service import NewsletterService, get_newsletter_service
from services.newsletter_publisher import NewsletterPublisher, get_newsletter_publisher
from services.sponsor_service import SponsorService, get_sponsor_service

__all__ = [
    # Campaign management
    'CampaignService',
    'get_campaign_service',
    # Engagement tracking
    'EngagementService',
    'get_engagement_service',
    # Analytics and reporting
    'AnalyticsService',
    'get_analytics_service',
    # Email sending
    'EmailSenderService',
    'get_email_sender_service',
    # Newsletter editions
    'NewsletterService',
    'get_newsletter_service',
    # Newsletter publishing
    'NewsletterPublisher',
    'get_newsletter_publisher',
    # Sponsor management
    'SponsorService',
    'get_sponsor_service',
]
