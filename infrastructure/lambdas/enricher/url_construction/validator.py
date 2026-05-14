"""
URL Validator - HTTP Validation
================================
Single Responsibility: Validate URLs are accessible

IMPROVEMENT: Captures final URL even when timeout occurs during redirect following
"""

import logging
import requests
from config.constants import URL_VALIDATION_TIMEOUT, USER_AGENT, HTTP_STATUS_OK

logger = logging.getLogger()

MAX_REDIRECTS = 10  # Prevent infinite redirect loops


def validate_url_exists(url):
    """
    Validate URL is accessible (HTTP 200)

    IMPROVEMENT: Manually follows redirects so we capture the final URL even if
    the destination times out. This is critical for tracking URLs that redirect
    to slow-loading sites.

    Example:
        url9490.notification.gcs-web.com → www.alx-inc.com/news-releases/...
        Even if www.alx-inc.com times out, we still capture that final URL.

    Args:
        url: URL to validate

    Returns:
        tuple: (is_valid, final_url, status_code)
            - is_valid: True if final destination returned 200
            - final_url: Last URL in redirect chain (even on timeout!)
            - status_code: HTTP status (0 if timeout, 999 if too many redirects)
    """
    current_url = url
    redirect_count = 0

    try:
        while redirect_count < MAX_REDIRECTS:
            response = requests.head(
                current_url,
                timeout=URL_VALIDATION_TIMEOUT,
                allow_redirects=False,  # Manual redirect following
                headers={'User-Agent': USER_AGENT}
            )

            # Success - no more redirects
            if response.status_code == HTTP_STATUS_OK:
                logger.debug(f"URL validation: {response.status_code} for {current_url[:60]}...")
                return True, current_url, response.status_code

            # Redirect - follow it
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_url = response.headers.get('Location')
                if not redirect_url:
                    logger.warning(f"Redirect without Location header: {current_url[:60]}...")
                    return False, current_url, response.status_code

                # Handle relative redirects
                if redirect_url.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(current_url)
                    redirect_url = f"{parsed.scheme}://{parsed.netloc}{redirect_url}"

                logger.info(f"Following redirect: {current_url[:60]}... → {redirect_url[:60]}...")
                current_url = redirect_url
                redirect_count += 1
                continue

            # Other status code (404, 403, etc.)
            logger.warning(f"URL validation failed: {response.status_code} for {current_url[:60]}...")
            return False, current_url, response.status_code

        # Too many redirects
        logger.warning(f"Too many redirects (>{MAX_REDIRECTS}): {url[:60]}...")
        return False, current_url, 999

    except requests.Timeout:
        # CRITICAL: Return the last URL we reached, even though it timed out
        # This captures tracking URL → final URL redirects where the final site is slow
        logger.warning(f"URL validation timeout at: {current_url[:80]}...")
        logger.info(f"✓ Captured final URL despite timeout: {current_url[:80]}...")
        return False, current_url, 0  # Not valid (timed out), but we have the final URL!

    except Exception as e:
        logger.warning(f"URL validation failed: {e}")
        return False, current_url, 0  # Return last known URL, not original
