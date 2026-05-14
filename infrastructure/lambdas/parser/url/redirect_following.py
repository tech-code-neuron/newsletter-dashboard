"""
Parser - Redirect Following
============================
Follow URL redirects to get final destination

SOLID Principles:
- Single Responsibility: Only follows redirects
- HEAD/GET fallback for better reliability
- Exponential backoff + jitter for retry logic

Last Created: 2026-03-11
"""

import logging
import time
import requests
from typing import Tuple
from constants import (
    REDIRECT_TIMEOUT_SECONDS,
    REDIRECT_MAX_REDIRECTS,
    REDIRECT_MAX_RETRIES,
    GCS_REDIRECT_TIMEOUT_SECONDS,
    SENDGRID_REDIRECT_TIMEOUT_SECONDS,
    USER_AGENT_FULL
)
from .http_session import get_http_session
from .domain_utils import extract_domain_from_url

logger = logging.getLogger()


# ============================================================================
# Legacy Redirect Following (Simple HEAD Request)
# ============================================================================

def follow_redirect_url(url: str, max_redirects: int = REDIRECT_MAX_REDIRECTS, timeout: int = REDIRECT_TIMEOUT_SECONDS) -> str:
    """
    Follow URL redirects to get final destination

    Single Responsibility: Only follows redirects

    LEGACY: Use follow_redirect_with_fallback() for better reliability

    Args:
        url: URL to follow
        max_redirects: Maximum redirects to follow
        timeout: Request timeout in seconds

    Returns:
        str: Final URL or original URL if failed
    """
    session = get_http_session()

    try:
        response = session.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={'User-Agent': USER_AGENT_FULL}
        )

        # Return final URL after redirects
        final_url = response.url

        # If redirected, log it
        if response.history:
            logger.info(f"Followed {len(response.history)} redirect(s): {url[:50]}... → {final_url[:50]}...")

        return final_url

    except requests.Timeout:
        logger.warning(f"Timeout following redirect: {url[:60]}...")
        return url
    except requests.RequestException as e:
        logger.warning(f"Error following redirect {url[:60]}...: {e}")
        return url


def follow_redirect_to_final_url(url: str, timeout: int = REDIRECT_TIMEOUT_SECONDS) -> Tuple[str, bool, int]:
    """
    Follow redirect and validate final URL

    Single Responsibility: Orchestrates redirect + validation

    Args:
        url: URL to follow
        timeout: Request timeout in seconds

    Returns:
        tuple: (final_url, is_valid, status_code)
    """
    from .url_validation import validate_url_exists

    # Follow redirects
    final_url = follow_redirect_url(url, timeout=timeout)

    # Validate final URL
    is_valid, validated_url, status_code = validate_url_exists(final_url, timeout=timeout)

    return validated_url if is_valid else final_url, is_valid, status_code


# ============================================================================
# Advanced Redirect Following (HEAD/GET Fallback)
# ============================================================================

def _follow_redirect_head(url: str, timeout: int, max_retries: int) -> Tuple[str, bool]:
    """
    HEAD request with exponential backoff retry

    Single Responsibility: Only handles HEAD requests with retry

    Args:
        url: URL to follow
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts

    Returns:
        tuple: (final_url, success)
    """
    session = get_http_session()

    for attempt in range(max_retries):
        try:
            response = session.head(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={'User-Agent': USER_AGENT_FULL}
            )

            if response.status_code in [200, 301, 302]:
                return response.url, True

        except requests.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"Timeout attempt {attempt+1}/{max_retries}, retry in {wait_time}s")
                time.sleep(wait_time)
                continue
            logger.warning(f"HEAD timeout after {max_retries} attempts")
            return url, False

        except requests.RequestException as e:
            logger.warning(f"HEAD failed: {e}")
            return url, False

    return url, False


def _follow_redirect_get(url: str, timeout: int, max_retries: int) -> Tuple[str, bool, str]:
    """
    GET request with full browser headers (SendGrid, anti-bot)

    Single Responsibility: Only handles GET requests with retry

    Used for:
    - SendGrid /ls/click tracking URLs (HEAD fails with 403)
    - Cloudflare-protected sites
    - Anti-bot systems requiring full browser headers

    Args:
        url: URL to follow
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts

    Returns:
        tuple: (final_url, success, method_used)
    """
    session = get_http_session()

    for attempt in range(max_retries):
        try:
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={
                    'User-Agent': USER_AGENT_FULL,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
            )

            if response.status_code in [200, 301, 302]:
                return response.url, True, 'GET'

        except requests.Timeout:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                base_wait = 2 ** attempt  # 1s, 2s, 4s
                jitter = time.time() % 1  # Random jitter 0-1s
                wait_time = base_wait + (0.5 * jitter)  # Add 0-50% jitter
                logger.warning(f"GET timeout attempt {attempt+1}/{max_retries}, retry in {wait_time:.1f}s")
                time.sleep(wait_time)
                continue
            return url, False, 'GET_TIMEOUT'

        except requests.RequestException as e:
            logger.warning(f"GET failed: {e}")
            return url, False, 'GET_ERROR'

    return url, False, 'GET_FAILED'


def follow_redirect_with_fallback(url: str, timeout: int = REDIRECT_TIMEOUT_SECONDS, max_retries: int = REDIRECT_MAX_RETRIES) -> Tuple[str, bool, str]:
    """
    Follow redirects with HEAD/GET fallback and retry logic

    Single Responsibility: Only follows redirects with smart fallback

    Strategy:
    1. Detect domain type (GCS, SendGrid, standard)
    2. SendGrid /ls/click → Use GET immediately (HEAD fails)
    3. GCS domains → Use 60s timeout (observed high latency)
    4. Others → Try HEAD first, fallback to GET if timeout/403
    5. Exponential backoff retry: 1s, 2s, 4s

    This fixes the 20% redirect success rate issue:
    - SendGrid tracking URLs require GET with browser headers
    - GCS domains need longer timeout (60s vs 30s)
    - Retry logic handles transient failures

    Args:
        url: URL to follow
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts

    Returns:
        tuple: (final_url, success, method_used)
    """
    # Extract domain for timeout selection
    domain = extract_domain_from_url(url)

    # GCS domains need 60s+ timeout (observed high latency)
    if domain and 'gcs-web.com' in domain:
        timeout = GCS_REDIRECT_TIMEOUT_SECONDS  # 60s
        logger.info(f"Using extended timeout for GCS domain: {timeout}s")

    # SendGrid click tracking requires GET (HEAD fails)
    if '/ls/click' in url or 'sendgrid' in url.lower():
        logger.info("SendGrid URL detected, using GET immediately")
        return _follow_redirect_get(url, SENDGRID_REDIRECT_TIMEOUT_SECONDS, max_retries)

    # Try HEAD first (faster, no body transfer)
    final_url, success = _follow_redirect_head(url, timeout, max_retries)
    if success:
        logger.info(f"HEAD redirect successful: {url[:40]}... → {final_url[:40]}...")
        return final_url, True, 'HEAD'

    # Fallback to GET if HEAD failed
    logger.info(f"HEAD failed, trying GET: {url[:60]}...")
    return _follow_redirect_get(url, timeout, max_retries)
