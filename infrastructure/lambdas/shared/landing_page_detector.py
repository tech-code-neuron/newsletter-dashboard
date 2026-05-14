"""
Landing Page Detector - Single Source of Truth
================================================
SOLID: Single Responsibility - Detect landing pages across all Lambdas

PURPOSE:
--------
Prevents publishing generic landing pages (e.g., /press-releases/2026) to production.
Landing pages are list pages, not specific press releases.

USED BY:
--------
- Enricher: Validate before saving to DynamoDB
- Scraper: Block saves of landing pages
- Playwright Scraper: Replace fallback save with review queue
- Pre-commit: Validate no duplication exists

DETECTION METHODS:
------------------
1. Generic segments: URL ends with /press-releases, /news, etc.
2. Year-based paths: URL ends with /press-releases/2026
3. Short paths: Domain + ≤1 segment (e.g., company.com/news)

EXAMPLES:
---------
Landing pages (REJECT):
  - https://ir.parkhotels.com/press-releases/2026
  - https://investors.company.com/news-releases
  - https://company.com/investors

Specific press releases (ACCEPT):
  - https://ir.rymanhp.com/news-releases/news-release-details/ryman-hospitality-...
  - https://investors.company.com/news/2026/01/company-announces-earnings

Created: 2026-03-13
Last Modified: 2026-03-13
"""

from typing import Optional


# ============================================================================
# Landing Page Patterns (Single Source of Truth)
# ============================================================================

GENERIC_PAGE_SEGMENTS = {
    'news-releases',
    'news',
    'press-releases',
    'news-and-events',
    'investors',
    'press-room',
    'media',
    'newsroom',
    'investor-relations',
    'ir',  # Common IR abbreviation
    'press',
}


# ============================================================================
# Landing Page Detection
# ============================================================================

def is_landing_page(url: str) -> bool:
    """
    Check if URL is a generic landing page (not a specific press release)

    Landing pages are generic URLs that show lists of press releases,
    not individual press release content.

    Detection logic:
    1. Generic segments: Last segment is in GENERIC_PAGE_SEGMENTS
    2. Year-based paths: Last segment is a year (2000-2100) with generic parent
    3. Short paths: Domain + ≤1 segment

    Args:
        url: Full URL string

    Returns:
        bool: True if URL is a landing page (should be rejected)

    Examples:
        >>> is_landing_page('https://ir.parkhotels.com/press-releases/2026')
        True
        >>> is_landing_page('https://ir.company.com/news-releases')
        True
        >>> is_landing_page('https://ir.rymanhp.com/news/2026/01/earnings-report')
        False
    """
    if not url:
        return False

    # Normalize URL: remove trailing slash, parse path
    url = url.rstrip('/')
    path_parts = url.split('/')

    # Extract path segments (skip protocol + domain)
    # ['https:', '', 'ir.company.com', 'press-releases', '2026']
    # -> ['press-releases', '2026']
    path_segments = [s for s in path_parts[3:] if s]

    if not path_segments:
        return True  # Just domain = landing page

    # Get last segment
    last_segment = path_segments[-1].lower()

    # Method 1: Generic segment check
    # Example: /press-releases, /news, /investors
    if last_segment in GENERIC_PAGE_SEGMENTS:
        return True

    # Method 1b: Root-level default page check (ASP.NET, PHP, HTML defaults)
    # Only flag as landing page when at shallow depth (1-2 segments)
    # Example LANDING: https://ir.stagindustrial.com/default.aspx (1 segment)
    # Example OK: https://investors.brixmor.com/.../BRIXMOR-ANNOUNCES-.../default.aspx (deep path)
    DEFAULT_PAGE_FILES = {'default.aspx', 'index.html', 'index.php', 'default.html', 'index.aspx'}
    if last_segment in DEFAULT_PAGE_FILES and len(path_segments) <= 2:
        return True

    # Method 2: Year-based path check
    # Example: /press-releases/2026, /news/2025
    if last_segment.isdigit() and 2000 <= int(last_segment) <= 2100:
        # Check if parent segment is generic
        if len(path_segments) >= 2:
            parent_segment = path_segments[-2].lower()
            if parent_segment in GENERIC_PAGE_SEGMENTS:
                return True  # /press-releases/2026 IS a landing page

    # Method 3: Short path check
    # Example: company.com/news (domain + 1 segment)
    if len(path_segments) <= 1:
        # Exception: Some companies use /news/press-release-title format
        # Only flag if the single segment is generic
        if path_segments[0].lower() in GENERIC_PAGE_SEGMENTS:
            return True

    return False


def get_landing_page_reason(url: str) -> Optional[str]:
    """
    Get human-readable reason why URL is a landing page

    Useful for debugging and manual review queue messages.

    Args:
        url: Full URL string

    Returns:
        str: Reason if landing page, None otherwise

    Examples:
        >>> get_landing_page_reason('https://ir.company.com/press-releases/2026')
        'Year-based path: /press-releases/2026 (generic parent)'
        >>> get_landing_page_reason('https://ir.company.com/news-releases')
        'Generic segment: news-releases'
        >>> get_landing_page_reason('https://ir.company.com/news/2026/01/earnings')
        None
    """
    if not url:
        return None

    url = url.rstrip('/')
    path_parts = url.split('/')
    path_segments = [s for s in path_parts[3:] if s]

    if not path_segments:
        return "Empty path (domain only)"

    last_segment = path_segments[-1].lower()

    # Check 1: Generic segment
    if last_segment in GENERIC_PAGE_SEGMENTS:
        return f"Generic segment: {last_segment}"

    # Check 1b: Root-level default page files (only at shallow depth)
    DEFAULT_PAGE_FILES = {'default.aspx', 'index.html', 'index.php', 'default.html', 'index.aspx'}
    if last_segment in DEFAULT_PAGE_FILES and len(path_segments) <= 2:
        return f"Root-level default page: {last_segment}"

    # Check 2: Year-based path
    if last_segment.isdigit() and 2000 <= int(last_segment) <= 2100:
        if len(path_segments) >= 2:
            parent_segment = path_segments[-2].lower()
            if parent_segment in GENERIC_PAGE_SEGMENTS:
                return f"Year-based path: /{parent_segment}/{last_segment} (generic parent)"

    # Check 3: Short path
    if len(path_segments) <= 1:
        if path_segments[0].lower() in GENERIC_PAGE_SEGMENTS:
            return f"Short path with generic segment: {path_segments[0]}"

    return None


# ============================================================================
# Utility Page Detection (Optional - for completeness)
# ============================================================================

def is_utility_page(url: str) -> bool:
    """
    Check if URL is unsubscribe/preferences/etc. (not press release content)

    Utility pages should be filtered out early in the pipeline.

    Args:
        url: Full URL string

    Returns:
        bool: True if URL is a utility page
    """
    utility_patterns = [
        '/unsubscribe',
        '/email-alert',
        '/preferences',
        '/manage-alerts',
        '/manage-subscriptions',
        '/opt-out',
        '/activate',
        '/email-activation',
        '/investor-email-alerts',  # Q4 Inc email signup pages
        '/email-alerts',
        # Legal/policy pages (footer links, not PRs)
        '/legal/',
        '/privacy/',
        '/terms/',
        '/cookie',
    ]
    return any(pattern in url.lower() for pattern in utility_patterns)
