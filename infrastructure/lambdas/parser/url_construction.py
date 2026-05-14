"""
Parser Lambda - URL Construction
=================================
Company-specific URL construction methods

SOLID Principles:
- Single Responsibility: Each method constructs ONE URL type
- Open/Closed: Add new methods without modifying existing
- No Hardcoded Values: All constants imported

Last Updated: 2026-03-09
"""

import re
import logging
from datetime import datetime
from constants import (
    KNOWN_SLUG_PATH_TEMPLATE,
    KNOWN_SLUG_WORD_COUNT,
    KNOWN_SLUG_WORD_COUNT_LONG,
    # Legacy aliases
    GCS_URL_PATH_TEMPLATE,
    GCS_SLUG_WORD_COUNT,
    GCS_SLUG_WORD_COUNT_LONG
)

logger = logging.getLogger()

# ============================================================================
# Slug Generation
# ============================================================================


def create_slug_from_subject(subject, word_count=KNOWN_SLUG_WORD_COUNT):
    """
    Create URL slug from email subject

    Single Responsibility: Only creates slug

    Example:
        "Essential Properties: Announces Dividend" → "essential-properties-announces-dividend"

    Args:
        subject: Email subject line
        word_count: Number of words to include in slug

    Returns:
        str: URL slug
    """
    if not subject:
        return ""

    # Remove common prefixes/noise
    clean = subject.lower()
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean)  # Email reply/forward prefixes

    # Extract first N words
    words = re.findall(r'\b[a-z0-9]+\b', clean)
    slug_words = words[:word_count]

    # Join with hyphens
    slug = '-'.join(slug_words)

    return slug


# ============================================================================
# Known Slug URL Construction (per-company verified patterns)
# ============================================================================
# NOTE: There is NO "GCS category" - these functions are for companies
# with verified domain+slug URL patterns (individually tested per-company)


def create_known_slug_url(subject, ir_domain):
    """
    Create known-slug press release URL (7-word pattern)

    Single Responsibility: Only constructs known-slug URLs

    Used by companies with verified domain+slug patterns.
    Each company must be individually tested before adding to overrides.

    Args:
        subject: Email subject line
        ir_domain: Company IR domain

    Returns:
        str: Constructed URL
    """
    if not subject or not ir_domain:
        return None

    # Create 7-word slug
    slug = create_slug_from_subject(subject, word_count=KNOWN_SLUG_WORD_COUNT)
    if not slug:
        return None

    # Build URL: https://{domain}/news-releases/news-release-details/{slug}
    url = f"https://{ir_domain}{KNOWN_SLUG_PATH_TEMPLATE}{slug}"

    logger.debug(f"Known-slug URL: {url}")
    return url


def create_known_slug_9_word_url(subject, ir_domain):
    """
    Create known-slug URL with 9-word slug

    Single Responsibility: Only constructs 9-word known-slug URLs

    Args:
        subject: Email subject line
        ir_domain: Company IR domain

    Returns:
        str: Constructed URL
    """
    if not subject or not ir_domain:
        return None

    # Create 9-word slug
    slug = create_slug_from_subject(subject, word_count=KNOWN_SLUG_WORD_COUNT_LONG)
    if not slug:
        return None

    # Build URL
    url = f"https://{ir_domain}{KNOWN_SLUG_PATH_TEMPLATE}{slug}"

    logger.debug(f"Known-slug 9-word URL: {url}")
    return url


# Legacy aliases for backward compatibility
def create_gcs_url_from_subject(subject, ir_domain):
    """Legacy alias for create_known_slug_url"""
    return create_known_slug_url(subject, ir_domain)


def create_gcs_9_word_url(subject, ir_domain):
    """Legacy alias for create_known_slug_9_word_url"""
    return create_known_slug_9_word_url(subject, ir_domain)


# ============================================================================
# ASPX URL Construction (Brixmor Pattern)
# ============================================================================


def create_brixmor_aspx_url(subject, ir_domain, email_date=None):
    """
    Create Brixmor-style ASPX URL from subject

    Single Responsibility: Only constructs Brixmor ASPX URLs

    Pattern: https://{domain}/{slug}/default.aspx
    Note: Slug is CASE-SENSITIVE (preserves original capitalization)

    Examples:
        Subject: "Brixmor: Announces Dividend"
        → https://investors.brixmor.com/Brixmor-Announces-Dividend/default.aspx

    Args:
        subject: Email subject line (PRESERVES CASE)
        ir_domain: Company IR domain
        email_date: Optional email date (for date-stamped URLs)

    Returns:
        str: Constructed URL
    """
    if not subject or not ir_domain:
        return None

    # Clean subject but PRESERVE CASE
    clean = subject
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean, flags=re.IGNORECASE)

    # Extract words (preserve case, remove punctuation)
    words = re.findall(r'\b[A-Za-z0-9]+\b', clean)
    slug_words = words[:KNOWN_SLUG_WORD_COUNT]

    # Join with hyphens (CASE PRESERVED)
    slug = '-'.join(slug_words)

    # Build URL: https://{domain}/{Slug}/default.aspx
    url = f"https://{ir_domain}/{slug}/default.aspx"

    logger.debug(f"Brixmor ASPX URL: {url}")
    return url


# ============================================================================
# URL Construction Router (Strategy Pattern)
# ============================================================================


def construct_url_for_company(company, email_subject, email_date=None):
    """
    Construct press release URL using company-specific method

    Single Responsibility: Orchestrates URL construction

    Strategy Pattern: Routes to appropriate construction method

    Args:
        company: Company dictionary
        email_subject: Email subject line
        email_date: Optional email date

    Returns:
        tuple: (url, method_used) or (None, None)
    """
    ticker = company.get('ticker', 'UNKNOWN')
    ir_domain = company.get('ir_domain')

    if not ir_domain:
        logger.warning(f"No IR domain for {ticker}")
        return None, None

    # Get construction method from company record
    method = company.get('url_construction_method')

    # Strategy pattern: Route to appropriate method
    # New canonical names
    if method == 'known_slug_construction':
        url = create_known_slug_url(email_subject, ir_domain)
        return url, method

    elif method == 'known_slug_construction_9':
        url = create_known_slug_9_word_url(email_subject, ir_domain)
        return url, method

    # Legacy aliases (backward compatibility)
    elif method == 'gcs_hosted' or method == 'gcs_custom_domain':
        url = create_known_slug_url(email_subject, ir_domain)
        return url, method

    elif method == 'gcs_9_word_slug':
        url = create_known_slug_9_word_url(email_subject, ir_domain)
        return url, method

    # Other strategies (unchanged)
    elif method == 'brixmor_aspx':
        url = create_brixmor_aspx_url(email_subject, ir_domain, email_date)
        return url, method

    else:
        # No specific construction method
        logger.debug(f"No URL construction method for {ticker}")
        return None, None
