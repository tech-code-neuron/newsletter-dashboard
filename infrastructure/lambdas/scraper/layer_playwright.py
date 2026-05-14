"""
Scraper Layer: Playwright (Bulletproof Stealth)
================================================
Layer 4: Full browser with comprehensive anti-bot protection

SOLID Principles:
- Single Responsibility: Only implements Playwright scraping
- Template Method: Inherits workflow from ScraperLayer
- Open/Closed: Can extend without modifying base class

Last Created: 2026-03-11
"""

import logging
import random
import time
from typing import Optional, Tuple

from scraper_base import ScraperLayer, TIMEOUT_PLAYWRIGHT, SEARCH_REFERRERS
from session_manager import extract_homepage_url

logger = logging.getLogger()

# ============================================================================
# Playwright Availability Check
# ============================================================================

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not available")


# ============================================================================
# Stealth Script
# ============================================================================

def get_playwright_stealth_script() -> str:
    """
    Get comprehensive stealth JavaScript

    Single Responsibility: Only returns stealth script

    Separated from main function for clarity and testability

    Returns:
        str: JavaScript code for stealth
    """
    return """
        // Hide webdriver
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // Plugins (real-looking array)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [{name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer'}]
        });

        // Languages consistency
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'language', {get: () => 'en-US'});

        // Chrome runtime
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // Canvas fingerprint randomization
        const getImageData = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {
            const data = getImageData.apply(this, arguments);
            return data.split('').map((c, i) =>
                i % 10 === 0 ? String.fromCharCode(c.charCodeAt(0) + Math.floor(Math.random() * 3) - 1) : c
            ).join('');
        };

        // WebGL fingerprint randomization
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter.apply(this, arguments);
        };

        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({state: 'default'}) :
            originalQuery(parameters)
        );

        // Battery API
        Object.defineProperty(navigator, 'getBattery', {
            value: () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1
            })
        });

        // Connection API
        Object.defineProperty(navigator, 'connection', {
            get: () => ({effectiveType: '4g', rtt: 50, downlink: 10})
        });
    """


# ============================================================================
# Helper Functions
# ============================================================================

def playwright_session_warmup(page, homepage: str):
    """
    Session warmup with human-like behavior

    Single Responsibility: Handles session warmup

    Args:
        page: Playwright page object
        homepage: Homepage URL
    """
    if not homepage:
        return

    logger.info(f"Multi-step warmup: homepage → scroll → delay → target")

    # Step 1: Visit homepage
    page.goto(homepage, wait_until='domcontentloaded', timeout=TIMEOUT_PLAYWRIGHT * 1000)
    time.sleep(random.uniform(1.5, 3.0))

    # Step 2: Human-like scrolling pattern
    for i in range(3):
        scroll_y = random.randint(200, 500)
        page.evaluate(f"window.scrollTo(0, {scroll_y * (i+1)});")
        time.sleep(random.uniform(0.3, 0.8))

    # Step 3: Random mouse movement simulation
    page.mouse.move(random.randint(100, 500), random.randint(100, 500))
    time.sleep(random.uniform(0.5, 1.5))


def playwright_human_behavior(page):
    """
    Simulate human scrolling behavior

    Single Responsibility: Simulates human behavior

    Args:
        page: Playwright page object
    """
    time.sleep(random.uniform(2, 3))

    # Scroll to different positions
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
    time.sleep(0.5)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
    time.sleep(0.5)


# ============================================================================
# PlaywrightLayer Implementation
# ============================================================================

class PlaywrightLayer(ScraperLayer):
    """
    Layer 4: Playwright with comprehensive anti-bot protection

    Strategy:
    - Full browser (Chromium)
    - Comprehensive stealth scripts
    - Canvas + WebGL fingerprint randomization
    - Multi-step session warmup
    - Human-like behavior (scroll, mouse, delays)
    - Real browser profile

    Success rate: 90%+ (bulletproof, but slowest ~30-45s)
    """

    def __init__(self):
        """Initialize Playwright layer"""
        super().__init__(layer_name='playwright')

    def _is_available(self) -> bool:
        """
        Check if Playwright is available

        Returns:
            bool: True if available
        """
        return PLAYWRIGHT_AVAILABLE

    def _scrape_impl(self, url: str, domain: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Scrape using Playwright with full anti-bot arsenal

        Single Responsibility: Only scrapes using Playwright

        Strategy:
        1. Launch Chromium with stealth settings
        2. Create context with real browser profile
        3. Inject stealth script
        4. Session warmup (homepage + scroll + mouse)
        5. Navigate to target URL
        6. Human-like behavior
        7. Extract content
        8. Cleanup and return result

        Args:
            url: URL to scrape
            domain: Domain name

        Returns:
            tuple: (html_content, final_url, status_code)
        """
        try:
            with sync_playwright() as p:
                # Step 1: Launch Chromium
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--no-sandbox'
                    ]
                )

                # Step 2: Create stealth context
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                    permissions=['geolocation', 'notifications'],
                    geolocation={'latitude': 40.7128, 'longitude': -74.0060, 'accuracy': 100},
                    extra_http_headers={
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Site': 'cross-site',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-User': '?1',
                        'Sec-Fetch-Dest': 'document',
                        'Referer': random.choice(SEARCH_REFERRERS),
                        'Cache-Control': 'max-age=0'
                    }
                )

                # Step 3: Inject stealth script
                context.add_init_script(get_playwright_stealth_script())

                page = context.new_page()

                # Step 4: Session warmup
                homepage = extract_homepage_url(url)
                if homepage and homepage != url:
                    playwright_session_warmup(page, homepage)

                # Step 5: Navigate to target URL
                self.logger.info(f"Navigating to target URL")
                response = page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT_PLAYWRIGHT * 1000)

                # Step 6: Simulate human behavior
                playwright_human_behavior(page)

                # Step 7: Extract content
                html_content = page.content()
                final_url = page.url
                status_code = response.status if response else None

                # Step 8: Cleanup
                browser.close()

                # Return result
                if status_code == 200:
                    return html_content, final_url, 200
                else:
                    self.logger.warning(f"HTTP {status_code}")
                    return None, None, status_code

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}")
            return None, None, None

    def _record_result(self, domain: str, success: bool):
        """
        Record result for adaptive layer selection

        Args:
            domain: Domain name
            success: Whether scraping succeeded
        """
        self.logger.info(f"Result: {domain} - playwright - {'SUCCESS' if success else 'FAILED'}")


# ============================================================================
# Factory Function
# ============================================================================

def create_playwright_layer() -> PlaywrightLayer:
    """
    Factory function to create PlaywrightLayer

    Returns:
        PlaywrightLayer: New layer instance
    """
    return PlaywrightLayer()
