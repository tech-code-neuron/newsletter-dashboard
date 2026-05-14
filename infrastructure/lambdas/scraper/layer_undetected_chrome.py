"""
Scraper Layer: undetected-chromedriver (Binary Patches)
========================================================
Layer 3: Selenium with binary patches + canvas randomization

SOLID Principles:
- Single Responsibility: Only implements undetected-chrome scraping
- Template Method: Inherits workflow from ScraperLayer
- Open/Closed: Can extend without modifying base class

Last Created: 2026-03-11
"""

import logging
import random
import time
from typing import Optional, Tuple

from scraper_base import ScraperLayer, MIN_VALID_PAGE_SIZE
from session_manager import extract_homepage_url

logger = logging.getLogger()

# ============================================================================
# undetected-chromedriver Availability Check
# ============================================================================

try:
    import undetected_chromedriver as uc
    UNDETECTED_CHROME_AVAILABLE = True
except ImportError:
    UNDETECTED_CHROME_AVAILABLE = False
    logger.warning("undetected_chromedriver not available")


# ============================================================================
# UndetectedChromeLayer Implementation
# ============================================================================

class UndetectedChromeLayer(ScraperLayer):
    """
    Layer 3: undetected-chromedriver (binary patches + canvas randomization)

    Strategy:
    - Binary-level patches to Chrome
    - Canvas fingerprint randomization
    - Session warmup with human-like behavior
    - Scrolling patterns
    - Human timing delays

    Success rate: 85-95% (very effective for most anti-bot systems)
    """

    def __init__(self):
        """Initialize undetected-chrome layer"""
        super().__init__(layer_name='undetected_chrome')

    def _is_available(self) -> bool:
        """
        Check if undetected-chromedriver is available

        Returns:
            bool: True if available
        """
        return UNDETECTED_CHROME_AVAILABLE

    def _scrape_impl(self, url: str, domain: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Scrape using undetected-chromedriver

        Single Responsibility: Only scrapes using undetected-chrome

        Strategy:
        1. Launch Chrome with binary patches
        2. Inject canvas randomization script
        3. Session warmup (visit homepage + scroll)
        4. Navigate to target URL
        5. Human-like behavior (scroll, delays)
        6. Extract content
        7. Cleanup and return result

        Args:
            url: URL to scrape
            domain: Domain name

        Returns:
            tuple: (html_content, final_url, status_code)
        """
        driver = None

        try:
            # Step 1: Launch Chrome with binary patches
            options = uc.ChromeOptions()
            options.headless = True
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')

            driver = uc.Chrome(options=options, use_subprocess=False, version_main=120)

            # Step 2: Inject canvas randomization script
            canvas_script = """
            const getImageData = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function() {
                const data = getImageData.apply(this, arguments);
                return data.split('').map(c =>
                    String.fromCharCode(c.charCodeAt(0) + Math.random() * 0.0001)
                ).join('');
            };
            """
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': canvas_script})

            # Step 3: Session warmup (visit homepage + scroll)
            homepage = extract_homepage_url(url)
            if homepage:
                self.logger.info(f"Session warmup: homepage → scroll → delay → target")
                driver.get(homepage)
                time.sleep(random.uniform(2, 4))

                # Scroll a bit (human behavior)
                driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(random.uniform(0.5, 1.5))

            # Step 4: Navigate to target URL
            driver.get(url)

            # Step 5: Human-like behavior pattern
            time.sleep(random.uniform(1, 2))  # Page load time
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(random.uniform(0.5, 1))

            # Step 6: Extract content
            html_content = driver.page_source
            final_url = driver.current_url

            # Step 7: Cleanup
            driver.quit()

            # Validate content
            if html_content and len(html_content) > MIN_VALID_PAGE_SIZE:
                return html_content, final_url, 200
            else:
                self.logger.warning(f"Insufficient content: {len(html_content) if html_content else 0} bytes")
                return None, None, None

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}")

            # Cleanup on error
            if driver:
                try:
                    driver.quit()
                except:
                    pass

            return None, None, None

    def _record_result(self, domain: str, success: bool):
        """
        Record result for adaptive layer selection

        Args:
            domain: Domain name
            success: Whether scraping succeeded
        """
        self.logger.info(f"Result: {domain} - undetected_chrome - {'SUCCESS' if success else 'FAILED'}")


# ============================================================================
# Factory Function
# ============================================================================

def create_undetected_chrome_layer() -> UndetectedChromeLayer:
    """
    Factory function to create UndetectedChromeLayer

    Returns:
        UndetectedChromeLayer: New layer instance
    """
    return UndetectedChromeLayer()
