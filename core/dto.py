"""
Data Transfer Objects (DTOs) for Repository Pattern

These DTOs provide template-compatible interfaces that work with both
SQLite (SQLAlchemy models) and DynamoDB (dict responses).

Each DTO mimics the SQLAlchemy model interface used in templates,
including properties and methods like `company.ticker`, `release.get_detail_url()`.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import re


def parse_date(date_value) -> Optional[datetime]:
    """Parse various date formats to datetime"""
    if date_value is None:
        return None
    if isinstance(date_value, datetime):
        return date_value
    if isinstance(date_value, str):
        # Handle ISO format
        try:
            return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
        except ValueError:
            pass
        # Handle date-only format
        try:
            return datetime.strptime(date_value, '%Y-%m-%d')
        except ValueError:
            pass
    return None


class CompanyDTO:
    """Template-compatible company DTO"""

    def __init__(self, data: Dict[str, Any]):
        # Core fields
        self.ticker = data.get('ticker', '')
        self.name = data.get('name') or data.get('company_name', '')
        self.id = data.get('id') or hash(self.ticker)  # Use ticker hash for DynamoDB

        # URLs
        self.ir_url = data.get('ir_url', '')
        self.press_release_url = data.get('press_release_url', '')
        self.rss_feed_url = data.get('rss_feed_url', '')
        self.company_rss_feed_url = data.get('company_rss_feed_url', '')

        # Config
        self.ir_platform = data.get('ir_platform', '')
        self.sector = data.get('sector', '')
        self.active = data.get('active', True)
        self.emails_activated = data.get('emails_activated', False)
        self.ignore_company_rss = data.get('ignore_company_rss', False)
        self.newswire_provider = data.get('newswire_provider', '')
        self.newswire_id = data.get('newswire_id', '')
        self.scraping_status = data.get('scraping_status', '')
        self.scraper_variant = data.get('scraper_variant', '')

        # Timestamps
        self.created_at = parse_date(data.get('created_at'))
        self.updated_at = parse_date(data.get('updated_at'))

        # Computed fields (for company list with stats)
        self.has_releases = data.get('has_releases', False)
        self.is_stale = data.get('is_stale', False)
        self.latest_date = parse_date(data.get('latest_date'))
        self.release_count = data.get('release_count', 0)

    def __repr__(self):
        return f"<CompanyDTO {self.ticker}: {self.name}>"


class PressReleaseDTO:
    """Template-compatible press release DTO"""

    def __init__(self, data: Dict[str, Any], company: Optional[CompanyDTO] = None):
        # Core fields
        self.url = data.get('url', '')
        self.title = data.get('title', '')
        self.id = data.get('id') or hash(self.url)  # Use URL hash for DynamoDB

        # For DynamoDB, ticker comes from item; for SQLite, from company relationship
        self._ticker = data.get('ticker', '')
        self._company = company

        # IDs
        self.unique_id = data.get('unique_id', '')
        self.slug = data.get('slug', '')
        self.company_id = data.get('company_id')

        # Dates
        self.published_date = parse_date(
            data.get('published_date') or data.get('press_release_date')
        )
        self.scraped_date = parse_date(data.get('scraped_date'))

        # Content
        self.content = data.get('content', '')
        self.full_text = data.get('full_text', '')
        self.summary = data.get('summary', '')

        # Classification
        self.category = data.get('category', '')
        self.subcategory = data.get('subcategory', '')
        self.is_breaking = data.get('is_breaking', False)
        self.relevance = data.get('relevance')

        # Newsletter
        self.included_in_newsletter = data.get('included_in_newsletter', True)
        self.manually_edited = data.get('manually_edited', False)
        self.editor_notes = data.get('editor_notes', '')
        self.newsletter_id = data.get('newsletter_id')

        # Soft delete
        self.deleted_at = parse_date(data.get('deleted_at'))

    @property
    def company(self) -> CompanyDTO:
        """Lazy-load company for template compatibility"""
        if self._company is None:
            self._company = CompanyDTO({'ticker': self._ticker})
        return self._company

    @company.setter
    def company(self, value):
        """Allow setting company"""
        self._company = value

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        """Mark as deleted"""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self):
        """Restore from deletion"""
        self.deleted_at = None

    def generate_slug(self) -> str:
        """Generate URL slug from first 4 words of title"""
        words = re.sub(r'[^\w\s]', '', self.title.lower()).split()
        return '-'.join(words[:4])

    def get_detail_url(self) -> Optional[str]:
        """Get the new URL format: /press-release/TICKER/YEAR/UNIQUEID/slug"""
        if not self.unique_id or not self.slug:
            return self.url  # Fall back to original URL
        ticker = self.company.ticker if self.company else 'unknown'
        year = self.published_date.year if self.published_date else datetime.now().year
        return f'/press-release/{ticker}/{year}/{self.unique_id}/{self.slug}'

    def __repr__(self):
        ticker = self.company.ticker if self.company else 'Unknown'
        return f"<PressReleaseDTO {ticker}: {self.title[:50]}>"


class NewsletterDTO:
    """Template-compatible newsletter DTO"""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id') or data.get('newsletter_id')
        self.newsletter_type = data.get('newsletter_type', '')
        self.date = parse_date(data.get('date'))
        self.created_at = parse_date(data.get('created_at'))
        self.status = data.get('status', 'draft')
        self.sent_at = parse_date(data.get('sent_at'))
        self.html_content = data.get('html_content', '')
        self.subject_line = data.get('subject_line', '')
        self.recipient_count = data.get('recipient_count', 0)

        # Press releases (lazy loaded)
        self._press_releases = None

    @property
    def press_releases(self) -> List[PressReleaseDTO]:
        """Press releases in this newsletter (lazy load if needed)"""
        return self._press_releases or []

    @press_releases.setter
    def press_releases(self, value):
        self._press_releases = value

    def __repr__(self):
        date_str = self.date.strftime('%Y-%m-%d') if self.date else 'unknown'
        return f"<NewsletterDTO {self.newsletter_type} {date_str}>"


class ReviewEmailDTO:
    """Template-compatible review email DTO"""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id') or hash(data.get('gmail_message_id', ''))
        self.gmail_message_id = data.get('gmail_message_id', '')

        # Email content
        self.subject = data.get('subject', '')
        self.from_header = data.get('from_header', '')
        self.from_email = data.get('from_email', '')
        self.from_domain = data.get('from_domain', '')
        self.date = parse_date(data.get('date'))
        self.raw_email = data.get('raw_email', '')
        self.screenshot_path = data.get('screenshot_path', '')

        # Classification
        self.classification_reason = data.get('classification_reason', '')
        self.status = data.get('status', 'pending')

        # Link to press release
        self.press_release_id = data.get('press_release_id')
        self._press_release = None

        # Timestamps
        self.created_at = parse_date(data.get('created_at'))
        self.processed_at = parse_date(data.get('processed_at'))

    @property
    def press_release(self) -> Optional[PressReleaseDTO]:
        """Linked press release (lazy load)"""
        return self._press_release

    @press_release.setter
    def press_release(self, value):
        self._press_release = value

    def __repr__(self):
        return f"<ReviewEmailDTO {self.subject[:50]}>"


class RelevanceDecisionDTO:
    """Template-compatible relevance decision DTO"""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id') or data.get('decision_id')
        self.press_release_id = data.get('press_release_id')
        self.decision = data.get('decision', '')
        self.decided_at = parse_date(data.get('decided_at'))
        self.decided_by = data.get('decided_by', 'user')

        # Link to press release
        self._press_release = None

    @property
    def press_release(self) -> Optional[PressReleaseDTO]:
        return self._press_release

    @press_release.setter
    def press_release(self, value):
        self._press_release = value

    def __repr__(self):
        return f'<RelevanceDecisionDTO {self.press_release_id}: {self.decision}>'
