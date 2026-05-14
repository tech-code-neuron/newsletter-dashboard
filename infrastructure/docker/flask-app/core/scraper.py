"""
Web scraper for REIT press releases
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from core.models import get_session, Company, PressRelease, init_db
from urllib.parse import urljoin, urlparse
import time
import re
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
from collections import defaultdict

# Import centralized configuration (SOLID Principle)
from config.scraper_config import (
    TIMEOUT_SHORT, TIMEOUT_MEDIUM, TIMEOUT_LONG,
    RATE_LIMIT_DELAY, RATE_LIMIT_DELAY_SHORT,
    USER_AGENT, MAX_CONTAINERS_TO_PARSE,
    DEFAULT_BROWSER_WORKERS, DEFAULT_RSS_WORKERS,
    MAX_WORDS_FOR_COMPARISON, SEPARATOR_LINE,
    COMMON_PRESS_RELEASE_PATHS
)
from utils.time_config import Q4_DATE_PATTERNS, find_date_from_context
from utils.platform_registry import PlatformRegistry

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════

# Date extraction function moved to utils/time_config.py (SOLID Principle)


class PressReleaseScraper:
    """Scraper for REIT investor relations press releases"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT
        })
        self.db_session = get_session()
        self.browser = None        # Playwright browser (lazy init)
        self.playwright = None     # Playwright instance (lazy init)

        # Load selector config
        config_path = Path(__file__).parent.parent / 'config' / 'selectors.json'
        with open(config_path, 'r') as f:
            self.selectors = json.load(f)

    def _get_platform_router(self):
        """
        Returns a mapping of platform names to their scraper methods.
        Delegates to PlatformRegistry (SOLID Principle).

        Returns:
            dict: {platform_name: scraper_method}
        """
        return PlatformRegistry.get_platform_router(self)

    def _route_to_scraper(self, company, lookback_days):
        """
        Routes a company to the appropriate scraper method based on its platform.
        Delegates to PlatformRegistry (SOLID Principle).

        Args:
            company: Company model instance
            lookback_days: How far back to scrape

        Returns:
            tuple: (new_count, platform_key) where platform_key is for results tracking
        """
        return PlatformRegistry.route_to_scraper(self, company, lookback_days)

    def _ensure_browser(self):
        """Lazy-initialize Playwright browser (call before any JS scraping)"""
        if self.browser is None:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False,
                args=['--disable-dev-shm-usage']  # Prevents crashes in low-memory
            )
            logger.info("Playwright browser started (non-headless mode)")

    def find_press_release_page(self, ir_url):
        """
        Given an IR homepage, try to find the press releases page
        Returns the URL of the press releases page
        """
        if not ir_url:
            return None
        
        try:
            response = self.session.get(ir_url, timeout=TIMEOUT_MEDIUM)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Common text patterns for press release links
            patterns = [
                'press release', 'news release', 'press releases',
                'news releases', 'news & events', 'news and events',
                'press', 'news', 'media'
            ]
            
            # Find links that might lead to press releases
            for link in soup.find_all('a', href=True):
                link_text = link.get_text().lower().strip()
                href = link.get('href')
                
                for pattern in patterns:
                    if pattern in link_text or pattern in href.lower():
                        press_url = urljoin(ir_url, href)
                        return press_url
            
            # Fallback: common URL patterns (from config)
            base_domain = urlparse(ir_url).netloc

            for path in COMMON_PRESS_RELEASE_PATHS:
                test_url = f"https://{base_domain}{path}"
                try:
                    test_response = self.session.head(test_url, timeout=TIMEOUT_SHORT)
                    if test_response.status_code == 200:
                        return test_url
                except Exception:
                    continue
            
        except Exception as e:
            logger.error(f"Error finding press release page for {ir_url}: {e}")
        
        return None
    
    def extract_press_releases(self, url, company):
        """
        Extract press releases from a press release page (generic fallback)
        Returns list of dicts with title, url, date, content
        """
        try:
            response = self.session.get(url, timeout=TIMEOUT_LONG)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            releases = []
            
            # Look for article/press release containers
            containers = soup.find_all(['article', 'div'], class_=re.compile(
                r'(press|release|news|item|entry|article)', re.I
            ))
            
            if not containers:
                # Fallback: find all links that look like press releases
                containers = soup.find_all('a', href=True, string=re.compile(r'.{10,}'))
            
            for container in containers[:MAX_CONTAINERS_TO_PARSE]:
                try:
                    release = self._parse_release_container(container, url)
                    if release:
                        releases.append(release)
                except Exception as e:
                    logger.debug(f"Error parsing container: {e}")
                    continue
            
            logger.info(f"Found {len(releases)} releases for {company.ticker} at {url}")
            return releases
            
        except Exception as e:
            logger.error(f"Error scraping {url} for {company.ticker}: {e}")
            return []
    
    def _parse_release_container(self, container, base_url):
        """Parse a single press release container"""
        release = {}
        
        link = container if container.name == 'a' else container.find('a', href=True)
        if not link:
            return None
        
        release['title'] = link.get_text().strip()
        release['url'] = urljoin(base_url, link.get('href'))
        
        if len(release['title']) < 20:
            return None
        
        date = self._extract_date(container)
        if date:
            release['date'] = date
        else:
            release['date'] = datetime.now()
        
        return release
    
    def _extract_date(self, element):
        """Try to extract a date from an element"""
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})',
        ]
        
        text = element.get_text()
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                try:
                    from dateutil import parser
                    date_str = match.group(0)
                    return parser.parse(date_str)
                except Exception:
                    continue
        
        time_elem = element.find('time')
        if time_elem and time_elem.get('datetime'):
            try:
                from dateutil import parser
                return parser.parse(time_elem.get('datetime'))
            except Exception:
                pass

        return None

    def scrape_gcs(self, company, lookback_days=14):
        """
        Scrape press releases from GCS (GlobeNewswire Corporate Solutions) sites.
        Delegates to GcsScraper class.
        """
        from scrapers.gcs import GcsScraper

        self._ensure_browser()
        scraper = GcsScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['gcs']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_gcs_with_dates(self, company, lookback_days=14):
        """
        Scrape press releases from GCS sites with date extraction.
        Delegates to GcsWithDatesScraper class.
        """
        from scrapers.gcs_with_dates import GcsWithDatesScraper

        self._ensure_browser()
        scraper = GcsWithDatesScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['gcs_with_dates']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_wordpress_pdf(self, company, lookback_days=14):
        """
        Scrape press releases from WordPress sites with PDF links.
        Delegates to WordpressPdfScraper class.
        """
        from scrapers.wordpress_pdf import WordpressPdfScraper

        scraper = WordpressPdfScraper(
            session=self.session,
            db_session=self.db_session,
            browser=None,  # This scraper doesn't use browser
            config=self.selectors['wordpress_pdf']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_q4_detail(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 sites using /press-releases/detail/[ID]/ URL pattern.
        Delegates to Q4DetailScraper class.
        """
        from scrapers.q4_detail import Q4DetailScraper

        self._ensure_browser()
        scraper = Q4DetailScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['q4_detail']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_apollo_accordion(self, company, lookback_days=14):
        """
        Scrape press releases from Apollo sites with accordion navigation.
        Delegates to ApolloAccordionScraper class.
        """
        from scrapers.apollo_accordion import ApolloAccordionScraper

        self._ensure_browser()
        scraper = ApolloAccordionScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['apollo_accordion']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_investis(self, company, lookback_days=14):
        """
        Scrape press releases from Investis platform sites.
        Delegates to InvestisScraper class.
        """
        from scrapers.investis import InvestisScraper

        self._ensure_browser()
        scraper = InvestisScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['investis']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_olp_pdf(self, company, lookback_days=14):
        """
        Scrape press releases from One Liberty Properties (OLP) PDF listing page.
        Delegates to OlpPdfScraper class.
        """
        from scrapers.olp_pdf import OlpPdfScraper

        self._ensure_browser()
        scraper = OlpPdfScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['olp_pdf']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_welltower(self, company, lookback_days=14):
        """
        Scrape press releases from Welltower (WELL).
        Delegates to WelltowerScraper class.
        """
        from scrapers.welltower import WelltowerScraper

        self._ensure_browser()
        scraper = WelltowerScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['welltower']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_date_slug(self, company, lookback_days=14):
        """
        Scrape press releases from sites with /YYYY-MM-DD-Title-Slug URL pattern.
        Delegates to DateSlugScraper class.
        """
        from scrapers.date_slug import DateSlugScraper

        self._ensure_browser()
        scraper = DateSlugScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['date_slug']
        )
        return scraper.scrape(company, lookback_days)

    def scrape_q4_pdf(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 sites that link to PDFs.
        Delegates to Q4PdfScraper class.
        """
        from scrapers.q4_pdf import Q4PdfScraper

        scraper = Q4PdfScraper(
            session=self.session,
            db_session=self.db_session,
            browser=None,  # Doesn't use Playwright
            config=self.selectors['q4_pdf']
        )
        return scraper.scrape(company, lookback_days)

    def fetch_press_release_content(self, url):
        """Fetch the full content of a press release"""
        try:
            response = self.session.get(url, timeout=TIMEOUT_LONG)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            
            content_areas = [
                soup.find('article'),
                soup.find('div', class_=re.compile(r'(content|body|article|press)', re.I)),
                soup.find('main'),
                soup.find('div', id=re.compile(r'(content|body|article|press)', re.I))
            ]
            
            for area in content_areas:
                if area:
                    text = area.get_text(separator='\n', strip=True)
                    if len(text) > 200:
                        return text
            
            text = soup.get_text(separator='\n', strip=True)
            return text
            
        except Exception as e:
            logger.error(f"Error fetching content from {url}: {e}")
            return None
    
    # ─────────────────────────────────────────────────────
    # Q4 DRUPAL HTML SCRAPER (NEW)
    # ─────────────────────────────────────────────────────
    
    def scrape_html_q4_drupal(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 Drupal-rendered IR pages (HTML variant).
        Delegates to Q4DrupalHtmlScraper class.
        """
        from scrapers.q4_drupal_html import Q4DrupalHtmlScraper

        scraper = Q4DrupalHtmlScraper(
            session=self.session,
            db_session=self.db_session,
            browser=None,  # HTML variant doesn't use Playwright
            config=self.selectors['q4_drupal']['html']
        )
        return scraper.scrape(company, lookback_days)

    # Alias for backwards compatibility
    def scrape_q4_drupal(self, company, lookback_days=14):
        """Alias for scrape_html_q4_drupal"""
        return self.scrape_html_q4_drupal(company, lookback_days)

    # ─────────────────────────────────────────────────────
    # Q4 JAVASCRIPT SCRAPER (PLAYWRIGHT)
    # ─────────────────────────────────────────────────────

    def scrape_js_q4_drupal(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 Drupal JavaScript-rendered pages (JS variant).
        Delegates to Q4DrupalJsScraper class.
        """
        from scrapers.q4_drupal_js import Q4DrupalJsScraper

        self._ensure_browser()
        scraper = Q4DrupalJsScraper(
            session=self.session,
            db_session=self.db_session,
            browser=self.browser,
            config=self.selectors['q4_drupal']['js']
        )
        return scraper.scrape(company, lookback_days)


    # ─────────────────────────────────────────────────────
    # LEGACY SINGLE-COMPANY SCRAPER
    # ─────────────────────────────────────────────────────
    
    def scrape_company(self, company, lookback_days=2):
        """
        Scrape press releases for a single company (legacy HTML fallback).
        Only processes releases from the last N days.
        """
        if not company.active:
            logger.debug(f"Skipping inactive company: {company.ticker}")
            return 0
        
        press_url = company.press_release_url or company.ir_url
        
        if not press_url:
            logger.warning(f"No IR URL for {company.ticker} - skipping")
            return 0
        
        if not company.press_release_url and company.ir_url:
            found_url = self.find_press_release_page(company.ir_url)
            if found_url:
                company.press_release_url = found_url
                self.db_session.commit()
                press_url = found_url
        
        logger.info(f"Scraping {company.ticker} at {press_url}")
        
        releases = self.extract_press_releases(press_url, company)
        
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        recent_releases = [r for r in releases if r.get('date') and r['date'] >= cutoff_date]
        
        new_count = 0
        
        for release_data in recent_releases:
            existing = self.db_session.query(PressRelease).filter_by(
                url=release_data['url']
            ).first()
            
            if existing:
                logger.debug(f"Already have: {release_data['title'][:50]}")
                continue
            
            content = self.fetch_press_release_content(release_data['url'])
            
            press_release = PressRelease(
                company_id=company.id,
                title=release_data['title'],
                url=release_data['url'],
                published_date=release_data['date'],
                content=content,
                category=None,
                included_in_newsletter=True
            )
            
            self.db_session.add(press_release)
            new_count += 1
            
            logger.info(f"  ✓ New release: {release_data['title'][:60]}")
            self.db_session.commit()
        
        return new_count
    
    # ─────────────────────────────────────────────────────
    # MAIN ORCHESTRATOR (UPDATED WITH ROUTING)
    # ─────────────────────────────────────────────────────
    
    def scrape_all_companies(self, lookback_days=14, rss_only=False, parallel=False, max_workers=10):
        """
        Scrape all active companies, routing to the right scraper by platform.

        CONSOLIDATED ORCHESTRATOR (SOLID Principle) - handles both serial and parallel execution.

        Routing priority:
          1. GCS (if ir_url contains 'gcs-web.com')
          2. Q4 variants (Drupal HTML/JS, Detail, PDF)
          3. Custom scrapers (Investis, Apollo, Welltower, etc.)
          4. Legacy HTML fallback (everything else)

        Args:
            lookback_days: How far back to look for releases (default: 14)
            rss_only: Deprecated parameter (kept for backwards compatibility)
            parallel: If True, use parallel execution (default: False)
            max_workers: Max concurrent threads for parallel mode (default: 10)

        Returns:
            int: Total number of new releases found
        """
        # 1. Fetch all active companies
        companies = self.db_session.query(Company).filter(
            Company.active == True,
            Company.ir_url.isnot(None)
        ).all()

        mode = "PARALLEL" if parallel else "SERIAL"
        logger.info(f"Starting {mode} scrape of {len(companies)} companies (lookback={lookback_days}d)")
        if parallel:
            logger.info(f"  Max workers: {max_workers}")

        # 2. Filter companies based on rss_only mode
        companies_to_scrape = [] if rss_only else companies

        # 3. Execute based on mode
        if parallel:
            return self._scrape_parallel(companies_to_scrape, lookback_days, max_workers)
        else:
            return self._scrape_serial(companies_to_scrape, lookback_days, rss_only)

    def _scrape_serial(self, companies, lookback_days, rss_only):
        """
        SOLID: Single Responsibility - Serial scraping execution

        Args:
            companies: List of Company instances to scrape
            lookback_days: How far back to scrape
            rss_only: Deprecated parameter

        Returns:
            int: Total number of new releases
        """
        total_new = 0
        results = defaultdict(int)

        for i, company in enumerate(companies, 1):
            try:
                platform = company.ir_platform or 'unknown'
                logger.info(f"\n[{i}/{len(companies)}] {company.ticker} (platform={platform})")

                # Route to appropriate scraper using Strategy Pattern
                new_count, platform_key = self._route_to_scraper(company, lookback_days)
                results[platform_key] += new_count

                total_new += new_count
                time.sleep(RATE_LIMIT_DELAY)  # Rate limiting

            except Exception as e:
                logger.error(f"Failed to scrape {company.ticker}: {e}")
                results['failed'] += 1
                continue

        # Log summary
        self._log_serial_summary(results, total_new)
        return total_new

    def _scrape_parallel(self, companies, lookback_days, max_workers):
        """
        SOLID: Single Responsibility - Parallel scraping execution

        Args:
            companies: List of Company instances to scrape
            lookback_days: How far back to scrape
            max_workers: Max concurrent threads

        Returns:
            int: Total number of new releases
        """
        # Set up shared state
        results = defaultdict(int)
        results_lock = Lock()

        # Create worker function
        worker_func = self._create_scrape_worker(lookback_days, results, results_lock)

        # Execute parallel scraping
        start_time = time.time()
        total_new = self._execute_parallel_scraping(companies, max_workers, worker_func)
        elapsed = time.time() - start_time

        # Log summary
        self._log_parallel_summary(len(companies), results, elapsed, total_new)
        return total_new

    def _log_serial_summary(self, results, total_new):
        """SOLID: Single Responsibility - Log serial scraping summary"""
        logger.info(f"\n{SEPARATOR_LINE}")
        logger.info(f"Scraping complete!")
        logger.info(f"  GCS:           {results['gcs']} new releases")
        logger.info(f"  WordPress PDF: {results['wordpress_pdf']} new releases")
        logger.info(f"  Q4 PDF:        {results['q4_pdf']} new releases")
        logger.info(f"  Q4 JavaScript: {results['q4_js']} new releases")
        logger.info(f"  Q4 Drupal:     {results['q4_drupal']} new releases")
        logger.info(f"  HTML fallback: {results['html_fallback']} new releases")
        logger.info(f"  Skipped:       {results['skipped']}")
        logger.info(f"  Failed:        {results['failed']}")
        logger.info(f"  TOTAL NEW:     {total_new}")
        logger.info(SEPARATOR_LINE)

    def _log_parallel_summary(self, companies_count, results, elapsed, total_new):
        """SOLID: Single Responsibility - Log parallel scraping summary"""
        logger.info(f"\n{SEPARATOR_LINE}")
        logger.info(f"PARALLEL SCRAPING COMPLETE")
        logger.info(SEPARATOR_LINE)
        logger.info(f"  Time elapsed:  {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"  Companies:     {companies_count}")
        logger.info(f"  GCS:           {results['gcs']} new releases")
        logger.info(f"  Q4 JavaScript: {results['q4_js']} new releases")
        logger.info(f"  Q4 Drupal:     {results['q4_drupal']} new releases")
        logger.info(f"  HTML fallback: {results['html_fallback']} new releases")
        logger.info(f"  Failed:        {results['failed']}")
        logger.info(f"  TOTAL NEW:     {total_new}")
        logger.info(SEPARATOR_LINE)

    # ═══════════════════════════════════════════════════════════
    # HELPER METHODS - SOLID Principle: Single Responsibility
    # ═══════════════════════════════════════════════════════════

    def _create_scrape_worker(self, lookback_days, results, results_lock):
        """
        SOLID: Single Responsibility - Creates thread worker function
        Returns: Worker function for ThreadPoolExecutor
        """
        def scrape_single_company(company, platform_type):
            """Worker function that runs in a thread"""
            try:
                # Each thread gets its own DB session and scraper
                engine = init_db()
                thread_db = get_session(engine)
                thread_scraper = PressReleaseScraper()
                thread_scraper.db_session = thread_db

                # Re-fetch company in this thread's session
                thread_company = thread_db.query(Company).filter_by(id=company.id).first()

                platform = thread_company.ir_platform or 'unknown'
                ticker = thread_company.ticker

                # Route to appropriate scraper using Strategy Pattern
                new_count, result_key = thread_scraper._route_to_scraper(thread_company, lookback_days)

                # Update shared results (thread-safe)
                with results_lock:
                    if result_key:
                        results[result_key] += new_count

                logger.info(f"✓ {ticker} ({platform}): {new_count} new")

                # Cleanup
                thread_scraper.close()
                thread_db.close()

                return (ticker, new_count, None)

            except Exception as e:
                logger.error(f"✗ {company.ticker}: {e}")
                with results_lock:
                    results['failed'] += 1
                return (company.ticker, 0, str(e))

        return scrape_single_company

    def _execute_parallel_scraping(self, companies, max_workers, worker_func):
        """
        SOLID: Single Responsibility - Manages thread pool execution
        Returns: Total count of new releases
        """
        logger.info(f"\n{SEPARATOR_LINE}")
        logger.info(f"SCRAPING {len(companies)} COMPANIES")
        logger.info(SEPARATOR_LINE)

        total_new = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(worker_func, company, 'browser'): company
                for company in companies
            }

            for future in as_completed(futures):
                ticker, count, error = future.result()
                total_new += count

        return total_new

    def scrape_all_companies_parallel(self, lookback_days=14, rss_only=False, max_browser_workers=10, max_rss_workers=20):
        """
        DEPRECATED: Use scrape_all_companies(parallel=True) instead.
        Maintained for backwards compatibility.

        Args:
            lookback_days: How far back to look for releases
            rss_only: Deprecated parameter
            max_browser_workers: Max concurrent browser instances
            max_rss_workers: Deprecated (kept for compatibility)

        Returns:
            Total number of new releases found
        """
        logger.warning("scrape_all_companies_parallel is deprecated. Use scrape_all_companies(parallel=True) instead.")
        return self.scrape_all_companies(
            lookback_days=lookback_days,
            rss_only=rss_only,
            parallel=True,
            max_workers=max_browser_workers
        )

    # Platform detection methods moved to utils/platform_registry.py (SOLID Principle)

    def detect_platform(self, company):
        """
        Auto-detect the correct scraper platform for a company by testing patterns.
        Delegates to PlatformRegistry (SOLID Principle).

        Args:
            company: Company model instance

        Returns:
            str: Platform identifier ('q4_detail', 'q4_js', 'gcs_with_dates', etc.) or None
        """
        return PlatformRegistry.detect_platform(self, company)

    def detect_and_update_platforms(self, auto_commit=True):
        """
        Find all companies with NULL platforms and auto-detect their platform.
        Updates the database with detected platforms.

        Args:
            auto_commit: If True, commit after each successful detection (default)

        Returns:
            dict: Summary of results {'detected': int, 'failed': int, 'already_set': int}
        """
        # Query for companies needing platform detection
        companies = self.db_session.query(Company).filter(
            Company.ir_platform.is_(None),
            Company.active == True
        ).order_by(Company.ticker).all()

        logger.info(f"Found {len(companies)} companies with NULL platform")

        results = {'detected': 0, 'failed': 0, 'already_set': 0}

        for company in companies:
            logger.info(f"\n[{company.ticker}] {company.name}")

            platform = self.detect_platform(company)

            if platform:
                company.ir_platform = platform
                results['detected'] += 1

                if auto_commit:
                    self.db_session.commit()
                    logger.info(f"[{company.ticker}] ✓ Updated to platform: {platform}")
            else:
                results['failed'] += 1
                logger.warning(f"[{company.ticker}] ✗ Could not detect platform")

            # Be polite - wait between requests
            time.sleep(RATE_LIMIT_DELAY_SHORT)

        if not auto_commit and results['detected'] > 0:
            self.db_session.commit()
            logger.info(f"\nCommitted {results['detected']} platform updates")

        return results

    def close(self):
        """Clean up resources"""
        if self.browser:
            self.browser.close()
            logger.info("Playwright browser closed")
        if self.playwright:
            self.playwright.stop()
        self.db_session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='REIT Press Release Scraper')
    parser.add_argument('--rss-only', action='store_true', help='Only scrape RSS feeds')
    parser.add_argument('--q4-drupal-only', action='store_true', help='Only scrape Q4 Drupal companies')
    parser.add_argument('--ticker', type=str, help='Scrape a single company by ticker')
    parser.add_argument('--lookback', type=int, default=14, help='Lookback days (default: 14)')
    parser.add_argument('--detect-platforms', action='store_true', help='Auto-detect platforms for companies with NULL ir_platform')
    args = parser.parse_args()

    scraper = PressReleaseScraper()

    try:
        if args.detect_platforms:
            # Auto-detect and update platforms
            logger.info("Starting platform auto-detection...")
            results = scraper.detect_and_update_platforms()
            logger.info("\n" + "="*60)
            logger.info(f"Platform Detection Results:")
            logger.info(f"  ✓ Detected and updated: {results['detected']}")
            logger.info(f"  ✗ Failed to detect: {results['failed']}")
            logger.info("="*60)

        elif args.ticker:
            # Single company mode
            company = scraper.db_session.query(Company).filter_by(
                ticker=args.ticker.upper()
            ).first()
            if not company:
                logger.error(f"Company not found: {args.ticker}")
            else:
                # Use centralized routing (DRY principle)
                count, _ = scraper._route_to_scraper(company, args.lookback)
                logger.info(f"Done: {count} new releases for {company.ticker}")
        
        elif args.q4_drupal_only:
            # Only Q4 Drupal companies
            companies = scraper.db_session.query(Company).filter(
                Company.active == True,
                Company.ir_platform == 'q4_drupal'
            ).all()
            logger.info(f"Scraping {len(companies)} Q4 Drupal companies")
            total = 0
            for i, company in enumerate(companies, 1):
                logger.info(f"\n[{i}/{len(companies)}] {company.ticker}")
                total += scraper.scrape_html_q4_drupal(company, args.lookback)
                time.sleep(RATE_LIMIT_DELAY)
            logger.info(f"\nDone: {total} total new releases")
        
        else:
            scraper.scrape_all_companies(
                lookback_days=args.lookback,
                rss_only=args.rss_only
            )
    finally:
        scraper.close()
