"""
Parser - URL Filtering
=======================
Filter press release URLs (exclude logos, unsubscribe, landing pages)

SOLID Principles:
- Single Responsibility: Only filters URLs
- No Hardcoded Values: All patterns from constants.py

Last Created: 2026-03-11
Last Modified: 2026-03-13 (switched to shared landing page detector)
"""

import re
import os
import sys
import logging
from typing import Optional
from constants import (
    EXCLUDE_PATTERNS,
    PRESS_RELEASE_PATTERNS,
)

# Add shared modules to path (shared is at same level as parser directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.landing_page_detector import is_landing_page as shared_is_landing_page

logger = logging.getLogger()


def is_press_release_url(url: str) -> bool:
    """
    Check if URL is likely a press release (not logo/unsubscribe/etc.)

    Single Responsibility: Only filters URLs

    Args:
        url: URL string

    Returns:
        bool: True if likely press release, False otherwise
    """
    if not url:
        return False

    url_lower = url.lower()

    # Exclude known non-press-release patterns
    for pattern in EXCLUDE_PATTERNS:
        if pattern in url_lower:
            return False

    # Check if landing page (generic /news/ or /press-releases/)
    if is_landing_page(url):
        return False

    # Check if URL matches positive press release patterns
    has_pr_pattern = any(pattern in url_lower for pattern in PRESS_RELEASE_PATTERNS)

    # If has press release keyword pattern, definitely keep it
    if has_pr_pattern:
        return True

    # Allow tracking/notification URLs (they redirect to press releases)
    if 'notification' in url_lower or 'click' in url_lower or 'redirect' in url_lower:
        return True

    # Parse URL to check if it's just a homepage
    try:
        path = url_lower.split('//')[1].split('?')[0]  # Get domain+path without query
        path_after_domain = '/'.join(path.split('/')[1:])  # Get everything after domain

        # If no path after domain, it's just homepage
        if not path_after_domain or path_after_domain == '':
            return False

        # If path has substantial content (not just "/" or single char), keep it
        if len(path_after_domain) > 10:
            return True

    except IndexError:
        # If URL parsing fails, err on the side of keeping it
        return True

    return False


def is_landing_page(url: str) -> bool:
    """
    Check if URL is a landing page (not a specific press release)

    DELEGATES to shared/landing_page_detector.py for single source of truth.

    Args:
        url: URL string

    Returns:
        bool: True if landing page, False otherwise
    """
    return shared_is_landing_page(url)


def filter_press_release_urls(urls: list) -> list:
    """
    Filter list of URLs to only press release URLs

    Single Responsibility: Only filters URL list

    Args:
        urls: List of URLs

    Returns:
        list: Filtered URLs (only press release URLs)
    """
    return [url for url in urls if is_press_release_url(url)]
