"""
URL Detector - Landing Page & Utility Page Detection
====================================================
Single Responsibility: Detect URL types (landing pages, utility pages)

NOTE: This module imports from shared/landing_page_detector.py
      to ensure single source of truth for landing page detection.
"""

import os
import sys

# Add shared modules to path (Lambda and local dev)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

try:
    from shared.landing_page_detector import is_landing_page as shared_is_landing_page
    from shared.landing_page_detector import GENERIC_PAGE_SEGMENTS
except ImportError:
    from landing_page_detector import is_landing_page as shared_is_landing_page
    from landing_page_detector import GENERIC_PAGE_SEGMENTS


def is_landing_page(url):
    """
    Check if URL is a generic landing page (no specific content)

    DELEGATES to shared/landing_page_detector.py for single source of truth.

    Args:
        url: Full URL string

    Returns:
        bool: True if URL appears to be a landing page
    """
    return shared_is_landing_page(url)


def is_utility_page(url):
    """
    Check if URL is unsubscribe/preferences/etc.

    Args:
        url: Full URL string

    Returns:
        bool: True if URL is a utility page
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)

    # Check URL fragment (e.g., #unsubscribe)
    if parsed.fragment and 'unsubscribe' in parsed.fragment.lower():
        return True

    utility_patterns = [
        '/unsubscribe', '/email-alert', '/preferences',
        '/manage-alerts', '/manage-subscriptions', '/opt-out',
        '/investor-email-alerts', '/email-alerts'
    ]
    return any(pattern in url.lower() for pattern in utility_patterns)


def get_path_depth(url):
    """
    Count path segments after domain

    Args:
        url: Full URL string

    Returns:
        int: Number of path segments
    """
    path_segments = [s for s in url.split('/')[3:] if s]
    return len(path_segments)
