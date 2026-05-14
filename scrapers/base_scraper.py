"""
Base scraper class with shared functionality for all platform scrapers.
"""
from datetime import datetime, timedelta
from urllib.parse import urljoin
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# CONSTANTS - Centralized configuration
# ═══════════════════════════════════════════════════════════

# HTTP configuration
CONTENT_FETCH_TIMEOUT = 30  # Seconds to wait for content fetch
MAX_CONTENT_LENGTH = 10000  # Max characters to extract from content

# ═══════════════════════════════════════════════════════════


class BaseScraper:
    """Base class for platform-specific scrapers"""

    def __init__(self, session, db_session, browser, config):
        """
        Initialize base scraper.

        Args:
            session: requests.Session for HTTP requests
            db_session: SQLAlchemy database session
            browser: Playwright browser instance (can be None)
            config: Platform-specific config from selectors.json
        """
        self.session = session
        self.db_session = db_session
        self.browser = browser
        self.config = config
        self.logger = logger

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases for a company.
        Must be implemented by subclasses.

        Args:
            company: Company model instance
            lookback_days: Only return releases from last N days

        Returns:
            int: Number of new press releases saved
        """
        raise NotImplementedError("Subclasses must implement scrape()")

    def save_release(self, company, release_data, content=None):
        """
        Save a press release to database.

        Args:
            company: Company model instance
            release_data: Dict with 'title', 'url', 'date'
            content: Optional content string

        Returns:
            bool: True if saved, False if duplicate
        """
        from models import PressRelease

        # Check for duplicates
        existing = self.db_session.query(PressRelease).filter_by(
            url=release_data['url']
        ).first()

        if existing:
            return False

        # Fetch content if not provided
        if content is None:
            content = self.fetch_content(release_data['url'])

        # Extract first 2000 words for full_text field
        full_text = None
        if content:
            words = content.split()
            if len(words) > 2000:
                full_text = ' '.join(words[:2000])
            else:
                full_text = content

        press_release = PressRelease(
            company_id=company.id,
            title=release_data['title'],
            url=release_data['url'],
            published_date=release_data.get('date') or datetime.now(),
            content=content,
            full_text=full_text,
            category=None,
            included_in_newsletter=True
        )

        # Generate unique_id and slug
        press_release.unique_id = press_release.generate_unique_id(self.db_session)
        press_release.slug = press_release.generate_slug()

        self.db_session.add(press_release)
        self.db_session.commit()

        date_str = release_data.get('date', datetime.now()).strftime('%Y-%m-%d')
        self.logger.info(f"  ✓ [{company.ticker}] ({date_str}) {release_data['title'][:60]}")

        return True

    def fetch_content(self, url):
        """
        Fetch press release content from URL.

        Args:
            url: URL to fetch

        Returns:
            str: Extracted text content
        """
        try:
            from bs4 import BeautifulSoup

            response = self.session.get(url, timeout=CONTENT_FETCH_TIMEOUT)
            if response.status_code != 200:
                return f"Failed to fetch content (HTTP {response.status_code})"

            soup = BeautifulSoup(response.content, 'html.parser')

            # Remove script and style elements
            for script in soup(['script', 'style']):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)

            return text[:MAX_CONTENT_LENGTH]  # Limit to prevent memory issues

        except Exception as e:
            self.logger.warning(f"Failed to fetch content from {url}: {e}")
            return f"Content unavailable: {e}"

    def make_absolute_url(self, base_url, href):
        """Convert relative URL to absolute URL"""
        return urljoin(base_url, href)

    def is_within_lookback(self, pub_date, lookback_days):
        """Check if date is within lookback window"""
        if not pub_date:
            return True  # Include if no date
        cutoff = datetime.now() - timedelta(days=lookback_days)
        return pub_date >= cutoff
