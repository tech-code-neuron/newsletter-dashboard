"""
URL Construction Strategies
===========================
SOLID: Strategy Pattern - Open/Closed Principle

Add new URL construction methods by creating new strategy classes,
not by modifying existing code.

Each strategy:
1. Implements construct() method
2. Returns constructed URL or None
3. Handles its own error logging

Usage:
    strategy = URL_CONSTRUCTION_STRATEGIES['gcs_hosted']
    url = strategy.construct(subject, ir_domain, email_date)
"""

import re
import logging
from datetime import datetime
from abc import ABC, abstractmethod

from .constants import (
    KNOWN_SLUG_PATH_TEMPLATE,
    KNOWN_SLUG_WORD_COUNT,
    KNOWN_SLUG_WORD_COUNT_9,
    BRIXMOR_URL_PATH_TEMPLATE,
    TERRENO_URL_PATH_TEMPLATE,
    # Legacy aliases for backward compatibility
    GCS_URL_PATH_TEMPLATE,
    GCS_SLUG_WORD_COUNT,
    GCS_SLUG_WORD_COUNT_9
)

logger = logging.getLogger(__name__)


# ============================================================================
# Base Strategy Class
# ============================================================================

class URLConstructionStrategy(ABC):
    """
    Base class for all URL construction strategies
    SOLID: Strategy Pattern - Each concrete strategy implements construct()
    """

    def __init__(self, strategy_name):
        """
        Initialize strategy with name for logging

        Args:
            strategy_name: Human-readable strategy name
        """
        self.strategy_name = strategy_name

    @abstractmethod
    def construct(self, subject, ir_domain, email_date=None):
        """
        Construct URL from email metadata

        Args:
            subject: Email subject line
            ir_domain: Company IR domain
            email_date: Email date (optional, for year-based URLs)

        Returns:
            Constructed URL string or None if construction fails
        """
        pass

    def _remove_email_prefixes(self, subject):
        """
        Remove common email prefixes (RE:, FW:, Fwd:)

        Args:
            subject: Raw email subject

        Returns:
            Cleaned subject line
        """
        return re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE)

    def _extract_words(self, text):
        """
        Extract alphanumeric words from text

        Args:
            text: Input text

        Returns:
            List of words (alphanumeric only)
        """
        return re.findall(r'\b[a-zA-Z0-9]+\b', text)

    def _extract_title_after_prefix(self, subject):
        """
        Extract title after company prefix (e.g., "Company Name - Title")

        Args:
            subject: Email subject

        Returns:
            Title portion (or full subject if no prefix)
        """
        if ' - ' in subject:
            _, title = subject.split(' - ', 1)
            return title
        return subject


# ============================================================================
# Concrete Strategy Implementations
# ============================================================================

class KnownSlugConstructionStrategy(URLConstructionStrategy):
    """
    Known Slug URL Construction (7-word slug, lowercase)
    Pattern: {domain}/news-releases/news-release-details/{slug}

    Used by: Companies with verified domain+slug URL patterns
    Each company must be individually tested to confirm this pattern works.
    There is NO auto-detection based on domain or platform.
    """

    def __init__(self):
        super().__init__('Known Slug Construction (7-word)')

    def construct(self, subject, ir_domain, email_date=None):
        try:
            # Clean subject
            subject = self._remove_email_prefixes(subject)

            # Extract words
            words = self._extract_words(subject)

            # Take first N words, lowercase, join with hyphens
            slug = '-'.join(words[:KNOWN_SLUG_WORD_COUNT]).lower()

            # Construct URL
            url = f"https://{ir_domain}{KNOWN_SLUG_PATH_TEMPLATE}{slug}"

            logger.info(f"Constructed known-slug URL: {url}")
            return url

        except Exception as e:
            logger.error(f"Error constructing known-slug URL: {e}")
            return None


# Legacy alias for backward compatibility
GCSHostedStrategy = KnownSlugConstructionStrategy


class KnownSlugConstruction9Strategy(URLConstructionStrategy):
    """
    Known Slug URL Construction with 9-word slug
    Pattern: {domain}/news-releases/news-release-details/{slug}

    Used by: Companies with verified 9-word slug patterns (SLG, SUI)
    """

    def __init__(self):
        super().__init__('Known Slug Construction (9-word)')

    def construct(self, subject, ir_domain, email_date=None):
        try:
            # Clean subject
            subject = self._remove_email_prefixes(subject)

            # Extract words
            words = self._extract_words(subject)

            # Take first 9 words, lowercase, join with hyphens
            slug = '-'.join(words[:KNOWN_SLUG_WORD_COUNT_9]).lower()

            # Construct URL
            url = f"https://{ir_domain}{KNOWN_SLUG_PATH_TEMPLATE}{slug}"

            logger.info(f"Constructed known-slug 9-word URL: {url}")
            return url

        except Exception as e:
            logger.error(f"Error constructing known-slug 9-word URL: {e}")
            return None


# Legacy alias for backward compatibility
GCS9WordStrategy = KnownSlugConstruction9Strategy


class BrixmorAspxStrategy(URLConstructionStrategy):
    """
    Brixmor ASPX URL Construction (case-sensitive slugs)
    Pattern: {domain}/news-presentations/press-releases/news-details/{YYYY}/{SUBJECT-SLUG}/default.aspx

    CRITICAL: Preserves original capitalization (case-sensitive URLs!)
    """

    def __init__(self):
        super().__init__('Brixmor ASPX (case-sensitive)')

    def construct(self, subject, ir_domain, email_date=None):
        try:
            # Clean subject
            subject = self._remove_email_prefixes(subject)

            # Extract title after company prefix
            title = self._extract_title_after_prefix(subject)

            # Extract words - PRESERVE CAPITALIZATION
            words = self._extract_words(title)

            # Create slug - NO LOWERCASE (case-sensitive URLs!)
            slug = '-'.join(words)

            # Get year (from email date or current year)
            year = email_date.year if email_date else datetime.utcnow().year

            # Construct Brixmor ASPX URL
            url = f"https://{ir_domain}/news-presentations/press-releases/news-details/{year}/{slug}/default.aspx"

            logger.info(f"Crafted Brixmor ASPX URL: {url}")
            return url

        except Exception as e:
            logger.error(f"Error crafting Brixmor ASPX URL: {e}")
            return None


class DirectURLStrategy(URLConstructionStrategy):
    """
    Direct URL Extraction from Email Body
    No construction needed - URLs are already in email

    This is a placeholder strategy that returns None,
    signaling that URLs should be extracted directly from email body.
    """

    def __init__(self):
        super().__init__('Direct URL (from email body)')

    def construct(self, subject, ir_domain, email_date=None):
        """
        Direct URL strategy doesn't construct - returns None to signal
        that URLs should be extracted from email body instead.
        """
        logger.info("Using direct URL extraction from email body")
        return None


class RedirectFollowStrategy(URLConstructionStrategy):
    """
    Redirect Following Strategy
    Follows notification/tracking URLs to get final press release URL

    This is a placeholder strategy that returns None,
    signaling that redirects should be followed in the main processing logic.
    """

    def __init__(self):
        super().__init__('Redirect Follow')

    def construct(self, subject, ir_domain, email_date=None):
        """
        Redirect follow strategy doesn't construct - returns None to signal
        that redirect following logic should be used.
        """
        logger.info("Using redirect follow strategy")
        return None


class EPRTScrapeListStrategy(URLConstructionStrategy):
    """
    EPRT-Specific Press Release List Scraping
    Scrapes press releases list page to find matching title

    This is a placeholder strategy that returns None,
    signaling that EPRT scraping logic should be used.
    """

    def __init__(self):
        super().__init__('EPRT Scrape List')

    def construct(self, subject, ir_domain, email_date=None):
        """
        EPRT strategy doesn't construct - returns None to signal
        that list scraping logic should be used.
        """
        logger.info("Using EPRT list scraping strategy")
        return None


# ============================================================================
# Strategy Router
# ============================================================================
# SOLID: Open/Closed - Add new strategies to this map without modifying code
#
# IMPORTANT: There is NO "GCS category" - known_slug_construction strategies
# are for companies with individually verified domain+slug patterns.
# Each company must be tested before adding to the overrides list.

URL_CONSTRUCTION_STRATEGIES = {
    # New canonical names (use these in new configs)
    'known_slug_construction': KnownSlugConstructionStrategy(),
    'known_slug_construction_9': KnownSlugConstruction9Strategy(),

    # Legacy aliases (backward compatibility - same implementations)
    'gcs_hosted': KnownSlugConstructionStrategy(),
    'gcs_custom_domain': KnownSlugConstructionStrategy(),
    'gcs_9_words': KnownSlugConstruction9Strategy(),
    'gcs_9_word_slug': KnownSlugConstruction9Strategy(),

    # Other strategies (unchanged)
    'brixmor_aspx': BrixmorAspxStrategy(),
    'direct_url': DirectURLStrategy(),
    'redirect_follow': RedirectFollowStrategy(),
    'eprt_scrape_list': EPRTScrapeListStrategy()
}


def get_url_strategy(construction_method):
    """
    Get URL construction strategy by method name

    Args:
        construction_method: Strategy name (e.g., 'gcs_hosted', 'brixmor_aspx')

    Returns:
        URLConstructionStrategy instance or None if not found
    """
    strategy = URL_CONSTRUCTION_STRATEGIES.get(construction_method)
    if not strategy:
        logger.warning(f"Unknown URL construction method: {construction_method}")
    return strategy
