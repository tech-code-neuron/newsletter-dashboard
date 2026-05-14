"""
Parser - Domain Utilities
==========================
Extract domain from URLs

SOLID Principles:
- Single Responsibility: Only extracts domains
- Handles common patterns (www prefix removal, etc.)

Last Created: 2026-03-11
"""

import logging
from urllib.parse import urlparse
from typing import Optional

logger = logging.getLogger()


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract domain from URL, handling common patterns

    Single Responsibility: Only extracts domain

    Examples:
        "https://investors.terreno.com/press-releases" → "terreno.com"
        "https://alx.gcs-web.com/news" → "alx.gcs-web.com"
        "http://www.realty.com" → "realty.com"

    Args:
        url: URL string

    Returns:
        str: Domain (lowercase, www removed) or None
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www prefix
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain
    except Exception as e:
        logger.warning(f"Failed to extract domain from {url}: {e}")
        return None
