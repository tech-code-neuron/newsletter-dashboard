"""
Parser - URL Classification
============================
Classify URLs as newswire, redirect, or direct

SOLID Principles:
- Single Responsibility: Only classifies URL type
- No Hardcoded Values: All constants from constants.py

Last Created: 2026-03-11
"""

import logging
from constants import NEWSWIRE_DOMAINS, REDIRECT_DOMAINS

logger = logging.getLogger()


def classify_url(url: str) -> str:
    """
    Classify URL as newswire, redirect, or direct

    Single Responsibility: Only classifies URL type

    Args:
        url: URL string

    Returns:
        str: 'newswire', 'redirect', or 'direct'
    """
    from .domain_utils import extract_domain_from_url

    domain = extract_domain_from_url(url)
    if not domain:
        return 'direct'

    # Check if newswire
    if domain in NEWSWIRE_DOMAINS:
        return 'newswire'

    # Check if redirect
    if domain in REDIRECT_DOMAINS or 'notification' in url.lower() or 'sendgrid' in url.lower():
        return 'redirect'

    return 'direct'
