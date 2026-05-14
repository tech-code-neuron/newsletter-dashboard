"""
Newsletter Service - Business Logic for Newsletter Editions

Handles:
    - Loading newsletter editions from DynamoDB
    - Navigation between editions (prev/next)
    - Listing published editions for archive

SOLID Principles:
    - Single Responsibility: Newsletter edition queries only
    - Dependency Injection: DynamoDB resource injected for testability
"""

import os
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Configuration
from config.aws_config import aws_config

NEWSLETTER_EDITIONS_TABLE = os.environ.get(
    'NEWSLETTER_EDITIONS_TABLE',
    'reitsheet-newsletter-editions'
)


class NewsletterService:
    """Service for loading newsletter editions from DynamoDB."""

    def __init__(self, dynamodb_resource=None):
        """
        Initialize with optional DynamoDB resource.

        Args:
            dynamodb_resource: boto3 DynamoDB resource (defaults to production)
        """
        import boto3
        self.dynamodb = dynamodb_resource or boto3.resource(
            'dynamodb',
            region_name=aws_config.aws_region
        )
        self.table = self.dynamodb.Table(NEWSLETTER_EDITIONS_TABLE)
        # Cache for published dates (populated lazily)
        self._published_dates_cache: Optional[List[str]] = None

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest published newsletter edition.

        Returns:
            Newsletter edition dict or None if no published editions exist
        """
        published_dates = self.list_published_dates()
        if not published_dates:
            return None
        # Dates are sorted descending, so first is latest
        return self.get_by_date(published_dates[0])

    def get_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific edition by date.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            Newsletter edition dict or None if not found
        """
        try:
            response = self.table.get_item(Key={'date': date})
            item = response.get('Item')
            if item and item.get('status') == 'published':
                return item
            return None
        except Exception as e:
            logger.error(f"Error getting newsletter edition {date}: {e}")
            return None

    def get_navigation(self, date: str) -> tuple:
        """
        Get previous and next published dates for navigation.

        Args:
            date: Current edition date in YYYY-MM-DD format

        Returns:
            Tuple of (prev_date, next_date) - either can be None
        """
        prev_date = self.get_previous_date(date)
        next_date = self.get_next_date(date)
        return (prev_date, next_date)

    def get_previous_date(self, date: str) -> Optional[str]:
        """
        Get the previous published date.

        Args:
            date: Current edition date in YYYY-MM-DD format

        Returns:
            Previous published date string or None if at oldest
        """
        published_dates = self.list_published_dates()
        if not published_dates:
            return None

        try:
            current_index = published_dates.index(date)
            # Dates are sorted descending, so "previous" is at index + 1
            if current_index + 1 < len(published_dates):
                return published_dates[current_index + 1]
            return None
        except ValueError:
            # Date not in list - find nearest older date
            for pub_date in published_dates:
                if pub_date < date:
                    return pub_date
            return None

    def get_next_date(self, date: str) -> Optional[str]:
        """
        Get the next published date.

        Args:
            date: Current edition date in YYYY-MM-DD format

        Returns:
            Next published date string or None if at newest
        """
        published_dates = self.list_published_dates()
        if not published_dates:
            return None

        try:
            current_index = published_dates.index(date)
            # Dates are sorted descending, so "next" is at index - 1
            if current_index > 0:
                return published_dates[current_index - 1]
            return None
        except ValueError:
            # Date not in list - find nearest newer date
            for pub_date in reversed(published_dates):
                if pub_date > date:
                    return pub_date
            return None

    def list_published_dates(self) -> List[str]:
        """
        List all published edition dates, sorted descending (newest first).

        Returns:
            List of date strings in YYYY-MM-DD format
        """
        # Return cached dates if available
        if self._published_dates_cache is not None:
            return self._published_dates_cache

        try:
            from boto3.dynamodb.conditions import Attr

            # Scan for published editions, only fetch date field
            response = self.table.scan(
                FilterExpression=Attr('status').eq('published'),
                ProjectionExpression='#d',
                ExpressionAttributeNames={'#d': 'date'}
            )
            items = response.get('Items', [])

            # Handle pagination if needed
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=Attr('status').eq('published'),
                    ProjectionExpression='#d',
                    ExpressionAttributeNames={'#d': 'date'},
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))

            # Extract dates and sort descending
            dates = [item.get('date') for item in items if item.get('date')]
            dates.sort(reverse=True)

            # Cache for future calls
            self._published_dates_cache = dates
            return dates

        except Exception as e:
            logger.error(f"Error listing published newsletter dates: {e}")
            return []

    def invalidate_cache(self) -> None:
        """
        Invalidate the published dates cache.

        Call this after publishing a new edition to refresh the cache.
        """
        self._published_dates_cache = None

    # =========================================================================
    # Archive Operations
    # =========================================================================

    def get_archive_summary(self, limit: int = 52) -> List[Dict[str, Any]]:
        """
        Get a summary of published editions for archive display.

        Returns lightweight records with just date and headline.

        Args:
            limit: Maximum number of editions to return (default: 52 = 1 year)

        Returns:
            List of dicts with date and headline fields
        """
        published_dates = self.list_published_dates()[:limit]

        summaries = []
        for date in published_dates:
            try:
                # Fetch just the fields needed for archive display
                response = self.table.get_item(
                    Key={'date': date},
                    ProjectionExpression='#d, headline, item_count',
                    ExpressionAttributeNames={'#d': 'date'}
                )
                item = response.get('Item')
                if item:
                    summaries.append({
                        'date': item.get('date'),
                        'headline': item.get('headline', 'Newsletter Edition'),
                        'item_count': int(item.get('item_count', 0))
                    })
            except Exception as e:
                logger.warning(f"Error fetching archive summary for {date}: {e}")
                continue

        return summaries


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_newsletter_service() -> NewsletterService:
    """
    Get or create newsletter service instance (singleton).

    Returns:
        NewsletterService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = NewsletterService()
    return _service_instance
