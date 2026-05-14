"""
Parser Lambda - URL Utilities
==============================
URL extraction, filtering, validation, and redirect following

SOLID Refactoring (2026-03-19):
- Created RedirectFollower class (consolidates 5 redirect functions)
- Added DomainTimeoutRegistry for domain-specific timeouts
- Uses Strategy pattern for redirect methods (HEAD/GET)

SOLID Principles:
- Single Responsibility: Each class/function does ONE thing
- Open/Closed: Easy to add new domain timeout rules
- DRY: Redirect logic consolidated in one place

Last Updated: 2026-03-19 (SOLID refactoring)
"""

import re
import os
import sys
import logging
import requests
import time
from dataclasses import dataclass
from typing import Optional, Tuple, List, Callable
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from constants import (
    EXCLUDE_PATTERNS,
    PRESS_RELEASE_PATTERNS,
    PRESS_RELEASE_LINK_KEYWORDS,
    REDIRECT_DOMAINS,
    REDIRECT_TIMEOUT_SECONDS,
    REDIRECT_MAX_REDIRECTS,
    URL_VALIDATION_TIMEOUT_SECONDS,
    GCS_REDIRECT_TIMEOUT_SECONDS,
    SENDGRID_REDIRECT_TIMEOUT_SECONDS,
    REDIRECT_MAX_RETRIES,
    NEWSWIRE_DOMAINS,
    USER_AGENT_FULL
)

# Import from shared module (works in both dev and Lambda deployment)
_shared_path_lambda = os.path.join(os.path.dirname(__file__), 'shared')
_shared_path_dev = os.path.join(os.path.dirname(__file__), '..', 'shared')
if os.path.exists(_shared_path_lambda):
    sys.path.insert(0, _shared_path_lambda)
else:
    sys.path.insert(0, _shared_path_dev)
from landing_page_detector import is_landing_page as shared_is_landing_page

logger = logging.getLogger()


# ============================================================================
# Domain Timeout Registry (SOLID: Open/Closed - easy to add new domains)
# ============================================================================


class DomainTimeoutRegistry:
    """
    Registry for domain-specific timeout configurations.

    SOLID: Open/Closed - Add new domains without modifying code.
    """

    # Domain patterns and their timeouts
    DOMAIN_TIMEOUTS = {
        'gcs-web.com': GCS_REDIRECT_TIMEOUT_SECONDS,  # 60s - high latency
        'sendgrid': SENDGRID_REDIRECT_TIMEOUT_SECONDS,  # 45s
    }

    # Domains that require GET instead of HEAD
    GET_REQUIRED_PATTERNS = ['/ls/click', 'sendgrid']

    @classmethod
    def get_timeout(cls, url: str, default: int = REDIRECT_TIMEOUT_SECONDS) -> int:
        """Get timeout for URL based on domain patterns."""
        url_lower = url.lower()
        for pattern, timeout in cls.DOMAIN_TIMEOUTS.items():
            if pattern in url_lower:
                logger.info(f"Using extended timeout for {pattern}: {timeout}s")
                return timeout
        return default

    @classmethod
    def requires_get(cls, url: str) -> bool:
        """Check if URL requires GET instead of HEAD."""
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in cls.GET_REQUIRED_PATTERNS)

# ============================================================================
# HTTP Session with Connection Pooling (Phase 1 Optimization)
# ============================================================================

# Module-level HTTP session with connection pooling
# Persists across Lambda invocations in same container (warm starts)
HTTP_SESSION = None


def get_http_session():
    """
    Get or create HTTP session with connection pooling

    Single Responsibility: Only manages HTTP session

    Connection pool settings:
    - Pool size: 10 connections
    - Max retries: 0 (we handle retries ourselves)
    - Timeout: Configurable per request

    Returns:
        requests.Session: Configured session with connection pooling
    """
    global HTTP_SESSION

    if HTTP_SESSION is None:
        HTTP_SESSION = requests.Session()

        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0  # We handle retries ourselves
        )

        HTTP_SESSION.mount('http://', adapter)
        HTTP_SESSION.mount('https://', adapter)

        logger.info("Created HTTP session with connection pooling")

    return HTTP_SESSION

# URL extraction regex
URL_PATTERN = re.compile(r'https?://[^\s<>"]+')


# ============================================================================
# Redirect Follower (SOLID: Consolidates 5 redirect functions)
# ============================================================================


@dataclass
class RedirectResult:
    """Result of a redirect follow attempt."""
    final_url: str
    success: bool
    method: str  # 'HEAD', 'GET', 'HEAD_TIMEOUT', etc.


class RedirectFollower:
    """
    Follow URL redirects with smart HEAD/GET fallback.

    SOLID: Single Responsibility - Only handles redirect following.
    DRY: Consolidates _follow_redirect_head, _follow_redirect_get,
         follow_redirect_url, follow_redirect_to_final_url, and
         follow_redirect_with_fallback into ONE class.

    Strategy:
    1. Check if URL requires GET (SendGrid /ls/click)
    2. Use domain-specific timeout (GCS = 60s, SendGrid = 45s)
    3. Try HEAD first (faster, no body transfer)
    4. Fall back to GET if HEAD fails
    5. Exponential backoff retry on timeout
    """

    # Full browser headers for GET requests (anti-bot bypass)
    GET_HEADERS = {
        'User-Agent': USER_AGENT_FULL,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    @classmethod
    def follow(
        cls,
        url: str,
        timeout: Optional[int] = None,
        max_retries: int = REDIRECT_MAX_RETRIES
    ) -> RedirectResult:
        """
        Follow redirects with smart HEAD/GET fallback.

        Args:
            url: URL to follow
            timeout: Request timeout (auto-detected from domain if None)
            max_retries: Maximum retry attempts

        Returns:
            RedirectResult with final_url, success, and method
        """
        # Get domain-specific timeout
        if timeout is None:
            timeout = DomainTimeoutRegistry.get_timeout(url)

        # Check if GET is required (SendGrid, etc.)
        if DomainTimeoutRegistry.requires_get(url):
            logger.info("URL requires GET (anti-bot), skipping HEAD")
            return cls._follow_with_get(url, timeout, max_retries)

        # Try HEAD first (faster)
        result = cls._follow_with_head(url, timeout, max_retries)
        if result.success:
            return result

        # Fall back to GET
        logger.info(f"HEAD failed, trying GET: {url[:60]}...")
        return cls._follow_with_get(url, timeout, max_retries)

    @classmethod
    def _follow_with_head(cls, url: str, timeout: int, max_retries: int) -> RedirectResult:
        """Follow with HEAD request and retry logic."""
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
                    logger.info(f"HEAD redirect successful: {url[:40]}... → {response.url[:40]}...")
                    return RedirectResult(response.url, True, 'HEAD')

            except requests.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"HEAD timeout {attempt+1}/{max_retries}, retry in {wait_time}s")
                    time.sleep(wait_time)
                    continue

            except requests.RequestException as e:
                logger.warning(f"HEAD failed: {e}")
                return RedirectResult(url, False, 'HEAD_ERROR')

        return RedirectResult(url, False, 'HEAD_TIMEOUT')

    @classmethod
    def _follow_with_get(cls, url: str, timeout: int, max_retries: int) -> RedirectResult:
        """Follow with GET request (full browser headers)."""
        session = get_http_session()

        for attempt in range(max_retries):
            try:
                response = session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=cls.GET_HEADERS
                )

                if response.status_code in [200, 301, 302]:
                    return RedirectResult(response.url, True, 'GET')

            except requests.Timeout:
                if attempt < max_retries - 1:
                    base_wait = 2 ** attempt
                    jitter = time.time() % 1
                    wait_time = base_wait + (0.5 * jitter)
                    logger.warning(f"GET timeout {attempt+1}/{max_retries}, retry in {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue

            except requests.RequestException as e:
                logger.warning(f"GET failed: {e}")
                return RedirectResult(url, False, 'GET_ERROR')

        return RedirectResult(url, False, 'GET_TIMEOUT')


# ============================================================================
# URL Extraction with Fuzzy Logic
# ============================================================================


def extract_urls_with_context(html_body, plain_body=None):
    """
    Extract URLs with link text context for prioritization

    Single Responsibility: Extracts URLs with context from HTML/plain text

    This fixes the "missed PR links" issue by:
    1. Extracting link text from HTML <a> tags
    2. Scoring URLs by likelihood of being the PR link
    3. Prioritizing "View Press Release", "Read More", etc.

    Priority scoring:
    - 100: Link text contains "press release", "full article", "read more", etc.
    - 50: URL domain matches company IR domain (checked later)
    - 10: URL contains /news/ or /press/ or /release/ or /detail/
    - 1: Any other URL

    Args:
        html_body: HTML email body
        plain_body: Plain text email body (fallback)

    Returns:
        list: Tuples of (url, link_text, priority_score) sorted by priority (highest first)
    """
    urls_with_context = []

    # Parse HTML to extract <a> tags with link text
    if html_body:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_body, 'html.parser')  # Using built-in parser (no lxml needed)

            for link in soup.find_all('a', href=True):
                url = link['href']
                link_text = link.get_text(strip=True).lower()

                # Calculate priority score
                score = 1

                # High priority: Link text contains PR keywords
                if any(kw in link_text for kw in PRESS_RELEASE_LINK_KEYWORDS):
                    score = 100
                    logger.info(f"High-priority PR link found (text: '{link_text[:40]}'): {url[:60]}...")

                # Medium priority: URL contains PR path patterns
                elif any(p in url.lower() for p in ['/news/', '/press/', '/release/', '/detail/', '/newsroom/']):
                    score = 10

                urls_with_context.append((url, link_text, score))

        except ImportError:
            logger.warning("BeautifulSoup not available - falling back to plain text extraction")
        except Exception as e:
            logger.warning(f"Error parsing HTML for URL context: {e}")

    # Fallback: Extract URLs from plain text (no context, score=1)
    if plain_body and not urls_with_context:
        plain_urls = URL_PATTERN.findall(plain_body)
        urls_with_context = [(url.rstrip('.,;:)]}'), '', 1) for url in plain_urls]

    # Sort by priority score (highest first)
    urls_with_context.sort(key=lambda x: x[2], reverse=True)

    return urls_with_context


def extract_urls_from_email(msg):
    """
    Extract URLs from email message with priority scoring

    Single Responsibility: Orchestrates email parsing + URL extraction

    Returns URLs sorted by priority (most likely PR link first)

    Args:
        msg: Email message object

    Returns:
        list: URLs sorted by priority (highest first)
    """
    html_body = None
    plain_body = None

    # Extract HTML and plain text bodies
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            try:
                if content_type == 'text/html':
                    html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                elif content_type == 'text/plain':
                    plain_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            except Exception as e:
                logger.warning(f"Error decoding email part ({content_type}): {e}")
    else:
        try:
            plain_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except Exception as e:
            logger.warning(f"Error decoding email payload: {e}")

    # Extract URLs with context and priority
    urls_with_context = extract_urls_with_context(html_body, plain_body)

    # Return URLs only (already sorted by priority)
    return [url for url, _, _ in urls_with_context]


# ============================================================================
# URL Extraction (Legacy - Plain Text Only)
# ============================================================================


def extract_urls_from_text(text):
    """
    Extract all URLs from text using regex

    Single Responsibility: Only extracts URLs

    DEPRECATED: Use extract_urls_from_email() for priority-based extraction

    Args:
        text: Plain text content

    Returns:
        list: URLs found in text
    """
    if not text:
        return []

    urls = URL_PATTERN.findall(text)
    # Clean up URLs (remove trailing punctuation)
    return [url.rstrip('.,;:)]}') for url in urls]


# ============================================================================
# URL Filtering
# ============================================================================


def is_press_release_url(url):
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


def is_landing_page(url):
    """
    Check if URL is a landing page (not a specific press release)

    DELEGATES to shared/landing_page_detector.py for single source of truth.

    Args:
        url: URL string

    Returns:
        bool: True if landing page, False otherwise
    """
    return shared_is_landing_page(url)


# ============================================================================
# URL Classification
# ============================================================================


def classify_url(url):
    """
    Classify URL as newswire, redirect, or direct

    Single Responsibility: Only classifies URL type

    Args:
        url: URL string

    Returns:
        str: 'newswire', 'redirect', or 'direct'
    """
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


# ============================================================================
# Domain Extraction
# ============================================================================


def extract_domain_from_url(url):
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


# ============================================================================
# URL Validation
# ============================================================================


def validate_url_exists(url, timeout=URL_VALIDATION_TIMEOUT_SECONDS):
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


# ============================================================================
# Redirect Following (LEGACY WRAPPERS - Use RedirectFollower class)
# ============================================================================


def follow_redirect_url(url, max_redirects=REDIRECT_MAX_REDIRECTS, timeout=REDIRECT_TIMEOUT_SECONDS):
    """
    DEPRECATED: Use RedirectFollower.follow() instead.

    Follow URL redirects to get final destination.
    """
    result = RedirectFollower.follow(url, timeout=timeout)
    return result.final_url


def follow_redirect_to_final_url(url, timeout=REDIRECT_TIMEOUT_SECONDS):
    """
    Follow redirect and validate final URL.

    DEPRECATED: Use RedirectFollower.follow() + validate_url_exists().
    """
    result = RedirectFollower.follow(url, timeout=timeout)
    is_valid, validated_url, status_code = validate_url_exists(result.final_url, timeout=timeout)
    return validated_url if is_valid else result.final_url, is_valid, status_code


def _follow_redirect_head(url, timeout, max_retries):
    """DEPRECATED: Use RedirectFollower._follow_with_head() instead."""
    result = RedirectFollower._follow_with_head(url, timeout, max_retries)
    return result.final_url, result.success


def _follow_redirect_get(url, timeout, max_retries):
    """DEPRECATED: Use RedirectFollower._follow_with_get() instead."""
    result = RedirectFollower._follow_with_get(url, timeout, max_retries)
    return result.final_url, result.success, result.method


def follow_redirect_with_fallback(url, timeout=REDIRECT_TIMEOUT_SECONDS, max_retries=REDIRECT_MAX_RETRIES):
    """
    Follow redirects with HEAD/GET fallback and retry logic.

    SOLID: Delegates to RedirectFollower.follow() - consolidates 5 functions.

    Args:
        url: URL to follow
        timeout: Request timeout in seconds (auto-detected from domain if None)
        max_retries: Maximum retry attempts

    Returns:
        tuple: (final_url, success, method_used)
    """
    result = RedirectFollower.follow(url, timeout=timeout, max_retries=max_retries)
    return result.final_url, result.success, result.method
