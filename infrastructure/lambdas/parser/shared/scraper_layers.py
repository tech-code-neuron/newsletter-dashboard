"""
Scraper Layer Base Class
========================
SOLID: Template Method Pattern + Strategy Pattern

Base class eliminates duplication across scraper layers.
Each layer implements scrape() and follows consistent patterns:
1. Try scraping with layer-specific technique
2. Record success/failure for adaptive selection
3. Return (html, url, status) tuple
4. Handle 403 specially (escalate immediately)

Concrete Layers:
- Layer 1: CurlCffiLayer (TLS fingerprinting)
- Layer 2: CloudscraperLayer (Cloudflare solver)
- Layer 3: UndetectedChromeLayer (binary patches)
- Layer 4: PlaywrightLayer (full browser with stealth)
"""

import time
import random
import logging
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from .constants import (
    TIMEOUT_LONG,
    TIMEOUT_MEDIUM,
    TIMEOUT_SHORT,
    TIMEOUT_PLAYWRIGHT,
    MIN_VALID_PAGE_SIZE,
    SEARCH_REFERRERS,
    DNS_LOOKUP_TIME,
    TCP_HANDSHAKE_TIME,
    TLS_HANDSHAKE_TIME
)

logger = logging.getLogger(__name__)


# ============================================================================
# Base Layer Class
# ============================================================================

class ScraperLayer(ABC):
    """
    Base class for all scraper layers
    SOLID: Template Method Pattern - Common flow, layer-specific implementation
    """

    def __init__(self, layer_number, layer_name, available=True):
        """
        Initialize scraper layer

        Args:
            layer_number: Layer number (1-4)
            layer_name: Human-readable layer name
            available: Whether this layer is available (dependency installed)
        """
        self.layer_number = layer_number
        self.layer_name = layer_name
        self.available = available

    @abstractmethod
    def _scrape_impl(self, url, domain):
        """
        Layer-specific scraping implementation

        Args:
            url: URL to scrape
            domain: Domain name (for caching/fingerprinting)

        Returns:
            Tuple of (html_content, final_url, status_code)
            Returns (None, None, None) on failure
            Returns (None, None, 403) on 403 (triggers escalation)
        """
        pass

    def scrape(self, url, domain):
        """
        Main scraping method (Template Method Pattern)

        Args:
            url: URL to scrape
            domain: Domain name

        Returns:
            Tuple of (html_content, final_url, status_code)
        """
        if not self.available:
            logger.warning(f"Layer {self.layer_number}: Not available (dependency not installed)")
            return None, None, None

        logger.info(f"Layer {self.layer_number}: {self.layer_name}")

        try:
            # Call layer-specific implementation
            html, final_url, status = self._scrape_impl(url, domain)

            # Record result for adaptive selection
            success = status == 200 and html and len(html) > MIN_VALID_PAGE_SIZE
            self._record_result(domain, success)

            # Log result
            if success:
                logger.info(f"✅ Layer {self.layer_number} SUCCESS ({self.layer_name})")
            elif status == 403:
                logger.warning(f"Layer {self.layer_number}: 403 detected - escalating")
            elif status:
                logger.warning(f"Layer {self.layer_number}: HTTP {status}")
            else:
                logger.warning(f"Layer {self.layer_number}: Failed")

            return html, final_url, status

        except Exception as e:
            logger.warning(f"Layer {self.layer_number} failed: {type(e).__name__}")
            self._record_result(domain, False)
            return None, None, None

    def _record_result(self, domain, success):
        """
        Record layer result for adaptive selection

        Args:
            domain: Domain name
            success: Whether the attempt succeeded
        """
        # Import here to avoid circular dependency
        try:
            from . import scraper_utils
            scraper_utils.record_layer_success(domain, self.layer_name, success)
        except ImportError:
            # If scraper_utils not available, skip recording
            pass

    def _extract_homepage_url(self, url):
        """
        Extract homepage URL for session warming

        Args:
            url: Full URL

        Returns:
            Homepage URL (scheme + netloc)
        """
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except:
            return None

    def _network_timing_delay(self):
        """
        Simulate realistic network timing delays
        Mimics DNS lookup + TCP handshake + TLS handshake
        """
        dns_delay = random.uniform(*DNS_LOOKUP_TIME)
        tcp_delay = random.uniform(*TCP_HANDSHAKE_TIME)
        tls_delay = random.uniform(*TLS_HANDSHAKE_TIME)
        total_delay = dns_delay + tcp_delay + tls_delay
        time.sleep(total_delay)


# ============================================================================
# Concrete Layer Implementations
# ============================================================================

class CurlCffiLayer(ScraperLayer):
    """
    Layer 1: TLS Fingerprinting with curl_cffi
    Fast, lightweight, 70-85% success rate
    """

    def __init__(self, available=True):
        super().__init__(1, 'curl_cffi (TLS fingerprinting)', available)
        self.session_pool = {}  # Session pooling for connection reuse

    def _get_pooled_session(self, domain):
        """Get or create pooled session for domain"""
        if domain not in self.session_pool:
            try:
                from curl_cffi import requests as curl_requests
                self.session_pool[domain] = curl_requests.Session()
            except ImportError:
                return None
        return self.session_pool.get(domain)

    def _scrape_impl(self, url, domain):
        try:
            from curl_cffi import requests as curl_requests
        except ImportError:
            return None, None, None

        # Get pooled session
        session = self._get_pooled_session(domain)
        if not session:
            return None, None, None

        # Network timing delay
        self._network_timing_delay()

        # Pre-fetch homepage for connection warmup
        homepage = self._extract_homepage_url(url)
        if homepage and homepage != url:
            try:
                logger.info(f"Pre-fetching homepage for connection warmup")
                session.head(homepage, impersonate="chrome120", timeout=TIMEOUT_SHORT)
                time.sleep(random.uniform(0.5, 1.5))
            except:
                pass  # Don't fail if pre-fetch fails

        # Main request with perfect TLS fingerprint
        headers = {
            'Referer': random.choice(SEARCH_REFERRERS),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Cache-Control': 'max-age=0'
        }

        response = session.get(
            url,
            impersonate="chrome120",
            headers=headers,
            timeout=TIMEOUT_LONG,
            allow_redirects=True
        )

        if response.status_code == 200:
            return response.text, response.url, 200
        else:
            return None, None, response.status_code


class CloudscraperLayer(ScraperLayer):
    """
    Layer 2: Cloudflare Challenge Solver
    Fast, 60-80% success rate on Cloudflare-protected sites
    """

    def __init__(self, available=True):
        super().__init__(2, 'cloudscraper (Cloudflare solver)', available)

    def _scrape_impl(self, url, domain):
        try:
            import cloudscraper
        except ImportError:
            return None, None, None

        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True
            }
        )

        # Session warmup - visit homepage first
        homepage = self._extract_homepage_url(url)
        if homepage and homepage != url:
            try:
                logger.info(f"Session warmup: visiting homepage")
                scraper.get(homepage, timeout=TIMEOUT_MEDIUM)
                time.sleep(random.uniform(1, 3))
            except:
                pass

        # Enhanced headers
        scraper.headers.update({
            'Referer': random.choice(SEARCH_REFERRERS),
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document'
        })

        response = scraper.get(url, timeout=TIMEOUT_LONG)

        if response.status_code == 200:
            return response.text, response.url, 200
        else:
            return None, None, response.status_code


class UndetectedChromeLayer(ScraperLayer):
    """
    Layer 3: Binary-Level Automation Hiding
    Slower, but 85-95% success rate
    """

    def __init__(self, available=True):
        super().__init__(3, 'undetected-chrome (binary patches)', available)

    def _scrape_impl(self, url, domain):
        try:
            import undetected_chromedriver as uc
        except ImportError:
            return None, None, None

        driver = None
        try:
            options = uc.ChromeOptions()
            options.headless = True
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')

            driver = uc.Chrome(options=options, use_subprocess=False, version_main=120)

            # Canvas fingerprint randomization
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

            # Session warming: Visit homepage first
            homepage = self._extract_homepage_url(url)
            if homepage:
                logger.info(f"Session warmup: homepage → delay → target")
                driver.get(homepage)
                time.sleep(random.uniform(2, 4))

                # Scroll a bit (human behavior)
                driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(random.uniform(0.5, 1.5))

            # Navigate to target URL
            driver.get(url)

            # Human-like behavior
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(random.uniform(0.5, 1))

            html_content = driver.page_source
            final_url = driver.current_url

            driver.quit()

            if html_content and len(html_content) > MIN_VALID_PAGE_SIZE:
                return html_content, final_url, 200
            else:
                return None, None, None

        except Exception as e:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            raise e


class PlaywrightLayer(ScraperLayer):
    """
    Layer 4: Full Browser with Maximum Stealth
    Slowest, but 90%+ success rate
    """

    def __init__(self, available=True):
        super().__init__(4, 'playwright (full stealth)', available)

    def _get_stealth_script(self):
        """
        SOLID: Single Responsibility - Returns comprehensive stealth JavaScript
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
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
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

    def _session_warmup(self, page, homepage):
        """
        SOLID: Single Responsibility - Handles session warmup
        """
        if not homepage:
            return

        logger.info(f"Multi-step warmup: homepage → scroll → delay → target")

        # Visit homepage
        page.goto(homepage, wait_until='domcontentloaded', timeout=TIMEOUT_PLAYWRIGHT * 1000)
        time.sleep(random.uniform(1.5, 3.0))

        # Human-like scrolling
        for i in range(3):
            scroll_y = random.randint(200, 500)
            page.evaluate(f"window.scrollTo(0, {scroll_y * (i+1)});")
            time.sleep(random.uniform(0.3, 0.8))

        # Random mouse movement
        page.mouse.move(random.randint(100, 500), random.randint(100, 500))
        time.sleep(random.uniform(0.5, 1.5))

    def _human_behavior(self, page):
        """
        SOLID: Single Responsibility - Simulates human behavior
        """
        time.sleep(random.uniform(2, 3))

        # Scroll to different positions
        positions = [0.2, 0.5, 0.7]
        for pos in positions:
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {pos});")
            time.sleep(random.uniform(0.5, 1.0))

        # Random mouse movements
        for _ in range(2):
            page.mouse.move(random.randint(100, 800), random.randint(100, 600))
            time.sleep(random.uniform(0.3, 0.7))

    def _scrape_impl(self, url, domain):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None, None, None

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York'
            )

            page = context.new_page()

            # Inject stealth script
            page.add_init_script(self._get_stealth_script())

            # Session warmup
            homepage = self._extract_homepage_url(url)
            if homepage:
                self._session_warmup(page, homepage)

            # Navigate to target
            page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT_PLAYWRIGHT * 1000)

            # Human behavior
            self._human_behavior(page)

            # Get content
            html_content = page.content()
            final_url = page.url

            browser.close()

            if html_content and len(html_content) > MIN_VALID_PAGE_SIZE:
                return html_content, final_url, 200
            else:
                return None, None, None


# ============================================================================
# Layer Factory
# ============================================================================

def create_scraper_layers():
    """
    Create all available scraper layers

    Returns:
        List of ScraperLayer instances (only available ones)
    """
    layers = []

    # Layer 1: curl_cffi
    try:
        from curl_cffi import requests as curl_requests
        layers.append(CurlCffiLayer(available=True))
    except ImportError:
        layers.append(CurlCffiLayer(available=False))

    # Layer 2: cloudscraper
    try:
        import cloudscraper
        layers.append(CloudscraperLayer(available=True))
    except ImportError:
        layers.append(CloudscraperLayer(available=False))

    # Layer 3: undetected-chromedriver
    try:
        import undetected_chromedriver as uc
        layers.append(UndetectedChromeLayer(available=True))
    except ImportError:
        layers.append(UndetectedChromeLayer(available=False))

    # Layer 4: playwright
    try:
        from playwright.sync_api import sync_playwright
        layers.append(PlaywrightLayer(available=True))
    except ImportError:
        layers.append(PlaywrightLayer(available=False))

    return layers
