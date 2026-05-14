"""
Parser - Tracking URL Hint Extraction
======================================
Extract company ticker hints from tracking URL patterns

SOLID Principles:
- Single Responsibility: Only extracts ticker hints from tracking URLs
- No HTTP requests: Pattern-based extraction (<5ms)

Handles:
- GCS-Web company subdomains (alx.gcs-web.com → ALX)
- Q4 Inc company subdomains (terreno.q4inc.com → TERRENO)
- SendGrid query parameters (?c=EPRT, ?cid=terreno)

Why This Matters:
- Parser URL matching uses GSI on ir_domain (fast, 1-2ms)
- But tracking URLs have third-party domains: notification.gcs-web.com
- This extracts ticker hints from URL structure WITHOUT HTTP requests
- Falls back to Layer 2 confidence scoring if hint extraction fails

Created: 2026-03-16
"""

import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger()

# Reserved subdomains that are NOT company tickers
RESERVED_SUBDOMAINS = {
    'notification', 'alert', 'www', 'ir', 'investors',
    'news', 'press', 'email', 'events', 'api'
}


def extract_company_hint_from_tracking_url(url: str) -> Optional[str]:
    """
    Extract company ticker hint from tracking URL structure

    Single Responsibility: Pattern-based ticker extraction (no HTTP)

    Strategies:
    1. GCS-Web company subdomains: alx.gcs-web.com → ALX
    2. Q4 Inc company subdomains: terreno.q4inc.com → TERRENO
    3. SendGrid query parameters: ?c=EPRT → EPRT

    Examples:
        "https://alx.gcs-web.com/..." → "ALX"
        "https://terreno.q4inc.com/..." → "TERRENO"
        "https://url9490.ct.sendgrid.net/ls/click?c=EPRT" → "EPRT"
        "https://notification.gcs-web.com/..." → None (reserved subdomain)

    Args:
        url: Tracking URL

    Returns:
        str: Uppercase ticker hint, or None if no hint found
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Strategy 1: GCS-Web company-specific subdomains
        if domain.endswith('.gcs-web.com'):
            subdomain = domain.split('.')[0]
            if subdomain not in RESERVED_SUBDOMAINS:
                logger.debug(f"GCS-Web subdomain hint: {subdomain} from {url}")
                return subdomain.upper()

        # Strategy 2: Q4 Inc company-specific subdomains
        if domain.endswith('.q4inc.com') or domain.endswith('.q4web.com'):
            subdomain = domain.split('.')[0]
            if subdomain not in RESERVED_SUBDOMAINS:
                logger.debug(f"Q4 Inc subdomain hint: {subdomain} from {url}")
                return subdomain.upper()

        # Strategy 3: SendGrid query parameters
        if 'sendgrid.net' in domain:
            params = parse_qs(parsed.query)

            # Common parameter names for company identifier
            for param_name in ['c', 'cid', 'company', 'ticker']:
                if param_name in params:
                    hint = params[param_name][0]
                    if hint:
                        logger.debug(f"SendGrid param hint: {hint} from {url}")
                        return hint.upper()

        # No hint found
        return None

    except Exception as e:
        logger.warning(f"Failed to extract tracking hint from {url}: {e}")
        return None


def get_tracking_url_patterns() -> dict:
    """
    Get all tracking URL patterns for documentation/testing

    Returns:
        dict: Pattern descriptions and examples
    """
    return {
        'gcs_web': {
            'pattern': '{ticker}.gcs-web.com',
            'examples': [
                'https://alx.gcs-web.com/news/abc123',
                'https://ryman.gcs-web.com/press-releases'
            ]
        },
        'q4_inc': {
            'pattern': '{ticker}.q4inc.com or {ticker}.q4web.com',
            'examples': [
                'https://terreno.q4inc.com/investors',
                'https://eprt.q4web.com/news'
            ]
        },
        'sendgrid': {
            'pattern': 'sendgrid.net/...?c={ticker}',
            'examples': [
                'https://url9490.ct.sendgrid.net/ls/click?c=EPRT',
                'https://email.ct.sendgrid.net/click?cid=terreno'
            ]
        }
    }
