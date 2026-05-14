"""
Press Release Pipeline - Web Scraper Lambda (Multi-Layer Anti-Bot)
======================================================
Triggered by: SQS Scrape Queue
Purpose: Scrape press release content for newsletter summaries

CRITICAL RULE: Never retry on 403 - escalate to next layer instead

Anti-Bot Strategy (5-Layer Cascade):
  Layer 1: curl_cffi (TLS fingerprinting - fast, 70-85% success)
  Layer 2: cloudscraper (Cloudflare solver - fast, 60-80% success)
  Layer 3: undetected-chromedriver (binary patches - 85-95% success)
  Layer 4: Playwright stealth + session warming (slow, 90%+ success)
  Layer 5: Save URL only (graceful degradation)

Session Warming:
  - Visit homepage first (build cookies)
  - Human-like delays (2-5s)
  - Referrer spoofing (Google search traffic)
  - Real browser profiles

Content Extraction:
  - First 2000 words only (for newsletter summaries)
  - Never republishes full content
  - Always links back to source (drives traffic to IR sites)
"""

import json
import hashlib
import time
import re
import random
from datetime import datetime
from urllib.parse import urlparse, urljoin
import boto3
import os
import logging

# Layer 1: curl_cffi (TLS fingerprinting - mimics real browser TLS handshake)
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    logging.warning("curl_cffi not available")

# Layer 2: cloudscraper (Cloudflare challenge solver)
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    logging.warning("cloudscraper not available")

# Layer 3: undetected-chromedriver (binary-level automation hiding)
try:
    import undetected_chromedriver as uc
    UNDETECTED_CHROME_AVAILABLE = True
except ImportError:
    UNDETECTED_CHROME_AVAILABLE = False
    logging.warning("undetected-chromedriver not available")

# Layer 4: Playwright (full browser automation with stealth)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("playwright not available")

# Fallback: basic requests (rarely used)
try:
    import requests
except ImportError:
    from urllib import request
    requests = None

# HTML parsing
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logging.warning("BeautifulSoup4 not available - content extraction disabled")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
REIT_NEWS_TABLE = os.environ['REIT_NEWS_TABLE']
URL_CACHE_TABLE = os.environ.get('URL_CACHE_TABLE', 'reitsheet-url-cache')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
USER_AGENT = os.environ.get('USER_AGENT', 'REITSheet/1.0 (+https://reitsheet.co)')

# Configure logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# DynamoDB tables
reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)
url_cache_table = dynamodb.Table(URL_CACHE_TABLE)

# ============================================================================
# Constants - SOLID Principle: No Magic Numbers
# ============================================================================

# Timeouts (seconds)
TIMEOUT_LONG = 30        # Main requests (Cloudflare challenges)
TIMEOUT_MEDIUM = 10      # Homepage warmup
TIMEOUT_SHORT = 5        # Quick pre-fetch requests
TIMEOUT_PLAYWRIGHT = 30  # Playwright page loads

# Content extraction
MAX_WORDS = 2000  # Extract first 2000 words for newsletter summaries

# Page validation thresholds (bytes)
MIN_VALID_PAGE_SIZE = 5000   # Minimum size for valid press release (5KB)
MIN_PAGE_SIZE = 1000          # Minimum size to have any content (1KB)

# Human behavior simulation (seconds)
HUMAN_DELAY_MIN = 2  # Minimum human-like delay
HUMAN_DELAY_MAX = 5  # Maximum human-like delay

# Network timing simulation (seconds) - mimic real browser
DNS_LOOKUP_TIME = (0.05, 0.15)     # DNS resolution
TCP_HANDSHAKE_TIME = (0.1, 0.3)    # TCP connection
TLS_HANDSHAKE_TIME = (0.15, 0.4)   # TLS handshake

# Adaptive selection threshold
MIN_ATTEMPTS_FOR_ADAPTIVE = 3  # Minimum attempts before using adaptive selection
ADAPTIVE_SUCCESS_THRESHOLD = 0.7  # 70%+ success rate to use adaptive selection

# Search engine referrers (sites often whitelist these)
SEARCH_REFERRERS = [
    'https://www.google.com/search?q=investor+relations+press+release',
    'https://www.bing.com/search?q=corporate+news',
    'https://duckduckgo.com/?q=company+announcement'
]

# ADVANCED FEATURE: Session pooling (connection reuse)
SESSION_POOL = {}
CHROME_DRIVER_POOL = {}

# ADVANCED FEATURE: Domain fingerprinting (adaptive layer selection)
DOMAIN_FINGERPRINTS = {}  # Track which layers work for which domains


def extract_homepage_url(url):
    """Extract homepage URL for session warming"""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"
    except:
        return None


def extract_domain(url):
    """Extract domain from URL for fingerprinting"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except:
        return None


def validate_page_content(html):
    """
    Check if we got actual page content (not 403 page)
    Returns: (is_valid, page_size, has_content)
    """
    try:
        if not html:
            return False, 0, False

        page_size = len(html)

        # Check for common 403/error indicators
        html_lower = html.lower()
        error_indicators = [
            'access denied',
            'forbidden',
            '403',
            'blocked',
            'captcha',
            'please verify you are a human'
        ]

        has_error = any(indicator in html_lower for indicator in error_indicators)

        # Consider it valid if:
        # 1. Page is substantial (>MIN_VALID_PAGE_SIZE)
        # 2. No obvious error indicators
        # 3. Has some text content
        is_valid = page_size > MIN_VALID_PAGE_SIZE and not has_error
        has_content = page_size > MIN_PAGE_SIZE

        logger.info(f"Page validation: size={page_size}b, valid={is_valid}, has_content={has_content}")
        return is_valid, page_size, has_content

    except Exception as e:
        logger.error(f"Error validating page: {e}")
        return False, 0, False


def extract_text_content(html):
    """
    Extract clean text from press release HTML
    Tries multiple common selectors used by IR platforms
    Returns: (text_preview, word_count) - First 2000 words
    """
    if not BS4_AVAILABLE or not html:
        logger.warning("BeautifulSoup not available or no HTML - skipping content extraction")
        return None, 0

    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Try common press release content selectors (in priority order)
        selectors = [
            '.xn-content',              # Q4/GCS press releases (e.g., Brixmor)
            '.module_body',             # Q4 outer container
            'article',                  # Semantic HTML
            '[class*="release"]',       # Generic release containers
            '[class*="press"]',         # Generic press containers
            '.news-content',            # Common news class
            '.pr-content',              # PR content
            'main',                     # Semantic main content
        ]

        content_div = None
        for selector in selectors:
            content_div = soup.select_one(selector)
            if content_div:
                logger.info(f"Found content using selector: {selector}")
                break

        if not content_div:
            # Fallback: use body
            content_div = soup.find('body')
            logger.warning("No specific content selector found, using body")

        if not content_div:
            logger.error("No content found in HTML")
            return None, 0

        # Extract text
        text = content_div.get_text(separator=' ', strip=True)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)

        # Count words
        words = text.split()
        word_count = len(words)

        # Extract first 2000 words for newsletter summaries
        if word_count > MAX_WORDS:
            preview = ' '.join(words[:MAX_WORDS])
            logger.info(f"Extracted {MAX_WORDS} words from {word_count} total")
        else:
            preview = text
            logger.info(f"Extracted all {word_count} words")

        return preview, word_count

    except Exception as e:
        logger.error(f"Error extracting content: {e}")
        return None, 0


def human_delay():
    """Random delay to mimic human behavior"""
    delay = random.uniform(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
    time.sleep(delay)


def network_timing_delay():
    """ADVANCED: Mimic real browser network timing"""
    time.sleep(random.uniform(*DNS_LOOKUP_TIME))      # DNS
    time.sleep(random.uniform(*TCP_HANDSHAKE_TIME))   # TCP
    time.sleep(random.uniform(*TLS_HANDSHAKE_TIME))   # TLS


def get_pooled_session(domain, impersonate="chrome120"):
    """
    ADVANCED: Connection reuse (session pooling)
    Reuses sessions for the same domain (like real browsers)
    """
    if domain not in SESSION_POOL:
        if CURL_CFFI_AVAILABLE:
            SESSION_POOL[domain] = curl_requests.Session()
            logger.info(f"Created new session pool for {domain}")
        else:
            SESSION_POOL[domain] = None
    return SESSION_POOL[domain]


def record_layer_success(domain, layer, success):
    """
    ADVANCED: Domain fingerprinting for adaptive layer selection
    Tracks which layers work for which domains
    """
    if domain not in DOMAIN_FINGERPRINTS:
        DOMAIN_FINGERPRINTS[domain] = {
            'curl_cffi': {'attempts': 0, 'successes': 0},
            'cloudscraper': {'attempts': 0, 'successes': 0},
            'undetected_chrome': {'attempts': 0, 'successes': 0},
            'playwright': {'attempts': 0, 'successes': 0}
        }

    if layer in DOMAIN_FINGERPRINTS[domain]:
        DOMAIN_FINGERPRINTS[domain][layer]['attempts'] += 1
        if success:
            DOMAIN_FINGERPRINTS[domain][layer]['successes'] += 1

        # Log success rate
        stats = DOMAIN_FINGERPRINTS[domain][layer]
        rate = stats['successes'] / stats['attempts'] if stats['attempts'] > 0 else 0
        logger.info(f"Domain fingerprint: {domain} / {layer} = {rate:.1%} success rate")


def get_best_layer_for_domain(domain):
    """
    ADVANCED: Adaptive layer selection
    Returns the best-performing layer for a domain, or None to try all
    """
    if domain not in DOMAIN_FINGERPRINTS:
        return None  # No data, try all layers

    fingerprint = DOMAIN_FINGERPRINTS[domain]
    best_layer = None
    best_rate = 0

    for layer, stats in fingerprint.items():
        if stats['attempts'] >= MIN_ATTEMPTS_FOR_ADAPTIVE:
            rate = stats['successes'] / stats['attempts']
            if rate > best_rate:
                best_rate = rate
                best_layer = layer

    if best_rate >= ADAPTIVE_SUCCESS_THRESHOLD:
        logger.info(f"Adaptive selection: Using {best_layer} for {domain} ({best_rate:.1%} success)")
        return best_layer

    return None  # No clear winner, try all layers


def scrape_layer1_curl_cffi(url, domain):
    """
    Layer 1: TLS Fingerprinting with curl_cffi
    ADVANCED: Session pooling + network timing + pre-fetching
    Returns: (html_content, final_url, status_code)
    """
    if not CURL_CFFI_AVAILABLE:
        return None, None, None

    try:
        logger.info(f"Layer 1: curl_cffi (TLS fingerprinting + session reuse)")

        # ADVANCED: Get pooled session for connection reuse
        session = get_pooled_session(domain)
        if not session:
            return None, None, None

        # ADVANCED: Network timing delays (mimic real browser)
        network_timing_delay()

        # ADVANCED: Pre-fetching (warm up connection to homepage first)
        homepage = extract_homepage_url(url)
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

        # Record result for adaptive selection
        success = response.status_code == 200
        record_layer_success(domain, 'curl_cffi', success)

        if success:
            logger.info(f"✅ Layer 1 SUCCESS (curl_cffi)")
            return response.text, response.url, 200
        elif response.status_code == 403:
            logger.warning(f"Layer 1: 403 detected - escalating immediately")
            return None, None, 403
        else:
            logger.warning(f"Layer 1: HTTP {response.status_code}")
            return None, None, response.status_code

    except Exception as e:
        logger.warning(f"Layer 1 failed: {type(e).__name__}")
        record_layer_success(domain, 'curl_cffi', False)
        return None, None, None


def scrape_layer2_cloudscraper(url, domain):
    """
    Layer 2: Cloudflare Challenge Solver
    ADVANCED: Session warmup + connection pooling
    Returns: (html_content, final_url, status_code)
    """
    if not CLOUDSCRAPER_AVAILABLE:
        return None, None, None

    try:
        logger.info(f"Layer 2: cloudscraper (Cloudflare solver + session warmup)")

        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True
            }
        )

        # ADVANCED: Session warmup - visit homepage first
        homepage = extract_homepage_url(url)
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

        success = response.status_code == 200
        record_layer_success(domain, 'cloudscraper', success)

        if success:
            logger.info(f"✅ Layer 2 SUCCESS (cloudscraper)")
            return response.text, response.url, 200
        elif response.status_code == 403:
            logger.warning(f"Layer 2: 403 detected - escalating")
            return None, None, 403
        else:
            logger.warning(f"Layer 2: HTTP {response.status_code}")
            return None, None, response.status_code

    except Exception as e:
        logger.warning(f"Layer 2 failed: {type(e).__name__}")
        record_layer_success(domain, 'cloudscraper', False)
        return None, None, None


def scrape_layer3_undetected_chrome(url, domain):
    """
    Layer 3: Undetected Chrome (binary-level patches)
    ADVANCED: Canvas randomization + timing patterns
    Returns: (html_content, final_url, status_code)
    """
    if not UNDETECTED_CHROME_AVAILABLE:
        return None, None, None

    try:
        logger.info(f"Layer 3: undetected-chrome (binary patches + canvas randomization)")

        options = uc.ChromeOptions()
        options.headless = True
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')

        driver = uc.Chrome(options=options, use_subprocess=False, version_main=120)

        # ADVANCED: Canvas fingerprint randomization
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

        # Session warming: Visit homepage first with human timing
        homepage = extract_homepage_url(url)
        if homepage:
            logger.info(f"Session warmup: homepage → delay → target")
            driver.get(homepage)
            time.sleep(random.uniform(2, 4))  # Human-like delay

            # Scroll a bit (human behavior)
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(random.uniform(0.5, 1.5))

        # Navigate to target URL
        driver.get(url)

        # ADVANCED: Human-like behavior pattern
        time.sleep(random.uniform(1, 2))  # Page load time
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        time.sleep(random.uniform(0.5, 1))

        html_content = driver.page_source
        final_url = driver.current_url

        driver.quit()

        success = html_content and len(html_content) > MIN_VALID_PAGE_SIZE
        record_layer_success(domain, 'undetected_chrome', success)

        if success:
            logger.info(f"✅ Layer 3 SUCCESS (undetected-chrome)")
            return html_content, final_url, 200
        else:
            logger.warning(f"Layer 3: Insufficient content")
            return None, None, None

    except Exception as e:
        logger.warning(f"Layer 3 failed: {type(e).__name__}")
        record_layer_success(domain, 'undetected_chrome', False)
        try:
            driver.quit()
        except:
            pass
        return None, None, None


def _get_playwright_stealth_script():
    """
    SOLID: Single Responsibility - Returns comprehensive stealth JavaScript
    Separated from main function for clarity and testability
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


def _playwright_session_warmup(page, homepage):
    """
    SOLID: Single Responsibility - Handles session warmup with human-like behavior
    Separated from main scraping logic for clarity
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


def _playwright_human_behavior(page):
    """
    SOLID: Single Responsibility - Simulates human scrolling behavior
    """
    time.sleep(random.uniform(2, 3))

    # Scroll to different positions
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
    time.sleep(0.5)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
    time.sleep(0.5)


def scrape_layer4_playwright_stealth(url, domain):
    """
    Layer 4: Playwright with comprehensive anti-bot protection
    SOLID: Refactored into focused helper functions
    Returns: (html_content, final_url, status_code)
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None, None, None

    try:
        logger.info(f"Layer 4: Playwright BULLETPROOF (full anti-bot arsenal)")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox'
                ]
            )

            # Create stealth context
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

            # Inject stealth script
            context.add_init_script(_get_playwright_stealth_script())

            page = context.new_page()

            # Session warming with human behavior
            homepage = extract_homepage_url(url)
            if homepage and homepage != url:
                _playwright_session_warmup(page, homepage)

            # Navigate to target URL
            logger.info(f"Navigating to target URL")
            response = page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT_PLAYWRIGHT * 1000)

            # Simulate human behavior
            _playwright_human_behavior(page)

            # Extract content
            html_content = page.content()
            final_url = page.url
            status_code = response.status if response else None

            browser.close()

            # Record result
            success = status_code == 200
            record_layer_success(domain, 'playwright', success)

            if success:
                logger.info(f"✅ Layer 4 SUCCESS (Playwright bulletproof)")
                return html_content, final_url, 200
            elif status_code == 403:
                logger.error(f"Layer 4: 403 EVEN WITH FULL ARSENAL - extremely aggressive protection")
                return None, None, 403
            else:
                logger.warning(f"Layer 4: HTTP {status_code}")
                return None, None, status_code

    except Exception as e:
        logger.warning(f"Layer 4 failed: {type(e).__name__}")
        record_layer_success(domain, 'playwright', False)
        return None, None, None


def scrape_press_release(url):
    """
    BULLETPROOF 4-Layer Cascade with Adaptive Selection
    Returns: (html_content, final_url, method_used, is_valid)
    """
    domain = extract_domain(url)

    # ADVANCED: Adaptive layer selection (skip to best-performing layer)
    best_layer = get_best_layer_for_domain(domain)
    if best_layer:
        logger.info(f"Adaptive: Skipping to {best_layer} based on history")
        if best_layer == 'cloudscraper':
            html, final_url, status = scrape_layer2_cloudscraper(url, domain)
            if html and status == 200:
                is_valid, page_size, has_content = validate_page_content(html)
                if is_valid:
                    return html, final_url, 'cloudscraper_adaptive', True
        elif best_layer == 'undetected_chrome':
            html, final_url, status = scrape_layer3_undetected_chrome(url, domain)
            if html and status == 200:
                is_valid, page_size, has_content = validate_page_content(html)
                if is_valid:
                    return html, final_url, 'undetected_chrome_adaptive', True

    # Standard 4-layer cascade
    logger.info(f"Standard cascade: Trying all layers")

    # Layer 1: curl_cffi (TLS fingerprinting - fastest)
    html, final_url, status = scrape_layer1_curl_cffi(url, domain)
    if html and status == 200:
        is_valid, page_size, has_content = validate_page_content(html)
        if is_valid:
            logger.info(f"✅ Layer 1 VICTORY - Page size: {page_size}b")
            return html, final_url, 'curl_cffi_tls', True
    if status == 403:
        logger.warning("⚠️  Layer 1: 403 - ESCALATING to Layer 2")

    # Layer 2: cloudscraper (Cloudflare solver)
    html, final_url, status = scrape_layer2_cloudscraper(url, domain)
    if html and status == 200:
        is_valid, page_size, has_content = validate_page_content(html)
        if is_valid:
            logger.info(f"✅ Layer 2 VICTORY - Page size: {page_size}b")
            return html, final_url, 'cloudscraper', True
    if status == 403:
        logger.warning("⚠️  Layer 2: 403 - ESCALATING to Layer 3")

    # Layer 3: undetected-chromedriver (binary patches)
    html, final_url, status = scrape_layer3_undetected_chrome(url, domain)
    if html and status == 200:
        is_valid, page_size, has_content = validate_page_content(html)
        if is_valid:
            logger.info(f"✅ Layer 3 VICTORY - Page size: {page_size}b")
            return html, final_url, 'undetected_chrome', True

    # Layer 4: Playwright BULLETPROOF (full arsenal)
    html, final_url, status = scrape_layer4_playwright_stealth(url, domain)
    if html and status == 200:
        is_valid, page_size, has_content = validate_page_content(html)
        if is_valid:
            logger.info(f"✅ Layer 4 VICTORY - Page size: {page_size}b")
            return html, final_url, 'playwright_bulletproof', True
    if status == 403:
        logger.error("❌ Layer 4: 403 EVEN WITH FULL ARSENAL - nuclear-level protection")

    # All layers failed
    logger.error(f"❌ TOTAL FAILURE - All 4 layers blocked for {url}")
    return None, None, 'all_layers_failed', False


def follow_redirects(url, max_redirects=10):
    """
    Follow HTTP redirects to final destination URL
    Uses HEAD request for efficiency (doesn't download body)
    Returns: (final_url, status_code, redirect_count)
    """
    if requests:
        return follow_redirects_requests(url, max_redirects)
    else:
        return follow_redirects_urllib(url, max_redirects)


def follow_redirects_requests(url, max_redirects=10):
    """
    Follow redirects using requests library (preferred)
    """
    try:
        # Configure session with custom headers
        session = requests.Session()
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9'
        })

        # Use HEAD request to avoid downloading full page
        response = session.head(
            url,
            allow_redirects=True,
            timeout=TIMEOUT_SECONDS,
            max_redirects=max_redirects
        )

        # Get final URL after all redirects
        final_url = response.url
        status_code = response.status_code
        redirect_count = len(response.history)

        logger.info(f"Followed {redirect_count} redirects: {url} → {final_url}")

        return (final_url, status_code, redirect_count)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout following redirects: {url}")
        raise
    except requests.exceptions.TooManyRedirects:
        logger.error(f"Too many redirects: {url}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error following redirects: {e}")
        raise


def follow_redirects_urllib(url, max_redirects=10):
    """
    Fallback: Follow redirects using urllib (if requests not available)
    """
    try:
        req = request.Request(url, headers={'User-Agent': USER_AGENT})
        response = request.urlopen(req, timeout=TIMEOUT_SECONDS)

        final_url = response.geturl()
        status_code = response.getcode()

        # urllib doesn't track redirect count easily
        redirect_count = 0 if final_url == url else 1

        return (final_url, status_code, redirect_count)

    except Exception as e:
        logger.error(f"Error following redirects (urllib): {e}")
        raise


def extract_company_domain(url):
    """
    Extract company domain from URL
    Example: https://investors.example.com/press/123 → investors.example.com
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception as e:
        logger.error(f"Error extracting domain: {e}")
        return None


def save_press_release(url, content_preview, word_count, metadata):
    """
    Save press release URL + extracted content to DynamoDB
    """
    try:
        press_release_id = hashlib.sha256(url.encode()).hexdigest()
        first_seen_at = datetime.utcnow().isoformat()
        company_domain = extract_company_domain(url)

        item = {
            'press_release_id': press_release_id,
            'first_seen_at': first_seen_at,
            'url': url,
            'company_domain': company_domain,
            'source_type': metadata.get('source_type', 'scraped'),
            'scraped_at': datetime.utcnow().isoformat(),
            **metadata
        }

        # Add extracted content if available
        if content_preview:
            item['content_preview'] = content_preview
            item['word_count'] = word_count
            item['content_extracted'] = True
        else:
            item['content_extracted'] = False

        # Add company_id if domain extracted successfully
        if company_domain:
            item['company_id'] = company_domain

        reit_news_table.put_item(Item=item)

        logger.info(f"✅ Saved: {url} ({word_count} words, {metadata.get('scrape_method', 'unknown')})")

    except Exception as e:
        logger.error(f"Error saving press release: {e}")
        raise


def log_to_url_cache(url, scrape_metadata):
    """
    CRITICAL: Write immutable log entry to URL cache table
    This table is NEVER deleted - permanent record of all scrape attempts
    Even if reitsheet-reit-news gets cleared, this preserves the history

    Purpose:
      - Prevent re-scraping same URL
      - Audit trail of all activity
      - Recovery from accidental deletion
    """
    try:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        timestamp = datetime.utcnow().isoformat()

        cache_entry = {
            'url_hash': url_hash,
            'scraped_at': timestamp,
            'url': url,
            'ticker': scrape_metadata.get('ticker'),
            'company_name': scrape_metadata.get('company_name'),
            'scrape_status': 'success' if scrape_metadata.get('success') else 'failed',
            'scrape_method': scrape_metadata.get('scrape_method'),
            'word_count': scrape_metadata.get('word_count', 0),
            'content_extracted': scrape_metadata.get('content_extracted', False),
            'bypass_403': scrape_metadata.get('bypass_403', False),
            'source_type': scrape_metadata.get('source_type'),
        }

        # Add error info if failed
        if scrape_metadata.get('error'):
            cache_entry['error'] = scrape_metadata['error']
        if scrape_metadata.get('note'):
            cache_entry['note'] = scrape_metadata['note']

        url_cache_table.put_item(Item=cache_entry)
        logger.info(f"📝 Logged to immutable URL cache: {url_hash[:16]}...")

    except Exception as e:
        logger.error(f"CRITICAL: Failed to log to URL cache: {e}")
        # Don't fail the whole operation if cache logging fails


def check_already_scraped(url):
    """
    CRITICAL: Check if URL has already been scraped successfully
    Checks BOTH url_cache (immutable log) and reit_news tables
    Prevents unnecessary re-scraping and avoids rate limits
    Returns: (already_scraped, existing_data)
    """
    try:
        url_hash = hashlib.sha256(url.encode()).hexdigest()

        # Query immutable URL cache first (faster, purpose-built for this)
        response = url_cache_table.query(
            KeyConditionExpression='url_hash = :hash',
            ExpressionAttributeValues={':hash': url_hash},
            Limit=10,  # Get recent attempts
            ScanIndexForward=False  # Most recent first
        )

        items = response.get('Items', [])
        if not items:
            logger.info(f"🆕 New URL - not in cache")
            return False, None

        # Check for successful scrape with content
        for item in items:
            if item.get('scrape_status') == 'success' and item.get('content_extracted'):
                logger.info(f"✅ CACHE HIT - URL already scraped ({item.get('word_count', 0)} words)")
                logger.info(f"   Last scraped: {item.get('scraped_at')}")
                return True, item

        # Found attempts but no successful content extraction
        logger.info(f"⚠️  URL attempted before but no successful content - will retry")
        return False, None

    except Exception as e:
        logger.error(f"Error checking cache: {e}")
        # On error, assume not scraped (fail-safe: allow scraping)
        return False, None


def process_url(url, metadata):
    """
    Scrape press release and extract content
    CACHE-AWARE: Checks database before scraping to prevent duplicates
    4-layer cascade (NO RETRIES) with adaptive selection
    """
    try:
        logger.info(f"🎯 Processing: {url}")

        # CRITICAL: Check cache first to avoid re-scraping
        already_scraped, existing_data = check_already_scraped(url)
        if already_scraped:
            logger.info(f"⏭️  SKIPPING - Already scraped with {existing_data.get('word_count', 0)} words")
            return True  # Already done, no need to scrape again

        logger.info(f"🌐 Scraping fresh content...")

        # 4-layer bulletproof cascade
        html_content, final_url, method, is_valid = scrape_press_release(url)

        if is_valid and final_url and html_content:
            # SUCCESS - Extract content from HTML
            logger.info(f"✅ Page loaded via {method} - extracting content")

            # Extract text content (first 2000 words)
            content_preview, word_count = extract_text_content(html_content)

            if content_preview:
                logger.info(f"📝 Extracted {word_count} words from press release")
            else:
                logger.warning("⚠️  No content extracted - saving URL only")

            scrape_metadata = {
                **metadata,
                'original_url': url if url != final_url else None,
                'scrape_method': method,
                'source_type': metadata.get('source_type', 'scraped'),
                'success': True,
                'bypass_403': True,
                'word_count': word_count,
                'content_extracted': bool(content_preview)
            }

            # Save to content table
            save_press_release(final_url, content_preview, word_count, scrape_metadata)

            # CRITICAL: Log to immutable URL cache (permanent record)
            log_to_url_cache(final_url, scrape_metadata)

            return True

        else:
            # All 4 layers failed - blocked by 403 or other issue
            logger.error(f"❌ BLOCKED: All layers failed for {url}")

            scrape_metadata = {
                **metadata,
                'scrape_method': method if method else 'all_layers_failed',
                'source_type': 'scrape_failed',
                'success': False,
                'bypass_403': False,
                'note': '403 or other protection blocked all 4 layers',
                'word_count': 0,
                'content_extracted': False
            }

            # Save failure to content table
            save_press_release(url, None, 0, scrape_metadata)

            # CRITICAL: Log failure to immutable cache (track failed attempts)
            log_to_url_cache(url, scrape_metadata)

            return False

    except Exception as e:
        logger.error(f"❌ EXCEPTION: {type(e).__name__}: {str(e)[:200]}")

        # Save error for review
        try:
            error_metadata = {
                **metadata,
                'scrape_method': 'exception',
                'source_type': 'scrape_error',
                'success': False,
                'bypass_403': False,
                'error': str(e)[:200],
                'word_count': 0,
                'content_extracted': False
            }
            save_press_release(url, None, 0, error_metadata)

            # CRITICAL: Log exception to immutable cache
            log_to_url_cache(url, error_metadata)
        except:
            logger.error("Failed to save error record")

        return False


def lambda_handler(event, context):
    """
    Main Lambda handler
    Processes SQS messages containing newswire URLs
    """
    logger.info(f"Received {len(event['Records'])} messages")

    # Track failures for partial batch response
    batch_item_failures = []

    for record in event['Records']:
        message_id = record['messageId']

        try:
            # Parse message body
            body = json.loads(record['body'])
            url = body['url']

            logger.info(f"Processing: {url}")

            # Process URL (4-layer cascade, no retries)
            metadata = {
                'email_key': body.get('email_key'),
                'ticker': body.get('ticker'),
                'company_name': body.get('company_name'),
                'extracted_at': body.get('extracted_at'),
                'queued_at': body.get('queued_at')
            }

            success = process_url(url, metadata)

            if success:
                logger.info(f"Successfully processed: {url}")
            else:
                logger.warning(f"Skipped (non-retryable): {url}")

        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}")
            batch_item_failures.append({
                'itemIdentifier': message_id
            })

    # Return partial batch response
    # Failed messages will be retried, successful ones deleted
    return {
        'batchItemFailures': batch_item_failures
    }
