"""
Enricher - URL Classification
==============================
Classify URLs as newswire or direct

SOLID Principles:
- Single Responsibility: Only classifies URLs
- No Hardcoded Values: Newswire domains from constants

Last Created: 2026-03-11
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger()

# Newswire domains (require scraping)
NEWSWIRE_DOMAINS = {
    'globenewswire.com',
    'businesswire.com',
    'prnewswire.com',
    'accesswire.com',
    'prnews.com',
    'marketwired.com'
}


def classify_url(url: str) -> str:
    """
    Classify URL type

    Single Responsibility: Only classifies URLs

    Args:
        url: URL to classify

    Returns:
        str: 'newswire', 'direct', or 'unknown'
    """
    domain = urlparse(url).netloc.lower()

    # Remove www. prefix for consistent matching
    domain = domain.replace('www.', '')

    if any(nw in domain for nw in NEWSWIRE_DOMAINS):
        return 'newswire'
    else:
        return 'direct'
