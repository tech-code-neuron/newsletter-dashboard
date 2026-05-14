"""
Enricher - URL Selection
=========================
Select best URL from email via domain matching and redirect resolution

SOLID Principles:
- Single Responsibility: Only selects URLs
- Domain matching: Prioritizes URLs matching company domains
- Redirect resolution: Follows tracking URLs to final destination

Last Created: 2026-03-11
"""

import logging
import requests
from urllib.parse import urlparse
from typing import Optional, List

logger = logging.getLogger()

# Constants
REDIRECT_TIMEOUT = 10  # Redirect following timeout (seconds)

# Tracking URL domains that need redirect resolution
TRACKING_DOMAINS = {'sendgrid.net', 'ct.sendgrid.net', 'links.', 'click.', 'track.'}

# Paths to exclude from URL selection
EXCLUDE_PATHS = ['unsubscribe', 'email-alert', 'preferences', 'manage-alerts']


def select_best_url_from_email(urls: List[str], company: dict) -> Optional[str]:
    """
    Select the URL that best matches the company's press release domain

    Single Responsibility: Only selects URLs based on domain matching

    Strategy:
        1. Follow redirects for tracking URLs (SendGrid, etc.)
        2. Match resolved URLs against press_release_url domain/path
        3. Return best match

    Priority (after redirect resolution):
        1. URLs matching press_release_url domain/path pattern
        2. URLs matching ir_domain
        3. First URL (fallback)

    Args:
        urls: List of URLs from email
        company: Company config dict with press_release_url, ir_domain

    Returns:
        str: Best matching URL
    """
    if not urls:
        return None

    if len(urls) == 1:
        return urls[0]

    press_release_url = company.get('press_release_url', '')
    ir_domain = company.get('ir_domain', '')

    # Extract domain and path pattern from press_release_url
    pr_domain = None
    pr_path_pattern = None

    if press_release_url:
        parsed = urlparse(press_release_url)
        pr_domain = parsed.netloc
        pr_path_parts = parsed.path.split('/')
        # Get the main path component (e.g., "/news-1/news-releases/")
        pr_path_pattern = '/'.join([p for p in pr_path_parts if p and p != 'default.aspx'])

    # Resolve URLs if they're tracking links
    resolved_urls = []
    for url in urls:
        parsed_url = urlparse(url)

        # Check if this is a tracking URL
        is_tracking = any(domain in parsed_url.netloc for domain in TRACKING_DOMAINS)

        if is_tracking:
            # Follow redirect to get real destination
            try:
                logger.info(f"Following tracking URL: {url[:60]}...")
                response = requests.head(url, allow_redirects=True, timeout=REDIRECT_TIMEOUT)
                final_url = response.url
                resolved_urls.append((final_url, url))  # (final_url, original_url)
                logger.info(f"  → Resolved to: {final_url[:80]}...")
            except Exception as e:
                logger.warning(f"Failed to resolve tracking URL ({e}), using original")
                resolved_urls.append((url, url))
        else:
            resolved_urls.append((url, url))

    # Now match resolved URLs against company domains
    # Priority 1: Match press_release_url domain + path pattern
    if pr_domain and pr_path_pattern:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if pr_domain in parsed_url.netloc and pr_path_pattern in parsed_url.path:
                logger.info(f"✓ Selected URL matching press release pattern: {final_url[:80]}...")
                return final_url

    # Priority 2: Match press_release_url domain only (exclude non-PR paths)
    if pr_domain:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if pr_domain in parsed_url.netloc:
                # Exclude obvious non-PR paths
                if not any(exclude in parsed_url.path.lower() for exclude in EXCLUDE_PATHS):
                    logger.info(f"✓ Selected URL matching PR domain: {final_url[:80]}...")
                    return final_url

    # Priority 3: Match ir_domain (exclude non-PR paths)
    if ir_domain:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if ir_domain in parsed_url.netloc:
                # Exclude non-PR paths
                if not any(exclude in parsed_url.path.lower() for exclude in EXCLUDE_PATHS):
                    logger.info(f"✓ Selected URL matching IR domain: {final_url[:80]}...")
                    return final_url

    # Fallback: First resolved URL (but log warning)
    first_final, first_original = resolved_urls[0]
    logger.warning(f"No domain match found, using first URL: {first_final[:80]}...")
    return first_final
