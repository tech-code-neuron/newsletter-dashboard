"""
Data Transfer Objects (DTOs) for Repository Pattern

These DTOs provide template-compatible interfaces that work with both
SQLite (SQLAlchemy models) and DynamoDB (dict responses).

Each DTO mimics the SQLAlchemy model interface used in templates,
including properties and methods like `company.ticker`, `release.get_detail_url()`.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Protocol, runtime_checkable
import re
import hashlib


# =============================================================================
# Protocols (SOLID: Interface Segregation + Dependency Inversion)
# =============================================================================

@runtime_checkable
class CompanyLike(Protocol):
    """Protocol for company objects used in templates."""
    ticker: str
    name: str


@runtime_checkable
class PublishableItem(Protocol):
    """
    Protocol for items publishable to the newsletter.

    Both PressReleaseDTO and DisclosureDTO implement this interface.
    Publisher code should type-hint with this Protocol.

    SOLID Principles:
    - Interface Segregation: Minimal interface for publishing
    - Dependency Inversion: Publisher depends on abstraction
    - Liskov Substitution: Both DTOs are substitutable
    """
    # Identity
    url: str
    title: str
    ticker: str

    # Company (must have .ticker and .name)
    @property
    def company(self) -> CompanyLike: ...

    # Newsletter workflow
    newsletter_status: str
    newsletter_section: Optional[str]
    published_for_date: Optional[str]

    # Sorting
    @property
    def published_date(self) -> Optional[datetime]: ...

    # Display
    @property
    def display_title(self) -> str: ...

    # Type discrimination
    @property
    def is_sec_filing(self) -> bool: ...


# =============================================================================
# Helper Functions
# =============================================================================

def parse_date(date_value) -> Optional[datetime]:
    """
    Parse various date formats to timezone-aware datetime.

    CRITICAL: Always returns timezone-aware datetimes to prevent
    comparison errors between naive and aware datetimes.

    Returns:
        datetime with timezone (UTC), or None if parsing fails
    """
    if date_value is None:
        return None

    if isinstance(date_value, datetime):
        # Ensure existing datetime is timezone-aware
        if date_value.tzinfo is None:
            # Naive datetime - assume UTC and make aware
            return date_value.replace(tzinfo=timezone.utc)
        return date_value

    if isinstance(date_value, str):
        # Handle date-only format FIRST (e.g., '2026-03-16')
        # Must check before fromisoformat() because it also parses date-only strings
        # but returns midnight which causes timezone display bugs
        if len(date_value) == 10 and date_value[4] == '-' and date_value[7] == '-':
            try:
                dt = datetime.strptime(date_value, '%Y-%m-%d')
                # Use NOON UTC (not midnight!) so ET conversion stays on same day
                # Midnight UTC = 8 PM ET previous day (bug)
                # Noon UTC = 8 AM ET same day (correct)
                dt = dt.replace(hour=12, tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass

        # Handle ISO format with timezone (e.g., '2026-03-15T20:00:00+00:00')
        try:
            dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            # fromisoformat can return naive datetime for some formats
            # Always ensure timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass

    return None


def generate_deterministic_id(key: str) -> int:
    """
    Generate deterministic integer ID from string key.

    Uses MD5 hash to create stable IDs that don't change between Python executions.
    This is needed because Python's built-in hash() is non-deterministic for security.

    Args:
        key: String key (e.g., URL, ticker)

    Returns:
        Stable integer ID
    """
    # Take first 8 characters of MD5 hex digest and convert to int
    # This gives us a 32-bit integer (4 billion possible values)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


class CompanyDTO:
    """Template-compatible company DTO"""

    def __init__(self, data: Dict[str, Any]):
        # Core fields
        self.ticker = data.get('ticker', '')
        self.name = data.get('company_name') or data.get('name', '')  # company_name is canonical
        self.id = data.get('id') or generate_deterministic_id(self.ticker)  # Stable hash for DynamoDB

        # URLs
        self.ir_url = data.get('ir_url', '')
        self.press_release_url = data.get('press_release_url', '')
        self.rss_feed_url = data.get('rss_feed_url', '')
        self.company_rss_feed_url = data.get('company_rss_feed_url', '')

        # Config
        self.ir_platform = data.get('ir_platform', '') or data.get('url_construction_method', '')
        self.sector = data.get('sector', '')
        self.active = data.get('active', True)
        self.emails_activated = data.get('emails_activated', False)
        self.ignore_company_rss = data.get('ignore_company_rss', False)
        self.newswire_provider = data.get('newswire_provider', '')
        self.newswire_id = data.get('newswire_id', '')
        self.scraping_status = data.get('scraping_status', '')
        self.scraper_variant = data.get('scraper_variant', '')

        # Playwright fields
        self.playwright_url = data.get('playwright_url', '')
        self.playwright_selector = data.get('playwright_selector', '')
        self.playwright_wait_for = data.get('playwright_wait_for', '')
        self.url_construction_method = data.get('url_construction_method', '')

        # SEC EDGAR fields
        self.cik = data.get('cik', '')
        self.op_cik = data.get('op_cik', '')
        self.op_name = data.get('op_name', '')
        self.op_has_unique_filings = data.get('op_has_unique_filings', False)

        # Company type (public/private)
        self.is_public = data.get('is_public', True)  # Default True for existing companies

        # Sponsor fields (for private companies)
        self.lead_sponsor = data.get('lead_sponsor', '')
        self.second_sponsor = data.get('second_sponsor', '')

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
        self.display_title = data.get('display_title')  # Cleaned title (optional)
        self.id = data.get('id') or generate_deterministic_id(self.url)  # Stable hash for DynamoDB

        # For DynamoDB, ticker comes from item; for SQLite, from company relationship
        self._ticker = data.get('ticker', '')
        self._company = company

        # IDs
        self.unique_id = data.get('unique_id', '')
        self.slug = data.get('slug', '')
        self.year = data.get('year')
        self.company_id = data.get('company_id')

        # Dates
        # Priority: RSS pubDate > email_received_at > press_release_date (date-only fallback)
        # NOTE: first_seen_at is EXCLUDED - it's Lambda processing time, not email time
        rss_pub_date = data.get('rss_pub_date_at')      # Most accurate: RSS pubDate timestamp
        email_received = data.get('email_received_at')  # Email Date header timestamp
        self.published_date = parse_date(
            rss_pub_date or                        # Priority 1: RSS pubDate (most accurate)
            email_received or                      # Priority 2: Email receipt time
            data.get('press_release_date')         # Priority 3: Date-only (old data)
        )
        # Source tracking for debugging
        self.date_source = 'rss' if rss_pub_date else 'email' if email_received else 'fallback'
        # Flag: True if we have actual time info (not just date-only)
        self.has_time_info = rss_pub_date is not None or email_received is not None
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

        # Newsletter Publisher fields
        self.newsletter_status = data.get('newsletter_status', 'ready')  # ready, needs_review, published, excluded
        self.newsletter_section = data.get('newsletter_section')  # Manual override: headline, other, or None (auto)
        self.published_for_date = data.get('published_for_date')  # Date string (YYYY-MM-DD) when published, or None
        self.previously_published = data.get('previously_published', False)  # True if ever published

        # Soft delete
        self.deleted_at = parse_date(data.get('deleted_at'))

    @property
    def ticker(self) -> str:
        """Get ticker from company or stored value"""
        if self._company:
            return self._company.ticker
        return self._ticker

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

    @property
    def is_sec_filing(self) -> bool:
        """Not an SEC filing (for publisher integration)"""
        return False

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
        self.id = data.get('id') or generate_deterministic_id(data.get('gmail_message_id', ''))
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


# SEC 8-K Item descriptions for disclosure display
SEC_8K_ITEM_DESCRIPTIONS = {
    '1.01': 'Entry into a Material Definitive Agreement',
    '1.02': 'Termination of a Material Definitive Agreement',
    '1.03': 'Bankruptcy or Receivership',
    '2.01': 'Completion of Acquisition or Disposition of Assets',
    '2.02': 'Results of Operations and Financial Condition',
    '2.03': 'Creation of a Direct Financial Obligation',
    '2.04': 'Triggering Events That Accelerate or Increase a Direct Financial Obligation',
    '2.05': 'Costs Associated with Exit or Disposal Activities',
    '2.06': 'Material Impairments',
    '3.01': 'Notice of Delisting or Transfer',
    '3.02': 'Unregistered Sales of Equity Securities',
    '3.03': 'Material Modification to Rights of Security Holders',
    '4.01': 'Changes in Registrant\'s Certifying Accountant',
    '4.02': 'Non-Reliance on Previously Issued Financial Statements',
    '5.01': 'Changes in Control of Registrant',
    '5.02': 'Departure/Appointment of Directors or Officers',
    '5.03': 'Amendments to Articles of Incorporation or Bylaws',
    '5.04': 'Temporary Suspension of Trading Under Employee Benefit Plans',
    '5.05': 'Amendment to Code of Ethics',
    '5.06': 'Change in Shell Company Status',
    '5.07': 'Submission of Matters to a Vote of Security Holders',
    '5.08': 'Shareholder Nominations',
    '7.01': 'Regulation FD Disclosure',
    '8.01': 'Other Events',
    '9.01': 'Financial Statements and Exhibits',
}


class DisclosureDTO:
    """
    Template-compatible prospectus/disclosure DTO.

    Supports 424B2, 424B5, FWP filings with offering details.
    """

    def __init__(self, data: Dict[str, Any]):
        # Primary key
        self.filing_url = data.get('filing_url', '')

        # Company info
        self.ticker = data.get('ticker', '')

        # Issuer info (for OP tracking)
        self.issuer_cik = data.get('issuer_cik', '')
        self.issuer_name = data.get('issuer_name', '')
        self.issuer_type = data.get('issuer_type', 'reit')  # 'reit' or 'op'

        # Filing metadata
        self.form_type = data.get('form_type', '424B5')  # 424B2, 424B5, FWP
        self.filing_date = data.get('filing_date', '')
        self.accession_number = data.get('accession_number', '')

        # Offering details
        self.offering_type = data.get('offering_type', 'priced')  # atm, shelf, preliminary, priced
        self.security_type = data.get('security_type', '')  # Senior Notes, Common Stock, etc.
        self.principal_amount = data.get('principal_amount')  # Numeric (e.g., 500000000)
        self.principal_display = data.get('principal_display', '')  # "$500 Million"
        self.maturity_date = data.get('maturity_date')
        self.coupon_rate = data.get('coupon_rate')
        self.pricing_date = data.get('pricing_date')
        self.price_per_share = data.get('price_per_share')  # For equity offerings
        self.use_of_proceeds = data.get('use_of_proceeds', '')

        # SEC document URL
        self.sec_document_url = data.get('sec_document_url')

        # AI-generated content
        self.ai_summary_title = data.get('ai_summary_title', '')
        self.ai_summary_content = data.get('ai_summary_content', '')

        # Publication tracking (PublishableItem Protocol compliance)
        self.newsletter_status = data.get('newsletter_status', 'ready')
        self.published_at = parse_date(data.get('published_at'))
        self.newsletter_date = data.get('newsletter_date')
        self.published_for_date = data.get('published_for_date')  # YYYY-MM-DD
        self.previously_published = data.get('previously_published', False)  # True if ever published
        self.newsletter_section = data.get('newsletter_section')  # Optional override (SEC filings default to 'financing')

        # Timestamps
        self.sec_accepted_at = parse_date(data.get('sec_accepted_at'))  # SEC's official acceptance timestamp
        self.first_seen_at = parse_date(data.get('first_seen_at'))  # Our processing timestamp

        # Generate stable ID
        self.id = data.get('id') or generate_deterministic_id(self.filing_url)

    @property
    def company_name(self) -> str:
        """Alias for issuer_name (backward compatibility)"""
        return self.issuer_name

    @property
    def company(self):
        """Provide PressReleaseDTO-compatible company interface for templates."""
        # Return a lightweight object with .name and .ticker attributes
        class _DisclosureCompany:
            def __init__(self, ticker, name):
                self.ticker = ticker
                self.name = name
        return _DisclosureCompany(self.ticker, self.issuer_name)

    @property
    def title(self) -> str:
        """Provide PressReleaseDTO-compatible title for template filters."""
        return self.ai_summary_title or f'{self.ticker} {self.form_type} Filing'

    @property
    def sec_url(self) -> str:
        """Get SEC EDGAR URL"""
        return self.sec_document_url or self.filing_url

    @property
    def display_title(self) -> str:
        """Get best title for display"""
        return self.ai_summary_title or f'{self.ticker} {self.form_type} Filing'

    @property
    def display_summary(self) -> str:
        """Get summary for display"""
        return self.ai_summary_content or ''

    @property
    def filing_date_display(self) -> str:
        """Get filing date formatted for display"""
        if self.filing_date:
            try:
                dt = datetime.strptime(self.filing_date, '%Y-%m-%d')
                return dt.strftime('%b %d')
            except ValueError:
                return self.filing_date
        return ''

    @property
    def coupon_display(self) -> str:
        """Get coupon rate formatted for display"""
        if self.coupon_rate:
            return f'{self.coupon_rate}%'
        return '-'

    @property
    def offering_type_display(self) -> str:
        """Get human-readable offering type"""
        types = {
            'atm': 'ATM',
            'shelf': 'Shelf',
            'preliminary': 'Launch',
            'priced': 'Priced'
        }
        return types.get(self.offering_type, 'Other')

    @property
    def maturity_display(self) -> str:
        """Get maturity date formatted for display"""
        if self.maturity_date:
            try:
                dt = datetime.strptime(self.maturity_date, '%Y-%m-%d')
                return dt.strftime('%b %Y')
            except ValueError:
                return self.maturity_date
        return '-'

    @property
    def is_sec_filing(self) -> bool:
        """Identify as SEC filing for publisher integration"""
        return True

    @property
    def url(self) -> str:
        """Alias for filing_url (template compatibility with PressReleaseDTO)"""
        return self.filing_url

    @property
    def published_date(self) -> Optional[datetime]:
        """Return SEC acceptance timestamp for sorting (compatible with PressReleaseDTO).

        Uses sec_accepted_at (SEC's official timestamp) for accurate sorting.
        Falls back to first_seen_at for legacy items without sec_accepted_at.
        """
        return self.sec_accepted_at or self.first_seen_at

    def get_detail_url(self) -> str:
        """Get Flask route URL for detail view"""
        from urllib.parse import quote
        return f'/disclosures/{quote(self.filing_url, safe="")}'

    def __repr__(self):
        return f"<DisclosureDTO {self.ticker} {self.form_type}>"


class EmailDTO:
    """
    Template-compatible email DTO for S3 email display.

    Provides consistent interface for email data parsed from S3 objects.
    Used for email viewer feature (/emails route).
    """

    def __init__(self, data: Dict[str, Any]):
        # S3 metadata
        self.id = data.get('id', '')  # S3 object key
        self.size = data.get('size', 0)  # S3 object size in bytes
        self.last_modified = parse_date(data.get('last_modified'))  # S3 last modified time

        # Email headers
        self.message_id = data.get('message_id', '')
        self.subject = data.get('subject', '')
        self.from_header = data.get('from_header', '')  # Full "Name <email>" format
        self.from_email = data.get('from_email', '')  # Just email address
        self.from_domain = data.get('from_domain', '')  # Just domain
        self.from_name = data.get('from_name', '')  # Just name part
        self.to_header = data.get('to_header', '')
        self.date = parse_date(data.get('date'))  # Email Date header
        self.received_date = parse_date(data.get('received_date'))  # Server received date

        # Email body
        self.body_html = data.get('body_html', '')
        self.body_text = data.get('body_text', '')
        self.has_html = bool(data.get('body_html'))
        self.has_attachments = data.get('has_attachments', False)
        self.attachment_count = data.get('attachment_count', 0)

        # All headers (dict)
        self.headers = data.get('headers', {})

        # Extracted/parsed metadata
        self.ticker = data.get('ticker', '')  # Extracted from subject/sender
        self.company_name = data.get('company_name', '')  # Extracted from sender

        # Processing status (for future DynamoDB integration)
        self.status = data.get('status', '')  # pending, processed, etc.
        self.classification = data.get('classification', '')  # landing_page, failed_match, etc.

        # Pipeline tracking status (enriched from email_tracking table)
        self.pipeline_status = data.get('pipeline_status')  # {status, stage, error, ...}

    @property
    def display_date(self) -> Optional[datetime]:
        """Get best available date for display (email date > received date > last modified)"""
        return self.date or self.received_date or self.last_modified

    @property
    def size_kb(self) -> float:
        """Get size in KB for display"""
        return round(self.size / 1024, 1)

    @property
    def size_mb(self) -> float:
        """Get size in MB for display"""
        return round(self.size / (1024 * 1024), 2)

    @property
    def display_from(self) -> str:
        """Get formatted 'from' for display (name or email)"""
        if self.from_name:
            return f"{self.from_name} ({self.from_domain})"
        elif self.from_email:
            return self.from_email
        else:
            return self.from_header

    @property
    def body_preview(self) -> str:
        """Get short preview of email body (first 200 chars)"""
        body = self.body_text or self.body_html
        if not body:
            return ""
        # Strip HTML tags if using HTML body
        if not self.body_text and self.body_html:
            import re
            body = re.sub(r'<[^>]+>', '', self.body_html)
        # Return first 200 chars
        preview = body.strip()[:200]
        if len(body) > 200:
            preview += "..."
        return preview

    def __repr__(self):
        return f"<EmailDTO {self.id}: {self.subject[:50]}>"
