"""
Scraper Layer: curl_cffi (TLS Fingerprinting)
==============================================
Layer 1: Fast TLS fingerprinting with session reuse

SOLID Principles:
- Single Responsibility: Only implements curl_cffi scraping
- Template Method: Inherits workflow from ScraperLayer
- Open/Closed: Can extend without modifying base class

Last Created: 2026-03-11
"""

import logging
import random
import time
from typing import Optional, Tuple

from scraper_base import ScraperLayer, TIMEOUT_LONG, TIMEOUT_SHORT, SEARCH_REFERRERS
from session_manager import (
    get_pooled_session,
    extract_homepage_url,
    network_timing_delay
)

logger = logging.getLogger()

# ============================================================================
# curl_cffi Availability Check
# ============================================================================

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    logger.warning("curl_cffi not available")


# ============================================================================
# curl_cffi Session Factory
# ============================================================================

def create_curl_cffi_session():
    """
    Create new curl_cffi session

    Single Responsibility: Only creates session

    Returns:
        curl_cffi.Session: New session with connection pooling
    """
    if not CURL_CFFI_AVAILABLE:
        return None

    try:
        # curl_cffi has built-in session pooling
        session = curl_requests.Session()
        return session
    except Exception as e:
        logger.error(f"Failed to create curl_cffi session: {e}")
        return None


# ============================================================================
# CurlCffiLayer Implementation
# ============================================================================

class CurlCffiLayer(ScraperLayer):
    """
    Layer 1: curl_cffi with TLS fingerprinting

    Strategy:
    - TLS fingerprinting (mimics Chrome 120)
    - Session pooling for connection reuse
    - Network timing delays
    - Homepage pre-fetching (warmup)
    - Google search referrer (organic traffic)

    Success rate: 70-85% (fastest layer)
    """

    def __init__(self):
        """Initialize curl_cffi layer"""
        super().__init__(layer_name='curl_cffi')

    def _is_available(self) -> bool:
        """
        Check if curl_cffi is available

        Returns:
            bool: True if available
        """
        return CURL_CFFI_AVAILABLE

    def _scrape_impl(self, url: str, domain: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Scrape using curl_cffi with TLS fingerprinting

        Single Responsibility: Only scrapes using curl_cffi

        Strategy:
        1. Get pooled session for connection reuse
        2. Network timing delay (mimic real browser)
        3. Pre-fetch homepage (session warmup)
        4. Main request with Chrome 120 TLS fingerprint
        5. Return result

        Args:
            url: URL to scrape
            domain: Domain name

        Returns:
            tuple: (html_content, final_url, status_code)
        """
        # Step 1: Get pooled session
        session = get_pooled_session(domain, session_factory=create_curl_cffi_session)
        if not session:
            self.logger.error("Failed to get curl_cffi session")
            return None, None, None

        # Step 2: Network timing delay
        network_timing_delay()

        # Step 3: Pre-fetch homepage (warmup)
        homepage = extract_homepage_url(url)
        if homepage and homepage != url:
            try:
                self.logger.info(f"Pre-fetching homepage for connection warmup")
                session.head(homepage, impersonate="chrome120", timeout=TIMEOUT_SHORT)
                time.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                self.logger.debug(f"Pre-fetch failed (non-fatal): {e}")

        # Step 4: Main request with perfect TLS fingerprint
        headers = {
            'Referer': random.choice(SEARCH_REFERRERS),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Cache-Control': 'max-age=0'
        }

        try:
            response = session.get(
                url,
                impersonate="chrome120",
                headers=headers,
                timeout=TIMEOUT_LONG,
                allow_redirects=True
            )

            # Step 5: Return result
            if response.status_code == 200:
                return response.text, response.url, 200
            else:
                self.logger.warning(f"HTTP {response.status_code}")
                return None, None, response.status_code

        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            return None, None, None

    def _record_result(self, domain: str, success: bool):
        """
        Record result for adaptive layer selection

        Single Responsibility: Only records results

        Default implementation: just log
        (Can be overridden to persist to database)

        Args:
            domain: Domain name
            success: Whether scraping succeeded
        """
        # Log result (can be extended to store in DynamoDB/S3)
        self.logger.info(f"Result: {domain} - curl_cffi - {'SUCCESS' if success else 'FAILED'}")


# ============================================================================
# Factory Function (Convenience)
# ============================================================================

def create_curl_cffi_layer() -> CurlCffiLayer:
    """
    Factory function to create CurlCffiLayer

    Single Responsibility: Only creates layer

    Returns:
        CurlCffiLayer: New layer instance
    """
    return CurlCffiLayer()
