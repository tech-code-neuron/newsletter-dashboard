"""
URL Constructor - Strategy Pattern for URL Construction
=======================================================
Single Responsibility: Construct press release URLs using company-specific methods
"""

import re
import logging
from config.constants import (
    KNOWN_SLUG_PATH_TEMPLATE,
    KNOWN_SLUG_WORD_COUNT,
    KNOWN_SLUG_WORD_COUNT_LONG,
    # Legacy aliases
    GCS_URL_PATH_TEMPLATE,
    GCS_SLUG_WORD_COUNT,
    GCS_SLUG_WORD_COUNT_LONG
)

logger = logging.getLogger()


def create_slug_from_subject(subject, word_count=GCS_SLUG_WORD_COUNT, exclude_noise_words=True):
    """
    Create URL slug from email subject

    Example:
        "Essential Properties: Announces Dividend" → "essential-properties-announces-dividend"
        "SL Green at the One Madison" → "sl-green-one-madison" (excludes "at", "the")

    Args:
        subject: Email subject line
        word_count: Number of words to include in slug
        exclude_noise_words: Exclude common noise words (default: True)

    Returns:
        str: URL slug (lowercase, hyphenated)
    """
    if not subject:
        return ""

    # Common noise words to exclude from slugs
    # NOTE: "and" is kept (used in SLG and SUI slugs)
    NOISE_WORDS = {
        'of', 'for', 'as', 'to', 'a', 'an', 'the', 'in', 'on', 'at',
        'or', 'but', 'with', 'by', 'from'
    }

    # Remove common prefixes/noise
    clean = subject.lower()
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean)

    # Remove decimal points from numbers (e.g., "1.5" → "15", "$2.3" → "$23")
    clean = re.sub(r'(\d+)\.(\d+)', r'\1\2', clean)

    # Extract all alphanumeric words
    words = re.findall(r'\b[a-z0-9]+\b', clean)

    # Filter out noise words if enabled
    if exclude_noise_words:
        filtered_words = [w for w in words if w not in NOISE_WORDS]
    else:
        filtered_words = words

    # Take first N words
    slug_words = filtered_words[:word_count]

    # Join with hyphens
    slug = '-'.join(slug_words)

    return slug


def create_known_slug_url(subject, ir_domain, word_count=KNOWN_SLUG_WORD_COUNT):
    """
    Create known-slug press release URL (verified per-company pattern)

    Pattern: https://{domain}/news-releases/news-release-details/{slug}

    NOTE: This is NOT a "GCS" category - each company using this pattern
    must be individually verified before adding to URL_CONSTRUCTION_OVERRIDES.

    Args:
        subject: Email subject line
        ir_domain: Company IR domain
        word_count: Slug word count (7 or 9)

    Returns:
        str: Constructed URL or None
    """
    if not subject or not ir_domain:
        return None

    slug = create_slug_from_subject(subject, word_count=word_count)
    if not slug:
        return None

    url = f"https://{ir_domain}{KNOWN_SLUG_PATH_TEMPLATE}{slug}"

    logger.debug(f"Known-slug URL constructed: {url}")
    return url


# Legacy alias for backward compatibility
def create_gcs_url(subject, ir_domain, word_count=KNOWN_SLUG_WORD_COUNT):
    """Legacy alias for create_known_slug_url"""
    return create_known_slug_url(subject, ir_domain, word_count)


def create_brixmor_aspx_url(subject, ir_domain, email_date=None):
    """
    Create Brixmor-style ASPX URL

    Pattern: https://{domain}/{Slug}/default.aspx
    Note: Slug is CASE-SENSITIVE (preserves capitalization)

    Args:
        subject: Email subject line (PRESERVES CASE)
        ir_domain: Company IR domain
        email_date: Optional email date (unused but accepted for interface compatibility)

    Returns:
        str: Constructed URL or None
    """
    if not subject or not ir_domain:
        return None

    # Clean subject but PRESERVE CASE
    clean = subject
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean, flags=re.IGNORECASE)

    # Extract words (preserve case, remove punctuation)
    words = re.findall(r'\b[A-Za-z0-9]+\b', clean)
    slug_words = words[:GCS_SLUG_WORD_COUNT]

    # Join with hyphens (CASE PRESERVED)
    slug = '-'.join(slug_words)

    url = f"https://{ir_domain}/{slug}/default.aspx"

    logger.debug(f"Brixmor ASPX URL constructed: {url}")
    return url



# ============================================================================
# Strategy Pattern - URL Construction Strategies
# ============================================================================
# IMPORTANT: There is NO "GCS category" - known_slug_construction strategies
# are for companies with individually verified domain+slug patterns.

URL_CONSTRUCTION_STRATEGIES = {
    # New canonical names (use these in new configs)
    'known_slug_construction': lambda subject, domain, date=None: create_known_slug_url(subject, domain, KNOWN_SLUG_WORD_COUNT),
    'known_slug_construction_9': lambda subject, domain, date=None: create_known_slug_url(subject, domain, KNOWN_SLUG_WORD_COUNT_LONG),

    # Legacy aliases (backward compatibility)
    'gcs_hosted': lambda subject, domain, date=None: create_known_slug_url(subject, domain, KNOWN_SLUG_WORD_COUNT),
    'gcs_custom_domain': lambda subject, domain, date=None: create_known_slug_url(subject, domain, KNOWN_SLUG_WORD_COUNT),
    'gcs_9_word_slug': lambda subject, domain, date=None: create_known_slug_url(subject, domain, KNOWN_SLUG_WORD_COUNT_LONG),

    # Other strategies (unchanged)
    'brixmor_aspx': create_brixmor_aspx_url,
}


def construct_url_for_company(company, email_subject, email_date=None):
    """
    Construct URL using company-specific method

    Strategy Pattern: Routes to appropriate construction method

    Args:
        company: Company dictionary from DynamoDB
        email_subject: Email subject line
        email_date: Optional email date

    Returns:
        tuple: (url, method_used) or (None, None)
    """
    ticker = company.get('ticker', 'UNKNOWN')
    ir_domain = company.get('ir_domain')
    method = company.get('url_construction_method')

    if not ir_domain:
        logger.warning(f"No IR domain for {ticker}")
        return None, None

    if not method or method == 'direct_url':
        logger.debug(f"No URL construction method for {ticker}")
        return None, None

    # Strategy Pattern: O(1) lookup instead of if-elif chain
    strategy = URL_CONSTRUCTION_STRATEGIES.get(method)

    if not strategy:
        logger.warning(f"Unknown construction method: {method} for {ticker}")
        return None, None

    try:
        url = strategy(email_subject, ir_domain, email_date)
        return url, method
    except Exception as e:
        logger.error(f"Error constructing URL for {ticker} using {method}: {e}")
        return None, None
