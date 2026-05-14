"""
Scraper Layer: cloudscraper (Cloudflare Solver)
================================================
Layer 2: Cloudflare challenge solver with session warmup

SOLID Principles:
- Single Responsibility: Only implements cloudscraper scraping
- Template Method: Inherits workflow from ScraperLayer
- Open/Closed: Can extend without modifying base class

Last Created: 2026-03-11
"""

import logging
import random
import time
from typing import Optional, Tuple

from scraper_base import ScraperLayer, TIMEOUT_LONG, TIMEOUT_MEDIUM, SEARCH_REFERRERS
from session_manager import extract_homepage_url

logger = logging.getLogger()

# ============================================================================
# cloudscraper Availability Check
# ============================================================================

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    logger.warning("cloudscraper not available")


# ============================================================================
# CloudscraperLayer Implementation
# ============================================================================

class CloudscraperLayer(ScraperLayer):
    """
    Layer 2: cloudscraper (Cloudflare challenge solver)

    Strategy:
    - Cloudflare challenge solver (JS challenges, CAPTCHAs)
    - Session warmup (visit homepage)
    - Enhanced browser headers
    - Google search referrer

    Success rate: 60-80% (good for Cloudflare-protected sites)
    """

    def __init__(self):
        """Initialize cloudscraper layer"""
        super().__init__(layer_name='cloudscraper')

    def _is_available(self) -> bool:
        """
        Check if cloudscraper is available

        Returns:
            bool: True if available
        """
        return CLOUDSCRAPER_AVAILABLE

    def _scrape_impl(self, url: str, domain: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Scrape using cloudscraper (Cloudflare solver)

        Single Responsibility: Only scrapes using cloudscraper

        Strategy:
        1. Create scraper with Chrome profile
        2. Session warmup (visit homepage)
        3. Enhanced headers
        4. Main request
        5. Return result

        Args:
            url: URL to scrape
            domain: Domain name

        Returns:
            tuple: (html_content, final_url, status_code)
        """
        # Step 1: Create scraper with Chrome profile
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True
            }
        )

        # Step 2: Session warmup - visit homepage first
        homepage = extract_homepage_url(url)
        if homepage and homepage != url:
            try:
                self.logger.info(f"Session warmup: visiting homepage")
                scraper.get(homepage, timeout=TIMEOUT_MEDIUM)
                time.sleep(random.uniform(1, 3))
            except Exception as e:
                self.logger.debug(f"Warmup failed (non-fatal): {e}")

        # Step 3: Enhanced headers
        scraper.headers.update({
            'Referer': random.choice(SEARCH_REFERRERS),
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document'
        })

        # Step 4: Main request
        try:
            response = scraper.get(url, timeout=TIMEOUT_LONG)

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

        Args:
            domain: Domain name
            success: Whether scraping succeeded
        """
        self.logger.info(f"Result: {domain} - cloudscraper - {'SUCCESS' if success else 'FAILED'}")


# ============================================================================
# Factory Function
# ============================================================================

def create_cloudscraper_layer() -> CloudscraperLayer:
    """
    Factory function to create CloudscraperLayer

    Returns:
        CloudscraperLayer: New layer instance
    """
    return CloudscraperLayer()
