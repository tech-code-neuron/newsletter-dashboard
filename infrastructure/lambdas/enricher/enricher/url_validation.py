"""
Enricher - URL Validation
==========================
Validate URL accessibility (HTTP HEAD requests)

SOLID Principles:
- Single Responsibility: Only validates URLs
- Uses HTTP HEAD for efficiency (no body download)

Last Created: 2026-03-11
"""

import logging
import requests
from typing import Tuple

logger = logging.getLogger()

# Constants
URL_VALIDATION_TIMEOUT = 5  # HTTP HEAD request timeout (seconds)
HTTP_STATUS_OK = 200
USER_AGENT = 'Mozilla/5.0 (compatible; REITSheet/1.0; +https://reitsheet.co)'


def validate_url_exists(url: str) -> Tuple[bool, str, int]:
    """
    Validate URL is accessible (HTTP 200)

    Single Responsibility: Only validates URLs

    Uses HTTP HEAD request for efficiency (no body download)

    Args:
        url: URL to validate

    Returns:
        tuple: (is_valid, final_url, status_code)
    """
    try:
        response = requests.head(
            url,
            timeout=URL_VALIDATION_TIMEOUT,
            allow_redirects=True,
            headers={'User-Agent': USER_AGENT}
        )

        final_url = response.url if response.history else url
        is_valid = response.status_code == HTTP_STATUS_OK

        logger.debug(f"URL validation: {response.status_code} for {url[:60]}...")
        return is_valid, final_url, response.status_code

    except requests.Timeout:
        logger.warning(f"URL validation timeout: {url[:60]}...")
        return False, url, 0
    except Exception as e:
        logger.warning(f"URL validation failed: {e}")
        return False, url, 0
