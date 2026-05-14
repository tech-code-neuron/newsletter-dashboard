"""
Session Manager - Connection Pooling and Warmup
================================================
Manages HTTP sessions with connection pooling and session warmup

SOLID Principles:
- Single Responsibility: Only manages sessions
- Dependency Injection: Sessions can be tested independently
- Open/Closed: Can extend with new session types

Last Created: 2026-03-11
"""

import logging
import random
import time
from typing import Dict, Optional

logger = logging.getLogger()

# ============================================================================
# Module-Level Session Pool (Persists Across Lambda Invocations)
# ============================================================================

# Session pool: domain → session object
# Persists across Lambda warm starts for connection reuse
SESSION_POOL: Dict[str, any] = {}

# Session pool size limit
MAX_POOL_SIZE = 50

# ============================================================================
# Session Pool Management
# ============================================================================


def get_pooled_session(domain: str, session_factory=None):
    """
    Get or create pooled session for domain

    Single Responsibility: Only manages session pooling

    Sessions are cached per domain for connection reuse
    (Lambda containers reuse sessions across invocations)

    Args:
        domain: Domain name (key for pooling)
        session_factory: Optional factory function to create new session

    Returns:
        Session object or None
    """
    global SESSION_POOL

    # Check if session exists in pool
    if domain in SESSION_POOL:
        logger.debug(f"Reusing pooled session for {domain}")
        return SESSION_POOL[domain]

    # Create new session if pool not full
    if len(SESSION_POOL) >= MAX_POOL_SIZE:
        logger.warning(f"Session pool full ({MAX_POOL_SIZE}), clearing oldest")
        # Simple eviction: clear random entry
        if SESSION_POOL:
            evict_domain = random.choice(list(SESSION_POOL.keys()))
            del SESSION_POOL[evict_domain]

    # Create new session
    if session_factory:
        try:
            session = session_factory()
            SESSION_POOL[domain] = session
            logger.debug(f"Created new session for {domain}")
            return session
        except Exception as e:
            logger.error(f"Failed to create session for {domain}: {e}")
            return None

    return None


def clear_session_pool():
    """
    Clear all pooled sessions

    Single Responsibility: Only clears pool

    Useful for:
    - Testing
    - Memory cleanup
    - Forcing fresh sessions
    """
    global SESSION_POOL
    SESSION_POOL.clear()
    logger.info("Session pool cleared")


# ============================================================================
# Session Warmup Strategies
# ============================================================================


def warmup_http_session(session, homepage: str, target_url: str):
    """
    Warm up HTTP session by visiting homepage first

    Single Responsibility: Only warms up HTTP session

    Strategy:
    1. Visit homepage with HEAD request
    2. Human-like delay (0.5-1.5s)
    3. Ready for target URL request

    Args:
        session: HTTP session object (requests.Session or curl_cffi.Session)
        homepage: Homepage URL
        target_url: Target URL (for logging)

    Returns:
        bool: Success
    """
    if not homepage or homepage == target_url:
        return True

    try:
        logger.info(f"Warming up session: {homepage[:60]}...")

        # Visit homepage (HEAD request for speed)
        session.head(homepage, timeout=5)

        # Human-like delay
        time.sleep(random.uniform(0.5, 1.5))

        logger.debug("Session warmup complete")
        return True

    except Exception as e:
        logger.warning(f"Session warmup failed (non-fatal): {e}")
        return False


def warmup_browser_session(page, homepage: str, target_url: str):
    """
    Warm up browser session with human-like behavior

    Single Responsibility: Only warms up browser session

    Strategy (multi-step):
    1. Visit homepage
    2. Random scrolling (3 positions)
    3. Random mouse movement
    4. Human-like delays between actions
    5. Ready for target URL

    Args:
        page: Browser page object (Playwright or Selenium)
        homepage: Homepage URL
        target_url: Target URL

    Returns:
        bool: Success
    """
    if not homepage or homepage == target_url:
        return True

    try:
        logger.info(f"Multi-step warmup: homepage → scroll → delay → target")

        # Step 1: Visit homepage
        page.goto(homepage, wait_until='domcontentloaded', timeout=30000)
        time.sleep(random.uniform(1.5, 3.0))

        # Step 2: Human-like scrolling pattern
        for i in range(3):
            scroll_y = random.randint(200, 500)
            page.evaluate(f"window.scrollTo(0, {scroll_y * (i+1)});")
            time.sleep(random.uniform(0.3, 0.8))

        # Step 3: Random mouse movement simulation
        if hasattr(page, 'mouse'):
            page.mouse.move(random.randint(100, 500), random.randint(100, 500))

        time.sleep(random.uniform(0.5, 1.5))

        logger.debug("Browser warmup complete")
        return True

    except Exception as e:
        logger.warning(f"Browser warmup failed (non-fatal): {e}")
        return False


def warmup_selenium_session(driver, homepage: str, target_url: str):
    """
    Warm up Selenium session with human-like behavior

    Single Responsibility: Only warms up Selenium session

    Strategy:
    1. Visit homepage
    2. Scroll to middle of page
    3. Human-like delay (2-4s)
    4. Ready for target URL

    Args:
        driver: Selenium WebDriver
        homepage: Homepage URL
        target_url: Target URL

    Returns:
        bool: Success
    """
    if not homepage or homepage == target_url:
        return True

    try:
        logger.info(f"Session warmup: homepage → delay → target")

        # Step 1: Visit homepage
        driver.get(homepage)
        time.sleep(random.uniform(2, 4))

        # Step 2: Scroll a bit (human behavior)
        driver.execute_script("window.scrollTo(0, 300);")
        time.sleep(random.uniform(0.5, 1.5))

        logger.debug("Selenium warmup complete")
        return True

    except Exception as e:
        logger.warning(f"Selenium warmup failed (non-fatal): {e}")
        return False


# ============================================================================
# Network Timing Simulation
# ============================================================================


def network_timing_delay():
    """
    Add random network timing delay

    Single Responsibility: Only adds network delay

    Simulates realistic network latency patterns (100-500ms)
    """
    delay = random.uniform(0.1, 0.5)
    time.sleep(delay)


def human_delay(min_seconds: float = 1.0, max_seconds: float = 3.0):
    """
    Add human-like delay

    Single Responsibility: Only adds human delay

    Args:
        min_seconds: Minimum delay
        max_seconds: Maximum delay
    """
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


# ============================================================================
# Homepage URL Extraction
# ============================================================================


def extract_homepage_url(url: str) -> Optional[str]:
    """
    Extract homepage URL from full URL

    Single Responsibility: Only extracts homepage

    Example:
        "https://investors.terreno.com/press/123" → "https://investors.terreno.com"

    Args:
        url: Full URL

    Returns:
        str: Homepage URL (scheme + netloc) or None
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception as e:
        logger.warning(f"Failed to extract homepage from {url}: {e}")
        return None


# ============================================================================
# Domain Extraction
# ============================================================================


def extract_domain(url: str) -> Optional[str]:
    """
    Extract domain from URL

    Single Responsibility: Only extracts domain

    Example:
        "https://investors.terreno.com/press/123" → "terreno.com"

    Args:
        url: URL string

    Returns:
        str: Domain (lowercase, www removed) or None
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]

        # Remove subdomain for pooling key (keep parent domain)
        parts = domain.split('.')
        if len(parts) > 2:
            # Keep last 2 parts (e.g., investors.terreno.com → terreno.com)
            domain = '.'.join(parts[-2:])

        return domain

    except Exception as e:
        logger.warning(f"Failed to extract domain from {url}: {e}")
        return None
