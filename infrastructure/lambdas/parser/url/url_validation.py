"""
Parser - URL Validation
========================
Check if URL is accessible (not 404)

SOLID Principles:
- Single Responsibility: Only validates URL accessibility
- Uses session for connection pooling

Last Created: 2026-03-11
"""

import logging
import requests
from typing import Tuple
from constants import URL_VALIDATION_TIMEOUT_SECONDS, USER_AGENT_FULL
from .http_session import get_http_session

logger = logging.getLogger()


def validate_url_exists(url: str, timeout: int = URL_VALIDATION_TIMEOUT_SECONDS) -> Tuple[bool, str, int]:
    """
    Check if URL is accessible (not 404)

    Single Responsibility: Only validates URL accessibility

    UPDATED 2026-03-10: Uses session for connection pooling and full browser headers

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        tuple: (is_valid, final_url, status_code)
    """
    session = get_http_session()

    try:
        response = session.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={'User-Agent': USER_AGENT_FULL}
        )

        final_url = response.url if response.history else url
        is_valid = response.status_code == 200

        return is_valid, final_url, response.status_code

    except requests.Timeout:
        logger.warning(f"Timeout validating URL: {url[:60]}...")
        return False, url, 0
    except requests.RequestException as e:
        logger.warning(f"Error validating URL {url[:60]}...: {e}")
        return False, url, 0
