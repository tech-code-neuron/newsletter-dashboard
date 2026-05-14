"""
Publisher Service - Business Logic for Newsletter Publishing

SOLID Principles:
- Single Responsibility: Handles newsletter publishing logic only
- Dependency Inversion: Depends on repository abstractions

Responsibilities:
- Time window calculation (8:01am prior day -> 8:00am selected day)
- Press release filtering by date window and status
- HTML generation for Beehiiv
- Status management (ready, needs_review, published, excluded)
"""
import logging
from datetime import datetime, timedelta, time, timezone
from typing import Dict, List, Optional, Any, Tuple
from zoneinfo import ZoneInfo

from core.repositories import get_press_release_repo, get_disclosure_repo
from core.dto import PublishableItem
from config.query_limits import MAX_PRESS_RELEASES_PER_PAGE
from config.section_config import VALID_MANUAL_SECTIONS

logger = logging.getLogger(__name__)

# Eastern timezone for business logic
ET = ZoneInfo('America/New_York')

# Time window boundaries
WINDOW_START_TIME = time(8, 1)  # 8:01 AM ET
WINDOW_END_TIME = time(9, 30)   # 9:30 AM ET (extended to capture same-day morning releases)


class PublisherService:
    """
    Service layer for newsletter publishing operations.

    Handles:
    - Date window calculation
    - Press release filtering for publishing
    - Status updates
    - HTML generation
    """

    def __init__(self):
        """Initialize service with repository references."""
        self.pr_repo = get_press_release_repo()
        self.disclosure_repo = get_disclosure_repo()

    # =========================================================================
    # Date Window Calculation
    # =========================================================================

    def get_time_window(self, selected_date: datetime.date) -> Tuple[datetime, datetime]:
        """
        Calculate the time window for press releases.

        Standard: 8:01 AM ET prior day -> 8:00 AM ET selected day
        Weekend: Friday 8:01 AM ET -> Monday 8:00 AM ET
                 (Sat/Sun/Mon all show Friday's releases since companies don't issue on weekends)

        Args:
            selected_date: The target date (newsletter date)

        Returns:
            Tuple of (start_datetime, end_datetime) in ET
        """
        weekday = selected_date.weekday()  # 0=Monday, 5=Saturday, 6=Sunday

        # Weekend window: Sat (5), Sun (6), Mon (0) all map to Fri 8:01 AM → Mon 8:00 AM
        if weekday in (5, 6, 0):  # Saturday, Sunday, or Monday
            # Find the Friday before this date
            if weekday == 5:  # Saturday - Friday was 1 day ago
                friday = selected_date - timedelta(days=1)
                monday = selected_date + timedelta(days=2)
            elif weekday == 6:  # Sunday - Friday was 2 days ago
                friday = selected_date - timedelta(days=2)
                monday = selected_date + timedelta(days=1)
            else:  # Monday (weekday=0) - Friday was 3 days ago
                friday = selected_date - timedelta(days=3)
                monday = selected_date

            start_dt = datetime.combine(friday, WINDOW_START_TIME, tzinfo=ET)
            end_dt = datetime.combine(monday, WINDOW_END_TIME, tzinfo=ET)
            return start_dt, end_dt

        # Standard weekday window
        end_dt = datetime.combine(selected_date, WINDOW_END_TIME, tzinfo=ET)
        prior_date = selected_date - timedelta(days=1)
        start_dt = datetime.combine(prior_date, WINDOW_START_TIME, tzinfo=ET)

        return start_dt, end_dt

    def format_time_window(self, selected_date: datetime.date) -> str:
        """
        Format time window as human-readable string.

        Args:
            selected_date: The target date

        Returns:
            Formatted string like "Mar 14, 8:01am -> Mar 15, 8:00am ET"
        """
        start_dt, end_dt = self.get_time_window(selected_date)

        start_str = start_dt.strftime('%b %d, %-I:%M%p').lower().replace('am', 'am').replace('pm', 'pm')
        end_str = end_dt.strftime('%b %d, %-I:%M%p').lower().replace('am', 'am').replace('pm', 'pm')

        return f"{start_str} -> {end_str} ET"

    # =========================================================================
    # Press Release Queries
    # =========================================================================

    def get_releases_for_publisher(
        self,
        selected_date: datetime.date,
        status_filter: Optional[str] = None
    ) -> List[Any]:
        """
        Get press releases within the time window for publishing.

        Args:
            selected_date: Target newsletter date
            status_filter: Optional filter ('ready', 'needs_review', etc.)

        Returns:
            List of press releases within the window
        """
        start_dt, end_dt = self.get_time_window(selected_date)

        # Get all releases in the time window
        releases = self.pr_repo.get_by_date_range(
            start_date=start_dt,
            end_date=end_dt,
            limit=MAX_PRESS_RELEASES_PER_PAGE
        )

        # Filter by status if specified
        if status_filter:
            releases = [r for r in releases if (r.newsletter_status or 'ready') == status_filter]

        # Sort by published_date descending (most recent first)
        # Use timezone-aware datetime.min to handle both naive and aware datetimes
        releases.sort(key=lambda r: r.published_date or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        return releases

    def get_ready_releases_for_publisher(self, selected_date: datetime.date) -> List[Any]:
        """
        Get only 'ready' press releases for the publisher preview.

        Args:
            selected_date: Target newsletter date

        Returns:
            List of ready press releases
        """
        return self.get_releases_for_publisher(selected_date, status_filter='ready')

    def count_releases_by_status(self, selected_date: datetime.date) -> Dict[str, int]:
        """
        Count press releases by newsletter status for the given date.

        Args:
            selected_date: Target date

        Returns:
            Dict with counts: {'ready': N, 'needs_review': N, 'published': N, 'excluded': N}
        """
        releases = self.get_releases_for_publisher(selected_date)

        counts = {
            'ready': 0,
            'needs_review': 0,
            'published': 0,
            'excluded': 0,
            'total': len(releases)
        }

        for r in releases:
            status = r.newsletter_status or 'ready'
            if status in counts:
                counts[status] += 1

        return counts

    # =========================================================================
    # SEC Disclosure Queries
    # =========================================================================

    def get_disclosures_for_publisher(
        self,
        selected_date: datetime.date,
        status_filter: Optional[str] = None
    ) -> List[Any]:
        """
        Get SEC disclosures within the time window for publishing.

        Args:
            selected_date: Target newsletter date
            status_filter: Optional filter ('ready', 'needs_review', etc.)

        Returns:
            List of disclosures within the window
        """
        start_dt, end_dt = self.get_time_window(selected_date)

        # Convert to UTC for DynamoDB comparison
        start_utc = start_dt.astimezone(timezone.utc)
        end_utc = end_dt.astimezone(timezone.utc)

        # Get disclosures in the time window
        disclosures = self.disclosure_repo.get_by_date_range(
            start_dt=start_utc,
            end_dt=end_utc,
            limit=100
        )

        # Filter by status if specified
        if status_filter:
            disclosures = [d for d in disclosures if (d.newsletter_status or 'ready') == status_filter]

        # Sort by first_seen_at descending
        disclosures.sort(
            key=lambda d: d.first_seen_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        return disclosures

    def get_all_items_for_publisher(
        self,
        selected_date: datetime.date,
        status_filter: Optional[str] = None
    ) -> List[Any]:
        """
        Get both press releases and SEC disclosures for publishing.

        Combines and sorts both types of items by published_date.

        Args:
            selected_date: Target newsletter date
            status_filter: Optional filter ('ready', etc.)

        Returns:
            Combined list of press releases and disclosures, sorted by date
        """
        # Fetch press releases
        releases = self.get_releases_for_publisher(selected_date, status_filter)

        # Fetch SEC disclosures
        disclosures = self.get_disclosures_for_publisher(selected_date, status_filter)

        # Combine
        all_items = list(releases) + list(disclosures)

        # Sort by published_date descending (both DTOs have this property)
        all_items.sort(
            key=lambda item: item.published_date or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        return all_items

    def count_all_items_by_status(self, selected_date: datetime.date) -> Dict[str, int]:
        """
        Count all items (press releases + disclosures) by status.

        Args:
            selected_date: Target date

        Returns:
            Dict with counts: {'ready': N, 'sec_filings': N, 'total': N, ...}
        """
        releases = self.get_releases_for_publisher(selected_date)
        disclosures = self.get_disclosures_for_publisher(selected_date)

        counts = {
            'ready': 0,
            'needs_review': 0,
            'published': 0,
            'excluded': 0,
            'press_releases': len(releases),
            'sec_filings': len(disclosures),
            'total': len(releases) + len(disclosures)
        }

        for r in releases:
            status = r.newsletter_status or 'ready'
            if status in counts:
                counts[status] += 1

        for d in disclosures:
            status = d.newsletter_status or 'ready'
            if status in counts:
                counts[status] += 1

        return counts

    # =========================================================================
    # SEC Disclosure Status Management
    # =========================================================================

    def update_disclosure_status(
        self,
        filing_url: str,
        status: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update the newsletter status of an SEC disclosure.

        Args:
            filing_url: SEC filing URL
            status: New status ('ready', 'needs_review', 'published', 'excluded')

        Returns:
            Tuple of (success, error_message)
        """
        valid_statuses = {'ready', 'needs_review', 'published', 'excluded'}
        if status not in valid_statuses:
            return False, f"Invalid status: {status}. Must be one of: {valid_statuses}"

        try:
            self.disclosure_repo.update(filing_url, {'newsletter_status': status})
            logger.info(f"Updated disclosure status for {filing_url[:50]}...: {status}")
            return True, None

        except Exception as e:
            logger.error(f"Error updating disclosure status: {e}")
            return False, str(e)

    def publish_disclosures_for_date(
        self,
        filing_urls: List[str],
        newsletter_date: str
    ) -> Tuple[int, int]:
        """
        Mark SEC disclosures as published for a specific newsletter date.

        Args:
            filing_urls: List of SEC filing URLs
            newsletter_date: Date string (YYYY-MM-DD) of the newsletter

        Returns:
            Tuple of (success_count, failure_count)
        """
        success_count = 0
        failure_count = 0

        for url in filing_urls:
            try:
                self.disclosure_repo.update(url, {
                    'newsletter_status': 'published',
                    'published_for_date': newsletter_date
                })
                success_count += 1
                logger.info(f"Published disclosure {url[:50]}... for date {newsletter_date}")
            except Exception as e:
                logger.error(f"Error publishing disclosure {url}: {e}")
                failure_count += 1

        return success_count, failure_count

    # =========================================================================
    # Status Management
    # =========================================================================

    def update_newsletter_status(
        self,
        url: str,
        status: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update the newsletter status of a press release.

        Also syncs the `included_in_newsletter` boolean:
        - 'ready' status -> included_in_newsletter = True
        - Any other status -> included_in_newsletter = False

        Args:
            url: Press release URL
            status: New status ('ready', 'needs_review', 'published', 'excluded')

        Returns:
            Tuple of (success, error_message)
        """
        valid_statuses = {'ready', 'needs_review', 'published', 'excluded'}
        if status not in valid_statuses:
            return False, f"Invalid status: {status}. Must be one of: {valid_statuses}"

        try:
            update_data = {'newsletter_status': status}

            # Sync included_in_newsletter with status
            # Only 'ready' items are included in newsletter
            update_data['included_in_newsletter'] = (status == 'ready')

            # Clear published_for_date when not published (fixes desktop/mobile consistency)
            if status != 'published':
                update_data['published_for_date'] = None

            self.pr_repo.update(url, update_data)
            logger.info(f"Updated newsletter status for {url}: {status} (included={status == 'ready'})")
            return True, None

        except Exception as e:
            logger.error(f"Error updating newsletter status: {e}")
            return False, str(e)

    def mark_as_published(self, urls: List[str]) -> Tuple[int, int]:
        """
        Mark multiple press releases as published.

        Args:
            urls: List of press release URLs

        Returns:
            Tuple of (success_count, failure_count)
        """
        success_count = 0
        failure_count = 0

        for url in urls:
            success, _ = self.update_newsletter_status(url, 'published')
            if success:
                success_count += 1
            else:
                failure_count += 1

        return success_count, failure_count

    def publish_for_date(self, urls: List[str], newsletter_date: str) -> Tuple[int, int]:
        """
        Mark press releases as published for a specific newsletter date.

        Sets both newsletter_status='published' and published_for_date to track
        which newsletter included the item. This prevents items from appearing
        as 'ready' in subsequent newsletters.

        Args:
            urls: List of press release URLs
            newsletter_date: Date string (YYYY-MM-DD) of the newsletter

        Returns:
            Tuple of (success_count, failure_count)
        """
        success_count = 0
        failure_count = 0

        for url in urls:
            try:
                self.pr_repo.update(url, {
                    'newsletter_status': 'published',
                    'published_for_date': newsletter_date,
                    'included_in_newsletter': False
                })
                success_count += 1
                logger.info(f"Published {url} for date {newsletter_date}")
            except Exception as e:
                logger.error(f"Error publishing {url}: {e}")
                failure_count += 1

        return success_count, failure_count

    # =========================================================================
    # Newsletter Title Management
    # =========================================================================

    def update_newsletter_title(self, url: str, title: str) -> Tuple[bool, Optional[str]]:
        """
        Update the display title for a press release.

        Args:
            url: Press release URL
            title: New title (or empty to clear override)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            display_title = title.strip() if title else None
            self.pr_repo.update(url, {'display_title': display_title})
            logger.info(f"Updated display title for {url}")
            return True, None

        except Exception as e:
            logger.error(f"Error updating display title: {e}")
            return False, str(e)

    def get_display_title(self, release: PublishableItem) -> str:
        """
        Get the display title for a publishable item.

        Uses centralized title_utils.get_display_title() for consistent priority.
        See core/title_utils.py for priority order documentation.

        Args:
            release: PublishableItem (PressReleaseDTO or DisclosureDTO)

        Returns:
            Display title string
        """
        from core.title_utils import get_display_title
        return get_display_title(release)

    # =========================================================================
    # Section Classification Override
    # =========================================================================

    def update_newsletter_section(self, url: str, section: str) -> Tuple[bool, Optional[str]]:
        """
        Update the newsletter section classification for a press release.

        Args:
            url: Press release URL
            section: New section ('headline', 'other', 'auto')

        Returns:
            Tuple of (success, error_message)
        """
        if section not in VALID_MANUAL_SECTIONS:
            return False, f"Invalid section: {section}. Must be one of: {VALID_MANUAL_SECTIONS}"

        try:
            # 'auto' means NULL (use automatic classification)
            newsletter_section = None if section == 'auto' else section

            self.pr_repo.update(url, {'newsletter_section': newsletter_section})
            logger.info(f"Updated newsletter section for {url}: {section}")
            return True, None

        except Exception as e:
            logger.error(f"Error updating newsletter section: {e}")
            return False, str(e)

    def get_effective_section(self, release: PublishableItem, title_getter=None) -> str:
        """
        Get the effective section for a publishable item.

        Returns the manual override if set, otherwise computes from title.

        Args:
            release: PublishableItem (PressReleaseDTO or DisclosureDTO)
            title_getter: Optional function to get display title

        Returns:
            'headline', 'financing', 'management', 'property', 'earnings',
            'conference_call', 'dividend', or 'other'
        """
        from core.publisher_generator import get_section_classification

        # If manually overridden, use that
        if release.newsletter_section:
            return release.newsletter_section

        # Otherwise, compute from title
        from core.title_utils import get_display_title
        title = title_getter(release) if title_getter else get_display_title(release)

        return get_section_classification(title, item=release)

    def get_auto_section(self, release: PublishableItem, title_getter=None) -> str:
        """
        Get the auto-classified section (ignoring any manual override).

        Args:
            release: PublishableItem (PressReleaseDTO or DisclosureDTO)
            title_getter: Optional function to get display title

        Returns:
            'headline', 'financing', 'management', 'property', 'earnings',
            'conference_call', 'dividend', or 'other'
        """
        from core.publisher_generator import get_section_classification
        from core.title_utils import get_display_title

        title = title_getter(release) if title_getter else get_display_title(release)

        return get_section_classification(title, item=release)


# =============================================================================
# Shared Functions (Single Source of Truth)
# =============================================================================

def apply_url_ordering(releases: List, url_order: List[str]) -> List:
    """
    Apply custom URL ordering to releases.

    Preserves ALL releases - ordered items appear first, then remaining items
    in their original order. This is the single source of truth for ordering
    logic used across all publisher routes.

    Args:
        releases: List of release DTOs with .url attribute
        url_order: List of URLs in desired order (may be subset of all releases)

    Returns:
        Ordered list with ALL releases (ordered first, then unordered)
    """
    if not url_order:
        return releases

    url_to_release = {r.url: r for r in releases}
    ordered = []
    for url in url_order:
        if url in url_to_release:
            ordered.append(url_to_release.pop(url))
    # Include remaining releases not in custom order
    ordered.extend(url_to_release.values())
    return ordered


def create_section_getter(service: 'PublisherService'):
    """
    Create a section getter function that handles SEC filings consistently.

    SEC filings default to 'financing' section, but can be overridden via
    newsletter_section field. Press releases use auto-classification or override.

    Args:
        service: PublisherService instance for get_effective_section calls

    Returns:
        Callable that takes a release and returns its section string
    """
    def section_getter(release):
        # Check for manual override first (both PR and SEC filings)
        if hasattr(release, 'newsletter_section') and release.newsletter_section:
            return release.newsletter_section
        # SEC filings default to financing when no override
        if getattr(release, 'is_sec_filing', False):
            return 'financing'
        return service.get_effective_section(release, service.get_display_title)
    return section_getter


def filter_publishable_items(items: List, date_str: str) -> List:
    """
    Filter items to those that are publishable for a given date.

    Includes:
    - 'ready' items (default status)
    - Same-day published items (allows republishing/editing)

    Excludes:
    - Items published for a different date (previously published)
    - Excluded items

    This is the single source of truth for item filtering logic used
    across all publisher routes.

    Args:
        items: List of DTOs with newsletter_status and published_for_date attributes
        date_str: Newsletter date string (YYYY-MM-DD)

    Returns:
        Filtered list of publishable items
    """
    return [
        r for r in items
        if (r.newsletter_status or 'ready') == 'ready'
        or (r.newsletter_status == 'published' and r.published_for_date == date_str)
    ]


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_publisher_service() -> PublisherService:
    """
    Get or create publisher service instance (singleton).

    Returns:
        PublisherService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = PublisherService()
    return _service_instance
