"""
Enricher - URL Construction Strategies
=======================================
Construct press release URLs using company-specific methods

SOLID Principles:
- Strategy Pattern: URL construction methods
- Single Responsibility: Only constructs URLs
- Open/Closed: Add methods by registering in strategy dict

Last Created: 2026-03-11
"""

import re
import logging
from typing import Optional, Tuple, Callable, Dict

logger = logging.getLogger()

# ============================================================================
# Constants
# ============================================================================

# GCS URL Construction
GCS_URL_PATH_TEMPLATE = '/news-releases/news-release-details/'
GCS_SLUG_WORD_COUNT = 7  # Standard GCS slug length
GCS_SLUG_WORD_COUNT_LONG = 9  # Extended slug for some companies


# ============================================================================
# Slug Creation
# ============================================================================

def create_slug_from_subject(subject: str, word_count: int = GCS_SLUG_WORD_COUNT) -> str:
    """
    Create URL slug from email subject

    Single Responsibility: Only creates slug

    Example:
        "Essential Properties: Announces Dividend" → "essential-properties-announces-dividend"

    Args:
        subject: Email subject line
        word_count: Number of words to include in slug

    Returns:
        str: URL slug (lowercase, hyphenated)
    """
    if not subject:
        return ""

    # Remove common prefixes/noise
    clean = subject.lower()
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean)

    # Extract first N words
    words = re.findall(r'\b[a-z0-9]+\b', clean)
    slug_words = words[:word_count]

    # Join with hyphens
    slug = '-'.join(slug_words)

    return slug


# ============================================================================
# URL Construction Methods
# ============================================================================

def create_gcs_url(subject: str, ir_domain: str, email_date: str = None) -> Optional[str]:
    """
    Create GCS-hosted press release URL

    Single Responsibility: Only constructs GCS URLs

    Pattern: https://{domain}/news-releases/news-release-details/{slug}

    Args:
        subject: Email subject line
        ir_domain: Company IR domain (e.g., "chatham.gcs-web.com")
        email_date: Optional email date (unused but accepted for interface compatibility)

    Returns:
        str: Constructed URL or None
    """
    if not subject or not ir_domain:
        return None

    slug = create_slug_from_subject(subject, word_count=GCS_SLUG_WORD_COUNT)
    if not slug:
        return None

    url = f"https://{ir_domain}{GCS_URL_PATH_TEMPLATE}{slug}"

    logger.debug(f"GCS URL constructed: {url}")
    return url


def create_gcs_url_long_slug(subject: str, ir_domain: str, email_date: str = None) -> Optional[str]:
    """
    Create GCS URL with 9-word slug (some companies use longer slugs)

    Single Responsibility: Only constructs GCS URLs with long slugs

    Args:
        subject: Email subject line
        ir_domain: Company IR domain
        email_date: Optional email date (unused)

    Returns:
        str: Constructed URL or None
    """
    if not subject or not ir_domain:
        return None

    slug = create_slug_from_subject(subject, word_count=GCS_SLUG_WORD_COUNT_LONG)
    if not slug:
        return None

    url = f"https://{ir_domain}{GCS_URL_PATH_TEMPLATE}{slug}"

    logger.debug(f"GCS URL (9-word slug) constructed: {url}")
    return url


def create_brixmor_aspx_url(subject: str, ir_domain: str, email_date: str = None) -> Optional[str]:
    """
    Create Brixmor-style ASPX URL

    Single Responsibility: Only constructs Brixmor ASPX URLs

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
# Strategy Pattern - URL Construction Registry
# ============================================================================

# URL Construction Strategy Router (Strategy Pattern)
# Maps method name → construction function
URL_CONSTRUCTION_STRATEGIES: Dict[str, Callable[[str, str, str], Optional[str]]] = {
    'gcs_hosted': create_gcs_url,
    'gcs_custom_domain': create_gcs_url,
    'gcs_9_word_slug': create_gcs_url_long_slug,
    'brixmor_aspx': create_brixmor_aspx_url,
}


def construct_url_for_company(company: dict, email_subject: str, email_date: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Construct URL using company-specific method

    Single Responsibility: Orchestrates URL construction

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


# ============================================================================
# Strategy Registration (Open/Closed Principle)
# ============================================================================

def register_url_construction_method(method_name: str, construction_function: Callable) -> None:
    """
    Register new URL construction method (Open/Closed Principle)

    Single Responsibility: Only registers methods

    Allows adding new methods without modifying existing code

    Args:
        method_name: Method name (e.g., "custom_method")
        construction_function: Function that constructs URLs
    """
    URL_CONSTRUCTION_STRATEGIES[method_name] = construction_function
    logger.info(f"Registered URL construction method: {method_name}")


def unregister_url_construction_method(method_name: str) -> None:
    """
    Unregister URL construction method

    Single Responsibility: Only unregisters methods

    Args:
        method_name: Method name to remove
    """
    if method_name in URL_CONSTRUCTION_STRATEGIES:
        del URL_CONSTRUCTION_STRATEGIES[method_name]
        logger.info(f"Unregistered URL construction method: {method_name}")
