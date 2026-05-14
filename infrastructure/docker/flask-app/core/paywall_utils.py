"""
Access Indicator Utilities

Detects paywalled and login-required news sources.
"""
from urllib.parse import urlparse

PAYWALLED_DOMAINS = {'nytimes.com', 'wsj.com', 'ft.com', 'bloomberg.com'}
LOGIN_REQUIRED_DOMAINS = {'bisnow.com'}


def is_paywalled_url(url: str) -> bool:
    """Check if URL is from a paywalled domain."""
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower().removeprefix('www.')
        return any(domain == d or domain.endswith('.' + d) for d in PAYWALLED_DOMAINS)
    except Exception:
        return False


def is_login_required_url(url: str) -> bool:
    """Check if URL requires login (e.g., Bisnow)."""
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower().removeprefix('www.')
        return any(domain == d or domain.endswith('.' + d) for d in LOGIN_REQUIRED_DOMAINS)
    except Exception:
        return False


def get_access_indicator(url: str) -> str:
    """
    Get access indicator text for a URL.

    Returns:
        "(Paywall)" for paywalled sites (WSJ, NYT, FT, Bloomberg)
        "(Login Required)" for login-required sites (Bisnow)
        "" for free/open sites
    """
    if is_paywalled_url(url):
        return "(Paywall)"
    if is_login_required_url(url):
        return "(Login Required)"
    return ""
