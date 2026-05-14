"""
Simplified Newsletter Publisher

Replaces the old 11-step cascade with a clean 3-step process:
1. Save edition to DynamoDB
2. Mark items as published
3. Done (no S3, no CloudFront, no archive regeneration)

The old system required:
- publish_to_s3() - homepage HTML
- archive_to_s3() - archive HTML
- regenerate_previous_archive() - update prior edition navigation
- publish_current_manifest() - current.json
- update_cloudfront_redirect() - redirect function
- save_newsletter_metadata() - metadata record
- update_current_homepage() - pointer record
- mark_as_published() - update press releases
- mark_disclosures_published() - update SEC filings
- CloudFront invalidation
- Multiple HTML generation passes

The new system:
- save_edition() - one DynamoDB write with all edition data
- mark_items_published() - batch update items
- Navigation computed at render time (no regeneration needed)
- Pages server-rendered (no static files)

SOLID Principles:
- Single Responsibility: Newsletter publishing only
- Dependency Inversion: DynamoDB resource injected
- Interface Segregation: Simple publish/draft interface
"""

import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Configuration
from config.aws_config import aws_config

NEWSLETTER_EDITIONS_TABLE = os.environ.get(
    'NEWSLETTER_EDITIONS_TABLE',
    'reitsheet-newsletter-editions'
)

PRESS_RELEASES_TABLE = os.environ.get(
    'PRESS_RELEASES_TABLE',
    'reitsheet-reit-news-v2'  # Primary press releases table
)

DISCLOSURES_TABLE = os.environ.get(
    'DISCLOSURES_TABLE',
    'reitsheet-8k-disclosures'  # SEC filings table
)


class NewsletterPublisher:
    """
    Simplified newsletter publishing service.

    Replaces the 11-step cascade with a clean 3-step process:
    1. Save edition to reitsheet-newsletter-editions
    2. Mark items as published in their respective tables
    3. Done

    No S3, no CloudFront, no archive regeneration - pages are server-rendered.
    """

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
        self.editions_table = self.dynamodb.Table(NEWSLETTER_EDITIONS_TABLE)
        self.pr_table = self.dynamodb.Table(PRESS_RELEASES_TABLE)
        self.disclosures_table = self.dynamodb.Table(DISCLOSURES_TABLE)

    # =========================================================================
    # Main Publishing Flow
    # =========================================================================

    def publish(
        self,
        date: str,
        items: List[Dict[str, Any]],
        sections: Dict[str, List[Dict[str, Any]]],
        headline: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Publish a newsletter edition.

        Three-step process:
        1. Save edition to reitsheet-newsletter-editions (with items and sections)
        2. Mark all items as published in their source tables
        3. Return success with edition metadata

        Args:
            date: Edition date (YYYY-MM-DD)
            items: List of newsletter items (dicts with url, ticker, title, etc.)
            sections: Dict mapping section_key to list of items
            headline: Optional headline for the edition (defaults to first headline item)

        Returns:
            dict with:
                - success: bool
                - edition: dict with date, status, item_count
                - items_published: int (number of items marked published)
                - error: str (only if success=False)
        """
        try:
            # Step 1: Save edition to DynamoDB
            edition = self._save_edition(date, items, sections, headline, status='published')

            # Step 2: Mark items as published
            items_published = self._mark_items_published(items, date)

            logger.info(f"Published newsletter edition {date}: {len(items)} items")

            return {
                'success': True,
                'edition': {
                    'date': date,
                    'status': 'published',
                    'item_count': len(items),
                    'headline': edition.get('headline'),
                    'published_at': edition.get('published_at')
                },
                'items_published': items_published
            }

        except Exception as e:
            logger.error(f"Error publishing newsletter {date}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def save_draft(
        self,
        date: str,
        items: List[Dict[str, Any]],
        sections: Dict[str, List[Dict[str, Any]]],
        headline: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save newsletter as draft without marking items as published.

        Drafts can be edited and re-saved before final publish.

        Args:
            date: Edition date (YYYY-MM-DD)
            items: List of newsletter items
            sections: Dict mapping section_key to list of items
            headline: Optional headline for the edition

        Returns:
            dict with:
                - success: bool
                - edition: dict with date, status, item_count
                - error: str (only if success=False)
        """
        try:
            edition = self._save_edition(date, items, sections, headline, status='draft')

            logger.info(f"Saved draft newsletter edition {date}: {len(items)} items")

            return {
                'success': True,
                'edition': {
                    'date': date,
                    'status': 'draft',
                    'item_count': len(items),
                    'headline': edition.get('headline'),
                    'updated_at': edition.get('updated_at')
                }
            }

        except Exception as e:
            logger.error(f"Error saving draft {date}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_draft(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Get a draft edition for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Edition dict if draft exists, None otherwise
        """
        try:
            response = self.editions_table.get_item(Key={'date': date})
            item = response.get('Item')

            if item and item.get('status') == 'draft':
                return item

            return None

        except Exception as e:
            logger.error(f"Error getting draft {date}: {e}")
            return None

    def delete_draft(self, date: str) -> bool:
        """
        Delete a draft edition.

        Only deletes if status is 'draft' (published editions cannot be deleted).

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            True if deleted, False if not found or not a draft
        """
        try:
            # Check if it exists and is a draft
            existing = self.get_draft(date)
            if not existing:
                logger.warning(f"Draft {date} not found or not a draft")
                return False

            # Delete the draft
            self.editions_table.delete_item(Key={'date': date})
            logger.info(f"Deleted draft newsletter edition {date}")
            return True

        except Exception as e:
            logger.error(f"Error deleting draft {date}: {e}")
            return False

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _save_edition(
        self,
        date: str,
        items: List[Dict[str, Any]],
        sections: Dict[str, List[Dict[str, Any]]],
        headline: Optional[str],
        status: str
    ) -> Dict[str, Any]:
        """
        Save edition to DynamoDB.

        Args:
            date: Edition date (YYYY-MM-DD)
            items: List of newsletter items
            sections: Dict mapping section_key to list of items
            headline: Optional headline text
            status: 'draft' or 'published'

        Returns:
            The saved edition dict
        """
        now = datetime.now(timezone.utc).isoformat()

        # Extract URLs for each item (primary identifier)
        item_urls = [item.get('url') for item in items if item.get('url')]

        # Derive headline from first headline section item if not provided
        if not headline and sections.get('headline'):
            first_headline = sections['headline'][0]
            headline = first_headline.get('title', first_headline.get('display_title', ''))

        # Build section summary (section_key -> count)
        section_counts = {key: len(section_items) for key, section_items in sections.items()}

        edition = {
            'date': date,
            'status': status,
            'headline': headline or '',
            'item_count': len(items),
            'section_counts': section_counts,
            'item_urls': item_urls,
            'updated_at': now
        }

        if status == 'published':
            edition['published_at'] = now

        # Store full item data for accurate rendering
        # Convert to DynamoDB-safe format (use Decimal for numbers)
        edition['items'] = self._convert_items_for_dynamodb(items)
        edition['sections'] = self._convert_sections_for_dynamodb(sections)

        self.editions_table.put_item(Item=edition)
        return edition

    def _convert_items_for_dynamodb(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert items to DynamoDB-safe format.

        - Removes None values (DynamoDB doesn't allow them)
        - Converts floats to Decimal

        Args:
            items: List of item dicts

        Returns:
            DynamoDB-safe list of dicts
        """
        safe_items = []
        for item in items:
            safe_item = {}
            for key, value in item.items():
                if value is None:
                    continue  # Skip None values
                if isinstance(value, float):
                    safe_item[key] = Decimal(str(value))
                elif isinstance(value, datetime):
                    safe_item[key] = value.isoformat()
                else:
                    safe_item[key] = value
            safe_items.append(safe_item)
        return safe_items

    def _convert_sections_for_dynamodb(
        self,
        sections: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Convert sections dict to DynamoDB-safe format.

        Args:
            sections: Dict mapping section_key to list of items

        Returns:
            DynamoDB-safe sections dict
        """
        safe_sections = {}
        for section_key, section_items in sections.items():
            safe_sections[section_key] = self._convert_items_for_dynamodb(section_items)
        return safe_sections

    def _mark_items_published(self, items: List[Dict[str, Any]], date: str) -> int:
        """
        Mark all items as published in their source tables.

        Separates press releases from SEC filings and updates each table.

        Args:
            items: List of item dicts (must have 'url' and optionally 'is_sec_filing')
            date: Newsletter date (YYYY-MM-DD)

        Returns:
            Number of items successfully marked as published
        """
        success_count = 0
        now = datetime.now(timezone.utc).isoformat()

        for item in items:
            url = item.get('url')
            if not url:
                continue

            is_sec_filing = item.get('is_sec_filing', False)

            try:
                if is_sec_filing:
                    # Update disclosures table
                    self.disclosures_table.update_item(
                        Key={'filing_url': url},
                        UpdateExpression='SET newsletter_status = :status, published_for_date = :date, published_at = :now, previously_published = :pp',
                        ExpressionAttributeValues={
                            ':status': 'published',
                            ':date': date,
                            ':now': now,
                            ':pp': True
                        }
                    )
                else:
                    # Update press releases table
                    self.pr_table.update_item(
                        Key={'url': url},
                        UpdateExpression='SET newsletter_status = :status, published_for_date = :date, included_in_newsletter = :included, previously_published = :pp',
                        ExpressionAttributeValues={
                            ':status': 'published',
                            ':date': date,
                            ':included': False,  # No longer "ready" to include
                            ':pp': True
                        }
                    )

                success_count += 1

            except Exception as e:
                logger.warning(f"Error marking item {url[:50]}... as published: {e}")
                continue

        return success_count

    # =========================================================================
    # Unpublish (Rollback)
    # =========================================================================

    def unpublish(self, date: str) -> Dict[str, Any]:
        """
        Unpublish an edition, reverting items to 'ready' status.

        This is a rollback operation - use with caution.

        Args:
            date: Edition date (YYYY-MM-DD)

        Returns:
            dict with success, items_reverted, error
        """
        try:
            # Get the edition
            response = self.editions_table.get_item(Key={'date': date})
            edition = response.get('Item')

            if not edition:
                return {'success': False, 'error': f'Edition {date} not found'}

            if edition.get('status') != 'published':
                return {'success': False, 'error': f'Edition {date} is not published'}

            # Get item URLs
            item_urls = edition.get('item_urls', [])
            items = edition.get('items', [])

            # Revert items to ready
            reverted_count = self._mark_items_ready(items, item_urls)

            # Update edition status to draft
            self.editions_table.update_item(
                Key={'date': date},
                UpdateExpression='SET #status = :status, unpublished_at = :now',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'draft',
                    ':now': datetime.now(timezone.utc).isoformat()
                }
            )

            logger.info(f"Unpublished edition {date}, reverted {reverted_count} items")

            return {
                'success': True,
                'items_reverted': reverted_count
            }

        except Exception as e:
            logger.error(f"Error unpublishing {date}: {e}")
            return {'success': False, 'error': str(e)}

    def _mark_items_ready(
        self,
        items: List[Dict[str, Any]],
        item_urls: List[str]
    ) -> int:
        """
        Revert items to 'ready' status.

        Args:
            items: List of item dicts (with is_sec_filing flag)
            item_urls: List of URLs (fallback if items missing)

        Returns:
            Number of items successfully reverted
        """
        success_count = 0

        # Build URL -> is_sec_filing map from items
        sec_filing_urls = set()
        for item in items:
            if item.get('is_sec_filing'):
                sec_filing_urls.add(item.get('url'))

        # Process all URLs
        urls_to_process = [item.get('url') for item in items] if items else item_urls

        for url in urls_to_process:
            if not url:
                continue

            is_sec_filing = url in sec_filing_urls

            try:
                if is_sec_filing:
                    self.disclosures_table.update_item(
                        Key={'filing_url': url},
                        UpdateExpression='SET newsletter_status = :status, previously_published = :pp REMOVE published_for_date, published_at',
                        ExpressionAttributeValues={':status': 'ready', ':pp': False}
                    )
                else:
                    self.pr_table.update_item(
                        Key={'url': url},
                        UpdateExpression='SET newsletter_status = :status, included_in_newsletter = :included, previously_published = :pp REMOVE published_for_date',
                        ExpressionAttributeValues={
                            ':status': 'ready',
                            ':included': True,
                            ':pp': False
                        }
                    )

                success_count += 1

            except Exception as e:
                logger.warning(f"Error reverting item {url[:50]}...: {e}")
                continue

        return success_count


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_publisher_instance = None


def get_newsletter_publisher() -> NewsletterPublisher:
    """
    Get or create newsletter publisher instance (singleton).

    Returns:
        NewsletterPublisher instance
    """
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = NewsletterPublisher()
    return _publisher_instance
